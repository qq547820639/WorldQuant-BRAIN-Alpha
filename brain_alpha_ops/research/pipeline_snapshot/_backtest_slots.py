"""Backtest slot snapshot renderer for progress and Web payloads."""

from __future__ import annotations

import time
from typing import Callable

from brain_alpha_ops.models import Candidate

from ..pipeline_helpers import slot_message, slot_progress_percent


def backtest_slot_snapshot(
    *,
    active_limit: int,
    candidate_at_slot: Callable[[int], Candidate | None],
    official_calls_halted: bool,
    official_halt_reason: str,
    cloud_correlation_risk: Callable[[Candidate], dict],
    now: float | None = None,
) -> list[dict]:
    """Render current backtest slots for progress and Web payloads."""

    current_time = time.monotonic() if now is None else float(now)
    rows = []
    for slot in range(1, active_limit + 1):
        candidate = candidate_at_slot(slot)
        if not candidate:
            status = "CAPACITY_WAIT" if official_calls_halted else "EMPTY"
            rows.append(
                {
                    "slot": slot,
                    "alpha_id": "",
                    "simulation_id": "",
                    "status": status,
                    "official_alpha_id": "",
                    "score": None,
                    "poll_count": 0,
                    "progress_percent": 0,
                    "next_poll_seconds": 0,
                    "message": (
                        f"官方调用暂停：{official_halt_reason}"
                        if official_calls_halted
                        else "空闲，等待候选进入官方回测。"
                    ),
                }
            )
            continue
        status = candidate.submission.get("simulation_status") or candidate.lifecycle_status
        next_poll_at = float(candidate.submission.get("next_poll_at", 0.0) or 0.0)
        rows.append(
            {
                "slot": slot,
                "alpha_id": candidate.alpha_id,
                "simulation_id": candidate.simulation_id,
                "status": status,
                "lifecycle_status": candidate.lifecycle_status,
                "official_alpha_id": candidate.official_alpha_id,
                "score": candidate.scorecard.get("total_score", 0.0),
                "family": candidate.family,
                "hypothesis": candidate.hypothesis,
                "expression": candidate.expression,
                "scorecard": candidate.scorecard,
                "local_quality": candidate.local_quality,
                "validation": candidate.validation,
                "official_metrics": candidate.official_metrics,
                "gate": candidate.gate,
                "cloud_correlation_risk": cloud_correlation_risk(candidate),
                "poll_count": candidate.submission.get("poll_count", 0),
                "progress_percent": slot_progress_percent(status),
                "next_poll_seconds": round(max(0.0, next_poll_at - current_time), 1),
                "message": slot_message(status),
            }
        )
    return rows
