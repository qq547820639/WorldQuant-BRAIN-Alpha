"""Deprecated default classes split out of ``runtime_constants`` for line-budget compliance.

These two classes are retained solely for backward compatibility with
``tests/test_runtime_constants.py``. They are re-exported from
``brain_alpha_ops.runtime_constants`` so existing imports continue to work.

.. deprecated:: 0.3.1
    Target removal: v0.4 (2026-Q3). Use ``ScoringConfig`` and ``ResearchBudget``
    from ``brain_alpha_ops.config_models`` instead.
"""

from __future__ import annotations


# ═══════════════════════════════════════════════════════════════════════════
# Scoring / pipeline defaults
# ═══════════════════════════════════════════════════════════════════════════

class ScoringDefaults:
    """Defaults for the scoring system and quality gates.

    .. deprecated:: 0.3.1
        Target removal: v0.4 (2026-Q3).  Use ``ScoringConfig`` from ``brain_alpha_ops.config_models`` instead.
        This class is retained only for backward compatibility with
        ``tests/test_runtime_constants.py`` and will be removed in v0.4.
        The authoritative defaults now live in ``config_models.ScoringConfig``.
    """

    DEFAULT_PRIOR_LAYER_WEIGHT: float = 0.30
    DEFAULT_EMPIRICAL_LAYER_WEIGHT: float = 0.45
    DEFAULT_CHECKLIST_LAYER_WEIGHT: float = 0.25
    DEFAULT_LOCAL_PRIOR_WEIGHT: float = 0.65
    DEFAULT_LOCAL_QUALITY_WEIGHT: float = 0.35
    DEFAULT_SUBMIT_THRESHOLD: float = 85.0
    DEFAULT_OPTIMIZE_THRESHOLD: float = 70.0
    DEFAULT_RESEARCH_THRESHOLD: float = 50.0
    ASSISTANT_BONUS_CAP: float = 4.0
    ASSISTANT_PENALTY_CAP: float = 5.0


class PipelineDefaults:
    """Defaults for the alpha research pipeline.

    .. deprecated:: 0.3.1
        Target removal: v0.4 (2026-Q3).  Use ``ResearchBudget`` from ``brain_alpha_ops.config_models`` instead.
        This class is retained only for backward compatibility with
        ``tests/test_runtime_constants.py`` and will be removed in v0.4.
        The authoritative defaults now live in ``config_models.ResearchBudget``.
    """

    DEFAULT_MAX_CANDIDATES_PER_CYCLE: int = 20
    DEFAULT_MAX_VALIDATIONS_PER_CYCLE: int = 10
    DEFAULT_MAX_SIMULATIONS_PER_CYCLE: int = 3
    DEFAULT_RETAINED_POOL_SIZE: int = 10
    DEFAULT_BACKTEST_BATCH_SIZE: int = 3
    DEFAULT_MIN_LOCAL_QUALITY: float = 4.0
    DEFAULT_CYCLE_PAUSE_SECONDS: float = 2.0
    DEFAULT_MAX_CYCLES: int = 10
    CONVERGENCE_STALL_CYCLES: int = 5
