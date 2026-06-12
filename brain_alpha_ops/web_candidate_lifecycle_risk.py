"""Local lifecycle-history risk summaries for candidate decisions."""

from __future__ import annotations

from hashlib import sha256
from typing import Any

from brain_alpha_ops.redaction import redact_text
from brain_alpha_ops.web_runtime_state import status_category


LIFECYCLE_RISK_SCHEMA_VERSION = "candidate-lifecycle-risk-v1"
LIFECYCLE_RISK_REASON_CODES = {
    "lifecycle_history_blocked",
    "lifecycle_history_failed",
}

_ARCHIVE_TOKENS = (
    "candidate_pool_pruned",
    "hard_gate_blocked",
    "high_cloud_similarity",
    "local_prefilter_rejected",
    "local_standard_rejected",
    "official_standard_rejected",
    "rejected",
)


def enrich_candidates_with_lifecycle_risk(
    rows: list[dict[str, Any]],
    lifecycle_rows: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Return candidate rows annotated with local lifecycle replay risk.

    The helper is pure and local-only: lifecycle rows are existing JSONL records,
    not live BRAIN calls.  It intentionally exposes only compact state metadata
    so the Web payload can explain risk without leaking notes or credentials.
    """

    if not lifecycle_rows:
        return [dict(row) for row in rows]
    result: list[dict[str, Any]] = []
    for row in rows:
        candidate = dict(row)
        if existing_lifecycle_risk(candidate):
            result.append(candidate)
            continue
        risk = lifecycle_risk_for_candidate(candidate, lifecycle_rows)
        if risk:
            candidate["lifecycle_risk"] = risk
            extra_fields = candidate.get("extra_fields") if isinstance(candidate.get("extra_fields"), dict) else {}
            candidate["extra_fields"] = {**extra_fields, "lifecycle_risk": risk}
        result.append(candidate)
    return result


def existing_lifecycle_risk(row: dict[str, Any]) -> dict[str, Any]:
    risk = row.get("lifecycle_risk")
    if isinstance(risk, dict):
        return risk
    extra_fields = row.get("extra_fields") if isinstance(row.get("extra_fields"), dict) else {}
    risk = extra_fields.get("lifecycle_risk")
    return risk if isinstance(risk, dict) else {}


def lifecycle_risk_for_candidate(
    candidate: dict[str, Any],
    lifecycle_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    matches: list[tuple[int, dict[str, Any], str]] = []
    for index, raw in enumerate(lifecycle_rows):
        if not isinstance(raw, dict):
            continue
        matched_by = _match_candidate(candidate, raw)
        if matched_by:
            matches.append((index, raw, matched_by))
    if not matches:
        return {}

    latest_index, latest, matched_by = max(
        matches,
        key=lambda item: (_text(item[1].get("timestamp")), item[0]),
    )
    del latest_index
    category = _category(latest)
    stage = _text(latest.get("stage") or latest.get("action"))
    status = _text(latest.get("status") or latest.get("lifecycle_status"))
    event_text = f"{stage} {status} {_text(latest.get('lifecycle_status'))}".lower()
    action_hint = "retain"
    reason_code = ""
    blocking = False
    if category == "blocked":
        reason_code = "lifecycle_history_blocked"
        action_hint = "archive" if any(token in event_text for token in _ARCHIVE_TOKENS) else "optimize"
        blocking = action_hint == "archive"
    elif category == "failed":
        reason_code = "lifecycle_history_failed"
        action_hint = "archive" if any(token in event_text for token in _ARCHIVE_TOKENS) else "optimize"
        blocking = action_hint == "archive"

    return {
        "schema_version": LIFECYCLE_RISK_SCHEMA_VERSION,
        "source": "lifecycle_jsonl",
        "local_only": True,
        "official_api_called": False,
        "submit_allowed": False,
        "matched_event_count": len(matches),
        "matched_by": matched_by,
        "latest_stage": stage,
        "latest_status": status,
        "latest_status_category": category,
        "latest_event_at": _text(latest.get("timestamp")),
        "action_hint": action_hint,
        "blocking": blocking,
        "reason_code": reason_code,
    }


def lifecycle_history_requires_rework(row: dict[str, Any]) -> bool:
    risk = existing_lifecycle_risk(row)
    if not risk:
        decision = row.get("production_decision") if isinstance(row.get("production_decision"), dict) else {}
        evidence = decision.get("decision_evidence") if isinstance(decision.get("decision_evidence"), dict) else {}
        risk = evidence.get("lifecycle_risk") if isinstance(evidence.get("lifecycle_risk"), dict) else {}
    return str(risk.get("reason_code") or "") in LIFECYCLE_RISK_REASON_CODES and str(risk.get("action_hint") or "") == "optimize"


def lifecycle_history_should_archive(row: dict[str, Any]) -> bool:
    risk = existing_lifecycle_risk(row)
    if not risk:
        decision = row.get("production_decision") if isinstance(row.get("production_decision"), dict) else {}
        evidence = decision.get("decision_evidence") if isinstance(decision.get("decision_evidence"), dict) else {}
        risk = evidence.get("lifecycle_risk") if isinstance(evidence.get("lifecycle_risk"), dict) else {}
    return str(risk.get("reason_code") or "") in LIFECYCLE_RISK_REASON_CODES and str(risk.get("action_hint") or "") == "archive"


def _match_candidate(candidate: dict[str, Any], lifecycle_row: dict[str, Any]) -> str:
    candidate_ids = _identity_values(candidate)
    lifecycle_ids = _identity_values(lifecycle_row)
    for value in candidate_ids:
        if value and value in lifecycle_ids:
            return "identity"

    candidate_expression = _expression_key(candidate.get("expression"))
    lifecycle_expression = _expression_key(lifecycle_row.get("expression"))
    if candidate_expression and candidate_expression == lifecycle_expression:
        return "expression"

    candidate_digest = _expression_digest(candidate_expression)
    lifecycle_digest = _text(lifecycle_row.get("expression_digest"))
    if candidate_digest and candidate_digest == lifecycle_digest:
        return "expression_digest"
    return ""


def _identity_values(row: dict[str, Any]) -> set[str]:
    return {
        _text(row.get("alpha_id")),
        _text(row.get("official_alpha_id")),
        _text(row.get("simulation_id")),
    } - {""}


def _expression_key(value: Any) -> str:
    return " ".join(_text(value, max_length=500).lower().split())


def _expression_digest(value: str) -> str:
    return "expr_" + sha256(value.encode("utf-8")).hexdigest()[:12] if value else ""


def _category(row: dict[str, Any]) -> str:
    value = _text(row.get("status_category")).lower()
    return value or status_category(row)


def _text(value: Any, *, max_length: int = 160) -> str:
    return redact_text(value, max_length=max_length).strip()
