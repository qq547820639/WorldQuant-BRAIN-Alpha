"""Structured three-layer knowledge base for cross-session research continuity.

Replaces the flat JSONL ResearchMemory model with a layered approach inspired by
QuantGPT's rules/findings/failures design.  Each layer has a distinct lifecycle:

  Layer 1 — rules/     : Verified stable rules (MUST follow).
  Layer 2 — findings/  : Empirical discoveries (reference).
  Layer 3 — failures/  : Disproven paths (MUST NOT repeat).

Knowledge is persisted as individual structured files under each directory,
making it human-readable, git-diffable, and easily auditable.

P3-2: per-instance ``threading.RLock`` guards every write method
(``save`` / ``delete`` / ``touch`` / ``extract_from_memory``).  Reads
remain lock-free so the assistant UI and pipeline reads are unaffected.

This package re-exports the public API previously provided by the flat
``knowledge_base.py`` module so existing imports continue to work.
"""
from __future__ import annotations

from ._types import (
    KB_SCHEMA_VERSION,
    RESEARCH_KNOWLEDGE_SCHEMA_VERSION,
    RESEARCH_KNOWLEDGE_SUMMARY_VERSION,
    RULE_CATEGORIES,
    FINDING_CATEGORIES,
    FAILURE_CATEGORIES,
    _RESEARCH_KIND_TO_LAYER,
    _LAYER_TO_RESEARCH_KIND,
    _DEFAULT_CATEGORY_BY_KIND,
    KnowledgeRecord,
    KnowledgeEntry,
    _compute_entry_id,
    _bounded_confidence,
    _stringify_evidence,
    _knowledge_record_from_input,
)
from ._structured import (
    StructuredKnowledgeBase,
    _classify_failure_category,
)
from ._base import (
    ResearchKnowledgeBase,
    integrate_knowledge_base_with_memory,
)

__all__ = [
    # Schema constants
    "KB_SCHEMA_VERSION",
    "RESEARCH_KNOWLEDGE_SCHEMA_VERSION",
    "RESEARCH_KNOWLEDGE_SUMMARY_VERSION",
    "RULE_CATEGORIES",
    "FINDING_CATEGORIES",
    "FAILURE_CATEGORIES",
    "_RESEARCH_KIND_TO_LAYER",
    "_LAYER_TO_RESEARCH_KIND",
    "_DEFAULT_CATEGORY_BY_KIND",
    # Dataclasses
    "KnowledgeRecord",
    "KnowledgeEntry",
    # Bases
    "StructuredKnowledgeBase",
    "ResearchKnowledgeBase",
    # Helpers / functions
    "integrate_knowledge_base_with_memory",
    "_compute_entry_id",
    "_bounded_confidence",
    "_stringify_evidence",
    "_knowledge_record_from_input",
    "_classify_failure_category",
]
