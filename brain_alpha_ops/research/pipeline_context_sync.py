"""Context and cloud-sync helpers for AlphaResearchPipeline."""

from __future__ import annotations

from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.brain_api.user_alpha_sync import list_user_alphas_for_sync, normalize_user_alpha_sync_range
from brain_alpha_ops.redaction import redact_error_message

from .pipeline_official_context import OfficialContextLoadService, configured_official_context_files_exist


class PipelineContextSyncMixin:
    def _sync_cloud_alphas(self):
        sync_range = normalize_user_alpha_sync_range(
            self.config.budget.cloud_sync_range if self.config.budget.require_cloud_sync else "all"
        )
        cached_rows = self.repository.latest_cloud_alphas()
        if self._local_data_dir_existed_at_start and cached_rows and not self.config.budget.require_cloud_sync:
            if cached_rows:
                self.cloud_alphas = cached_rows
                self._refresh_cloud_similarity_index()
                self.cloud_sync = {
                    "status": "loaded",
                    "status_code": "CACHE_LOADED",
                    "range": sync_range,
                    "count": len(cached_rows),
                    "scanned": len(cached_rows),
                    "total": len(cached_rows),
                    "added": 0,
                    "updated": 0,
                    "skipped": 0,
                    "failed": 0,
                    "cached": True,
                    "stale": False,
                    "warning": "",
                    "run_status": "skipped",
                }
                self._event("cloud_sync_skipped_cache_loaded", f"Loaded {len(cached_rows)} cached cloud alphas from local data; per-run sync is manual.")
            else:
                self.cloud_alphas = []
                self._refresh_cloud_similarity_index()
                self.cloud_sync = {
                    "status": "skipped",
                    "status_code": "CACHE_EMPTY_MANUAL_SYNC",
                    "range": sync_range,
                    "count": 0,
                    "scanned": 0,
                    "total": 0,
                    "added": 0,
                    "updated": 0,
                    "skipped": 0,
                    "failed": 0,
                    "cached": False,
                    "stale": False,
                    "warning": "Local data directory exists; cloud sync is manual for this run.",
                    "run_status": "skipped",
                }
                self._event("cloud_sync_skipped_manual", "Local data directory exists; skipped automatic cloud alpha sync.")
            self._progress(
                "cloud_sync",
                1,
                1,
                f"已加载本地云端缓存：{len(cached_rows)} 条；本轮未自动同步。",
                data={"cloud_sync": self.cloud_sync, "cloud_alphas": self.cloud_alphas},
            )
            return

        if not self.config.budget.require_cloud_sync:
            self._event("cloud_sync_initial_required", "No local cloud alpha cache found; running first-login sync.")
        self._progress(
            "cloud_sync",
            0,
            1,
            f"同步云端 Alpha：{sync_range}",
            data={"cloud_sync": {"status": "running", "status_code": "RUNNING", "range": sync_range, "scanned": 0, "added": 0, "skipped": 0, "failed": 0}},
        )
        sync_meta = {"cached": False, "stale": False, "warning": "", "cancelled": False}
        def on_cloud_progress(progress: dict) -> bool:
            if self._should_stop():
                sync_meta["cancelled"] = True
                sync_meta["warning"] = "Cloud alpha sync stopped before merge."
                return False
            sync_meta["cached"] = sync_meta["cached"] or bool(progress.get("cached"))
            sync_meta["stale"] = sync_meta["stale"] or bool(progress.get("stale"))
            sync_meta["warning"] = str(progress.get("warning") or sync_meta["warning"] or "")
            scanned = int(progress.get("scanned", 0))
            reference_total = int(progress.get("api_reported_total") or progress.get("filter_window_count") or progress.get("total") or 0)
            page = int(progress.get("pages_fetched") or progress.get("page_number") or 0)
            expected_pages = int(progress.get("expected_pages") or 0)
            page_text = f"；当前第 {page} 页" if page else ""
            reference_text = (
                f"接口分页参考数 {reference_total} 条，不是云端 Alpha 总量"
                if reference_total > 0
                else "接口分页参考数仍在确认"
            )
            self._progress(
                "cloud_sync",
                scanned,
                0,
                f"云端 Alpha 分页拉取中：已拉取 {scanned} 条；{reference_text}{page_text}。",
                data={
                    "progress_indeterminate": True,
                    "cloud_sync": {
                        "status": "running",
                        "status_code": "RUNNING",
                        "range": sync_range,
                        "scanned": scanned,
                        "api_reported_total": reference_total,
                        "filter_window_count": reference_total,
                        "page_size": int(progress.get("page_size", 0) or 0),
                        "page_limit": int(progress.get("page_limit", 0) or 0),
                        "pages_fetched": page,
                        "expected_pages": expected_pages,
                        "next_offset": int(progress.get("next_offset", 0) or 0),
                        "offset": int(progress.get("offset", 0) or 0),
                        "added": 0,
                        "skipped": 0,
                        "failed": 0,
                        "cached": bool(progress.get("cached")),
                        "stale": bool(progress.get("stale")),
                        "warning": str(progress.get("warning") or ""),
                    }
                },
            )
            if self._should_stop():
                sync_meta["cancelled"] = True
                sync_meta["warning"] = "Cloud alpha sync stopped before merge."
                return False
            return True

        try:
            rows = list_user_alphas_for_sync(self.api, sync_range, progress_callback=on_cloud_progress)
        except BrainAPIError as exc:
            self.cloud_alphas = []
            self._refresh_cloud_similarity_index()
            self.cloud_sync = {
                "status": "failed",
                "status_code": f"HTTP_{exc.status_code}" if exc.status_code else "FAILED",
                "range": sync_range,
                "count": 0,
                "scanned": 0,
                "added": 0,
                "skipped": 0,
                "failed": 1,
                "warning": redact_error_message(exc),
            }
            self._event("cloud_sync_failed", self.cloud_sync["warning"], level="WARN")
        else:
            if sync_meta["cancelled"] or self._should_stop():
                self.cloud_alphas = []
                self._refresh_cloud_similarity_index()
                self.cloud_sync = {
                    "status": "stopped",
                    "status_code": "STOPPED",
                    "range": sync_range,
                    "count": 0,
                    "scanned": 0,
                    "total": 0,
                    "added": 0,
                    "updated": 0,
                    "skipped": 0,
                    "failed": 0,
                    "cached": bool(sync_meta["cached"]),
                    "stale": bool(sync_meta["stale"]),
                    "warning": str(sync_meta["warning"] or "Cloud alpha sync stopped before merge."),
                    "run_status": "stopped",
                }
                self._event("cloud_sync_stopped", self.cloud_sync["warning"], level="WARN")
                self._progress(
                    "cloud_sync",
                    1,
                    1,
                    "云端 Alpha 同步已停止，未合并部分结果。",
                    data={"cloud_sync": self.cloud_sync, "cloud_alphas": self.cloud_alphas},
                )
                return
            self.cloud_alphas = rows
            self._refresh_cloud_similarity_index()
            merge_stats = self.repository.merge_cloud_alphas(rows, sync_range=sync_range)
            self.cloud_sync = {
                "status": "synced",
                "status_code": "SYNCED",
                "range": sync_range,
                "count": len(rows),
                "scanned": len(rows),
                "total": len(rows),
                "added": merge_stats["added"],
                "updated": merge_stats["updated"],
                "skipped": merge_stats["skipped"],
                "failed": 0,
                "cached": bool(sync_meta["cached"]),
                "stale": bool(sync_meta["stale"]),
                "warning": str(sync_meta["warning"]),
            }
            self._event("cloud_alphas_synced", f"Synced {len(rows)} cloud alphas for range {sync_range}.")
        self._progress(
            "cloud_sync",
            1,
            1,
            f"云端 Alpha 同步完成：{self.cloud_sync['count']} 条。",
            data={"cloud_sync": self.cloud_sync, "cloud_alphas": self.cloud_alphas},
        )

    def _load_official_context(self) -> tuple[list[dict], list[dict]]:
        result = OfficialContextLoadService(
            config=self.config,
            api=self.api,
            generator=self.generator,
            local_data_dir_existed_at_start=self._local_data_dir_existed_at_start,
            progress=self._progress,
            event=self._event,
            halt_official_calls=self._halt_official_calls,
        ).load()
        self.generator = result.generator
        self._loader = result.loader
        self._mapper = result.mapper
        self._theme_engine = result.theme_engine
        self._selector = result.selector
        self._hypothesis_library = result.hypothesis_library
        self.optimizer = result.optimizer
        self._active_dataset_id = result.active_dataset_id
        self.context_summary = result.context_summary
        self._refresh_context_validation_cache(result.fields, result.operators)
        self._apply_knowledge_constraints_to_generator()
        return result.fields, result.operators

    def _apply_knowledge_constraints_to_generator(self) -> None:
        if not hasattr(self.generator, "set_knowledge_constraints"):
            return
        try:
            constraints = self._knowledge_base.get_generation_constraints()
            supported_fields = {
                str(field).lower()
                for field in getattr(self._local_backtest_engine, "supported_fields", set())
                if str(field)
            }
            active_fields = {
                str(field).lower()
                for field in getattr(self.generator, "_fields", set())
                if str(field)
            }
            local_preferred_fields = sorted(supported_fields & active_fields) or sorted(supported_fields)
            active_operators = {
                str(operator).lower()
                for operator in getattr(self.generator, "_operators", set())
                if str(operator)
            }
            supported_operators = {
                str(operator).lower()
                for operator in getattr(self._local_backtest_engine, "supported_operators", set())
                if str(operator)
            }
            local_preferred_operators = sorted(supported_operators & active_operators) or sorted(supported_operators)
            if local_preferred_fields:
                constraints["preferred_fields"] = local_preferred_fields
                constraints["strict_preferred_fields"] = True
            if local_preferred_operators:
                constraints["preferred_operators"] = local_preferred_operators
                constraints["strict_preferred_operators"] = True
            self.generator.set_knowledge_constraints(constraints)
            self.context_summary["knowledge_constraints"] = {
                "preferred_fields_count": len(constraints.get("preferred_fields") or []),
                "preferred_operators_count": len(constraints.get("preferred_operators") or []),
                "forbidden_patterns_count": len(constraints.get("forbidden_patterns") or []),
                "strict_preferred_fields": bool(constraints.get("strict_preferred_fields")),
                "strict_preferred_operators": bool(constraints.get("strict_preferred_operators")),
                "applied": True,
            }
            self._event(
                "knowledge_constraints_applied",
                "Applied structured knowledge constraints to candidate generator.",
                data=self.context_summary["knowledge_constraints"],
            )
        except Exception as exc:
            self.context_summary["knowledge_constraints"] = {
                "applied": False,
                "error": redact_error_message(exc, max_length=180),
            }
            self._event(
                "knowledge_constraints_failed",
                "Failed to apply structured knowledge constraints to candidate generator.",
                level="WARN",
                data=self.context_summary["knowledge_constraints"],
            )

    def _configured_official_context_files_exist(self) -> bool:
        return configured_official_context_files_exist(self.config.storage_dir)
