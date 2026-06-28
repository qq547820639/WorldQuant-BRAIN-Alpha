"""Scoring helpers for Web candidate simulation state."""

from __future__ import annotations

import logging
from typing import Any

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.scoring import build_scorecard, evaluate_quality_gate
from brain_alpha_ops.scoring.release_score_gate import evaluate_release_score
from brain_alpha_ops.submission_readiness import missing_official_metric_fields

logger = logging.getLogger(__name__)


def score_simulated_candidate(candidate: dict[str, Any], config: RunConfig) -> dict[str, Any]:
    data = dict(candidate)
    data.setdefault("alpha_id", "")
    data.setdefault("expression", "")
    data.setdefault("family", "")
    data.setdefault("hypothesis", "")
    model = Candidate.from_dict(data)
    model.scorecard = build_scorecard(model, config.ops.thresholds, config.ops.scoring)
    gate = _official_simulation_gate(model, config)
    rescored = model.to_dict()
    merged = dict(candidate)
    for key, value in rescored.items():
        if key != "extra_fields":
            merged[key] = value
    merged["gate"] = gate
    extra_fields = dict(candidate.get("extra_fields") or {})
    for key, value in dict(rescored.get("extra_fields") or {}).items():
        if key not in merged:
            extra_fields[key] = value
    if extra_fields:
        merged["extra_fields"] = extra_fields
    return merged


def _official_simulation_gate(candidate: Candidate, config: RunConfig) -> dict[str, Any]:
    metrics = candidate.official_metrics or {}
    missing_fields = missing_official_metric_fields(metrics) if metrics else []
    pass_fail = str(metrics.get("pass_fail") or "").strip().upper()
    release_gate = (
        evaluate_release_score(
            metrics,
            config.ops.thresholds,
            settings=_candidate_settings(candidate),
        ).to_dict()
        if metrics
        else {}
    )
    if metrics and not missing_fields and pass_fail in {"PASS", "FAIL"} and release_gate.get("status") == "PASS":
        gate = evaluate_quality_gate(
            candidate,
            config.ops.thresholds,
            settings=_candidate_settings(candidate),
        )
        gate["official_release_gate"] = release_gate
        return gate

    failed_reasons: list[str] = []
    if not metrics:
        failed_reasons.append("official_metrics_present: missing official simulation result")
    if missing_fields:
        failed_reasons.append("official_metric_fields_complete: missing " + ", ".join(missing_fields))
    if pass_fail not in {"PASS", "FAIL"}:
        failed_reasons.append("official_pass_fail: missing official pass/fail")
    if release_gate and release_gate.get("status") != "PASS":
        failed_reasons.append(f"official_release_gate: {release_gate.get('status', 'UNKNOWN')}")
    return {
        "schema_version": "production-gate-v2.2",
        "submission_ready": False,
        "status": "NEEDS_ITERATION",
        "failed_reasons": failed_reasons,
        "warnings": ["official_simulation_gate_fail_closed"],
        "hard_gate_blocked": True,
        "official_release_gate": release_gate,
    }


def _candidate_settings(candidate: Candidate) -> dict[str, Any]:
    submission = candidate.submission if isinstance(candidate.submission, dict) else {}
    for key in ("settings", "brain_settings"):
        value = submission.get(key)
        if isinstance(value, dict):
            return value
    output_config = candidate.alpha_output_config if isinstance(candidate.alpha_output_config, dict) else {}
    settings = output_config.get("settings")
    return dict(settings) if isinstance(settings, dict) else {}


def candidate_score(candidate: dict[str, Any]) -> float:
    scorecard = candidate.get("scorecard") if isinstance(candidate.get("scorecard"), dict) else {}
    value = scorecard.get("total_score", candidate.get("score"))
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return score if score == score else 0.0


def default_simulation_dataset(config: RunConfig) -> str:
    try:
        settings = config.ops.settings.to_platform_dict()["settings"]
    except Exception:
        logger.warning(
            "failed to extract settings from config; returning empty dataset",
            exc_info=True,
        )
        return ""
    return str(settings.get("dataset") or "")
