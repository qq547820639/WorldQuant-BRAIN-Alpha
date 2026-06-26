"""ResearchKnowledgeBase — compatibility wrapper for the web-facing API.

Wraps :class:`StructuredKnowledgeBase` so the older flat-record contract
(``KnowledgeRecord`` in, research-shaped dict out) keeps working for the
web layer and tests.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ._types import (
    RESEARCH_KNOWLEDGE_SCHEMA_VERSION,
    RESEARCH_KNOWLEDGE_SUMMARY_VERSION,
    _RESEARCH_KIND_TO_LAYER,
    _LAYER_TO_RESEARCH_KIND,
    _DEFAULT_CATEGORY_BY_KIND,
    KnowledgeEntry,
    KnowledgeRecord,
    _bounded_confidence,
    _stringify_evidence,
    _knowledge_record_from_input,
)
from ._structured import StructuredKnowledgeBase

logger = logging.getLogger("brain_alpha_ops.research.knowledge_base")


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
        evidence_values = [_stringify_evidence(value) for value in item.evidence]
        if item.source_run_id:
            metadata["source_run_id"] = item.source_run_id
        if item.evidence:
            metadata["evidence_payload"] = evidence_values
        entry = KnowledgeEntry(
            layer=_RESEARCH_KIND_TO_LAYER[kind],
            category=_DEFAULT_CATEGORY_BY_KIND[kind],
            title=item.title,
            description=item.body,
            evidence=evidence_values,
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
