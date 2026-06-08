"""Background production job runner for the local web console."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from brain_alpha_ops.observability import error_payload


RunConfigFromPayload = Callable[[dict[str, Any]], Any]
RunPipeline = Callable[..., Any]
ComputeRunStats = Callable[[dict[str, Any], Any], dict[str, Any]]
SafeErrorMessage = Callable[[Exception], str]


def run_guided_job_service(
    job_id: str,
    payload: dict[str, Any],
    *,
    job_store: Any,
    run_config_from_payload: RunConfigFromPayload,
    compute_run_stats: ComputeRunStats,
    safe_error_message: SafeErrorMessage,
    log: logging.Logger,
) -> None:
    try:
        from brain_alpha_ops.ux.guided_pipeline import GuidedPipeline

        job_store.update(
            job_id,
            status="running",
            progress={"phase": "startup", "current": 0, "total": 1, "percent": 0, "message": "引导式生产任务启动...", "alpha_id": ""},
        )
        run_config = run_config_from_payload(payload)
        guided = GuidedPipeline(run_config, stop_callback=lambda: job_store.is_cancelled(job_id))
        phase_names = list(getattr(guided, "phases", {}) or {}) or ["guided"]

        def _progress_cb(phase: str, status: str = "", data: dict[str, Any] | None = None) -> None:
            progress_data = data if isinstance(data, dict) else {}
            try:
                current = phase_names.index(phase) + 1
            except ValueError:
                current = min(len(phase_names), 1)
            total = max(1, len(phase_names))
            explicit_percent = progress_data.get("percent")
            try:
                percent = float(explicit_percent)
            except (TypeError, ValueError):
                base = (current - 1) / total * 100.0
                percent = current / total * 100.0 if status == "completed" else max(5.0, base)
            message = (
                progress_data.get("message")
                or progress_data.get("summary")
                or progress_data.get("error")
                or status
                or phase
            )
            job_store.update(job_id, progress={
                "phase": phase,
                "status": status,
                "current": current,
                "total": total,
                "percent": max(0.0, min(100.0, percent)),
                "message": str(message),
                "alpha_id": str(progress_data.get("alpha_id") or ""),
                "data": progress_data,
            })

        guided.on_progress(_progress_cb)
        result = guided.resume() if payload.get("resume") else guided.run()

        final_status = "stopped" if job_store.is_cancelled(job_id) else "completed"
        result_data = result.to_dict() if hasattr(result, "to_dict") else result
        result_data = result_data if isinstance(result_data, dict) else {}
        summary = result_data.get("summary") if isinstance(result_data.get("summary"), dict) else {}
        candidates = summary.get("candidates") or result_data.get("candidates", [])
        backtests = summary.get("backtest_slots") or result_data.get("backtests") or []

        job_store.update(
            job_id,
            status=final_status,
            result=result_data,
            progress={
                "phase": final_status,
                "current": 1,
                "total": 1,
                "percent": 100,
                "message": "引导式任务完成。" if final_status == "completed" else "任务已停止。",
                "alpha_id": "",
                "data": {
                    "candidates": candidates,
                    "backtests": backtests,
                    "stats": compute_run_stats({"candidates": candidates, "backtests": backtests}, run_config),
                    "checkpoint_available": True,
                },
            },
        )
    except Exception as exc:
        message = safe_error_message(exc)
        error_context = error_payload(exc, error_code="GUIDED_JOB_FAILED", job_id=job_id, phase="guided_run")
        log.error("guided production job failed: %s", error_context, exc_info=True)
        job_store.update(
            job_id,
            status="failed",
            error=message,
            progress={
                "phase": "failed",
                "current": 1,
                "total": 1,
                "percent": 100,
                "message": message,
                "alpha_id": "",
                "error_context": error_context,
            },
        )


def run_job_service(
    job_id: str,
    payload: dict[str, Any],
    *,
    job_store: Any,
    run_config_from_payload: RunConfigFromPayload,
    run_pipeline_from_config: RunPipeline,
    compute_run_stats: ComputeRunStats,
    safe_error_message: SafeErrorMessage,
    log: logging.Logger,
    heartbeat_interval_seconds: float = 30.0,
) -> None:
    heartbeat_stop = threading.Event()
    heartbeat_thread: threading.Thread | None = None
    try:
        job_store.update(
            job_id,
            status="running",
            progress={"phase": "startup", "current": 0, "total": 1, "percent": 0, "message": "后台任务启动。", "alpha_id": ""},
        )
        run_config = run_config_from_payload(payload)
        heartbeat_thread = _start_pipeline_heartbeat(
            job_id,
            job_store=job_store,
            stop_event=heartbeat_stop,
            interval_seconds=heartbeat_interval_seconds,
            log=log,
        )

        def _progress_update(progress: dict[str, Any]) -> None:
            fields: dict[str, Any] = {"progress": progress}
            if _progress_terminal_status(progress) in {"stopped", "cancelled"}:
                fields["status"] = _progress_terminal_status(progress)
            job_store.update(job_id, **fields)

        result = run_pipeline_from_config(
            run_config,
            progress_callback=_progress_update,
            stop_callback=lambda: job_store.is_cancelled(job_id),
        )
        _stop_pipeline_heartbeat(heartbeat_stop, heartbeat_thread)
        heartbeat_thread = None
        final_status = "stopped" if job_store.is_cancelled(job_id) else "completed"
        result_data = result.to_dict()
        last_progress = (job_store.get(job_id) or {}).get("progress", {})
        last_data = dict(last_progress.get("data") or {})
        last_data.update(result_data.get("summary") or {})
        last_data["candidates"] = result_data.get("candidates") or []
        last_data["backtests"] = (result_data.get("summary") or {}).get("backtest_slots") or last_data.get("backtests", [])
        last_data["stats"] = compute_run_stats(last_data, run_config)
        job_store.update(
            job_id,
            status=final_status,
            result=result_data,
            progress={
                "phase": final_status,
                "current": 0 if final_status == "stopped" else 1,
                "total": 1,
                "percent": 0 if final_status == "stopped" else 100,
                "message": "任务已停止。" if final_status == "stopped" else "任务完成。",
                "alpha_id": "",
                "continuous": run_config.ops.budget.run_forever,
                "data": last_data,
            },
        )
    except Exception as exc:
        _stop_pipeline_heartbeat(heartbeat_stop, heartbeat_thread)
        message = safe_error_message(exc)
        error_context = error_payload(exc, error_code="RUN_JOB_FAILED", job_id=job_id, phase="run_job")
        log.error("production job failed: %s", error_context, exc_info=True)
        job_store.update(
            job_id,
            status="failed",
            error=message,
            progress={
                "phase": "failed",
                "current": 1,
                "total": 1,
                "percent": 100,
                "message": message,
                "alpha_id": "",
                "error_context": error_context,
            },
        )


def _start_pipeline_heartbeat(
    job_id: str,
    *,
    job_store: Any,
    stop_event: threading.Event,
    interval_seconds: float,
    log: logging.Logger,
) -> threading.Thread | None:
    interval = max(0.0, float(interval_seconds or 0.0))
    if interval <= 0:
        return None

    def _heartbeat_loop() -> None:
        count = 0
        while not stop_event.wait(interval):
            try:
                if job_store.is_cancelled(job_id):
                    return
                count += 1
                heartbeat_result = _store_heartbeat(job_store, job_id, heartbeat_count=count)
                if heartbeat_result is True:
                    continue
                if heartbeat_result is False:
                    return
                row = job_store.get(job_id) or {}
                status = str(row.get("status") or "").strip().lower()
                if status not in {"queued", "running", "stopping"}:
                    return
                progress = row.get("progress") if isinstance(row.get("progress"), dict) else {}
                message = str(
                    progress.get("status_message")
                    or progress.get("message")
                    or "等待官方接口或流水线进度回调。"
                )
                next_progress = dict(progress)
                next_progress.update({
                    "phase": str(progress.get("phase") or "pipeline_waiting"),
                    "status_message": f"{message} 后台仍在运行。",
                    "message": f"{message} 后台仍在运行。",
                    "heartbeat": {
                        "count": count,
                        "source": "web_run_job",
                        "updated_at": time.time(),
                    },
                })
                job_store.update(job_id, progress=next_progress)
            except Exception:
                log.warning("production job heartbeat failed", exc_info=True)
                return

    thread = threading.Thread(target=_heartbeat_loop, name=f"brain-alpha-heartbeat-{job_id}", daemon=True)
    thread.start()
    return thread


def _store_heartbeat(job_store: Any, job_id: str, *, heartbeat_count: int) -> bool | None:
    heartbeat = getattr(job_store, "heartbeat", None)
    if not callable(heartbeat):
        return None
    return bool(
        heartbeat(
            job_id,
            operation="run_pipeline",
            heartbeat_count=heartbeat_count,
            source="web_run_job",
        )
    )


def _stop_pipeline_heartbeat(stop_event: threading.Event, thread: threading.Thread | None) -> None:
    stop_event.set()
    if thread is not None:
        thread.join(timeout=1.0)


def _progress_terminal_status(progress: dict[str, Any]) -> str:
    if not isinstance(progress, dict):
        return ""
    status = str(progress.get("status") or "").strip().lower()
    phase = str(progress.get("phase") or "").strip().lower()
    for value in (status, phase):
        if value in {"stopped", "cancelled", "canceled"}:
            return "cancelled" if value == "canceled" else value
    return ""
