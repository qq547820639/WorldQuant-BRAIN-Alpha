"""TypedDict definitions for commonly used dict structures.

These types provide static type checking for dict returns that were
previously untyped dict[str, Any]. Use these to improve IDE support
and catch type errors at development time.
"""

from __future__ import annotations

from typing import Any, TypedDict

try:
    from typing import NotRequired  # Python 3.11+
except ImportError:  # pragma: no cover
    from typing_extensions import NotRequired


class OfficialMetrics(TypedDict):
    """Metrics returned from BRAIN API simulation/check results."""
    sharpe: float
    fitness: NotRequired[float]
    turnover: NotRequired[float]
    returns: NotRequired[float]
    drawdown: NotRequired[float]
    correlation: NotRequired[float]
    self_correlation: NotRequired[float]
    prod_correlation: NotRequired[float]
    weight_concentration: NotRequired[float]
    sub_universe_sharpe: NotRequired[float]
    margin: NotRequired[float]
    alphaSize: NotRequired[int]
    subUniverseSize: NotRequired[int]
    pass_fail: NotRequired[str]
    long_count: NotRequired[int]
    short_count: NotRequired[int]
    turnover_min: NotRequired[float]
    turnover_platform: NotRequired[float]
    turnover_quality: NotRequired[float]


class ScorecardDict(TypedDict):
    """Scorecard result from build_scorecard()."""
    total_score: float
    decision_band: str
    schema_version: NotRequired[str]
    score_basis: NotRequired[str]
    local_rank_score: NotRequired[float]
    base_local_rank_score: NotRequired[float]
    layer_weights: NotRequired[dict[str, float]]
    prior: NotRequired[dict[str, Any]]
    empirical: NotRequired[dict[str, Any]]
    submission_checklist: NotRequired[dict[str, Any]]
    assistant_guidance_adjustment: NotRequired[dict[str, Any]]
    confidence: NotRequired[float | None]
    calibration: NotRequired[dict[str, Any]]
    settings_trace: NotRequired[dict[str, Any]]
    attribution_tree: NotRequired[dict[str, Any]]
    top_failures: NotRequired[list[dict[str, str]]]
    improvement_hints: NotRequired[list[str]]


class GateResultDict(TypedDict):
    """Gate result from GateConfig.evaluate()."""
    gate_name: str
    passed: bool
    check_items: list[dict[str, Any]]
    failed_items: list[str]
    threshold_source: str
    notes: NotRequired[list[str]]
    zero_deviation: NotRequired[bool]


class BrainAPIResponse(TypedDict):
    """Standard response from BRAIN API operations."""
    ok: bool
    status: NotRequired[str]
    error: NotRequired[str]
    error_code: NotRequired[str]
    alpha_id: NotRequired[str]
    simulation_id: NotRequired[str]
    metrics: NotRequired[OfficialMetrics]
    raw: NotRequired[dict[str, Any]]


# ── Candidate Sub-structure TypedDicts ────────────────────────────────


class LocalQualityDict(TypedDict, total=False):
    """Local prefilter quality assessment result."""
    passed: bool
    score: float
    reasons: list[str]
    warnings: list[str]
    local_backtest: dict[str, Any]
    local_backtest_support: dict[str, Any]


class ValidationDict(TypedDict, total=False):
    """Candidate validation result (strategy-switch resets to {})."""
    status: str
    score: float
    details: dict[str, Any]


class QualityDiagnosisDict(TypedDict, total=False):
    """Quality diagnosis for candidate pipeline gating."""
    local_candidate_valid: bool
    submission_ready: bool
    blocking_reasons: list[str]


class SubmissionDict(TypedDict, total=False):
    """Submission tracking data accumulated during the submission pipeline."""
    safety: dict[str, Any]
    cross_review: dict[str, Any]
    live_submit_readiness: dict[str, Any]
    result: dict[str, Any]
    gate_decision: dict[str, Any]
    settings: dict[str, Any]
    backtest_slot: str
    simulation_status: str
    next_poll_at: float
    poll_count: int
    robustness_policy: dict[str, Any]
    anti_overfit_report: dict[str, Any]
    rolling_validation_report: dict[str, Any]
    secondary_fusion_child_id: str


