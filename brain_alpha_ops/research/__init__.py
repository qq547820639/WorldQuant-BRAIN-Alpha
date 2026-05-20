"""Research operations: alpha generation, validation, scoring, and submission.

This namespace exposes the historical convenience imports lazily.  Importing a
small submodule such as ``brain_alpha_ops.research.scoring`` should not eagerly
load the whole research stack or optional YAML-backed hypothesis library.
"""

from __future__ import annotations

import importlib
from typing import Any


_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "CandidateGenerator": ("brain_alpha_ops.research.generator", "CandidateGenerator"),
    "extract_fields": ("brain_alpha_ops.research.generator", "extract_fields"),
    "extract_operators": ("brain_alpha_ops.research.generator", "extract_operators"),
    "local_quality": ("brain_alpha_ops.research.generator", "local_quality"),
    "DynamicThemeEngine": ("brain_alpha_ops.research.theme_engine", "DynamicThemeEngine"),
    "DatasetSelector": ("brain_alpha_ops.research.dataset_selector", "DatasetSelector"),
    "AlphaCheck": ("brain_alpha_ops.research.alpha_checks", "AlphaCheck"),
    "AlphaCheckRegistry": ("brain_alpha_ops.research.alpha_checks", "AlphaCheckRegistry"),
    "CheckResult": ("brain_alpha_ops.research.alpha_checks", "CheckResult"),
    "CheckReport": ("brain_alpha_ops.research.alpha_checks", "CheckReport"),
    "AlphaTemplate": ("brain_alpha_ops.research.templates", "AlphaTemplate"),
    "AlphaTemplateRegistry": ("brain_alpha_ops.research.templates", "AlphaTemplateRegistry"),
    "diagnose": ("brain_alpha_ops.research.diagnostics", "diagnose"),
    "get_mutation_mode": ("brain_alpha_ops.research.diagnostics", "get_mutation_mode"),
    "record_alpha_result": ("brain_alpha_ops.research.experience", "record_alpha_result"),
    "get_winning_patterns": ("brain_alpha_ops.research.experience", "get_winning_patterns"),
    "ResearchMemory": ("brain_alpha_ops.research.memory", "ResearchMemory"),
    "KnowledgeRecord": ("brain_alpha_ops.research.knowledge_base", "KnowledgeRecord"),
    "ResearchKnowledgeBase": ("brain_alpha_ops.research.knowledge_base", "ResearchKnowledgeBase"),
    "build_assistant_context_pack": ("brain_alpha_ops.research.context", "build_assistant_context_pack"),
    "render_context_prompt": ("brain_alpha_ops.research.context", "render_context_prompt"),
    "AssistantResponseParseError": ("brain_alpha_ops.research.assistant", "AssistantResponseParseError"),
    "assistant_response_to_generation_guidance": ("brain_alpha_ops.research.assistant", "assistant_response_to_generation_guidance"),
    "build_assistant_request_pack": ("brain_alpha_ops.research.assistant", "build_assistant_request_pack"),
    "build_offline_assistant_response": ("brain_alpha_ops.research.assistant", "build_offline_assistant_response"),
    "parse_assistant_response": ("brain_alpha_ops.research.assistant", "parse_assistant_response"),
    "render_assistant_request_prompt": ("brain_alpha_ops.research.assistant", "render_assistant_request_prompt"),
    "assistant_guidance_digest": ("brain_alpha_ops.research.guidance", "assistant_guidance_digest"),
    "assistant_guidance_outcome_status": ("brain_alpha_ops.research.guidance", "assistant_guidance_outcome_status"),
    "assistant_guidance_scoring_eligibility": ("brain_alpha_ops.research.guidance", "assistant_guidance_scoring_eligibility"),
    "assistant_guidance_scoring_policy": ("brain_alpha_ops.research.guidance", "assistant_guidance_scoring_policy"),
    "ensure_assistant_guidance_digest": ("brain_alpha_ops.research.guidance", "ensure_assistant_guidance_digest"),
    "ExpressionHistoryIndex": ("brain_alpha_ops.research.expression_index", "ExpressionHistoryIndex"),
    "ExpressionSqliteIndex": ("brain_alpha_ops.research.expression_sqlite_index", "ExpressionSqliteIndex"),
    "ExpressionEngine": ("brain_alpha_ops.research.expression_engine", "ExpressionEngine"),
    "validate_expression": ("brain_alpha_ops.research.expression_engine", "validate_expression"),
    "RecordSqliteIndex": ("brain_alpha_ops.research.record_sqlite_index", "RecordSqliteIndex"),
    "AntiOverfitService": ("brain_alpha_ops.research.anti_overfit", "AntiOverfitService"),
    "RollingValidationService": ("brain_alpha_ops.research.rolling_validation", "RollingValidationService"),
    "RobustnessDecision": ("brain_alpha_ops.research.robustness_policy", "RobustnessDecision"),
    "RobustnessPolicy": ("brain_alpha_ops.research.robustness_policy", "RobustnessPolicy"),
    "CrossReviewService": ("brain_alpha_ops.research.llm_review", "CrossReviewService"),
    "FallbackLLMProvider": ("brain_alpha_ops.research.llm_review", "FallbackLLMProvider"),
    "LLMProvider": ("brain_alpha_ops.research.llm_review", "LLMProvider"),
    "LLMProviderRouter": ("brain_alpha_ops.research.llm_review", "LLMProviderRouter"),
    "OpenAICompatibleProvider": ("brain_alpha_ops.research.llm_review", "OpenAICompatibleProvider"),
    "PromptRunLedger": ("brain_alpha_ops.research.llm_review", "PromptRunLedger"),
    "StaticLLMProvider": ("brain_alpha_ops.research.llm_review", "StaticLLMProvider"),
    "GenerationPhaseService": ("brain_alpha_ops.research.generation_phase", "GenerationPhaseService"),
    "OfficialWorkflowService": ("brain_alpha_ops.research.official_workflow", "OfficialWorkflowService"),
    "CycleDecision": ("brain_alpha_ops.research.research_cycle_orchestrator", "CycleDecision"),
    "ResearchCycleOrchestrator": ("brain_alpha_ops.research.research_cycle_orchestrator", "ResearchCycleOrchestrator"),
    "DatasetSelectionResult": ("brain_alpha_ops.research.dataset_selection", "DatasetSelectionResult"),
    "DatasetSelectionService": ("brain_alpha_ops.research.dataset_selection", "DatasetSelectionService"),
    "ExperienceFeedbackResult": ("brain_alpha_ops.research.experience_feedback", "ExperienceFeedbackResult"),
    "ExperienceFeedbackService": ("brain_alpha_ops.research.experience_feedback", "ExperienceFeedbackService"),
    "BacktestSlotManager": ("brain_alpha_ops.research.backtest_slots", "BacktestSlotManager"),
    "BacktestBatchPlan": ("brain_alpha_ops.research.batch_backtest_coordinator", "BacktestBatchPlan"),
    "BatchBacktestCoordinator": ("brain_alpha_ops.research.batch_backtest_coordinator", "BatchBacktestCoordinator"),
    "CandidatePoolService": ("brain_alpha_ops.research.candidate_pool", "CandidatePoolService"),
    "build_production_context": ("brain_alpha_ops.research.production_context", "build_production_context"),
    "eligible_strategy_profiles": ("brain_alpha_ops.research.production_context", "eligible_strategy_profiles"),
    "StrategyLifecyclePlugin": ("brain_alpha_ops.research.strategy_lifecycle", "StrategyLifecyclePlugin"),
    "StrategyLifecycleTracker": ("brain_alpha_ops.research.strategy_lifecycle", "StrategyLifecycleTracker"),
    "StrategySwitchService": ("brain_alpha_ops.research.strategy_switch", "StrategySwitchService"),
    "build_research_observability_snapshot": ("brain_alpha_ops.research.observability", "build_research_observability_snapshot"),
    "observability_context": ("brain_alpha_ops.research.observability", "observability_context"),
    "ScoringParams": ("brain_alpha_ops.research.scoring_params", "ScoringParams"),
    "DimensionParam": ("brain_alpha_ops.research.scoring_params", "DimensionParam"),
    "AutoCalibrator": ("brain_alpha_ops.research.auto_calibrator", "AutoCalibrator"),
    "IterativeOptimizer": ("brain_alpha_ops.research.iterative_optimizer", "IterativeOptimizer"),
    "MutationResult": ("brain_alpha_ops.research.iterative_optimizer", "MutationResult"),
    "HypothesisLibrary": ("brain_alpha_ops.research.hypothesis_library", "HypothesisLibrary"),
    "Hypothesis": ("brain_alpha_ops.research.hypothesis_library", "Hypothesis"),
    "ExpressionFamily": ("brain_alpha_ops.research.hypothesis_library", "ExpressionFamily"),
    "FieldCategoryDef": ("brain_alpha_ops.research.hypothesis_library", "FieldCategoryDef"),
    "AdaptationConfig": ("brain_alpha_ops.research.hypothesis_library", "AdaptationConfig"),
    "FailureMode": ("brain_alpha_ops.research.hypothesis_library", "FailureMode"),
    "Rationale": ("brain_alpha_ops.research.hypothesis_library", "Rationale"),
    "ExperienceWeights": ("brain_alpha_ops.research.hypothesis_library", "ExperienceWeights"),
    "GenerationMeta": ("brain_alpha_ops.research.hypothesis_library", "GenerationMeta"),
    "HypothesisDrivenGenerator": ("brain_alpha_ops.research.hypothesis_driven_generator", "HypothesisDrivenGenerator"),
    "GenerationModeRouter": ("brain_alpha_ops.research.hypothesis_driven_generator", "GenerationModeRouter"),
    "HypothesisSelector": ("brain_alpha_ops.research.hypothesis_driven_generator", "HypothesisSelector"),
    "ExpressionFamilySelector": ("brain_alpha_ops.research.hypothesis_driven_generator", "ExpressionFamilySelector"),
    "FieldSelector": ("brain_alpha_ops.research.hypothesis_driven_generator", "FieldSelector"),
    "ContextAdapter": ("brain_alpha_ops.research.hypothesis_driven_generator", "ContextAdapter"),
}

__all__ = [*_LAZY_EXPORTS, "alpha_fusion"]


def __getattr__(name: str) -> Any:
    if name == "alpha_fusion":
        module = importlib.import_module("brain_alpha_ops.research.fusion")
        globals()[name] = module
        return module
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = target
    module = importlib.import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
