"""Constants for production defect tracking validation."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT = ROOT / "docs" / "DEFECT_ANALYSIS_REPORT_20260602.md"
DEFAULT_CONFIG = ROOT / "config" / "run_config.json"
DEFAULT_JOBS = ROOT / "data" / "jobs_production.json"
SCHEMA_VERSION = "prod_defect_tracking_check.v1"
REQUIRED_PROD_IDS = tuple(f"PROD-{index:03d}" for index in range(1, 26))
REQUIRED_PROD_007_SNIPPETS = (
    "local_backtest_failed",
    "submission.local_backtest.pass_local=false",
    "official metrics",
    "pass_fail=PASS",
    "decision_band=submit_candidate",
    "不降低",
    "ready_to_submit=false",
    "eligible_count=0",
    "不能声明已有可提交 Alpha",
)
REQUIRED_PROD_012_SNIPPETS = (
    "bad_signal_slots=0",
    "require_official_pass",
    "require_official_metrics",
    "decision_band=submit_candidate",
    "pass_fail=PASS",
    "ready_to_submit=false",
    "eligible_count=0",
    "不能声明已有可提交 Alpha",
)
REQUIRED_PROD_013_SNIPPETS = (
    "std=4",
    "bad_std=[]",
    "不降低",
    "pass_fail=PASS",
    "ready_to_submit=false",
    "eligible_count=0",
    "不能声明已有可提交 Alpha",
)
REQUIRED_PROD_014_SNIPPETS = (
    "official_pass_fail",
    "decision_band_submit_candidate",
    "SUBMITTABLE",
    "BLOCKED",
    "pass_fail=PASS",
    "decision_band=submit_candidate",
    "不降低",
    "ready_to_submit=false",
    "eligible_count=0",
    "不能声明已有可提交 Alpha",
)
REQUIRED_PROD_015_SNIPPETS = (
    "max_generation_attempts=5",
    "GenerationPhaseService",
    "去重后继续补足",
    "requested=30",
    "generated=30",
    "high_similarity_pairs=0",
    "parse_failures=0",
    "submit_candidate",
    "不降低",
    "pass_fail=PASS",
    "ready_to_submit=false",
    "eligible_count=0",
    "不能声明已有可提交 Alpha",
)
REQUIRED_PROD_016_SNIPPETS = (
    "prod_stub_alpha",
    "looks_non_production_alpha_id",
    "non_production_source_reasons",
    "NON_PRODUCTION_ALPHA_ID",
    "non_production_official_alpha_id",
    "stub",
    "本地 stub",
    "fail-closed",
    "不降低",
    "pass_fail=PASS",
    "ready_to_submit=false",
    "eligible_count=0",
    "不能声明已有可提交 Alpha",
)
REQUIRED_PROD_017_SNIPPETS = (
    "_reject_high_cloud_similarity_before_official",
    "HIGH_CLOUD_SIMILARITY_REJECTED",
    "official validation",
    "官方验证",
    "不降低",
    "pass_fail=PASS",
    "ready_to_submit=false",
    "eligible_count=0",
    "不能声明已有可提交 Alpha",
)
REQUIRED_PROD_018_SNIPPETS = (
    "HypothesisDrivenGenerator.generate",
    "duplicate_expression_skipped",
    "requested=30",
    "generated=30",
    "fallback_count=0",
    "submit_candidate",
    "不降低",
    "pass_fail=PASS",
    "ready_to_submit=false",
    "eligible_count=0",
    "不能声明已有可提交 Alpha",
)
REQUIRED_PROD_019_SNIPPETS = (
    "high_turnover",
    "local_backtest_failed",
    "expression_key",
    "expression_fingerprint",
    "expression_similarity",
    "forbidden_patterns",
    "不降低",
    "pass_fail=PASS",
    "ready_to_submit=false",
    "eligible_count=0",
    "不能声明已有可提交 Alpha",
)
REQUIRED_PROD_020_SNIPPETS = (
    "HypothesisDrivenGenerator._expression_forbidden",
    "_generate_bare_fallback",
    "forbidden_patterns",
    "expression_key",
    "expression_fingerprint",
    "expression_similarity",
    "_FORBIDDEN_PATTERN_SIMILARITY_THRESHOLD=0.90",
    "test_generator_knowledge_constraints_block_fallback_fingerprint_and_similarity",
    "不降低",
    "pass_fail=PASS",
    "ready_to_submit=false",
    "eligible_count=0",
    "不能声明已有可提交 Alpha",
)
REQUIRED_PROD_021_SNIPPETS = (
    "candidates_count",
    "candidates_preview",
    "candidates_submission_evidence",
    "candidate_pool_truncated",
    "test_live_submit_readiness_uses_submission_evidence_outside_compacted_preview",
    "test_compact_runtime_result_keeps_submission_evidence_outside_preview",
    "不降低",
    "pass_fail=PASS",
    "ready_to_submit=false",
    "eligible_count=0",
    "不能声明已有可提交 Alpha",
)
REQUIRED_PROD_022_SNIPPETS = (
    "production_gap_summary",
    "official_validation_without_simulation",
    "local_only_candidate_jobs",
    "latest_candidate_local_backtest_failed",
    "latest_candidate_high_cloud_similarity",
    "candidate_family_missing_official_metrics",
    "job_family_blocking_reason_counts",
    "test_live_submit_readiness_reports_production_gap_summary",
    "不降低",
    "pass_fail=PASS",
    "ready_to_submit=false",
    "eligible_count=0",
    "不能声明已有可提交 Alpha",
)
REQUIRED_PROD_023_SNIPPETS = (
    "rank(ts_delta(returns, N))",
    "is_high_turnover_generation_risk",
    "direct_returns_delta_window",
    "test_generation_risk_blocks_direct_returns_delta_without_blocking_other_returns_usage",
    "test_candidate_generator_blocks_direct_returns_delta_risk",
    "test_bare_fallback_deduplicates_single_field_batch",
    "不降低",
    "pass_fail=PASS",
    "ready_to_submit=false",
    "eligible_count=0",
    "不能声明已有可提交 Alpha",
)
REQUIRED_PROD_024_SNIPPETS = (
    "_candidate_submission_audit_evidence",
    "candidates_submission_evidence",
    "auditable candidate",
    "candidate_pool_truncated",
    "test_live_submit_readiness_reports_truncated_candidate_preview_with_incomplete_evidence",
    "test_compact_runtime_result_keeps_submission_evidence_outside_preview",
    "不降低",
    "pass_fail=PASS",
    "ready_to_submit=false",
    "eligible_count=0",
    "不能声明已有可提交 Alpha",
)
REQUIRED_PROD_025_SNIPPETS = (
    "readiness_gate_invariants",
    "missing_official_alpha_id",
    "non_production_official_alpha_id",
    "missing_official_metrics",
    "missing_official_metric_fields",
    "official_pass_fail_not_pass",
    "official_sharpe_below_threshold",
    "official_fitness_below_threshold",
    "official_turnover_above_threshold",
    "official_self_correlation_above_threshold",
    "official_prod_correlation_above_threshold",
    "official_weight_concentration_above_threshold",
    "decision_band_not_submit_candidate",
    "local_backtest_failed",
    "missing_cloud_similarity",
    "high_cloud_similarity",
    "test_live_submit_readiness_requires_official_metrics_above_config_thresholds",
    "test_live_submit_readiness_requires_complete_official_release_metrics",
    "test_prod_defect_tracking_rejects_readiness_gate_invariant_relaxation",
    "不降低",
    "pass_fail=PASS",
    "ready_to_submit=false",
    "eligible_count=0",
    "不能声明已有可提交 Alpha",
)
REQUIRED_VALIDATION_SNIPPETS = (
    "tests/test_hypothesis_driven_generator.py::test_dynamic_theme_generation_seeds_high_structure_templates",
    "tests/test_hypothesis_driven_generator.py tests/test_scoring_gate.py tests/test_official_scoring_system.py",
    "Local non-submit generation probe for `analyst4` / `fundamental6` / `model16` / `news12` / `pv1`",
    "tests/test_generation_phase.py tests/test_budget_and_policy.py",
    "Local non-submit generation refill probe for `analyst4` / `fundamental6` / `model16` / `news12` / `pv1`",
    "scripts/check_live_submit_readiness.py --json",
    "test_generator_retries_after_duplicate_expression_skips",
    "Local non-submit direct generator refill probe",
    "test_live_submit_readiness_blocks_failed_local_backtest",
    "test_pipeline_local_prefilter_rejects_failed_local_backtest",
    "test_forbidden_patterns_block_expression_fingerprint_and_similarity",
    "test_generator_knowledge_constraints_block_fallback_fingerprint_and_similarity",
    "test_live_submit_readiness_uses_submission_evidence_outside_compacted_preview",
    "test_compact_runtime_result_keeps_submission_evidence_outside_preview",
    "test_live_submit_readiness_reports_production_gap_summary",
    "test_generation_risk_blocks_direct_returns_delta_without_blocking_other_returns_usage",
    "test_candidate_generator_blocks_direct_returns_delta_risk",
    "test_live_submit_readiness_reports_truncated_candidate_preview_with_incomplete_evidence",
    "test_prod_defect_tracking_rejects_readiness_gate_invariant_relaxation",
    "test_prod_defect_tracking_rejects_stale_tracker_claimable_evidence",
    "completion_claimable=true",
    "completion_blockers=[]",
)
EXPECTED_THRESHOLDS = {
    "min_sharpe": 1.25,
    "min_fitness": 1.0,
    "platform_max_turnover": 0.70,
    "max_self_correlation": 0.70,
    "require_official_pass": True,
    "require_official_metrics": True,
}
EXPECTED_SUBMISSION_POLICY = {
    "max_expression_similarity": 0.9,
    "require_pre_submit_check_passed": True,
}
EXPECTED_GENERATION_CONFIG = {
    "max_generation_attempts": 5,
}
