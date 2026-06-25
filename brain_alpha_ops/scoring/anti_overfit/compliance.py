from __future__ import annotations

import re
from typing import Any

from .models import (
    ComplianceGuardrailResult,
    DUPLICATE_SUBMISSION_WINDOW_DAYS,
    HIGH_FREQUENCY_RETRY_THRESHOLD,
    PARAMETER_TWEAK_IMPROVEMENT_THRESHOLD,
    SIMILARITY_THRESHOLD,
)


def _tokenize_expression(expression: str) -> set[str]:
    """Tokenize an expression into a set of meaningful tokens for comparison."""
    tokens = re.findall(r'[a-zA-Z_]\w*', expression.lower())
    return set(tokens)


def check_expression_similarity(
    expression_a: str,
    expression_b: str,
    *,
    threshold: float = SIMILARITY_THRESHOLD,
) -> dict[str, Any]:
    """Check similarity between two expressions using token-based comparison.

    Returns similarity score (0-1) and whether it exceeds the threshold.
    """
    tokens_a = _tokenize_expression(expression_a)
    tokens_b = _tokenize_expression(expression_b)
    if not tokens_a or not tokens_b:
        return {"score": 0.0, "blocked": False, "details": "empty expression"}
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    jaccard = len(intersection) / len(union) if union else 0.0
    blocked = jaccard >= threshold
    details = ""
    if blocked:
        details = (
            f"expression similarity {jaccard:.3f} >= {threshold} threshold; "
            f"shared tokens: {sorted(intersection)[:10]}"
        )
    return {"score": jaccard, "blocked": blocked, "details": details}


def check_parameter_tweak(
    current_metrics: dict[str, Any],
    previous_metrics: dict[str, Any],
    *,
    improvement_threshold: float = PARAMETER_TWEAK_IMPROVEMENT_THRESHOLD,
) -> dict[str, Any]:
    """Detect parameter tweaks that only change Decay/Delay with <5% improvement.

    Compares current vs previous metrics. If only decay/delay changed and
    the improvement is below the threshold, flags as a parameter tweak.
    """
    changed_keys = set()
    improved_keys = set()
    decay_delay_only = True
    for key in set(list(current_metrics.keys()) + list(previous_metrics.keys())):
        curr = current_metrics.get(key)
        prev = previous_metrics.get(key)
        if curr == prev:
            continue
        changed_keys.add(key)
        key_lower = key.lower()
        if key_lower not in ("decay", "delay"):
            decay_delay_only = False
        if isinstance(curr, (int, float)) and isinstance(prev, (int, float)) and prev != 0:
            improvement = (curr - prev) / abs(prev)
            if improvement > 0:
                improved_keys.add(key)
    flagged = False
    details = ""
    if changed_keys and decay_delay_only and improved_keys:
        max_improvement = 0.0
        for key in improved_keys:
            curr = current_metrics.get(key, 0)
            prev = previous_metrics.get(key, 0)
            if isinstance(curr, (int, float)) and isinstance(prev, (int, float)) and prev != 0:
                imp = (curr - prev) / abs(prev)
                max_improvement = max(max_improvement, imp)
        if max_improvement < improvement_threshold:
            flagged = True
            details = (
                f"parameter tweak detected: only Decay/Delay changed, "
                f"improvement {max_improvement:.1%} < {improvement_threshold:.0%} threshold"
            )
    return {"flagged": flagged, "details": details}


def check_duplicate_submission(
    expression: str,
    submission_history: list[dict[str, Any]],
    *,
    window_days: int = DUPLICATE_SUBMISSION_WINDOW_DAYS,
) -> dict[str, Any]:
    """Check if the same expression was submitted within the window period.

    Args:
        expression: current expression to check
        submission_history: list of dicts with 'expression' and 'submitted_at' keys
        window_days: lookback window in days

    Returns dict with blocked flag and details.
    """
    from datetime import datetime, timedelta, timezone

    normalized = expression.strip().lower()
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    for entry in submission_history:
        prev_expr = str(entry.get("expression", "")).strip().lower()
        if prev_expr != normalized:
            continue
        submitted_at = entry.get("submitted_at", "")
        if not submitted_at:
            continue
        try:
            ts = datetime.fromisoformat(submitted_at)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
        if ts >= cutoff:
            return {
                "blocked": True,
                "details": (
                    f"same expression submitted {submitted_at} "
                    f"(within {window_days}-day window)"
                ),
                "previous_submission": submitted_at,
            }
    return {"blocked": False, "details": ""}


