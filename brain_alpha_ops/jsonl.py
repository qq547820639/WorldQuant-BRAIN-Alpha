"""Small JSONL helpers for bounded, fault-tolerant local history reads."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Callable, Iterator


@dataclass(frozen=True)
class JsonlReadResult:
    rows: list[dict[str, Any]]
    path: str
    exists: bool
    requested_limit: int
    parsed_count: int
    skipped_blank_count: int
    skipped_invalid_count: int
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "exists": self.exists,
            "requested_limit": self.requested_limit,
            "parsed_count": self.parsed_count,
            "skipped_blank_count": self.skipped_blank_count,
            "skipped_invalid_count": self.skipped_invalid_count,
            "error": self.error,
        }


def read_jsonl_tail(path: str | Path, *, limit: int = 500) -> list[dict[str, Any]]:
    return read_jsonl_tail_with_stats(path, limit=limit).rows


def read_jsonl_records(path: str | Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    """Read JSONL records with an optional tail limit.

    ``limit=None`` streams the whole file. A positive limit reads only the
    trailing records, which is the default pattern for growing local history
    files used by dashboards and recent-memory features.
    """
    if limit is not None:
        return read_jsonl_tail(path, limit=limit)
    return list(iter_jsonl_records(path))


def iter_jsonl_records(path: str | Path) -> Iterator[dict[str, Any]]:
    target = Path(path)
    if not target.is_file():
        return
    try:
        with target.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    yield item
    except OSError:
        return


def count_jsonl_records(
    path: str | Path,
    *,
    predicate: Callable[[dict[str, Any]], bool] | None = None,
) -> int:
    count = 0
    for item in iter_jsonl_records(path):
        if predicate is None or predicate(item):
            count += 1
    return count


def read_jsonl_tail_with_stats(path: str | Path, *, limit: int = 500) -> JsonlReadResult:
    target = Path(path)
    safe_limit = max(1, int(limit or 1))
    if not target.is_file():
        return JsonlReadResult([], str(target), False, safe_limit, 0, 0, 0)

    rows: list[dict[str, Any]] = []
    skipped_blank = 0
    skipped_invalid = 0
    try:
        for line in tail_text_lines(target, safe_limit):
            if not line.strip():
                skipped_blank += 1
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                skipped_invalid += 1
                continue
            if isinstance(item, dict):
                rows.append(item)
            else:
                skipped_invalid += 1
    except OSError as exc:
        return JsonlReadResult([], str(target), True, safe_limit, 0, skipped_blank, skipped_invalid, str(exc))
    return JsonlReadResult(rows[-safe_limit:], str(target), True, safe_limit, len(rows), skipped_blank, skipped_invalid)


def tail_text_lines(path: str | Path, limit: int, *, chunk_size: int = 1024 * 1024) -> list[str]:
    target = Path(path)
    safe_limit = max(0, int(limit or 0))
    if safe_limit <= 0:
        return []
    with target.open("rb") as handle:
        handle.seek(0, 2)
        position = handle.tell()
        buffer = b""
        lines: list[bytes] = []
        while position > 0 and len(lines) <= safe_limit:
            read_size = min(chunk_size, position)
            position -= read_size
            handle.seek(position)
            buffer = handle.read(read_size) + buffer
            lines = buffer.splitlines()
        return [line.decode("utf-8", errors="replace") for line in lines[-safe_limit:]]
