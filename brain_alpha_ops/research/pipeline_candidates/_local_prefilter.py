"""Local prefilter helpers and mixin for ``PipelineCandidatePoolMixin``.

Extracted from the original ``pipeline_candidates.py`` monolith. Holds the
module-level helpers ``_safe_float`` and ``_local_backtest_failure_category``
plus the ``_LocalPrefilterMixin`` carrying the local scoring, backtest
prefilter, generation-field prefilter, and local-backtest knowledge recording
methods.
"""

from __future__ import annotations

import logging

from brain_alpha_ops.models import Candidate
from brain_alpha_ops.redaction import redact_error_message

from ..field_quality import non_signal_generation_fields
from ..generator import extract_fields, extract_operators, local_quality
from ..knowledge_base import KnowledgeEntry
from ..local_backtest_gate import apply_local_backtest_gate
from ..pipeline_helpers import blocked_gate as _blocked_gate
from ..pipeline_helpers import rank_candidates
from ..scoring import build_scorecard

# Preserve the original ``brain_alpha_ops.research.pipeline_candidates``
# logger name so downstream log filters and test caplog assertions keep
# working after the monolith was split into submodules.
logger = logging.getLogger("brain_alpha_ops.research.pipeline_candidates")


def _local_backtest_failure_category(result: dict) -> str:
    """Classify failed local backtests for generation feedback."""
    turnover = _safe_float(result.get("turnover"))
    if turnover is not None and turnover > 0.70:
        return "high_turnover"
    reasons = " ".join(str(reason).lower() for reason in (result.get("pass_reasons") or []))
    if "turnover" in reasons and "(fail)" in reasons and ("70%" in reasons or "0.70" in reasons):
        return "high_turnover"
    return "low_signal"


def _safe_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


