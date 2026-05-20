"""Round 5 experiment monitor & full-dimensional status reporter.

Lifecycle:
    1. t+2min   -> initialization check (config, generator stats, first batch status)
    2. t+10min   -> full-dimensional heartbeat (repeats every 10 min)
    3. completed -> final summary + target achievement report

Usage:
    # Attached mode (launches experiment + monitors)
    python experiments/monitor_round5.py --candidates 100

    # Standalone mode (attaches to a running experiment log)
    python experiments/monitor_round5.py --attach LOG_PATH
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


_EXPERIMENT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _EXPERIMENT_DIR.parent


# ===========================================================================
# Round 5 baseline values & targets
# ===========================================================================

@dataclass
class Round5Targets:
    """Round 5 metrics — baselines (Round 4) vs targets."""

    # -- Generation quality --
    strategy_families:          Tuple[int, int] = (4, 13)      # (was, target)
    templates:                  Tuple[int, int] = (10, 64)     # (was, target — ts_cov removed)
    safe_fields:                Tuple[int, int] = (8, 22)      # (was, target)
    rejection_rate_pct:         Tuple[float, float] = (0.0, 0.0)  # (was, must stay)

    # -- Sharpe distribution --
    sharpe_ge_125_pct:          Tuple[float, float] = (2.1, 5.0)   # >= 1.25
    sharpe_ge_100_pct:          Tuple[float, float] = (10.4, 15.0) # >= 1.0
    sharpe_ge_050_pct:          Tuple[float, float] = (22.9, 30.0) # >= 0.5
    sharpe_positive_pct:        Tuple[float, float] = (48.0, 55.0) # > 0
    negative_sharpe_pct:        Tuple[float, float] = (52.0, 40.0) # < 0 (want lower)

    # -- Extremes --
    max_sharpe:                 Tuple[float, float] = (1.38, 1.75) # was, target
    mean_sharpe:                Tuple[float, float] = (-0.092, 0.0) # was, target

    # -- Correlation blocking --
    correlation_block_pct:      Tuple[float, float] = (float("nan"), float("nan"))
    # ^^ baseline unknown (first measurement); set after initial parse

    def all_metrics(self) -> Dict[str, Tuple[float, float]]:
        return {
            k: v for k, v in self.__dict__.items()
            if isinstance(v, tuple) and len(v) == 2
        }


# ===========================================================================
# Status snapshot data model
# ===========================================================================

@dataclass
class ExperimentSnapshot:
    """Full-dimensional status at a point in time."""
    timestamp: datetime
    elapsed: str                                  # "HH:MM:SS"

    # -- Progress --
    total_candidates: int = 0
    completed: int = 0
    failed: int = 0
    in_flight: int = 0
    progress_pct: float = 0.0

    # -- Generation (parsed from log) --
    generated_count: int = 0
    pre_validation_rejects: int = 0
    themes_used: List[str] = field(default_factory=list)
    theme_families_count: int = 0

    # -- Sharpe distribution --
    sharpes: List[float] = field(default_factory=list)
    sharpe_ge_125: int = 0
    sharpe_ge_100: int = 0
    sharpe_ge_050: int = 0
    sharpe_positive: int = 0
    sharpe_negative: int = 0
    max_sharpe: float = float("-inf")
    min_sharpe: float = float("inf")
    mean_sharpe: float = 0.0

    # -- Failure breakdown --
    failure_reasons: Counter = field(default_factory=Counter)

    # -- Throughput --
    completed_since_last: int = 0
    rate_per_min: float = 0.0
    eta_minutes: float = 0.0

    # -- Equipment health --
    pid: int = 0
    log_size_mb: float = 0.0
    stalled: bool = False
    stall_duration_min: float = 0.0

    def _compute_sharpe_stats(self) -> None:
        if not self.sharpes:
            return
        self.sharpe_ge_125 = sum(1 for s in self.sharpes if s >= 1.25)
        self.sharpe_ge_100 = sum(1 for s in self.sharpes if s >= 1.0)
        self.sharpe_ge_050 = sum(1 for s in self.sharpes if s >= 0.5)
        self.sharpe_positive = sum(1 for s in self.sharpes if s > 0)
        self.sharpe_negative = sum(1 for s in self.sharpes if s < 0)
        self.max_sharpe = max(self.sharpes)
        self.min_sharpe = min(self.sharpes)
        self.mean_sharpe = round(sum(self.sharpes) / len(self.sharpes), 4)


# ===========================================================================
# Data collectors
# ===========================================================================

class DataCollector:
    """Read experiment progress from intermediate results JSON + log file."""

    def __init__(self, results_path: Path, log_path: Optional[Path] = None):
        self._results = results_path
        self._log = log_path
        self._last_completed = 0

    def snapshot(self) -> ExperimentSnapshot:
        results = self._load_results()
        total = results.get("total", 0)
        completed = results.get("completed", 0)
        failed = results.get("failed", 0)

        snap = ExperimentSnapshot(
            timestamp=datetime.now(),
            elapsed=self._elapsed_from_log(),
            total_candidates=total,
            completed=completed,
            failed=failed,
            in_flight=total - completed - failed,
            progress_pct=round((completed + failed) / max(total, 1) * 100, 1),
        )

        # Parse individual result records
        records = results.get("results", [])
        sharpes = self._extract_sharpes(records)
        snap.sharpes = sharpes
        snap._compute_sharpe_stats()

        # Failure breakdown
        snap.failure_reasons = self._classify_failures(records)

        # Generation stats from log
        self._parse_generation_from_log(snap)

        # Health
        snap.pid = self._pid_from_log()
        snap.log_size_mb = self._log_size_mb()

        # Throughput
        completed_delta = max(0, completed - self._last_completed)
        snap.completed_since_last = completed_delta
        snap.rate_per_min = self._estimate_rate()
        snap.eta_minutes = self._estimate_eta(snap)

        self._last_completed = completed
        return snap

    def _load_results(self) -> dict:
        if not self._results.exists():
            return {}
        try:
            return json.loads(self._results.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _elapsed_from_log(self) -> str:
        """Infer elapsed time from log mtime or first timestamp."""
        if self._log and self._log.exists():
            try:
                text = self._log.read_text(encoding="utf-8", errors="replace")[:2000]
                m = re.search(r'\[(\d{2}:\d{2}:\d{2})\]', text)
                if m:
                    start_t = m.group(1)
                    now = datetime.now().strftime("%H:%M:%S")
                    # Approximate — use file mtime as fallback
                    mtime = datetime.fromtimestamp(self._log.stat().st_mtime)
                    return str(timedelta(seconds=int(time.time() - self._log.stat().st_ctime)))
            except Exception:
                pass
        return "??:??:??"

    def _extract_sharpes(self, records: list) -> List[float]:
        out = []
        for r in records:
            if r.get("status") not in ("completed",):
                continue
            s = r.get("sharpe")
            if s is None:
                continue
            try:
                v = float(s)
            except (TypeError, ValueError):
                continue
            out.append(v)
        return out

    def _classify_failures(self, records: list) -> Counter:
        counter: Counter = Counter()
        for r in records:
            if r.get("status") in ("completed",):
                continue
            detail = str(r.get("error", "") or r.get("brain_failure_detail", ""))[:80]
            if not detail:
                detail = str(r.get("status", "unknown"))
            counter[detail] += 1
        return counter

    def _parse_generation_from_log(self, snap: ExperimentSnapshot) -> None:
        if not self._log or not self._log.exists():
            return
        try:
            text = self._log.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return

        # Generation count
        m = re.search(r'Generated\s+(\d+)\s+candidates', text)
        if m:
            snap.generated_count = int(m.group(1))

        # Pre-validation rejects
        m = re.search(r'(\d+)\s+rejected\s+by\s+pre-validation', text)
        if m:
            snap.pre_validation_rejects = int(m.group(1))

        # Themes detected in generated expressions
        m = re.search(r'Generated\s+\d+\s+candidates:', text)
        if not m:
            m = re.search(r'Generated \d+ candidates', text)

    def _pid_from_log(self) -> int:
        if self._log and self._log.exists():
            try:
                text = self._log.read_text(encoding="utf-8", errors="replace")[:500]
                m = re.search(r'pid[=:]?\s*(\d+)', text)
                if m:
                    return int(m.group(1))
            except Exception:
                pass
        return 0

    def _log_size_mb(self) -> float:
        if self._log and self._log.exists():
            return round(self._log.stat().st_size / (1024 * 1024), 2)
        return 0.0

    def _estimate_rate(self) -> float:
        if not self._log or not self._log.exists():
            return 0.0
        mtime = self._log.stat().st_mtime
        age_s = max(1, time.time() - self._log.stat().st_ctime)
        age_min = age_s / 60.0
        results = self._load_results()
        done = results.get("completed", 0) + results.get("failed", 0)
        return round(done / max(age_min, 0.1), 2)

    def _estimate_eta(self, snap: ExperimentSnapshot) -> float:
        remaining = snap.total_candidates - snap.completed - snap.failed
        rate = snap.rate_per_min
        if rate <= 0:
            return float("inf")
        return round(remaining / rate, 1)




# ===========================================================================
# Full-dimensional reporter
# ===========================================================================

class FullDimensionalReporter:
    """Format snapshots into structured, readable output."""

    BOX_WIDTH = 64
    SEP = "-" * BOX_WIDTH
    THIN = "·" * BOX_WIDTH

    def __init__(self, targets: Round5Targets):
        self._t = targets
        self._last_timestamp: Optional[datetime] = None

    def init_report(self, snap: ExperimentSnapshot) -> str:
        """Initialization report at t+2min."""
        self._last_timestamp = snap.timestamp
        lines = []
        lines.append("")
        lines.append("+" + "=" * 60 + "+")
        lines.append("║" + "  Round 5 实验 · 初始化状态检查 (t+2min)".center(62) + "║")
        lines.append("+" + "=" * 60 + "+")
        lines.append(f"  时间: {snap.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"  PID : {snap.pid or '(pending)'}")
        lines.append(f"  日志: {snap.log_size_mb} MB")
        lines.append("")
        lines.append(self._section("[~] 配置基线 vs Round 5 目标"))
        lines.extend(self._config_target_table())
        lines.append("")
        lines.append(self._section("[i] 初始状态"))
        lines.extend(self._progress_table(snap))
        lines.append("")
        lines.append(self._section("[T] 调度"))
        lines.append(f"  下一轮全维度汇报: {self._next_report_time(snap.timestamp, 10)}")
        lines.append(f"  汇报间隔: 10 分钟")
        lines.append(self.SEP)
        return "\n".join(lines)

    def heartbeat_report(self, snap: ExperimentSnapshot) -> str:
        """Full-dimensional status report every 10 min."""
        ts = snap.timestamp.strftime("%H:%M:%S")
        lines = []
        lines.append("")
        lines.append("+" + "-" * 60 + "+")
        lines.append(f"|  Round 5 全维度状态汇报  [{ts}]".ljust(63) + "|")
        lines.append("+" + "-" * 60 + "+")
        lines.append(f"  已运行: {snap.elapsed}  |  PID: {snap.pid}")
        lines.append("")

        # === Section 1: Progress ===
        lines.append(self._section("= 1. 实验进度"))
        lines.extend(self._progress_table(snap))
        lines.append(f"  吞吐: {snap.rate_per_min}/min  |  ETA: {self._fmt_eta(snap.eta_minutes)}")

        # === Section 2: Sharpe Distribution ===
        lines.append("")
        lines.append(self._section("= 2. Sharpe 分布"))
        lines.extend(self._sharpe_table(snap))

        # === Section 3: Target Achievement ===
        lines.append("")
        lines.append(self._section("= 3. 目标达成率 (Round 4 -> Round 5 目标)"))
        lines.extend(self._achievement_table(snap))

        # === Section 4: Failure Breakdown ===
        lines.append("")
        lines.append(self._section("= 4. 失败分类"))
        lines.extend(self._failure_table(snap))

        # === Section 5: Key Metrics Board ===
        lines.append("")
        lines.append(self._section("= 5. 关键指标看板"))
        lines.extend(self._dashboard(snap))

        # === Footer ===
        lines.append("")
        lines.append(f"  下一轮汇报: {self._next_report_time(snap.timestamp, 10)}")
        delta = snap.completed_since_last
        lines.append(f"  本周期完成: {delta} 个候选  |  速率: {snap.rate_per_min}/min")
        lines.append(self.SEP)

        self._last_timestamp = snap.timestamp
        return "\n".join(lines)

    def final_report(self, snap: ExperimentSnapshot) -> str:
        """Final summary after experiment ends."""
        lines = []
        lines.append("")
        lines.append("+" + "=" * 60 + "+")
        lines.append("║" + "  Round 5 实验完成 · 最终报告".center(62) + "║")
        lines.append("+" + "=" * 60 + "+")
        lines.append(f"  完成时间: {snap.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"  总耗时: {snap.elapsed}")
        lines.append("")
        lines.append(self._section("= 最终进度"))
        lines.extend(self._progress_table(snap))
        lines.append("")
        lines.append(self._section("= 最终 Sharpe 分布"))
        lines.extend(self._sharpe_table(snap))
        lines.append("")
        lines.append(self._section("= 最终目标达成"))
        lines.extend(self._achievement_table(snap))
        lines.append("")
        lines.append(self._section("= 失败总结"))
        lines.extend(self._failure_table(snap))
        lines.append("")
        lines.append(self._section("= Round 5 结论"))
        lines.extend(self._verdict(snap))
        lines.append("")
        lines.append("+" + "=" * 60 + "+")
        return "\n".join(lines)

    # -- Sub-tables ------------------------------------------------------

    def _config_target_table(self) -> List[str]:
        rows = [
            f"  {'指标':<28} {'Round 4':>8} {'-> Round 5':>10}",
            f"  {'-'*28} {'-'*8} {'-'*10}",
        ]
        conf = [
            ("策略族", *self._t.strategy_families),
            ("模板数", *self._t.templates),
            ("SAFE_FIELDS", *self._t.safe_fields),
            ("拒绝率 %", *self._t.rejection_rate_pct),
        ]
        for name, was, target in conf:
            rows.append(f"  {name:<28} {was:>8} -> {target:>10}")
        return rows

    def _progress_table(self, snap: ExperimentSnapshot) -> List[str]:
        rows = [
            f"  总候选: {snap.total_candidates}  |  "
            f"已完成: {snap.completed}  |  "
            f"失败: {snap.failed}  |  "
            f"进行中: {snap.in_flight}",
            f"  进度: {snap.progress_pct}%  "
            f"{self._bar(snap.progress_pct)}",
        ]
        if snap.generated_count:
            rows.append(
                f"  生成: {snap.generated_count}  |  "
                f"预检拒绝: {snap.pre_validation_rejects}"
            )
        return rows

    def _sharpe_table(self, snap: ExperimentSnapshot) -> List[str]:
        n = max(len(snap.sharpes), 1)
        return [
            f"  样本数: {n}",
            f"  {'等级':<16} {'数量':>6} {'占比':>8} {'目标':>8}",
            f"  {'-'*16} {'-'*6} {'-'*8} {'-'*8}",
            f"  >= 1.25  {'(金)':<5} {snap.sharpe_ge_125:>6} {self._pct(snap.sharpe_ge_125,n):>7}% {self._mark(snap.sharpe_ge_125/n*100, self._t.sharpe_ge_125_pct[1], 5.0)}",
            f"  >= 1.00  {'(银)':<5} {snap.sharpe_ge_100:>6} {self._pct(snap.sharpe_ge_100,n):>7}% {self._mark(snap.sharpe_ge_100/n*100, self._t.sharpe_ge_100_pct[1], 15.0)}",
            f"  >= 0.50  {'(铜)':<5} {snap.sharpe_ge_050:>6} {self._pct(snap.sharpe_ge_050,n):>7}% {self._mark(snap.sharpe_ge_050/n*100, self._t.sharpe_ge_050_pct[1], 30.0)}",
            f"  > 0     {'(正)':<5} {snap.sharpe_positive:>6} {self._pct(snap.sharpe_positive,n):>7}%",
            f"  < 0     {'(负)':<5} {snap.sharpe_negative:>6} {self._pct(snap.sharpe_negative,n):>7}% {self._mark_lt(snap.sharpe_negative/n*100, self._t.negative_sharpe_pct[1])}",
            f"  {'-'*16} {'-'*6} {'-'*8} {'-'*8}",
            f"  {'Max Sharpe':<16} {snap.max_sharpe:>6.3f}",
            f"  {'Min Sharpe':<16} {snap.min_sharpe:>6.3f}",
            f"  {'Mean Sharpe':<16} {snap.mean_sharpe:>6.4f}",
        ]

    def _achievement_table(self, snap: ExperimentSnapshot) -> List[str]:
        n = max(len(snap.sharpes), 1)
        rows = [
            f"  {'指标':<28} {'Round 4':>7} {'当前':>7} {'目标':>7} {'达成':>5}",
            f"  {'-'*28} {'-'*7} {'-'*7} {'-'*7} {'-'*5}",
        ]
        metrics = [
            (">= 1.25 %",    2.1,  self._pct_val(snap.sharpe_ge_125, n), 5.0),
            (">= 1.00 %",    10.4, self._pct_val(snap.sharpe_ge_100, n), 15.0),
            (">= 0.50 %",    22.9, self._pct_val(snap.sharpe_ge_050, n), 30.0),
            ("正 Sharpe %", 48.0, self._pct_val(snap.sharpe_positive, n), 55.0),
            ("负 Sharpe %", 52.0, self._pct_val(snap.sharpe_negative, n), 40.0, True),
            ("Max Sharpe",  1.38, snap.max_sharpe, 1.75),
            ("Mean Sharpe", -0.092, snap.mean_sharpe, 0.0),
        ]
        for name, was, now, target, *lower_better in metrics:
            lb = lower_better[0] if lower_better else False
            achieve = self._rate_achievement(was, now, target, lb)
            rows.append(f"  {name:<28} {was:>7.3f} {now:>7.3f} {target:>7.3f} {achieve:>5}")
        return rows

    def _failure_table(self, snap: ExperimentSnapshot) -> List[str]:
        if not snap.failure_reasons:
            return ["  (无失败记录)"]
        rows = [f"  {'原因':<40} {'次数':>6}"]
        rows.append(f"  {'-'*40} {'-'*6}")
        for reason, count in snap.failure_reasons.most_common(8):
            rows.append(f"  {reason[:40]:<40} {count:>6}")
        return rows

    def _dashboard(self, snap: ExperimentSnapshot) -> List[str]:
        n = max(len(snap.sharpes), 1)
        return [
            f"  生成器: validated_generator (64 模板, 13 策略族)",
            f"  多样性: Jaccard < 0.68 | 分层窗口 (短/中/长) | Quality pre-filter",
            f"  字段: 22 verified BRAIN fields | 10 分类池",
            f"  >=1.25 达标: {'[OK]' if snap.sharpe_ge_125 / n * 100 >= self._t.sharpe_ge_125_pct[1] else '[...]'} "
            f"  >=1.00 达标: {'[OK]' if snap.sharpe_ge_100 / n * 100 >= self._t.sharpe_ge_100_pct[1] else '[...]'} "
            f"  负Sharpe: {'[OK]' if snap.sharpe_negative / n * 100 <= self._t.negative_sharpe_pct[1] else '[...]'}",
        ]

    def _verdict(self, snap: ExperimentSnapshot) -> List[str]:
        n = max(len(snap.sharpes), 1)
        results = []
        p125 = self._pct_val(snap.sharpe_ge_125, n)
        p100 = self._pct_val(snap.sharpe_ge_100, n)
        neg = self._pct_val(snap.sharpe_negative, n)

        results.append(f"  Round 4 基线 -> Round 5 实际 -> 目标")
        results.append(f"  Sharpe >= 1.25: {2.1}% -> {p125:.1f}% -> 5.0%  "
                       f"{'[OK] 达成' if p125 >= 5.0 else '[X] 未达成'}")
        results.append(f"  Sharpe >= 1.00: {10.4}% -> {p100:.1f}% -> 15.0%  "
                       f"{'[OK] 达成' if p100 >= 15.0 else '[X] 未达成'}")
        results.append(f"  负 Sharpe 率: {52.0}% -> {neg:.1f}% -> <40.0%  "
                       f"{'[OK] 达成' if neg <= 40.0 else '[X] 未达成'}")
        results.append(f"  Max Sharpe:    {1.38} -> {snap.max_sharpe:.3f} -> 1.75  "
                       f"{'[OK] 达成' if snap.max_sharpe >= 1.75 else '[X] 未达成'}")

        passed = sum([
            p125 >= 5.0, p100 >= 15.0, neg <= 40.0,
            snap.max_sharpe >= 1.75,
        ])
        results.append(f"")
        results.append(f"  目标达成: {passed}/4  -> {'*** 全部达标' if passed == 4 else f'[...] 完成 {passed}/4'}")
        return results

    # -- Helpers ---------------------------------------------------------

    @staticmethod
    def _section(title: str) -> str:
        return f"  {title}"

    @staticmethod
    def _pct(num: int, total: int) -> str:
        if total == 0:
            return "  0.0"
        return f"{num/total*100:6.1f}"

    @staticmethod
    def _pct_val(num: int, total: int) -> float:
        if total == 0:
            return 0.0
        return round(num / total * 100, 1)

    @staticmethod
    def _mark(current: float, target: float, _target_raw: float = 0) -> str:
        if current >= target:
            return "[OK]"
        return "[...]"

    @staticmethod
    def _mark_lt(current: float, target: float) -> str:
        if current <= target:
            return "[OK]"
        return "[...]"

    @staticmethod
    def _rate_achievement(was: float, now: float, target: float, lower_better: bool = False) -> str:
        import math
        if was == target:
            return "N/A"
        if math.isinf(now) or math.isnan(now):
            return "--"
        if lower_better:
            gap = was - target
            progress = was - now
        else:
            gap = target - was
            progress = now - was
        if gap <= 0 or math.isinf(gap) or math.isnan(gap):
            return "[OK]"
        if math.isinf(progress) or math.isnan(progress):
            return "--"
        pct = min(100, max(0, round(progress / gap * 100)))
        bar_len = 4
        filled = round(pct / 100 * bar_len)
        bar = "#" * filled + "." * (bar_len - filled)
        return bar

    @staticmethod
    def _bar(pct: float, width: int = 20) -> str:
        filled = round(pct / 100 * width)
        return "[" + "#" * filled + "." * (width - filled) + "]"

    @staticmethod
    def _fmt_eta(minutes: float) -> str:
        if minutes == float("inf") or minutes < 0:
            return "计算中..."
        if minutes < 1:
            return "<1 min"
        return f"~{int(minutes)} min"

    @staticmethod
    def _next_report_time(now: datetime, interval: int) -> str:
        return (now + timedelta(minutes=interval)).strftime("%H:%M:%S")


# ===========================================================================
# Monitor engine — timed task scheduler
# ===========================================================================

class Round5Monitor:
    """Orchestrates: launch -> init-check (2min) -> heartbeat (10min) -> final"""

    INIT_CHECK_DELAY_SEC = 120        # t+2min
    HEARTBEAT_INTERVAL_SEC = 600     # every 10 min

    def __init__(
        self,
        candidate_count: int = 100,
        *,
        log_path: Optional[Path] = None,
        results_path: Optional[Path] = None,
        targets: Optional[Round5Targets] = None,
        attach_only: bool = False,
    ):
        self._count = candidate_count
        self._log_path = log_path or (_EXPERIMENT_DIR / "experiment_r5.log")
        self._results_path = results_path or (_EXPERIMENT_DIR / "_intermediate_results.json")
        self._targets = targets or Round5Targets()
        self._attach_only = attach_only
        self._proc: Optional[subprocess.Popen] = None
        self._start_time: Optional[datetime] = None

    def launch(self) -> None:
        """Start experiment subprocess (skipped in attach mode)."""
        if self._attach_only:
            print("  [attach] 外部进程模式 — 读取现有日志")
            self._start_time = datetime.now()
            return

        python = sys.executable
        cmd = [
            python, "-u",
            str(_EXPERIMENT_DIR / "_run_simple.py"),
            "--candidates", str(self._count),
        ]
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        log_fh = open(self._log_path, "w", encoding="utf-8")
        # Pass BRAIN credentials from parent environment
        env = os.environ.copy()
        self._proc = subprocess.Popen(
            cmd,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            cwd=str(_PROJECT_ROOT),
            env=env,
        )
        self._start_time = datetime.now()
        log_fh.close()
        print(f"  [launch] 实验已启动  pid={self._proc.pid}  log={self._log_path.name}")

    def run(self) -> int:
        """Main monitoring loop with scheduled tasks."""
        reporter = FullDimensionalReporter(self._targets)
        collector = DataCollector(self._results_path, self._log_path)

        self.launch()
        start = self._start_time or datetime.now()

        print(f"\n{'='*64}")
        print(f"  Round 5 监控系统已就绪")
        print(f"  候选数: {self._count}  |  模式: {'attach' if self._attach_only else 'launch+monitor'}")
        print(f"  初始化检查: t+2min  |  心跳间隔: 10min")
        print(f"{'='*64}\n")

        init_done = False
        last_heartbeat = start
        last_heartbeat_count = 0

        while True:
            now = datetime.now()
            elapsed = (now - start).total_seconds()

            # -- Check if experiment has finished --
            if self._proc is not None and self._proc.poll() is not None:
                # Process exited
                snap = collector.snapshot()
                print(reporter.final_report(snap))
                return self._proc.returncode

            if self._attach_only:
                # In attach mode, check if log has stopped updating
                results = collector._load_results()
                done = results.get("completed", 0) + results.get("failed", 0)
                total = results.get("total", 0)
                if total > 0 and done >= total:
                    snap = collector.snapshot()
                    print(reporter.final_report(snap))
                    return 0

            # -- t+2min: initialization check (once) --
            if not init_done and elapsed >= self.INIT_CHECK_DELAY_SEC:
                snap = collector.snapshot()
                print(reporter.init_report(snap))
                init_done = True
                last_heartbeat = now
                last_heartbeat_count = snap.completed + snap.failed

            # -- every 10min: full-dimensional heartbeat --
            if init_done and (now - last_heartbeat).total_seconds() >= self.HEARTBEAT_INTERVAL_SEC:
                snap = collector.snapshot()
                print(reporter.heartbeat_report(snap))
                last_heartbeat = now
                last_heartbeat_count = snap.completed + snap.failed

            # -- Stall detection --
            if init_done and (now - last_heartbeat).total_seconds() > 1800:
                snap = collector.snapshot()
                if (snap.completed + snap.failed) == last_heartbeat_count:
                    print(f"\n  [WARN] 停滞 {int((now - last_heartbeat).total_seconds()/60)}min "
                          f"— 进度无变化 ({snap.completed + snap.failed}/{snap.total_candidates})")
                    last_heartbeat = now

            time.sleep(15)  # check every 15 seconds

        return 0


# ===========================================================================
# CLI
# ===========================================================================

def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="Round 5 experiment monitor")
    p.add_argument("--candidates", type=int, default=100, help="候选数量")
    p.add_argument("--attach", type=str, default="", help="附加到已有日志")
    p.add_argument("--results", type=str, default="", help="中间结果 JSON 路径")
    args = p.parse_args()

    log_path = Path(args.attach) if args.attach else None
    results_path = Path(args.results) if args.results else None
    attach = bool(args.attach)

    monitor = Round5Monitor(
        candidate_count=args.candidates,
        log_path=log_path,
        results_path=results_path,
        attach_only=attach,
    )
    return monitor.run()


if __name__ == "__main__":
    raise SystemExit(main())
