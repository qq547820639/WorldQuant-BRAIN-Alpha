"""Structured scoring interpreter routes (Workstream D4.1).

Exposes the structured ``GateDecision`` payload, multi-dimensional
attribution, and replayable audit-trail export to the frontend so the
panels can render "why ranked this way, why blocked, next action"
without re-implementing the decision logic.

Routes:
  * POST /api/scoring/gate_decision     -> handle_scoring_gate_decision
  * POST /api/scoring/multi_attribution -> handle_scoring_multi_attribution
  * GET  /api/audit/export              -> handle_audit_export

Also hosts the legacy red-line scoring web integration (consolidated from
``web_redline_scoring.py``): red-line report, scoring evaluate/health/
attribution, and checkpoint status.  The handlers are intentionally thin:
they delegate to the underlying services and only normalise the
request/response shape.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from brain_alpha_ops.compliance.redline_verifier import RedLineVerifier
from brain_alpha_ops.config import load_run_config
from brain_alpha_ops.jsonl import read_jsonl_tail
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.redaction import redact_error_message, redact_text
from brain_alpha_ops.scoring._attribution_multi import (
    build_multi_dimensional_attribution,
)
from brain_alpha_ops.scoring._gate_decision import GateDecisionService
from brain_alpha_ops.scoring.history import ScoreHistoryDB
from brain_alpha_ops.scoring.official_scoring import (
    OfficialScoringSystem,
)
from brain_alpha_ops.scoring.release_score_gate import evaluate_release_score

logger = logging.getLogger(__name__)

GATE_DECISION_ROUTE_SCHEMA = "scoring_gate_decision.v1"
MULTI_ATTRIBUTION_ROUTE_SCHEMA = "scoring_multi_attribution.v1"
AUDIT_EXPORT_ROUTE_SCHEMA = "audit_export_route.v1"

_DEFAULT_AUDIT_DIR = "data/audit_trail"
_MAX_MULTI_ATTR_SCORECARDS = 200
_MAX_AUDIT_EXPORT_LIMIT = 5000


# ═══════════════════════ Red-line scoring handlers ═════════════════════════


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
    score_history_status = "persisted"
    score_history_error = ""
    try:
        db = ScoreHistoryDB(config.ops.storage_dir)
        db.append(result)
    except Exception as exc:
        score_history_status = "failed"
        score_history_error = redact_error_message(exc)
        logger.warning(
            "score history append failed for alpha_id=%s: %s",
            redact_text(result.alpha_id, max_length=64),
            score_history_error,
        )

    payload = result.to_dict()
    payload["score_history_status"] = score_history_status
    if score_history_error:
        payload["score_history_error"] = score_history_error
    return payload


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
        "attribution_summary": result.get("attribution_summary"),
        "hard_gates": result.get("hard_gates"),
        "soft_gates": result.get("soft_gates"),
        "top_failures": result.get("top_failures"),
        "improvement_hints": result.get("improvement_hints"),
    }


def handle_checkpoint_status(query: dict[str, Any]) -> dict[str, Any]:
    """GET /api/checkpoint/status — list checkpoints and latest resume status."""
    try:
        from brain_alpha_ops.ux.guided_pipeline import GuidedPipeline
        config = load_run_config()
        gp = GuidedPipeline(config)
        checkpoints = gp.list_checkpoints()
        latest = gp.latest_checkpoint()
        history = gp.list_history()
        analytics = gp.history_analytics(limit=10)
        return {
            "ok": True,
            "schema_version": "checkpoint_status.v1",
            "storage_dir": config.ops.storage_dir,
            "checkpoint_count": len(checkpoints),
            "checkpoints": checkpoints[:10],
            "latest": latest.to_dict() if latest else None,
            "history_count": len(history),
            "history": history[:10],
            "latest_history": history[0] if history else None,
            "history_analytics": analytics,
            "latest_comparison": analytics.get("latest_comparison"),
            "resume_available": latest is not None,
        }
    except Exception as exc:
        from brain_alpha_ops.redaction import redact_error_message
        logger.warning("checkpoint status unavailable", exc_info=True)
        return {"ok": False, "error": redact_error_message(exc), "resume_available": False}


# ═══════════════════════ Structured gate-decision handlers ═════════════════


def handle_scoring_gate_decision(body: dict[str, Any]) -> dict[str, Any]:
    """POST /api/scoring/gate_decision — structured gate-decision payload.

    Accepts the same request shape as ``/api/scoring/evaluate`` (a
    ``candidate`` object or an ``alpha_id`` to look up).  Returns the
    ``GateDecisionOutcome`` plus the release-gate snapshot used as evidence.
    """
    config = load_run_config()
    candidate, lookup_error = _candidate_from_request(body, config.ops.storage_dir)
    if candidate is None:
        return {"ok": False, **lookup_error}

    release_gate: dict[str, Any] | None = None
    metrics = candidate.official_metrics if isinstance(candidate.official_metrics, dict) else {}
    if metrics:
        try:
            release_gate = evaluate_release_score(
                metrics, config.thresholds, settings=config.settings
            ).to_dict()
        except Exception as exc:
            logger.warning(
                "release gate eval failed for alpha_id=%s: %s",
                redact_text(candidate.alpha_id, max_length=64),
                redact_error_message(exc),
            )

    service = GateDecisionService()
    outcome = service.decide(
        candidate,
        gate_results=candidate.gate,
        release_gate=release_gate,
    )
    payload = outcome.to_dict()
    payload["ok"] = True
    payload["schema_version"] = GATE_DECISION_ROUTE_SCHEMA
    payload["release_gate"] = release_gate or {}
    payload["candidate_snapshot"] = _candidate_snapshot(candidate)
    return payload


def handle_scoring_multi_attribution(body: dict[str, Any]) -> dict[str, Any]:
    """POST /api/scoring/multi_attribution — multi-dimensional attribution.

    Accepts a body of the form::

        {
          "scorecards": [<scorecard dict>, ...],
          "candidates": [<candidate dict>, ...]  // optional context
        }

    Returns the aggregated by_gate / by_metric / by_dataset / by_region /
    by_time summary so the frontend can render tooltips explaining why
    candidates were ranked or blocked across each dimension.
    """
    scorecards = body.get("scorecards")
    if not isinstance(scorecards, list):
        return {
            "ok": False,
            "error": "scorecards must be a list of scorecard dicts",
            "error_code": "MULTI_ATTR_INVALID_SCORECARDS",
        }
    if not scorecards:
        return {
            "ok": False,
            "error": "no scorecards provided",
            "error_code": "MULTI_ATTR_NO_SCORECARDS",
        }
    scorecards = scorecards[:_MAX_MULTI_ATTR_SCORECARDS]

    raw_candidates = body.get("candidates") or []
    if not isinstance(raw_candidates, list):
        raw_candidates = []
    candidates = _coerce_candidates(raw_candidates)

    try:
        result = build_multi_dimensional_attribution(
            scorecards, candidates=candidates
        )
    except Exception as exc:
        logger.warning("multi-attribution failed: %s", redact_error_message(exc))
        return {
            "ok": False,
            "error": redact_error_message(exc),
            "error_code": "MULTI_ATTR_FAILED",
        }

    return {
        "ok": True,
        "schema_version": MULTI_ATTRIBUTION_ROUTE_SCHEMA,
        "multi_attribution": result,
    }


def handle_audit_export(query: dict[str, Any]) -> dict[str, Any]:
    """GET /api/audit/export — replayable audit trail export.

    Query parameters:
      * ``alpha_id``        — restrict to a single candidate (optional)
      * ``limit``           — max entries (default 500, max 5000)
      * ``event_type``      — filter by event_type substring
      * ``passed``          — filter by passed flag (true/false)
      * ``audit_dir``       — override audit directory (defaults to data/audit_trail)
    """
    from brain_alpha_ops.audit_trail.export import export_audit_trail

    alpha_id = _first_value(query, "alpha_id") or None
    limit = _bounded_int(
        _first_value(query, "limit") or "500",
        lower=1,
        upper=_MAX_AUDIT_EXPORT_LIMIT,
    )
    audit_dir = _first_value(query, "audit_dir") or _DEFAULT_AUDIT_DIR
    filters = _extract_filters(query)

    try:
        entries = export_audit_trail(
            alpha_id=alpha_id,
            filters=filters or None,
            audit_dir=audit_dir,
            limit=limit,
        )
    except Exception as exc:
        logger.warning("audit export failed: %s", redact_error_message(exc))
        return {
            "ok": False,
            "error": redact_error_message(exc),
            "error_code": "AUDIT_EXPORT_FAILED",
        }

    return {
        "ok": True,
        "schema_version": AUDIT_EXPORT_ROUTE_SCHEMA,
        "alpha_id": alpha_id or "",
        "entry_count": len(entries),
        "entries": entries,
    }


# ═══════════════════════ Shared helpers ═════════════════════════════════════


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


def _candidate_snapshot(candidate: Any) -> dict[str, Any]:
    """Minimal candidate snapshot for the frontend (no sensitive fields)."""
    gate = candidate.gate if isinstance(candidate.gate, dict) else {}
    return {
        "alpha_id": str(getattr(candidate, "alpha_id", "") or ""),
        "lifecycle_status": str(getattr(candidate, "lifecycle_status", "") or ""),
        "total_score": float(
            (candidate.scorecard or {}).get("total_score", 0.0) or 0.0
            if isinstance(candidate.scorecard, dict)
            else 0.0
        ),
        "decision_band": str(
            (candidate.scorecard or {}).get("decision_band", "") or ""
            if isinstance(candidate.scorecard, dict)
            else ""
        ),
        "has_official_metrics": bool(candidate.official_metrics),
        "gate_submission_ready": bool(gate.get("submission_ready")),
        "gate_hard_blocked": bool(gate.get("hard_gate_blocked")),
    }


def _coerce_candidates(raw_candidates: list[Any]) -> list[Any]:
    """Coerce a list of candidate dicts into Candidate objects when possible."""
    from brain_alpha_ops.models import Candidate

    out: list[Any] = []
    for raw in raw_candidates[:_MAX_MULTI_ATTR_SCORECARDS]:
        if not isinstance(raw, dict):
            continue
        try:
            out.append(Candidate.from_dict(raw))
        except Exception:
            # Keep the raw dict so build_multi_dimensional_attribution can
            # still inspect it via getattr-style access where possible.
            logger.warning(
                "Candidate.from_dict coercion failed; keeping raw dict", exc_info=True
            )
            out.append(raw)
    return out


def _first_value(query: dict[str, Any], key: str) -> str:
    """Return the first value for ``key`` from a parsed query dict."""
    value = query.get(key)
    if isinstance(value, list):
        value = value[0] if value else ""
    if value is None:
        return ""
    return str(value).strip()


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


def _extract_filters(query: dict[str, Any]) -> dict[str, Any]:
    """Build a filters dict for ``export_audit_trail`` from query params."""
    filters: dict[str, Any] = {}
    event_type = _first_value(query, "event_type")
    if event_type:
        filters["event_type"] = event_type
    passed_raw = _first_value(query, "passed").lower()
    if passed_raw in {"true", "false"}:
        filters["passed"] = passed_raw == "true"
    gate_name = _first_value(query, "gate_name")
    if gate_name:
        filters["gate_name"] = gate_name
    return filters


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
        from brain_alpha_ops.redaction import redact_error_message
        logger.warning("scoring auto-calibration status unavailable", exc_info=True)
        return {
            "available": False,
            "trigger_requested": bool(trigger),
            "triggered": False,
            "error": redact_error_message(exc),
        }


__all__ = [
    "AUDIT_EXPORT_ROUTE_SCHEMA",
    "GATE_DECISION_ROUTE_SCHEMA",
    "MULTI_ATTRIBUTION_ROUTE_SCHEMA",
    "handle_audit_export",
    "handle_checkpoint_status",
    "handle_redline_report",
    "handle_scoring_attribution",
    "handle_scoring_evaluate",
    "handle_scoring_gate_decision",
    "handle_scoring_health",
    "handle_scoring_multi_attribution",
]
