"""Text/table primitives and finding builders for tracker validation."""

from __future__ import annotations

import re
from typing import Any


def section(text: str, heading: str) -> str:
    marker = f"## {heading}"
    start = text.find(marker)
    if start == -1:
        return ""
    next_start = text.find("\n## ", start + len(marker))
    return text[start:] if next_start == -1 else text[start:next_start]


def expect_all(
    text: str,
    expected_values: tuple[str, ...],
    code: str,
    findings: list[dict[str, str]],
    message: str = "expected tracker fact is missing",
) -> None:
    for expected in expected_values:
        if expected not in text:
            findings.append(finding(code, expected, message))


def has_fact(text: str, expected: str) -> bool:
    if "=" not in expected:
        return expected in text
    return re.search(r"(?<![A-Za-z0-9_])" + re.escape(expected) + r"(?![A-Za-z0-9_])", text) is not None


def reject_any(
    text: str,
    rejected_values: tuple[str, ...],
    code: str,
    findings: list[dict[str, str]],
    message: str = "stale tracker fact is still present",
) -> None:
    for rejected in rejected_values:
        if rejected in text:
            findings.append(finding(code, rejected, message))


def table_row(section: str, first_cell: str) -> str:
    prefix = f"| {first_cell} |"
    for line in section.splitlines():
        if line.startswith(prefix):
            return line
    return ""


def table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def finding(code: str, expected: str, message: str) -> dict[str, str]:
    return {"code": code, "expected": expected, "message": message}


def _check_baseline_row_values(
    rows: list[dict[str, str]],
    code: str,
    expected_values: list[tuple[str, Any]],
    findings: list[dict[str, str]],
    message: str,
) -> None:
    if not rows:
        return
    result = rows[0]["result"]
    for key, value in expected_values:
        if value is None:
            continue
        expected = f"{key}={value}"
        if not has_fact(result, expected):
            findings.append(finding(code, expected, message))
