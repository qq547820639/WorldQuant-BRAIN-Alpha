"""Budgeted full-market backtest planning and execution helpers."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable


@dataclass(frozen=True)
class ParallelBacktestBudget:
    market_count: int
    alpha_count: int
    max_workers: int
    max_batches: int
    per_account_limit: int

    @property
    def requested_jobs(self) -> int:
        return max(0, self.market_count) * max(0, self.alpha_count)

    @property
    def capacity(self) -> int:
        return max(0, self.max_batches) * max(1, self.per_account_limit)

    @property
    def selected_jobs(self) -> int:
        return min(self.requested_jobs, self.capacity)


class ParallelBacktestPlanner:
    """Create bounded execution plans for broad market backtest runs."""

    def plan(
        self,
        expressions: list[str],
        *,
        markets: list[str] | None = None,
        max_workers: int = 4,
        max_batches: int = 10,
        per_account_limit: int = 20,
    ) -> dict[str, Any]:
        clean_expressions = _unique_text(expressions)
        duplicate_expressions = _duplicate_text(expressions)
        clean_markets = _unique_text(markets or ["USA"])
        if not clean_expressions or not clean_markets:
            return {
                "ok": False,
                "schema_version": "parallel_backtest_plan.v1",
                "error_code": "EMPTY_PARALLEL_BACKTEST_PLAN",
                "requested_jobs": 0,
                "selected_jobs": 0,
                "skipped_jobs": 0,
                "markets": clean_markets,
                "alpha_count": len(clean_expressions),
                "duplicate_expressions": duplicate_expressions,
                "rate_limit": {
                    "max_workers": max(1, int(max_workers or 1)),
                    "max_batches": max(1, int(max_batches or 1)),
                    "per_account_limit": max(1, int(per_account_limit or 1)),
                    "bounded": True,
                },
                "account_safety": {
                    "requires_explicit_live_confirmation": True,
                    "deduplicated_expressions": True,
                    "capacity_limited": False,
                    "validation_before_submit": True,
                    "empty_plan_blocked": True,
                },
                "batches": [],
                "jobs": [],
            }
        budget = ParallelBacktestBudget(
            market_count=len(clean_markets),
            alpha_count=len(clean_expressions),
            max_workers=max(1, int(max_workers or 1)),
            max_batches=max(1, int(max_batches or 1)),
            per_account_limit=max(1, int(per_account_limit or 1)),
        )
        jobs: list[dict[str, Any]] = []
        for market in clean_markets:
            for expression in clean_expressions:
                if len(jobs) >= budget.selected_jobs:
                    break
                jobs.append(
                    {
                        "job_index": len(jobs),
                        "market": market,
                        "expression": expression,
                        "status": "planned",
                        "settings_overrides": {"region": market},
                    }
                )
            if len(jobs) >= budget.selected_jobs:
                break
        skipped_count = max(0, budget.requested_jobs - len(jobs))
        return {
            "ok": bool(jobs),
            "schema_version": "parallel_backtest_plan.v1",
            "error_code": "" if jobs else "EMPTY_PARALLEL_BACKTEST_PLAN",
            "requested_jobs": budget.requested_jobs,
            "selected_jobs": len(jobs),
            "skipped_jobs": skipped_count,
            "markets": clean_markets,
            "alpha_count": len(clean_expressions),
            "duplicate_expressions": duplicate_expressions,
            "rate_limit": {
                "max_workers": min(budget.max_workers, max(1, len(jobs) or 1)),
                "max_batches": budget.max_batches,
                "per_account_limit": budget.per_account_limit,
                "bounded": True,
            },
            "account_safety": {
                "requires_explicit_live_confirmation": True,
                "deduplicated_expressions": True,
                "duplicate_expression_count": len(duplicate_expressions),
                "capacity_limited": skipped_count > 0,
                "validation_before_submit": True,
            },
            "batches": _job_batches(jobs, budget.per_account_limit),
            "jobs": jobs,
        }


BacktestJobRunner = Callable[[dict[str, Any]], dict[str, Any]]
ProgressCallback = Callable[[dict[str, Any]], None]


class ParallelBacktestExecutor:
    """Run a bounded parallel backtest plan with per-job result accounting."""

    def execute(
        self,
        expressions: list[str],
        *,
        runner: BacktestJobRunner,
        markets: list[str] | None = None,
        max_workers: int = 4,
        max_batches: int = 10,
        per_account_limit: int = 20,
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        plan = ParallelBacktestPlanner().plan(
            expressions,
            markets=markets,
            max_workers=max_workers,
            max_batches=max_batches,
            per_account_limit=per_account_limit,
        )
        jobs = [job for job in plan.get("jobs", []) if isinstance(job, dict)]
        events: list[dict[str, Any]] = []
        if not jobs:
            _emit_event(events, progress_callback, "plan_empty", selected_jobs=0, requested_jobs=plan.get("requested_jobs", 0))
            return {
                "ok": False,
                "schema_version": "parallel_backtest_execution.v1",
                "error_code": plan.get("error_code") or "EMPTY_PARALLEL_BACKTEST_PLAN",
                "requested_jobs": plan.get("requested_jobs", 0),
                "selected_jobs": 0,
                "submitted_count": 0,
                "completed_count": 0,
                "failed_count": 0,
                "skipped_jobs": plan.get("skipped_jobs", 0),
                "rate_limit": dict(plan.get("rate_limit") or {}),
                "account_safety": dict(plan.get("account_safety") or {}),
                "plan": plan,
                "results": [],
                "progress_events": events,
            }

        safe_workers = min(
            max(1, int(max_workers or 1)),
            max(1, int(plan.get("rate_limit", {}).get("max_workers") or 1)),
            len(jobs),
        )
        results: list[dict[str, Any] | None] = [None] * len(jobs)
        _emit_event(
            events,
            progress_callback,
            "planned",
            selected_jobs=len(jobs),
            requested_jobs=plan.get("requested_jobs", 0),
            skipped_jobs=plan.get("skipped_jobs", 0),
            max_workers=safe_workers,
        )
        if safe_workers == 1:
            for index, job in enumerate(jobs):
                _emit_event(events, progress_callback, "job_started", job_index=index, market=job.get("market", ""))
                results[index] = _run_job(index, job, runner)
                _emit_event(
                    events,
                    progress_callback,
                    "job_finished",
                    job_index=index,
                    market=job.get("market", ""),
                    ok=bool(results[index].get("ok")) if isinstance(results[index], dict) else False,
                )
        else:
            with ThreadPoolExecutor(max_workers=safe_workers) as executor:
                futures = {
                    executor.submit(_run_job, index, job, runner): index
                    for index, job in enumerate(jobs)
                }
                for index, job in enumerate(jobs):
                    _emit_event(events, progress_callback, "job_started", job_index=index, market=job.get("market", ""))
                for future in as_completed(futures):
                    index = futures[future]
                    try:
                        results[index] = future.result()
                    except Exception as exc:
                        results[index] = _job_error(index, jobs[index], exc)
                    _emit_event(
                        events,
                        progress_callback,
                        "job_finished",
                        job_index=index,
                        market=jobs[index].get("market", ""),
                        ok=bool(results[index].get("ok")) if isinstance(results[index], dict) else False,
                    )

        item_results = [result for result in results if isinstance(result, dict)]
        submitted_count = sum(1 for result in item_results if result.get("simulation_id"))
        completed_count = sum(
            1
            for result in item_results
            if str(result.get("status", "")).upper() == "COMPLETED"
        )
        failed_count = sum(1 for result in item_results if not bool(result.get("ok")))
        failure_counts = _failure_counts(item_results)
        _emit_event(
            events,
            progress_callback,
            "completed",
            selected_jobs=len(jobs),
            submitted_count=submitted_count,
            completed_count=completed_count,
            failed_count=failed_count,
        )
        return {
            "ok": failed_count == 0 and len(item_results) == len(jobs),
            "schema_version": "parallel_backtest_execution.v1",
            "requested_jobs": plan.get("requested_jobs", 0),
            "selected_jobs": len(jobs),
            "submitted_count": submitted_count,
            "completed_count": completed_count,
            "failed_count": failed_count,
            "failure_counts": failure_counts,
            "skipped_jobs": plan.get("skipped_jobs", 0),
            "max_workers": safe_workers,
            "rate_limit": {
                **dict(plan.get("rate_limit") or {}),
                "max_workers": safe_workers,
                "bounded": True,
            },
            "account_safety": dict(plan.get("account_safety") or {}),
            "plan": plan,
            "results": item_results,
            "progress_events": events,
        }


def _run_job(index: int, job: dict[str, Any], runner: BacktestJobRunner) -> dict[str, Any]:
    try:
        payload = runner(dict(job))
        if not isinstance(payload, dict):
            raise TypeError("backtest runner must return a mapping")
        result = dict(payload)
    except Exception as exc:
        return _job_error(index, job, exc)
    result.setdefault("ok", True)
    result["job_index"] = index
    result.setdefault("market", job.get("market", ""))
    result.setdefault("expression", job.get("expression", ""))
    status = str(result.get("status") or "").upper()
    if status in {"FAILED", "ERROR"}:
        result["ok"] = False
        result.setdefault("error_code", f"SIMULATION_{status}")
    return result


def _job_error(index: int, job: dict[str, Any], exc: Exception) -> dict[str, Any]:
    return {
        "ok": False,
        "error_code": "PARALLEL_BACKTEST_JOB_ERROR",
        "error": str(exc),
        "job_index": index,
        "market": job.get("market", ""),
        "expression": job.get("expression", ""),
    }


def _job_batches(jobs: list[dict[str, Any]], batch_size: int) -> list[dict[str, Any]]:
    safe_size = max(1, int(batch_size or 1))
    batches: list[dict[str, Any]] = []
    for start in range(0, len(jobs), safe_size):
        chunk = jobs[start : start + safe_size]
        batches.append(
            {
                "batch_index": len(batches),
                "job_count": len(chunk),
                "first_job_index": chunk[0]["job_index"] if chunk else 0,
                "last_job_index": chunk[-1]["job_index"] if chunk else 0,
            }
        )
    return batches


def _unique_text(values: list[str]) -> list[str]:
    seen: set[str] = set()
    rows: list[str] = []
    for value in values:
        text = str(value or "").strip()
        marker = text.lower()
        if not text or marker in seen:
            continue
        seen.add(marker)
        rows.append(text)
    return rows


def _duplicate_text(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    duplicate_markers: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        marker = text.lower()
        if not text:
            continue
        if marker in seen and marker not in duplicate_markers:
            duplicates.append(text)
            duplicate_markers.add(marker)
        seen.add(marker)
    return duplicates


def _failure_counts(results: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        if result.get("ok"):
            continue
        code = str(result.get("error_code") or result.get("status") or "UNKNOWN_FAILURE").strip() or "UNKNOWN_FAILURE"
        counts[code] = counts.get(code, 0) + 1
    return counts


def _emit_event(events: list[dict[str, Any]], callback: ProgressCallback | None, event: str, **data: Any) -> None:
    payload = {
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **data,
    }
    events.append(payload)
    if callback is None:
        return
    try:
        callback(dict(payload))
    except Exception:
        return
