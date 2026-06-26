"""Simulation-related real backend handlers."""

from __future__ import annotations

import logging
import threading
import time

from brain_alpha_ops.runtime_constants import (
    REAL_SUBMIT_DISABLED_WEB_FLOW,
)
from brain_alpha_ops.web.business.web_jobs import job_update as _job_update
from brain_alpha_ops.web.business.web_jobs import new_job_id as _new_job_id

logger = logging.getLogger("brain_alpha_ops.web.business.web_business")


# ── Real backend handlers ─────────────────────────────────────────────────
def _real_sync(payload):
    try:
        from brain_alpha_ops.brain_api.user_alpha_sync import (
            list_user_alphas_for_sync,
            sync_range_from_payload,
        )
        from brain_alpha_ops.config import load_run_config
        from brain_alpha_ops.runner import api_from_run_config
        config = load_run_config()
        api = api_from_run_config(config)
        sync_range = sync_range_from_payload(payload)
        alphas = list_user_alphas_for_sync(api, sync_range)
        return {"ok": True, "synced": len(alphas), "range": sync_range}
    except Exception as e:
        from brain_alpha_ops.redaction import redact_error_message
        logger.exception("real_sync failed")
        return {"ok": False, "error": redact_error_message(e)}


def _real_submit(payload):
    if REAL_SUBMIT_DISABLED_WEB_FLOW:
        return _submit_disabled_payload()
    job_id = _new_job_id("submit")
    _job_update(
        job_id,
        ok=True,
        operation="submit_alpha",
        status="running",
        progress={
            "phase": "submission",
            "status": "running",
            "status_message": "正在启动 BRAIN Alpha 提交流程...",
            "percent_complete": 5,
        },
        result=None,
    )
    thread = threading.Thread(target=_run_submit_alpha_job, args=(job_id, dict(payload or {})), daemon=True)
    thread.start()
    return {
        "ok": True,
        "job_id": job_id,
        "task_id": job_id,
        "status": "running",
        "submitted": False,
        "sse_url": f"/sse?job_id={job_id}",
        "status_url": f"/api/production-validation/status?job_id={job_id}",
    }


def _submit_disabled_payload() -> dict:
    return {
        "ok": False,
        "submitted": False,
        "status": "BLOCKED",
        "error_code": "REAL_SUBMIT_DISABLED_WEB_FLOW",
        "error": "真实提交已从普通 Web 流程关闭；请先完成提交前阻断复核，如确需提交需走单独审批路径。",
        "required_next_steps": [
            "完成官方上下文刷新和提交前阻断复核",
            "确认候选具备官方 Alpha ID 与完整官方指标",
            "如需真实提交，由维护者在单独审批路径中执行",
        ],
    }

def _run_submit_alpha_job(job_id: str, payload: dict) -> None:
    """Background job: simulate, check, and submit an alpha to BRAIN API.

    Delegates to: _submit_and_poll_simulation() → _check_submit_alpha().
    """
    expression = str(payload.get("expression", ""))
    if not expression:
        _job_update(job_id, ok=False, status="failed",
            error="No expression provided for submission.",
            progress={"phase": "submission", "status": "failed", "status_message": "提交失败：缺少表达式", "percent_complete": 100})
        return
    try:
        from brain_alpha_ops.config import load_run_config
        from brain_alpha_ops.runner import api_from_run_config
        config = load_run_config()
        api = api_from_run_config(config)
        api.authenticate()
        settings = payload.get("settings") or (config.ops.settings.to_platform_dict() if hasattr(config.ops.settings, "to_platform_dict") else config.ops.settings)
        if isinstance(settings, dict) and "settings" in settings:
            settings = settings["settings"]
        result = _submit_and_poll_simulation(job_id, expression, api, settings)
        if result is None:
            return  # failed/timeout already handled inside
        _check_and_submit_alpha(job_id, expression, api, result, settings)

    except Exception as exc:
        from brain_alpha_ops.redaction import redact_error_message
        error_msg = redact_error_message(exc)
        _job_update(job_id, ok=False, status="failed",
            error=error_msg,
            result={"ok": False, "error": error_msg, "error_code": "SUBMIT_JOB_FAILED"},
            progress={
                "phase": "submission", "status": "failed",
                "status_message": f"提交异常: {str(exc)[:100]}",
                "percent_complete": 100,
                "expression": expression,
            })



