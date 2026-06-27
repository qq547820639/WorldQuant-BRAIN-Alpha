"""Anti-overfit audit wiring (Workstream B4.1).

Routes ``MutationResult`` and ``StrategyLifecycleTracker`` events into the
lifecycle audit trail via the B3 ``record_*`` helpers. Records per-Alpha:
source, variant generation reason, feedback signal, elimination reason,
optimization count, and official-simulation reach.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from brain_alpha_ops.audit_trail.lifecycle_writer import (
    record_gate_decision,
    record_lifecycle_transition,
    record_optimization_suggestion,
)
from brain_alpha_ops.redaction import redact_error_message

logger = logging.getLogger(__name__)


def record_mutation_result(
    *, alpha_id: str, mutation: Any,
    context: dict[str, Any] | None = None,
) -> None:
    """Record a ``MutationResult`` to the audit trail.

    Maps ``mutation.reason`` → suggestion, ``mutation.parent_failure`` →
    parent_failure, ``mutation.mode`` → expected_effect. Best-effort: never
    raises (audit must not break the pipeline).
    """
    reason = str(getattr(mutation, "reason", "") or "")
    parent_failure = str(getattr(mutation, "parent_failure", "") or "")
    mode = str(getattr(mutation, "mode", "") or "")
    metadata = dict(getattr(mutation, "metadata", {}) or {})
    ctx = dict(context or {})
    ctx.setdefault("mutation_mode", mode)
    ctx.setdefault("mutation_metadata", metadata)
    try:
        record_optimization_suggestion(
            alpha_id=alpha_id,
            suggestion=reason or f"mutation:{mode}",
            expected_effect=mode,
            parent_failure=parent_failure,
            context=ctx,
        )
    except Exception as exc:  # noqa: BLE001 — audit must never break the pipeline
        logger.debug("mutation audit skipped: %s", redact_error_message(exc))


def record_strategy_event(row: dict[str, Any]) -> None:
    """Route a ``StrategyLifecycleTracker`` record to the audit trail.

    Action mapping:
    - ``mutate``/``retire`` → ``record_optimization_suggestion``
      (variant reason / elimination reason)
    - ``validate`` → ``record_gate_decision`` (feedback signal)
    - ``propose``/``reward`` → ``record_lifecycle_transition`` (best-effort)
    """
    action = str(row.get("action", "") or "")
    profile_id = str(row.get("profile_id", "") or "")
    reason = str(row.get("reason", "") or "")
    metrics = dict(row.get("metrics", {}) or {})
    meta = _row_meta(row)
    try:
        if action in ("mutate", "retire"):
            record_optimization_suggestion(
                alpha_id=profile_id,
                suggestion=reason or f"strategy:{action}",
                expected_effect=action,
                parent_failure=str(row.get("parent_profile_id", "") or ""),
                context={"strategy_action": action, **metrics, **meta},
            )
        elif action == "validate":
            ready_rate = float(metrics.get("ready_rate", 0.0) or 0.0)
            record_gate_decision(
                alpha_id=profile_id,
                gate_name="strategy_validation",
                passed=ready_rate > 0.0,
                reason=reason,
                attribution=metrics,
                context=meta,
            )
        else:
            record_lifecycle_transition(
                alpha_id=profile_id, from_state="", to_state=action,
                reason=reason, trigger_rule="strategy_lifecycle",
                context={**metrics, **meta},
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("strategy audit skipped: %s", redact_error_message(exc))


def make_strategy_audit_sink(
    next_sink: Callable[[dict[str, Any]], None] | None = None,
) -> Callable[[dict[str, Any]], None]:
    """Compose a ``record_sink`` that writes to the audit trail then chains.

    Usage::

        tracker = StrategyLifecycleTracker(
            record_sink=make_strategy_audit_sink(existing_sink),
        )
    """
    def _sink(row: dict[str, Any]) -> None:
        record_strategy_event(row)
        if next_sink is not None:
            try:
                next_sink(row)
            except Exception:  # noqa: BLE001
                logger.debug("strategy audit sink downstream failed", exc_info=True)
    return _sink


def record_alpha_origin(
    *, alpha_id: str, source: str,
    context: dict[str, Any] | None = None,
) -> None:
    """Record the origin/source of an Alpha (B4.1: 来源)."""
    try:
        record_lifecycle_transition(
            alpha_id=alpha_id, from_state="", to_state="draft",
            reason=f"alpha_origin:{source}", trigger_rule="origin",
            context={"source": source, **dict(context or {})},
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("alpha origin audit skipped: %s", redact_error_message(exc))


def _row_meta(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "cycle": row.get("cycle", 0),
        "profile_index": row.get("profile_index", 0),
        "profile_name": row.get("profile_name", ""),
    }
