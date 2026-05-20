"""Web API endpoints for redline verification and scoring attribution.

Exposes:
  GET  /api/redline/report        -> ComplianceReport JSON
  POST /api/scoring/evaluate      -> ScoringResult JSON
  GET  /api/scoring/health        -> ScoreHistoryDB convergence stats
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from brain_alpha_ops.compliance.redline_verifier import RedLineVerifier
from brain_alpha_ops.config import load_run_config
from brain_alpha_ops.jsonl import read_jsonl_tail
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.scoring.official_scoring import (
    OfficialScoringSystem,
    ScoreHistoryDB,
)


def _get_storage_dir() -> str:
    config = load_run_config()
    return config.ops.storage_dir


def handle_redline_report(query: dict[str, Any]) -> dict[str, Any]:
    """GET /api/redline/report — full ComplianceReport as JSON."""
    config = load_run_config()
    verifier = RedLineVerifier(config)
    report = verifier.verify_all()
    return report.to_dict()


def handle_scoring_evaluate(body: dict[str, Any]) -> dict[str, Any]:
    """POST /api/scoring/evaluate — evaluate a candidate and return ScoringResult."""
    config = load_run_config()
    candidate, lookup_error = _candidate_from_request(body, config.ops.storage_dir)
    if candidate is None:
        return {"ok": False, **lookup_error}

    system = OfficialScoringSystem(config.ops)
    result = system.evaluate(candidate)

    # Persist to score history
    try:
        db = ScoreHistoryDB(config.ops.storage_dir)
        db.append(result)
    except Exception:
        pass

    return result.to_dict()


def handle_scoring_health(query: dict[str, Any]) -> dict[str, Any]:
    """GET /api/scoring/health — convergence stats and scorecard health."""
    storage_dir = _get_storage_dir()
    db = ScoreHistoryDB(storage_dir)
    stats = db.convergence_stats()
    auto_calibrate = _query_truthy(query.get("auto_calibrate"))
    return {
        "ok": True,
        "schema_version": "scoring_health.v1",
        "storage_dir": storage_dir,
        "auto_calibration": _auto_calibration_status(storage_dir, trigger=auto_calibrate),
        **stats,
    }


def handle_scoring_attribution(body: dict[str, Any]) -> dict[str, Any]:
    """POST /api/scoring/attribution — lightweight attribution-only report."""
    result = handle_scoring_evaluate(body)
    if not result.get("ok", True):
        return result
    return {
        "ok": True,
        "attribution": result.get("attribution_tree"),
        "hard_gates": result.get("hard_gates"),
        "soft_gates": result.get("soft_gates"),
        "top_failures": result.get("top_failures"),
        "improvement_hints": result.get("improvement_hints"),
    }


def _candidate_from_request(body: dict[str, Any], storage_dir: str) -> tuple[Candidate | None, dict[str, Any]]:
    candidate = body.get("candidate")
    if isinstance(candidate, dict):
        try:
            return Candidate.from_dict(candidate), {}
        except TypeError as exc:
            return None, {
                "error": "invalid 'candidate' object",
                "error_code": "SCORING_INVALID_CANDIDATE",
                "detail": str(exc),
            }

    alpha_id = str(
        body.get("alpha_id")
        or body.get("official_alpha_id")
        or body.get("simulation_id")
        or ""
    ).strip()
    if not alpha_id:
        return None, {
            "error": "missing candidate or alpha_id in request body",
            "error_code": "SCORING_CANDIDATE_REQUIRED",
        }

    limit = _bounded_int(body.get("limit", 5000), lower=1, upper=50000)
    row = _find_candidate_row(storage_dir, alpha_id, limit=limit)
    if row is None:
        return None, {
            "error": f"candidate not found for alpha_id '{alpha_id}'",
            "error_code": "SCORING_CANDIDATE_NOT_FOUND",
            "alpha_id": alpha_id,
            "searched": ["candidates.jsonl", "run_history/latest.json", "recent run_history/*.json"],
        }
    try:
        return Candidate.from_dict(row), {}
    except TypeError as exc:
        return None, {
            "error": f"stored candidate is incomplete for alpha_id '{alpha_id}'",
            "error_code": "SCORING_CANDIDATE_INCOMPLETE",
            "alpha_id": alpha_id,
            "detail": str(exc),
        }


def _find_candidate_row(storage_dir: str, alpha_id: str, *, limit: int) -> dict[str, Any] | None:
    storage = Path(storage_dir)
    for row in reversed(read_jsonl_tail(storage / "candidates.jsonl", limit=limit)):
        if _matches_candidate_id(row, alpha_id):
            return _candidate_payload(row)

    history_dir = storage / "run_history"
    history_files: list[Path] = []
    latest = history_dir / "latest.json"
    if latest.is_file():
        history_files.append(latest)
    if history_dir.is_dir():
        recent = sorted(
            [p for p in history_dir.glob("*.json") if p.name != "latest.json"],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:10]
        history_files.extend(recent)

    for path in history_files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for row in _candidate_rows_from_snapshot(payload):
            if _matches_candidate_id(row, alpha_id):
                return _candidate_payload(row)
    return None


def _candidate_rows_from_snapshot(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    containers = [
        payload,
        payload.get("result") if isinstance(payload.get("result"), dict) else {},
        payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
    ]
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    if isinstance(result.get("summary"), dict):
        containers.append(result["summary"])

    for container in containers:
        if not isinstance(container, dict):
            continue
        for key in ("candidates", "passed_candidates", "submitted_candidates"):
            value = container.get(key)
            if isinstance(value, list):
                rows.extend(item for item in value if isinstance(item, dict))
    return rows


def _candidate_payload(row: dict[str, Any]) -> dict[str, Any]:
    nested = row.get("candidate")
    if isinstance(nested, dict):
        return nested
    return row


def _matches_candidate_id(row: dict[str, Any], alpha_id: str) -> bool:
    candidate = _candidate_payload(row)
    return alpha_id in {
        str(candidate.get("alpha_id") or ""),
        str(candidate.get("official_alpha_id") or ""),
        str(candidate.get("simulation_id") or ""),
        str(row.get("alpha_id") or ""),
        str(row.get("official_alpha_id") or ""),
        str(row.get("simulation_id") or ""),
    }


def _bounded_int(value: Any, *, lower: int, upper: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = lower
    return min(max(parsed, lower), upper)


def _query_truthy(value: Any) -> bool:
    if isinstance(value, list):
        value = value[0] if value else ""
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _auto_calibration_status(storage_dir: str, *, trigger: bool = False) -> dict[str, Any]:
    try:
        from brain_alpha_ops.research.auto_calibrator import AutoCalibrator

        calibrator = AutoCalibrator(storage_dir)
        total_pass_records = calibrator._count_passing_records()
        needs_calibration = calibrator.needs_calibration()
        status: dict[str, Any] = {
            "available": True,
            "trigger_requested": bool(trigger),
            "needs_calibration": needs_calibration,
            "total_pass_records": total_pass_records,
            "last_calibrated_count": calibrator._last_calibrated_count,
            "required": calibrator.MIN_CALIBRATION_SAMPLES,
            "calibrated_at": getattr(calibrator.params, "calibrated_at", ""),
        }
        if trigger and needs_calibration:
            report = calibrator.calibrate()
            status["triggered"] = True
            status["report"] = report
            status["needs_calibration"] = False if report.get("calibrated") else calibrator.needs_calibration()
            status["calibrated_at"] = getattr(calibrator.params, "calibrated_at", "")
        else:
            status["triggered"] = False
        return status
    except Exception as exc:
        return {
            "available": False,
            "trigger_requested": bool(trigger),
            "triggered": False,
            "error": str(exc),
        }


def handle_checkpoint_status(query: dict[str, Any]) -> dict[str, Any]:
    """GET /api/checkpoint/status — list checkpoints and latest resume status."""
    try:
        from brain_alpha_ops.ux.guided_pipeline import GuidedPipeline
        config = load_run_config()
        gp = GuidedPipeline(config)
        checkpoints = gp.list_checkpoints()
        latest = gp.latest_checkpoint()
        return {
            "ok": True,
            "schema_version": "checkpoint_status.v1",
            "checkpoint_count": len(checkpoints),
            "checkpoints": checkpoints[:10],
            "latest": latest.to_dict() if latest else None,
            "resume_available": latest is not None,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "resume_available": False}