class CandidateDict(TypedDict):
    """Candidate representation as a dict (for serialization)."""
    alpha_id: str
    expression: str
    family: str
    hypothesis: str
    lifecycle_status: str
    data_fields: NotRequired[list[str]]
    operators: NotRequired[list[str]]
    source_tags: NotRequired[list[str]]
    parent_id: NotRequired[str]
    mutation_type: NotRequired[str]
    dataset_id: NotRequired[str]
    template_source: NotRequired[str]
    local_quality: NotRequired[LocalQualityDict]
    validation: NotRequired[ValidationDict]
    simulation_id: NotRequired[str]
    official_alpha_id: NotRequired[str]
    official_metrics: NotRequired[OfficialMetrics]
    scorecard: NotRequired[ScorecardDict]
    gate: NotRequired[GateResultDict]
    submission: NotRequired[SubmissionDict]
    quality_diagnosis: NotRequired[QualityDiagnosisDict]
    created_at: NotRequired[str]


class PipelineSummaryDict(TypedDict):
    """Pipeline run summary."""
    run_id: str
    total_candidates: int
    submission_ready: NotRequired[int]
    auto_submitted: NotRequired[int]
    best_score: NotRequired[float]
    officially_simulated: NotRequired[int]
    official_validation_attempted: NotRequired[int]
    official_validation_passed: NotRequired[int]


class RedlineViolationDict(TypedDict, total=False):
    """Redline violation report entry."""
    redline_id: int
    redline_name: str
    severity: str
    file_path: str
    check_name: str
    actual_value: str
    expected_value: str
    deviation: str
    fix_guidance: str


# ── Web Layer TypedDicts ──────────────────────────────────────────────


class WebRouteResponse(TypedDict, total=False):
    """Standard HTTP response from web handlers."""
    ok: bool
    status: int
    data: dict[str, Any]
    error: str
    error_code: str


class CandidateListResponse(TypedDict, total=False):
    """Response from candidate list endpoints."""
    ok: bool
    candidates: list[CandidateDict]
    total: int
    limit: int
    offset: int


class SimulationJobResponse(TypedDict, total=False):
    """Response from simulation job endpoints."""
    ok: bool
    job_id: str
    status: str
    simulation_id: str
    alpha_id: str
    metrics: OfficialMetrics


class BacktestSlotResponse(TypedDict, total=False):
    """Response from backtest slot endpoints."""
    ok: bool
    slots: list[dict[str, Any]]
    active_count: int
    pending_count: int
    max_slots: int


class CloudSnapshotResponse(TypedDict, total=False):
    """Response from cloud snapshot endpoints."""
    ok: bool
    alphas: list[dict[str, Any]]
    total: int
    last_sync: str


class ConfigResponse(TypedDict, total=False):
    """Response from config endpoints."""
    ok: bool
    config: dict[str, Any]
    schema: dict[str, Any]


class SubmissionReadinessResponse(TypedDict, total=False):
    """Response from submission readiness endpoints."""
    ok: bool
    ready: bool
    blocking_issues: list[dict[str, Any]]
    warnings: list[dict[str, Any]]


class QualityCheckResponse(TypedDict, total=False):
    """Response from quality check endpoints."""
    ok: bool
    passed: bool
    total_score: float
    decision_band: str
    hard_gates: list[GateResultDict]
    soft_gates: list[GateResultDict]
    improvement_hints: list[str]


class SSEEvent(TypedDict, total=False):
    """Server-Sent Event structure."""
    event: str
    data: dict[str, Any]
    timestamp: str


class UserSession(TypedDict, total=False):
    """User session information."""
    session_id: str
    user_id: str
    csrf_token: str
    stream_token: str
    created_at: str
    expires_at: str


