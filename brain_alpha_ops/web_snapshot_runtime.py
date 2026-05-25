"""Runtime dependency facade for Web snapshot services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from brain_alpha_ops.research.observability import build_research_observability_snapshot
from brain_alpha_ops.research.repository import ResearchRepository
from brain_alpha_ops.web_assistant_snapshots import (
    assistant_context_snapshot as assistant_context_snapshot_service,
    assistant_guidance_history as assistant_guidance_history_service,
    assistant_guidance_snapshot as assistant_guidance_snapshot_service,
    assistant_request_snapshot as assistant_request_snapshot_service,
    assistant_response_guidance_payload as assistant_response_guidance_payload_service,
    assistant_response_parse_payload as assistant_response_parse_payload_service,
    durable_job_rows as durable_job_rows_service,
    latest_result_snapshot as latest_result_snapshot_service,
    latest_run_history_path as latest_run_history_path_service,
    prompt_run_ledger_snapshot as prompt_run_ledger_snapshot_service,
    research_knowledge_snapshot as research_knowledge_snapshot_service,
    research_memory_snapshot as research_memory_snapshot_service,
    research_observability_snapshot as research_observability_snapshot_service,
    save_assistant_guidance_payload as save_assistant_guidance_payload_service,
    user_profile_snapshot as user_profile_snapshot_service,
)
from brain_alpha_ops.web_review_api import (
    anti_overfit_snapshot as anti_overfit_snapshot_service,
    assistant_cross_review_payload as assistant_cross_review_payload_service,
    rolling_validation_snapshot as rolling_validation_snapshot_service,
)


@dataclass
class WebSnapshotRuntime:
    load_config: Callable[[], Any]
    web_error: Callable[[Exception, str], dict]
    bounded_query_float: Callable[..., float]
    payload_truthy: Callable[[Any], bool]
    read_storage_jsonl: Callable[..., list[dict]]
    run_config_from_payload: Callable[[dict], Any]
    cloud_alpha_snapshot: Callable[..., dict]
    storage_jsonl_path: Callable[[str], Path]
    safe_error_message: Callable[[Exception], str]
    job_store: Any
    sync_job_store: Any
    check_job_store: Any
    enrich_progress: Callable[[dict], dict]
    repository_factory: Callable[..., Any] = ResearchRepository
    observability_builder: Callable[..., dict] = build_research_observability_snapshot

    def durable_job_rows(self, *, limit: int) -> list[dict]:
        return durable_job_rows_service(
            stores=[
                ("production_job", self.job_store),
                ("sync_job", self.sync_job_store),
                ("check_job", self.check_job_store),
            ],
            limit=limit,
        )

    def research_memory_snapshot(self, *, limit: int = 5000, top_n: int = 10) -> dict:
        return research_memory_snapshot_service(
            limit=limit,
            top_n=top_n,
            load_config=self.load_config,
            web_error=self.web_error,
        )

    def research_knowledge_snapshot(self, *, limit: int = 100, min_confidence: float = 0.0) -> dict:
        return research_knowledge_snapshot_service(
            limit=limit,
            min_confidence=min_confidence,
            load_config=self.load_config,
            web_error=self.web_error,
        )

    def research_observability_snapshot(self, *, limit: int = 5000, top_n: int = 10, include_cloud: bool = True) -> dict:
        return research_observability_snapshot_service(
            limit=limit,
            top_n=top_n,
            include_cloud=include_cloud,
            load_config=self.load_config,
            durable_job_rows=self.durable_job_rows,
            observability_builder=self.observability_builder,
            web_error=self.web_error,
        )

    def prompt_run_ledger_snapshot(self, *, limit: int = 100) -> dict:
        return prompt_run_ledger_snapshot_service(
            limit=limit,
            load_config=self.load_config,
            web_error=self.web_error,
        )

    def assistant_guidance_snapshot(self, *, limit: int = 100, min_confidence: float | None = None) -> dict:
        return assistant_guidance_snapshot_service(
            limit=limit,
            min_confidence=min_confidence,
            load_config=self.load_config,
            bounded_query_float=self.bounded_query_float,
            payload_truthy=self.payload_truthy,
            read_storage_jsonl=self.read_storage_jsonl,
            web_error=self.web_error,
        )

    def assistant_guidance_history(
        self,
        rows: list[dict],
        *,
        min_confidence: float,
        scoring_policy: dict | None = None,
        outcomes_by_guidance: dict[str, dict] | None = None,
    ) -> list[dict]:
        return assistant_guidance_history_service(
            rows,
            min_confidence=min_confidence,
            scoring_policy=scoring_policy,
            outcomes_by_guidance=outcomes_by_guidance,
            bounded_query_float=self.bounded_query_float,
            payload_truthy=self.payload_truthy,
        )

    def assistant_context_snapshot(
        self,
        *,
        limit: int = 5000,
        top_n: int = 10,
        include_prompt: bool = True,
        include_sensitive: bool = False,
        latest_result_snapshot: Callable[[], dict],
    ) -> dict:
        return assistant_context_snapshot_service(
            limit=limit,
            top_n=top_n,
            include_prompt=include_prompt,
            include_sensitive=include_sensitive,
            load_config=self.load_config,
            latest_result_snapshot=latest_result_snapshot,
            cloud_alpha_snapshot=self.cloud_alpha_snapshot,
            web_error=self.web_error,
        )

    def assistant_request_snapshot(
        self,
        *,
        limit: int = 5000,
        top_n: int = 10,
        include_prompt: bool = True,
        include_offline_draft: bool = True,
        include_sensitive: bool = False,
        assistant_context_snapshot: Callable[..., dict],
    ) -> dict:
        return assistant_request_snapshot_service(
            limit=limit,
            top_n=top_n,
            include_prompt=include_prompt,
            include_offline_draft=include_offline_draft,
            include_sensitive=include_sensitive,
            assistant_context_snapshot=assistant_context_snapshot,
            web_error=self.web_error,
        )

    def assistant_response_parse_payload(self, payload: dict) -> dict:
        return assistant_response_parse_payload_service(payload)

    def assistant_response_guidance_payload(self, payload: dict) -> dict:
        return assistant_response_guidance_payload_service(payload, bounded_query_float=self.bounded_query_float)

    def anti_overfit_snapshot(self, candidate_id: str, latest_result_snapshot: Callable[[], dict]) -> dict:
        return anti_overfit_snapshot_service(
            candidate_id=candidate_id,
            latest_result_snapshot=latest_result_snapshot,
        )

    def rolling_validation_snapshot(self, candidate_id: str, windows: int, latest_result_snapshot: Callable[[], dict]) -> dict:
        return rolling_validation_snapshot_service(
            candidate_id=candidate_id,
            windows=windows,
            latest_result_snapshot=latest_result_snapshot,
        )

    def assistant_cross_review_payload(self, payload: dict) -> dict:
        return assistant_cross_review_payload_service(
            payload,
            bounded_query_float=self.bounded_query_float,
        )

    def save_assistant_guidance_payload(self, payload: dict, assistant_guidance_snapshot: Callable[..., dict]) -> dict:
        return save_assistant_guidance_payload_service(
            payload,
            run_config_from_payload=self.run_config_from_payload,
            bounded_query_float=self.bounded_query_float,
            payload_truthy=self.payload_truthy,
            assistant_guidance_snapshot=assistant_guidance_snapshot,
            repository_factory=self.repository_factory,
        )

    def latest_result_snapshot(self, latest_run_history_path: Callable[[], Path | None]) -> dict:
        return latest_result_snapshot_service(
            job_store=self.job_store,
            latest_run_history_path=latest_run_history_path,
            enrich_progress=self.enrich_progress,
            web_error=self.web_error,
        )

    def latest_run_history_path(self) -> Path | None:
        return latest_run_history_path_service(load_config=self.load_config)

    def user_profile_snapshot(self) -> dict:
        return user_profile_snapshot_service(
            job_store=self.job_store,
            storage_jsonl_path=self.storage_jsonl_path,
            safe_error_message=self.safe_error_message,
        )
