"""Tests for the data-driven failure-to-strategy ranking (P2-15).

P2-15 (2026-06-13) introduced
``brain_alpha_ops.research.failure_strategy_ranking`` which replaces the
hard-coded ``IterativeOptimizer._FAILURE_TO_STRATEGY`` table with a
ranking learned from ``data/ab_tests.jsonl``. This module pins the
contract:

* ``DEFAULT_FAILURE_TO_STRATEGY`` is the legacy baseline ordering.
* ``load_failure_strategy_ranking`` reads ``ab_tests.jsonl`` and emits
  one ranking per failure dimension. With insufficient evidence the
  ranking is identical to the legacy default.
* ``get_strategy_for_failure`` looks up a ranking, falling back to a
  safe default when the failure key is unknown.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest


def _write_ab_records(storage_dir: Path, records: list[dict]) -> None:
    """Write ``ab_tests.jsonl`` rows under ``storage_dir``."""
    storage_dir.mkdir(parents=True, exist_ok=True)
    target = storage_dir / "ab_tests.jsonl"
    with target.open("w", encoding="utf-8") as fh:
        for row in records:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _ab_row(*, mutation_type: str, parent_sharpe: float, parent_pass_fail: str = "FAIL",
            sharpe_delta: float = 0.0, parent_turnover: float = 0.2,
            parent_correlation: float = 0.4, parent_weight_concentration: float = 0.05,
            parent_fitness: float = 1.5, parent_margin: float = 8.0,
            parent_sub_universe_sharpe: float = 1.0) -> dict:
    return {
        "mutation_type": mutation_type,
        "parent_sharpe": parent_sharpe,
        "parent_pass_fail": parent_pass_fail,
        "sharpe_delta": sharpe_delta,
        "parent_turnover": parent_turnover,
        "parent_correlation": parent_correlation,
        "parent_weight_concentration": parent_weight_concentration,
        "parent_fitness": parent_fitness,
        "parent_margin": parent_margin,
        "parent_sub_universe_sharpe": parent_sub_universe_sharpe,
    }


class TestDefaultMapping:
    """The hard-coded baseline must be preserved exactly."""

    def test_default_mapping_covers_all_failure_dimensions(self):
        from brain_alpha_ops.research.failure_strategy_ranking import (
            DEFAULT_FAILURE_TO_STRATEGY,
        )
        # P2-15 (2026-06-13) baseline — keep these keys stable so
        # downstream code that special-cases a failure dimension does
        # not silently break.
        expected_keys = {
            "sharpe", "fitness", "correlation",
            "turnover_platform", "turnover_quality", "turnover_low",
            "concentration", "margin", "sub_universe_sharpe", "gate",
        }
        assert set(DEFAULT_FAILURE_TO_STRATEGY.keys()) == expected_keys

    def test_default_mapping_orders_are_non_empty(self):
        from brain_alpha_ops.research.failure_strategy_ranking import (
            DEFAULT_FAILURE_TO_STRATEGY,
        )
        for failure, strategies in DEFAULT_FAILURE_TO_STRATEGY.items():
            assert strategies, f"{failure} has empty default order"
            # No duplicates within a single failure dimension.
            assert len(set(strategies)) == len(strategies), failure


class TestClassifyFailure:
    """``_classify_failure`` must bucket rows into the right dimension."""

    def test_turnover_platform_when_turnover_too_high(self):
        from brain_alpha_ops.research.failure_strategy_ranking import _classify_failure

        row = _ab_row(mutation_type="field_swap", parent_sharpe=1.5, parent_turnover=0.85)
        assert _classify_failure(row) == "turnover_platform"

    def test_turnover_low_when_turnover_zero(self):
        from brain_alpha_ops.research.failure_strategy_ranking import _classify_failure

        row = _ab_row(mutation_type="window_perturb", parent_sharpe=1.5, parent_turnover=0.0)
        assert _classify_failure(row) == "turnover_low"

    def test_correlation_when_correlation_too_high(self):
        from brain_alpha_ops.research.failure_strategy_ranking import _classify_failure

        row = _ab_row(mutation_type="operator_substitute", parent_sharpe=1.5, parent_correlation=0.9)
        assert _classify_failure(row) == "correlation"

    def test_concentration_when_weight_concentration_too_high(self):
        from brain_alpha_ops.research.failure_strategy_ranking import _classify_failure

        row = _ab_row(
            mutation_type="structure_refine",
            parent_sharpe=1.5,
            parent_weight_concentration=0.25,
        )
        assert _classify_failure(row) == "concentration"

    def test_sharpe_when_low_sharpe_and_other_metrics_normal(self):
        from brain_alpha_ops.research.failure_strategy_ranking import _classify_failure

        row = _ab_row(mutation_type="field_swap", parent_sharpe=0.5)
        assert _classify_failure(row) == "sharpe"

    def test_fitness_when_low_fitness(self):
        from brain_alpha_ops.research.failure_strategy_ranking import _classify_failure

        row = _ab_row(mutation_type="field_swap", parent_sharpe=1.5, parent_fitness=0.4)
        assert _classify_failure(row) == "fitness"

    def test_margin_when_low_margin(self):
        from brain_alpha_ops.research.failure_strategy_ranking import _classify_failure

        row = _ab_row(mutation_type="structure_refine", parent_sharpe=1.5, parent_margin=1.0)
        assert _classify_failure(row) == "margin"

    def test_sub_universe_sharpe_when_oos_disagrees(self):
        from brain_alpha_ops.research.failure_strategy_ranking import _classify_failure

        row = _ab_row(
            mutation_type="field_swap",
            parent_sharpe=1.5,
            parent_sub_universe_sharpe=0.3,
        )
        assert _classify_failure(row) == "sub_universe_sharpe"

    def test_returns_none_for_passing_row(self):
        from brain_alpha_ops.research.failure_strategy_ranking import _classify_failure

        row = _ab_row(
            mutation_type="field_swap",
            parent_sharpe=1.5,
            parent_pass_fail="PASS",
        )
        assert _classify_failure(row) is None


class TestParentRecordPassed:
    def test_pass_fail_mapping(self):
        from brain_alpha_ops.research.failure_strategy_ranking import parent_record_passed

        assert parent_record_passed({"parent_pass_fail": "PASS"}) is True
        assert parent_record_passed({"parent_pass_fail": "FAIL"}) is False
        assert parent_record_passed({"parent_pass_fail": "pass"}) is True
        assert parent_record_passed({"parent_pass_fail": "fail"}) is False

    def test_unknown_pass_fail_returns_none(self):
        from brain_alpha_ops.research.failure_strategy_ranking import parent_record_passed

        assert parent_record_passed({}) is None
        assert parent_record_passed({"parent_pass_fail": ""}) is None
        assert parent_record_passed({"parent_pass_fail": "MAYBE"}) is None


class TestLoadFailureStrategyRanking:
    """Behavioural coverage for the learned ranking."""

    def test_missing_storage_dir_falls_back_to_defaults(self, tmp_path):
        from brain_alpha_ops.research.failure_strategy_ranking import (
            DEFAULT_FAILURE_TO_STRATEGY,
            load_failure_strategy_ranking,
        )

        # No ``ab_tests.jsonl`` under ``tmp_path``.
        ranking = load_failure_strategy_ranking(storage_dir=str(tmp_path))
        assert ranking == DEFAULT_FAILURE_TO_STRATEGY

    def test_empty_ab_tests_falls_back_to_defaults(self, tmp_path):
        from brain_alpha_ops.research.failure_strategy_ranking import (
            DEFAULT_FAILURE_TO_STRATEGY,
            load_failure_strategy_ranking,
        )
        _write_ab_records(tmp_path, [])

        ranking = load_failure_strategy_ranking(storage_dir=str(tmp_path))
        assert ranking == DEFAULT_FAILURE_TO_STRATEGY

    def test_insufficient_history_keeps_default_order(self, tmp_path):
        """Below the ``min_history`` threshold the default order wins."""
        from brain_alpha_ops.research.failure_strategy_ranking import (
            DEFAULT_FAILURE_TO_STRATEGY,
            load_failure_strategy_ranking,
        )

        # Four rows of ``field_swap`` (below default ``min_history=5``).
        rows = [
            _ab_row(
                mutation_type="field_swap",
                parent_sharpe=0.5,
                sharpe_delta=0.10,
            )
            for _ in range(4)
        ]
        _write_ab_records(tmp_path, rows)

        ranking = load_failure_strategy_ranking(storage_dir=str(tmp_path))
        # The default sharpe ranking is preserved because we don't
        # have enough positive samples to trust the learned one.
        assert ranking["sharpe"] == DEFAULT_FAILURE_TO_STRATEGY["sharpe"]

    def test_learned_ranking_uses_positive_delta_only(self, tmp_path):
        """Strategies that produced no positive ``sharpe_delta`` (or fewer
        than ``min_history`` positive samples) must NOT be promoted to
        the front of the learned ranking. The default ``structure_refine``
        slot is preserved as a safety net."""
        from brain_alpha_ops.research.failure_strategy_ranking import (
            load_failure_strategy_ranking,
        )

        # Six positive ``field_swap`` rows + six negative ``window_perturb``
        # rows. ``field_swap`` qualifies for the learned top slot;
        # ``window_perturb`` does not (zero positive samples).
        rows = [
            _ab_row(
                mutation_type="field_swap",
                parent_sharpe=0.5,
                sharpe_delta=0.20,
            )
            for _ in range(6)
        ]
        rows += [
            _ab_row(
                mutation_type="window_perturb",
                parent_sharpe=0.5,
                sharpe_delta=-0.05,
            )
            for _ in range(6)
        ]
        _write_ab_records(tmp_path, rows)

        ranking = load_failure_strategy_ranking(storage_dir=str(tmp_path))
        # The learned ranking must promote ``field_swap`` to the top.
        assert ranking["sharpe"][0] == "field_swap"
        # ``window_perturb`` is excluded from the learned slot because
        # it has zero positive samples; it only appears via the
        # default-order fallback append (position 1, not 0).
        assert ranking["sharpe"].index("window_perturb") > 0
        # The default ``structure_refine`` slot is preserved.
        assert "structure_refine" in ranking["sharpe"]

    def test_learned_ranking_orders_by_average_positive_delta(self, tmp_path):
        """Higher average ``sharpe_delta`` wins over lower ones."""
        from brain_alpha_ops.research.failure_strategy_ranking import (
            load_failure_strategy_ranking,
        )

        rows = []
        # field_swap — average 0.30, 6 samples
        for _ in range(6):
            rows.append(_ab_row(mutation_type="field_swap",
                                parent_sharpe=0.5, sharpe_delta=0.30))
        # structure_refine — average 0.10, 6 samples
        for _ in range(6):
            rows.append(_ab_row(mutation_type="structure_refine",
                                parent_sharpe=0.5, sharpe_delta=0.10))
        _write_ab_records(tmp_path, rows)

        ranking = load_failure_strategy_ranking(storage_dir=str(tmp_path))
        # ``field_swap`` should win over ``structure_refine`` (higher
        # average positive delta).
        assert ranking["sharpe"].index("field_swap") < ranking["sharpe"].index("structure_refine")

    def test_corrupt_ab_records_are_skipped(self, tmp_path):
        """Malformed JSON lines are silently skipped — the function must
        not raise."""
        from brain_alpha_ops.research.failure_strategy_ranking import (
            load_failure_strategy_ranking,
        )
        target = tmp_path / "ab_tests.jsonl"
        target.write_text(
            "not-json\n"
            + json.dumps(_ab_row(mutation_type="field_swap",
                                 parent_sharpe=0.5, sharpe_delta=0.20))
            + "\n"
            + "}\n",  # another malformed line
            encoding="utf-8",
        )
        ranking = load_failure_strategy_ranking(storage_dir=str(tmp_path))
        # The single good row should still be considered; with 1
        # positive sample (below min_history=5) the default order
        # wins. We only care that no exception was raised.
        assert "sharpe" in ranking

    def test_mutation_type_aliases(self, tmp_path):
        """Legacy ``mutation_type`` values (``window``/``structure``/``operator``)
        are mapped to the modern strategy names."""
        from brain_alpha_ops.research.failure_strategy_ranking import (
            load_failure_strategy_ranking,
        )

        rows = [
            _ab_row(
                mutation_type="window",
                parent_sharpe=0.5,
                sharpe_delta=0.20,
            )
            for _ in range(6)
        ]
        _write_ab_records(tmp_path, rows)

        ranking = load_failure_strategy_ranking(storage_dir=str(tmp_path))
        # ``window`` is an alias for ``window_perturb``; the learned
        # ranking must therefore promote ``window_perturb``.
        assert "window_perturb" in ranking["sharpe"]
        assert ranking["sharpe"][0] == "window_perturb"


class TestGetStrategyForFailure:
    """``get_strategy_for_failure`` looks up the ranking with a safe fallback."""

    def test_known_failure_returns_ranking_copy(self):
        from brain_alpha_ops.research.failure_strategy_ranking import get_strategy_for_failure

        ranking = {"sharpe": ["field_swap", "structure_refine"]}
        result = get_strategy_for_failure("sharpe", ranking)
        assert result == ["field_swap", "structure_refine"]
        # Returned list must be a copy so callers cannot mutate the
        # internal ranking.
        result.append("injected")
        assert ranking["sharpe"] == ["field_swap", "structure_refine"]

    def test_unknown_failure_falls_back_to_default(self):
        from brain_alpha_ops.research.failure_strategy_ranking import (
            DEFAULT_FAILURE_TO_STRATEGY,
            get_strategy_for_failure,
        )

        result = get_strategy_for_failure("never_seen_failure", {})
        assert result == DEFAULT_FAILURE_TO_STRATEGY.get(
            "never_seen_failure", ["structure_refine", "field_swap"]
        )


class TestMutationTypeToStrategyMapping:
    """Pin the legacy ``mutation_type`` → strategy alias table."""

    def test_alias_table_includes_modern_names(self):
        from brain_alpha_ops.research.failure_strategy_ranking import _MUTATION_TYPE_TO_STRATEGY

        for name in (
            "field_swap",
            "field_swap_semantic",
            "window_perturb",
            "longer_window",
            "structure_refine",
            "operator_substitute",
        ):
            assert name in _MUTATION_TYPE_TO_STRATEGY, name

    def test_alias_table_includes_legacy_aliases(self):
        from brain_alpha_ops.research.failure_strategy_ranking import _MUTATION_TYPE_TO_STRATEGY

        for legacy, modern in (
            ("window", "window_perturb"),
            ("structure", "structure_refine"),
            ("operator", "operator_substitute"),
        ):
            assert _MUTATION_TYPE_TO_STRATEGY[legacy] == modern, legacy
