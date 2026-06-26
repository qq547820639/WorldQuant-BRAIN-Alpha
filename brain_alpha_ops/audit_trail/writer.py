"""Audit trail writer for scoring results, gate decisions, and attribution.

Writes JSONL records to ``data/audit_trail/scoring_audit.jsonl`` with
structured entries covering scoring evaluations, gate decisions, and
attribution breakdowns. Lifecycle/gate/optimization/simulation audit
records live in ``lifecycle_writer.py`` (sibling module).
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from collections.abc import Generator
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

AUDIT_TRAIL_SCHEMA_VERSION = "audit_trail.v1"
_DEFAULT_AUDIT_DIR = "data/audit_trail"
_MAX_ENTRY_SIZE_BYTES = 64 * 1024


@dataclass
class AuditTrailEntry:
    """Single audit trail record for a scoring evaluation."""

    entry_id: str = ""
    alpha_id: str = ""
    expression: str = ""
    event_type: str = ""  # "scoring_evaluated", "gate_decided", "attribution_recorded"
    scoring_version: str = ""
    threshold_version: str = ""
    config_hash: str = ""
    total_score: float = 0.0
    decision_band: str = ""
    passed_gate: bool = False
    evaluated_at: str = ""
    gate_decisions: list[dict[str, Any]] = field(default_factory=list)
    triggered_rules: list[dict[str, Any]] = field(default_factory=list)
    attribution_summary: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class AuditTrailWriter:
    """Thread-safe JSONL audit trail writer for scoring evaluations."""

    def __init__(self, audit_dir: str | Path = _DEFAULT_AUDIT_DIR):
        self._dir = Path(audit_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "scoring_audit.jsonl"
        self._lock = threading.Lock()

    def write_entry(self, entry: AuditTrailEntry) -> None:
        record = entry.to_dict()
        record["schema_version"] = AUDIT_TRAIL_SCHEMA_VERSION
        record["written_at"] = datetime.now(timezone.utc).isoformat()
        line = json.dumps(record, ensure_ascii=False, default=str)
        if len(line.encode("utf-8")) > _MAX_ENTRY_SIZE_BYTES:
            logger.warning(
                "audit_trail: entry for %s exceeds size limit (%d bytes), truncating details",
                entry.alpha_id, len(line.encode("utf-8")),
            )
            record["details"] = {"_truncated": True}
            record["gate_decisions"] = []
            record["triggered_rules"] = []
            line = json.dumps(record, ensure_ascii=False, default=str)
        with self._lock:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

    def read_entries(self, *, alpha_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if not self._path.is_file():
            return []
        entries: list[dict[str, Any]] = []
        with self._lock:
            with open(self._path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if alpha_id and record.get("alpha_id") != alpha_id:
                        continue
                    entries.append(record)
                    if len(entries) >= limit:
                        break
        return list(reversed(entries))

    def entry_count(self) -> int:
        if not self._path.is_file():
            return 0
        with self._lock:
            with open(self._path, "rb") as f:
                count = sum(1 for _ in f)
        return count


def write_scoring_audit(
    scoring_result: Any,
    *,
    audit_dir: str | Path = _DEFAULT_AUDIT_DIR,
    scoring_version: str = "",
    extra_details: dict[str, Any] | None = None,
) -> AuditTrailEntry:
    """Write a complete scoring audit trail entry from a ScoringResult."""
    now = datetime.now(timezone.utc).isoformat()
    alpha_id = getattr(scoring_result, "alpha_id", "")
    expression = getattr(scoring_result, "expression", "")
    gate_decisions = _extract_gate_decisions(scoring_result)
    triggered_rules = _extract_triggered_rules(scoring_result)

    entry = AuditTrailEntry(
        entry_id=_new_entry_id(alpha_id),
        alpha_id=alpha_id,
        expression=expression,
        event_type="scoring_evaluated",
        scoring_version=scoring_version or getattr(scoring_result, "scoring_schema", ""),
        threshold_version=getattr(scoring_result, "threshold_version", ""),
        config_hash=getattr(scoring_result, "config_hash", ""),
        total_score=getattr(scoring_result, "total_score", 0.0),
        decision_band=getattr(scoring_result, "decision_band", ""),
        passed_gate=getattr(scoring_result, "passed_gate", False),
        evaluated_at=getattr(scoring_result, "evaluated_at", now),
        gate_decisions=gate_decisions,
        triggered_rules=triggered_rules,
        attribution_summary=getattr(scoring_result, "attribution_report", lambda: "")() if hasattr(scoring_result, "attribution_report") else "",
        details=extra_details or {},
    )
    _get_writer(audit_dir).write_entry(entry)
    return entry


# --- Singleton cache + helpers ---------------------------------------------

_writer_lock = threading.Lock()
_writer_instances: dict[str, AuditTrailWriter] = {}


def _get_writer(audit_dir: str | Path = _DEFAULT_AUDIT_DIR) -> AuditTrailWriter:
    key = str(Path(audit_dir))
    if key not in _writer_instances:
        with _writer_lock:
            if key not in _writer_instances:
                _writer_instances[key] = AuditTrailWriter(audit_dir)
    return _writer_instances[key]


def _new_entry_id(alpha_id: str) -> str:
    return f"{alpha_id}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:8]}"


def _iter_gates(scoring_result: Any) -> Generator[tuple[str, Any], None, None]:
    for gate in getattr(scoring_result, "hard_gates", []):
        yield "HARD", gate
    for gate in getattr(scoring_result, "soft_gates", []):
        yield "SOFT", gate


def _gate_to_dict(gate: Any) -> dict[str, Any]:
    if hasattr(gate, "to_dict"):
        return gate.to_dict()
    return gate if isinstance(gate, dict) else {}


def _extract_gate_decisions(scoring_result: Any) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    for gate_type, gate in _iter_gates(scoring_result):
        gate_dict = _gate_to_dict(gate)
        decisions.append({
            "gate_name": gate_dict.get("gate_name", ""),
            "passed": gate_dict.get("passed", False),
            "gate_type": gate_type,
            "threshold_source": gate_dict.get("threshold_source", ""),
            "failed_items": gate_dict.get("failed_items", []),
            "check_count": len(gate_dict.get("check_items", [])),
        })
    release = getattr(scoring_result, "release_gate", {})
    if release:
        decisions.append({
            "gate_name": "RELEASE_SCORE_GATE",
            "passed": release.get("pass_fail", False),
            "gate_type": "RELEASE",
            "threshold_source": "BRAIN_Official",
            "status": release.get("status", ""),
            "failed_items": [
                a.get("reason", "")
                for a in release.get("attributions", [])
                if not a.get("passed", True)
            ],
        })
    return decisions


def _extract_triggered_rules(scoring_result: Any) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for gate_type, gate in _iter_gates(scoring_result):
        gate_dict = _gate_to_dict(gate)
        for item in gate_dict.get("check_items", []):
            if not item.get("passed", True):
                rules.append({
                    "gate": gate_dict.get("gate_name", ""),
                    "rule": item.get("name", ""),
                    "gate_type": gate_type,
                    "actual": item.get("actual"),
                    "target": item.get("target"),
                    "direction": item.get("direction", ""),
                    "source": item.get("source", ""),
                })
    for failure in getattr(scoring_result, "top_failures", []):
        if not any(r["rule"] == failure.get("item", "") for r in rules):
            rules.append({
                "gate": "FAILURE_COLLECTION",
                "rule": failure.get("item", ""),
                "gate_type": failure.get("severity", "SOFT"),
                "reason": failure.get("reason", ""),
                "source": failure.get("source", ""),
            })
    return rules
