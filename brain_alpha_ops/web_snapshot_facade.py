"""Public snapshot function facade for the local web module."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class WebSnapshotFacade:
    runtime_factory: Callable[[], Any]
    latest_result_snapshot_func: Callable[[], dict] | None = None
    latest_run_history_path_func: Callable[[], Path | None] | None = None
    assistant_context_snapshot_func: Callable[..., dict] | None = None
    assistant_guidance_snapshot_func: Callable[..., dict] | None = None

    def _runtime(self) -> Any:
        return self.runtime_factory()

    def durable_job_rows(self, *, limit: int) -> list[dict]:
        return self._runtime().durable_job_rows(limit=limit)

    def research_memory_snapshot(self, *, limit: int = 5000, top_n: int = 10) -> dict:
        return self._runtime().research_memory_snapshot(limit=limit, top_n=top_n)

    def research_knowledge_snapshot(self, *, limit: int = 100, min_confidence: float = 0.0) -> dict:
        return self._runtime().research_knowledge_snapshot(limit=limit, min_confidence=min_confidence)

    def research_observability_snapshot(self, *, limit: int = 5000, top_n: int = 10, include_cloud: bool = True) -> dict:
        return self._runtime().research_observability_snapshot(limit=limit, top_n=top_n, include_cloud=include_cloud)

    def prompt_run_ledger_snapshot(self, *, limit: int = 100) -> dict:
        return self._runtime().prompt_run_ledger_snapshot(limit=limit)

    def assistant_guidance_snapshot(self, *, limit: int = 100, min_confidence: float | None = None) -> dict:
        return self._runtime().assistant_guidance_snapshot(limit=limit, min_confidence=min_confidence)

    def assistant_guidance_history(
        self,
        rows: list[dict],
        *,
        min_confidence: float,
        scoring_policy: dict | None = None,
        outcomes_by_guidance: dict[str, dict] | None = None,
    ) -> list[dict]:
        return self._runtime().assistant_guidance_history(
            rows,
            min_confidence=min_confidence,
            scoring_policy=scoring_policy,
            outcomes_by_guidance=outcomes_by_guidance,
        )

    def assistant_context_snapshot(
        self,
        *,
        limit: int = 5000,
        top_n: int = 10,
        include_prompt: bool = True,
        include_sensitive: bool = False,
    ) -> dict:
        return self._runtime().assistant_context_snapshot(
            limit=limit,
            top_n=top_n,
            include_prompt=include_prompt,
            include_sensitive=include_sensitive,
            latest_result_snapshot=self._latest_result_snapshot,
        )

    def assistant_request_snapshot(
        self,
        *,
        limit: int = 5000,
        top_n: int = 10,
        include_prompt: bool = True,
        include_offline_draft: bool = True,
        include_sensitive: bool = False,
    ) -> dict:
        return self._runtime().assistant_request_snapshot(
            limit=limit,
            top_n=top_n,
            include_prompt=include_prompt,
            include_offline_draft=include_offline_draft,
            include_sensitive=include_sensitive,
            assistant_context_snapshot=self._assistant_context_snapshot,
        )

    def assistant_response_parse_payload(self, payload: dict) -> dict:
        return self._runtime().assistant_response_parse_payload(payload)

    def assistant_response_guidance_payload(self, payload: dict) -> dict:
        return self._runtime().assistant_response_guidance_payload(payload)

    def anti_overfit_snapshot(self, candidate_id: str = "") -> dict:
        return self._runtime().anti_overfit_snapshot(candidate_id, self._latest_result_snapshot)

    def rolling_validation_snapshot(self, candidate_id: str = "", windows: int = 4) -> dict:
        return self._runtime().rolling_validation_snapshot(candidate_id, windows, self._latest_result_snapshot)

    def assistant_cross_review_payload(self, payload: dict) -> dict:
        return self._runtime().assistant_cross_review_payload(payload)

    def save_assistant_guidance_payload(self, payload: dict) -> dict:
        return self._runtime().save_assistant_guidance_payload(payload, self._assistant_guidance_snapshot)

    def latest_result_snapshot(self) -> dict:
        return self._runtime().latest_result_snapshot(self._latest_run_history_path)

    def latest_run_history_path(self) -> Path | None:
        return self._runtime().latest_run_history_path()

    def user_profile_snapshot(self) -> dict:
        return self._runtime().user_profile_snapshot()

    def _latest_result_snapshot(self) -> dict:
        if self.latest_result_snapshot_func is not None:
            return self.latest_result_snapshot_func()
        return self.latest_result_snapshot()

    def _latest_run_history_path(self) -> Path | None:
        if self.latest_run_history_path_func is not None:
            return self.latest_run_history_path_func()
        return self.latest_run_history_path()

    def _assistant_context_snapshot(self, **kwargs) -> dict:
        if self.assistant_context_snapshot_func is not None:
            return self.assistant_context_snapshot_func(**kwargs)
        return self.assistant_context_snapshot(**kwargs)

    def _assistant_guidance_snapshot(self, **kwargs) -> dict:
        if self.assistant_guidance_snapshot_func is not None:
            return self.assistant_guidance_snapshot_func(**kwargs)
        return self.assistant_guidance_snapshot(**kwargs)
