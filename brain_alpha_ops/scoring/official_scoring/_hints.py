"""Improvement hints and failure collection mixin for OfficialScoringSystem."""
from __future__ import annotations

from typing import Dict, List


class _HintsMixin:
    """Improvement hints and failure collection methods extracted from OfficialScoringSystem."""

    def _generate_improvement_hints(self, candidate, scorecard: dict, gate: dict) -> List[str]:
        """Generate actionable improvement suggestions based on failures."""
        hints = []

        empirical = scorecard.get("empirical", {})
        prior = scorecard.get("prior", {})

        # Empirical failures
        for item in empirical.get("items", []):
            if not item.get("passed", True):
                name = item["name"]
                if name == "sharpe":
                    hints.append(
                        f"Sharpe ({item['actual']}) below BRAIN threshold ({item['target']}). "
                        "Consider: shorter decay, different universe, or adding risk controls."
                    )
                elif name == "fitness":
                    hints.append(
                        f"Fitness ({item['actual']}) below threshold ({item['target']}). "
                        "Consider: reduce turnover to improve returns/turnover ratio."
                    )
                elif name == "turnover_platform":
                    hints.append(
                        f"Turnover ({item['actual']}) exceeds BRAIN max ({item['target']}). "
                        "Consider: use longer windows (ts_mean, ts_decay_linear) or slower signals."
                    )
                elif name == "turnover_quality":
                    hints.append(
                        f"Turnover ({item['actual']}) exceeds advisor quality target ({item['target']}). "
                        "Consider: add decay, use ts_decay_linear, or increase window length."
                    )
                elif name == "self_correlation":
                    hints.append(
                        f"Self-correlation ({item['actual']}) too high ({item['target']}). "
                        "Consider: change feature combination, use different operators, or check cloud overlap."
                    )
                elif name == "weight_concentration":
                    hints.append(
                        f"Weight concentration ({item['actual']}) too high ({item['target']}). "
                        "Consider: use group_neutralize with subindustry, or more diversified signals."
                    )

        # Checklist failures
        checklist = scorecard.get("submission_checklist", {})
        for item in checklist.get("items", []):
            if not item.get("passed", True):
                if item["name"] == "official_metrics_present":
                    hints.append("Missing official simulation results — run BRAIN API simulation first.")
                elif item["name"] == "official_pass":
                    hints.append("BRAIN official check did not pass — address hard gate failures.")
                elif item["name"] == "economic_logic":
                    hints.append("Hypothesis text too short (< 40 chars). Write a concrete economic thesis.")
                elif item["name"] == "diversity":
                    hints.append("Plain momentum template detected — add liquidity filter (adv20, vwap).")

        # Prior-based hints
        if prior.get("score", 100) < 60:
            hints.append("Low prior score. Improve: add more fields, use risk controls, diversify operators.")

        return hints[:8]  # Limit to top 8

    def _collect_failures(self, scorecard: dict, gate: dict) -> List[Dict[str, str]]:
        """Collect and rank all failures for reporting."""
        failures = []

        empirical = scorecard.get("empirical", {})
        for item in empirical.get("items", []):
            if not item.get("passed", True):
                severity = "HARD" if item.get("is_hard_gate") else "SOFT"
                failures.append({
                    "item": item["name"],
                    "severity": severity,
                    "reason": f"actual={item['actual']} {item['direction']} {item['target']}",
                    "source": "empirical_score",
                })

        checklist = scorecard.get("submission_checklist", {})
        for item in checklist.get("items", []):
            if not item.get("passed", True):
                failures.append({
                    "item": item["name"],
                    "severity": "SOFT",
                    "reason": item.get("meaning", ""),
                    "source": "submission_checklist",
                })

        # Sort: HARD first
        failures.sort(key=lambda f: (0 if f["severity"] == "HARD" else 1, f["item"]))
        return failures
