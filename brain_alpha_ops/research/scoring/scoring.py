"""Scorecard assembly, production gate, and confidence estimation.

Merged from the former ``scorecard`` sub-module.  This is the top-level
scoring entry point that orchestrates prior, empirical, and guidance
scoring.  Shared helpers and empirical scoring live in
``scoring_empirical``; prior and guidance scoring live in
``scoring_components``.

Contains ``build_scorecard``, ``submission_checklist``,
``evaluate_quality_gate`` (BRAIN Alpha Check gate), ``_scorecard_settings``,
``decision_band``, ``estimate_score_confidence``, and the schema-version
constants.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from brain_alpha_ops.config import QualityThresholds, ScoringConfig
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research._ratio import _ratio
from brain_alpha_ops.research.scoring_explainability import (
    scorecard_improvement_hints,
    scorecard_top_failures,
)
from brain_alpha_ops.scoring.attribution import build_attribution_tree
from brain_alpha_ops.scoring.shared_scores import normalize_family_label
from brain_alpha_ops.types import ScorecardDict

from brain_alpha_ops.research.scoring.scoring_components import (
    assistant_guidance_score_adjustment,
    local_convergence_score,
    prior_score,
)
from brain_alpha_ops.research.scoring.scoring_empirical import (
    _bounded_score,
    _format_empirical_failure,
    check,
    empirical_score,
)

if TYPE_CHECKING:
    from brain_alpha_ops.research.scoring_params import ScoringParams


SCORECARD_SCHEMA_VERSION = "scorecard-v2.3"
PRODUCTION_GATE_SCHEMA_VERSION = "production-gate-v2.2"


def build_scorecard(
    candidate: Candidate,
    thresholds: QualityThresholds,
    scoring: ScoringConfig | None = None,
    params: "ScoringParams | None" = None,
    settings: dict | None = None,
) -> ScorecardDict:
    prior = prior_score(candidate, weights_override=scoring.prior_weights_override if scoring else None, params=params)
    effective_settings = _scorecard_settings(candidate, settings)
    empirical = empirical_score(candidate.official_metrics, thresholds, settings=effective_settings)
    checklist = submission_checklist(candidate, thresholds)
    base_local_rank_score = local_convergence_score(candidate, prior, scoring=scoring)
    guidance_adjustment = assistant_guidance_score_adjustment(candidate, scoring=scoring)
    local_rank_score = _bounded_score(base_local_rank_score + float(guidance_adjustment.get("adjustment", 0.0) or 0.0))
    official_verified = bool(candidate.official_metrics)

    # Three-layer weights from ScoringConfig, falling back to the original 30/45/25.
    lw = scoring.get_layer_weights() if scoring else {"prior": 0.30, "empirical": 0.45, "checklist": 0.25}
    if official_verified:
        total = _bounded_score(
            lw["prior"] * prior["score"]
            + lw["empirical"] * empirical["score"]
            + lw["checklist"] * checklist["score"]
        )
        score_basis = "official_verified"
    else:
        total = _bounded_score(local_rank_score)
        score_basis = "local_prior"
    scorecard = {
        "schema_version": SCORECARD_SCHEMA_VERSION,
        "total_score": total,
        "decision_band": decision_band(total, empirical.get("hard_gate_failed", False), scoring=scoring),
        "score_basis": score_basis,
        "local_rank_score": local_rank_score,
        "base_local_rank_score": base_local_rank_score,
        "layer_weights": lw,
        "prior": prior,
        "empirical": empirical,
        "submission_checklist": checklist,
        "assistant_guidance_adjustment": {
            **guidance_adjustment,
            "applied_to_total": (not official_verified and float(guidance_adjustment.get("adjustment", 0.0) or 0.0) != 0.0),
        },
        "confidence": estimate_score_confidence({"empirical": empirical, "score_basis": score_basis}) if official_verified else None,
        "calibration": {
            "prior_minus_empirical": round(prior["score"] - empirical["score"], 2)
            if official_verified
            else None,
            "sample_weight": 1.0 if official_verified else 0.25,
            "purpose": "Track whether local priors predict official outcomes over time.",
            "params_used": params is not None,
        },
        "settings_trace": effective_settings,
    }
    scorecard["attribution_tree"] = build_attribution_tree(scorecard).to_dict()
    scorecard["top_failures"] = scorecard_top_failures(scorecard)
    scorecard["improvement_hints"] = scorecard_improvement_hints(scorecard)
    return scorecard


def submission_checklist(candidate: Candidate, thresholds: QualityThresholds) -> dict:
    metrics = candidate.official_metrics or {}
    checks = [
        check("official_metrics_present", bool(metrics), 15, "Official simulation metrics are required."),
        check("official_pass", metrics.get("pass_fail") == "PASS" or not thresholds.require_official_pass, 15, "BRAIN pass/fail result."),
        check("economic_logic", len(candidate.hypothesis) >= 40 or not thresholds.require_economic_logic, 15, "One-sentence economic/behavioral thesis."),
        check("data_delay_conservative", True, 10, "Default settings use Delay 1 unless changed by user."),
        check("local_quality", candidate.local_quality.get("passed", False), 15, "Local prefilter quality."),
        check("self_correlation_proxy", _ratio(metrics.get("correlation"), bounded=True) <= thresholds.max_self_correlation if metrics else False, 20, "Official/local correlation proxy."),
        check(
            "diversity",
            normalize_family_label(candidate.family) != "momentum"
            or "adv20" in candidate.expression
            or "vwap" in candidate.expression,
            10,
            "Avoid plain crowded templates.",
        ),
    ]
    score = _bounded_score(sum(row.get("points", 0) for row in checks if bool(row.get("passed", False))))
    return {"score": score, "items": checks}


def evaluate_quality_gate(
    candidate: Candidate,
    thresholds: QualityThresholds,
    *,
    settings: dict | None = None,
) -> dict:
    if not candidate.scorecard:
        candidate.scorecard = build_scorecard(candidate, thresholds, settings=settings)
    scorecard = candidate.scorecard
    empirical = scorecard["empirical"]
    failed = []
    warnings = []

    # P1-2: Check hard gates first — BRAIN official hard gates are blocking
    if empirical.get("hard_gate_failed"):
        failed.extend(empirical.get("hard_gate_failures", []))
        warnings.append("hard_gate_blocked: BRAIN official checks failed — submission blocked regardless of total score")

    # Collect all remaining failed items (soft indicators + submission checklist)
    for row in empirical.get("items", []):
        if not bool(row.get("passed", False)) and row.get("points", 1) > 0 and not row.get("is_hard_gate"):
            failed.append(_format_empirical_failure(row))
    for row in scorecard["submission_checklist"]["items"]:
        if not bool(row.get("passed", False)):
            failed.append(str(row.get("name", "check")) + ": " + str(row.get("meaning", "")))
    if not candidate.official_metrics:
        failed.append("official_metrics_present: missing official simulation result")

    passed = not failed  # gate passes when no individual checks fail (official Alpha Checks standard)
    if not passed and scorecard["total_score"] >= 70:
        warnings.append("research_candidate_only_not_submission_ready")

    gate = {
        "schema_version": PRODUCTION_GATE_SCHEMA_VERSION,
        "submission_ready": passed,
        "status": "SUBMISSION_READY" if passed else "NEEDS_ITERATION",
        "failed_reasons": failed,
        "warnings": warnings,
        "hard_gate_blocked": empirical.get("hard_gate_failed", False),
        "source_notes": {
            "thresholds": "BRAIN 官方 Alpha Check 标准 (LOW_SHARPE/LOW_FITNESS/HIGH_TURNOVER/CONCENTRATED_WEIGHT/SELF_CORRELATION/LOW_SUB_UNIVERSE_SHARPE)。Drawdown 非 BRAIN 硬性检查。",
            "official_checks": "官方模拟与 alpha check 是提交前必要证据。",
            "hard_gate_policy": "P1-2: BRAIN hard gates (sharpe/fitness/turnover_platform/self_correlation/prod_correlation/weight_concentration/sub_universe_sharpe/turnover_min) are blocking — any failure prevents submission regardless of total score.",
        },
    }
    candidate.gate = gate
    return gate


def _scorecard_settings(candidate: Candidate, explicit: dict | None = None) -> dict:
    """Return the BRAIN settings used for official threshold selection."""
    if isinstance(explicit, dict) and explicit:
        return dict(explicit)
    submission = candidate.submission if isinstance(candidate.submission, dict) else {}
    for key in ("settings", "brain_settings"):
        value = submission.get(key)
        if isinstance(value, dict) and value:
            return dict(value)
    validation = candidate.validation if isinstance(candidate.validation, dict) else {}
    value = validation.get("settings")
    if isinstance(value, dict) and value:
        return dict(value)
    return {}


def decision_band(score: float, hard_gate_failed: bool = False, scoring: ScoringConfig | None = None) -> str:
    if hard_gate_failed:
        return "hard_gate_blocked"
    thresholds = {"submit": 85.0, "optimize": 70.0, "research": 50.0}
    if scoring and isinstance(getattr(scoring, "decision_thresholds", None), dict):
        for key in thresholds:
            value = scoring.decision_thresholds.get(key)
            if isinstance(value, (int, float)):
                thresholds[key] = float(value)
    if score >= thresholds["submit"]:
        return "submit_candidate"
    if score >= thresholds["optimize"]:
        return "optimize_before_submit"
    if score >= thresholds["research"]:
        return "research_only"
    return "abandon_or_rebuild"


# ═══════════════════════════════════════════════════════════════════════
# P2: score confidence estimation from point estimate to interval estimate.
# ═══════════════════════════════════════════════════════════════════════

def estimate_score_confidence(scorecard: dict) -> dict:
    """估算 scorecard total_score 的置信度。

    基于 empirical items 的内部离散度和数据完备性评估评分可靠性。

    返回:
        {
            "confidence_level": "high" | "medium" | "low",
            "item_count": int,
            "passed_count": int,
            "score_variance": float,        # Item score variance.
            "score_dispersion": float,       # Coefficient of variation (std/mean).
            "data_completeness": float,      # Between 0 and 1.
            "interpretation": str,
        }
    """
    empirical = scorecard.get("empirical", {})
    items = empirical.get("items", [])

    if not items:
        return {
            "confidence_level": "low",
            "item_count": 0, "passed_count": 0,
            "score_variance": 0.0, "score_dispersion": 0.0,
            "data_completeness": 0.0,
            "interpretation": "No empirical items — score based on prior only.",
        }

    # Point values for passed score items.
    scores = [row.get("points", 0) for row in items if row.get("passed")]
    n_items = len(scores)
    passed_count = len(scores)
    data_completeness = n_items / max(len(items), 1)

    if n_items < 2:
        confidence_level = "low"
        variance = 0.0
        dispersion = 1.0
    else:
        mean_score = sum(scores) / n_items
        variance = sum((s - mean_score) ** 2 for s in scores) / n_items
        std_dev = variance ** 0.5
        dispersion = std_dev / max(mean_score, 0.01)

        if dispersion < 0.50 and data_completeness > 0.8:
            confidence_level = "high"
        elif dispersion < 0.75:
            confidence_level = "medium"
        else:
            confidence_level = "low"

    # Interpretation.
    if confidence_level == "high":
        interpretation = (
            f"Score estimate is robust: {passed_count}/{len(items)} items passed, "
            f"low dispersion (cv={dispersion:.3f}), near-complete data."
        )
    elif confidence_level == "medium":
        interpretation = (
            f"Score estimate is acceptable: {passed_count}/{len(items)} items passed, "
            f"moderate dispersion (cv={dispersion:.3f}). Consider adding more validation data."
        )
    else:
        interpretation = (
            f"Score estimate is unreliable: {passed_count}/{len(items)} items passed, "
            f"high dispersion (cv={dispersion:.3f}). More official simulation data needed."
        )

    return {
        "confidence_level": confidence_level,
        "item_count": n_items,
        "passed_count": passed_count,
        "score_variance": round(variance, 4),
        "score_dispersion": round(dispersion, 4),
        "data_completeness": round(data_completeness, 4),
        "interpretation": interpretation,
    }
