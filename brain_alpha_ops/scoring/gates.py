"""Configurable gates constrained to BRAIN official hard checks."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from brain_alpha_ops.config import QualityThresholds
from brain_alpha_ops.research.scoring import empirical_score

logger = logging.getLogger(__name__)


OFFICIAL_HARD_GATE_NAMES: set[str] = {
    "sharpe",
    "fitness",
    "turnover_min",
    "turnover_platform",
    "self_correlation",
    "prod_correlation",
    "weight_concentration",
    "sub_universe_sharpe",
}


@dataclass(frozen=True)
class GateResult:
    """Pass/Fail gate result with full traceability."""

    gate_name: str
    passed: bool
    check_items: list[dict[str, Any]] = field(default_factory=list)  # N-05: mutable in frozen; to_dict() converts to list
    failed_items: list[str] = field(default_factory=list)
    threshold_source: str = "BRAIN_Official"
    notes: list[str] = field(default_factory=list)
    zero_deviation: bool = True

    def to_dict(self) -> dict:
        """S-01: Convert tuple fields back to lists for backward compatibility."""

        return {
            "gate_name": self.gate_name,
            "passed": self.passed,
            "check_items": list(self.check_items),
            "failed_items": list(self.failed_items),
            "threshold_source": self.threshold_source,
            "notes": list(self.notes),
            "zero_deviation": self.zero_deviation,
        }


class GateConfig:
    """Configurable Pass/Fail gate constrained to BRAIN official hard checks."""

    def __init__(self, thresholds: QualityThresholds | None = None):
        self.thresholds = thresholds or QualityThresholds()
        self._gates: list[dict[str, Any]] = []

    @classmethod
    def from_thresholds(cls, thresholds: QualityThresholds) -> "GateConfig":
        return cls(thresholds)

    def add_hard_gate(self, name: str, check_fn: Callable, description: str = "") -> "GateConfig":
        if name not in OFFICIAL_HARD_GATE_NAMES:
            raise ValueError(
                f"hard gate '{name}' is not a BRAIN official hard check; "
                f"allowed={sorted(OFFICIAL_HARD_GATE_NAMES)}"
            )
        self._gates.append({
            "name": name,
            "type": "HARD",
            "check": check_fn,
            "description": description,
            "source": "BRAIN_Official",
        })
        return self

    def add_soft_gate(self, name: str, check_fn: Callable, description: str = "") -> "GateConfig":
        self._gates.append({
            "name": name,
            "type": "SOFT",
            "check": check_fn,
            "description": description,
            "source": "Advisor_Standard",
        })
        return self

    @property
    def hard_gates(self) -> list[dict[str, Any]]:
        return [gate for gate in self._gates if gate.get("type") == "HARD"]

    def evaluate(self, metrics: dict) -> GateResult:
        passed_all = True
        items: list[dict[str, Any]] = []
        failed: list[str] = []
        official_rows = _official_hard_gate_rows(metrics, self.thresholds)
        for gate in self._gates:
            passed, payload, reason = _evaluate_gate(gate, metrics, self.thresholds, official_rows)
            items.append(payload)
            if not passed:
                failed.append(reason)
                if gate["type"] == "HARD":
                    passed_all = False
        return GateResult(
            gate_name="OFFICIAL_CONFIGURED_GATE",
            passed=passed_all,
            check_items=items,
            failed_items=failed,
            threshold_source="BRAIN_Official",
            zero_deviation=all(bool(item.get("zero_deviation", True)) for item in items),
        )


def _official_hard_gate_rows(metrics: dict, thresholds: QualityThresholds) -> dict[str, dict]:
    return {
        row.get("name"): row
        for row in empirical_score(
            metrics,
            thresholds,
            settings={"delay": _delay(metrics)},
        ).get("items", [])
        if row.get("is_hard_gate")
    }


def _evaluate_gate(
    gate: dict[str, Any],
    metrics: dict,
    thresholds: QualityThresholds,
    official_rows: dict[str, dict],
) -> tuple[bool, dict[str, Any], str]:
    error = ""
    try:
        configured_passed = _call_gate_check(gate["check"], metrics, thresholds)
    except Exception as exc:
        logger.warning("configured gate check failed: gate=%s", gate.get("name", ""), exc_info=True)
        configured_passed = False
        error = str(exc)
    official_row = official_rows.get(gate["name"]) if gate["type"] == "HARD" else None
    official_passed = bool(official_row.get("passed")) if official_row else configured_passed
    zero_deviation = gate["type"] != "HARD" or configured_passed == official_passed
    passed = bool(configured_passed and official_passed and zero_deviation)
    payload = {
        "name": gate["name"],
        "type": gate["type"],
        "passed": passed,
        "source": gate["source"],
        "description": gate["description"],
        "configured_passed": configured_passed,
    }
    if official_row:
        payload.update({
            "official_passed": official_passed,
            "zero_deviation": zero_deviation,
            "actual": official_row.get("actual"),
            "target": official_row.get("target"),
            "direction": official_row.get("direction"),
        })
    if error:
        payload["error"] = error
    return passed, payload, _failure_reason(gate["name"], zero_deviation, error)


def _call_gate_check(check_fn: Callable, metrics: dict, thresholds: QualityThresholds) -> bool:
    """Try check_fn(metrics, thresholds), fall back to check_fn(metrics) if signature mismatch."""
    try:
        return bool(check_fn(metrics, thresholds))
    except TypeError as exc:
        # S-02: Only retry if the error is signature-related ("takes"/"positional"),
        # not if check_fn itself has a bug. Any error in the second call propagates.
        msg = str(exc).lower()
        if "takes" in msg or "positional" in msg:
            return bool(check_fn(metrics))
        raise


def _failure_reason(name: str, zero_deviation: bool, error: str) -> str:
    if not zero_deviation:
        return f"{name}: configured gate deviates from BRAIN official check"
    if error:
        return f"{name}: {error}"
    return name


def _delay(metrics: dict) -> int:
    try:
        return int(metrics.get("delay", 1) or 1)
    except (TypeError, ValueError):
        return 1
