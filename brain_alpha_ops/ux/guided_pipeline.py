"""用户体验优化 — 流程引导、实时状态反馈、可操作错误提示、断点续跑与历史回溯。

GuidedPipeline — wraps AlphaResearchPipeline with:
  1. Step-by-step process guidance with progress indicators
  2. Real-time status feedback via callback mechanism
  3. Actionable error messages with fix suggestions
  4. Structured result presentation (JSON + human-readable)
  5. Checkpoint/resume mechanism for long-running pipelines
  6. Historical run browser and replay capability

Usage:
    from brain_alpha_ops.ux.guided_pipeline import GuidedPipeline
    gp = GuidedPipeline(run_config)
    gp.run_guided()
"""

from __future__ import annotations

import json
import logging
import os
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.models import Candidate, PipelineEvent, PipelineResult
from brain_alpha_ops.runner import run_pipeline_from_config

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Data Structures
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class PipelinePhase:
    """Single phase in the guided pipeline flow."""
    name: str
    description: str
    status: str = "pending"  # pending | running | completed | failed | skipped
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_seconds: float = 0.0
    result_summary: str = ""
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def start(self) -> None:
        self.status = "running"
        self.started_at = datetime.now(timezone.utc).isoformat()

    def complete(self, summary: str = "") -> None:
        self.status = "completed"
        self.completed_at = datetime.now(timezone.utc).isoformat()
        if self.started_at:
            start = datetime.fromisoformat(self.started_at)
            end = datetime.fromisoformat(self.completed_at)
            self.duration_seconds = (end - start).total_seconds()
        self.result_summary = summary

    def fail(self, error: str) -> None:
        self.status = "failed"
        self.completed_at = datetime.now(timezone.utc).isoformat()
        self.errors.append(error)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "duration_seconds": self.duration_seconds,
            "result_summary": self.result_summary,
            "errors": self.errors,
            "warnings": self.warnings,
        }


@dataclass
class CheckpointData:
    """Serializable checkpoint for pipeline resume."""
    run_id: str
    phase_completed: str  # Last completed phase name
    candidates_generated: int
    simulations_completed: int
    submissions_made: int
    cycle_number: int
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    snapshot: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "phase_completed": self.phase_completed,
            "candidates_generated": self.candidates_generated,
            "simulations_completed": self.simulations_completed,
            "submissions_made": self.submissions_made,
            "cycle_number": self.cycle_number,
            "timestamp": self.timestamp,
            "snapshot": self.snapshot,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CheckpointData":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class RunRecord:
    """Historical run record for browsing and replay."""
    run_id: str
    started_at: str
    completed_at: Optional[str] = None
    status: str = "running"  # running | completed | failed | cancelled
    phases: List[Dict[str, Any]] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    checkpoint_path: str = ""

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "phases": self.phases,
            "summary": self.summary,
            "checkpoint_path": self.checkpoint_path,
        }


# ═══════════════════════════════════════════════════════════════════════
# Error Classification & Actionable Messages
# ═══════════════════════════════════════════════════════════════════════
# Unified error knowledge — delegates to brain_alpha_ops.error_knowledge

from brain_alpha_ops.error_knowledge import classify_ux_error as _unified_classify, UX_ERROR_CODES

# Backward-compat: retain classify_error() with same return shape
def classify_error(error: Exception) -> Dict[str, str]:
    """Classify an error and return actionable guidance (uses unified error_knowledge)."""
    try:
        info = _unified_classify(error)
        return {
            "type": info.error_code or type(error).__name__,
            "message": str(error)[:200],
            "fix": info.fix_hint or "未知错误。请检查日志文件 data/*.log 获取详细信息。",
            "retry": "yes" if info.retryable else ("maybe" if info.retryable is None else "no"),
        }
    except Exception:
        return {
            "type": type(error).__name__,
            "message": str(error)[:200],
            "fix": "未知错误。请检查日志文件 data/*.log 获取详细信息。",
            "retry": "maybe",
        }


# ═══════════════════════════════════════════════════════════════════════
# Guided Pipeline
# ═══════════════════════════════════════════════════════════════════════

