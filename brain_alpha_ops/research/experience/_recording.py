"""Recording of Alpha official backtest features.

Re-exported via ``brain_alpha_ops.research.experience``.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from brain_alpha_ops.research.experience._common import (
    DEFAULT_HISTORY_LIMIT,
    _load_records,
    _num,
    _ratio,
)

if TYPE_CHECKING:
    from brain_alpha_ops.models import Candidate


# ═══════════════════════════════════════════════════════════════════════
# Recording
# ═══════════════════════════════════════════════════════════════════════

def record_alpha_result(
    candidate: "Candidate",
    storage_dir: str = "data",
) -> None:
    """Record Alpha official backtest features in the experience database.

    Writes to data/alpha_features.jsonl, one JSON record per line.

    Feature data all comes from actual BRAIN API results:
      - field_set: fields used in the expression (validated by OfficialDataLoader)
      - operator_set: operators used in the expression (from the BRAIN /operators API)
      - window_values: numeric parameters in the expression
      - metrics: sharpe/fitness/turnover/correlation/margin (from simulation results)

    P1 AB comparison: when candidate has parent_id, automatically look up the
    parent Alpha's official result and record a comparison in ab_tests.jsonl.
    """
    metrics = candidate.official_metrics or {}
    if not metrics:
        return

    # Extract windows from the expression.
    window_values = [int(v) for v in re.findall(r"\b(\d+)\b", candidate.expression) if 3 <= int(v) <= 252]

    features: dict[str, Any] = {
        "alpha_id": candidate.alpha_id,
        "official_alpha_id": candidate.official_alpha_id or "",
        "expression": candidate.expression,
        "family": candidate.family,
        "field_set": sorted(candidate.data_fields or []),
        "operator_set": sorted(candidate.operators or []),
        "window_values": sorted(window_values),
        # Official metrics (sourced from BRAIN API normalize_metrics).
        "sharpe": _num(metrics.get("sharpe")),
        "fitness": _num(metrics.get("fitness")),
        "turnover": _ratio(metrics.get("turnover")),
        "returns": _num(metrics.get("returns", 0)),
        "correlation": abs(_ratio(metrics.get("correlation"))),
        "margin": _num(metrics.get("margin", 0)),
        "weight_concentration": _ratio(metrics.get("weight_concentration")),
        "sub_universe_sharpe": _num(metrics.get("sub_universe_sharpe", 0)),
        "pass_fail": metrics.get("pass_fail", "UNKNOWN"),
        # Source tracking
        "source": "BRAIN_official_simulation_result",
    }

    # P1: record parent information for AB comparison.
    if candidate.parent_id:
        features["parent_id"] = candidate.parent_id
        features["mutation_type"] = candidate.mutation_type or "unknown"

    path = os.path.join(storage_dir, "alpha_features.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(features, ensure_ascii=False) + "\n")

    # P1: AB comparison — if the candidate has a parent Alpha, compare results.
    if candidate.parent_id:
        _record_ab_comparison(candidate, storage_dir)


# ═══════════════════════════════════════════════════════════════════════
# P1: AB comparison — causal-effect evaluation of mutations
# ═══════════════════════════════════════════════════════════════════════

def _record_ab_comparison(
    mutant: "Candidate",
    storage_dir: str = "data",
) -> None:
    """Compare an Alpha's results before and after mutation and record them in ab_tests.jsonl.

    Look up the parent Alpha result in alpha_features.jsonl.
    If found, write a comparison record.
    """
    parent_id = mutant.parent_id
    if not parent_id:
        return
    mutation_type = mutant.mutation_type or "unknown"

    # Look up the parent Alpha result.
    features_path = os.path.join(storage_dir, "alpha_features.jsonl")
    if not os.path.exists(features_path):
        return

    parent_record = None
    records = _load_records(features_path, limit=DEFAULT_HISTORY_LIMIT)
    for r in records:
        if r.get("alpha_id") == parent_id or r.get("official_alpha_id") == parent_id:
            parent_record = r
            break

    if not parent_record:
        return  # The parent Alpha does not have an official result yet.

    # Compare metrics.
    mutant_metrics = mutant.official_metrics or {}
    mutation_display = (
        (mutant.expression[:80] + "…")
        if len(mutant.expression) > 80
        else mutant.expression
    )

    comparison = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "parent_id": parent_id,
        "mutant_id": mutant.alpha_id,
        "mutation_type": mutation_type,
        "mutation_display": mutation_display,
        # Parent metrics
        "parent_sharpe": _num(parent_record.get("sharpe")),
        "parent_fitness": _num(parent_record.get("fitness")),
        "parent_turnover": _ratio(parent_record.get("turnover")),
        "parent_margin": _num(parent_record.get("margin")),
        "parent_pass_fail": parent_record.get("pass_fail", "UNKNOWN"),
        # Mutant metrics
        "mutant_sharpe": _num(mutant_metrics.get("sharpe")),
        "mutant_fitness": _num(mutant_metrics.get("fitness")),
        "mutant_turnover": _ratio(mutant_metrics.get("turnover")),
        "mutant_margin": _num(mutant_metrics.get("margin", 0)),
        "mutant_pass_fail": mutant_metrics.get("pass_fail", "UNKNOWN"),
        # Improvement
        "sharpe_delta": round(
            _num(mutant_metrics.get("sharpe")) - _num(parent_record.get("sharpe")), 4
        ),
        "fitness_delta": round(
            _num(mutant_metrics.get("fitness")) - _num(parent_record.get("fitness")), 4
        ),
        "turnover_delta": round(
            _ratio(mutant_metrics.get("turnover")) - _ratio(parent_record.get("turnover")), 4
        ),
        "margin_delta": round(
            _num(mutant_metrics.get("margin", 0)) - _num(parent_record.get("margin")), 4
        ),
        "improved": (
            _num(mutant_metrics.get("sharpe")) > _num(parent_record.get("sharpe"))
        ),
    }

    ab_path = os.path.join(storage_dir, "ab_tests.jsonl")
    os.makedirs(os.path.dirname(ab_path), exist_ok=True)
    with open(ab_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(comparison, ensure_ascii=False) + "\n")


def get_mutation_effectiveness(
    storage_dir: str = "data",
    min_samples: int = 3,
    history_limit: int = DEFAULT_HISTORY_LIMIT,
) -> dict[str, Any]:
    """Summarize improvement results by mutation_type.

    Aggregates average Sharpe improvement, success rate, and related deltas
    from ab_tests.jsonl.

    Returns:
        {
            "total_comparisons": int,
            "by_mutation_type": {...},
            "summary": str,
        }
    """
    ab_path = os.path.join(storage_dir, "ab_tests.jsonl")
    if not os.path.exists(ab_path):
        return {"total_comparisons": 0, "by_mutation_type": {}, "summary": "No AB test data."}

    records = _load_records(ab_path, limit=history_limit)
    if not records:
        return {"total_comparisons": 0, "by_mutation_type": {}, "summary": "AB test database empty."}

    by_type: dict[str, dict[str, Any]] = {}
    for r in records:
        mtype = r.get("mutation_type", "unknown")
        if mtype not in by_type:
            by_type[mtype] = {
                "count": 0, "improvements": 0,
                "avg_sharpe_delta": 0.0, "avg_fitness_delta": 0.0,
                "avg_turnover_delta": 0.0, "avg_margin_delta": 0.0,
            }
        info = by_type[mtype]
        info["count"] += 1
        if r.get("improved"):
            info["improvements"] += 1
        info["avg_sharpe_delta"] += r.get("sharpe_delta", 0)
        info["avg_fitness_delta"] += r.get("fitness_delta", 0)
        info["avg_turnover_delta"] += r.get("turnover_delta", 0)
        info["avg_margin_delta"] += r.get("margin_delta", 0)

    for mtype, info in by_type.items():
        n = max(info["count"], 1)
        info["improvement_rate"] = round(info["improvements"] / n, 3)
        info["avg_sharpe_delta"] = round(info["avg_sharpe_delta"] / n, 4)
        info["avg_fitness_delta"] = round(info["avg_fitness_delta"] / n, 4)
        info["avg_turnover_delta"] = round(info["avg_turnover_delta"] / n, 4)
        info["avg_margin_delta"] = round(info["avg_margin_delta"] / n, 4)

    total = len(records)
    total_improved = sum(1 for r in records if r.get("improved"))

    return {
        "total_comparisons": total,
        "total_improvement_rate": round(total_improved / max(total, 1), 3),
        "history_limit": history_limit,
        "by_mutation_type": {
            mtype: info
            for mtype, info in sorted(
                by_type.items(),
                key=lambda x: x[1].get("avg_sharpe_delta", 0),
                reverse=True,
            )
        },
        "source": "BRAIN_official_simulation_AB_comparisons",
        "summary": (
            f"From {total} AB comparisons: {total_improved} improved "
            f"({total_improved/max(total,1)*100:.1f}%). "
            f"Most effective mutation: "
            f"{max(by_type.items(), key=lambda x: x[1].get('avg_sharpe_delta', 0))[0] if by_type else 'N/A'}."
        ),
    }
