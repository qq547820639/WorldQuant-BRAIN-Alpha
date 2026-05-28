"""Structured three-layer knowledge base for cross-session research continuity.

Replaces the flat JSONL ResearchMemory model with a layered approach inspired by
QuantGPT's rules/findings/failures design.  Each layer has a distinct lifecycle:

  Layer 1 — rules/     : Verified stable rules (MUST follow).
  Layer 2 — findings/  : Empirical discoveries (reference).
  Layer 3 — failures/  : Disproven paths (MUST NOT repeat).

Knowledge is persisted as individual structured files under each directory,
making it human-readable, git-diffable, and easily auditable.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from brain_alpha_ops.jsonl import read_jsonl_tail
from brain_alpha_ops.research.expression_ast import (
    expression_fingerprint,
    expression_key,
    expression_profile_summary,
)

logger = logging.getLogger(__name__)

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
    except Exception:
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


class StructuredKnowledgeBase:
    """Three-layer structured knowledge base with persistence and querying.

    Directory layout::

        {storage_dir}/knowledge/
        ├── rules/
        │   ├── field_selection/
        │   ├── operator_usage/
        │   └── ...
        ├── findings/
        │   ├── field_effectiveness/
        │   └── ...
        └── failures/
            ├── overfit/
            ├── collinearity/
            └── ...

    Each entry is stored as a JSON file named ``{entry_id}.json``.
    """

    def __init__(self, storage_dir: str | Path = "data"):
        self.storage_dir = Path(storage_dir)
        self._base = self.storage_dir / "knowledge"
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Create the full three-layer directory tree."""
        layers = {
            "rules": RULE_CATEGORIES,
            "findings": FINDING_CATEGORIES,
            "failures": FAILURE_CATEGORIES,
        }
        for layer, categories in layers.items():
            for category in categories:
                (self._base / layer / category).mkdir(parents=True, exist_ok=True)

    # ── CRUD ──────────────────────────────────────────────────────────────

    def save(self, entry: KnowledgeEntry) -> str:
        """Persist a knowledge entry. Returns the entry_id."""
        entry.updated_at = datetime.now(timezone.utc).isoformat()
        if not entry.entry_id:
            entry.entry_id = _compute_entry_id(entry)
        self._ensure_directories()
        path = self._path_for(entry)
        path.write_text(
            json.dumps(entry.to_dict(), ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        logger.info("knowledge_base: saved %s entry %s (%s/%s)", entry.layer, entry.entry_id, entry.layer, entry.category)
        return entry.entry_id

    def load(self, entry_id: str) -> KnowledgeEntry | None:
        """Load a single knowledge entry by ID."""
        for layer_dir in self._base.iterdir():
            if not layer_dir.is_dir():
                continue
            for category_dir in layer_dir.iterdir():
                if not category_dir.is_dir():
                    continue
                path = category_dir / f"{entry_id}.json"
                if path.is_file():
                    return self._load_file(path)
        return None

    def list_layer(self, layer: str) -> list[KnowledgeEntry]:
        """List all entries in a given layer (rules|findings|failures)."""
        layer_dirs = {"rule": "rules", "finding": "findings", "failure": "failures"}
        dir_name = layer_dirs.get(layer, layer)
        entries = []
        layer_dir = self._base / dir_name
        if not layer_dir.is_dir():
            return entries
        for category_dir in sorted(layer_dir.iterdir()):
            if not category_dir.is_dir():
                continue
            for path in sorted(category_dir.glob("*.json")):
                entry = self._load_file(path)
                if entry:
                    entries.append(entry)
        return entries

    def list_category(self, layer: str, category: str) -> list[KnowledgeEntry]:
        """List all entries in a given layer + category."""
        layer_dirs = {"rule": "rules", "finding": "findings", "failure": "failures"}
        dir_name = layer_dirs.get(layer, layer)
        entries = []
        cat_dir = self._base / dir_name / category
        if not cat_dir.is_dir():
            return entries
        for path in sorted(cat_dir.glob("*.json")):
            entry = self._load_file(path)
            if entry:
                entries.append(entry)
        return entries

    def delete(self, entry_id: str) -> bool:
        """Delete a knowledge entry by ID. Returns True if deleted."""
        for layer_name in ("rules", "findings", "failures"):
            layer_dir = self._base / layer_name
            if not layer_dir.is_dir():
                continue
            for category_dir in layer_dir.iterdir():
                if not category_dir.is_dir():
                    continue
                path = category_dir / f"{entry_id}.json"
                if path.is_file():
                    path.unlink()
                    logger.info("knowledge_base: deleted entry %s", entry_id)
                    return True
        return False

    def touch(self, entry_id: str) -> bool:
        """Increment hit_count and update updated_at for an existing entry."""
        entry = self.load(entry_id)
        if entry is None:
            return False
        entry.hit_count += 1
        self.save(entry)
        return True

    # ── Intelligent knowledge extraction from research records ───────────

    def extract_from_memory(self, memory_summary: dict[str, Any]) -> dict[str, int]:
        """Automatically extract structured knowledge from ResearchMemory summaries.

        Returns a dict mapping layer to count of new entries created.
        """
        counts = {"rules": 0, "findings": 0, "failures": 0}

        # ── Extract rules from high-confidence successful patterns ──
        for family_entry in (memory_summary.get("families") or [])[:10]:
            if family_entry.get("success_rate", 0) >= 0.6 and family_entry.get("count", 0) >= 3:
                kb_entry = KnowledgeEntry(
                    layer="rule",
                    category="expression_structure",
                    title=f"Family {family_entry.get('name', 'unknown')} is a reliable pattern",
                    description=f"Alpha family '{family_entry.get('name')}' consistently produces "
                                f"quality signals (success_rate={family_entry.get('success_rate')}, "
                                f"n={family_entry.get('count')}, "
                                f"avg_score={family_entry.get('avg_score', 0)}).",
                    confidence=family_entry.get("success_rate", 0),
                    source_tags=["auto_extracted", "research_memory"],
                    hit_count=family_entry.get("count", 0),
                )
                self.save(kb_entry)
                counts["rules"] += 1

        # ── Extract findings from field/operator effectiveness ──
        for field_entry in (memory_summary.get("fields") or [])[:15]:
            if field_entry.get("count", 0) >= 2:
                kb_entry = KnowledgeEntry(
                    layer="finding",
                    category="field_effectiveness",
                    title=f"Field '{field_entry.get('name', 'unknown')}' shows promise",
                    description=f"Field '{field_entry.get('name')}' used {field_entry.get('count')} times "
                                f"with success_rate={field_entry.get('success_rate', 0)}, "
                                f"avg_sharpe={field_entry.get('avg_sharpe', 0)}.",
                    confidence=min(0.9, field_entry.get("success_rate", 0) + 0.1),
                    source_tags=["auto_extracted", "research_memory"],
                    fields_involved=[field_entry.get("name", "")],
                )
                self.save(kb_entry)
                counts["findings"] += 1

        for op_entry in (memory_summary.get("operators") or [])[:10]:
            if op_entry.get("count", 0) >= 2:
                kb_entry = KnowledgeEntry(
                    layer="finding",
                    category="operator_effectiveness",
                    title=f"Operator '{op_entry.get('name', 'unknown')}' effective",
                    description=f"Operator '{op_entry.get('name')}' used {op_entry.get('count')} times "
                                f"with success_rate={op_entry.get('success_rate', 0)}.",
                    confidence=min(0.9, op_entry.get("success_rate", 0) + 0.1),
                    source_tags=["auto_extracted", "research_memory"],
                    operators_involved=[op_entry.get("name", "")],
                )
                self.save(kb_entry)
                counts["findings"] += 1

        # ── Extract failures from failure patterns ──
        for fail in (memory_summary.get("failure_patterns") or [])[:10]:
            if fail.get("count", 0) >= 2:
                kb_entry = KnowledgeEntry(
                    layer="failure",
                    category=_classify_failure_category(fail.get("reason", "")),
                    title=f"Avoid: {fail.get('reason', 'unknown failure')}",
                    description=f"Pattern '{fail.get('reason')}' failed {fail.get('count')} times. "
                                f"Investigate alternatives or avoid this pattern.",
                    confidence=min(0.95, 0.5 + fail.get("count", 0) * 0.1),
                    source_tags=["auto_extracted", "research_memory"],
                )
                self.save(kb_entry)
                counts["failures"] += 1

        return counts

    # ── Query helpers ─────────────────────────────────────────────────────

    def find_by_pattern(self, expression: str) -> list[KnowledgeEntry]:
        """Find knowledge entries whose expression_pattern matches the given expression."""
        fingerprint = expression_fingerprint(expression)
        matches = []
        for layer in ("rules", "failures"):
            for entry in self.list_layer(layer):
                if entry.expression_pattern:
                    entry_fp = expression_fingerprint(entry.expression_pattern)
                    if entry_fp == fingerprint:
                        matches.append(entry)
        return matches

    def get_generation_constraints(self) -> dict[str, Any]:
        """Build a constraint dict for CandidateGenerator based on all rules."""
        constraints: dict[str, Any] = {
            "preferred_fields": set(),
            "preferred_operators": set(),
            "forbidden_patterns": [],
            "window_constraints": {},
        }
        for entry in self.list_layer("rules"):
            constraints["preferred_fields"].update(entry.fields_involved)
            constraints["preferred_operators"].update(entry.operators_involved)
        for entry in self.list_layer("failures"):
            if entry.expression_pattern:
                constraints["forbidden_patterns"].append(entry.expression_pattern)
            if entry.title:
                constraints["forbidden_patterns"].append(entry.title)
        return {
            "preferred_fields": sorted(constraints["preferred_fields"]),
            "preferred_operators": sorted(constraints["preferred_operators"]),
            "forbidden_patterns": constraints["forbidden_patterns"],
            "window_constraints": constraints["window_constraints"],
        }

    def summary(self) -> dict[str, Any]:
        """Return a compact summary of the knowledge base state."""
        return {
            "schema_version": KB_SCHEMA_VERSION,
            "rules_count": len(self.list_layer("rules")),
            "findings_count": len(self.list_layer("findings")),
            "failures_count": len(self.list_layer("failures")),
            "rules_by_category": {
                cat: len(self.list_category("rule", cat))
                for cat in sorted(RULE_CATEGORIES)
                if (self._base / "rules" / cat).is_dir()
            },
            "findings_by_category": {
                cat: len(self.list_category("finding", cat))
                for cat in sorted(FINDING_CATEGORIES)
                if (self._base / "findings" / cat).is_dir()
            },
            "failures_by_category": {
                cat: len(self.list_category("failure", cat))
                for cat in sorted(FAILURE_CATEGORIES)
                if (self._base / "failures" / cat).is_dir()
            },
            "storage_path": str(self._base),
        }

    # ── Internals ─────────────────────────────────────────────────────────

    def _path_for(self, entry: KnowledgeEntry) -> Path:
        # Map layer values to directory names
        layer_dirs = {"rule": "rules", "finding": "findings", "failure": "failures"}
        dir_name = layer_dirs.get(entry.layer, entry.layer)
        return self._base / dir_name / entry.category / f"{entry.entry_id}.json"

    @staticmethod
    def _load_file(path: Path) -> KnowledgeEntry | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return KnowledgeEntry(**{
                k: v for k, v in data.items()
                if k in {f.name for f in KnowledgeEntry.__dataclass_fields__.values()}
            })
        except (json.JSONDecodeError, TypeError, OSError) as exc:
            logger.warning("knowledge_base: failed to load %s: %s", path, exc)
            return None


class ResearchKnowledgeBase:
    """Compatibility wrapper for the web-facing research knowledge API."""

    def __init__(self, storage_dir: str | Path = "data"):
        self._structured = StructuredKnowledgeBase(storage_dir)

    def add(self, record: KnowledgeRecord | dict[str, Any]) -> dict[str, Any]:
        item = _knowledge_record_from_input(record)
        kind = item.kind.strip().lower()
        if kind not in _RESEARCH_KIND_TO_LAYER:
            raise ValueError(f"unsupported knowledge kind: {item.kind}")
        now = datetime.now(timezone.utc).isoformat()
        created_at = item.created_at or now
        metadata = dict(item.metadata or {})
        if item.source_run_id:
            metadata["source_run_id"] = item.source_run_id
        if item.evidence:
            metadata["evidence_payload"] = item.evidence
        entry = KnowledgeEntry(
            layer=_RESEARCH_KIND_TO_LAYER[kind],
            category=_DEFAULT_CATEGORY_BY_KIND[kind],
            title=item.title,
            description=item.body,
            evidence=[_stringify_evidence(value) for value in item.evidence],
            confidence=_bounded_confidence(item.confidence),
            source_tags=[str(tag) for tag in item.source_tags if str(tag)],
            expression_pattern=item.expression_pattern,
            fields_involved=[str(field) for field in item.fields_involved if str(field)],
            operators_involved=[str(operator) for operator in item.operators_involved if str(operator)],
            created_at=created_at,
            updated_at=item.updated_at or created_at,
            metadata=metadata,
        )
        entry_id = self._structured.save(entry)
        saved = self._research_dict(entry)
        saved["knowledge_id"] = f"rk_{entry_id}"
        return saved

    def latest(
        self,
        kind: str | None = None,
        *,
        limit: int = 100,
        min_confidence: float = 0.0,
    ) -> list[dict[str, Any]]:
        kinds = [kind.strip().lower()] if kind else list(_RESEARCH_KIND_TO_LAYER)
        rows: list[dict[str, Any]] = []
        threshold = _bounded_confidence(min_confidence)
        for item_kind in kinds:
            if item_kind not in _RESEARCH_KIND_TO_LAYER:
                raise ValueError(f"unsupported knowledge kind: {kind}")
            layer = _RESEARCH_KIND_TO_LAYER[item_kind]
            for entry in self._structured.list_layer(layer):
                if _bounded_confidence(entry.confidence) >= threshold:
                    rows.append(self._research_dict(entry))
        rows.sort(key=lambda row: str(row.get("updated_at") or row.get("created_at") or ""), reverse=True)
        return rows[: max(0, int(limit or 0))]

    def summary(self, *, limit: int = 100, min_confidence: float = 0.0) -> dict[str, Any]:
        items = self.latest(limit=limit, min_confidence=min_confidence)
        counts = {kind: 0 for kind in _RESEARCH_KIND_TO_LAYER}
        for row in items:
            row_kind = str(row.get("kind") or "")
            if row_kind in counts:
                counts[row_kind] += 1
        return {
            "ok": True,
            "schema_version": RESEARCH_KNOWLEDGE_SUMMARY_VERSION,
            "count": len(items),
            "counts": counts,
            "items": items,
            "structured_summary": self._structured.summary(),
        }

    @staticmethod
    def _research_dict(entry: KnowledgeEntry) -> dict[str, Any]:
        kind = _LAYER_TO_RESEARCH_KIND.get(entry.layer, entry.layer)
        source_run_id = ""
        if isinstance(entry.metadata, dict):
            source_run_id = str(entry.metadata.get("source_run_id") or "")
        return {
            "schema_version": RESEARCH_KNOWLEDGE_SCHEMA_VERSION,
            "knowledge_id": f"rk_{entry.entry_id}",
            "entry_id": entry.entry_id,
            "kind": kind,
            "title": entry.title,
            "body": entry.description,
            "confidence": _bounded_confidence(entry.confidence),
            "evidence": list(entry.evidence or []),
            "source_run_id": source_run_id,
            "source_tags": list(entry.source_tags or []),
            "expression_pattern": entry.expression_pattern,
            "fields_involved": list(entry.fields_involved or []),
            "operators_involved": list(entry.operators_involved or []),
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
            "metadata": dict(entry.metadata or {}),
        }


def integrate_knowledge_base_with_memory(
    storage_dir: str | Path,
    memory_summary: dict[str, Any] | None = None,
) -> dict[str, int]:
    """Convenience: extract knowledge from research memory into structured KB.

    If memory_summary is not provided, attempts to load from ResearchMemory.
    """
    kb = StructuredKnowledgeBase(storage_dir)
    if memory_summary is None:
        from brain_alpha_ops.research.memory import ResearchMemory
        memory = ResearchMemory(storage_dir)
        memory_summary = memory.summary()
    return kb.extract_from_memory(memory_summary)


def _classify_failure_category(reason: str) -> str:
    """Map a failure reason string to a failure category."""
    reason_lower = reason.lower()
    if any(kw in reason_lower for kw in ("overfit", "overfit", "low sharpe", "sharpe")):
        return "overfit"
    if any(kw in reason_lower for kw in ("collinear", "correlat", "multicollinear")):
        return "collinearity"
    if any(kw in reason_lower for kw in ("turnover", "high to")):
        return "high_turnover"
    if any(kw in reason_lower for kw in ("self_corr", "self corr", "duplicate", "similar")):
        return "self_correlation"
    if any(kw in reason_lower for kw in ("reject", "check fail", "platform")):
        return "platform_rejection"
    if any(kw in reason_lower for kw in ("low", "poor", "fail", "weak")):
        return "low_signal"
    return "low_signal"
