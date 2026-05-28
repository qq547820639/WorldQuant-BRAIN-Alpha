"""Auto-submission safety and cross-review helpers for AlphaResearchPipeline."""

from __future__ import annotations

import logging

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.redaction import redact_error_message

from .assistant import build_assistant_request_pack
from .context import build_assistant_context_pack
from .pipeline_helpers import blocked_gate as _blocked_gate

logger = logging.getLogger(__name__)
SUBMITTED_CLOUD_STATUSES = {"ACTIVE", "SUBMITTED", "PRODUCTION", "CONDUCTED"}


class PipelineSubmissionMixin:
    def _check_before_submit(self, candidate: Candidate) -> dict:
        """提交前最终 AlphaCheck 门禁。

        仅在 safety checks 全部通过后调用，确保 ERROR 级别
        AlphaCheck 失败会阻断自动提交。

        Returns:
            {"passed": bool, "failed_checks": [...], "warnings": [...]}
        """
        if not candidate.official_metrics or not candidate.expression:
            return {"passed": True, "failed_checks": [], "warnings": []}

        sim_result = {
            "_thresholds": self.config.thresholds,
            **candidate.official_metrics,
            "expression": candidate.expression,
            "data_fields": getattr(candidate, "data_fields", []),
            "operators": getattr(candidate, "operators", []),
        }
        try:
            sim_result["settings"] = self.config.settings.__dict__
        except Exception as exc:
            logger.warning("Failed to serialize settings for check registry: %s", exc)

        try:
            report = self.check_registry.evaluate(sim_result)
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
        safety = self._assess_auto_submission(candidate, submitted_this_run)
        candidate.submission["safety"] = safety
        if not safety["allowed"]:
            self._event("auto_submit_skipped", "; ".join(safety["failed_reasons"]), candidate.alpha_id)
            return 0
        cross_review = self._pre_submit_cross_review(candidate)
        candidate.submission["cross_review"] = cross_review
        if not cross_review.get("allowed", False):
            failed_reasons = list(cross_review.get("failed_reasons") or [])
            if not failed_reasons:
                failed_reasons = ["cross_review_rejected"]
            candidate.gate = _blocked_gate("CROSS_REVIEW_BLOCKED", failed_reasons)
            candidate.lifecycle_status = "auto_submit_cross_review_blocked"
            self._event("auto_submit_cross_review_blocked", "; ".join(failed_reasons), candidate.alpha_id, level="WARN")
            return 0
        submission = self.api.submit_alpha(
            candidate.official_alpha_id,
            candidate.expression,
            self.config.settings.to_platform_dict()["settings"],
        )
        candidate.submission["result"] = submission
        candidate.lifecycle_status = "submitted"
        self.ledger.record(candidate, submission, mode="auto")
        self._record_lifecycle(candidate, "submitted", "auto")
        self._event("alpha_submitted", f"Submitted {candidate.alpha_id}.", candidate.alpha_id)
        return 1

    def _pre_submit_cross_review(self, candidate: Candidate) -> dict:
        try:
            context_pack = build_assistant_context_pack(
                RunConfig(ops=self.config),
                latest_result_snapshot=self._candidate_review_snapshot(candidate),
                include_prompt=False,
            )
            request_pack = build_assistant_request_pack(context_pack)
            primary_response = request_pack.get("offline_draft") or {}
            review_result = self._cross_review_service.review(
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
            self._event("auto_submit_cross_review_failed", message, candidate.alpha_id, level="WARN")
            return {
                "allowed": False,
                "decision": {},
                "failed_reasons": [f"cross_review_error:{message}"],
                "request_digest": "",
                "context_digest": "",
            }

    def _candidate_review_snapshot(self, candidate: Candidate) -> dict[str, object]:
        backtest = candidate.submission.get("local_backtest") if isinstance(candidate.submission, dict) else {}
        if not isinstance(backtest, dict):
            backtest = {}
        summary = {
            "cycle": self.run_id or "candidate_review",
            "candidates": [candidate.to_dict()],
            "passed_candidates": [candidate.to_dict()] if candidate.local_quality.get("passed") else [],
            "pending_backtest_candidates": [],
            "backtest_records": [backtest] if backtest else [],
            "official_call_policy": {
                "auto_submit": bool(getattr(self.config, "auto_submit", False)),
                "require_cloud_sync": bool(self.config.budget.require_cloud_sync),
            },
            "strategy_profile": self._current_strategy_profile(),
            "convergence": self.convergence.summary() if hasattr(self, "convergence") else {},
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

    def _assess_auto_submission(self, candidate: Candidate, submitted_this_run: int) -> dict:
        safety = self.ledger.assess(
            candidate,
            self.config.submission_policy,
            mode="auto",
            run_submission_count=submitted_this_run,
        )
        checks = list(safety.get("checks") or [])
        failed = list(safety.get("failed_reasons") or [])

        def add(name: str, passed: bool, detail: str):
            checks.append({"name": name, "passed": bool(passed), "detail": detail})
            if not passed:
                failed.append(detail or name)

        if self.config.budget.require_cloud_sync:
            cloud_status = str(self.cloud_sync.get("status", "")).lower()
            add(
                "cloud_sync_completed",
                cloud_status in {"synced", "loaded"},
                self.cloud_sync.get("warning") or f"cloud sync status={cloud_status or 'unknown'}",
            )
            add(
                "cloud_sync_has_rows",
                bool(self.cloud_alphas),
                f"{len(self.cloud_alphas)} cloud alphas loaded",
            )
            add(
                "cloud_sync_not_stale",
                not bool(self.cloud_sync.get("stale")),
                "cloud alpha cache is stale" if self.cloud_sync.get("stale") else "cloud alpha sync is fresh",
            )

        cloud_alpha_status = self._cloud_status_for_candidate(candidate)
        already_submitted = str(cloud_alpha_status.get("status", "")).upper() in SUBMITTED_CLOUD_STATUSES
        add(
            "cloud_status_not_already_submitted",
            not already_submitted,
            cloud_alpha_status.get("status") or "not found",
        )

        cloud_risk = self._cloud_correlation_risk(candidate)
        add(
            "cloud_self_correlation",
            cloud_risk.get("level") != "high",
            f"{cloud_risk.get('level', 'unknown')} {float(cloud_risk.get('max_similarity', 0.0) or 0.0):.4f}",
        )

        safety["checks"] = checks
        safety["failed_reasons"] = failed
        safety["allowed"] = not failed
        safety["status"] = "ALLOW" if not failed else "BLOCK"
        # ── P0-4: AlphaCheck gate — ERROR-level failures block submission ──
        if safety["allowed"] and candidate.official_metrics:
            check_result = self._check_before_submit(candidate)
            if not check_result["passed"]:
                for err in check_result["failed_checks"]:
                    failed.append(f"BRAIN_CHECK_GATE:{err['name']}:{err['message']}")
                safety["allowed"] = False
                safety["status"] = "BLOCK"
            safety["alpha_check_gate"] = check_result
        safety["cloud_sync"] = dict(self.cloud_sync)
        safety["cloud_status"] = cloud_alpha_status
        safety["cloud_correlation_risk"] = cloud_risk
        return safety
