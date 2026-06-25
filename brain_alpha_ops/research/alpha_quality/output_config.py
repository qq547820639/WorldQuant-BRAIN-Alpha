"""Alpha output configuration builder.

Extracted from the original ``alpha_quality.py`` monolith. Builds the
complete Alpha output parameter plan used by Web generation.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from brain_alpha_ops.config_models import OpsConfig, RunConfig

from .utils import _json_safe, _ops_from_config


def build_alpha_output_config(
    run_config: RunConfig | OpsConfig,
    *,
    dataset_id: str = "",
    generation_args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the complete Alpha output parameter plan used by Web generation."""

    ops_config = _ops_from_config(run_config)
    settings = asdict(ops_config.settings)
    if dataset_id:
        settings["dataset"] = dataset_id
    thresholds = asdict(ops_config.thresholds)
    budget = asdict(ops_config.budget)
    scoring = asdict(ops_config.scoring)
    submission_policy = asdict(ops_config.submission_policy)
    generation_args = dict(generation_args or {})
    return {
        "schema_version": "alpha-output-config-v1",
        "local_only": bool(generation_args.get("local_only", True)),
        "official_api_called": bool(generation_args.get("official_api_called", False)),
        "allow_submit": bool(generation_args.get("allow_submit", False)),
        "alpha_type": settings.get("type", "REGULAR"),
        "dataset_id": settings.get("dataset", ""),
        "settings": _json_safe(settings),
        "platform_payload": _json_safe(ops_config.settings.to_platform_dict()),
        "generation": {
            "requested_count": generation_args.get("count", budget.get("max_candidates_per_cycle")),
            "top_n": generation_args.get("top_n", budget.get("retained_alpha_pool_size")),
            "use_research_memory": bool(generation_args.get("use_research_memory")),
            "min_success_rate": generation_args.get("min_success_rate"),
            "assistant_min_confidence": generation_args.get("assistant_min_confidence"),
            "official_validations_per_cycle": budget.get("max_official_validations_per_cycle"),
            "official_simulations_per_cycle": budget.get("max_official_simulations_per_cycle"),
            "official_concurrent_simulations": budget.get("max_official_concurrent_simulations"),
            "official_backtest_batch_size": budget.get("official_backtest_batch_size"),
            "mode": generation_args.get("mode", "local_candidate_generator"),
        },
        "local_gate": {
            "min_local_quality_score": budget.get("min_local_quality_score"),
            "min_local_quality_score_points": float(budget.get("min_local_quality_score", 0.0) or 0.0) * 10,
            "min_prior_score_for_official_validation": budget.get("min_prior_score_for_official_validation"),
            "min_prior_score_for_official_simulation": budget.get("min_prior_score_for_official_simulation"),
        },
        "official_thresholds": {
            "min_sharpe": thresholds.get("min_sharpe"),
            "min_sharpe_delay0": thresholds.get("min_sharpe_delay0"),
            "min_fitness": thresholds.get("min_fitness"),
            "min_fitness_delay0": thresholds.get("min_fitness_delay0"),
            "min_turnover": thresholds.get("min_turnover"),
            "platform_max_turnover": thresholds.get("platform_max_turnover"),
            "target_max_turnover": thresholds.get("target_max_turnover"),
            "max_self_correlation": thresholds.get("max_self_correlation"),
            "max_prod_correlation": thresholds.get("max_prod_correlation"),
            "max_weight_concentration": thresholds.get("max_weight_concentration"),
            "max_drawdown": thresholds.get("max_drawdown"),
            "min_returns": thresholds.get("min_returns"),
            "min_margin_bps": thresholds.get("min_margin_bps"),
            "require_official_pass": thresholds.get("require_official_pass"),
            "require_official_metrics": thresholds.get("require_official_metrics"),
        },
        "submission_policy": {
            "max_expression_similarity": submission_policy.get("max_expression_similarity"),
            "block_micro_variants": submission_policy.get("block_micro_variants"),
            "require_pre_submit_check_passed": submission_policy.get("require_pre_submit_check_passed"),
            "auto_submit": False,
        },
        "qualified_alpha_definition": {
            "local": [
                "required candidate fields are present",
                "FASTEXPR has balanced parentheses and valid known operator arity",
                "window and score values stay within configured bounds",
                "local quality score reaches the configured threshold",
            ],
            "submission": [
                "real official_alpha_id is present",
                "official simulation metrics are complete",
                "official pass_fail is PASS when required",
                "official metrics meet configured BRAIN thresholds",
                "decision_band is submit_candidate and gate.submission_ready is true",
                "pre-submit check and cloud similarity review remain current before real submit",
            ],
        },
    }
