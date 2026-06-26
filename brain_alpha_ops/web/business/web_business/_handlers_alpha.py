"""Alpha-related real backend handlers."""

from __future__ import annotations

import logging
import sys
import threading

from brain_alpha_ops.config import load_run_config as _load_run_config
from brain_alpha_ops.web.business.web_jobs import job_update as _job_update
from brain_alpha_ops.web.business.web_jobs import new_job_id as _new_job_id

logger = logging.getLogger("brain_alpha_ops.web.business.web_business")


def _pkg():
    return sys.modules["brain_alpha_ops.web.business.web_business"]


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

        run_config_loader = _pkg()._load_run_config_injected or _load_run_config
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

def _real_check_batch(payload):
    """Batch expression validation delegating to web_check_batch_context."""
    from brain_alpha_ops.web_check_batch_context import (
        check_batch_official_context_payload,
    )

    # Resolve through globals so tests can monkeypatch web.load_run_config.
    loader = _pkg()._load_run_config_injected or _load_run_config
    return check_batch_official_context_payload(payload, load_run_config=loader)
