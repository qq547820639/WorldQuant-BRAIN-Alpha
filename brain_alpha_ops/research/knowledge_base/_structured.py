"""Three-layer structured knowledge base with persistence and querying.

Each entry is stored as a JSON file named ``{entry_id}.json`` under
``{storage_dir}/knowledge/{layer}/{category}/``.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from brain_alpha_ops.redaction import redact_error_message, redact_text
from brain_alpha_ops.research.expression_ast import (
    expression_fingerprint,
)

from ._types import (
    KB_SCHEMA_VERSION,
    RULE_CATEGORIES,
    FINDING_CATEGORIES,
    FAILURE_CATEGORIES,
    KnowledgeEntry,
    _compute_entry_id,
)

logger = logging.getLogger("brain_alpha_ops.research.knowledge_base")


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
        # P3-2: per-instance write lock.  Two concurrent writers (e.g. the
        # pipeline and the assistant thread) used to race on path creation
        # and JSON file overwrite.  Reads remain lock-free.
        self._write_lock = threading.RLock()
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
        with self._write_lock:
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
        with self._write_lock:
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
        with self._write_lock:
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

        # Hold the write lock for the whole batch — prevents two extractors
        # from interleaving their saves (P3-2).
        with self._write_lock:
            return self._extract_from_memory_locked(memory_summary, counts)

    def _extract_from_memory_locked(
        self, memory_summary: dict[str, Any], counts: dict[str, int]
    ) -> dict[str, int]:
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
            logger.warning(
                "knowledge_base: failed to load %s: %s",
                redact_text(path, max_length=180),
                redact_error_message(exc),
            )
            return None


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