# ── Scoring Layer TypedDicts ──────────────────────────────────────────


class PriorScoreDict(TypedDict):
    """Prior score result from prior_score()."""
    score: float
    dimensions: NotRequired[dict[str, float]]
    weights: NotRequired[dict[str, float]]
    items: NotRequired[list[dict[str, Any]]]


class EmpiricalScoreDict(TypedDict):
    """Empirical score result from empirical_score()."""
    score: float
    items: NotRequired[list[dict[str, Any]]]
    hard_gate_failed: NotRequired[bool]


class ChecklistScoreDict(TypedDict):
    """Submission checklist score from submission_checklist()."""
    score: float
    items: NotRequired[list[dict[str, Any]]]
    passed_count: NotRequired[int]
    failed_count: NotRequired[int]


class AttributionNodeDict(TypedDict):
    """Attribution tree node."""
    name: str
    score: float
    weight: NotRequired[float]
    contribution: NotRequired[float]
    explanation: NotRequired[str]
    historical_trend: NotRequired[str]
    children: NotRequired[list["AttributionNodeDict"]]


class ScoringConfigDict(TypedDict, total=False):
    """Scoring configuration."""
    prior_weight: float
    empirical_weight: float
    checklist_weight: float
    prior_weights_override: dict[str, float]


# ── Research Layer TypedDicts ─────────────────────────────────────────


class GenerationResultDict(TypedDict):
    """Result from candidate generation."""
    candidates: list[CandidateDict]
    total_generated: int
    duplicates_skipped: NotRequired[int]
    expression_diversity_score: NotRequired[float]


class ConvergenceSummaryDict(TypedDict, total=False):
    """Convergence tracking summary."""
    sharpe_trend: str
    recent_avg_sharpe: float
    stalled: bool
    stall_cycles: int
    recommendation: str
    cycle_count: int


class PipelineEventDict(TypedDict, total=False):
    """Pipeline event structure."""
    event: str
    message: str
    alpha_id: str
    level: str
    data: dict[str, Any]
    timestamp: str


class BacktestResultDict(TypedDict, total=False):
    """Backtest result structure."""
    ok: bool
    alpha_id: str
    simulation_id: str
    status: str
    metrics: OfficialMetrics
    error: str


class OptimizationResultDict(TypedDict, total=False):
    """Optimization result from iterative optimizer."""
    original_expression: str
    optimized_expression: str
    mutations_applied: list[dict[str, Any]]
    improvement_score: float
    reason: str


# ── Data Layer TypedDicts ─────────────────────────────────────────────


class OfficialFieldDict(TypedDict, total=False):
    """Official field from BRAIN API."""
    id: str
    name: str
    category: str
    delay: int
    coverage: float
    dataset: str
    source: str


class OfficialDatasetDict(TypedDict, total=False):
    """Official dataset from BRAIN API."""
    id: str
    name: str
    field_count: int
    category: str


class OfficialOperatorDict(TypedDict, total=False):
    """Official operator from BRAIN API."""
    name: str
    category: str
    definition: str
    description: str


# ── Configuration TypedDicts ──────────────────────────────────────────
class BrainSettingsDict(TypedDict, total=False):
    """BRAIN platform settings."""
    instrumentType: str
    region: str
    delay: int
    universe: str
    dataset: str
    type: str


class ResearchBudgetDict(TypedDict, total=False):
    """Research budget settings."""
    max_cycles: int
    max_candidates_per_cycle: int
    retained_alpha_pool_size: int
    min_prior_score_for_official_validation: float
    min_prior_score_for_official_simulation: float
    enable_secondary_fusion: bool
    run_forever: bool
    cycle_pause_seconds: float


class QualityThresholdsDict(TypedDict, total=False):
    """Quality threshold settings."""
    min_sharpe: float
    min_fitness: float
    min_turnover: float
    max_turnover: float
    max_self_correlation: float
    max_prod_correlation: float
    max_weight_concentration: float
    min_sub_universe_sharpe: float
