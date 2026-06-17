"""BRAIN API output simulation and deviation comparison helpers.

Provides zero-deviation BRAIN API response simulation that:
- Matches BRAIN official Alpha Check response format exactly
- Compares all canonical metrics between configured and official values
- Produces detailed deviation reports for every mismatched field
"""
from __future__ import annotations

import math
from typing import Any

from brain_alpha_ops.brain_api.canonical import CANONICAL_METRIC_NAMES, CANONICAL_THRESHOLDS
from brain_alpha_ops.models import Candidate

# Tolerable floating-point epsilon for deviation detection
_ZERO_DEVIATION_EPSILON = 1e-9
_METRIC_VALUE_EPSILON = 0.001

def simulate_brain_api_output(
    candidate: Candidate,
    scorecard: dict[str, Any],
    thresholds: Any,
) -> tuple[dict[str, Any], float, list[str]]:
    """Simulate a BRAIN-alpha-check-like API output and compare deviations.

    Returns:
        (simulated_api_output, deviation_score, deviation_details)
        - deviation_score == 0.0 means perfect zero-deviation alignment
        - deviation_score > 0 indicates mismatch severity
    """
    deviations: list[str] = []

    empirical = scorecard.get("empirical", {})
    metrics = candidate.official_metrics or {}
    local_hard_gate_passed = not bool(empirical.get("hard_gate_failed", False))
    official_pass = str(metrics.get("pass_fail") or "").strip().upper()
    reconstructed_status = "PASS" if local_hard_gate_passed and metrics else "FAIL"
    has_official_pass_fail = official_pass in {"PASS", "FAIL"}
    api_status = official_pass if has_official_pass_fail else "UNKNOWN"
    official_pass_fail_source = (
        "candidate.official_metrics.pass_fail"
        if has_official_pass_fail
        else "missing_official_pass_fail"
        if metrics
        else "missing_official_metrics"
    )

    # Build BRAIN-official-format check items from all hard gate rows
    check_items: dict[str, dict[str, Any]] = {}
    for row in empirical.get("items", []):
        if not row.get("is_hard_gate"):
            continue
        check_items[row["name"]] = {
            "value": row.get("actual"),
            "threshold": row.get("target"),
            "direction": row.get("direction"),
            "passed": bool(row.get("passed")),
            "source": row.get("source", "BRAIN_Official_Alpha_Check"),
        }

    # Build full canonical threshold trace for zero-deviation verification
    canonical_thresholds_used: dict[str, float] = {}
    for key, canonical_value in CANONICAL_THRESHOLDS.items():
        try:
            configured = float(getattr(thresholds, key, canonical_value))
        except (TypeError, ValueError):
            configured = float(canonical_value)
        canonical_thresholds_used[key] = configured
        if abs(configured - float(canonical_value)) > _ZERO_DEVIATION_EPSILON:
            deviations.append(
                f"threshold deviation: {key}={configured} (canonical={canonical_value})"
            )

    # Build soft-gate warning items for quality targets
    soft_warnings: list[dict[str, Any]] = []
    for row in empirical.get("items", []):
        if row.get("is_hard_gate"):
            continue
        if not bool(row.get("passed")):
            soft_warnings.append({
                "name": row.get("name", ""),
                "actual": row.get("actual"),
                "target": row.get("target"),
                "direction": row.get("direction"),
                "source": row.get("source", "Advisor_Standard"),
            })

    # Build brain_checks dictionary (matching BRAIN check-result format)
    brain_checks_dict: dict[str, dict[str, Any]] = {}
    if isinstance(metrics.get("brain_checks"), dict):
        brain_checks_dict = {
            str(k): {
                "result": (v.get("result") or "").upper() if isinstance(v, dict) else "",
                "limit": v.get("limit") if isinstance(v, dict) else None,
                "value": v.get("value") if isinstance(v, dict) else None,
            }
            for k, v in metrics.get("brain_checks", {}).items()
            if isinstance(v, dict)
        }

    # Build the simulated API output matching BRAIN response format
    simulated = {
        "alpha_id": candidate.official_alpha_id or candidate.alpha_id,
        "expression": candidate.expression,
        "status": api_status,
        "checks": check_items,
        "brain_checks": brain_checks_dict,
        "score": {
            "total": scorecard["total_score"],
            "prior": scorecard["prior"]["score"],
            "empirical": scorecard["empirical"]["score"],
            "checklist": scorecard["submission_checklist"]["score"],
        },
        "gate": {
            "hard_gate_passed": has_official_pass_fail and api_status == "PASS",
            "reconstructed_hard_gate_passed": local_hard_gate_passed,
            "soft_gate_warnings": soft_warnings,
            "submission_ready": has_official_pass_fail and api_status == "PASS",
            "local_submission_ready": scorecard.get("decision_band") == "submit_candidate",
        },
        "meta": {
            "simulated": True,
            "scoring_schema": "scorecard-v2.3",
            "threshold_version": "CANONICAL_v2",
            "official_pass_fail_source": official_pass_fail_source,
            "thresholds_used": canonical_thresholds_used,
            "thresholds_zero_deviation": len(
                [d for d in deviations if d.startswith("threshold deviation")]
            ) == 0,
        },
    }

    # ── Zero-Deviation Calculation ──

    deviation = 0.0

    # Core pass/fail deviation
    if not has_official_pass_fail:
        deviation = 1.0
        deviations.append(
            "official pass_fail missing; local reconstructed hard gates are diagnostic only"
        )

    if candidate.official_metrics:
        # Pass/fail alignment
        if has_official_pass_fail and official_pass != reconstructed_status:
            deviation = 1.0
            deviations.append(
                f"pass_fail mismatch: official={official_pass}, reconstructed={reconstructed_status}"
            )
        elif official_pass == "FAIL" and empirical.get("hard_gate_failed"):
            for reason in empirical.get("hard_gate_failures", [])[:3]:
                deviations.append(f"official FAIL reconstructed from hard gate: {reason}")

        # Compare all canonical metrics with official values
        metric_value_comparisons = _compare_canonical_metrics(metrics, simulated, scorecard)
        for msg in metric_value_comparisons:
            deviations.append(msg)
            deviation = max(deviation, 0.5)

        # Self-correlation status comparison
        sc_status = str(metrics.get("self_correlation_status") or "").upper()
        if sc_status in {"FAIL", "FAILED"} and simulated["checks"].get("self_correlation", {}).get("passed"):
            deviations.append(
                "self_correlation mismatch: official FAIL but local gate passed"
            )
            deviation = max(deviation, 0.5)

    # Threshold deviation penalty
    threshold_deviations = [d for d in deviations if d.startswith("threshold deviation")]
    if threshold_deviations:
        deviation = max(deviation, 1.0)

    return simulated, deviation, deviations

