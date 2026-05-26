"""Executable coverage checks for the production diagnosis gap plan."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from brain_alpha_ops.web_check_availability import CHECK_LABELS


SCHEMA_VERSION = "diagnosis_gap_coverage.v1"
REQUIRED_DIMENSIONS = (
    "Functional closure",
    "Technical compliance",
    "Parameter accuracy",
    "Data lineage",
    "Experience",
    "Scoring",
)
REQUIRED_UPGRADE_AREAS = (
    "Architecture",
    "Data efficiency",
    "LLM prompting",
    "Backtest execution",
    "Errors and logs",
)


@dataclass(frozen=True)
class GapCoverageFinding:
    severity: str
    code: str
    message: str
    evidence: Any = None


def check_diagnosis_gap_coverage(
    config_path: str | Path | None = None,
    *,
    strict_freshness: bool = False,
) -> dict[str, Any]:
    """Check that the PDF diagnosis plan is covered by executable code paths."""
    from brain_alpha_ops.production_diagnostics import build_diagnostic_snapshot

    snapshot = build_diagnostic_snapshot(config_path)
    findings: list[GapCoverageFinding] = []
    _check_dimensions(snapshot, findings)
    _check_contract(snapshot, findings)
    _check_parameter_audit(snapshot, findings)
    _check_official_context(snapshot, findings, strict_freshness=strict_freshness)
    _check_scoring(snapshot, findings)
    _check_experience(snapshot, findings)
    _check_upgrade_plan(snapshot, findings)

    blocking_count = sum(1 for item in findings if item.severity == "P0")
    p1_count = sum(1 for item in findings if item.severity == "P1")
    ok = blocking_count == 0 and (not strict_freshness or p1_count == 0)
    return {
        "ok": ok,
        "schema_version": SCHEMA_VERSION,
        "config": str(config_path or ""),
        "strict_freshness": bool(strict_freshness),
        "blocking_count": blocking_count,
        "p1_count": p1_count,
        "finding_count": len(findings),
        "findings": [asdict(item) for item in findings],
        "snapshot_schema_version": snapshot.get("schema_version"),
        "coverage": {
            "dimensions": [row.get("dimension") for row in snapshot.get("gap_matrix") or []],
            "upgrade_areas": [row.get("area") for row in snapshot.get("upgrade_plan") or []],
            "parameter_audit": (snapshot.get("parameter_audit") or {}).get("schema_version", ""),
            "history_replay": (snapshot.get("history_replay") or {}).get("capability", ""),
            "frontend_inline": bool((snapshot.get("frontend_inline") or {}).get("ok")),
        },
    }


def _check_dimensions(snapshot: dict[str, Any], findings: list[GapCoverageFinding]) -> None:
    dimensions = {str(row.get("dimension") or "") for row in snapshot.get("gap_matrix") or []}
    missing = [item for item in REQUIRED_DIMENSIONS if item not in dimensions]
    if missing:
        findings.append(
            GapCoverageFinding(
                "P0",
                "missing_gap_dimensions",
                "The diagnosis gap matrix does not cover every required PDF dimension.",
                missing,
            )
        )


def _check_contract(snapshot: dict[str, Any], findings: list[GapCoverageFinding]) -> None:
    redline = snapshot.get("redline") or {}
    contract = snapshot.get("contract_comparison") or {}
    if not redline.get("ok", redline.get("overall") == "PASS"):
        findings.append(
            GapCoverageFinding(
                "P0",
                "redline_contract_failed",
                "BRAIN six-red-line verification must pass before the diagnosis plan is complete.",
                {"overall": redline.get("overall"), "failed": redline.get("failed")},
            )
        )
    if contract.get("thresholds_zero_deviation") is not True:
        findings.append(
            GapCoverageFinding(
                "P0",
                "thresholds_not_zero_deviation",
                "Configured thresholds must match canonical BRAIN thresholds exactly.",
                contract.get("thresholds"),
            )
        )
    if contract.get("frontend_inline_synced") is not True:
        findings.append(
            GapCoverageFinding(
                "P1",
                "frontend_not_synced",
                "The shipped Web artifact must be synchronized with source modules.",
                snapshot.get("frontend_inline"),
            )
        )


def _check_parameter_audit(snapshot: dict[str, Any], findings: list[GapCoverageFinding]) -> None:
    audit = snapshot.get("parameter_audit") or {}
    if audit.get("schema_version") != "parameter_audit_snapshot.v1":
        findings.append(
            GapCoverageFinding(
                "P0",
                "parameter_audit_missing",
                "Runtime parameter audit snapshot is missing from the diagnosis snapshot.",
                audit,
            )
        )
        return
    if audit.get("ok") is not True:
        for item in audit.get("findings") or []:
            findings.append(
                GapCoverageFinding(
                    str(item.get("severity") or "P0"),
                    f"parameter_audit_{item.get('code') or 'finding'}",
                    str(item.get("message") or "Parameter audit finding."),
                    item,
                )
            )
    required = set(audit.get("traceable_sections") or [])
    missing = [item for item in REQUIRED_TRACE_SECTIONS if item not in required]
    if missing:
        findings.append(
            GapCoverageFinding(
                "P0",
                "parameter_audit_sections_incomplete",
                "Parameter audit does not declare every required trace section.",
                missing,
            )
        )


def _check_official_context(
    snapshot: dict[str, Any],
    findings: list[GapCoverageFinding],
    *,
    strict_freshness: bool,
) -> None:
    validation = snapshot.get("official_context_validation") or {}
    contract = snapshot.get("contract_comparison") or {}
    refresh = snapshot.get("official_refresh") or {}
    if validation.get("blocking_ok") is not True:
        findings.append(
            GapCoverageFinding(
                "P0",
                "official_context_blocking",
                "Official fields/operators/datasets must pass structural and lineage checks.",
                validation.get("findings"),
            )
        )
    if contract.get("dataset_field_counts_match") is not True:
        findings.append(
            GapCoverageFinding(
                "P0",
                "dataset_lineage_mismatch",
                "Dataset field-count lineage must match official field records.",
                validation.get("lineage"),
            )
        )
    if strict_freshness and refresh.get("stale_count", 0):
        findings.append(
            GapCoverageFinding(
                "P1",
                "official_context_stale",
                "Strict mode requires non-stale official context metadata.",
                refresh,
            )
        )
    if strict_freshness and refresh.get("last_attempt_ok") is not True:
        findings.append(
            GapCoverageFinding(
                "P1",
                "official_refresh_not_verified",
                "Strict mode requires a successful credential-backed official context refresh record.",
                refresh,
            )
        )


def _check_scoring(snapshot: dict[str, Any], findings: list[GapCoverageFinding]) -> None:
    scoring = snapshot.get("scoring_probe") or {}
    if scoring.get("zero_deviation") is not True:
        findings.append(
            GapCoverageFinding(
                "P0",
                "scoring_not_zero_deviation",
                "API-shaped scoring probe must produce zero output deviation.",
                scoring.get("deviation_details"),
            )
        )
    if not scoring.get("settings_trace") or not scoring.get("threshold_trace"):
        findings.append(
            GapCoverageFinding(
                "P0",
                "scoring_trace_missing",
                "Scoring output must include settings and threshold traces.",
                {"settings_trace": scoring.get("settings_trace"), "threshold_trace": scoring.get("threshold_trace")},
            )
        )
    attribution = scoring.get("attribution_summary") or {}
    if attribution.get("schema_version") != "score_attribution_summary.v1":
        findings.append(
            GapCoverageFinding(
                "P1",
                "scoring_attribution_summary_missing",
                "Scoring output should expose a stable multidimensional attribution summary.",
                attribution,
            )
        )


def _check_experience(snapshot: dict[str, Any], findings: list[GapCoverageFinding]) -> None:
    history = snapshot.get("history_replay") or {}
    if history.get("capability") != "ready":
        findings.append(
            GapCoverageFinding(
                "P1",
                "history_replay_not_ready",
                "Guided checkpoint/run-history replay must remain available.",
                history,
            )
        )
    missing_suggestions = [
        name
        for name, (_label, suggestion) in CHECK_LABELS.items()
        if not str(suggestion or "").strip()
    ]
    if missing_suggestions:
        findings.append(
            GapCoverageFinding(
                "P1",
                "web_check_suggestions_missing",
                "Every Web pre-submit check should expose an actionable suggestion.",
                missing_suggestions,
            )
        )


def _check_upgrade_plan(snapshot: dict[str, Any], findings: list[GapCoverageFinding]) -> None:
    areas = {str(row.get("area") or "") for row in snapshot.get("upgrade_plan") or []}
    missing = [item for item in REQUIRED_UPGRADE_AREAS if item not in areas]
    if missing:
        findings.append(
            GapCoverageFinding(
                "P1",
                "upgrade_plan_areas_missing",
                "The QuantGPT-aligned upgrade plan must keep all PDF plan areas visible.",
                missing,
            )
        )


REQUIRED_TRACE_SECTIONS = (
    "ops.settings",
    "ops.budget",
    "ops.thresholds",
    "ops.submission_policy",
    "ops.scoring",
    "ops.official_api",
)
