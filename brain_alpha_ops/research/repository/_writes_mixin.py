"""Write-side mixin for ``ResearchRepository``: persist records to JSONL files."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from brain_alpha_ops.jsonl import read_jsonl_tail
from brain_alpha_ops.models import Candidate, PipelineEvent, utc_now
from brain_alpha_ops.research.contracts import (
    assistant_guidance_record,
    backtest_record,
    lifecycle_record,
    strategy_lifecycle_record,
)
from brain_alpha_ops.research.guidance import ensure_assistant_guidance_digest
from brain_alpha_ops.research.repository._constants import (
    _repository_safe,
    _with_expression_summary,
)
from brain_alpha_ops.research.repository._core_mixin import ResearchRepositoryCoreMixin


class ResearchRepositoryWritesMixin(ResearchRepositoryCoreMixin):
    def save_candidate(self, run_id: str, candidate: Candidate):
        record = {"run_id": run_id, **candidate.to_dict()}
        extra_fields = record.get("extra_fields") if isinstance(record.get("extra_fields"), dict) else {}
        if isinstance(extra_fields.get("scientific_audit"), dict):
            record.setdefault("scientific_audit", extra_fields["scientific_audit"])
        self._append("candidates.jsonl", _with_expression_summary(record))

    def save_event(self, run_id: str, event: PipelineEvent):
        self._append("events.jsonl", {"run_id": run_id, **event.to_dict()})

    def save_lifecycle_record(self, run_id: str, record: dict[str, Any]):
        self._append("lifecycle.jsonl", _with_expression_summary(lifecycle_record(run_id, record)))

    def save_cloud_alpha(self, record: dict[str, Any]):
        self.merge_cloud_alphas([record])

    def save_check_record(self, record: dict[str, Any]):
        self._append("checks.jsonl", _with_expression_summary({"timestamp": utc_now(), **record}))

    def save_backtest_record(self, run_id: str, record: dict[str, Any]):
        self._append(
            "backtests.jsonl",
            _with_expression_summary(backtest_record(run_id, record)),
        )

    def save_assistant_guidance(self, guidance: dict[str, Any], *, source: str = "web") -> None:
        guidance = ensure_assistant_guidance_digest(guidance)
        self._append("assistant_guidance.jsonl", assistant_guidance_record(guidance, source=source))

    def save_strategy_lifecycle_record(self, run_id: str, record: dict[str, Any]) -> None:
        self._append("strategy_lifecycle.jsonl", strategy_lifecycle_record(run_id, record))

    def save_run_history(
        self,
        run_id: str,
        result: dict[str, Any],
        *,
        status: str = "completed",
        parameter_audit: dict[str, Any] | None = None,
        experiment_id: str = "",
        experiment_version: str = "",
    ) -> Path:
        """Persist the latest run snapshot for UI recovery after app restart."""
        history_dir = Path(self.storage_dir) / "run_history"
        history_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            **(result or {}),
            "run_id": run_id,
            "status": status,
            "timestamp": utc_now(),
        }
        if experiment_id:
            payload["experiment_id"] = experiment_id
        if experiment_version:
            payload["experiment_version"] = experiment_version
        if parameter_audit is not None:
            payload["parameter_audit"] = parameter_audit
        payload = _repository_safe(payload)
        with self._file_lock("run_history"):
            target = history_dir / f"{run_id}.json"
            latest = history_dir / "latest.json"
            tmp = history_dir / f".{run_id}.{os.getpid()}.{time.time_ns()}.tmp"
            data = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
            tmp.write_text(data, encoding="utf-8")
            tmp.replace(target)
            latest_tmp = history_dir / f".latest.{os.getpid()}.{time.time_ns()}.tmp"
            latest_tmp.write_text(data, encoding="utf-8")
            latest_tmp.replace(latest)
            return target

    def save_family_record(self, candidate: Candidate):
        self._append(
            "families.jsonl",
            {
                "timestamp": utc_now(),
                "family": candidate.family,
                "alpha_id": candidate.alpha_id,
                "parent_id": candidate.parent_id,
                "mutation_type": candidate.mutation_type,
                "status": candidate.lifecycle_status,
                "score": candidate.scorecard.get("total_score"),
                "correlation": (candidate.official_metrics or {}).get("correlation"),
            },
        )

    def maybe_archive(self, filename: str, max_size_mb: int = 50, max_age_days: int = 30):
        """C4: Archive large JSONL files when they exceed max_size_mb.

        Renames the current file to a timestamped archive and cleans up
        archives older than max_age_days.
        """
        from datetime import datetime, timedelta

        with self._file_lock(filename):
            path = self._safe_storage_path(filename)
            if not path.is_file():
                return
            size_mb = path.stat().st_size / (1024 * 1024)
            if size_mb <= max_size_mb:
                return

            suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_path = self._safe_archive_path(filename, suffix)
            try:
                path.rename(archive_path)
            except OSError:
                return

        # Clean up old archives
        cutoff = datetime.now() - timedelta(days=max_age_days)
        stem = Path(filename).stem
        for old in sorted(self._storage_root().glob(f"{stem}_*.jsonl")):
            try:
                mtime = datetime.fromtimestamp(old.stat().st_mtime)
                if mtime < cutoff:
                    old.unlink()
            except OSError:
                continue

    def save_ab_test(self, run_id: str, before: dict[str, Any], after: dict[str, Any], only_changed: str):
        self._append(
            "ab_tests.jsonl",
            {
                "timestamp": utc_now(),
                "run_id": run_id,
                "only_changed": only_changed,
                "before": before,
                "after": after,
            },
        )

    def latest_backtest_records(self, *, limit: int = 500) -> list[dict[str, Any]]:
        return read_jsonl_tail(self._safe_storage_path("backtests.jsonl"), limit=max(1, int(limit or 1)))