def check_high_frequency_retry(
    expression: str,
    failure_history: list[dict[str, Any]],
    *,
    threshold: int = HIGH_FREQUENCY_RETRY_THRESHOLD,
) -> dict[str, Any]:
    """Detect high-frequency retry: >threshold failures for the same expression.

    Args:
        expression: current expression
        failure_history: list of dicts with 'expression' and 'failed_at' keys
        threshold: maximum allowed failures

    Returns dict with blocked flag, failure count, and details.
    """
    normalized = expression.strip().lower()
    failure_count = sum(
        1 for entry in failure_history
        if str(entry.get("expression", "")).strip().lower() == normalized
    )
    blocked = failure_count > threshold
    details = ""
    if blocked:
        details = (
            f"high-frequency retry detected: {failure_count} failures "
            f"for this expression (threshold: {threshold})"
        )
    return {
        "blocked": blocked,
        "failure_count": failure_count,
        "details": details,
    }


def run_compliance_guardrails(
    expression: str,
    *,
    candidate_metrics: dict[str, Any] | None = None,
    previous_metrics: dict[str, Any] | None = None,
    submission_history: list[dict[str, Any]] | None = None,
    failure_history: list[dict[str, Any]] | None = None,
    reference_expressions: list[str] | None = None,
    similarity_threshold: float = SIMILARITY_THRESHOLD,
    improvement_threshold: float = PARAMETER_TWEAK_IMPROVEMENT_THRESHOLD,
    duplicate_window_days: int = DUPLICATE_SUBMISSION_WINDOW_DAYS,
    retry_threshold: int = HIGH_FREQUENCY_RETRY_THRESHOLD,
) -> ComplianceGuardrailResult:
    """Run all compliance guardrail checks.

    Args:
        expression: current expression to validate
        candidate_metrics: current candidate metrics (for parameter tweak check)
        previous_metrics: previous candidate metrics (for parameter tweak check)
        submission_history: past submissions (for duplicate detection)
        failure_history: past failures (for retry detection)
        reference_expressions: existing expressions (for similarity check)
        similarity_threshold: auto-block threshold for similarity (default 0.95)
        improvement_threshold: minimum improvement for parameter tweaks (default 5%)
        duplicate_window_days: lookback window for duplicates (default 7 days)
        retry_threshold: max failures before blocking (default 3)

    Returns ComplianceGuardrailResult with all check results.
    """
    result = ComplianceGuardrailResult()

    if reference_expressions:
        best_score = 0.0
        best_details = ""
        for ref_expr in reference_expressions:
            check = check_expression_similarity(
                expression, ref_expr, threshold=similarity_threshold
            )
            if check["score"] > best_score:
                best_score = check["score"]
                best_details = check["details"]
            if check["blocked"]:
                result.similarity_block = True
                result.similarity_score = best_score
                result.similarity_details = best_details
                break
        if not result.similarity_block:
            result.similarity_score = best_score
            result.similarity_details = best_details

    if candidate_metrics and previous_metrics:
        tweak = check_parameter_tweak(
            candidate_metrics, previous_metrics,
            improvement_threshold=improvement_threshold,
        )
        result.parameter_tweak_flag = tweak["flagged"]
        result.parameter_tweak_details = tweak["details"]

    if submission_history:
        dup = check_duplicate_submission(
            expression, submission_history, window_days=duplicate_window_days,
        )
        result.duplicate_block = dup["blocked"]
        result.duplicate_details = dup["details"]

    if failure_history:
        retry = check_high_frequency_retry(
            expression, failure_history, threshold=retry_threshold,
        )
        result.high_frequency_block = retry["blocked"]
        result.high_frequency_failure_count = retry["failure_count"]
        result.high_frequency_details = retry["details"]

    block_reasons: list[str] = []
    if result.similarity_block:
        block_reasons.append(f"similarity: {result.similarity_details}")
    if result.parameter_tweak_flag:
        block_reasons.append(f"parameter_tweak: {result.parameter_tweak_details}")
    if result.duplicate_block:
        block_reasons.append(f"duplicate: {result.duplicate_details}")
    if result.high_frequency_block:
        block_reasons.append(f"high_frequency: {result.high_frequency_details}")

    result.block_reasons = block_reasons
    result.overall_blocked = bool(block_reasons)
    return result
