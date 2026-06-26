"""Structured scoring interpreter routes (Workstream D4.1).

Exposes the structured ``GateDecision`` payload, multi-dimensional
attribution, and replayable audit-trail export to the frontend so the
panels can render "why ranked this way, why blocked, next action"
without re-implementing the decision logic.

Routes:
  * POST /api/scoring/gate_decision     -> handle_scoring_gate_decision
  * POST /api/scoring/multi_attribution -> handle_scoring_multi_attribution
  * GET  /api/audit/export              -> handle_audit_export

The handlers are intentionally thin: they delegate to the services in
``scoring._gate_decision``, ``scoring._attribution_multi`` and
``audit_trail.export`` and only normalise the request/response shape.
"""

from __future__ import annotations

import logging
from typing import Any

from brain_alpha_ops.config import load_run_config
from brain_alpha_ops.redaction import redact_error_message, redact_text
from brain_alpha_ops.scoring._attribution_multi import (
    build_multi_dimensional_attribution,
)
from brain_alpha_ops.scoring._gate_decision import GateDecisionService
from brain_alpha_ops.scoring.release_score_gate import evaluate_release_score

logger = logging.getLogger(__name__)

GATE_DECISION_ROUTE_SCHEMA = "scoring_gate_decision.v1"
MULTI_ATTRIBUTION_ROUTE_SCHEMA = "scoring_multi_attribution.v1"
AUDIT_EXPORT_ROUTE_SCHEMA = "audit_export_route.v1"

_DEFAULT_AUDIT_DIR = "data/audit_trail"
_MAX_MULTI_ATTR_SCORECARDS = 200
_MAX_AUDIT_EXPORT_LIMIT = 5000


def handle_scoring_gate_decision(body: dict[str, Any]) -> dict[str, Any]:
    """POST /api/scoring/gate_decision — structured gate-decision payload.

    Accepts the same request shape as ``/api/scoring/evaluate`` (a
    ``candidate`` object or an ``alpha_id`` to look up).  Returns the
    ``GateDecisionOutcome`` plus the release-gate snapshot used as evidence.
    """
    from brain_alpha_ops.web_redline_scoring import _candidate_from_request

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


# --- Helpers ----------------------------------------------------------------


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


__all__ = [
    "AUDIT_EXPORT_ROUTE_SCHEMA",
    "GATE_DECISION_ROUTE_SCHEMA",
    "MULTI_ATTRIBUTION_ROUTE_SCHEMA",
    "handle_audit_export",
    "handle_scoring_gate_decision",
    "handle_scoring_multi_attribution",
]
