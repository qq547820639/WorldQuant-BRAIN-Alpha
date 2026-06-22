"""BRAIN Alpha Ops web business handlers.

Extracted from web/__init__.py (B-01 refactor) — all _real_* request
handlers, plus security helpers used by the dispatch layer.
"""

from __future__ import annotations

import logging
import threading
import time

from brain_alpha_ops.config import load_run_config as _load_run_config
from brain_alpha_ops.runtime_constants import (
    REAL_SUBMIT_DISABLED_WEB_FLOW,
)
from brain_alpha_ops.web.business.web_jobs import job_update as _job_update
from brain_alpha_ops.web.business.web_jobs import new_job_id as _new_job_id
from brain_alpha_ops.web.security.web_session import (
    DEFAULT_SESSION_TTL_SECONDS as _SESSION_TTL_SECONDS,
)
from brain_alpha_ops.web.security.web_session import csrf_for_session as _csrf_for_session

# ═══════════════════════════════════════════════════════════════════════
# B-07: Explicit dependency injection points (replaces globals().get())
# These module-level variables are set by web/__init__.py at application
# startup, making the dependency graph explicit and IDE-trackable.
# ═══════════════════════════════════════════════════════════════════════

_load_run_config_injected = None
_run_config_from_payload_injected = None
_web_error_injected = None
_submit_background_job_injected = None
_job_registry_injected = None


def inject_dependencies(
    *,
    load_run_config=None,
    run_config_from_payload=None,
    web_error=None,
    submit_background_job=None,
    job_registry=None,
):
    """Inject web-module dependencies for production use.
    
    Called by web/__init__.py during application startup. Each kwarg maps
    to the function or object that the business layer needs.
    """
    global _load_run_config_injected, _run_config_from_payload_injected
    global _web_error_injected, _submit_background_job_injected, _job_registry_injected
    if load_run_config is not None:
        _load_run_config_injected = load_run_config
    if run_config_from_payload is not None:
        _run_config_from_payload_injected = run_config_from_payload
    if web_error is not None:
        _web_error_injected = web_error
    if submit_background_job is not None:
        _submit_background_job_injected = submit_background_job
    if job_registry is not None:
        _job_registry_injected = job_registry

logger = logging.getLogger(__name__)


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

def _real_generate(payload):
    job_id = _new_job_id("generate")
    _job_update(
        job_id,
        ok=True,
        operation="generate_candidates",
        status="running",
        progress={
            "phase": "candidate_generation",
            "status": "running",
            "status_message": "Generating local Alpha candidates and quality diagnostics.",
            "percent_complete": 5,
        },
        result=None,
    )
    thread = threading.Thread(target=_run_generate_candidates_job, args=(job_id, dict(payload or {})), daemon=True)
    thread.start()
    return {
        "ok": True,
        "job_id": job_id,
        "task_id": job_id,
        "status": "running",
        "sse_url": f"/sse?job_id={job_id}",
        "status_url": f"/api/production-validation/status?job_id={job_id}",
    }


def _run_generate_candidates_job(job_id: str, payload: dict) -> None:
    _job_update(
        job_id,
        progress={
            "phase": "candidate_generation",
            "status": "running",
            "status_message": "Applying local generation, quality gates, and output-parameter audit.",
            "percent_complete": 35,
        },
    )
    try:
        # Initialize official data loader so local_quality() can score expressions
        from brain_alpha_ops.data import OfficialDataLoader
        from brain_alpha_ops.models import Candidate
        from brain_alpha_ops.redaction import redact_error_message
        from brain_alpha_ops.research.repository import ResearchRepository
        from brain_alpha_ops.web_candidates.generation import generate_candidates_payload
        OfficialDataLoader.instance()

        run_config_loader = _load_run_config_injected or _load_run_config
        run_config = run_config_loader()
        result = generate_candidates_payload(
            payload,
            run_config_from_payload=lambda _body: run_config,
        )
        if result.get("ok"):
            persistence = _persist_generated_candidates(job_id, run_config, result, Candidate, ResearchRepository)
            summary = result.setdefault("summary", {})
            if isinstance(summary, dict):
                summary["persistence"] = persistence
        # P1-2: Auto-record trend on successful candidate generation
        if result.get("ok"):
            try:
                from brain_alpha_ops.web.api.trends import record_trend
                generated_count = int(result.get("count") or len(result.get("candidates") or []))
                record_trend(
                    candidates=generated_count,
                    submissions=0,
                    completed_cycles=0,
                )
            except (ValueError, TypeError, OSError):
                pass

        status = "completed" if result.get("ok") else "failed"
        _job_update(
            job_id,
            ok=bool(result.get("ok")),
            status=status,
            result=result,
            error=result.get("error", ""),
            progress={
                "phase": "candidate_generation",
                "status": status,
                "status_message": _generation_status_message(result),
                "percent_complete": 100,
                "candidates_generated": int(result.get("count") or len(result.get("candidates") or [])),
                "quality_summary": (result.get("summary") or {}).get("quality_summary") if isinstance(result.get("summary"), dict) else {},
            },
        )
    except Exception as exc:
        try:
            from brain_alpha_ops.redaction import redact_error_message

            error = redact_error_message(exc)
        except (ValueError, TypeError, OSError):
            error = str(exc)
        _job_update(
            job_id,
            ok=False,
            status="failed",
            error=error,
            result={"ok": False, "error": error, "error_code": "GENERATE_CANDIDATES_JOB_FAILED"},
            progress={
                "phase": "candidate_generation",
                "status": "failed",
                "status_message": "Candidate generation failed before quality diagnostics completed.",
                "percent_complete": 100,
                "error": error,
            },
        )


