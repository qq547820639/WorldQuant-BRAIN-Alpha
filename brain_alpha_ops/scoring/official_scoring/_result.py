"""ScoringResult dataclass for the official scoring system."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from brain_alpha_ops.scoring.attribution import AttributionNode
from brain_alpha_ops.scoring.gates import GateResult
from brain_alpha_ops.scoring.visualization import summarize_score_attribution


@dataclass
class ScoringResult:
    """Complete scoring result with full attribution."""
    alpha_id: str
    expression: str
    total_score: float
    decision_band: str
    passed_gate: bool
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Score breakdown
    prior: Dict[str, Any] = field(default_factory=dict)
    empirical: Dict[str, Any] = field(default_factory=dict)
    checklist: Dict[str, Any] = field(default_factory=dict)
    layer_weights: Dict[str, float] = field(default_factory=dict)

    # Gates
    hard_gates: List[GateResult] = field(default_factory=list)
    soft_gates: List[GateResult] = field(default_factory=list)
    release_gate: Dict[str, Any] = field(default_factory=dict)

    # Attribution
    attribution_tree: Optional[AttributionNode] = None
    top_failures: List[Dict[str, str]] = field(default_factory=list)
    improvement_hints: List[str] = field(default_factory=list)

    # API simulation
    simulated_api_output: Dict[str, Any] = field(default_factory=dict)
    api_output_deviation: float = 0.0  # 0.0 = perfect match
    deviation_details: List[str] = field(default_factory=list)

    # Traceability
    threshold_version: str = "CANONICAL_v2"
    scoring_schema: str = "scorecard-v2.3"
    scoring_version: str = ""
    config_hash: str = ""
    score_basis: str = ""
    settings_trace: Dict[str, Any] = field(default_factory=dict)
    threshold_trace: Dict[str, Any] = field(default_factory=dict)
    calibration: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "alpha_id": self.alpha_id,
            "expression": self.expression,
            "total_score": self.total_score,
            "decision_band": self.decision_band,
            "passed_gate": self.passed_gate,
            "evaluated_at": self.evaluated_at,
            "prior": self.prior,
            "empirical": self.empirical,
            "checklist": self.checklist,
            "layer_weights": self.layer_weights,
            "hard_gates": [g.to_dict() for g in self.hard_gates],
            "soft_gates": [g.to_dict() for g in self.soft_gates],
            "release_gate": self.release_gate,
            "attribution_tree": self.attribution_tree.to_dict() if self.attribution_tree else None,
            "top_failures": self.top_failures,
            "improvement_hints": self.improvement_hints,
            "simulated_api_output": self.simulated_api_output,
            "api_output_deviation": self.api_output_deviation,
            "deviation_details": self.deviation_details,
            "threshold_version": self.threshold_version,
            "scoring_schema": self.scoring_schema,
            "scoring_version": self.scoring_version,
            "config_hash": self.config_hash,
            "score_basis": self.score_basis,
            "settings_trace": self.settings_trace,
            "threshold_trace": self.threshold_trace,
            "calibration": self.calibration,
            "attribution_summary": summarize_score_attribution(
                {
                    "total_score": self.total_score,
                    "decision_band": self.decision_band,
                    "attribution_tree": self.attribution_tree.to_dict() if self.attribution_tree else None,
                    "top_failures": self.top_failures,
                    "improvement_hints": self.improvement_hints,
                }
            ),
        }

    def attribution_report(self) -> str:
        """Generate human-readable attribution report."""
        lines = [
            "=" * 64,
            f"  Scoring Attribution Report — {self.alpha_id}",
            "=" * 64,
            f"  Total Score    : {self.total_score:.2f}  ({self.decision_band})",
            f"  Gate Result    : {'PASS' if self.passed_gate else 'FAIL'}",
            f"  API Deviation  : {self.api_output_deviation:.4f}",
            "",
        ]

        if self.attribution_tree:
            lines.append("  Score Attribution:")
            self._render_tree(lines, self.attribution_tree, depth=1)

        if self.top_failures:
            lines.append("")
            lines.append("  Top Failures:")
            for f in self.top_failures[:5]:
                lines.append(f"    - [{f['severity']}] {f['item']}: {f['reason']}")

        if self.improvement_hints:
            lines.append("")
            lines.append("  Improvement Hints:")
            for hint in self.improvement_hints[:5]:
                lines.append(f"    → {hint}")

        if self.deviation_details:
            lines.append("")
            lines.append("  API Deviation Notes:")
            for d in self.deviation_details[:3]:
                lines.append(f"    ⚠ {d}")

        lines.append("")
        lines.append("=" * 64)
        return "\n".join(lines)

    @staticmethod
    def _render_tree(lines: List[str], node: AttributionNode, depth: int) -> None:
        indent = "    " * depth
        trend = f" [{node.historical_trend}]" if node.historical_trend else ""
        lines.append(
            f"{indent}{node.name:.<30} {node.score:>6.1f} × {node.weight:.2f} = {node.contribution:>7.2f}{trend}"
        )
        if node.explanation:
            lines.append(f"{indent}  ↳ {node.explanation}")
        for child in node.children:
            ScoringResult._render_tree(lines, child, depth + 1)
