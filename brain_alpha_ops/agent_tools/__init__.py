"""Whitelisted agent tool facade for Brain Alpha Ops.

Protocol-agnostic: MCP, a web API, or a local assistant can expose these
same tool definitions without letting the model call arbitrary Python code.

Subpackage split (formerly ``agent_tools.py``):
  ``__init__`` re-export shim; ``_helpers`` constants/converters;
  ``_toolbox`` BrainAlphaToolbox core; ``_context_mixin`` / ``_research_mixin``
  / ``_alert_assistant_mixin`` handler mixins.
"""
from __future__ import annotations

from brain_alpha_ops.agent_guidance_tools import (  # noqa: F401
    assistant_guidance_for_generator,
    assistant_guidance_summary,
    attach_assistant_guidance,
    guidance_sample_size,
    has_generator_bias,
    merge_generation_guidance,
)
from brain_alpha_ops.agent_live_tools import AgentLiveToolsMixin  # noqa: F401
from brain_alpha_ops.agent_research_tools import (  # noqa: F401
    assistant_response_guidance_tool,
    build_assistant_context_tool,
    build_assistant_request_tool,
    build_market_data_cache_tool,
    build_vectorized_market_data_from_args,
    collect_job_rows_with_diagnostics,
    cross_review_assistant_response_tool,
    orchestrate_parameter_search_from_args,
    parse_assistant_response_tool,
    plan_parallel_backtest_from_args,
    query_research_observability_snapshot,
    route_alert_from_args,
    run_anti_overfit_tool,
    run_rolling_validation_tool,
    search_parameters_tool,
    send_alert_tool,
)
from brain_alpha_ops.agent_tool_errors import tool_error  # noqa: F401
from brain_alpha_ops.agent_tool_registry import (  # noqa: F401
    resolve_tool_name,
    tool_definitions,
)
from brain_alpha_ops.config import RunConfig, load_run_config  # noqa: F401
from brain_alpha_ops.models import Candidate  # noqa: F401
from brain_alpha_ops.redaction import redact_data, redact_error_message  # noqa: F401
from brain_alpha_ops.research.assistant import (  # noqa: F401
    AssistantResponseParseError,
    assistant_response_to_generation_guidance,
    parse_assistant_response,
)
from brain_alpha_ops.research.expression_ast import expression_key  # noqa: F401
from brain_alpha_ops.research.expression_index import ExpressionHistoryIndex  # noqa: F401
from brain_alpha_ops.research.generator import (  # noqa: F401
    CandidateGenerator,
    extract_fields,
    extract_operators,
)
from brain_alpha_ops.research.guidance import ensure_assistant_guidance_digest  # noqa: F401
from brain_alpha_ops.research.memory import ResearchMemory  # noqa: F401
from brain_alpha_ops.research.observability import (  # noqa: F401
    actionable_duplicate_expression_records,
)
from brain_alpha_ops.research.scoring import build_scorecard  # noqa: F401
from brain_alpha_ops.research.validated_generator import validate_expression as local_validate_expression  # noqa: F401
from brain_alpha_ops.runner import api_from_run_config  # noqa: F401
from brain_alpha_ops.shared_bounds import (  # noqa: F401
    bounded_float,
    bounded_int,
    candidate_argument,
    required_text,
    truthy,
)
from brain_alpha_ops.tasks import JobStore  # noqa: F401

from ._alert_assistant_mixin import _AlertAssistantToolsMixin  # noqa: F401
from ._context_mixin import _ContextToolsMixin  # noqa: F401
from ._helpers import (  # noqa: F401
    MAX_TOOL_CANDIDATES,
    _dataset_to_dict,
    _field_to_dict,
    _operator_to_dict,
    _tool_error,
)
from ._research_mixin import _ResearchToolsMixin  # noqa: F401
from ._toolbox import BrainAlphaToolbox, logger  # noqa: F401

__all__ = [
    "AgentLiveToolsMixin",
    "AssistantResponseParseError",
    "BrainAlphaToolbox",
    "MAX_TOOL_CANDIDATES",
    "RunConfig",
    "load_run_config",
    "logger",
    "tool_error",
]
