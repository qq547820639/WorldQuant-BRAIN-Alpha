"""Grid-search helpers for ``AutoCalibrator``.

Extracted from the original ``auto_calibrator.py`` as a mixin so that the
parameter grid-search logic remains cohesive while keeping the main
calibrator module small.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from brain_alpha_ops.research.scoring_params import DimensionParam


class _GridSearchMixin:
    """Provides grid-search parameter tuning helpers."""

    def _grid_search_dimension(
        self,
        dim_name: str,
        base_dim: DimensionParam,
        grid_config: dict[str, list[float]],
        records: list[dict[str, Any]],
    ) -> tuple[DimensionParam, float]:
        """Grid-search tunable parameters for one dimension.

        Returns:
            (best DimensionParam, best MAE)
        """
        best_dim = base_dim
        best_mae = self._compute_mae(dim_name, base_dim, records)

        # Generate all parameter combinations.
        param_names = list(grid_config.keys())
        combinations = self._generate_grid_combinations(grid_config)

        for combo in combinations:
            test_dim = DimensionParam(**{**asdict(base_dim), "name": dim_name})
            for i, name in enumerate(param_names):
                setattr(test_dim, name, combo[i])

            mae = self._compute_mae(dim_name, test_dim, records)
            if mae < best_mae:
                best_mae = mae
                best_dim = test_dim

        return best_dim, best_mae

    @staticmethod
    def _generate_grid_combinations(
        grid_config: dict[str, list[float]]
    ) -> list[tuple[float, ...]]:
        """Generate grid-search parameter combinations as a Cartesian product."""
        keys = list(grid_config.keys())
        if not keys:
            return [()]

        result = [(v,) for v in grid_config[keys[0]]]
        for key in keys[1:]:
            new_result = []
            for combo in result:
                for v in grid_config[key]:
                    new_result.append(combo + (v,))
            result = new_result
        return result
