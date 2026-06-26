"""Markdown table parsing and expected-queue assembly helpers.

Split from the former ``scripts/check_review_gap_closure_tracker.py`` monolith
(Task A3). Holds the generic table-row extraction helper, the required-status
row validator, and the expected active-queue item computation.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_review_gap_closure_tracker_helpers import (  # noqa: E402
    OFFICIAL_CONTEXT_QUEUE_ITEM,
    finding as _finding,
    frontend_surface_requires_queue as _frontend_surface_requires_queue,
    table_cells as _table_cells,
)

from ._constants import BASE_QUEUE_ITEMS, FRONTEND_SURFACE_QUEUE_ITEM


def _table_payload(
    section: str,
    *,
    columns: tuple[str, ...],
    header: str,
    shape_code: str,
    shape_message: str,
    detail_code: str,
    detail_message: str,
    findings: list[dict[str, str]],
    detail_columns: tuple[str, ...] | None = None,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    required_detail_columns = detail_columns or columns
    for line in section.splitlines():
        if not line.startswith("| ") or line.startswith("|---") or line.startswith(header):
            continue
        cells = _table_cells(line)
        if len(cells) != len(columns):
            findings.append(_finding(shape_code, line, shape_message))
            continue
        row = dict(zip(columns, cells))
        rows.append(row)
        row_name = row[columns[0]]
        for column in required_detail_columns:
            if not row[column].strip():
                findings.append(_finding(detail_code, f"{row_name}:{column}", detail_message))
    return rows


def _expect_required_status_rows(
    rows: list[dict[str, str]],
    *,
    key_column: str,
    status_column: str,
    required_items: tuple[tuple[str, str], ...],
    missing_code: str,
    duplicate_code: str,
    mismatch_code: str,
    missing_message: str,
    duplicate_message: str,
    mismatch_message: str,
    findings: list[dict[str, str]],
) -> None:
    status_by_item: dict[str, str] = {}
    counts: dict[str, int] = {}
    for row in rows:
        key = row[key_column]
        status_by_item[key] = row[status_column]
        counts[key] = counts.get(key, 0) + 1
    for item, expected_status in required_items:
        count = counts.get(item, 0)
        if count == 0:
            findings.append(_finding(missing_code, item, missing_message))
            continue
        if count > 1:
            findings.append(_finding(duplicate_code, item, duplicate_message))
        if status_by_item.get(item, "") != expected_status:
            findings.append(_finding(mismatch_code, f"{item}:{expected_status}", mismatch_message))


def _expected_queue_items(
    official_context: dict[str, Any],
    *,
    react_surface: dict[str, Any],
    status_matrix: list[dict[str, str]],
    live_submit: dict[str, Any],
) -> tuple[str, ...]:
    blocking_count = int(official_context.get("blocking_count") or 0)
    p1_count = int(official_context.get("p1_count") or 0)
    items = list(BASE_QUEUE_ITEMS)
    if _frontend_surface_requires_queue(react_surface, status_matrix):
        items.append(FRONTEND_SURFACE_QUEUE_ITEM)
    if not official_context.get("available") or blocking_count or p1_count:
        items.append(OFFICIAL_CONTEXT_QUEUE_ITEM)
    return tuple(items)
