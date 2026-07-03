"""Public snapshot facade, runtime, and review API for the local web module.

Consolidated from the former ``web_snapshot_facade.py`` (``WebSnapshotFacade``
dataclass), ``web_snapshot_runtime.py`` (``WebSnapshotRuntime`` dataclass), and
``web_review.py`` (anti-overfit / rolling-validation / cross-review snapshot
helpers). The review helpers are co-located here because ``WebSnapshotRuntime``
delegates to them; the former ``from brain_alpha_ops.web_review import ...``
is replaced by local definitions and ``*_service`` aliases.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from brain_alpha_ops.scoring.anti_overfit import AntiOverfitService
from brain_alpha_ops.research.llm_review import cross_review_assistant_response
from brain_alpha_ops.research.observability import build_research_observability_snapshot
from brain_alpha_ops.research.repository import ResearchRepository
from brain_alpha_ops.research.rolling_validation import RollingValidationService
from brain_alpha_ops.web_candidates.payloads import DEFAULT_MAIN_POOL_SIZE
from brain_alpha_ops.web_snapshots import (  # noqa: F401
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


# ═══════════════════════ Review API (from web_review.py) ════════════════
LatestSnapshot = Callable[[], dict[str, Any]]
BoundedFloat = Callable[[Any, float, float], float]

_CANDIDATE_LIST_KEYS = {
    "candidates",
    "passed_candidates",
    "pending_backtest_candidates",
    "accepted_candidates",
    "archive_samples",
    "retained_candidates",
    "ranked_candidates",
    "pool",
}


def anti_overfit_snapshot(
    *,
    candidate_id: str = "",
    latest_result_snapshot: LatestSnapshot,
) -> dict[str, Any]:
    """Find a recent candidate and run deterministic anti-overfit checks."""
    snapshot = latest_result_snapshot()
    candidates = _collect_candidates(snapshot)
    selected = _select_candidate(candidates, candidate_id)
    if selected is None:
        return {
            "ok": False,
            "error_code": "CANDIDATE_NOT_FOUND" if candidate_id else "CANDIDATE_ID_REQUIRED",
            "error_category": "validation",
            "retryable": False,
            "candidate_id": candidate_id,
            "available_candidate_ids": _available_candidate_ids(candidates)[:50],
        }
    report = AntiOverfitService().evaluate(selected)
    return {
        "ok": True,
        "schema_version": "anti_overfit_snapshot.v1",
        "candidate_id": _candidate_identifier(selected),
        "anti_overfit_report": report,
    }


def rolling_validation_snapshot(
    *,
    candidate_id: str = "",
    windows: int = 4,
    latest_result_snapshot: LatestSnapshot,
) -> dict[str, Any]:
    """Find a recent candidate and run rolling validation checks."""
    snapshot = latest_result_snapshot()
    candidates = _collect_candidates(snapshot)
    selected = _select_candidate(candidates, candidate_id)
    if selected is None:
        return {
            "ok": False,
            "error_code": "CANDIDATE_NOT_FOUND" if candidate_id else "CANDIDATE_ID_REQUIRED",
            "error_category": "validation",
            "retryable": False,
            "candidate_id": candidate_id,
            "available_candidate_ids": _available_candidate_ids(candidates)[:50],
        }
    report = RollingValidationService().evaluate(selected, windows=windows)
    return {
        "ok": True,
        "schema_version": "rolling_validation_snapshot.v1",
        "candidate_id": _candidate_identifier(selected),
        "rolling_validation_report": report,
    }


def assistant_cross_review_payload(
    payload: dict[str, Any],
    *,
    bounded_query_float: BoundedFloat,
) -> dict[str, Any]:
    """Normalize a POST payload and run provider-neutral assistant cross-review."""
    request_pack = payload.get("request_pack")
    if request_pack is None:
        request_pack = payload.get("request")
    if not isinstance(request_pack, dict):
        raise ValueError("request_pack must be an object")
    primary = payload.get("primary_response")
    if primary is None:
        primary = payload.get("primary")
    if primary is None:
        raise ValueError("primary_response is required")
    reviewer = payload.get("reviewer_response")
    if reviewer is None:
        reviewer = payload.get("reviewer")
    min_confidence = bounded_query_float(payload.get("min_confidence", 0.6), 0.0, 1.0)
    return cross_review_assistant_response(
        request_pack,
        primary,
        reviewer_response=reviewer,
        min_confidence=min_confidence,
    )


def _collect_candidates(value: Any, *, _depth: int = 0) -> list[dict[str, Any]]:
    if _depth > 8:
        return []
    rows: list[dict[str, Any]] = []
    if isinstance(value, list):
        for item in value:
            rows.extend(_collect_candidates(item, _depth=_depth + 1))
        return rows
    if not isinstance(value, dict):
        return rows
    if _looks_like_candidate(value):
        rows.append(value)
    for key, child in value.items():
        if key in _CANDIDATE_LIST_KEYS or isinstance(child, dict):
            rows.extend(_collect_candidates(child, _depth=_depth + 1))
        elif isinstance(child, list) and key in _CANDIDATE_LIST_KEYS:
            rows.extend(_collect_candidates(child, _depth=_depth + 1))
    return _dedupe_candidates(rows)


def _looks_like_candidate(value: dict[str, Any]) -> bool:
    return bool(
        value.get("expression")
        and (
            value.get("alpha_id")
            or value.get("id")
            or value.get("official_alpha_id")
            or value.get("simulation_id")
        )
    )


def _select_candidate(candidates: list[dict[str, Any]], candidate_id: str) -> dict[str, Any] | None:
    wanted = str(candidate_id or "").strip()
    if wanted:
        for candidate in candidates:
            if wanted in _candidate_identifiers(candidate):
                return candidate
        return None
    return candidates[0] if len(candidates) == 1 else None


def _candidate_identifiers(candidate: dict[str, Any]) -> set[str]:
    raw_metrics = candidate.get("official_metrics")
    metrics = raw_metrics if isinstance(raw_metrics, dict) else {}
    raw_submission = candidate.get("submission")
    submission = raw_submission if isinstance(raw_submission, dict) else {}
    return {
        str(value)
        for value in (
            candidate.get("alpha_id"),
            candidate.get("id"),
            candidate.get("official_alpha_id"),
            candidate.get("simulation_id"),
            metrics.get("official_alpha_id"),
            metrics.get("alpha_id"),
            submission.get("official_alpha_id"),
            submission.get("simulation_id"),
        )
        if str(value or "").strip()
    }


def _candidate_identifier(candidate: dict[str, Any]) -> str:
    ids = _candidate_identifiers(candidate)
    for key in ("alpha_id", "id", "official_alpha_id", "simulation_id"):
        value = str(candidate.get(key) or "").strip()
        if value:
            return value
    return sorted(ids)[0] if ids else ""


def _available_candidate_ids(candidates: list[dict[str, Any]]) -> list[str]:
    return [_candidate_identifier(candidate) for candidate in candidates if _candidate_identifier(candidate)]


def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        key = (_candidate_identifier(candidate), str(candidate.get("expression") or ""))
        if key in seen:
            continue
        seen.add(key)
        rows.append(candidate)
    return rows


# Local aliases for the service functions used by WebSnapshotRuntime below.
# Previously these were imported from brain_alpha_ops.web_review; now they are
# defined locally above.
anti_overfit_snapshot_service = anti_overfit_snapshot
assistant_cross_review_payload_service = assistant_cross_review_payload
rolling_validation_snapshot_service = rolling_validation_snapshot


# ═══════════════════════ WebSnapshotFacade ═════════════════════════════
@dataclass(frozen=True)
class WebSnapshotFacade:
    runtime_factory: Callable[[], Any]
    latest_result_snapshot_func: "Callable[[], dict] | None" = None
    latest_run_history_path_func: "Callable[[], Path | None] | None" = None
    assistant_context_snapshot_func: "Callable[..., dict] | None" = None
    assistant_guidance_snapshot_func: "Callable[..., dict] | None" = None

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


# ═══════════════════════ WebSnapshotRuntime ════════════════════════════
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
            read_storage_jsonl=self.read_storage_jsonl,
            target_pool_size=self._candidate_target_pool_size(),
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

    def _candidate_target_pool_size(self) -> int:
        try:
            config = self.load_config()
            configured_size = getattr(
                config.ops.budget,
                "retained_alpha_pool_size",
                DEFAULT_MAIN_POOL_SIZE,
            )
            return max(1, int(configured_size or DEFAULT_MAIN_POOL_SIZE))
        except Exception:
            return DEFAULT_MAIN_POOL_SIZE


__all__ = [
    "WebSnapshotFacade",
    "WebSnapshotRuntime",
    "anti_overfit_snapshot",
    "assistant_cross_review_payload",
    "rolling_validation_snapshot",
]
