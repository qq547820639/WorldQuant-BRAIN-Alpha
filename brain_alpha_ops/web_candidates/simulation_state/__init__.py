"""State helpers for Web candidate official simulation jobs.

Re-export package: the original monolithic ``simulation_state.py`` module has
been split into responsibility-based submodules (``_cooldown``, ``_candidates``,
``_scoring``, ``_eligibility``). All public symbols (and the private helpers
that other modules relied on) remain importable from this exact path:
``brain_alpha_ops.web_candidates.simulation_state``.
"""

from __future__ import annotations

from brain_alpha_ops.web_candidates.simulation_state._candidates import (
    _CANDIDATES_FILE_LOCK,
    _candidate_merge_key,
    _merge_candidate_rows,
    _read_candidates_unlocked,
    append_backtest_record,
    candidate_update_row,
    load_candidates,
    save_candidate_update,
    save_candidates,
)
from brain_alpha_ops.web_candidates.simulation_state._cooldown import (
    COOLDOWN_UPDATE_FIELDS,
    DEFERRED_SIMULATION_STATUSES,
    SIMULATION_COOLDOWN_FILENAME,
    SIMULATION_COOLDOWN_SCOPE,
    _SIMULATION_COOLDOWN_FILE_LOCK,
    _read_simulation_cooldowns_unlocked,
    _safe_storage_file,
    _simulation_deferred_until,
    _write_simulation_cooldowns_unlocked,
    active_account_simulation_cooldown,
    clear_account_simulation_cooldown,
    clear_candidate_simulation_cooldown,
    defer_candidate,
    is_simulation_cooling_down,
    record_account_simulation_cooldown,
)
from brain_alpha_ops.web_candidates.simulation_state._eligibility import (
    GROUP_KEY_FIELDS,
    _candidate_dataset_key,
    _has_complete_official_simulation_result,
    _has_explicit_unsupported_local_backtest,
    _has_non_signal_candidate_fields,
    dedupe_simulation_targets,
    eligible_for_simulation,
    simulation_target_key,
)
from brain_alpha_ops.web_candidates.simulation_state._scoring import (
    _candidate_settings,
    _official_simulation_gate,
    candidate_score,
    default_simulation_dataset,
    score_simulated_candidate,
)

__all__ = [
    "COOLDOWN_UPDATE_FIELDS",
    "DEFERRED_SIMULATION_STATUSES",
    "GROUP_KEY_FIELDS",
    "SIMULATION_COOLDOWN_FILENAME",
    "SIMULATION_COOLDOWN_SCOPE",
    "active_account_simulation_cooldown",
    "append_backtest_record",
    "candidate_score",
    "candidate_update_row",
    "clear_account_simulation_cooldown",
    "clear_candidate_simulation_cooldown",
    "dedupe_simulation_targets",
    "default_simulation_dataset",
    "defer_candidate",
    "eligible_for_simulation",
    "is_simulation_cooling_down",
    "load_candidates",
    "record_account_simulation_cooldown",
    "save_candidate_update",
    "save_candidates",
    "score_simulated_candidate",
    "simulation_target_key",
]