def _persist_generated_candidates(job_id: str, run_config, result: dict, candidate_type, repository_type) -> dict:
    repo = repository_type(run_config.ops.storage_dir)
    persisted = 0
    skipped_invalid = 0
    skipped_reasons: dict[str, int] = {}
    errors: list[str] = []
    for row in result.get("candidates") or []:
        if not isinstance(row, dict):
            continue
        if not _generated_candidate_persistable(row):
            skipped_invalid += 1
            for reason in _generated_candidate_skip_reasons(row):
                skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
            continue
        try:
            from brain_alpha_ops.web_candidates.audit import attach_scientific_audit

            if "scientific_audit" not in row and not (
                isinstance(row.get("extra_fields"), dict)
                and isinstance(row.get("extra_fields", {}).get("scientific_audit"), dict)
            ):
                row = attach_scientific_audit(
                    row,
                    operation="candidate_generation",
                    source="candidate_persistence",
                    feedback_sources=["local_quality", "scorecard", "quality_gate"],
                )
            repo.save_candidate(job_id, candidate_type.from_dict(row))
            persisted += 1
        except Exception as exc:
            try:
                from brain_alpha_ops.redaction import redact_error_message

                errors.append(redact_error_message(exc))
            except (ValueError, TypeError, OSError):
                errors.append(str(exc))
    return {
        "schema_version": "candidate-persistence-v1",
        "target": "candidates.jsonl",
        "persisted_count": persisted,
        "skipped_invalid_count": skipped_invalid,
        "skipped_invalid_reasons": skipped_reasons,
        "error_count": len(errors),
        "errors": errors[:3],
    }


def _generated_candidate_persistable(row: dict) -> bool:
    diagnosis = row.get("quality_diagnosis") if isinstance(row.get("quality_diagnosis"), dict) else {}
    if diagnosis.get("local_candidate_valid") is False:
        return False
    local_quality = row.get("local_quality") if isinstance(row.get("local_quality"), dict) else {}
    if local_quality.get("passed") is False:
        return False
    return True


def _generated_candidate_skip_reasons(row: dict) -> list[str]:
    diagnosis = row.get("quality_diagnosis") if isinstance(row.get("quality_diagnosis"), dict) else {}
    reasons: list[str] = []
    for reason in diagnosis.get("blocking_reasons") or []:
        text = str(reason or "").strip()
        if text:
            reasons.append(text)
    local_quality = row.get("local_quality") if isinstance(row.get("local_quality"), dict) else {}
    for reason in local_quality.get("reasons") or []:
        text = str(reason or "").strip()
        if text:
            reasons.append(text.split(":", 1)[0])
    return sorted(set(reasons)) or ["local_candidate_invalid"]


def _generation_status_message(result: dict) -> str:
    if not result.get("ok"):
        return str(result.get("error") or "Candidate generation failed.")
    from brain_alpha_ops.web_candidates.generation_summary import (
        candidate_generation_status_message,
    )

    return candidate_generation_status_message(result)

