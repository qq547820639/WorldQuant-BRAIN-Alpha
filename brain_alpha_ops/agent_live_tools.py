"""Live BRAIN API tool handlers for the agent toolbox."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from brain_alpha_ops.agent_research_tools import run_parallel_backtest_from_args
from brain_alpha_ops.agent_tool_errors import tool_error
from brain_alpha_ops.brain_api.user_alpha_sync import (
    USER_ALPHA_SYNC_RANGES,
    list_user_alphas_for_sync,
    normalize_user_alpha_sync_range,
)
from brain_alpha_ops.research.repository import ResearchRepository
from brain_alpha_ops.runner import api_from_run_config
from brain_alpha_ops.shared_bounds import (
    bounded_float,
    bounded_int,
    expression_batch_argument,
    required_text,
)

MAX_SYNC_RANGE = USER_ALPHA_SYNC_RANGES
MAX_BATCH_SIMULATIONS = 10
MAX_BATCH_SIMULATION_WORKERS = 3


class AgentLiveToolsMixin:
    """Handlers that can touch the live official API when explicitly allowed."""

    def _run_simulation(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._run_simulation_with_api(args, self._api())

    def _run_simulation_batch(self, args: dict[str, Any]) -> dict[str, Any]:
        blocked = self._live_api_blocked(args, tool="run_simulation_batch")
        if blocked:
            return blocked
        expressions = expression_batch_argument(args)
        max_batch_size = bounded_int(args.get("max_batch_size", MAX_BATCH_SIMULATIONS), 1, MAX_BATCH_SIMULATIONS)
        selected = expressions[:max_batch_size]
        skipped = [
            {
                "index": index,
                "expression": expression,
                "reason": "batch_size_limit",
            }
            for index, expression in enumerate(expressions[max_batch_size:], start=max_batch_size)
        ]
        if not selected:
            return {
                "ok": False,
                "schema_version": "agent_simulation_batch_result.v1",
                "error_code": "EMPTY_SIMULATION_BATCH",
                "error": "run_simulation_batch requires at least one expression",
                "requested_count": 0,
                "submitted_count": 0,
                "completed_count": 0,
                "failed_count": 0,
                "skipped_count": len(skipped),
                "results": [],
                "skipped": skipped,
            }

        requested_max_workers = bounded_int(args.get("max_workers", 1), 1, MAX_BATCH_SIMULATION_WORKERS)
        shared_args = dict(args)
        shared_args.pop("expressions", None)
        shared_args.pop("max_batch_size", None)
        shared_args.pop("max_workers", None)

        results: list[dict[str, Any] | None] = [None] * len(selected)
        if self.api is not None:
            effective_workers = 1
        else:
            effective_workers = min(requested_max_workers, len(selected))

        if effective_workers == 1 or len(selected) == 1:
            api = self._batch_api_for_item()
            for index, expression in enumerate(selected):
                try:
                    results[index] = self._run_single_batch_simulation(index, expression, shared_args, api=api)
                except Exception as exc:
                    results[index] = tool_error(
                        exc,
                        "SIMULATION_BATCH_ITEM_ERROR",
                        tool="run_simulation_batch",
                        index=index,
                    )
        else:
            with ThreadPoolExecutor(max_workers=effective_workers) as executor:
                future_map = {}
                for index, expression in enumerate(selected):
                    api = self._batch_api_for_item()
                    future = executor.submit(self._run_single_batch_simulation, index, expression, shared_args, api)
                    future_map[future] = index
                # Use as_completed(timeout=...) as a batch-level stall detector:
                # individual simulations can run indefinitely, but if NO future
                # completes within the window the whole batch is considered stuck.
                _batch_stall_seconds = 1800  # 30 min without any simulation completing
                try:
                    for future in as_completed(future_map, timeout=_batch_stall_seconds):
                        index = future_map[future]
                        try:
                            results[index] = future.result()  # no per-future timeout
                        except Exception as exc:
                            results[index] = tool_error(
                                exc,
                                "SIMULATION_BATCH_ITEM_ERROR",
                                tool="run_simulation_batch",
                                index=index,
                            )
                except TimeoutError:
                    # Batch stalled: no future completed within the window.
                    # Cancel remaining futures and report as stalled.
                    for future, index in list(future_map.items()):
                        if results[index] is None:
                            future.cancel()
                            results[index] = tool_error(
                                TimeoutError(f"simulation batch stalled: no progress for {_batch_stall_seconds}s"),
                                "SIMULATION_BATCH_STALLED",
                                tool="run_simulation_batch",
                                index=index,
                            )
        item_results = [result for result in results if isinstance(result, dict)]
        submitted_count = sum(1 for result in item_results if result.get("simulation_id"))
        completed_count = sum(1 for result in item_results if str(result.get("status", "")).upper() == "COMPLETED")
        failed_count = sum(1 for result in item_results if not bool(result.get("ok")))
        return {
            "ok": failed_count == 0 and submitted_count == len(selected),
            "schema_version": "agent_simulation_batch_result.v1",
            "requested_count": len(expressions),
            "selected_count": len(selected),
            "submitted_count": submitted_count,
            "completed_count": completed_count,
            "failed_count": failed_count,
            "skipped_count": len(skipped),
            "requested_max_workers": requested_max_workers,
            "max_workers": effective_workers,
            "rate_limit": {
                "max_batch_size": max_batch_size,
                "max_workers": effective_workers,
                "bounded": True,
            },
            "account_safety": {
                "live_api_confirmation_required": True,
                "duplicate_preflight_required": True,
                "validate_before_submit": True,
            },
            "results": item_results,
            "skipped": skipped,
        }

    def _run_single_batch_simulation(
        self,
        index: int,
        expression: str,
        shared_args: dict[str, Any],
        api: Any | None = None,
    ) -> dict[str, Any]:
        item_args = dict(shared_args)
        item_args["expression"] = expression
        result = self._run_simulation_with_api(item_args, api or self._api())
        result["index"] = index
        result.setdefault("expression", expression)
        return result

    def _run_simulation_with_api(self, args: dict[str, Any], api: Any) -> dict[str, Any]:
        return self._run_simulation_with_api_and_settings(args, api)

    def _run_simulation_with_api_and_settings(
        self,
        args: dict[str, Any],
        api: Any,
        *,
        settings_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        blocked = self._live_api_blocked(args, tool="run_simulation")
        if blocked:
            return blocked
        expression = required_text(args, "expression")
        blocked = self._duplicate_live_expression_block(expression, tool="run_simulation")
        if blocked:
            return blocked
        settings = self._simulation_settings(settings_overrides)
        api.authenticate()
        validation = api.validate_expression(
            expression,
            settings,
        )
        if str(validation.get("status", "")).upper() not in {"PASS", "PASSED", "OK"}:
            return {"ok": False, "error_code": "VALIDATION_FAILED", "validation": validation}
        simulation_id = api.submit_simulation(
            expression,
            settings,
        )
        max_polls = bounded_int(args.get("max_polls", 5), 1, 20)
        poll_interval = float(args.get("poll_interval_seconds", 2.0))
        poll_interval = bounded_float(poll_interval, 0.5, 30.0, default=2.0)
        status = ""
        for _ in range(max_polls):
            status = str(api.poll_simulation(simulation_id))
            if status.upper() in {"COMPLETED", "FAILED", "ERROR"}:
                break
            time.sleep(poll_interval)
        payload = {"ok": True, "simulation_id": simulation_id, "status": status, "settings": settings}
        if status.upper() == "COMPLETED":
            payload["result"] = api.fetch_result(simulation_id)
        elif status.upper() in {"FAILED", "ERROR"}:
            payload["ok"] = False
            payload["error_code"] = "SIMULATION_FAILED"
            payload["error"] = f"simulation finished with status {status.upper()}"
        return payload

    def _batch_api_for_item(self):
        if self.api is not None:
            return self.api
        return api_from_run_config(self.run_config)

    def _simulation_settings(self, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        settings = dict(self.run_config.ops.settings.to_platform_dict()["settings"])
        for key, value in dict(overrides or {}).items():
            if value is not None and str(value).strip():
                settings[str(key)] = value
        return settings

    def _check_alpha(self, args: dict[str, Any]) -> dict[str, Any]:
        blocked = self._live_api_blocked(args, tool="check_alpha")
        if blocked:
            return blocked
        alpha_id = required_text(args, "alpha_id")
        api = self._api()
        api.authenticate()
        return {"ok": True, "alpha_id": alpha_id, "check": api.check_alpha(alpha_id)}

    def _submit_alpha(self, args: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": False,
            "error_code": "WEB_ONLY_SUBMIT_REQUIRED",
            "error": "Official Alpha submission is available only through the Web staged readiness and confirmation flow.",
        }

    def _sync_cloud_alphas(self, args: dict[str, Any]) -> dict[str, Any]:
        blocked = self._live_api_blocked(args, tool="sync_cloud_alphas")
        if blocked:
            return blocked
        sync_range = normalize_user_alpha_sync_range(args.get("sync_range"))
        api = self._api()
        api.authenticate()
        rows = list_user_alphas_for_sync(api, sync_range)
        merge_stats = ResearchRepository(self.run_config.ops.storage_dir).merge_cloud_alphas(
            rows,
            sync_range=sync_range,
        )
        return {
            "ok": True,
            "range": sync_range,
            "count": len(rows),
            "merge": merge_stats,
            "alphas": rows[: bounded_int(args.get("limit", 20), 1, 200)],
        }

    def _run_parallel_backtest(self, args: dict[str, Any]) -> dict[str, Any]:
        blocked = self._live_api_blocked(args, tool="run_parallel_backtest")
        if blocked:
            return blocked

        def runner(job: dict[str, Any]) -> dict[str, Any]:
            item_args = dict(args)
            item_args["expression"] = str(job.get("expression") or "")
            for key in ("expressions", "markets", "max_workers", "max_batches", "per_account_limit"):
                item_args.pop(key, None)
            settings_overrides = job.get("settings_overrides") if isinstance(job.get("settings_overrides"), dict) else {}
            result = self._run_simulation_with_api_and_settings(
                item_args,
                self._batch_api_for_item(),
                settings_overrides=settings_overrides,
            )
            result.setdefault("market", job.get("market", ""))
            return result

        return run_parallel_backtest_from_args(
            args,
            runner=runner,
            default_market=self.run_config.ops.settings.region,
        )
