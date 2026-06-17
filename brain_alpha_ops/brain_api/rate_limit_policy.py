"""Official BRAIN call pacing policy checks."""

from __future__ import annotations

from typing import Any


OFFICIAL_RATE_LIMITS: dict[str, dict[str, Any]] = {
    "max_concurrent_simulations_regular": {
        "max": 3,
        "doc_source": "BRAIN API - regular user concurrent simulation limit",
    },
    "max_concurrent_simulations_pre_consultant": {
        "max": 5,
        "doc_source": "BRAIN API - pre-consultant concurrent simulation limit",
    },
    "max_concurrent_simulations_consultant": {
        "max": 10,
        "doc_source": "BRAIN API - consultant concurrent simulation limit",
    },
    "min_retry_pause_seconds": {
        "min": 60,
        "doc_source": "Community best practice - batch interval recommendation",
    },
    "rate_limit_backoff_initial": {
        "min": 60,
        "doc_source": "BRAIN API - recommended initial backoff (60s to 3600s max)",
    },
}


def validate_rate_limit_policy(
    budget: dict[str, Any],
    api_config: dict[str, Any],
) -> list[dict[str, Any]]:
    """Validate account-safety limits for official BRAIN calls."""

    issues: list[dict[str, Any]] = []
    max_regular = int(OFFICIAL_RATE_LIMITS["max_concurrent_simulations_regular"]["max"])
    min_retry_pause = float(OFFICIAL_RATE_LIMITS["min_retry_pause_seconds"]["min"])
    min_backoff = float(OFFICIAL_RATE_LIMITS["rate_limit_backoff_initial"]["min"])

    max_concurrent = budget.get("max_official_concurrent_simulations")
    if max_concurrent is not None and int(max_concurrent) > max_regular:
        issues.append({
            "severity": "ERROR",
            "check": "official_concurrency_exceeds_regular_limit",
            "details": (
                "max_official_concurrent_simulations is "
                f"{max_concurrent}, but regular BRAIN accounts must stay at or below {max_regular}."
            ),
            "fix": f"Set max_official_concurrent_simulations to {max_regular} or lower.",
        })

    batch_size = budget.get("official_backtest_batch_size")
    if batch_size is not None and max_concurrent is not None and int(batch_size) > int(max_concurrent):
        issues.append({
            "severity": "ERROR",
            "check": "official_batch_size_exceeds_concurrency",
            "details": (
                f"official_backtest_batch_size is {batch_size}, which exceeds "
                f"max_official_concurrent_simulations={max_concurrent}."
            ),
            "fix": "Set official_backtest_batch_size no higher than max_official_concurrent_simulations.",
        })

    retry_pause = budget.get("official_retry_pause_seconds")
    if retry_pause is not None and float(retry_pause) < min_retry_pause:
        issues.append({
            "severity": "ERROR",
            "check": "official_retry_pause_too_short",
            "details": (
                f"official_retry_pause_seconds is {retry_pause}, but the traced "
                f"minimum safe batch pause is {min_retry_pause} seconds."
            ),
            "fix": f"Set official_retry_pause_seconds to at least {min_retry_pause}.",
        })

    if budget.get("stop_official_calls_on_rate_limit") is False:
        issues.append({
            "severity": "WARNING",
            "check": "official_rate_limit_does_not_halt_cycle",
            "details": (
                "stop_official_calls_on_rate_limit is false; official rate-limit responses "
                "should halt the current cycle instead of continuing to spend call budget."
            ),
            "fix": "Set stop_official_calls_on_rate_limit to true for production runs.",
        })

    backoff = api_config.get("rate_limit_backoff_seconds")
    if backoff is not None and float(backoff) < min_backoff:
        issues.append({
            "severity": "ERROR",
            "check": "official_rate_limit_backoff_too_short",
            "details": (
                f"rate_limit_backoff_seconds is {backoff}, but the traced initial "
                f"rate-limit backoff is {min_backoff} seconds."
            ),
            "fix": f"Set rate_limit_backoff_seconds to at least {min_backoff}.",
        })

    if api_config.get("allow_stale_context_on_rate_limit") is True:
        issues.append({
            "severity": "WARNING",
            "check": "stale_context_allowed_on_rate_limit",
            "details": (
                "allow_stale_context_on_rate_limit is true; production compliance checks "
                "should fail closed when official context cannot be refreshed."
            ),
            "fix": "Set allow_stale_context_on_rate_limit to false for production release checks.",
        })

    return issues
