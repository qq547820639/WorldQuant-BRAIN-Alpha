"""Run-history analytics for guided production replay and comparison."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class RunHistoryAnalytics:
    """Read run-history snapshots and build lightweight comparison analytics."""

    def __init__(self, storage_dir: str):
        self.storage_dir = str(storage_dir)
        self.history_dir = Path(storage_dir) / "run_history"

    def list_history(self, *, limit: int = 10) -> list[dict[str, Any]]:
        records = []
        for path in self._history_files(limit=limit):
            payload = self.load_run(path.stem)
            if payload:
                records.append(self.summarize(payload, path=path))
        return records

    def load_run(self, run_id: str) -> dict[str, Any] | None:
        path = self.history_dir / f"{run_id}.json"
        if not path.exists() and run_id == "latest":
            path = self.history_dir / "latest.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def analytics(self, *, limit: int = 10) -> dict[str, Any]:
        history = self.list_history(limit=limit)
        latest = history[0] if history else None
        previous = history[1] if len(history) > 1 else None
        return {
            "ok": True,
            "schema_version": "run_history_analytics.v1",
            "storage_dir": self.storage_dir,
            "history_count": len(history),
            "latest": latest,
            "previous": previous,
            "latest_comparison": self.compare_summaries(latest, previous) if latest and previous else None,
            "trend": self.trend(history),
            "history": history,
        }

    def compare(self, left_run_id: str, right_run_id: str) -> dict[str, Any]:
        left = self.load_run(left_run_id)
        right = self.load_run(right_run_id)
        if not left or not right:
            return {
                "ok": False,
                "schema_version": "run_history_comparison.v1",
                "error": "run_not_found",
                "left_run_id": left_run_id,
                "right_run_id": right_run_id,
            }
        comparison = self.compare_summaries(self.summarize(left), self.summarize(right))
        return {
            "ok": True,
            "schema_version": "run_history_comparison.v1",
            "left": self.summarize(left),
            "right": self.summarize(right),
            "deltas": comparison["deltas"],
            "better_than_right": comparison["better_than_right"],
            "comparison": comparison,
        }

    @staticmethod
    def summarize(payload: dict[str, Any], *, path: Path | None = None) -> dict[str, Any]:
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        candidates = _first_list(summary.get("candidates"), payload.get("candidates"))
        passed = _first_list(summary.get("passed_candidates"), payload.get("passed_candidates"))
        phases = _first_list(payload.get("phases"))
        best_score = _best_score(summary, candidates)
        return {
            "run_id": str(payload.get("run_id") or (path.stem if path else "")),
            "started_at": str(payload.get("started_at") or payload.get("timestamp") or ""),
            "completed_at": str(payload.get("completed_at") or payload.get("timestamp") or ""),
            "status": str(payload.get("status") or "unknown"),
            "candidates": _int_or(summary.get("total_candidates"), summary.get("produced_count"), len(candidates)),
            "submissions": _int_or(summary.get("auto_submitted"), summary.get("submitted_this_run"), 0),
            "submission_ready": _int_or(summary.get("submission_ready"), summary.get("ready_results_count"), len(passed)),
            "officially_simulated": _int_or(summary.get("officially_simulated"), 0),
            "official_validation_attempted": _int_or(summary.get("official_validation_attempted"), 0),
            "official_validation_passed": _int_or(summary.get("official_validation_passed"), 0),
            "best_score": best_score,
            "phases_completed": sum(1 for item in phases if item.get("status") == "completed"),
            "phase_count": len(phases),
            "duration_seconds": _duration_seconds(payload),
            "checkpoint_path": str(payload.get("checkpoint_path") or ""),
            "parameter_audit": _parameter_audit_summary(payload.get("parameter_audit")),
            "file": str(path) if path else "",
        }

    @staticmethod
    def compare_summaries(left: dict[str, Any] | None, right: dict[str, Any] | None) -> dict[str, Any]:
        left = left or {}
        right = right or {}
        keys = [
            "candidates",
            "submission_ready",
            "submissions",
            "officially_simulated",
            "official_validation_attempted",
            "official_validation_passed",
            "best_score",
            "phases_completed",
        ]
        return {
            "left_run_id": left.get("run_id", ""),
            "right_run_id": right.get("run_id", ""),
            "deltas": {key: round(_num(left.get(key)) - _num(right.get(key)), 4) for key in keys},
            "better_than_right": {
                "best_score": _num(left.get("best_score")) > _num(right.get("best_score")),
                "submission_ready": _num(left.get("submission_ready")) > _num(right.get("submission_ready")),
                "submissions": _num(left.get("submissions")) > _num(right.get("submissions")),
            },
        }

    @staticmethod
    def trend(history: list[dict[str, Any]]) -> dict[str, Any]:
        if not history:
            return {"status": "empty", "count": 0}
        scores = [_num(row.get("best_score")) for row in history if row.get("best_score") is not None]
        ready = [_num(row.get("submission_ready")) for row in history]
        return {
            "status": "ready" if len(history) >= 2 else "single_run",
            "count": len(history),
            "avg_best_score": round(sum(scores) / len(scores), 4) if scores else 0.0,
            "avg_submission_ready": round(sum(ready) / len(ready), 4) if ready else 0.0,
            "latest_best_score": scores[0] if scores else 0.0,
            "oldest_best_score": scores[-1] if scores else 0.0,
        }

    def _history_files(self, *, limit: int) -> list[Path]:
        if not self.history_dir.exists():
            return []
        files = [path for path in self.history_dir.glob("*.json") if path.name != "latest.json"]
        files.sort(key=_history_file_sort_key, reverse=True)
        if not files:
            latest = self.history_dir / "latest.json"
            files = [latest] if latest.is_file() else []
        return files[: max(1, int(limit or 1))]


def _first_list(*values: Any) -> list[dict[str, Any]]:
    for value in values:
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def _best_score(summary: dict[str, Any], candidates: list[dict[str, Any]]) -> float:
    if "best_score" in summary:
        return _num(summary.get("best_score"))
    scores = []
    for candidate in candidates:
        scorecard = candidate.get("scorecard") if isinstance(candidate.get("scorecard"), dict) else {}
        scores.append(_num(scorecard.get("total_score", candidate.get("score", 0.0))))
    return round(max(scores), 4) if scores else 0.0


def _duration_seconds(payload: dict[str, Any]) -> float:
    started = str(payload.get("started_at") or "")
    completed = str(payload.get("completed_at") or "")
    if not started or not completed:
        return 0.0
    try:
        return round((datetime.fromisoformat(completed) - datetime.fromisoformat(started)).total_seconds(), 4)
    except ValueError:
        return 0.0


def _int_or(*values: Any) -> int:
    for value in values:
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return 0


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parameter_audit_summary(value: Any) -> dict[str, Any]:
    audit = value if isinstance(value, dict) else {}
    return {
        "schema_version": str(audit.get("schema_version") or ""),
        "ok": bool(audit.get("ok")) if audit else False,
        "config_hash": str(audit.get("config_hash") or ""),
        "traceable_sections": list(audit.get("traceable_sections") or []),
        "thresholds_zero_deviation": bool(audit.get("thresholds_zero_deviation")) if audit else False,
        "api_paths_aligned": bool(audit.get("api_paths_aligned")) if audit else False,
    }


def _history_file_sort_key(path: Path) -> tuple[str, float, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    completed = str(
        payload.get("completed_at")
        or payload.get("timestamp")
        or payload.get("started_at")
        or ""
    )
    try:
        modified = path.stat().st_mtime
    except OSError:
        modified = 0.0
    return completed, modified, path.name