class _LocalPrefilterMixin:
    """Local scoring and prefilter methods for ``PipelineCandidatePoolMixin``."""

    def _local_prefilter(
        self,
        generated: list[Candidate],
        cycle: int,
        fields: list[dict],
        operators: list[dict],
    ) -> list[Candidate]:
        passed = []
        total = len(generated)
        for index, candidate in enumerate(generated, start=1):
            candidate.local_quality = local_quality(candidate, self.config.budget.min_local_quality_score)
            self._apply_local_backtest_prefilter(candidate)
            self._apply_generation_field_prefilter(candidate)
            # P1-15 fix: wrap build_scorecard in try/except so a single
            # scoring failure does not crash the entire prefilter loop.
            try:
                candidate.scorecard = build_scorecard(
                    candidate,
                    self.config.thresholds,
                    self.config.scoring,
                    params=self.auto_calibrator.params,
                )
            except Exception as _score_exc:
                _score_msg = redact_error_message(_score_exc, max_length=200)
                logger.warning("build_scorecard failed: %s", _score_msg)
                candidate.scorecard = {"total_score": 0.0, "error": _score_msg}
                candidate.lifecycle_status = "local_prefilter_rejected"
                candidate.gate = _blocked_gate("SCORING_ERROR", [_score_msg])
                self._event("scoring_failed", _score_msg, candidate.alpha_id, level="WARN")
                continue
            # Item 7: Detect cross-universe expression reuse
            _expr_key = getattr(candidate, "expression", "") or ""
            _cur_ds = getattr(self, "_active_dataset_id", "")
            if _expr_key and _cur_ds and hasattr(self, "_expression_universe_map"):
                _prev_ds = self._expression_universe_map.get(_expr_key)
                if _prev_ds and _prev_ds != _cur_ds:
                    logger.warning(
                        "cross-universe expression detected: %s was previously computed in dataset '%s', "
                        "now in '%s' — same expression across universes may inflate prod_correlation",
                        _expr_key[:80], _prev_ds, _cur_ds,
                    )
                elif not _prev_ds:
                    self._expression_universe_map[_expr_key] = _cur_ds
            candidate.submission["cycle"] = cycle
            context_reasons = self._official_context_reasons(candidate, fields, operators)
            if context_reasons:
                candidate.gate = {
                    "schema_version": "production-gate-v2.1",
                    "submission_ready": False,
                    "status": "OFFICIAL_CONTEXT_WARNING",
                    "failed_reasons": [],
                    "warnings": context_reasons,
                }
                candidate.local_quality.setdefault("warnings", []).extend(context_reasons)
                self._event("official_context_warning", "; ".join(context_reasons), candidate.alpha_id)
            if candidate.local_quality["passed"]:
                candidate.lifecycle_status = "local_prefilter_passed"
                passed.append(candidate)
            else:
                candidate.lifecycle_status = "local_prefilter_rejected"
                candidate.gate = _blocked_gate("LOCAL_PREFILTER_REJECTED", candidate.local_quality["reasons"])
                self._event("local_prefilter_rejected", "; ".join(candidate.local_quality["reasons"]), candidate.alpha_id)
                # P1-7: Feed prod_correlation failures back to hypothesis weights
                _reasons = " ".join(candidate.local_quality.get("reasons", []))
                if "prod_correlation" in _reasons and hasattr(self, "_generator") and hasattr(self._generator, "adjust_hypothesis_weight"):
                    _hyp = getattr(candidate, "hypothesis", "") or ""
                    if _hyp:
                        self._generator.adjust_hypothesis_weight(_hyp, 0.5)
            self._record_lifecycle(candidate, "local_scored", "; ".join(candidate.local_quality.get("reasons", [])))
            visible_candidates = rank_candidates(passed)
            self._progress(
                "local_scoring",
                index,
                total,
                f"本地评价 {index}/{total}：{candidate.alpha_id} = {candidate.scorecard.get('total_score', 0.0):.2f}",
                candidate.alpha_id,
                data={
                    "cycle": cycle,
                    "produced_count": self.produced_count,
                    "candidates": self._candidate_snapshot(visible_candidates, retained=False),
                    "candidate_pool_available_count": len(visible_candidates),
                    "candidate_pool_source_count": len(visible_candidates),
                    "retained_pool_limit": self.config.budget.retained_alpha_pool_size,
                    "local_scored_count": index,
                    "local_scoring_passed_count": len(visible_candidates),
                },
            )
        ranked = rank_candidates(passed)
        self._event("local_candidates_ranked", f"Ranked {len(ranked)} local candidates before official calls.")
        return ranked

    def _apply_local_backtest_prefilter(self, candidate: Candidate) -> None:
        outcome = apply_local_backtest_gate(
            candidate,
            engine=self._local_backtest_engine,
            cache_key=candidate.dataset_id or self._active_dataset_id or "default",
            extract_fields=extract_fields,
            extract_operators=extract_operators,
            reject_unsupported=True,
        )
        if outcome.get("result") is not None:
            self._record_local_backtest_knowledge(candidate, outcome["result"])

    def _apply_generation_field_prefilter(self, candidate: Candidate) -> None:
        non_signal_fields = non_signal_generation_fields(candidate)
        if not non_signal_fields:
            return
        local = dict(candidate.local_quality or {})
        reasons = list(local.get("reasons") or [])
        reason = "non_signal_generation_fields=" + ",".join(non_signal_fields[:8])
        if reason not in reasons:
            reasons.append(reason)
        local["passed"] = False
        local["reasons"] = reasons
        local["score"] = max(0.0, round(float(local.get("score", 0.0) or 0.0) - 8.0, 2))
        local["non_signal_generation_fields"] = non_signal_fields
        candidate.local_quality = local

    def _record_local_backtest_knowledge(self, candidate: Candidate, result: dict) -> None:
        try:
            if not result.get("ok"):
                layer = "failure"
                category = "low_signal"
                title = f"Local backtest error for {candidate.alpha_id}"
            elif result.get("pass_local"):
                layer = "finding"
                category = "field_effectiveness"
                title = f"Local backtest passed for {candidate.alpha_id}"
            else:
                layer = "failure"
                category = _local_backtest_failure_category(result)
                title = f"Local backtest rejected {candidate.alpha_id}"
            entry = KnowledgeEntry(
                layer=layer,
                category=category,
                title=title,
                description=f"Expression {candidate.expression} evaluated locally with status={result.get('ok')} pass_local={result.get('pass_local')}.",
                evidence=[str(result.get("pass_reasons") or result.get("error") or result.get("error_type") or "")],
                confidence=0.8 if result.get("pass_local") else 0.55,
                source_tags=["pipeline", "local_backtest", category],
                expression_pattern=candidate.expression,
                fields_involved=list(candidate.data_fields or []),
                operators_involved=list(candidate.operators or []),
                metadata={
                    "alpha_id": candidate.alpha_id,
                    "dataset_id": candidate.dataset_id,
                    "failure_category": category,
                    "local_backtest": dict(result),
                },
            )
            self._knowledge_base.save(entry)
        except Exception as exc:
            self._event(
                "knowledge_base_write_failed",
                redact_error_message(exc, max_length=160),
                candidate.alpha_id,
                level="WARN",
            )
