"""TypedDict definitions for commonly used dict structures.

These types provide static type checking for dict returns that were
previously untyped dict[str, Any]. Use these to improve IDE support
and catch type errors at development time.
"""

from __future__ import annotations

from typing import Any, TypedDict


class OfficialMetrics(TypedDict, total=False):
    """Metrics returned from BRAIN API simulation/check results."""
    sharpe: float
    fitness: float
    turnover: float
    returns: float
    drawdown: float
    correlation: float
    self_correlation: float
    prod_correlation: float
    weight_concentration: float
    sub_universe_sharpe: float
    margin: float
    alphaSize: int
    subUniverseSize: int
    pass_fail: str
    long_count: int
    short_count: int
    turnover_min: float
    turnover_platform: float
    turnover_quality: float


class ScorecardDict(TypedDict, total=False):
    """Scorecard result from build_scorecard()."""
    schema_version: str
    total_score: float
    decision_band: str
    score_basis: str
    local_rank_score: float
    base_local_rank_score: float
    layer_weights: dict[str, float]
    prior: dict[str, Any]
    empirical: dict[str, Any]
    submission_checklist: dict[str, Any]
    assistant_guidance_adjustment: dict[str, Any]
    confidence: float | None
    calibration: dict[str, Any]
    settings_trace: dict[str, Any]
    attribution_tree: dict[str, Any]
    top_failures: list[dict[str, str]]
    improvement_hints: list[str]


class GateResultDict(TypedDict, total=False):
    """Gate result from GateConfig.evaluate()."""
    gate_name: str
    passed: bool
    check_items: list[dict[str, Any]]
    failed_items: list[str]
    threshold_source: str
    notes: list[str]
    zero_deviation: bool


class BrainAPIResponse(TypedDict, total=False):
    """Standard response from BRAIN API operations."""
    ok: bool
    status: str
    error: str
    error_code: str
    alpha_id: str
    simulation_id: str
    metrics: OfficialMetrics
    raw: dict[str, Any]


class CandidateDict(TypedDict, total=False):
    """Candidate representation as a dict (for serialization)."""
    alpha_id: str
    expression: str
    family: str
    hypothesis: str
    data_fields: list[str]
    operators: list[str]
    source_tags: list[str]
    parent_id: str
    mutation_type: str
    dataset_id: str
    template_source: str
    local_quality: dict[str, Any]
    validation: dict[str, Any]
    simulation_id: str
    official_alpha_id: str
    official_metrics: OfficialMetrics
    scorecard: ScorecardDict
    gate: GateResultDict
    submission: dict[str, Any]
    lifecycle_status: str
    created_at: str


class PipelineSummaryDict(TypedDict, total=False):
    """Pipeline run summary."""
    run_id: str
    total_candidates: int
    submission_ready: int
    auto_submitted: int
    best_score: float
    officially_simulated: int
    official_validation_attempted: int
    official_validation_passed: int


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


class PriorScoreDict(TypedDict, total=False):
    """Prior score result from prior_score()."""
    score: float
    dimensions: dict[str, float]
    weights: dict[str, float]
    items: list[dict[str, Any]]


class EmpiricalScoreDict(TypedDict, total=False):
    """Empirical score result from empirical_score()."""
    score: float
    items: list[dict[str, Any]]
    hard_gate_failed: bool


class ChecklistScoreDict(TypedDict, total=False):
    """Submission checklist score from submission_checklist()."""
    score: float
    items: list[dict[str, Any]]
    passed_count: int
    failed_count: int


class AttributionNodeDict(TypedDict, total=False):
    """Attribution tree node."""
    name: str
    score: float
    weight: float
    contribution: float
    explanation: str
    historical_trend: str
    children: list["AttributionNodeDict"]


class ScoringConfigDict(TypedDict, total=False):
    """Scoring configuration."""
    prior_weight: float
    empirical_weight: float
    checklist_weight: float
    prior_weights_override: dict[str, float]


# ── Research Layer TypedDicts ─────────────────────────────────────────


class GenerationResultDict(TypedDict, total=False):
    """Result from candidate generation."""
    candidates: list[CandidateDict]
    total_generated: int
    duplicates_skipped: int
    expression_diversity_score: float


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
