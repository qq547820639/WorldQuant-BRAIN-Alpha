"""Account-safety controls for submissions."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
import re

from brain_alpha_ops.config import SubmissionPolicy
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.contracts import correlation_id
from brain_alpha_ops.research.expression_ast import expression_key, expression_profile_summary, expression_similarity, lexical_normalize


class SubmissionLedger:
    def __init__(self, storage_dir: str = "data"):
        self.path = os.path.join(storage_dir, "submissions.jsonl")

    def assess(
        self,
        candidate: Candidate,
        policy: SubmissionPolicy,
        *,
        mode: str,
        run_submission_count: int = 0,
    ) -> dict:
        records = self.records()
        checks = []

        def add(name: str, passed: bool, detail: str):
            checks.append({"name": name, "passed": bool(passed), "detail": detail})

        today = datetime.now(timezone.utc).date()
        today_count = sum(1 for record in records if _date(record) == today and record.get("status") == "SUBMITTED")
        add("daily_auto_submission_limit", today_count < policy.max_auto_submissions_per_day, f"{today_count}/{policy.max_auto_submissions_per_day} today")
        if mode == "auto":
            add("run_auto_submission_limit", run_submission_count < policy.max_auto_submissions_per_run, f"{run_submission_count}/{policy.max_auto_submissions_per_run} this run")
            last_auto = _last_auto(records)
            if last_auto:
                minutes = (datetime.now(timezone.utc) - _time(last_auto)).total_seconds() / 60
                add("minimum_auto_submit_interval", minutes >= policy.min_minutes_between_auto_submissions, f"{minutes:.1f} minutes since last auto submit")

        if not candidate.gate.get("submission_ready"):
            add("production_gate", False, "candidate is not submission-ready")
        account_risk = account_risk_level(candidate)
        add("account_risk_low", account_risk == "low", f"risk={account_risk}")

        official_alpha_id = candidate.official_alpha_id or candidate.official_metrics.get("official_alpha_id", "")
        add("official_alpha_id_present", bool(official_alpha_id), "official alpha id required")
        duplicate_id = any(record.get("official_alpha_id") == official_alpha_id for record in records if official_alpha_id)
        add("duplicate_official_alpha_id", not duplicate_id, "already submitted" if duplicate_id else "new id")

        candidate_key = expression_key(candidate.expression)
        duplicate_expr = any(expression_key(record.get("expression", "")) == candidate_key for record in records)
        add("duplicate_expression", not duplicate_expr, "already submitted" if duplicate_expr else "new expression")

        if policy.block_micro_variants:
            closest = max((similarity(candidate.expression, record.get("expression", "")) for record in records), default=0.0)
            add("micro_variant_similarity", closest < policy.max_expression_similarity, f"closest={closest:.3f}; limit={policy.max_expression_similarity:.3f}")

        failed = [check["detail"] for check in checks if not check["passed"]]
        return {
            "schema_version": "submission-safety-v2.1",
            "mode": mode,
            "allowed": not failed,
            "status": "ALLOW" if not failed else "BLOCK",
            "risk_level": account_risk,
            "failed_reasons": failed,
            "checks": checks,
            "policy": asdict(policy),
        }

    def record(self, candidate: Candidate, submission: dict, *, mode: str):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        record = {
            "schema_version": "submission_record.v1",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "status": str(submission.get("status", "SUBMITTED")).upper(),
            "alpha_id": candidate.alpha_id,
            "official_alpha_id": candidate.official_alpha_id or candidate.official_metrics.get("official_alpha_id", ""),
            "expression": candidate.expression,
            "family": candidate.family,
        }
        record["correlation_id"] = correlation_id(
            run_id="",
            alpha_id=record["alpha_id"],
            simulation_id=candidate.simulation_id,
            phase=f"submission:{mode}",
        )
        record.update(expression_profile_summary(candidate.expression))
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        try:
            from brain_alpha_ops.research.expression_sqlite_index import ExpressionSqliteIndex

            ExpressionSqliteIndex(os.path.dirname(self.path)).append_record(record, source_file="submissions.jsonl")
        except ImportError:
            import logging
            logging.getLogger(__name__).debug(
                "ExpressionSqliteIndex not available; submission record not indexed in SQLite.",
            )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "Failed to index submission record in SQLite index: %s", exc,
            )

    def records(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        records = []
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return records


def account_risk_level(candidate: Candidate) -> str:
    metrics = candidate.official_metrics or {}
    if not metrics:
        return "high"
    if candidate.gate.get("failed_reasons"):
        return "high"
    correlation = _ratio(metrics.get("correlation"))
    concentration = _ratio(metrics.get("weight_concentration"))
    turnover = _ratio(metrics.get("turnover"))
    # Aligned with BRAIN official: correlation < 0.70, concentration <= 0.10, turnover > 1%
    if correlation >= 0.70 or concentration >= 0.10 or turnover < 0.01:
        return "medium"
    return "low"


def normalize(expression: str) -> str:
    return lexical_normalize(expression)


def similarity(left: str, right: str) -> float:
    return expression_similarity(left, right)


NON_PRODUCTION_SOURCE_VALUES = {
    "mock",
    "demo",
    "dry-run",
    "dry_run",
    "dryrun",
    "test",
    "testing",
    "fake",
    "sample",
}
NON_PRODUCTION_ID_PREFIXES = tuple(f"{value}_" for value in NON_PRODUCTION_SOURCE_VALUES) + tuple(
    f"{value}-" for value in NON_PRODUCTION_SOURCE_VALUES
)


def non_production_source_reasons(candidate: Candidate | dict[str, object]) -> list[str]:
    """Return reasons a candidate should be blocked from production submission."""
    data = candidate if isinstance(candidate, dict) else candidate.__dict__
    reasons: list[str] = []
    alpha_id = str(data.get("alpha_id") or "").strip()
    official_alpha_id = str(data.get("official_alpha_id") or "").strip()
    simulation_id = str(data.get("simulation_id") or "").strip()
    source_tags = [str(tag).strip().lower() for tag in (data.get("source_tags") or []) if str(tag).strip()]

    for label, value in (("alpha_id", alpha_id), ("official_alpha_id", official_alpha_id), ("simulation_id", simulation_id)):
        if looks_non_production_identifier(value):
            reasons.append(f"{label} is a non-production identifier")

    if any(tag in NON_PRODUCTION_SOURCE_VALUES for tag in source_tags):
        reasons.append("source_tags include non-production markers")

    if str(data.get("source") or "").strip().lower() in NON_PRODUCTION_SOURCE_VALUES:
        reasons.append("source indicates non-production content")
    if str(data.get("environment") or "").strip().lower() != "production" and str(data.get("environment") or "").strip():
        reasons.append("environment is not production")
    if str(data.get("mode") or "").strip().lower() in NON_PRODUCTION_SOURCE_VALUES:
        reasons.append("mode is not production")
    return reasons


def _ratio(value) -> float:
    try:
        numeric = float(value or 0.0)
    except (TypeError, ValueError):
        numeric = 0.0
    return numeric / 100.0 if abs(numeric) > 1.0 else numeric


def _time(record: dict) -> datetime:
    try:
        parsed = datetime.fromisoformat(record.get("timestamp", ""))
    except ValueError:
        parsed = datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _date(record: dict):
    return _time(record).astimezone().date()


def _last_auto(records: list[dict]) -> dict | None:
    auto = [record for record in records if record.get("mode") == "auto"]
    return max(auto, key=_time) if auto else None


def looks_non_production_identifier(value: str) -> bool:
    text = str(value or "").strip().lower()
    return bool(text and (text in NON_PRODUCTION_SOURCE_VALUES or text.startswith(NON_PRODUCTION_ID_PREFIXES)))
