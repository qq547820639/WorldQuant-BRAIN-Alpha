"""Lifecycle audit writer for Workstream B.

Records lifecycle transitions, gate decisions, optimization suggestions,
and simulation writebacks to ``data/audit_trail/lifecycle_audit.jsonl``.
Each record includes: input params, capability_version (lazy), scoring_version,
gate_version, sim_config, result_summary, change_record.
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

LIFECYCLE_AUDIT_SCHEMA_VERSION = "lifecycle_audit.v1"
_DEFAULT_AUDIT_DIR = "data/audit_trail"
_MAX_ENTRY_SIZE_BYTES = 64 * 1024


class LifecycleAuditWriter:
    """Thread-safe JSONL writer for lifecycle/gate/optimization/simulation audit.

    Writes to ``{audit_dir}/lifecycle_audit.jsonl`` (sibling to
    ``scoring_audit.jsonl`` so existing readers remain unaffected).
    """

    def __init__(self, audit_dir: str | Path = _DEFAULT_AUDIT_DIR):
        self._dir = Path(audit_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "lifecycle_audit.jsonl"
        self._lock = threading.Lock()

    def _write(self, record: dict[str, Any]) -> None:
        record["schema_version"] = LIFECYCLE_AUDIT_SCHEMA_VERSION
        record["written_at"] = datetime.now(timezone.utc).isoformat()
        record.setdefault("entry_id", _new_entry_id(record.get("alpha_id", "")))
        line = json.dumps(record, ensure_ascii=False, default=str)
        if len(line.encode("utf-8")) > _MAX_ENTRY_SIZE_BYTES:
            record["context"] = {"_truncated": True}
            record.setdefault("details", {})
            record["details"] = {"_truncated": True}
            line = json.dumps(record, ensure_ascii=False, default=str)
        with self._lock:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

    def record_lifecycle_transition(
        self, *, alpha_id: str, from_state: str, to_state: str,
        reason: str = "", trigger_rule: str = "",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = {
            "event_type": "lifecycle_transition",
            "alpha_id": alpha_id,
            "from_state": from_state,
            "to_state": to_state,
            "reason": reason,
            "trigger_rule": trigger_rule,
            "context": _sanitize(context),
            "capability_version": _capability_version(),
            "scoring_version": _scoring_version(),
            "gate_version": _gate_version(),
            "change_record": {"field": "lifecycle_status", "old": from_state, "new": to_state},
        }
        self._write(record)
        return record

    def record_gate_decision(
        self, *, alpha_id: str, gate_name: str, passed: bool,
        reason: str = "", attribution: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = {
            "event_type": "gate_decision",
            "alpha_id": alpha_id,
            "gate_name": gate_name,
            "passed": bool(passed),
            "reason": reason,
            "attribution": _sanitize(attribution),
            "context": _sanitize(context),
            "capability_version": _capability_version(),
            "scoring_version": _scoring_version(),
            "gate_version": _gate_version(),
            "change_record": {"field": "gate", "gate_name": gate_name, "passed": bool(passed)},
        }
        self._write(record)
        return record

    def record_optimization_suggestion(
        self, *, alpha_id: str, suggestion: str,
        expected_effect: str = "", parent_failure: str = "",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = {
            "event_type": "optimization_suggestion",
            "alpha_id": alpha_id,
            "suggestion": suggestion,
            "expected_effect": expected_effect,
            "parent_failure": parent_failure,
            "context": _sanitize(context),
            "capability_version": _capability_version(),
            "scoring_version": _scoring_version(),
            "gate_version": _gate_version(),
            "change_record": {"field": "optimization", "suggestion": suggestion,
                              "parent_failure": parent_failure},
        }
        self._write(record)
        return record

    def record_simulation_writeback(
        self, *, alpha_id: str, sim_config: dict[str, Any] | None,
        result_summary: dict[str, Any] | None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = {
            "event_type": "simulation_writeback",
            "alpha_id": alpha_id,
            "sim_config": _sanitize(sim_config),
            "result_summary": _sanitize(result_summary),
            "context": _sanitize(context),
            "capability_version": _capability_version(),
            "scoring_version": _scoring_version(),
            "gate_version": _gate_version(),
            "change_record": {"field": "official_metrics", "sim_config": _sanitize(sim_config)},
        }
        self._write(record)
        return record

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

    def iter_all_entries(self) -> list[dict[str, Any]]:
        """Read all entries (no alpha filter) for retrospective queries."""
        if not self._path.is_file():
            return []
        out: list[dict[str, Any]] = []
        with self._lock:
            with open(self._path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return out

    def entry_count(self) -> int:
        if not self._path.is_file():
            return 0
        with self._lock:
            with open(self._path, "rb") as f:
                return sum(1 for _ in f)


# --- Module-level convenience wrappers --------------------------------------

_writer_lock = threading.Lock()
_writer_instances: dict[str, LifecycleAuditWriter] = {}


def _get_lifecycle_writer(audit_dir: str | Path = _DEFAULT_AUDIT_DIR) -> LifecycleAuditWriter:
    key = str(Path(audit_dir))
    if key not in _writer_instances:
        with _writer_lock:
            if key not in _writer_instances:
                _writer_instances[key] = LifecycleAuditWriter(audit_dir)
    return _writer_instances[key]


def record_lifecycle_transition(
    *, alpha_id: str, from_state: str, to_state: str,
    reason: str = "", trigger_rule: str = "",
    context: dict[str, Any] | None = None,
    audit_dir: str | Path = _DEFAULT_AUDIT_DIR,
) -> dict[str, Any]:
    return _get_lifecycle_writer(audit_dir).record_lifecycle_transition(
        alpha_id=alpha_id, from_state=from_state, to_state=to_state,
        reason=reason, trigger_rule=trigger_rule, context=context,
    )


def record_gate_decision(
    *, alpha_id: str, gate_name: str, passed: bool,
    reason: str = "", attribution: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    audit_dir: str | Path = _DEFAULT_AUDIT_DIR,
) -> dict[str, Any]:
    return _get_lifecycle_writer(audit_dir).record_gate_decision(
        alpha_id=alpha_id, gate_name=gate_name, passed=passed,
        reason=reason, attribution=attribution, context=context,
    )


def record_optimization_suggestion(
    *, alpha_id: str, suggestion: str, expected_effect: str = "",
    parent_failure: str = "", context: dict[str, Any] | None = None,
    audit_dir: str | Path = _DEFAULT_AUDIT_DIR,
) -> dict[str, Any]:
    return _get_lifecycle_writer(audit_dir).record_optimization_suggestion(
        alpha_id=alpha_id, suggestion=suggestion, expected_effect=expected_effect,
        parent_failure=parent_failure, context=context,
    )


def record_simulation_writeback(
    *, alpha_id: str, sim_config: dict[str, Any] | None,
    result_summary: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
    audit_dir: str | Path = _DEFAULT_AUDIT_DIR,
) -> dict[str, Any]:
    return _get_lifecycle_writer(audit_dir).record_simulation_writeback(
        alpha_id=alpha_id, sim_config=sim_config,
        result_summary=result_summary, context=context,
    )


# --- Helpers ----------------------------------------------------------------

def _new_entry_id(alpha_id: str) -> str:
    return f"{alpha_id}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:8]}"


def _sanitize(value: Any) -> dict[str, Any]:
    """Best-effort conversion of arbitrary values to a JSON-safe dict."""
    if value is None:
        return {}
    if isinstance(value, dict):
        try:
            json.dumps(value, default=str)
            return value
        except (TypeError, ValueError):
            return {"_raw": str(value)[:200]}
    if hasattr(value, "to_dict"):
        try:
            return value.to_dict()
        except Exception:  # noqa: BLE001
            return {"_raw": str(value)[:200]}
    return {"_value": str(value)[:200]}


def _capability_version() -> str:
    """Lazy capability registry version lookup with fallback."""
    try:
        from brain_alpha_ops.data.capability_registry import get_registry  # type: ignore
        registry = get_registry()
        if hasattr(registry, "version"):
            return str(registry.version())
    except Exception:  # noqa: BLE001 — registry may not exist yet (Workstream A)
        logger.debug("capability registry version lookup failed", exc_info=True)
    return "registry_unavailable"


def _scoring_version() -> str:
    return "scoring.v1"


def _gate_version() -> str:
    return "gates.v1"
