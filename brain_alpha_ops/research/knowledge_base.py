"""Structured research knowledge base for reusable rules/findings/failures."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from brain_alpha_ops.jsonl import read_jsonl_tail
from brain_alpha_ops.models import utc_now
from brain_alpha_ops.redaction import redact_data
from brain_alpha_ops.research.llm_review import _digest_text


KNOWLEDGE_RECORD_SCHEMA_VERSION = "research_knowledge_record.v1"
KNOWLEDGE_SUMMARY_SCHEMA_VERSION = "research_knowledge_summary.v1"
SUPPORTED_KINDS = {"rules", "findings", "failures"}


@dataclass(frozen=True)
class KnowledgeRecord:
    kind: str
    title: str
    body: str
    confidence: float = 0.5
    scope: str = "global"
    evidence: list[dict[str, Any]] = field(default_factory=list)
    source_run_id: str = ""
    expiry: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": KNOWLEDGE_RECORD_SCHEMA_VERSION,
            "kind": self.kind,
            "title": self.title,
            "body": self.body,
            "confidence": max(0.0, min(1.0, float(self.confidence))),
            "scope": self.scope or "global",
            "evidence": list(self.evidence),
            "source_run_id": self.source_run_id,
            "expiry": self.expiry,
        }
        digest_source = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        payload["knowledge_id"] = f"rk_{_digest_text(digest_source)}"
        payload["created_at"] = utc_now()
        return redact_data(payload)


class ResearchKnowledgeBase:
    """Append-only structured knowledge alongside JSONL research memory."""

    def __init__(self, storage_dir: str | Path = "data"):
        self.root = Path(storage_dir) / "research_knowledge"
        self.root.mkdir(parents=True, exist_ok=True)

    def add(self, record: KnowledgeRecord | dict[str, Any]) -> dict[str, Any]:
        payload = record.to_dict() if isinstance(record, KnowledgeRecord) else self._record_from_dict(record).to_dict()
        kind = _kind(payload.get("kind"))
        path = self.root / f"{kind}.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str) + "\n")
        return payload

    def latest(self, kind: str = "", *, limit: int = 100, min_confidence: float = 0.0) -> list[dict[str, Any]]:
        kinds = [_kind(kind)] if kind else sorted(SUPPORTED_KINDS)
        rows: list[dict[str, Any]] = []
        threshold = max(0.0, min(1.0, float(min_confidence or 0.0)))
        for item_kind in kinds:
            for row in read_jsonl_tail(self.root / f"{item_kind}.jsonl", limit=max(1, int(limit or 1))):
                if float(row.get("confidence", 0.0) or 0.0) >= threshold:
                    rows.append(row)
        rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
        return rows[: max(1, int(limit or 1))]

    def summary(self, *, limit: int = 100, min_confidence: float = 0.0) -> dict[str, Any]:
        rows = self.latest(limit=limit, min_confidence=min_confidence)
        counts: dict[str, int] = {}
        for row in rows:
            kind = str(row.get("kind") or "unknown")
            counts[kind] = counts.get(kind, 0) + 1
        return {
            "ok": True,
            "schema_version": KNOWLEDGE_SUMMARY_SCHEMA_VERSION,
            "source": "research_knowledge_jsonl",
            "root": str(self.root),
            "count": len(rows),
            "counts": counts,
            "items": rows,
        }

    def _record_from_dict(self, data: dict[str, Any]) -> KnowledgeRecord:
        return KnowledgeRecord(
            kind=_kind(data.get("kind")),
            title=str(data.get("title") or ""),
            body=str(data.get("body") or data.get("summary") or ""),
            confidence=max(0.0, min(1.0, float(data.get("confidence", 0.5) or 0.5))),
            scope=str(data.get("scope") or "global"),
            evidence=list(data.get("evidence") or []),
            source_run_id=str(data.get("source_run_id") or ""),
            expiry=str(data.get("expiry") or ""),
        )


def _kind(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text not in SUPPORTED_KINDS:
        raise ValueError(f"unsupported knowledge kind: {text or '<empty>'}")
    return text
