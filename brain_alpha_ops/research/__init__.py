"""Research operations — alpha generation, validation, scoring, and submission."""
from .generator import CandidateGenerator, extract_fields, extract_operators, local_quality
from .theme_engine import DynamicThemeEngine
from .dataset_selector import DatasetSelector
from .alpha_checks import AlphaCheck, AlphaCheckRegistry, CheckResult, CheckReport
from .templates import AlphaTemplate, AlphaTemplateRegistry
from .diagnostics import diagnose, get_mutation_mode
from .experience import record_alpha_result, get_winning_patterns
from .memory import ResearchMemory
from .knowledge_base import KnowledgeRecord, ResearchKnowledgeBase
from .context import build_assistant_context_pack, render_context_prompt
from .assistant import (
    AssistantResponseParseError,
    assistant_response_to_generation_guidance,
    build_assistant_request_pack,
    build_offline_assistant_response,
    parse_assistant_response,
    render_assistant_request_prompt,
)
from .guidance import (
    assistant_guidance_digest,
    assistant_guidance_outcome_status,
    assistant_guidance_scoring_eligibility,
    assistant_guidance_scoring_policy,
    ensure_assistant_guidance_digest,
)
from .expression_index import ExpressionHistoryIndex
from .expression_sqlite_index import ExpressionSqliteIndex
from .expression_engine import ExpressionEngine, validate_expression
from .record_sqlite_index import RecordSqliteIndex
from .anti_overfit import AntiOverfitService
from .rolling_validation import RollingValidationService
from .robustness_policy import RobustnessDecision, RobustnessPolicy
from .llm_review import CrossReviewService, FallbackLLMProvider, LLMProvider, LLMProviderRouter, OpenAICompatibleProvider, PromptRunLedger, StaticLLMProvider
from .generation_phase import GenerationPhaseService
from .official_workflow import OfficialWorkflowService
from .research_cycle_orchestrator import CycleDecision, ResearchCycleOrchestrator
from .dataset_selection import DatasetSelectionResult, DatasetSelectionService
from .experience_feedback import ExperienceFeedbackResult, ExperienceFeedbackService
from .backtest_slots import BacktestSlotManager
from .batch_backtest_coordinator import BacktestBatchPlan, BatchBacktestCoordinator
from .candidate_pool import CandidatePoolService
from .production_context import build_production_context, eligible_strategy_profiles
from .strategy_lifecycle import StrategyLifecyclePlugin, StrategyLifecycleTracker
from .strategy_switch import StrategySwitchService
from .observability import build_research_observability_snapshot, observability_context
from .scoring_params import ScoringParams, DimensionParam
from .auto_calibrator import AutoCalibrator
from .iterative_optimizer import IterativeOptimizer, MutationResult
from . import fusion as alpha_fusion
from .hypothesis_library import (
    HypothesisLibrary,
    Hypothesis,
    ExpressionFamily,
    FieldCategoryDef,
    AdaptationConfig,
    FailureMode,
    Rationale,
    ExperienceWeights,
    GenerationMeta,
)
from .hypothesis_driven_generator import (
    HypothesisDrivenGenerator,
    GenerationModeRouter,
    HypothesisSelector,
    ExpressionFamilySelector,
    FieldSelector,
    ContextAdapter,
)

__all__ = [
    "CandidateGenerator",
    "extract_fields",
    "extract_operators",
    "local_quality",
    "DynamicThemeEngine",
    "DatasetSelector",
    "AlphaCheck",
    "AlphaCheckRegistry",
    "CheckResult",
    "CheckReport",
    "AlphaTemplate",
    "AlphaTemplateRegistry",
    "diagnose",
    "get_mutation_mode",
    "record_alpha_result",
    "get_winning_patterns",
    "ResearchMemory",
    "KnowledgeRecord",
    "ResearchKnowledgeBase",
    "build_assistant_context_pack",
    "render_context_prompt",
    "AssistantResponseParseError",
    "assistant_response_to_generation_guidance",
    "build_assistant_request_pack",
    "build_offline_assistant_response",
    "parse_assistant_response",
    "render_assistant_request_prompt",
    "assistant_guidance_digest",
    "assistant_guidance_outcome_status",
    "assistant_guidance_scoring_eligibility",
    "assistant_guidance_scoring_policy",
    "ensure_assistant_guidance_digest",
    "ExpressionHistoryIndex",
    "ExpressionSqliteIndex",
    "ExpressionEngine",
    "validate_expression",
    "RecordSqliteIndex",
    "AntiOverfitService",
    "RollingValidationService",
    "RobustnessDecision",
    "RobustnessPolicy",
    "CrossReviewService",
    "FallbackLLMProvider",
    "LLMProvider",
    "LLMProviderRouter",
    "OpenAICompatibleProvider",
    "PromptRunLedger",
    "StaticLLMProvider",
    "GenerationPhaseService",
    "OfficialWorkflowService",
    "CycleDecision",
    "ResearchCycleOrchestrator",
    "DatasetSelectionResult",
    "DatasetSelectionService",
    "ExperienceFeedbackResult",
    "ExperienceFeedbackService",
    "BacktestSlotManager",
    "BacktestBatchPlan",
    "BatchBacktestCoordinator",
    "CandidatePoolService",
    "build_production_context",
    "eligible_strategy_profiles",
    "StrategyLifecyclePlugin",
    "StrategyLifecycleTracker",
    "StrategySwitchService",
    "build_research_observability_snapshot",
    "observability_context",
    # P0 modules
    "ScoringParams",
    "DimensionParam",
    "AutoCalibrator",
    "IterativeOptimizer",
    "MutationResult",
    "alpha_fusion",
    # Hypothesis Library
    "HypothesisLibrary",
    "Hypothesis",
    "ExpressionFamily",
    "FieldCategoryDef",
    "AdaptationConfig",
    "FailureMode",
    "Rationale",
    "ExperienceWeights",
    "GenerationMeta",
    # HypothesisDrivenGenerator
    "HypothesisDrivenGenerator",
    "GenerationModeRouter",
    "HypothesisSelector",
    "ExpressionFamilySelector",
    "FieldSelector",
    "ContextAdapter",
]
