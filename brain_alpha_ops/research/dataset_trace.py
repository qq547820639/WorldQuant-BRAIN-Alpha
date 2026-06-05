"""Dataset ID full-chain trace validator — ensures dataset_id is never lost.

This module provides a validator that checks every Candidate object in the
pipeline for proper dataset_id assignment, preventing the "system selection
disconnect" problem where candidates are generated without a dataset context.

Architecture: the validator traces dataset_id through all pipeline stages:
  Generation → Local Prefilter → Pool Merge → Scoring → Validation → Submission

Usage::

    from brain_alpha_ops.research.dataset_trace import DatasetTraceValidator
    validator = DatasetTraceValidator(official_datasets=["model77", "analyst4"])
    report = validator.validate_candidates(candidates)
    if not report.all_valid:
        fixed = validator.auto_fix_missing(candidates, default_dataset_id="model77")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from brain_alpha_ops.models import Candidate


@dataclass
class DatasetTraceReport:
    """Report of dataset_id tracing across candidates."""

    total: int = 0
    with_dataset: int = 0
    without_dataset: int = 0
    valid_dataset: int = 0
    invalid_dataset: int = 0
    all_valid: bool = False
    missing_ids: list[str] = field(default_factory=list)
    invalid_ids: list[str] = field(default_factory=list)
    fixed_count: int = 0
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "with_dataset": self.with_dataset,
            "without_dataset": self.without_dataset,
            "valid_dataset": self.valid_dataset,
            "invalid_dataset": self.invalid_dataset,
            "all_valid": self.all_valid,
            "missing_ids": self.missing_ids[:10],
            "invalid_ids": self.invalid_ids[:10],
            "fixed_count": self.fixed_count,
        }


class DatasetTraceValidator:
    """Validates and repairs dataset_id across the full candidate lifecycle.

    Responsibilities:
    1. Check that every Candidate has a non-empty dataset_id.
    2. Verify that each dataset_id exists in the official dataset list.
    3. Auto-fix missing IDs with the active dataset or a reasonable default.
    4. Generate trace reports for pipeline observability.

    Zero hardcoded datasets — all valid datasets come from official sources.
    """

    def __init__(
        self,
        *,
        official_datasets: list[str] | None = None,
        active_dataset_id: str = "",
    ) -> None:
        self._official: set[str] = set(official_datasets or [])
        self._active = str(active_dataset_id or "")

    def update_official_datasets(self, datasets: list[str]) -> None:
        """Update the set of known official dataset IDs."""
        self._official = {str(d) for d in datasets if d}

    def update_active_dataset(self, dataset_id: str) -> None:
        """Update the currently active dataset ID."""
        self._active = str(dataset_id or "")

    def validate_candidates(
        self,
        candidates: list["Candidate"],
        *,
        require_official: bool = True,
    ) -> DatasetTraceReport:
        """Validate dataset_id across all candidates.

        Args:
            candidates: list of Candidate objects to validate.
            require_official: if True, also verify dataset is in official list.

        Returns:
            DatasetTraceReport with validation results.
        """
        report = DatasetTraceReport(total=len(candidates))
        missing: list[str] = []
        invalid: list[str] = []

        for candidate in candidates:
            ds = str(getattr(candidate, "dataset_id", "") or "").strip()

            if not ds:
                report.without_dataset += 1
                missing.append(getattr(candidate, "alpha_id", "unknown"))
            else:
                report.with_dataset += 1
                if require_official and self._official and ds not in self._official:
                    report.invalid_dataset += 1
                    invalid.append(f"{getattr(candidate, 'alpha_id', '?')}:{ds}")
                else:
                    report.valid_dataset += 1

        report.missing_ids = missing
        report.invalid_ids = invalid
        report.all_valid = (
            report.without_dataset == 0
            and (not require_official or report.invalid_dataset == 0)
        )
        report.details = {
            "official_datasets": sorted(self._official),
            "active_dataset": self._active,
        }
        return report

    def auto_fix_missing(
        self,
        candidates: list["Candidate"],
        *,
        default_dataset_id: str = "",
        fix_invalid: bool = False,
    ) -> tuple[list["Candidate"], DatasetTraceReport]:
        """Auto-fix candidates with missing or invalid dataset_id.

        Args:
            candidates: list of Candidate objects to fix.
            default_dataset_id: fallback if no active dataset set.
            fix_invalid: also fix invalid (non-official) dataset IDs.

        Returns:
            (fixed_candidates, fix_report)
        """
        ds_id = self._active or str(default_dataset_id or "").strip()
        if not ds_id:
            return candidates, DatasetTraceReport(
                total=len(candidates), all_valid=False,
                details={"error": "no active or default dataset_id available for auto-fix"},
            )

        fixed = 0
        for candidate in candidates:
            current = str(getattr(candidate, "dataset_id", "") or "").strip()

            if not current:
                candidate.dataset_id = ds_id
                fixed += 1
            elif fix_invalid and self._official and current not in self._official:
                candidate.dataset_id = ds_id
                fixed += 1

        report = self.validate_candidates(candidates)
        report.fixed_count = fixed
        return candidates, report

    def check_candidate(
        self,
        candidate: "Candidate",
        *,
        raise_on_missing: bool = False,
    ) -> bool:
        """Check a single candidate's dataset_id.

        Args:
            candidate: the Candidate to check.
            raise_on_missing: if True, raise ValueError when dataset_id is missing.

        Returns:
            True if dataset_id is present and valid.

        Raises:
            ValueError: if raise_on_missing is True and dataset_id is missing/invalid.
        """
        ds = str(getattr(candidate, "dataset_id", "") or "").strip()

        if not ds:
            if raise_on_missing:
                raise ValueError(
                    f"Candidate {getattr(candidate, 'alpha_id', 'unknown')} "
                    f"is missing dataset_id"
                )
            return False

        if self._official and ds not in self._official:
            if raise_on_missing:
                raise ValueError(
                    f"Candidate {getattr(candidate, 'alpha_id', 'unknown')} "
                    f"has invalid dataset_id '{ds}' (not in official list: "
                    f"{sorted(self._official)})"
                )
            return False

        return True

    def compute_dataset_coverage(self, candidates: list["Candidate"]) -> dict[str, int]:
        """Compute how many candidates use each dataset.

        Returns:
            dict mapping dataset_id → count.
        """
        from collections import Counter

        counter: Counter[str] = Counter()
        for candidate in candidates:
            ds = str(getattr(candidate, "dataset_id", "") or "").strip()
            if ds:
                counter[ds] += 1
        return dict(counter.most_common())

    def get_missing_dataset_candidates(
        self,
        candidates: list["Candidate"],
    ) -> list["Candidate"]:
        """Return candidates that are missing dataset_id."""
        return [
            c for c in candidates
            if not str(getattr(c, "dataset_id", "") or "").strip()
        ]
