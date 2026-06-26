"""Tool definition dataclass, registry container, and schema helper.

Extracted from the former ``agent_tool_registry.py`` monolith
(deep-optimization-phase13, Task A8) so the metadata shape and the
ordered registry container live separately from the default-tool
builder. The public API is re-exported by the package ``__init__``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    live_api: bool = False
    destructive: bool = False
    alias_for: str = ""
    category: str = "research"
    chain_stage: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ToolRegistry:
    """Ordered, immutable-by-convention registry for safe agent tools."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._aliases: dict[str, str] = {}

    def register(self, definition: ToolDefinition) -> None:
        name = str(definition.name or "").strip()
        if not name:
            raise ValueError("tool name is required")
        if name in self._tools:
            raise ValueError(f"duplicate tool registration: {name}")
        self._tools[name] = definition
        if definition.alias_for:
            self._aliases[name] = definition.alias_for

    def register_alias(
        self,
        name: str,
        target: str,
        *,
        description: str,
        input_schema: dict[str, Any] | None = None,
        category: str | None = None,
        chain_stage: str | None = None,
    ) -> None:
        target_definition = self._tools.get(target)
        if target_definition is None:
            raise ValueError(f"alias target is not registered: {target}")
        self.register(
            ToolDefinition(
                name=name,
                description=description,
                input_schema=input_schema or dict(target_definition.input_schema),
                live_api=target_definition.live_api,
                destructive=target_definition.destructive,
                alias_for=target,
                category=category or target_definition.category,
                chain_stage=chain_stage or target_definition.chain_stage,
            )
        )

    def resolve(self, name: str) -> str:
        key = str(name or "").strip()
        return self._aliases.get(key, key)

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(str(name or "").strip())

    def list_tools(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    @property
    def aliases(self) -> dict[str, str]:
        return dict(self._aliases)


def _schema(properties: dict[str, str], *, required: list[str] | None = None) -> dict[str, Any]:
    required_names = required if required is not None else [name for name in properties if name in {"expression", "alpha_id", "raw_output"}]
    return {
        "type": "object",
        "properties": {name: {"type": kind} for name, kind in properties.items()},
        "required": required_names,
        "additionalProperties": False,
    }