def _real_check(payload):
    try:
        from brain_alpha_ops.research.expression_ast import expression_key
        expr = payload.get("expression", "")
        key = expression_key(expr)
        return {
            "ok": True,
            "local_only": True,
            "official_api_called": False,
            "available": True,
            "expression_key": key,
            "status": "LOCAL_EXPRESSION_CHECK_ONLY",
            "requires_official_check": True,
        }
    except Exception as e:
        from brain_alpha_ops.redaction import redact_error_message
        logger.exception("real_check failed")
        return {"ok": False, "error": redact_error_message(e)}

def _real_score(payload):
    try:
        from brain_alpha_ops.config import load_run_config
        from brain_alpha_ops.models import Candidate
        from brain_alpha_ops.research.scoring import build_scorecard
        config = load_run_config()
        expr = payload.get("expression", "")
        candidate = Candidate(expression=expr, alpha_id='', family='', hypothesis='')
        scorecard = build_scorecard(candidate, config.ops.thresholds, config.ops.scoring)
        return {"ok": True, "scoring": {
            "sharpe": float(scorecard.get("sharpe", 0) if isinstance(scorecard, dict) else getattr(scorecard, "sharpe", 0)),
            "fitness": float(scorecard.get("fitness", 0) if isinstance(scorecard, dict) else getattr(scorecard, "fitness", 0)),
            "local_score": float(scorecard.get("local_score", 0) if isinstance(scorecard, dict) else getattr(scorecard, "local_score", 0)),
        }}
    except Exception as e:
        from brain_alpha_ops.redaction import redact_error_message
        logger.exception("real_score failed")
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


def _real_connection(payload):
    try:
        from brain_alpha_ops.runner import api_from_run_config
        config_from_payload = _run_config_from_payload_injected
        if config_from_payload is None:
            return {"ok": False, "error_code": "FACADE_NOT_READY",
                    "error": "configuration service is not initialized yet"}
        config = config_from_payload(_safe_non_submit_run_payload(payload))
        api = api_from_run_config(config)
        auth_result = api.authenticate()
        profile = api.get_user_profile() if hasattr(api, "get_user_profile") else {}
        if isinstance(profile, dict) and profile.get("error"):
            from brain_alpha_ops.brain_api.base import BrainAPIError
            try:
                status_code = int(profile.get("status_code") or 0)
            except (TypeError, ValueError):
                status_code = 0
            raise BrainAPIError(
                str(profile.get("error") or "BRAIN profile check failed"),
                status_code=status_code or None,
                payload=profile,
            )
        auth_mode = ""
        if isinstance(auth_result, dict):
            auth_mode = str(auth_result.get("auth") or "")
        return {"ok": True, "connected": True, "environment": config.environment,
                "auth": auth_mode, "tier": profile.get("tier", "unknown") if isinstance(profile, dict) else "unknown"}
    except Exception as e:
        from brain_alpha_ops.redaction import redact_error_message
        logger.exception("real_connection failed")
        return _web_error_injected(e, "CONNECTION_FAILED") if _web_error_injected is not None else {"ok": False, "connected": False, "error": redact_error_message(e)}

def _real_run(payload):
    try:
        safe_payload = _safe_non_submit_run_payload(payload)
        # Validate before queuing so bad UI payloads fail synchronously. This
        # does not persist request credentials; run_config_from_payload only
        # applies them to the in-memory RunConfig used by this request.
        config_from_payload = _run_config_from_payload_injected
        if config_from_payload is None:
            return {"ok": False, "error_code": "FACADE_NOT_READY",
                    "error": "configuration service is not initialized yet"}
        config_from_payload(safe_payload)
        jobs = _production_job_store()
        if jobs is None:
            return {"ok": False, "error_code": "JOB_STORE_UNAVAILABLE", "error": "production job store is not available"}
        active = jobs.latest_active()
        if active:
            active_job_id, _job = active
            return {
                "ok": False,
                "error_code": "CONFLICT_RUNNING",
                "error": "已有生产任务正在运行，请先停止当前任务。",
                "job_id": active_job_id,
                "task_id": active_job_id,
            }
        job_id = jobs.create({
            "operation": "production_run",
            "safe_mode": {"auto_submit": False, "submit_endpoint_required": True},
            "result": {
                "summary": {
                    "submitted_this_run": 0,
                    "auto_submitted": 0,
                },
            },
            "progress": {
                "phase": "queued",
                "percent": 0,
                "percent_complete": 0,
                "message": "Non-submit production run queued.",
                "status_message": "非提交流水线已排队。",
            },
        })
        starter = _submit_background_job_injected
        if callable(starter):
            starter(run_job, job_id, safe_payload)  # noqa: F821
        else:
            threading.Thread(target=run_job, args=(job_id, safe_payload), daemon=True).start()  # noqa: F821
        return {
            "ok": True,
            "job_id": job_id,
            "task_id": job_id,
            "auto_submit": False,
            "submitted": False,
            "sse_url": f"/sse?job_id={job_id}",
            "status_url": f"/api/production-validation/status?job_id={job_id}",
        }
    except Exception as e:
        from brain_alpha_ops.redaction import redact_error_message
        logger.exception("failed to start non-submit production job")
        return _web_error_injected(e, "RUN_ERROR") if _web_error_injected is not None else {"ok": False, "error": redact_error_message(e)}


