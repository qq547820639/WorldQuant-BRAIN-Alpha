"""Checkpoint, resume, and run-history helpers for guided pipeline runs."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.models import Candidate, PipelineEvent, PipelineResult
from brain_alpha_ops.parameter_audit import build_parameter_audit_snapshot
from brain_alpha_ops.redaction import redact_text
from brain_alpha_ops.ux.guided_models import CheckpointData, PipelinePhase, RunRecord
from brain_alpha_ops.ux.history import RunHistoryAnalytics


logger = logging.getLogger("brain_alpha_ops.ux.guided_pipeline")


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
