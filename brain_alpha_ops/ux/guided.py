"""Guided pipeline UX: data structures, formatting, storage, and display.

Merges the former ``guided_models.py``, ``guided_formatting.py``,
``guided_storage.py``, and ``guided_display.py`` into a single cohesive
module for the guided pipeline user experience.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.error_knowledge import classify_ux_error as _unified_classify
from brain_alpha_ops.models import Candidate, PipelineEvent, PipelineResult
from brain_alpha_ops.parameter_audit import build_parameter_audit_snapshot
from brain_alpha_ops.redaction import redact_error_message, redact_text
from brain_alpha_ops.ux.history import RunHistoryAnalytics

logger = logging.getLogger("brain_alpha_ops.ux.guided_pipeline")


# ═══════════════════════════════════════════════════════════════════════
# Data structures (formerly guided_models.py)
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class PipelinePhase:
    """Single phase in the guided pipeline flow."""

    name: str
    description: str
    status: str = "pending"
    started_at: str | None = None
    completed_at: str | None = None
    duration_seconds: float = 0.0
    result_summary: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

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
                # S-14: dedup + cap to prevent unbounded growth
        if error not in self.errors and len(self.errors) < 20:
            self.errors.append(error)

    def to_dict(self) -> dict[str, Any]:
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
    phase_completed: str
    candidates_generated: int
    simulations_completed: int
    submissions_made: int
    cycle_number: int
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    snapshot: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
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
    def from_dict(cls, data: dict[str, Any]) -> "CheckpointData":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class RunRecord:
    """Historical run record for browsing and replay."""

    run_id: str
    started_at: str
    completed_at: str | None = None
    status: str = "running"
    phases: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    checkpoint_path: str = ""
    parameter_audit: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "phases": self.phases,
            "summary": self.summary,
            "checkpoint_path": self.checkpoint_path,
            "parameter_audit": self.parameter_audit,
        }


# ═══════════════════════════════════════════════════════════════════════
# Formatting helpers (formerly guided_formatting.py)
# ═══════════════════════════════════════════════════════════════════════


def classify_error(error: Exception) -> Dict[str, str]:
    """Classify an error and return actionable guidance."""
    try:
        info = _unified_classify(error)
        return {
            "type": info.error_code or type(error).__name__,
            "message": redact_error_message(error, max_length=200),
            "fix": info.fix_hint or "未知错误。请在页面事件记录中查看提示，或让维护者查看诊断信息。",
            "retry": "yes" if info.retryable else ("maybe" if info.retryable is None else "no"),
        }
    except Exception:
        logger.warning("guided pipeline error classification fallback failed", exc_info=True)
        return {
            "type": type(error).__name__,
            "message": redact_error_message(error, max_length=200),
            "fix": "未知错误。请在页面事件记录中查看提示，或让维护者查看诊断信息。",
            "retry": "maybe",
        }


def format_error_for_user(error: Exception) -> str:
    """Format an exception into a user-friendly, actionable message."""
    info = classify_error(error)
    lines = [
        f"\n  [W] 错误类型: {info['type']}",
        f"  错误信息: {info['message']}",
        f"  修复建议: {info['fix']}",
    ]
    if info["retry"] == "yes":
        lines.append("  可重试: 是 - 系统将自动重试")
    elif info["retry"] == "maybe":
        lines.append("  可重试: 不确定 - 请根据上述建议排查后重试")
    else:
        lines.append("  可重试: 否 - 请先修复问题后重新运行")
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
        lines.append("  失败原因:")
        for reason in gate["failed_reasons"][:3]:
            lines.append(f"    - {reason}")
    return "\n".join(lines)


def format_pipeline_progress(event: PipelineEvent) -> str:
    """Format a pipeline event for live display."""
    timestamp = event.timestamp[:19] if event.timestamp else ""
    level_icon = {"INFO": "[i]", "WARNING": "[W]", "ERROR": "[E]", "SUCCESS": "[+]"}.get(event.level, "[.]")
    return f"  [{timestamp}] {level_icon} {event.event}: {event.message}"


# ═══════════════════════════════════════════════════════════════════════
# Checkpoint, resume, and run-history helpers (formerly guided_storage.py)
# ═══════════════════════════════════════════════════════════════════════


def save_checkpoint(
    checkpoint_dir: Path,
    run_id: str,
    phase: str,
    result: PipelineResult | None = None,
) -> str:
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = CheckpointData(
        run_id=run_id,
        phase_completed=phase,
        candidates_generated=len(result.candidates) if result else 0,
        simulations_completed=result.summary.get("officially_simulated", 0) if result else 0,
        submissions_made=result.summary.get("auto_submitted", 0) if result else 0,
        cycle_number=result.summary.get("cycle", 0) if result else 0,
        snapshot=result.to_dict() if result else {},
    )
    path = checkpoint_dir / f"{run_id}.checkpoint.json"
    path.write_text(
        json.dumps(checkpoint.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(path)


def load_checkpoint(checkpoint_dir: Path, run_id: str) -> CheckpointData | None:
    path = checkpoint_dir / f"{run_id}.checkpoint.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return CheckpointData.from_dict(data)


def list_checkpoints(checkpoint_dir: Path) -> list[dict[str, Any]]:
    if not checkpoint_dir.exists():
        return []
    checkpoints = []
    for path in sorted(checkpoint_dir.glob("*.checkpoint.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            checkpoints.append({
                "run_id": data.get("run_id", path.stem.replace(".checkpoint", "")),
                "phase": data.get("phase_completed", "unknown"),
                "candidates": data.get("candidates_generated", 0),
                "timestamp": data.get("timestamp", ""),
                "file": str(path),
            })
        except Exception:
            logger.warning(
                "guided pipeline checkpoint file skipped: %s",
                redact_text(str(path), max_length=180),
                exc_info=True,
            )
            continue
    return checkpoints


def latest_checkpoint(checkpoint_dir: Path) -> CheckpointData | None:
    checkpoints = list_checkpoints(checkpoint_dir)
    if not checkpoints:
        return None
    return load_checkpoint(checkpoint_dir, str(checkpoints[0].get("run_id", "")))


def result_from_snapshot(snapshot: dict[str, Any]) -> PipelineResult | None:
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
        logger.warning("guided pipeline snapshot could not be restored", exc_info=True)
        return None


def save_run_record(
    *,
    history_dir: Path,
    checkpoint_dir: Path,
    run_config: RunConfig,
    phases: Iterable[PipelinePhase],
    result: PipelineResult,
) -> None:
    history_dir.mkdir(parents=True, exist_ok=True)
    record = RunRecord(
        run_id=result.run_id,
        started_at=datetime.now(timezone.utc).isoformat(),
        completed_at=datetime.now(timezone.utc).isoformat(),
        status="completed",
        phases=[phase.to_dict() for phase in phases],
        summary=result.summary,
        checkpoint_path=str(checkpoint_dir / f"{result.run_id}.checkpoint.json"),
        parameter_audit=build_parameter_audit_snapshot(
            run_config,
            source="guided_pipeline",
        ),
    )

    path = history_dir / f"{result.run_id}.json"
    path.write_text(
        json.dumps(record.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def list_history(storage_dir: Path, *, limit: int = 10) -> list[dict[str, Any]]:
    return RunHistoryAnalytics(str(storage_dir)).list_history(limit=limit)


def show_run(storage_dir: Path, run_id: str) -> dict[str, Any] | None:
    return RunHistoryAnalytics(str(storage_dir)).load_run(run_id)


def history_analytics(storage_dir: Path, *, limit: int = 10) -> dict[str, Any]:
    return RunHistoryAnalytics(str(storage_dir)).analytics(limit=limit)


# ═══════════════════════════════════════════════════════════════════════
# Console display helpers (formerly guided_display.py)
# ═══════════════════════════════════════════════════════════════════════


def print_progress(phases: dict[str, PipelinePhase]) -> None:
    """Print current progress to console."""
    total = len(phases)
    completed = sum(1 for phase in phases.values() if phase.status == "completed")

    bar_width = 40
    filled = int(bar_width * completed / total)
    bar = "=" * filled + "-" * (bar_width - filled)

    print(f"\n  Pipeline Progress: [{bar}] {completed}/{total} phases")
    for phase in phases.values():
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


def print_summary(
    phases: dict[str, PipelinePhase],
    result: PipelineResult | None,
) -> None:
    """Print structured result summary."""
    if result is None:
        print("\n  No pipeline result is available yet.")
        return
    summary = result.summary
    print("\n" + "=" * 64)
    print("  BRAIN Alpha Ops — Guided Pipeline Summary")
    print("=" * 64)
    print(f"  Run ID        : {result.run_id}")
    print(f"  Candidates    : {summary.get('total_candidates', 0):>5} generated")
    print(f"  Simulated     : {summary.get('officially_simulated', 0):>5} via BRAIN API")
    print(f"  Submitted     : {summary.get('auto_submitted', 0):>5} auto-submitted")
    print("  Phase Status  :")

    for phase in phases.values():
        icon = {
            "completed": "[OK]",
            "failed": "[XX]",
            "running": "[..]",
            "pending": "[  ]",
        }.get(phase.status, "[??]")
        duration = f" ({phase.duration_seconds:.1f}s)" if phase.duration_seconds > 0 else ""
        print(f"    {icon} {phase.description:<36} {phase.status}{duration}")

    score_dist = summary.get("score_distribution") or {}
    if score_dist:
        print("\n  Score Distribution:")
        for band, count in score_dist.items():
            bar = "█" * min(count, 30)
            print(f"    {band:<22} {count:>4} {bar}")

    gates = summary.get("gate_summary") or {}
    if gates:
        print("\n  Gate Results:")
        for gate_name, counts in gates.items():
            print(f"    {gate_name:<22} pass={counts.get('pass', 0)} fail={counts.get('fail', 0)}")

    print("=" * 64)
