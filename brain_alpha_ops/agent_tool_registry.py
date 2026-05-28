"""Tool registry for agent, MCP, and web assistant integrations.

The registry keeps tool metadata separate from the callable toolbox so every
protocol surface exposes the same safe whitelist and aliases.
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


def build_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            "list_context",
            "List local official fields, operators, and datasets available to the research engine.",
            _schema({"query": "string", "limit": "integer"}),
            category="data",
            chain_stage="context",
        )
    )
    registry.register(
        ToolDefinition(
            "generate_candidates",
            "Generate candidate FASTEXPR alpha expressions without calling the official API; local research memory guidance is enabled by default and optional assistant guidance can bias the local generator.",
            _schema({
                "count": "integer",
                "dataset_id": "string",
                "use_research_memory": "boolean",
                "top_n": "integer",
                "min_success_rate": "number",
                "assistant_response": "string",
                "assistant_raw_output": "string",
                "assistant_guidance": "object",
                "assistant_min_confidence": "number",
            }),
            category="research",
            chain_stage="generate",
        )
    )
    registry.register(
        ToolDefinition(
            "validate_expression",
            "Validate a FASTEXPR expression locally, optionally with the configured BRAIN API.",
            _schema({"expression": "string", "use_api": "boolean", "confirm_live_api": "boolean"}),
            live_api=True,
            category="validation",
            chain_stage="validate",
        )
    )
    registry.register(
        ToolDefinition(
            "score_candidate",
            "Compute local scorecard and gate-oriented diagnostics for one expression.",
            _schema({"expression": "string", "family": "string", "hypothesis": "string", "official_metrics": "object"}),
            category="scoring",
            chain_stage="screen",
        )
    )
    registry.register(
        ToolDefinition(
            "run_simulation",
            "Submit one expression to the configured simulation API and fetch the result when completed.",
            _schema({"expression": "string", "max_polls": "integer", "confirm_live_api": "boolean"}),
            live_api=True,
            category="backtest",
            chain_stage="deep_validate",
        )
    )
    registry.register(
        ToolDefinition(
            "run_simulation_batch",
            "Run a bounded batch of configured BRAIN simulations with per-expression validation, duplicate preflight, live API confirmation, and optional limited parallelism.",
            _schema(
                {
                    "expressions": "array",
                    "max_polls": "integer",
                    "max_batch_size": "integer",
                    "max_workers": "integer",
                    "confirm_live_api": "boolean",
                },
                required=["expressions"],
            ),
            live_api=True,
            category="backtest",
            chain_stage="deep_validate",
        )
    )
    registry.register(
        ToolDefinition(
            "check_alpha",
            "Run the configured alpha check for an official alpha id.",
            _schema({"alpha_id": "string", "confirm_live_api": "boolean"}),
            live_api=True,
            category="submission",
            chain_stage="pre_submit_check",
        )
    )
    registry.register(
        ToolDefinition(
            "submit_alpha",
            "Submit an official alpha after pre-submit check and explicit confirmation.",
            _schema({"alpha_id": "string", "expression": "string", "confirm_live_api": "boolean", "confirm_submit": "boolean"}),
            live_api=True,
            destructive=True,
            category="submission",
            chain_stage="submit",
        )
    )
    registry.register(
        ToolDefinition(
            "sync_cloud_alphas",
            "Sync user cloud alphas into the local research repository.",
            _schema({"sync_range": "string", "limit": "integer", "confirm_live_api": "boolean"}),
            live_api=True,
            category="data",
            chain_stage="context_refresh",
        )
    )
    registry.register(
        ToolDefinition(
            "get_job_status",
            "Read status from a configured task store.",
            _schema({"kind": "string", "job_id": "string"}),
            category="observability",
            chain_stage="observe",
        )
    )
    registry.register(
        ToolDefinition(
            "query_research_memory",
            "Summarize local research memory: fields, operators, failures, hypotheses, and lineage.",
            _schema({"limit": "integer", "top_n": "integer", "persist": "boolean"}),
            category="memory",
            chain_stage="context",
        )
    )
    registry.register(
        ToolDefinition(
            "query_expression_index",
            "Summarize or look up persisted FASTEXPR history by canonical fingerprint and semantic similarity.",
            _schema({"expression": "string", "limit": "integer", "top_n": "integer", "include_cloud": "boolean", "min_similarity": "number"}),
            category="memory",
            chain_stage="novelty_check",
        )
    )
    registry.register(
        ToolDefinition(
            "query_research_observability",
            "Summarize local research health: expression reuse, backtest failures, retryable errors, official-call guard blocks, and JSONL/cache status.",
            _schema({"limit": "integer", "top_n": "integer", "include_cloud": "boolean"}),
            category="observability",
            chain_stage="observe",
        )
    )
    registry.register(
        ToolDefinition(
            "build_market_data_cache",
            "Refresh or summarize the lightweight local market-data cache used by research screening and search helpers.",
            _schema({"source_file": "string", "limit": "integer", "refresh": "boolean"}),
            category="data",
            chain_stage="context_refresh",
        )
    )
    registry.register(
        ToolDefinition(
            "build_vectorized_market_data",
            "Build a bounded symbol-by-feature matrix from the local market-data cache for vector-style screening.",
            _schema({"fields": "array", "limit_symbols": "integer", "min_field_coverage": "number", "normalize": "boolean"}),
            category="data",
            chain_stage="vectorize",
        )
    )
    registry.register(
        ToolDefinition(
            "search_parameters",
            "Run a bounded local parameter search over a candidate using diagnostics-guided mutations.",
            _schema({"candidate": "object", "max_mutations": "integer"}, required=["candidate"]),
            category="optimization",
            chain_stage="search",
        )
    )
    registry.register(
        ToolDefinition(
            "orchestrate_parameter_search",
            "Run a multi-round bounded local parameter-search workflow with explicit mutation and keep-top budgets.",
            _schema({"candidate": "object", "rounds": "integer", "max_mutations": "integer", "keep_top": "integer"}, required=["candidate"]),
            category="optimization",
            chain_stage="search",
        )
    )
    registry.register(
        ToolDefinition(
            "plan_parallel_backtest",
            "Plan a capacity-limited full-market backtest schedule with rate-limit and account-safety metadata.",
            _schema({"expressions": "array", "markets": "array", "max_workers": "integer", "max_batches": "integer", "per_account_limit": "integer"}, required=["expressions"]),
            category="backtest",
            chain_stage="plan",
        )
    )
    registry.register(
        ToolDefinition(
            "run_parallel_backtest",
            "Execute a capacity-limited multi-market simulation batch with per-job validation, duplicate preflight, failure accounting, and rate-limit metadata.",
            _schema(
                {
                    "expressions": "array",
                    "markets": "array",
                    "max_workers": "integer",
                    "max_batches": "integer",
                    "per_account_limit": "integer",
                    "confirm_live_api": "boolean",
                },
                required=["expressions"],
            ),
            live_api=True,
            category="backtest",
            chain_stage="deep_validate",
        )
    )
    registry.register(
        ToolDefinition(
            "send_alert",
            "Emit a local or webhook alert for observability and operator notifications.",
            _schema({"title": "string", "message": "string", "severity": "string", "channel": "string", "webhook_url": "string", "metadata": "object"}),
            category="observability",
            chain_stage="alert",
        )
    )
    registry.register(
        ToolDefinition(
            "route_alert",
            "Route an alert through one or more configured local/webhook/callback channels.",
            _schema({"title": "string", "message": "string", "severity": "string", "channels": "array", "routes": "object"}),
            category="observability",
            chain_stage="alert",
        )
    )
    registry.register(
        ToolDefinition(
            "build_assistant_context",
            "Build an LLM-ready context pack from run config, latest local results, cloud cache, and research memory guidance.",
            _schema({"limit": "integer", "top_n": "integer", "include_prompt": "boolean"}),
            category="llm",
            chain_stage="context",
        )
    )
    registry.register(
        ToolDefinition(
            "build_assistant_request",
            "Build a provider-neutral LLM request envelope with response schema and offline fallback draft.",
            _schema({"limit": "integer", "top_n": "integer", "include_prompt": "boolean", "include_offline_draft": "boolean"}),
            category="llm",
            chain_stage="prompt",
        )
    )
    registry.register(
        ToolDefinition(
            "parse_assistant_response",
            "Parse and normalize a JSON response returned by an external assistant model.",
            _schema({"raw_output": "string"}),
            category="llm",
            chain_stage="parse",
        )
    )
    registry.register(
        ToolDefinition(
            "assistant_response_guidance",
            "Convert an assistant model response into generator-ready fields, operators, windows, and operational flags.",
            _schema({"raw_output": "string", "min_confidence": "number"}),
            category="llm",
            chain_stage="guide",
        )
    )
    registry.register(
        ToolDefinition(
            "run_anti_overfit",
            "Run deterministic anti-overfit checks for a candidate payload.",
            _schema({"candidate": "object"}, required=["candidate"]),
            category="validation",
            chain_stage="robustness",
        )
    )
    registry.register(
        ToolDefinition(
            "run_rolling_validation",
            "Run rolling validation checks for a candidate payload.",
            _schema({"candidate": "object", "windows": "integer"}, required=["candidate"]),
            category="validation",
            chain_stage="robustness",
        )
    )
    registry.register(
        ToolDefinition(
            "cross_review_assistant_response",
            "Cross-review a primary assistant response against an assistant request pack.",
            _schema(
                {"request_pack": "object", "primary_response": "string", "reviewer_response": "string", "min_confidence": "number"},
                required=["request_pack", "primary_response"],
            ),
            category="llm",
            chain_stage="review",
        )
    )
    registry.register_alias(
        "score_factor",
        "score_candidate",
        description="QuantGPT-style alias for the lightweight scorecard step; use this before spending live API/backtest budget.",
        category="scoring",
        chain_stage="screen",
    )
    registry.register_alias(
        "run_backtest",
        "run_simulation",
        description="QuantGPT-style alias for the configured BRAIN simulation/backtest workflow; requires live API confirmation.",
        category="backtest",
        chain_stage="deep_validate",
    )
    registry.register_alias(
        "run_batch_backtest",
        "run_simulation_batch",
        description="QuantGPT-style alias for a bounded batch of configured BRAIN simulations; requires the same live API confirmation and budget discipline as run_backtest.",
        category="backtest",
        chain_stage="deep_validate",
    )
    return registry


_DEFAULT_TOOL_REGISTRY = build_default_tool_registry()


def default_tool_registry() -> ToolRegistry:
    return _DEFAULT_TOOL_REGISTRY


def tool_definitions() -> list[ToolDefinition]:
    return default_tool_registry().list_tools()


def resolve_tool_name(name: str) -> str:
    return default_tool_registry().resolve(name)


def tool_aliases() -> dict[str, str]:
    return default_tool_registry().aliases
