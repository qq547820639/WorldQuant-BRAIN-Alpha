"""Re-export from the ``context`` subpackage for backward compatibility.

The original monolithic ``context.py`` was split into the
``brain_alpha_ops.research.context`` subpackage. This module re-exports
the full public API surface so legacy imports continue to work.

Sub-modules:
  - ``_pack``        : ``build_assistant_context_pack`` main entry +
                       ``ASSISTANT_CONTEXT_SENSITIVE_KEY_FRAGMENTS`` +
                       ``_redact_assistant_context_pack``
  - ``_sections``    : section builders + ``render_context_prompt``
  - ``_helpers``     : storage access, brief builders, join/format utilities
  - ``_compliance``  : ``_compliance_context``
"""
from __future__ import annotations

# Re-export everything from sub-modules
from brain_alpha_ops.research.context._pack import (  # noqa: F401
    ASSISTANT_CONTEXT_SENSITIVE_KEY_FRAGMENTS,
    _redact_assistant_context_pack,
    build_assistant_context_pack,
)
from brain_alpha_ops.research.context._sections import (  # noqa: F401
    _cloud_context,
    _expression_index_context,
    _generation_focus,
    _latest_result_context,
    _memory_context,
    _next_actions,
    _prompt_diagnostics,
    _risk_controls,
    _run_config_context,
    render_context_prompt,
)
from brain_alpha_ops.research.context._helpers import (  # noqa: F401
    _backtest_brief,
    _backtest_record_brief,
    _candidate_brief,
    _cloud_alpha_brief,
    _cloud_pass_fail,
    _cloud_snapshot_from_storage,
    _dataclass_dict,
    _expression_from_row,
    _first_dict,
    _first_list,
    _float_value,
    _guidance_outcomes,
    _int_value,
    _join_candidate_briefs,
    _join_duplicate_expressions,
    _join_failures,
    _join_field_combinations,
    _join_guidance_outcomes,
    _join_stat_bucket,
    _join_text_items,
    _latest_result_from_storage,
    _read_jsonl,
    _strong_guidance_outcome,
    _unique_text_items,
    _weak_guidance_outcome,
)
from brain_alpha_ops.research.context._compliance import _compliance_context  # noqa: F401

__all__ = [
    # Top-level API
    "build_assistant_context_pack",
    "render_context_prompt",
    "ASSISTANT_CONTEXT_SENSITIVE_KEY_FRAGMENTS",
    # Compliance
    "_compliance_context",
    # Sections
    "_run_config_context",
    "_latest_result_context",
    "_cloud_context",
    "_memory_context",
    "_expression_index_context",
    "_generation_focus",
    "_risk_controls",
    "_next_actions",
    "_prompt_diagnostics",
    # Helpers
    "_redact_assistant_context_pack",
    "_latest_result_from_storage",
    "_cloud_snapshot_from_storage",
    "_read_jsonl",
    "_candidate_brief",
    "_backtest_brief",
    "_backtest_record_brief",
    "_cloud_alpha_brief",
    "_expression_from_row",
    "_cloud_pass_fail",
    "_join_candidate_briefs",
    "_join_field_combinations",
    "_join_failures",
    "_join_stat_bucket",
    "_join_guidance_outcomes",
    "_join_duplicate_expressions",
    "_join_text_items",
    "_unique_text_items",
    "_guidance_outcomes",
    "_strong_guidance_outcome",
    "_weak_guidance_outcome",
    "_int_value",
    "_float_value",
    "_first_dict",
    "_first_list",
    "_dataclass_dict",
]
