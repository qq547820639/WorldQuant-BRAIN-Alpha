"""Re-export from the ``memory`` subpackage.

The original monolithic ``memory.py`` was split into:
  - ``_helpers`` : private statistical helpers used by ``ResearchMemory``
  - ``_memory``  : the ``ResearchMemory`` class itself

This file re-exports the full public API surface so legacy imports
``from brain_alpha_ops.research.memory import ResearchMemory`` continue to
work, and re-exports the private helper symbols so tests that monkeypatch
``brain_alpha_ops.research.memory._xxx`` keep functioning.
"""

from __future__ import annotations

from brain_alpha_ops.research.memory._memory import ResearchMemory  # noqa: F401
from brain_alpha_ops.research.memory._helpers import (  # noqa: F401
    _as_list,
    _candidate_guidance_digest,
    _clamp,
    _clean_reason,
    _failure_reasons,
    _finalize_stat_bucket,
    _guidance_outcome_status,
    _has_generator_bias,
    _is_success,
    _is_weak_guidance_outcome,
    _metrics_for,
    _num,
    _parse_window,
    _rank_buckets,
    _rank_guidance_buckets,
    _recommendations,
    _score_for,
    _stat_bucket,
    _top_field_combinations,
    _top_windows,
    _truthy,
    _update_bucket,
)

__all__ = [
    "ResearchMemory",
    # Private helpers re-exported for test monkeypatch compatibility.
    "_as_list",
    "_candidate_guidance_digest",
    "_clamp",
    "_clean_reason",
    "_failure_reasons",
    "_finalize_stat_bucket",
    "_guidance_outcome_status",
    "_has_generator_bias",
    "_is_success",
    "_is_weak_guidance_outcome",
    "_metrics_for",
    "_num",
    "_parse_window",
    "_rank_buckets",
    "_rank_guidance_buckets",
    "_recommendations",
    "_score_for",
    "_stat_bucket",
    "_top_field_combinations",
    "_top_windows",
    "_truthy",
    "_update_bucket",
]
