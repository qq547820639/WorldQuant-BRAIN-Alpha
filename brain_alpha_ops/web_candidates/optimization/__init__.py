"""Local-only candidate optimization for the Web candidate pool.

Subpackage split (formerly ``optimization.py`` monolith):
  - ``_helpers``       : candidate inspection utilities and conversion helpers
  - ``_explainability``: optimization explanation and expression proof builders
  - ``_prepare``       : optimized candidate preparation pipeline
  - ``_summary``       : summary builders for candidate optimization results
  - ``_payload``       : main orchestration for local candidate optimization
"""

from __future__ import annotations

from brain_alpha_ops.research.local_backtest_engine import LocalBacktestEngine

from ._helpers import (
    _candidate_blocking_codes,
    _candidate_needs_optimization,
    _candidate_rejected_by_local_gate,
    _candidate_rejection_reasons,
    _candidate_score,
    _candidate_submission_ready,
    _expression_key,
    _int_list,
    _is_submit_only_blocker,
    _optional_float,
    _optional_int,
    _rejected_reason_counts,
    _string_list,
)
from ._explainability import (
    _attach_expression_proof,
    _attach_optimization_explanation,
    _expression_change_summary,
    _mark_official_context_proof_failed,
    _official_context_explanation,
    _optimization_explanation,
    _optimizer_trace,
    _source_tags,
)
from ._prepare import _prepare_optimized_candidate
from ._summary import (
    _all_candidate_rows,
    _summary,
    _target_pool_size,
)
from ._payload import (
    ParameterSearchFactory,
    RepositoryFactory,
    RunConfigFromPayload,
    _rank_rework_sources,
    _resolve_dataset_id,
    _source_candidates,
    candidates_ledger_path,
    optimize_candidates_payload,
    persist_optimized_candidates,
)

__all__ = [
    # Type aliases
    "RunConfigFromPayload",
    "RepositoryFactory",
    "ParameterSearchFactory",
    # External class re-export (supports monkeypatch on package attribute)
    "LocalBacktestEngine",
    # Public API
    "optimize_candidates_payload",
    "persist_optimized_candidates",
    "candidates_ledger_path",
    # Private helpers (re-exported for backward compatibility)
    "_candidate_needs_optimization",
    "_candidate_submission_ready",
    "_candidate_rejected_by_local_gate",
    "_candidate_rejection_reasons",
    "_rejected_reason_counts",
    "_candidate_score",
    "_optional_float",
    "_optional_int",
    "_string_list",
    "_int_list",
    "_candidate_blocking_codes",
    "_is_submit_only_blocker",
    "_expression_key",
    "_attach_expression_proof",
    "_attach_optimization_explanation",
    "_optimization_explanation",
    "_expression_change_summary",
    "_official_context_explanation",
    "_optimizer_trace",
    "_mark_official_context_proof_failed",
    "_source_tags",
    "_prepare_optimized_candidate",
    "_summary",
    "_all_candidate_rows",
    "_target_pool_size",
    "_resolve_dataset_id",
    "_source_candidates",
    "_rank_rework_sources",
]
