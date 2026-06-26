"""JSONL source loading and record extraction for the expression index.

Re-exported via ``brain_alpha_ops.research.expression_index``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from brain_alpha_ops.jsonl import read_jsonl_tail
from brain_alpha_ops.research.expression_ast import (
    expression_profile_summary,
)

from brain_alpha_ops.research.expression_index._helpers import (
    _nested,
    _text,
)


def _load_jsonl(path: Path, *, limit: int) -> list[dict[str, Any]]:
    return read_jsonl_tail(path, limit=limit)


def _source_records_for(
    filename: str,
    source_rows: dict[str, list[dict[str, Any]]] | None,
    storage_dir: Path,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    if isinstance(source_rows, dict) and filename in source_rows:
        rows = source_rows.get(filename) or []
        safe_limit = max(1, int(limit or 1))
        return [row for row in rows[-safe_limit:] if isinstance(row, dict)]
    # Resolve ``_load_jsonl`` through the package namespace so tests which
    # monkeypatch ``brain_alpha_ops.research.expression_index._load_jsonl``
    # continue to intercept disk reads after the module split.
    from brain_alpha_ops.research.expression_index import _load_jsonl
    return _load_jsonl(storage_dir / filename, limit=limit)


def _expression_from_record(record: dict[str, Any]) -> str:
    expression = record.get("expression")
    if isinstance(expression, dict):
        code = expression.get("code") or expression.get("regular")
        if code:
            return _text(code)
    if expression:
        return _text(expression)

    candidate = record.get("candidate")
    if isinstance(candidate, dict):
        nested = _expression_from_record(candidate)
        if nested:
            return nested

    regular = record.get("regular")
    if isinstance(regular, dict) and regular.get("code"):
        return _text(regular.get("code"))

    raw = record.get("raw")
    if isinstance(raw, dict):
        raw_regular = raw.get("regular")
        if isinstance(raw_regular, dict) and raw_regular.get("code"):
            return _text(raw_regular.get("code"))

    return _text(record.get("expression_canonical"))


def _summary_from_record(record: dict[str, Any], expression: str) -> dict[str, Any]:
    fingerprint = _text(record.get("expression_fingerprint"))
    canonical = _text(record.get("expression_canonical"))
    profile = record.get("expression_profile") if isinstance(record.get("expression_profile"), dict) else {}
    if fingerprint and canonical and profile:
        return {
            "expression_canonical": canonical,
            "expression_fingerprint": fingerprint,
            "expression_profile": profile,
        }
    return expression_profile_summary(expression)
