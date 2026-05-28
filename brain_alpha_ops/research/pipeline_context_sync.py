"""Context and cloud-sync helpers for AlphaResearchPipeline."""

from __future__ import annotations

from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.redaction import redact_error_message

from .pipeline_official_context import OfficialContextLoadService, configured_official_context_files_exist


class PipelineContextSyncMixin:
    def _sync_cloud_alphas(self):
        sync_range = self.config.budget.cloud_sync_range
        cached_rows = self.repository.latest_cloud_alphas()
        if self._local_data_dir_existed_at_start and cached_rows:
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
        sync_meta = {"cached": False, "stale": False, "warning": ""}

        def on_cloud_progress(progress: dict):
            sync_meta["cached"] = sync_meta["cached"] or bool(progress.get("cached"))
            sync_meta["stale"] = sync_meta["stale"] or bool(progress.get("stale"))
            sync_meta["warning"] = str(progress.get("warning") or sync_meta["warning"] or "")
            self._progress(
                "cloud_sync",
                int(progress.get("scanned", 0)) if int(progress.get("total", 0) or 0) else 0,
                max(1, int(progress.get("total", 0) or 1)),
                f"云端 Alpha 扫描中：{progress.get('scanned', 0)} / {progress.get('total') or '总量确认中'}。",
                data={
                    "cloud_sync": {
                        "status": "running",
                        "status_code": "RUNNING",
                        "range": sync_range,
                        "scanned": int(progress.get("scanned", 0)),
                        "total": int(progress.get("total", 0) or 0),
                        "page_size": int(progress.get("page_size", 0) or 0),
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

        try:
            rows = self.api.list_user_alphas(sync_range, progress_callback=on_cloud_progress)
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
            self.generator.set_knowledge_constraints(constraints)
            self.context_summary["knowledge_constraints"] = {
                "preferred_fields_count": len(constraints.get("preferred_fields") or []),
                "preferred_operators_count": len(constraints.get("preferred_operators") or []),
                "forbidden_patterns_count": len(constraints.get("forbidden_patterns") or []),
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
