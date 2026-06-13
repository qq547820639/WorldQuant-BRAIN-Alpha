"""Data-driven failure-to-strategy ranking for the iterative optimizer.

P2-15 (2026-06-13): replaces the hard-coded
``IterativeOptimizer._FAILURE_TO_STRATEGY`` table with a learned ranking
backed by historical AB comparison rows in ``ab_tests.jsonl``. The learned
table is computed once at module import time and re-evaluated whenever
``reload_failure_strategy_ranking`` is called.

When no historical data is available the function falls back to the
original hard-coded order so the system remains deterministic from day 0.

Usage::

    from brain_alpha_ops.research.failure_strategy_ranking import (
        load_failure_strategy_ranking,
        get_strategy_for_failure,
    )

    ranking = load_failure_strategy_ranking(storage_dir="data")
    strategies = get_strategy_for_failure("sharpe", ranking)
    # → ["field_swap", "window_perturb", "structure_refine"] (or a learned order)
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from brain_alpha_ops.redaction import redact_error_message, redact_text

logger = logging.getLogger(__name__)

# Hard-coded fallback used when ab_tests.jsonl is empty / missing.
# This is the exact ordering that used to live in
# ``IterativeOptimizer._FAILURE_TO_STRATEGY`` (P2-15 baseline).
DEFAULT_FAILURE_TO_STRATEGY: dict[str, list[str]] = {
    "sharpe":              ["field_swap", "window_perturb", "structure_refine"],
    "fitness":             ["field_swap", "structure_refine", "operator_substitute"],
    "correlation":         ["field_swap_semantic", "operator_substitute", "structure_refine"],
    "turnover_platform":   ["longer_window", "structure_refine"],
    "turnover_quality":    ["longer_window", "structure_refine"],
    "turnover_low":        ["window_perturb", "field_swap"],
    "concentration":       ["structure_refine", "field_swap"],
    "margin":              ["structure_refine", "operator_substitute"],
    "sub_universe_sharpe": ["structure_refine", "field_swap"],
    "gate":                ["structure_refine", "field_swap"],
}

# Mapping from ``mutation_type`` strings the rest of the codebase writes
# into ab_tests.jsonl to the strategy names this module emits.  When the
# historical row is missing, the failure key keeps its fallback default.
_MUTATION_TYPE_TO_STRATEGY: dict[str, str] = {
    "field_swap":            "field_swap",
    "field_swap_semantic":   "field_swap_semantic",
    "window_perturb":        "window_perturb",
    "longer_window":         "longer_window",
    "structure_refine":      "structure_refine",
    "operator_substitute":   "operator_substitute",
    # fallbacks for legacy / free-form values written before P2-15
    "window":                "window_perturb",
    "structure":             "structure_refine",
    "operator":              "operator_substitute",
}

_MIN_HISTORY = 5
"""Minimum number of successful AB rows required before we trust the
learned ranking enough to override the hard-coded default for a given
failure dimension. Below this threshold we return the hard-coded order
unchanged so early-pipeline runs behave exactly as before."""

def _classify_failure(record: dict[str, Any]) -> str | None:
    """Best-effort mapping from a metrics record to a failure dimension key.

    Returns ``None`` when the record shows no failure or when the failure
    cannot be confidently classified. We deliberately treat the row as
    a *sharpe* failure when the parent record has ``pass_fail=FAIL``
    because ab_tests.jsonl rows are only written for parents that did
    not pass the gate; the row's parent_sharpe then drives the more
    specific classification.
    """
    sharpe = float(record.get("parent_sharpe") or 0.0)
    fitness = float(record.get("parent_fitness") or 0.0)
    turnover = float(record.get("parent_turnover") or 0.0)
    margin = float(record.get("parent_margin") or 0.0)
    sub = float(record.get("parent_sub_universe_sharpe") or 0.0)
    correlation = float(record.get("parent_correlation") or 0.0)
    concentration = float(record.get("parent_weight_concentration") or 0.0)

    # Specific dimension checks first (in priority order) so that rows
    # that mention multiple problems bucket into the most actionable one.
    if turnover > 0.70:
        return "turnover_platform"
    if turnover < 0.01:
        return "turnover_low"
    if correlation > 0.70:
        return "correlation"
    if concentration > 0.10:
        return "concentration"
    if sharpe < 1.25:
        return "sharpe"
    if fitness < 1.0:
        return "fitness"
    if margin < 4.0:
        return "margin"
    if sub < 0.5 * max(sharpe, 0.01):
        return "sub_universe_sharpe"
    if parent_record_passed(record) is False:
        return "gate"
    return None

def parent_record_passed(record: dict[str, Any]) -> bool | None:
    pf = str(record.get("parent_pass_fail") or "").upper().strip()
    if pf == "PASS":
        return True
    if pf == "FAIL":
        return False
    return None

def _load_ab_records(path: str, limit: int = 2000) -> list[dict[str, Any]]:
    if not os.path.isfile(path):
        return []
    out: list[dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
                if len(out) >= limit:
                    break
    except OSError as exc:
        logger.warning("could not read %s: %s", redact_text(path, max_length=180), redact_error_message(exc))
    return out

def load_failure_strategy_ranking(
    storage_dir: str = "data",
    *,
    min_history: int = _MIN_HISTORY,
) -> dict[str, list[str]]:
    """Build a failure-dimension → ordered strategy list from ab_tests.jsonl.

    Strategy order is the list of ``_MUTATION_TYPE_TO_STRATEGY`` keys that
    most consistently produced a positive ``sharpe_delta`` for the given
    failure dimension. Stable sort: ties are broken by the original
    :data:`DEFAULT_FAILURE_TO_STRATEGY` order so the function is
    deterministic and never produces a worse order than the baseline.
    """
    path = os.path.join(storage_dir, "ab_tests.jsonl")
    records = _load_ab_records(path)

    # Group: failure -> strategy -> [sharpe_delta, ...]
    bucket: dict[str, dict[str, list[float]]] = {}
    for record in records:
        # ``ab_tests.jsonl`` rows only carry the parent metrics for the
        # originating failure; we classify the failure from the parent
        # metrics embedded in the record. If classification is not
        # possible we skip the row rather than guess.
        dim = _classify_failure(record)
        if not dim:
            continue
        mtype = str(record.get("mutation_type") or "").strip().lower()
        strategy = _MUTATION_TYPE_TO_STRATEGY.get(mtype)
        if not strategy:
            continue
        delta = float(record.get("sharpe_delta") or 0.0)
        bucket.setdefault(dim, {}).setdefault(strategy, []).append(delta)

    ranking: dict[str, list[str]] = {}
    for dim, default_strategies in DEFAULT_FAILURE_TO_STRATEGY.items():
        strat_deltas = bucket.get(dim, {})
        seen_strategies = list(strat_deltas.keys())
        if not seen_strategies:
            ranking[dim] = list(default_strategies)
            continue
        # Score: average positive sharpe_delta, with a tiebreaker on count.
        # Strategies that have never produced a positive delta are
        # excluded from the ranking so the default order is never
        # beaten by a strategy with zero evidence of success.
        scored: list[tuple[str, float, int]] = []
        for strat, deltas in strat_deltas.items():
            positives = [d for d in deltas if d > 0]
            if len(positives) < min_history:
                # Treat a strategy with too few positive samples as
                # un-trustworthy; it stays in the legacy default slot.
                continue
            avg = sum(positives) / len(positives)
            scored.append((strat, avg, len(positives)))
        if not scored:
            ranking[dim] = list(default_strategies)
            continue
        scored.sort(key=lambda item: (item[1], item[2]), reverse=True)
        ordered = [s for s, _, _ in scored]
        # Append any default strategies we haven't seen yet, in default
        # order. This guarantees the returned list always includes the
        # legacy hard-coded fallback as a final safety net.
        for strat in default_strategies:
            if strat not in ordered:
                ordered.append(strat)
        ranking[dim] = ordered

    return ranking

def get_strategy_for_failure(
    failure: str,
    ranking: dict[str, list[str]],
) -> list[str]:
    """Return the ordered strategy list for *failure*, with a safe fallback."""
    strategies = ranking.get(failure)
    if strategies:
        return list(strategies)
    # Last-ditch fallback: use the hard-coded default.
    return list(DEFAULT_FAILURE_TO_STRATEGY.get(failure, ["structure_refine", "field_swap"]))

__all__ = [
    "DEFAULT_FAILURE_TO_STRATEGY",
    "load_failure_strategy_ranking",
    "get_strategy_for_failure",
]
