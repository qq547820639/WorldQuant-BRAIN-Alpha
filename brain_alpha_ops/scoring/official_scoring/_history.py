"""History tracking mixin for OfficialScoringSystem."""
from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional

from brain_alpha_ops.scoring.official_scoring._constants import (
    _MAX_SCORE_HISTORY_PER_ALPHA,
    _MAX_SCORE_HISTORY_TOTAL_ENTRIES,
    _TREND_DELTA_DECLINING,
    _TREND_DELTA_IMPROVING,
    SCORING_VERSION,
)

logger = logging.getLogger("brain_alpha_ops.scoring.official_scoring")


class _HistoryMixin:
    """History tracking methods extracted from OfficialScoringSystem."""

    def _record_history(self, alpha_id: str, result) -> None:
        with self._lock:
            if alpha_id not in self._score_history:
                self._score_history[alpha_id] = []
            history = self._score_history[alpha_id]
            history.append({
                "timestamp": result.evaluated_at,
                "total_score": result.total_score,
                "decision_band": result.decision_band,
                "passed_gate": result.passed_gate,
                "api_deviation": result.api_output_deviation,
            })
            if len(history) > _MAX_SCORE_HISTORY_PER_ALPHA:
                del history[:-_MAX_SCORE_HISTORY_PER_ALPHA]
            self._trim_score_history()
        # Persist to disk for convergence tracking across restarts
        if self._persisted_history is not None:
            try:
                self._persisted_history.append(result)
            except Exception:
                logger.warning("failed to persist score history", exc_info=True)

    def _write_audit_trail(self, result) -> None:
        """Write scoring result to audit trail for traceability."""
        try:
            from brain_alpha_ops.audit_trail import write_scoring_audit
            write_scoring_audit(
                result,
                audit_dir=self._audit_trail_dir or "data/audit_trail",
                scoring_version=SCORING_VERSION,
            )
        except Exception:
            logger.warning("failed to write audit trail", exc_info=True)

    def _trim_score_history(self) -> None:
        total_entries = sum(len(history) for history in self._score_history.values())
        while total_entries > _MAX_SCORE_HISTORY_TOTAL_ENTRIES:
            oldest_alpha: str | None = None
            oldest_timestamp = ""
            for alpha_id, history in self._score_history.items():
                if not history:
                    oldest_alpha = alpha_id
                    oldest_timestamp = ""
                    break
                timestamp = str(history[0].get("timestamp", ""))
                if oldest_alpha is None or timestamp < oldest_timestamp:
                    oldest_alpha = alpha_id
                    oldest_timestamp = timestamp
            if oldest_alpha is None:
                break
            history = self._score_history.get(oldest_alpha, [])
            if history:
                history.pop(0)
                total_entries -= 1
            if not history:
                self._score_history.pop(oldest_alpha, None)

    def get_score_trend(self, alpha_id: str) -> Optional[str]:
        """Get score trend over evaluations: improving/stable/declining."""
        with self._lock:
            history = list(self._score_history.get(alpha_id, []))
        if len(history) < 2:
            return None
        first = history[0]["total_score"]
        last = history[-1]["total_score"]
        delta = last - first
        if delta > _TREND_DELTA_IMPROVING:
            return "improving"
        if delta < _TREND_DELTA_DECLINING:
            return "declining"
        return "stable"
