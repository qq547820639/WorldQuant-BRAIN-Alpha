"""HypothesisLibrary — YAML-based loading, querying, and experience-weight management.

Extracted from the original ``hypothesis_library.py`` monolith. Provides
the ``HypothesisLibrary`` class that scans a directory of YAML files,
indexes hypotheses by ID and category, and applies adaptive EMA weight
updates driven by pipeline feedback.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from brain_alpha_ops.redaction import redact_error_message, redact_text

from ._file_repair import ensure_hypothesis_library_files, _safe_load_yaml
from .models import Hypothesis

logger = logging.getLogger(__name__)


class HypothesisLibrary:
    """Loads, indexes, and manages hypothesis definitions from YAML files.

    Usage::

        lib = HypothesisLibrary("brain_alpha_ops/research/hypotheses").load_all()
        all_h = lib.get_all()
        h = lib.get_by_id("earnings_revision_momentum")
        lib.update_weights("earnings_revision_momentum",
                           field_cat_weights={"earnings_estimate_revision": 1.5})
    """

    def __init__(self, directory: str | Path) -> None:
        self._directory: Path = Path(directory)
        self._hypotheses: dict[str, Hypothesis] = {}
        self._by_category: dict[str, list[Hypothesis]] = {}
        self._file_paths: dict[str, Path] = {}
        self._hypothesis_weights: dict[str, float] = {}

    # ── Loading ──────────────────────────────────────────────────────

    def load_all(self) -> "HypothesisLibrary":
        """Scan the hypothesis directory and load all .yaml files.

        Skips _schema.yaml and files starting with '_'.
        Returns self for method chaining.
        """
        ensure_hypothesis_library_files(self._directory)
        if not self._directory.exists():
            logger.warning("HypothesisLibrary: directory %s does not exist.", self._directory)
            return self

        self._hypotheses.clear()
        self._by_category.clear()
        self._file_paths.clear()

        yaml_files = sorted(
            p for p in self._directory.rglob("*.yaml")
            if not p.name.startswith("_")
        )
        for path in yaml_files:
            try:
                hypothesis = self._load_file(path)
                if hypothesis and hypothesis.id:
                    self._hypotheses[hypothesis.id] = hypothesis
                    self._file_paths[hypothesis.id] = path
                    cat = hypothesis.category.lower()
                    self._by_category.setdefault(cat, []).append(hypothesis)
            except Exception as exc:
                logger.error(
                    "HypothesisLibrary: failed to load %s: %s",
                    redact_text(path, max_length=180),
                    redact_error_message(exc),
                )

        self._validate_weights()
        logger.info(
            "HypothesisLibrary: loaded %d hypotheses from %s",
            len(self._hypotheses), self._directory,
        )
        return self

    def reload(self) -> "HypothesisLibrary":
        """Re-load all hypothesis files from disk, discarding runtime weight changes."""
        return self.load_all()

    # ── Query ────────────────────────────────────────────────────────

    def get_all(self) -> list[Hypothesis]:
        """Return all loaded hypotheses."""
        return list(self._hypotheses.values())

    def get_by_id(self, hypothesis_id: str) -> Hypothesis | None:
        """Return a hypothesis by its unique ID, or None."""
        return self._hypotheses.get(hypothesis_id)

    def get_by_category(self, category: str) -> list[Hypothesis]:
        """Return all hypotheses matching *category* (case-insensitive)."""
        return list(self._by_category.get(category.lower(), []))

    def get_ids(self) -> list[str]:
        """Return all hypothesis IDs."""
        return list(self._hypotheses.keys())

    @property
    def count(self) -> int:
        """Number of loaded hypotheses."""
        return len(self._hypotheses)

    # ── Weight Management ────────────────────────────────────────────

    def update_weights(
        self,
        hypothesis_id: str,
        field_cat_weights: dict[str, float] | None = None,
        expr_fam_weights: dict[str, float] | None = None,
        window_weights: dict[str, float] | None = None,
        *,
        sample_count: int | None = None,
    ) -> None:
        """Update experience weights using adaptive EMA smoothing::

            new = (1 - alpha) * old + alpha * update

        P2-16 (2026-06-13): ``alpha`` is no longer a fixed 0.2; it shrinks
        with the cumulative sample count so the EMA becomes a slow learner
        once the model has seen enough data::

            alpha = base_alpha / (1 + decay * sample_count)

        With ``base_alpha=0.2`` and ``decay=0.01`` the schedule is:
        - sample 1     → alpha ≈ 0.20   (responsive early)
        - sample 50    → alpha ≈ 0.10   (slowing down)
        - sample 200+  → alpha ≈ 0.05   (slow learner)

        The base value matches the previous fixed alpha so callers that
        don't pass ``sample_count`` see no behavior change.

        Parameters
        ----------
        hypothesis_id:
            ID of the hypothesis to update.
        field_cat_weights:
            Mapping of field category name → winner ratio (0.0–1.0).
        expr_fam_weights:
            Mapping of expression family ID → winner ratio (0.0–1.0).
        window_weights:
            Mapping of window (as int key) → winner ratio (0.0–1.0).
            Keys are automatically converted to str for internal storage.
        sample_count:
            Number of historical samples available for this hypothesis.
            When provided, the EMA alpha shrinks as above. When omitted
            the legacy fixed 0.2 alpha is used.
        """
        hyp = self._hypotheses.get(hypothesis_id)
        if hyp is None:
            logger.warning("HypothesisLibrary.update_weights: hypothesis '%s' not found.", hypothesis_id)
            return

        if sample_count is None:
            alpha = 0.2  # legacy fixed factor (P2-16 fallback)
        else:
            base_alpha = 0.2
            decay = 0.01
            alpha = max(0.05, min(0.5, base_alpha / (1.0 + decay * max(0, sample_count))))
        retain = 1.0 - alpha  # weight retained from the previous estimate

        # Update field category weights
        if field_cat_weights:
            for fc in hyp.field_categories:
                update = field_cat_weights.get(fc.category)
                if update is not None:
                    fc.weight = retain * fc.weight + alpha * max(0.0, min(1.0, float(update)))
                    hyp.experience_weights.field_category_weights[fc.category] = fc.weight

        # Update expression family weights
        if expr_fam_weights:
            for ef in hyp.expression_families:
                update = expr_fam_weights.get(ef.id)
                if update is not None:
                    ef.weight = retain * ef.weight + alpha * max(0.0, min(1.0, float(update)))
                    hyp.experience_weights.expression_family_weights[ef.id] = ef.weight

        # Update window weights
        if window_weights:
            raw_windows: dict[int, float] = {}
            for k, v in window_weights.items():
                w_val = int(k) if isinstance(k, str) else k
                raw_windows[w_val] = max(0.0, min(1.0, float(v)))
            for ef in hyp.expression_families:
                for w in ef.windows:
                    update = window_weights.get(w) or window_weights.get(str(w))
                    if update is not None:
                        key = str(w)
                        old = hyp.experience_weights.window_weights.get(key, 1.0)
                        new_val = retain * old + alpha * max(0.0, min(1.0, float(update)))
                        hyp.experience_weights.window_weights[key] = new_val

        # Update overall weight as average of expression family weights
        if hyp.expression_families:
            avg_weight = sum(ef.weight for ef in hyp.expression_families) / len(hyp.expression_families)
            hyp.experience_weights.overall = retain * hyp.experience_weights.overall + alpha * avg_weight

        self._validate_weights()

    # ── Internals ────────────────────────────────────────────────────

    def _load_file(self, path: Path) -> Hypothesis | None:
        """Load a single hypothesis YAML file and return a Hypothesis object."""
        with open(path, "r", encoding="utf-8") as f:
            raw: dict[str, Any] = _safe_load_yaml(f.read()) or {}

        if not isinstance(raw, dict) or "hypothesis" not in raw:
            logger.warning(
                "HypothesisLibrary._load_file: %s missing top-level 'hypothesis' key.",
                redact_text(path, max_length=180),
            )
            return None

        hyp = Hypothesis.from_dict(raw)
        if not hyp.id:
            logger.warning(
                "HypothesisLibrary._load_file: %s has empty 'id'.",
                redact_text(path, max_length=180),
            )
            return None
        return hyp

    def adjust_weight(self, hypothesis_name: str, factor: float) -> float:
        """Adjust hypothesis weight by *factor* (multiplicative).

        Called by the pipeline after prefilter evaluation:
        - factor < 1.0: penalize (e.g. 0.5 for prod_correlation failure)
        - factor > 1.0: reward   (e.g. 1.1 for a diverse candidate)

        Returns the new weight (clamped to [0.1, 5.0]).
        """
        old = self._hypothesis_weights.get(hypothesis_name, 1.0)
        new = max(0.1, min(5.0, old * factor))
        if abs(new - old) > 0.001:
            self._hypothesis_weights[hypothesis_name] = new
            self._validate_weights()
        return new

    def get_hypothesis_weight(self, hypothesis_name: str) -> float:
        """Return the feedback-adjusted weight for *hypothesis_name*.

        Closes the feedback loop with :meth:`adjust_weight`: the generate
        path (``HypothesisSelector``) reads this to bias hypothesis
        selection probability — penalised hypotheses become less likely
        to be selected, rewarded ones more likely. Returns 1.0 (neutral)
        when no feedback has been recorded for the hypothesis.
        """
        return self._hypothesis_weights.get(hypothesis_name, 1.0)

    def _validate_weights(self) -> None:
        """Ensure all experience weights are non-negative."""
        for hyp in self._hypotheses.values():
            ew = hyp.experience_weights
            ew.overall = max(0.0, ew.overall)
            for fc in hyp.field_categories:
                fc.weight = max(0.0, fc.weight)
            for ef in hyp.expression_families:
                ef.weight = max(0.0, ef.weight)
            ew.field_category_weights = {k: max(0.0, v) for k, v in ew.field_category_weights.items()}
            ew.expression_family_weights = {k: max(0.0, v) for k, v in ew.expression_family_weights.items()}
            ew.window_weights = {k: max(0.0, v) for k, v in ew.window_weights.items()}
