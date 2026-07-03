"""Common helpers, constants, and pattern-query functions for the experience subpackage.

Consolidated from the original ``experience`` subpackage. Holds the shared
helpers (``logger``, ``DEFAULT_HISTORY_LIMIT``, ``_num``, ``_ratio``,
``_load_records``, ``_empty_patterns``, ``normalize_brain_ratio``) and the
pattern-extraction / hypothesis-weight-feedback functions
(``get_winning_patterns``, ``update_hypothesis_weights``).

Re-exported via ``brain_alpha_ops.research.experience``.
"""
from __future__ import annotations

import logging
import os
import re
from collections import Counter
from typing import TYPE_CHECKING, Any

from brain_alpha_ops.jsonl import read_jsonl_records

# P0-4 fix (2026-06-13): all four _ratio() variants across
# research/{scoring,experience,safety,diagnostics}.py now share a single
# implementation in ``research._ratio``. The local definition below is kept
# for backward-compat with the previous module-level symbol.
from brain_alpha_ops.research._ratio import normalize_brain_ratio  # noqa: F401

logger = logging.getLogger("brain_alpha_ops.research.experience")

DEFAULT_HISTORY_LIMIT = 5000


def _num(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _ratio(value: Any) -> float:
    """Backwards-compatible wrapper for the canonical BRAIN ratio normalizer.

    See :func:`brain_alpha_ops.research._ratio.normalize_brain_ratio` for the
    full rule (percentage-scale when ``abs(value) >= 2.0``).
    """
    return normalize_brain_ratio(value, bounded=False)


def _load_records(path: str, *, limit: int | None = DEFAULT_HISTORY_LIMIT) -> list[dict[str, Any]]:
    return read_jsonl_records(path, limit=limit)


def _empty_patterns(reason: str) -> dict[str, Any]:
    return {
        "sample_size": 0,
        "total_records": 0,
        "avg_sharpe": 0.0,
        "avg_fitness": 0.0,
        "field_combinations": [],
        "top_operators": [],
        "preferred_windows": [],
        "top_categories": [],
        "source": "BRAIN_official_simulation_results",
        "summary": reason,
    }


# ═══════════════════════════════════════════════════════════════════════
# Pattern extraction and hypothesis weight feedback
# ═══════════════════════════════════════════════════════════════════════

def get_winning_patterns(
    storage_dir: str = "data",
    min_sharpe: float = 1.0,
    min_fitness: float = 0.5,
    min_sample: int = 3,
    history_limit: int = DEFAULT_HISTORY_LIMIT,
) -> dict[str, Any]:
    """Extract common feature patterns from winning Alphas.

    Args:
        storage_dir: data directory
        min_sharpe: minimum Sharpe threshold used to filter winning Alphas
        min_fitness: minimum Fitness threshold
        min_sample: minimum sample count; returns an empty result when too small

    Returns:
        {
            "sample_size": int,
            "total_records": int,
            "field_combinations": [{fields: [...], count: int, avg_sharpe: float}],
            "top_operators": [str],
            "preferred_windows": [int],
            "top_categories": [str],
            "summary": str,
        }
    """
    path = os.path.join(storage_dir, "alpha_features.jsonl")
    if not os.path.exists(path):
        return _empty_patterns("No experience database found — run official simulations first.")

    records = _load_records(path, limit=history_limit)
    if not records:
        return _empty_patterns("Experience database is empty.")

    total = len(records)

    # Filter winning alphas.
    winners = [
        r for r in records
        if r.get("pass_fail") == "PASS"
        and r.get("sharpe", 0) >= min_sharpe
        and r.get("fitness", 0) >= min_fitness
    ]

    if len(winners) < min_sample:
        return _empty_patterns(
            f"Only {len(winners)} winning alpha(s) with Sharpe >= {min_sharpe}, need {min_sample}+."
        )

    # Field combinations.
    field_combos = Counter(
        tuple(sorted(r.get("field_set", [])))
        for r in winners
        if len(r.get("field_set", [])) >= 2
    ).most_common(5)

    # Top operators.
    operator_counter = Counter(
        op for r in winners for op in r.get("operator_set", [])
    )
    top_operators = [op for op, _ in operator_counter.most_common(10)]

    # Preferred windows.
    window_counter = Counter(
        w for r in winners for w in r.get("window_values", [])
    )
    preferred_windows = [w for w, _ in window_counter.most_common(5)]

    # Top families.
    family_counter = Counter(r.get("family", "unknown") for r in winners)
    top_categories = [cat for cat, _ in family_counter.most_common(5)]

    # Average metrics for winners.
    avg_sharpe = sum(r.get("sharpe", 0) for r in winners) / len(winners)
    avg_fitness = sum(r.get("fitness", 0) for r in winners) / len(winners)

    return {
        "sample_size": len(winners),
        "total_records": total,
        "history_limit": history_limit,
        "avg_sharpe": round(avg_sharpe, 3),
        "avg_fitness": round(avg_fitness, 3),
        "field_combinations": [
            {"fields": list(f), "count": c, "avg_sharpe": round(
                sum(r.get("sharpe", 0) for r in winners if tuple(sorted(r.get("field_set", []))) == f) / max(c, 1), 3
            )}
            for f, c in field_combos
        ],
        "top_operators": top_operators,
        "preferred_windows": preferred_windows,
        "top_categories": top_categories,
        "source": "BRAIN_official_simulation_results",
        "summary": (
            f"From {total} total records, {len(winners)} winning alphas (Sharpe >= {min_sharpe}). "
            f"Avg Sharpe={avg_sharpe:.3f}, Avg Fitness={avg_fitness:.3f}. "
            f"Top operators: {', '.join(top_operators[:5])}. "
            f"Preferred windows: {preferred_windows}."
        ),
    }


# ── Hypothesis Weight Feedback ──────────────────────────────────────

def update_hypothesis_weights(
    library: Any,
    min_sharpe: float = 1.0,
    min_sample: int = 3,
    storage_dir: str = "data",
    history_limit: int = DEFAULT_HISTORY_LIMIT,
) -> dict[str, Any]:
    """Update hypothesis experience weights based on winning alpha patterns.

    Reads alpha_features.jsonl to identify winner alphas, then computes
    winner ratios per hypothesis/field/expression_family and calls
    HypothesisLibrary.update_weights() with EMA smoothing.

    Parameters
    ----------
    library:
        An instance of HypothesisLibrary (from hypothesis_library.py).
    min_sharpe:
        Minimum Sharpe ratio to qualify as a "winner".
    min_sample:
        Minimum number of winners required before updating weights.
    storage_dir:
        Directory containing alpha_features.jsonl.

    Returns
    -------
    dict with keys:
        updated_hypotheses: list of updated hypothesis IDs
        winner_count: total number of winner records
        total_records: total records scanned
        summary: str
    """
    path = os.path.join(storage_dir, "alpha_features.jsonl")
    if not os.path.exists(path):
        return {
            "updated_hypotheses": [],
            "winner_count": 0,
            "total_records": 0,
            "summary": f"No experience database found at {path}.",
        }

    records = _load_records(path, limit=history_limit)
    if not records:
        return {
            "updated_hypotheses": [],
            "winner_count": 0,
            "total_records": 0,
            "summary": "Experience database is empty.",
        }

    total = len(records)

    # Filter winners
    winners = [
        r for r in records
        if r.get("pass_fail") == "PASS"
        and r.get("sharpe", 0) >= min_sharpe
    ]
    if len(winners) < min_sample:
        return {
            "updated_hypotheses": [],
            "winner_count": len(winners),
            "total_records": total,
            "summary": (
                f"Only {len(winners)} winners (Sharpe >= {min_sharpe}), "
                f"need {min_sample}+ to update weights."
            ),
        }

    winner_count = len(winners)

    # For each hypothesis in the library, compute winner ratios
    all_hypothesis_ids = library.get_ids() if hasattr(library, 'get_ids') else []
    updated_ids: list[str] = []

    for hyp_id in all_hypothesis_ids:
        hyp = library.get_by_id(hyp_id) if hasattr(library, 'get_by_id') else None
        if hyp is None:
            continue

        # Compute field category winner ratios
        field_cat_weights: dict[str, float] = {}
        for fc in hyp.field_categories:
            # Count winners that used fields matching this category
            # Look in record field_set for category examples or partial matches
            matched = 0
            for r in winners:
                r_fields = [str(f).lower() for f in r.get("field_set", [])]
                examples = [str(e).lower() for e in fc.examples]
                # Match if any example or category keyword appears in record fields
                if any(
                    ex in " ".join(r_fields) or fc.category.lower() in " ".join(r_fields)
                    for ex in examples
                ):
                    matched += 1
            ratio = matched / winner_count if winner_count > 0 else 0.0
            field_cat_weights[fc.category] = ratio

        # Compute expression family winner ratios
        expr_fam_weights: dict[str, float] = {}
        for ef in hyp.expression_families:
            # Look for structure keywords in winning expressions
            structure_keywords = set(re.findall(r'\b\w+\b', ef.structure.lower()))
            structure_keywords.discard('f1')
            structure_keywords.discard('f2')
            structure_keywords.discard('field')
            structure_keywords.discard('window')
            structure_keywords.discard('w')

            matched = 0
            for r in winners:
                expr = str(r.get("expression", "")).lower()
                if any(kw in expr for kw in structure_keywords if len(kw) > 2):
                    matched += 1
            ratio = matched / winner_count if winner_count > 0 else 0.0
            expr_fam_weights[ef.id] = ratio

        # Compute window winner ratios
        window_weights: dict[str, float] = {}
        window_counter: dict[int, int] = {}
        for r in winners:
            for w_str in r.get("window_values", []):
                try:
                    w = int(w_str)
                    window_counter[w] = window_counter.get(w, 0) + 1
                except (TypeError, ValueError):
                    continue
        for w, cnt in window_counter.items():
            window_weights[str(w)] = cnt / winner_count if winner_count > 0 else 0.0

        # Update library weights
        if hasattr(library, 'update_weights'):
            library.update_weights(
                hyp_id,
                field_cat_weights=field_cat_weights,
                expr_fam_weights=expr_fam_weights,
                window_weights=window_weights,
            )
        updated_ids.append(hyp_id)

    return {
        "updated_hypotheses": updated_ids,
        "winner_count": winner_count,
        "total_records": total,
        "summary": (
            f"Updated {len(updated_ids)} hypotheses based on {winner_count} winners "
            f"(from {total} total records, min_sharpe={min_sharpe})."
        ),
    }
