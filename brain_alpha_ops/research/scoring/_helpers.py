"""Utility helpers for the scoring sub-package.

These small pure functions (``_num``, ``_bounded_score``, ``item``, ``check``,
etc.) are used across multiple scoring sub-modules.  Keeping them in one place
avoids duplication and mirrors the layout of the original ``scoring.py``.
"""

from __future__ import annotations


def _format_empirical_failure(row: dict) -> str:
    return (
        f"{str(row.get('name', 'check'))} "
        f"{str(row.get('direction', '-'))} "
        f"{str(row.get('target', '-'))} "
        f"(actual: {row.get('actual', '-')})"
    )


def item(name: str, actual, direction: str, target, passed: bool, points: int, *, is_hard_gate: bool = False) -> dict:
    return {
        "name": name,
        "actual": actual,
        "direction": direction,
        "target": target,
        "passed": bool(passed),
        "points": points,
        "is_hard_gate": is_hard_gate,
        "source": "BRAIN_Official" if is_hard_gate else "经验",
    }


def check(name: str, passed: bool, points: int, meaning: str) -> dict:
    return {"name": name, "passed": bool(passed), "points": points, "meaning": meaning}


def _bounded_score(value) -> float:
    return round(max(0.0, min(100.0, _num(value))), 2)


def _guidance_outcome_status(count: int, success_rate: float, avg_score: float) -> str:
    if count <= 0:
        return "unknown"
    if count >= 2 and (success_rate <= 0.25 or avg_score <= 50):
        return "weak"
    if success_rate >= 0.5 or avg_score >= 70:
        return "strong"
    return "neutral"


def _normalize_confidence(value) -> float:
    if value in (None, ""):
        return 1.0
    confidence = _num(value)
    if confidence > 1.0:
        confidence = confidence / 100.0
    return max(0.0, min(1.0, confidence))


def _int_num(value) -> int:
    return int(_num(value))


def _num(value) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0