class GuidedPipeline:
    """用户体验优化管道 — 包装标准流水线，增加流程引导和反馈。

    使用方式:
        gp = GuidedPipeline(run_config)
        gp.run_guided()  # 交互式运行

        # 或查看历史
        gp.list_history()
        gp.show_run("run_20260517_001")
    """

    PHASES = [
        ("init", "环境初始化与连接验证"),
        ("context", "BRAIN 平台上下文加载 (字段/算子/数据集)"),
        ("redline", "技术红线合规验证"),
        ("generation", "Alpha 候选生成"),
        ("validation", "本地质量评估与排序"),
        ("simulation", "BRAIN 官方回测仿真"),
        ("scoring", "多维评分与归因分析"),
        ("gating", "Pass/Fail 门禁评估"),
        ("submission", "提交决策与自动提交"),
        ("finalize", "结果汇总与持久化"),
    ]

    def __init__(self, run_config: RunConfig):
        self.run_config = run_config
        self.phases: Dict[str, PipelinePhase] = {}
        self._progress_callback: Optional[Callable] = None
        self._stop_flag = False
        self._checkpoint_dir = Path("data/checkpoints")
        self._last_result: Optional[PipelineResult] = None

        # Initialize phases
        for phase_id, phase_desc in self.PHASES:
            self.phases[phase_id] = PipelinePhase(name=phase_id, description=phase_desc)

    def on_progress(self, callback: Callable[[str, str, dict], None]) -> "GuidedPipeline":
        """Register progress callback: callback(phase_id, status, data)."""
        self._progress_callback = callback
        return self

    def stop(self) -> None:
        """Signal guided pipeline to stop gracefully."""
        self._stop_flag = True

    # ── Main Entry Point ──

    def run_guided(self) -> PipelineResult:
        """Run the complete guided pipeline with progress tracking."""
        run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        logger.info(f"GuidedPipeline started: {run_id}")
        self._notify("init", "running", {"run_id": run_id})

        result = None
        try:
            # Phase 1: Init
            result = self._phase_init(run_id)

            # Phase 2: Context
            result = self._phase_context(result)

            # Phase 3: Redline
            result = self._phase_redline(result)

            # Phase 4-9: Core pipeline (wrapped)
            result = self._phase_core_pipeline(result)

            # Phase 10: Finalize
            result = self._phase_finalize(result)

        except Exception as e:
            error_info = classify_error(e)
            logger.error(f"Pipeline failed: {error_info['type']} — {error_info['message']}")
            self._notify("error", "failed", error_info)
            # Save checkpoint for resume
            self._save_checkpoint(run_id, "error", result)
            raise

        self._last_result = result
        return result

    def run(self) -> PipelineResult:
        """Backward-compatible alias used by CLI and older docs."""
        return self.run_guided()

    def resume(self, run_id: str | None = None) -> PipelineResult:
        """Resume from the latest checkpoint when possible.

        The core pipeline already resumes persisted official backtests from the
        repository. Checkpoints preserve UX state and the latest snapshot; if a
        completed snapshot exists we return it, otherwise we start a guided run
        with persisted-backtest resume enabled.
        """
        checkpoint = self.load_checkpoint(run_id) if run_id else self.latest_checkpoint()
        if checkpoint:
            self._notify("resume", "running", checkpoint.to_dict())
            snapshot_result = self._result_from_snapshot(checkpoint.snapshot)
            if snapshot_result and checkpoint.phase_completed in {"finalize", "completed"}:
                self._last_result = snapshot_result
                self._notify("resume", "completed", {"run_id": checkpoint.run_id})
                return snapshot_result
        return self.run_guided()

    # ── Phase Implementations ──

    def _phase_init(self, run_id: str) -> PipelineResult:
        phase = self.phases["init"]
        phase.start()
        self._notify("init", "running", {})

        # Validate environment
        env = self.run_config.environment
        creds = self.run_config.credentials.resolve()
        has_auth = bool(creds.get("username") or creds.get("token"))

        if env == "production" and not has_auth:
            raise RuntimeError(
                "生产环境需要 BRAIN 凭据。请设置 BRAIN_USERNAME/BRAIN_PASSWORD "
                "或 BRAIN_TOKEN 环境变量。详见 README.md。"
            )

        if env == "production":
            phase.complete(f"环境: production, 认证: {'已配置' if has_auth else '未配置'}")
        else:
            phase.complete(f"环境: {env} (模拟模式)")

        self._notify("init", "completed", {"environment": env})
        return PipelineResult(run_id=run_id, candidates=[], events=[], summary={})

    def _phase_context(self, result: PipelineResult) -> PipelineResult:
        phase = self.phases["context"]
        phase.start()
        self._notify("context", "running", {})

        try:
            from brain_alpha_ops.brain_api.context_defaults import _ensure_loaded, _DEFAULTS_CACHE
            _ensure_loaded()
            fields_count = len(_DEFAULTS_CACHE.get("fields", []))
            ops_count = len(_DEFAULTS_CACHE.get("operators", []))

            if fields_count == 0:
                phase.fail("BRAIN 上下文为空 — 请运行 fetch_official_context.py 拉取数据")
                self._notify("context", "failed", {"error": "empty_context"})
                return result

            phase.complete(f"字段: {fields_count} 个, 算子: {ops_count} 个")
            self._notify("context", "completed", {
                "fields_count": fields_count,
                "operators_count": ops_count,
            })
        except Exception as e:
            phase.fail(str(e))
            self._notify("context", "failed", classify_error(e))

        return result

    def _phase_redline(self, result: PipelineResult) -> PipelineResult:
        phase = self.phases["redline"]
        phase.start()
        self._notify("redline", "running", {})

        try:
            from brain_alpha_ops.compliance.redline_verifier import RedLineVerifier
            verifier = RedLineVerifier()
            report = verifier.verify_all()

            if report.overall == "FAIL":
                blocking = [v for v in report.violations if v.severity == "BLOCKING"]
                phase.fail(f"红线验证失败: {len(blocking)} 个阻断项")
                self._notify("redline", "failed", {
                    "overall": report.overall,
                    "violations": len(report.violations),
                })
                # Don't raise — continue with warnings logged
                phase.warnings.extend(
                    f"[{v.redline_id}] {v.check_name}: {v.fix_guidance}" for v in blocking
                )
            else:
                phase.complete(f"通过: {report.passed}/{report.total_checks} 项")
                self._notify("redline", "completed", {
                    "overall": report.overall,
                    "passed": report.passed,
                })
        except ImportError:
            phase.complete("红线验证模块未加载 (跳过)")
            self._notify("redline", "completed", {"skipped": True})
        except Exception as e:
            phase.fail(str(e))

        return result

    def _phase_core_pipeline(self, result: PipelineResult) -> PipelineResult:
        """Wrap core pipeline with progress callbacks."""
        for phase_id in ["generation", "validation", "simulation", "scoring", "gating", "submission"]:
            phase = self.phases[phase_id]
            phase.start()
            self._notify(phase_id, "running", {})

        try:
            def progress_callback(event: PipelineEvent) -> None:
                if hasattr(event, 'event') and hasattr(event, 'level'):
                    phase_map = {
                        "generation": "generation",
                        "validation": "validation",
                        "simulation": "simulation",
                        "score": "scoring",
                        "gate": "gating",
                        "submit": "submission",
                    }
                    matched = "generation"
                    for key, pid in phase_map.items():
                        if key in (event.event or "").lower():
                            matched = pid
                            break
                    self._notify(matched, "progress", {
                        "event": event.event,
                        "alpha_id": event.alpha_id,
                        "message": event.message,
                    })

            def stop_callback() -> bool:
                return self._stop_flag

            pipeline_result = run_pipeline_from_config(
                self.run_config,
                progress_callback=progress_callback,
                stop_callback=stop_callback,
            )

            # Update phases with results
            summary = pipeline_result.summary
            self.phases["generation"].complete(
                f"生成 {summary.get('total_candidates', 0)} 个候选"
            )
            self.phases["simulation"].complete(
                f"官方仿真 {summary.get('officially_simulated', 0)} 个"
            )
            self.phases["submission"].complete(
                f"提交 {summary.get('auto_submitted', 0)} 个"
            )
            self.phases["scoring"].complete(
                f"评分分布: {summary.get('score_distribution', {})}"
            )

            return pipeline_result
        except Exception as e:
            for pid in ["generation", "validation", "simulation", "scoring", "gating", "submission"]:
                if self.phases[pid].status == "running":
                    self.phases[pid].fail("核心流水线异常终止")
            raise

    def _phase_finalize(self, result: PipelineResult) -> PipelineResult:
        phase = self.phases["finalize"]
        phase.start()
        self._notify("finalize", "running", {})

        try:
            summary = result.summary
            phase.complete(
                f"运行完成 — 候选 {summary.get('total_candidates', 0)} 个, "
                f"仿真 {summary.get('officially_simulated', 0)} 个, "
                f"提交 {summary.get('auto_submitted', 0)} 个"
            )

            # Save run record
            self._save_run_record(result)

            self._notify("finalize", "completed", {
                "summary": summary,
            })
        except Exception as e:
            phase.fail(str(e))

        return result

    # ── Progress Notification ──

    def _notify(self, phase_id: str, status: str, data: dict) -> None:
        if self._progress_callback:
            try:
                self._progress_callback(phase_id, status, data)
            except Exception:
                pass  # Don't let callback failures break the pipeline

    # ── Checkpoint / Resume ──

    def _save_checkpoint(self, run_id: str, phase: str, result: Optional[PipelineResult] = None) -> str:
        self._checkpoint_dir.mkdir(parents=True, exist_ok=True)
        checkpoint = CheckpointData(
            run_id=run_id,
            phase_completed=phase,
            candidates_generated=len(result.candidates) if result else 0,
            simulations_completed=result.summary.get("officially_simulated", 0) if result else 0,
            submissions_made=result.summary.get("auto_submitted", 0) if result else 0,
            cycle_number=result.summary.get("cycle", 0) if result else 0,
            snapshot=result.to_dict() if result else {},
        )
        path = self._checkpoint_dir / f"{run_id}.checkpoint.json"
        path.write_text(
            json.dumps(checkpoint.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return str(path)

    def load_checkpoint(self, run_id: str) -> Optional[CheckpointData]:
        path = self._checkpoint_dir / f"{run_id}.checkpoint.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return CheckpointData.from_dict(data)

    def list_checkpoints(self) -> List[Dict[str, Any]]:
        if not self._checkpoint_dir.exists():
            return []
        checkpoints = []
        for f in sorted(self._checkpoint_dir.glob("*.checkpoint.json"), reverse=True):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                checkpoints.append({
                    "run_id": data.get("run_id", f.stem.replace(".checkpoint", "")),
                    "phase": data.get("phase_completed", "unknown"),
                    "candidates": data.get("candidates_generated", 0),
                    "timestamp": data.get("timestamp", ""),
                    "file": str(f),
                })
            except Exception:
                continue
        return checkpoints

    def latest_checkpoint(self) -> Optional[CheckpointData]:
        checkpoints = self.list_checkpoints()
        if not checkpoints:
            return None
        return self.load_checkpoint(str(checkpoints[0].get("run_id", "")))

    @staticmethod
    def _result_from_snapshot(snapshot: Dict[str, Any]) -> Optional[PipelineResult]:
        if not isinstance(snapshot, dict) or not snapshot.get("run_id"):
            return None
        try:
            candidates = [
                Candidate.from_dict(row)
                for row in snapshot.get("candidates", [])
                if isinstance(row, dict)
            ]
            event_fields = set(PipelineEvent.__dataclass_fields__)
            events = [
                PipelineEvent(**{key: value for key, value in row.items() if key in event_fields})
                for row in snapshot.get("events", [])
                if isinstance(row, dict)
            ]
            summary = snapshot.get("summary") if isinstance(snapshot.get("summary"), dict) else {}
            return PipelineResult(
                run_id=str(snapshot.get("run_id")),
                candidates=candidates,
                events=events,
                summary=summary,
            )
        except Exception:
            return None

    # ── Run History ──

    def _save_run_record(self, result: PipelineResult) -> None:
        history_dir = Path("data/run_history")
        history_dir.mkdir(parents=True, exist_ok=True)

        record = RunRecord(
            run_id=result.run_id,
            started_at=datetime.now(timezone.utc).isoformat(),
            completed_at=datetime.now(timezone.utc).isoformat(),
            status="completed",
            phases=[p.to_dict() for p in self.phases.values()],
            summary=result.summary,
            checkpoint_path=str(self._checkpoint_dir / f"{result.run_id}.checkpoint.json"),
        )

        path = history_dir / f"{result.run_id}.json"
        path.write_text(
            json.dumps(record.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list_history(self) -> List[Dict[str, Any]]:
        history_dir = Path("data/run_history")
        if not history_dir.exists():
            return []

        records = []
        for f in sorted(history_dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                records.append({
                    "run_id": data.get("run_id", f.stem),
                    "started_at": data.get("started_at", ""),
                    "completed_at": data.get("completed_at", ""),
                    "status": data.get("status", "unknown"),
                    "candidates": data.get("summary", {}).get("total_candidates", 0),
                    "submissions": data.get("summary", {}).get("auto_submitted", 0),
                    "phases_completed": sum(
                        1 for p in data.get("phases", [])
                        if p.get("status") == "completed"
                    ),
                })
            except Exception:
                continue
        return records

    def show_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        path = Path("data/run_history") / f"{run_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    # ── Progress Display ──

    def print_progress(self) -> None:
        """Print current progress to console."""
        total = len(self.phases)
        completed = sum(1 for p in self.phases.values() if p.status == "completed")
        failed = sum(1 for p in self.phases.values() if p.status == "failed")
        running = sum(1 for p in self.phases.values() if p.status == "running")

        bar_width = 40
        filled = int(bar_width * completed / total)
        bar = "=" * filled + "-" * (bar_width - filled)

        print(f"\n  Pipeline Progress: [{bar}] {completed}/{total} phases")
        for phase_id, phase in self.phases.items():
            icon = {
                "completed": "[OK]",
                "running": "[..]",
                "failed": "[XX]",
                "pending": "[  ]",
                "skipped": "[--]",
            }.get(phase.status, "[??]")
            print(f"    {icon} {phase.description:<36} [{phase.status}]")
            if phase.errors:
                for err in phase.errors[:2]:
                    print(f"       [W] {err}")

    def print_summary(self, result: Optional[PipelineResult] = None) -> None:
        """Print structured result summary."""
        result = result or self._last_result
        if result is None:
            print("\n  No pipeline result is available yet.")
            return
        s = result.summary
        print("\n" + "=" * 64)
        print("  BRAIN Alpha Ops — Guided Pipeline Summary")
        print("=" * 64)
        print(f"  Run ID        : {result.run_id}")
        print(f"  Candidates    : {s.get('total_candidates', 0):>5} generated")
        print(f"  Simulated     : {s.get('officially_simulated', 0):>5} via BRAIN API")
        print(f"  Submitted     : {s.get('auto_submitted', 0):>5} auto-submitted")
        print(f"  Phase Status  :")

        for phase_id, phase in self.phases.items():
            icon = {"completed": "[OK]", "failed": "[XX]", "running": "[..]", "pending": "[  ]"}.get(phase.status, "[??]")
            duration = f" ({phase.duration_seconds:.1f}s)" if phase.duration_seconds > 0 else ""
            print(f"    {icon} {phase.description:<36} {phase.status}{duration}")

        # Scoring distribution
        score_dist = s.get("score_distribution") or {}
        if score_dist:
            print(f"\n  Score Distribution:")
            for band, count in score_dist.items():
                bar = "█" * min(count, 30)
                print(f"    {band:<22} {count:>4} {bar}")

        # Gate results
        gates = s.get("gate_summary") or {}
        if gates:
            print(f"\n  Gate Results:")
            for gate_name, counts in gates.items():
                print(f"    {gate_name:<22} pass={counts.get('pass',0)} fail={counts.get('fail',0)}")

        print("=" * 64)


# ═══════════════════════════════════════════════════════════════════════
# Standalone UX Utilities
# ═══════════════════════════════════════════════════════════════════════

def format_error_for_user(error: Exception) -> str:
    """Format an exception into a user-friendly, actionable message."""
    info = classify_error(error)
    lines = [
        f"\n  [W] 错误类型: {info['type']}",
        f"  错误信息: {info['message']}",
        f"  修复建议: {info['fix']}",
    ]
    if info["retry"] == "yes":
        lines.append(f"  可重试: 是 - 系统将自动重试")
    elif info["retry"] == "maybe":
        lines.append(f"  可重试: 不确定 - 请根据上述建议排查后重试")
    else:
        lines.append(f"  可重试: 否 - 请先修复问题后重新运行")
    return "\n".join(lines)


def format_candidate_summary(candidate: Candidate) -> str:
    """Format a single candidate as a readable summary."""
    sc = candidate.scorecard or {}
    gate = candidate.gate or {}
    lines = [
        f"  Alpha: {candidate.alpha_id}",
        f"  表达式: {candidate.expression[:80]}{'...' if len(candidate.expression) > 80 else ''}",
        f"  因子族: {candidate.family or 'N/A'}",
        f"  总分: {sc.get('total_score', 'N/A')} ({sc.get('decision_band', 'N/A')})",
        f"  Gate: {'PASS' if gate.get('submission_ready') else 'FAIL'}",
    ]
    if gate.get("failed_reasons"):
        lines.append(f"  失败原因:")
        for reason in gate["failed_reasons"][:3]:
            lines.append(f"    - {reason}")
    return "\n".join(lines)


def format_pipeline_progress(event: PipelineEvent) -> str:
    """Format a pipeline event for live display."""
    timestamp = event.timestamp[:19] if event.timestamp else ""
    level_icon = {"INFO": "[i]", "WARNING": "[W]", "ERROR": "[E]", "SUCCESS": "[+]"}.get(event.level, "[.]")
    return f"  [{timestamp}] {level_icon} {event.event}: {event.message}"


# ═══════════════════════════════════════════════════════════════════════
# CLI Entry Point
# ═══════════════════════════════════════════════════════════════════════

def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(
        prog="guided-pipeline",
        description="BRAIN Alpha Ops 引导式流水线 (含流程引导/实时反馈/断点续跑)",
    )
    parser.add_argument("--config", default=None, help="配置文件路径")
    parser.add_argument("--history", action="store_true", help="查看运行历史")
    parser.add_argument("--show", type=str, default=None, help="查看指定 run_id 的详情")
    parser.add_argument("--checkpoints", action="store_true", help="查看断点列表")
    args = parser.parse_args()

    from brain_alpha_ops.config import load_run_config
    run_config = load_run_config(args.config)

    gp = GuidedPipeline(run_config)

    if args.history:
        print("\n  Run History:")
        print("  " + "-" * 60)
        for record in gp.list_history()[:10]:
            print(f"  {record['run_id']}  [{record['status']}]  "
                  f"candidates={record['candidates']}  "
                  f"submissions={record['submissions']}")
        return 0

    if args.show:
        data = gp.show_run(args.show)
        if data:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(f"Run '{args.show}' not found.")
        return 0 if data else 1

    if args.checkpoints:
        checkpoints = gp.list_checkpoints()
        print(f"\n  Checkpoints ({len(checkpoints)}):")
        for cp in checkpoints[:10]:
            print(f"  {cp['run_id']}  phase={cp['phase']}  "
                  f"candidates={cp['candidates']}  time={cp['timestamp'][:19]}")
        return 0

    # Run guided pipeline
    def progress_handler(phase_id: str, status: str, data: dict) -> None:
        if status == "running":
            desc = gp.phases.get(phase_id, PipelinePhase(name=phase_id, description=phase_id)).description
            print(f"  [..] {desc}...")
        elif status == "completed":
            print(f"  [OK] Phase complete: {phase_id}")
        elif status == "failed":
            print(f"  [XX] Phase failed: {phase_id} -- {data.get('message', '')[:80]}")
        elif status == "progress":
            msg = data.get("message", "")
            if msg:
                print(f"       {msg[:100]}")

    gp.on_progress(progress_handler)

    try:
        result = gp.run_guided()
        gp.print_summary(result)
        return 0
    except Exception as e:
        print(format_error_for_user(e))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