def _safe_non_submit_run_payload(payload: dict | None) -> dict:
    safe_payload = dict(payload or {})
    safe_payload["autoSubmit"] = False
    safe_payload["auto_submit"] = False
    return safe_payload


def _production_job_store():
    """Return the production job store from the web module facade.

    Uses direct attribute access on the current module's globals rather than
    sys.modules string lookup, since JOB_REGISTRY is injected at module load time.
    """
    registry = _job_registry_injected
    return getattr(registry, "jobs", None) if registry is not None else None

def _real_check_batch(payload):
    """Batch expression validation delegating to web_check_batch_context."""
    from brain_alpha_ops.web_check_batch_context import (
        check_batch_official_context_payload,
    )

    # Resolve through globals so tests can monkeypatch web.load_run_config.
    loader = _load_run_config_injected or _load_run_config
    return check_batch_official_context_payload(payload, load_run_config=loader)

def _real_submit_batch(payload):
    """Batch submit with safety gates — real submission requires pre-flight checks."""
    return _submit_disabled_payload()

def _real_attribution(payload):
    """Real score attribution from the scoring system."""
    try:
        from brain_alpha_ops.config import load_run_config
        from brain_alpha_ops.models import Candidate
        from brain_alpha_ops.scoring.official_scoring import OfficialScoringSystem

        config = load_run_config()
        expression = payload.get("expression", "")
        if not expression:
            return {"ok": False, "error": "expression is required"}

        candidate = Candidate(expression=expression, alpha_id="", family="", hypothesis="")
        oss = OfficialScoringSystem(config.ops)
        result = oss.evaluate(candidate)

        return {
            "ok": True,
            "attribution": result.to_dict(),
            "report": result.attribution_report(),
        }
    except Exception as e:
        from brain_alpha_ops.redaction import redact_error_message
        logger.exception("real_attribution failed")
        return {"ok": False, "error": redact_error_message(e)}

def _real_stop(payload):
    """Request cancellation for the active production job."""
    try:
        job_id = str((payload or {}).get("job_id") or "")
        jobs = _production_job_store()
        if jobs is None:
            return {"ok": False, "error_code": "JOB_STORE_UNAVAILABLE", "error": "production job store is not available"}
        return {"ok": jobs.cancel(job_id), "job_id": job_id, "status": "stopping"}
    except Exception as e:
        from brain_alpha_ops.redaction import redact_error_message
        logger.exception("real_stop failed")
        return {"ok": False, "error": redact_error_message(e)}

def _real_session(payload):
    """Create or validate a web session."""
    from brain_alpha_ops.web.security.web_session import new_session_id
    sid = new_session_id()
    csrf = _csrf_for_session(sid)
    return {
        "ok": True,
        "session_id": sid[:8],
        "csrf_token": csrf[:16],
        "ttl_seconds": _SESSION_TTL_SECONDS,  # B-04: was NameError
    }


def _has_valid_local_origin(handler) -> bool:
    """Validate request origin through handler's built-in check."""
    checker = getattr(handler, "_is_allowed_local_request", None)
    if callable(checker):
        try:
            return bool(checker())
        except (ValueError, TypeError, OSError):
            logger.warning("Origin check failed with exception, denying request", exc_info=True)
            return False
    return False  # Deny-by-default: reject if handler has no origin checker (M-SEC-04)


def _has_valid_api_session(handler) -> bool:
    """Validate session/CSRF for API routes through handler's built-in check."""
    checker = getattr(handler, "_has_valid_session", None)
    if callable(checker):
        try:
            return bool(checker(""))
        except (ValueError, TypeError, OSError):
            logger.warning("Session check failed with exception, denying request", exc_info=True)
            return False
    return False  # Safety: deny if handler has no session checker
