"""``AutoCalibrator`` — the public calibrator class.

Extracted from the original ``auto_calibrator.py``; composes the scoring,
grid-search, and weight-calibration mixins into the final public class.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from brain_alpha_ops.jsonl import count_jsonl_records, read_jsonl_records
from brain_alpha_ops.research.scoring_params import ScoringParams

from ._grid_search import _GridSearchMixin
from ._scoring import _ScoringMixin
from ._weight_calibration import _WeightCalibrationMixin

# Preserve the original logger name exactly as ``__name__`` would have
# produced in the monolithic module.
logger = logging.getLogger("brain_alpha_ops.research.auto_calibrator")


class AutoCalibrator(_ScoringMixin, _GridSearchMixin, _WeightCalibrationMixin):
    """Automatically calibrate scoring parameters to reduce prior-vs-empirical error.

    Responsibilities:
    1. Read official backtest records from alpha_features.jsonl.
    2. Detect whether enough new samples are available.
    3. Grid-search tunable parameters for each dimension.
    4. Run dimension-weight and layer-weight calibration.
    5. Persist calibration results to scoring_calibration.json.

    P1-6: calibration sample-size gate
    - MIN_CALIBRATION_SAMPLES = 30, requiring at least 30 official BRAIN PASS records.
    - Insufficient samples return calibrated=False plus diagnostic details.
    - The pipeline emits a "calibration deferred" event without blocking the main flow.
    """

    # P1-6: calibration trigger raised to 30 for statistical reliability.
    MIN_CALIBRATION_SAMPLES: int = 30
    CALIBRATION_HISTORY_LIMIT: int = 1000

    # Grid-search step configuration per dimension.
    GRID_SEARCH_CONFIG: dict[str, dict[str, list[float]]] = {
        "structure": {
            "penalty_per_unit": [6.0, 7.0, 8.0, 9.0, 10.0],
            "penalty_threshold": [3.0, 4.0, 5.0],
            "base_score": [85.0, 90.0, 95.0],
            "floor": [15.0, 20.0, 25.0, 30.0],
        },
        "field_operator_support": {
            "base_score": [38.0, 42.0, 46.0],
            "bonus_per_unit": [6.0, 8.0, 10.0],
        },
        "horizon_turnover_proxy": {
            "threshold_low": [3.0, 5.0, 8.0],
            "threshold_high": [60.0, 90.0, 120.0],
            "score_in_range": [78.0, 82.0, 86.0],
            "score_out_range": [62.0, 68.0, 74.0],
            "score_no_data": [42.0, 50.0, 58.0],
        },
        "risk_control_proxy": {
            "tier_3_score": [80.0, 84.0, 88.0],
            "tier_2_score": [60.0, 66.0, 72.0],
            "tier_1_score": [42.0, 48.0, 54.0],
        },
        "diversity": {
            "high_score": [75.0, 80.0, 85.0],
            "low_score": [55.0, 60.0, 65.0, 70.0],
        },
        "explainability": {
            "threshold_high": [120.0, 140.0, 160.0],
            "score_in_range": [80.0, 85.0, 90.0],
            "score_out_range": [55.0, 60.0, 65.0],
        },
        "data_compliance": {
            "high_score": [78.0, 82.0, 86.0],
            "low_score": [25.0, 30.0, 35.0, 40.0],
        },
    }

    def __init__(self, storage_dir: str = "data"):
        self._storage_dir = storage_dir
        self._params: ScoringParams | None = None
        self._last_calibrated_count: int = 0
        self._load_existing()

    # Public API

    def needs_calibration(self) -> bool:
        """Check whether enough new samples are available for calibration.

        Conditions: PASS records in alpha_features.jsonl >= MIN_CALIBRATION_SAMPLES
        and new PASS records since the last calibration >= MIN_CALIBRATION_SAMPLES.
        """
        passing_count = self._count_passing_records()
        new_since_last = passing_count - self._last_calibrated_count
        return passing_count >= self.MIN_CALIBRATION_SAMPLES and new_since_last >= self.MIN_CALIBRATION_SAMPLES

    def calibrate(self) -> dict[str, Any]:
        """Execute the full calibration flow.

        1. Load the baseline defaults.
        2. Load PASS records.
        3. Grid-search optimized parameters for each dimension.
        4. Calibrate dimension weights.
        5. Calibrate layer weights.
        6. Persist results.

        Returns a calibration report dict.
        """
        baseline = ScoringParams.defaults()
        total_pass_records = self._count_passing_records()
        records = self._load_passing_records(limit=self.CALIBRATION_HISTORY_LIMIT)

        if total_pass_records < self.MIN_CALIBRATION_SAMPLES:
            deficit = self.MIN_CALIBRATION_SAMPLES - total_pass_records
            return {
                "calibrated": False,
                "status": "insufficient_samples",
                "error": f"insufficient samples: {total_pass_records} < {self.MIN_CALIBRATION_SAMPLES}",
                "sample_size": len(records),
                "total_pass_records": total_pass_records,
                "required": self.MIN_CALIBRATION_SAMPLES,
                "deficit": deficit,
                "summary": (
                    f"Calibration deferred: {total_pass_records} PASS records available, "
                    f"need {deficit} more (minimum {self.MIN_CALIBRATION_SAMPLES}). "
                    f"Using default/experience weights until threshold is met."
                ),
            }

        # Grid-search each calibratable dimension.
        optimized_dims = {}
        dim_reports = {}
        for dim_name, grid_config in self.GRID_SEARCH_CONFIG.items():
            if dim_name not in baseline.dimensions:
                continue
            base_dim = baseline.dimensions[dim_name]
            best_dim, best_mae = self._grid_search_dimension(
                dim_name, base_dim, grid_config, records
            )
            optimized_dims[dim_name] = best_dim
            dim_reports[dim_name] = {
                "original_mae": self._compute_mae(dim_name, base_dim, records),
                "optimized_mae": best_mae,
                "improvement": round(
                    self._compute_mae(dim_name, base_dim, records) - best_mae, 2
                ),
            }

        # Copy dimensions that were not optimized.
        for dim_name, dim in baseline.dimensions.items():
            if dim_name not in optimized_dims:
                optimized_dims[dim_name] = dim

        # Calibrate dimension weights.
        dim_weight_report = self._calibrate_dimension_weights(records)

        # Calibrate layer weights.
        layer_weight_report = self._calibrate_layer_weights(records)

        # Build final parameters.
        params = ScoringParams(
            dimensions=optimized_dims,
            layer_weights=layer_weight_report.get("optimized_weights", baseline.layer_weights),
            calibrated_at=datetime.now(timezone.utc).isoformat(),
        )

        # Update dimension weights.
        if "optimized_weights" in dim_weight_report:
            for dim_name, weight in dim_weight_report["optimized_weights"].items():
                if dim_name in params.dimensions:
                    params.dimensions[dim_name].weight = weight

        # Compute overall quality.
        overall_mae = self._compute_overall_mae(params, records)
        baseline_mae = self._compute_overall_mae(baseline, records)
        params.calibration_quality = {
            "r_squared": dim_weight_report.get("r_squared", 0.0),
            "mean_abs_error": round(overall_mae, 2),
            "sample_size": len(records),
            "total_pass_records": total_pass_records,
            "calibration_history_limit": self.CALIBRATION_HISTORY_LIMIT,
            "baseline_mae": round(baseline_mae, 2),
            "improvement_pct": round((baseline_mae - overall_mae) / max(baseline_mae, 0.01) * 100, 1),
        }

        # Persist calibration output.
        params.save(self._storage_dir)
        self._params = params
        self._last_calibrated_count = total_pass_records

        return {
            "calibrated": True,
            "sample_size": len(records),
            "total_pass_records": total_pass_records,
            "calibration_history_limit": self.CALIBRATION_HISTORY_LIMIT,
            "calibrated_at": params.calibrated_at,
            "calibration_quality": params.calibration_quality,
            "dimension_reports": dim_reports,
            "dimension_weights": dim_weight_report,
            "layer_weights": layer_weight_report,
            "summary": (
                f"Calibrated with {len(records)} records. "
                f"Overall MAE: {baseline_mae:.1f} → {overall_mae:.1f} "
                f"({params.calibration_quality['improvement_pct']:.1f}% improvement). "
                f"R²={params.calibration_quality['r_squared']:.4f}."
            ),
        }

    def apply(self, scoring_config: Any) -> Any:
        """Apply calibration results to a ScoringConfig.

        P3-18 (2026-06-13): rewritten to return a *new* ScoringConfig
        instance (via ``dataclasses.replace``) instead of mutating the
        passed-in object. The previous implementation directly assigned
        to ``scoring_config.prior_weights_override`` etc., which would
        raise ``FrozenInstanceError`` if ScoringConfig were ever made
        ``frozen=True`` and which silently violated the dataclass's
        intent that ScoringConfig is an immutable policy object.

        Callers that used to do ``config.scoring = auto_calibrator.apply(config.scoring)``
        keep working because we now return the new instance. Callers that
        did ``auto_calibrator.apply(config.scoring)`` *without* rebinding
        should be updated to::

            config.scoring = auto_calibrator.apply(config.scoring)

        Args:
            scoring_config: ScoringConfig instance (unchanged)

        Returns:
            A new ScoringConfig with calibrated layer weights and the
            prior-weights override applied.
        """
        import dataclasses

        params = self._params or ScoringParams.defaults()
        return dataclasses.replace(
            scoring_config,
            prior_weights_override=params.get_weights_override(),
            prior_layer_weight=params.layer_weights.get("prior", 0.30),
            empirical_layer_weight=params.layer_weights.get("empirical", 0.45),
            checklist_layer_weight=params.layer_weights.get("checklist", 0.25),
        )

    @property
    def params(self) -> ScoringParams:
        """Return current calibration parameters, defaulting when uncalibrated."""
        return self._params or ScoringParams.defaults()

    # Internal helpers

    def _load_existing(self) -> None:
        """Load an existing calibration file."""
        self._params = ScoringParams.load(self._storage_dir)
        if self._params:
            quality = self._params.calibration_quality
            self._last_calibrated_count = int(quality.get("total_pass_records") or quality.get("sample_size") or 0)

    def _load_passing_records(self, *, limit: int | None = CALIBRATION_HISTORY_LIMIT) -> list[dict[str, Any]]:
        """Load recent PASS records used as the calibration sample."""
        filepath = os.path.join(self._storage_dir, "alpha_features.jsonl")
        if not os.path.exists(filepath):
            return []

        return [
            record
            for record in read_jsonl_records(filepath, limit=limit)
            if record.get("pass_fail") == "PASS"
        ]

    def _count_passing_records(self) -> int:
        filepath = os.path.join(self._storage_dir, "alpha_features.jsonl")
        if not os.path.exists(filepath):
            return 0
        return count_jsonl_records(filepath, predicate=lambda record: record.get("pass_fail") == "PASS")
