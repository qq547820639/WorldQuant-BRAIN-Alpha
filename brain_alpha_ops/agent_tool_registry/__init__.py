"""Tool registry for agent, MCP, and web assistant integrations.

The registry keeps tool metadata separate from the callable toolbox so every
protocol surface exposes the same safe whitelist and aliases.

Re-export subpackage. The implementation has been split from the former
``agent_tool_registry.py`` monolith (deep-optimization-phase13, Task A8)
into responsibility-focused submodules. The public API and the private
``_schema`` / ``_DEFAULT_TOOL_REGISTRY`` / ``build_default_tool_registry``
helpers are re-exported here so ``from brain_alpha_ops.agent_tool_registry
import ...`` continues to resolve to this package directory.

The original module created no logger, so no hardcoded logger name is
required by Task A8.
"""

from __future__ import annotations

from ._registry import (
    _DEFAULT_TOOL_REGISTRY,
    build_default_tool_registry,
    default_tool_registry,
    resolve_tool_name,
    tool_aliases,
    tool_definitions,
)
from ._types import ToolDefinition, ToolRegistry, _schema

__all__ = [
    "ToolDefinition",
    "ToolRegistry",
    "build_default_tool_registry",
    "default_tool_registry",
    "tool_definitions",
    "resolve_tool_name",
    "tool_aliases",
]