def _submit_and_poll_simulation(job_id: str, expression: str, api, settings: dict) -> dict | None:
    """Submit a BRAIN simulation and poll until completion or timeout.

    Returns the simulation result dict on success, None on failure/timeout.
    """
    _job_update(job_id, progress={
        "phase": "submission", "status": "running",
        "status_message": "正在提交 BRAIN 模拟...",
        "percent_complete": 15,
        "expression": expression,
    })
    simulation_id = api.submit_simulation(expression, settings)
    _job_update(job_id, progress={
        "phase": "submission", "status": "running",
        "status_message": f"模拟已提交 (ID: {simulation_id})，等待结果...",
        "percent_complete": 25,
        "simulation_id": simulation_id,
        "expression": expression,
    })
    max_polls = 120
    poll_interval = 6.0
    completed = False
    for attempt in range(1, max_polls + 1):
        try:
            status = api.poll_simulation(simulation_id)
        except (ValueError, TypeError, OSError):
            time.sleep(poll_interval)
            continue
        if status == "COMPLETED":
            completed = True
            break
        elif status == "FAILED":
            _job_update(job_id, ok=False, status="failed",
                error="BRAIN simulation FAILED",
                progress={
                    "phase": "submission", "status": "failed",
                    "status_message": "BRAIN 模拟失败",
                    "percent_complete": 100,
                    "simulation_id": simulation_id,
                })
            return None
        if attempt % 10 == 0:
            pct = min(25 + int(35 * attempt / max_polls), 60)
            _job_update(job_id, progress={
                "phase": "submission", "status": "running",
                "status_message": f"轮询中 ({attempt}/{max_polls})...",
                "percent_complete": pct,
                "simulation_id": simulation_id,
            })
        time.sleep(poll_interval)
    if not completed:
        _job_update(job_id, ok=False, status="failed",
            error=f"Simulation timed out after {max_polls} polls",
            progress={
                "phase": "submission", "status": "timeout",
                "status_message": "模拟超时",
                "percent_complete": 100,
                "simulation_id": simulation_id,
            })
        return None
    _job_update(job_id, progress={
        "phase": "submission", "status": "running",
        "status_message": "正在获取模拟结果...",
        "percent_complete": 65,
    })
    result = api.fetch_result(simulation_id)
    alpha_id = str(result.get("alpha_id", "") or "")
    metrics = result.get("metrics", {}) if isinstance(result, dict) else {}
    _job_update(job_id, progress={
        "phase": "submission", "status": "running",
        "status_message": f"模拟完成, Alpha ID: {alpha_id or '(none)'}",
        "percent_complete": 75,
        "alpha_id": alpha_id,
        "simulation_id": simulation_id,
        "metrics": {k: v for k, v in (metrics.items() if isinstance(metrics, dict) else []) if k in ("sharpe", "fitness", "returns", "turnover", "drawdown", "margin")},
    })
    return result


def _check_and_submit_alpha(job_id: str, expression: str, api, result: dict, settings: dict) -> None:
    """Check alpha quality gate and submit if passed."""
    alpha_id = str(result.get("alpha_id", "") or "")
    metrics = result.get("metrics", {}) if isinstance(result, dict) else {}
    if not alpha_id:
        _job_update(job_id, ok=True, status="completed",
            result={
                "submitted": False,
                "simulation_id": result.get("simulation_id", ""),
                "expression": expression,
                "metrics": metrics,
                "note": "Simulation completed but no alpha_id generated.",
            },
            progress={
                "phase": "submission", "status": "completed",
                "status_message": "模拟完成但未生成 Alpha ID",
                "percent_complete": 100,
            })
        return
    _job_update(job_id, progress={
        "phase": "submission", "status": "running",
        "status_message": f"正在检查提交闸门 (Alpha {alpha_id})...",
        "percent_complete": 82,
    })
    check = api.check_alpha(alpha_id)
    check_status = str(check.get("status", "UNKNOWN") if isinstance(check, dict) else "UNKNOWN")
    if check_status != "PASSED":
        _job_update(job_id, ok=True, status="completed",
            result={
                "submitted": False,
                "simulation_id": result.get("simulation_id", ""),
                "alpha_id": alpha_id,
                "expression": expression,
                "metrics": metrics,
                "check_status": check_status,
                "checks": check.get("checks", {}) if isinstance(check, dict) else {},
                "note": f"Pre-submit check is '{check_status}', submission not performed.",
            },
            progress={
                "phase": "submission", "status": "completed",
                "status_message": f"提交前检查: {check_status}",
                "percent_complete": 100,
            })
        return
    _job_update(job_id, progress={
        "phase": "submission", "status": "running",
        "status_message": "检查通过！正在提交...",
        "percent_complete": 90,
    })
    simulation_id = result.get("simulation_id", "")
    submit_result = api.submit_alpha(alpha_id=alpha_id, expression=expression, settings=settings, bodyless=True)
    submit_status = str(submit_result.get("status", "UNKNOWN") if isinstance(submit_result, dict) else "UNKNOWN")
    _job_update(job_id, ok=True, status="completed",
        result={
            "submitted": True,
            "simulation_id": simulation_id,
            "alpha_id": alpha_id,
            "expression": expression,
            "metrics": metrics,
            "submit_status": submit_status,
            "submit_result": submit_result,
        },
        progress={
            "phase": "submission", "status": "completed",
            "status_message": f"提交成功！Alpha: {alpha_id}",
            "percent_complete": 100,
            "submitted": True,
            "alpha_id": alpha_id,
            "simulation_id": simulation_id,
        })

def _real_submit_batch(payload):
    """Batch submit with safety gates — real submission requires pre-flight checks."""
    return _submit_disabled_payload()
