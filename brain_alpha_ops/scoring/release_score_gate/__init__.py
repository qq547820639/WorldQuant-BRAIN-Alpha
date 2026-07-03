"""Release scoring gate that preserves official BRAIN metric values.

Re-export from the ``release_score_gate`` subpackage for backward compatibility.

Split from the former ``brain_alpha_ops/scoring/release_score_gate.py`` monolith
(deep-optimization-phase13) into responsibility-focused submodules:
``_models``, ``_checks``, ``_decision``, and ``_helpers`` (now consolidated into
``release_score_gate.py``). Public API and any private symbols referenced by
tests are re-exported here so existing imports of
``brain_alpha_ops.scoring.release_score_gate`` continue to resolve.
"""
from __future__ import annotations

from brain_alpha_ops.scoring.release_score_gate.release_score_gate import (  # noqa: F401
    _cmp_optional_max,
    _cmp_required_max,
    _cmp_required_min,
    _missing_sub_universe_threshold_inputs,
    _official_pass_attr,
    _sub_universe_sharpe_attr,
    _sub_universe_sharpe_threshold,
    _threshold_trace,
    decide_release,
    evaluate_release_score,
    _brain_check_value,
    _iter_delay_values,
    _metric,
    _metric_with_check_fallback,
    _settings_delay,
    _settings_delay_with_source,
    RELEASE_SCORE_GATE_SCHEMA,
    GateDecision,
    OfficialSnapshot,
    ScoreAttribution,
    ThresholdPolicy,
)

__all__ = [
    "RELEASE_SCORE_GATE_SCHEMA",
    "OfficialSnapshot",
    "ThresholdPolicy",
    "ScoreAttribution",
    "GateDecision",
    "decide_release",
    "evaluate_release_score",
]
