"""Knowledge base type definitions, constants, and conversion helpers.

Holds the dataclasses (``KnowledgeRecord``, ``KnowledgeEntry``), the schema
constants, and the helpers that convert/marshal records.  Keeping these in a
leaf module avoids circular imports between ``_base`` and ``_structured``.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

logger = logging.getLogger("brain_alpha_ops.research.knowledge_base")

# ── Schema version for all knowledge entries ──
KB_SCHEMA_VERSION = "knowledge_base.v1"
RESEARCH_KNOWLEDGE_SCHEMA_VERSION = "research_knowledge_record.v1"
RESEARCH_KNOWLEDGE_SUMMARY_VERSION = "research_knowledge_summary.v1"

# ── Allowed categories per layer ──
RULE_CATEGORIES = {
    "field_selection",      # which fields work together
    "operator_usage",       # operator-specific patterns
    "window_selection",     # lookback window conventions
    "neutralization",       # neutralization strategy
    "universe_constraint",  # universe/dataset constraints
    "expression_structure", # nesting, complexity rules
    "submission_safety",    # pre-submit checks
    "correlation_avoidance",# anti-duplicate patterns
}

FINDING_CATEGORIES = {
    "field_effectiveness",  # which fields yield high Sharpe
    "operator_effectiveness",
    "window_effectiveness",
    "combination_synergy",  # field pairs that work well together
    "market_regime",        # regime-specific observations
    "seasonality",          # time-period patterns
    "macro_sensitivity",    # sensitivity to macro conditions
}

FAILURE_CATEGORIES = {
    "overfit",              # overfit expression patterns
    "collinearity",         # multicollinear field combos
    "low_signal",           # persistently low quality
    "platform_rejection",   # consistently rejected by BRAIN
    "high_turnover",        # excessive turnover patterns
    "self_correlation",     # duplicate or near-duplicate
}

_RESEARCH_KIND_TO_LAYER = {
    "rules": "rule",
    "findings": "finding",
    "failures": "failure",
}
_LAYER_TO_RESEARCH_KIND = {value: key for key, value in _RESEARCH_KIND_TO_LAYER.items()}
_DEFAULT_CATEGORY_BY_KIND = {
    "rules": "expression_structure",
    "findings": "field_effectiveness",
    "failures": "low_signal",
}

@dataclass
class KnowledgeRecord:
    """Backward-compatible research knowledge record facade.

    The persisted implementation is ``StructuredKnowledgeBase``.  This record
    keeps the older web/API contract stable while the storage layout remains
    the newer three-layer rules/findings/failures structure.
    """

    kind: str = "findings"
    title: str = ""
    body: str = ""
    confidence: float = 0.0
    evidence: list[Any] = field(default_factory=list)
    source_run_id: str = ""
    source_tags: list[str] = field(default_factory=list)
    expression_pattern: str = ""
    fields_involved: list[str] = field(default_factory=list)
    operators_involved: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class KnowledgeEntry:
    """A single structured knowledge entry in the knowledge base.

    Attributes:
        entry_id: Unique identifier (auto-generated SHA256 hash).
        layer: "rule" | "finding" | "failure".
        category: Category within the layer (see *_CATEGORIES).
        title: Short human-readable title.
        description: Full description of the rule/finding/failure.
        evidence: List of supporting evidence (expression IDs, metrics).
        confidence: 0.0–1.0 confidence score based on evidence strength.
        source_tags: Tags indicating origin (e.g. "assistant_guided", "pipeline").
        expression_pattern: Canonical expression pattern or regex.
        fields_involved: List of data fields involved.
        operators_involved: List of operators involved.
        created_at: ISO 8601 timestamp.
        updated_at: ISO 8601 timestamp.
        hit_count: Number of times this rule has been reinforced/triggered.
        metadata: Arbitrary additional structured data.
    """
    entry_id: str = ""
    layer: str = "finding"
    category: str = "field_effectiveness"
    title: str = ""
    description: str = ""
    evidence: list[str] = field(default_factory=list)
    confidence: float = 0.0
    source_tags: list[str] = field(default_factory=list)
    expression_pattern: str = ""
    fields_involved: list[str] = field(default_factory=list)
    operators_involved: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    hit_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at
        if not self.entry_id:
            self.entry_id = _compute_entry_id(self)

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if k != "entry_id"} | {"entry_id": self.entry_id}

def _compute_entry_id(entry: KnowledgeEntry) -> str:
    payload = json.dumps({
        "layer": entry.layer,
        "category": entry.category,
        "title": entry.title,
        "expression_pattern": entry.expression_pattern,
    }, ensure_ascii=False, sort_keys=True)
    return sha256(payload.encode("utf-8")).hexdigest()[:16]

def _bounded_confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0

def _stringify_evidence(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception as exc:
        logger.exception("knowledge_base: unexpected error")
        logger.warning("knowledge_base: failed to serialize evidence value; using string fallback", exc_info=True)
        return str(value)

def _knowledge_record_from_input(record: KnowledgeRecord | dict[str, Any]) -> KnowledgeRecord:
    if isinstance(record, KnowledgeRecord):
        return record
    if not isinstance(record, dict):
        raise TypeError("knowledge record must be a mapping or KnowledgeRecord")
    evidence = record.get("evidence") or []
    source_tags = record.get("source_tags") or []
    fields_involved = record.get("fields_involved") or []
    operators_involved = record.get("operators_involved") or []
    metadata = record.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {"value": metadata}
    return KnowledgeRecord(
        kind=str(record.get("kind") or "findings"),
        title=str(record.get("title") or ""),
        body=str(record.get("body") or record.get("description") or ""),
        confidence=_bounded_confidence(record.get("confidence")),
        evidence=list(evidence) if isinstance(evidence, list) else [evidence],
        source_run_id=str(record.get("source_run_id") or ""),
        source_tags=[str(tag) for tag in source_tags if str(tag)],
        expression_pattern=str(record.get("expression_pattern") or ""),
        fields_involved=[str(field) for field in fields_involved if str(field)],
        operators_involved=[str(operator) for operator in operators_involved if str(operator)],
        created_at=str(record.get("created_at") or ""),
        updated_at=str(record.get("updated_at") or ""),
        metadata=dict(metadata),
    )
