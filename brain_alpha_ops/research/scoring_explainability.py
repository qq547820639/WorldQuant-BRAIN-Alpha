"""Explainability helpers for scorecard payloads."""

from __future__ import annotations


def scorecard_top_failures(scorecard: dict, *, limit: int = 8) -> list[dict[str, str]]:
    """Return the most actionable failed scoring and submission checks."""
    failures: list[dict[str, str]] = []
    empirical = scorecard.get("empirical", {}) if isinstance(scorecard, dict) else {}
    for row in empirical.get("items", []) if isinstance(empirical, dict) else []:
        if isinstance(row, dict) and not row.get("passed"):
            failures.append({
                "severity": "blocking" if row.get("is_hard_gate") else "warning",
                "item": str(row.get("name", "")),
                "reason": f"actual={row.get('actual')} {row.get('direction')} target={row.get('target')}",
            })
    checklist = scorecard.get("submission_checklist", {}) if isinstance(scorecard, dict) else {}
    for row in checklist.get("items", []) if isinstance(checklist, dict) else []:
        if isinstance(row, dict) and not row.get("passed"):
            failures.append({
                "severity": "blocking",
                "item": str(row.get("name", "")),
                "reason": str(row.get("meaning") or "submission checklist item did not pass"),
            })
    return failures[: max(1, int(limit or 1))]


def scorecard_improvement_hints(scorecard: dict, *, limit: int = 6) -> list[str]:
    """Translate scorecard failures into short user-facing repair hints."""
    hints: list[str] = []
    empirical = scorecard.get("empirical", {}) if isinstance(scorecard, dict) else {}
    failed_names = {
        str(row.get("name", ""))
        for row in empirical.get("items", []) if isinstance(row, dict) and not row.get("passed")
    } if isinstance(empirical, dict) else set()
    if {"sharpe", "fitness"} & failed_names:
        hints.append("Improve risk-adjusted return before another official submission check.")
    if {"turnover_min", "turnover_platform", "turnover_quality"} & failed_names:
        hints.append("Adjust decay, windows, or neutralization to bring turnover back into the official range.")
    if {"self_correlation", "prod_correlation"} & failed_names:
        hints.append("Generate a structurally different expression or use a different field family to reduce correlation risk.")
    if "weight_concentration" in failed_names:
        hints.append("Add broader cross-sectional normalization to reduce single-name concentration.")
    if "sub_universe_sharpe" in failed_names:
        hints.append("Improve sub-universe robustness before treating this Alpha as submission-ready.")
    checklist = scorecard.get("submission_checklist", {}) if isinstance(scorecard, dict) else {}
    failed_checklist = {
        str(row.get("name", ""))
        for row in checklist.get("items", []) if isinstance(row, dict) and not row.get("passed")
    } if isinstance(checklist, dict) else set()
    if "official_metrics_present" in failed_checklist:
        hints.append("Run official simulation so the local score is backed by BRAIN metrics.")
    if "official_pass" in failed_checklist:
        hints.append("Resolve failed official Alpha Check items before submission.")
    if not hints:
        hints.append("No blocking scoring failures detected; keep monitoring freshness, duplication, and submission preflight.")
    return hints[: max(1, int(limit or 1))]
