"""Score history persistence and convergence statistics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from brain_alpha_ops.jsonl import read_jsonl_records


class ScoreHistoryDB:
    """Lightweight score history store for convergence analysis."""

    DEFAULT_HISTORY_LIMIT = 5000

    def __init__(self, path: str = "data/score_history.jsonl"):
        target = Path(path)
        self._path = target if target.suffix.lower() == ".jsonl" else target / "score_history.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, result: Any) -> None:
        record = {
            "timestamp": result.evaluated_at,
            "alpha_id": result.alpha_id,
            "total_score": result.total_score,
            "decision_band": result.decision_band,
            "passed_gate": result.passed_gate,
            "api_deviation": result.api_output_deviation,
            "prior": result.prior.get("score"),
            "empirical": result.empirical.get("score"),
            "checklist": result.checklist.get("score"),
            "config_hash": result.config_hash,
        }
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def load_all(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        return read_jsonl_records(self._path, limit=limit)

    def convergence_stats(self, *, limit: int = DEFAULT_HISTORY_LIMIT) -> dict[str, Any]:
        """Compute convergence statistics from score history."""
        records = self.load_all(limit=limit)
        if len(records) < 3:
            return {"status": "insufficient_data", "count": len(records)}

        scores = [record["total_score"] for record in records]
        recent = scores[-10:] if len(scores) > 10 else scores

        return {
            "status": "ready",
            "total_evaluations": len(records),
            "history_limit": limit,
            "avg_score": round(sum(scores) / len(scores), 2),
            "recent_avg": round(sum(recent) / len(recent), 2),
            "std_dev": round(
                (sum((score - sum(scores) / len(scores)) ** 2 for score in scores) / len(scores)) ** 0.5,
                2,
            ),
            "trend": "improving"
            if recent[-1] > scores[0] + 3
            else "declining"
            if recent[-1] < scores[0] - 3
            else "stable",
            "pass_rate": round(
                sum(1 for record in records if record["passed_gate"]) / len(records),
                3,
            ),
            "api_zero_deviation_rate": round(
                sum(1 for record in records if record["api_deviation"] == 0.0) / len(records),
                3,
            ),
        }
