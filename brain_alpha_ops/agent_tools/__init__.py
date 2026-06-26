"""Whitelisted agent tool facade for Brain Alpha Ops.

Protocol-agnostic: MCP, a web API, or a local assistant can expose these
same tool definitions without letting the model call arbitrary Python code.

Subpackage split (formerly ``agent_tools.py``):
  ``__init__`` re-export shim; ``_helpers`` constants/converters;
  ``_toolbox`` BrainAlphaToolbox core; ``_context_mixin`` / ``_research_mixin``
  / ``_alert_assistant_mixin`` handler mixins.
"""
from __future__ import annotations

from brain_alpha_ops.agent_live_tools import AgentLiveToolsMixin  # noqa: F401
from brain_alpha_ops.agent_tool_errors import tool_error  # noqa: F401
from brain_alpha_ops.config import RunConfig, load_run_config  # noqa: F401
from brain_alpha_ops.research.assistant import AssistantResponseParseError  # noqa: F401
from brain_alpha_ops.research.expression_index import ExpressionHistoryIndex  # noqa: F401
from brain_alpha_ops.research.memory import ResearchMemory  # noqa: F401
from ._helpers import MAX_TOOL_CANDIDATES  # noqa: F401
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