def _compare_canonical_metrics(
    metrics: dict[str, Any],
    simulated: dict[str, Any],
    scorecard: dict[str, Any],
) -> list[str]:
    """Compare all BRAIN canonical metrics between official and simulated values.

    Returns a list of deviation messages for any metric mismatch.
    """
    deviations: list[str] = []

    # Metric key mapping: canonical -> official_metrics key -> simulated source
    metric_sources: list[tuple[str, str, str | None]] = [
        ("sharpe", "sharpe", None),          # direct comparison
        ("fitness", "fitness", None),         # direct comparison
        ("turnover", "turnover", "turnover"),
        ("returns", "returns", None),
        ("drawdown", "drawdown", "drawdown"),
        ("correlation", "correlation", "correlation"),
        ("self_correlation", "self_correlation", "self_correlation"),
        ("prod_correlation", "prod_correlation", "prod_correlation"),
        ("weight_concentration", "weight_concentration", "weight_concentration"),
        ("sub_universe_sharpe", "sub_universe_sharpe", "sub_universe_sharpe"),
        ("margin", "margin", None),
    ]

    for metric_name, official_key, _sim_key in metric_sources:
        if official_key not in metrics:
            continue
        official_val = _float_or_none(metrics.get(official_key))
        if official_val is None:
            continue

        # Find simulated value in check items
        simulated_val = None
        check_entry = simulated["checks"].get(metric_name)
        if isinstance(check_entry, dict):
            simulated_val = _float_or_none(check_entry.get("value"))

        # Fallback: try empirical items
        if simulated_val is None:
            empirical = scorecard.get("empirical", {})
            for row in empirical.get("items", []):
                if isinstance(row, dict) and row.get("name") == metric_name:
                    simulated_val = _float_or_none(row.get("actual"))
                    break

        if simulated_val is not None:
            if abs(official_val - simulated_val) > _METRIC_VALUE_EPSILON:
                deviations.append(
                    f"{metric_name} mismatch: official={official_val:.6f}, simulated={simulated_val:.6f}"
                )

    # Special: cross-check brain_checks for failed items
    brain_checks = metrics.get("brain_checks", {})
    if isinstance(brain_checks, dict):
        for check_name, check_data in brain_checks.items():
            if not isinstance(check_data, dict):
                continue
            result = str(check_data.get("result") or "").upper()
            if result in {"FAIL", "FAILED"}:
                check_lower = check_name.lower().replace("_", "")
                # Check if any simulated hard gate matches this check
                matched = False
                for sim_name, sim_entry in simulated["checks"].items():
                    if not isinstance(sim_entry, dict):
                        continue
                    if sim_name.lower().replace("_", "") == check_lower:
                        matched = True
                        if sim_entry.get("passed"):
                            deviations.append(
                                f"{check_name} mismatch: official FAIL but local gate passed"
                            )
                        break
                if not matched:
                    deviations.append(
                        f"{check_name}: official has FAIL check not found in simulated gates"
                    )

    return deviations

def _float_or_none(value: Any) -> float | None:
    """Safely convert to float, returning None for non-numeric values."""
    if value is None or isinstance(value, bool):
        return None
    try:
        val = float(value)
        if math.isnan(val) or math.isinf(val):
            return None
        return val
    except (TypeError, ValueError):
        return None

# Public API for simple PASS/FAIL deviation check
def is_zero_deviation(
    candidate: Candidate,
    scorecard: dict[str, Any],
    thresholds: Any,
) -> bool:
    """Quick check: is there any deviation between official and simulated API output?"""
    _simulated, deviation, _details = simulate_brain_api_output(candidate, scorecard, thresholds)
    return deviation == 0.0

# Public API: canonical threshold compliance
def check_threshold_compliance(thresholds: Any) -> tuple[bool, list[str]]:
    """Verify all configured thresholds match BRAIN canonical values exactly.

    Returns (is_compliant, deviation_messages).
    """
    deviations: list[str] = []
    for key, canonical_value in CANONICAL_THRESHOLDS.items():
        try:
            configured = float(getattr(thresholds, key, canonical_value))
        except (TypeError, ValueError):
            configured = float(canonical_value)
        if abs(configured - float(canonical_value)) > _ZERO_DEVIATION_EPSILON:
            deviations.append(
                f"{key}: configured={configured} != canonical={canonical_value}"
            )
    return len(deviations) == 0, deviations
