"""Auto-submission safety and cross-review helpers for AlphaResearchPipeline.

Migrated from PipelineSubmissionMixin to standalone class
using composition instead of inheritance.
"""

from __future__ import annotations
from dataclasses import asdict

import logging
from typing import TYPE_CHECKING

from brain_alpha_ops.candidate_lifecycle import LifecycleState, transition
from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.scoring._gate_decision import GateDecisionService
from brain_alpha_ops.scoring.release_score_gate import evaluate_release_score
from brain_alpha_ops.submission_readiness import (
    live_submit_readiness_hard_gate,
    missing_official_metric_fields,
)

from .assistant import build_assistant_request_pack
from .context import build_assistant_context_pack
from .pipeline_helpers import blocked_gate as _blocked_gate

if TYPE_CHECKING:
    from .pipeline import AlphaResearchPipeline

logger = logging.getLogger(__name__)
SUBMITTED_CLOUD_STATUSES = {"ACTIVE", "SUBMITTED", "PRODUCTION", "CONDUCTED"}


class SubmissionGateService:
    """Standalone submission gate service using composition.

    Takes a pipeline instance and accesses its state through the reference.
    """

    def __init__(self, pipeline: AlphaResearchPipeline) -> None:
        self._pipeline = pipeline
        self._gate_decision_service = GateDecisionService()

    def _check_before_submit(self, candidate: Candidate) -> dict:
        p = self._pipeline
        if not candidate.official_metrics or not candidate.expression:
            return {"passed": True, "failed_checks": [], "warnings": []}

        sim_result = {
            "_thresholds": p.config.thresholds,
            **candidate.official_metrics,
            "expression": candidate.expression,
            "data_fields": getattr(candidate, "data_fields", []),
            "operators": getattr(candidate, "operators", []),
        }
        try:
            sim_result["settings"] = asdict(p.config.settings)
        except Exception as exc:
            logger.warning(
                "Failed to serialize settings for check registry: %s",
                redact_error_message(exc),
            )

        try:
            report = p.check_registry.evaluate(sim_result)
        except Exception as exc:
            return {
                "passed": False,
                "failed_checks": [{"name": "check_registry_error", "message": redact_error_message(exc)}],
                "warnings": [],
            }

        errors = [r for r in report.results if not r.passed and r.severity == "ERROR"]
        warnings = [r for r in report.results if not r.passed and r.severity != "ERROR"]

        return {
            "passed": len(errors) == 0,
            "failed_checks": [{"name": r.check_name, "message": r.message} for r in errors],
            "warnings": [{"name": r.check_name, "message": r.message} for r in warnings],
        }

    def _try_auto_submit(self, candidate: Candidate, submitted_this_run: int) -> int:
        p = self._pipeline
        safety = self._assess_auto_submission(candidate, submitted_this_run)
        candidate.submission["safety"] = safety
        if not safety["allowed"]:
            p.services.runtime._event("auto_submit_skipped", "; ".join(safety["failed_reasons"]), candidate.alpha_id)
            return 0
        cross_review = p._pre_submit_cross_review(candidate)
        candidate.submission["cross_review"] = cross_review
        if not cross_review.get("allowed", False):
            failed_reasons = list(cross_review.get("failed_reasons") or [])
            if not failed_reasons:
                failed_reasons = ["cross_review_rejected"]
            candidate.gate = _blocked_gate("CROSS_REVIEW_BLOCKED", failed_reasons)
            transition(
                candidate, LifecycleState.ready_for_review,
                reason="auto_submit_cross_review_blocked",
                legacy_status="auto_submit_cross_review_blocked",
            )
            p.services.runtime._event("auto_submit_cross_review_blocked", "; ".join(failed_reasons), candidate.alpha_id, level="WARN")
            return 0
        readiness_gate = p._live_submit_readiness_gate(candidate)
        candidate.submission["live_submit_readiness"] = readiness_gate
        if not readiness_gate.get("ok"):
            failed_reasons = [
                str(readiness_gate.get("error_code") or "SUBMIT_READINESS_NOT_READY")
            ]
            candidate.gate = _blocked_gate("LIVE_SUBMIT_READINESS_BLOCKED", failed_reasons)
            transition(
                candidate, LifecycleState.ready_for_review,
                reason="auto_submit_readiness_blocked",
                legacy_status="auto_submit_readiness_blocked",
            )
            p.services.runtime._event("auto_submit_readiness_blocked", "; ".join(failed_reasons), candidate.alpha_id, level="WARN")
            return 0
        submission = p.api.submit_alpha(
            candidate.official_alpha_id,
            candidate.expression,
            p.config.settings.to_platform_dict()["settings"],
        )
        candidate.submission["result"] = submission
        transition(
            candidate, LifecycleState.submitted,
            reason="auto_submitted",
            legacy_status="submitted",
        )
        p.ledger.record(candidate, submission, mode="auto")
        p.services.runtime._record_lifecycle(candidate, "submitted", "auto")
        p.services.runtime._event("alpha_submitted", f"Submitted {candidate.alpha_id}.", candidate.alpha_id)
        return 1

    def _pre_submit_cross_review(self, candidate: Candidate) -> dict:
        p = self._pipeline
        try:
            context_pack = build_assistant_context_pack(
                RunConfig(ops=p.config),
                latest_result_snapshot=self._candidate_review_snapshot(candidate),
                include_prompt=False,
            )
            request_pack = build_assistant_request_pack(context_pack)
            primary_response = request_pack.get("offline_draft") or {}
            review_result = p._cross_review_service.review(
                request_pack,
                primary_response,
                min_confidence=0.6,
            )
            allowed = str(review_result.get("decision") or "").lower() in {"accept", "accept_with_warnings"}
            return {
                "allowed": allowed,
                "decision": review_result,
                "failed_reasons": [] if allowed else list(review_result.get("risk_flags") or review_result.get("recommendations") or ["cross_review_rejected"]),
                "request_digest": request_pack.get("prompt_digest", ""),
                "context_digest": request_pack.get("context_digest", ""),
            }
        except Exception as exc:
            message = redact_error_message(exc, max_length=180)
            p.services.runtime._event("auto_submit_cross_review_failed", message, candidate.alpha_id, level="WARN")
            return {
                "allowed": False,
                "decision": {},
                "failed_reasons": [f"cross_review_error:{message}"],
                "request_digest": "",
                "context_digest": "",
            }

    def _candidate_review_snapshot(self, candidate: Candidate) -> dict[str, object]:
        p = self._pipeline
        backtest = candidate.submission.get("local_backtest") if isinstance(candidate.submission, dict) else {}
        if not isinstance(backtest, dict):
            backtest = {}
        summary = {
            "cycle": p.run_id or "candidate_review",
            "candidates": [candidate.to_dict()],
            "passed_candidates": [candidate.to_dict()] if candidate.local_quality.get("passed") else [],
            "pending_backtest_candidates": [],
            "backtest_records": [backtest] if backtest else [],
            "official_call_policy": {
                "auto_submit": bool(getattr(p.config, "auto_submit", False)),
                "require_cloud_sync": bool(p.config.budget.require_cloud_sync),
            },
            "strategy_profile": p.services.strategy._current_strategy_profile(),
            "convergence": p.convergence.summary() if hasattr(p, "convergence") else {},
        }
        return {
            "source": "candidate_pre_submit_gate",
            "status": candidate.lifecycle_status,
            "summary": summary,
            "result": {
                "summary": summary,
                "candidates": [candidate.to_dict()],
            },
            "candidates": [candidate.to_dict()],
            "backtest_records": [backtest] if backtest else [],
            "latest_backtest": backtest,
        }

    def _record_gate_decision(self, candidate: Candidate, release_gate: dict) -> None:
        """Map gate outcomes to a lifecycle decision and record it (Workstream D2.2).

        Records the decision via ``record_gate_decision`` and triggers the
        lifecycle transition when the candidate is not already on a
        submission path.  Best-effort: never breaks the safety assessment.
        """
        try:
            from brain_alpha_ops.audit_trail.lifecycle_writer import record_gate_decision

            outcome = self._gate_decision_service.decide(
                candidate, gate_results=candidate.gate, release_gate=release_gate,
            )
            record_gate_decision(
                alpha_id=candidate.alpha_id,
                gate_name="submission_gate_decision",
                passed=outcome.action == "enter_official_simulation_queue",
                reason=outcome.reason,
                attribution=outcome.to_dict(),
                context={
                    "trigger_rule": "gate_decision_service",
                    "action": outcome.action,
                    "target_state": outcome.target_state.value,
                    "next_action_hint": outcome.next_action_hint,
                },
            )
            # Transition only for non-submission outcomes to avoid clobbering
            # the auto-submit flow (which manages its own transitions).
            current = getattr(candidate, "lifecycle_status", "") or ""
            if outcome.target_state.value not in {current, "submitted", "ready_for_review"}:
                transition(
                    candidate, outcome.target_state,
                    reason=f"gate_decision:{outcome.action}",
                    legacy_status=outcome.action,
                    context={"trigger_rule": "gate_decision_service"},
                )
            candidate.submission["gate_decision"] = outcome.to_dict()
        except Exception as exc:  # noqa: BLE001 — gate decision must never break safety
            logger.debug("gate decision recording skipped: %s", redact_error_message(exc))

    def _assess_auto_submission(self, candidate: Candidate, submitted_this_run: int) -> dict:
        p = self._pipeline
        safety = p.ledger.assess(
            candidate,
            p.config.submission_policy,
            mode="auto",
            run_submission_count=submitted_this_run,
        )
        checks = list(safety.get("checks") or [])
        failed = list(safety.get("failed_reasons") or [])

        def add(name: str, passed: bool, detail: str):
            checks.append({"name": name, "passed": bool(passed), "detail": detail})
            if not passed:
                failed.append(detail or name)

        metrics = candidate.official_metrics if isinstance(candidate.official_metrics, dict) else {}
        if not metrics:
            add("official_metric_fields_complete", False, "missing_official_metrics")
        else:
            missing_metric_fields = missing_official_metric_fields(metrics)
            add(
                "official_metric_fields_complete",
                not missing_metric_fields,
                "missing_official_metric_fields:" + ",".join(missing_metric_fields)
                if missing_metric_fields
                else "complete official metrics",
            )
            if not missing_metric_fields:
                release_gate = evaluate_release_score(metrics, p.config.thresholds, settings=p.config.settings).to_dict()
                release_gate_passed = release_gate.get("status") != "FAIL"
                failed_gate_names = [
                    str(row.get("name") or "official_release_gate")
                    for row in release_gate.get("attributions") or []
                    if isinstance(row, dict) and row.get("passed") is False and row.get("severity") == "ERROR"
                ]
                add(
                    "official_release_gate",
                    release_gate_passed,
                    "official release gate pass"
                    if release_gate_passed
                    else "official_release_gate_failed:" + ",".join(failed_gate_names),
                )
                safety["official_release_gate"] = release_gate
                self._record_gate_decision(candidate, release_gate)

        cloud_status = str(p.cloud_sync.get("status", "")).lower()
        add(
            "cloud_sync_completed",
            cloud_status in {"synced", "loaded"},
            p.cloud_sync.get("warning") or f"cloud sync status={cloud_status or 'unknown'}",
        )
        add(
            "cloud_sync_has_rows",
            bool(p.cloud_alphas),
            f"{len(p.cloud_alphas)} cloud alphas loaded",
        )
        add(
            "cloud_sync_not_stale",
            not bool(p.cloud_sync.get("stale")),
            "cloud alpha cache is stale" if p.cloud_sync.get("stale") else "cloud alpha sync is fresh",
        )

        cloud_alpha_status = p.services.candidate_pool._cloud_status_for_candidate(candidate)
        already_submitted = str(cloud_alpha_status.get("status", "")).upper() in SUBMITTED_CLOUD_STATUSES
        add(
            "cloud_status_not_already_submitted",
            not already_submitted,
            cloud_alpha_status.get("status") or "not found",
        )

        cloud_risk = p.services.candidate_pool._cloud_correlation_risk(candidate)
        add(
            "cloud_self_correlation",
            cloud_risk.get("level") != "high",
            f"{cloud_risk.get('level', 'unknown')} {float(cloud_risk.get('max_similarity', 0.0) or 0.0):.4f}",
        )

        safety["checks"] = checks
        safety["failed_reasons"] = failed
        safety["allowed"] = not failed
        safety["status"] = "ALLOW" if not failed else "BLOCK"
        if safety["allowed"] and candidate.official_metrics:
            check_result = self._check_before_submit(candidate)
            if not check_result["passed"]:
                for err in check_result["failed_checks"]:
                    failed.append(f"BRAIN_CHECK_GATE:{err['name']}:{err['message']}")
                safety["allowed"] = False
                safety["status"] = "BLOCK"
            safety["alpha_check_gate"] = check_result
        safety["cloud_sync"] = dict(p.cloud_sync)
        safety["cloud_status"] = cloud_alpha_status
        safety["cloud_correlation_risk"] = cloud_risk
        return safety
