"""Internal helpers and constants for the official_simulation subpackage."""

from __future__ import annotations

from typing import Any

from ..base import BrainAPIError
from ..official_helpers import _first_value
from ..official_helpers import items as _items
from ..official_helpers import scrub as _scrub
from ..rate_limit_policy import OFFICIAL_RATE_LIMITS

_CHECK_PASS_STATES = frozenset({"PASS", "PASSED", "SUCCESS", "SUCCEEDED", "OK"})
_CHECK_FAIL_STATES = frozenset({"FAIL", "FAILED", "ERROR", "REJECTED"})
_CHECK_PENDING_STATES = frozenset({"PENDING", "RUNNING", "IN_PROGRESS", "WAITING", "QUEUED"})
_MAX_DEFAULT_CONCURRENT_OFFICIAL_JOBS = int(OFFICIAL_RATE_LIMITS["max_concurrent_simulations_regular"]["max"])


def _verify_submit_guard(_submit_log) -> None:
    """Verify runtime_constants integrity before submit_alpha proceeds.

    Fail-closed: if we can't verify, block the submission. Uses hash-based
    verification so monkeypatching the sentinel string alone is insufficient —
    the attacker must also override the hash comparison function.
    """
    import hashlib as _hashlib
    try:
        from ... import runtime_constants as _rc
        if not hasattr(_rc, "REAL_SUBMIT_DISABLED_WEB_FLOW"):
            _submit_log.critical(
                "SUBMIT BLOCKED: runtime_constants.REAL_SUBMIT_DISABLED_WEB_FLOW missing — "
                "module may have been tampered with."
            )
            raise BrainAPIError(
                "SUBMIT INTEGRITY FAILURE: REAL_SUBMIT_DISABLED_WEB_FLOW attribute missing from "
                "runtime_constants. Submission blocked as a safety precaution."
            )
        if _rc.REAL_SUBMIT_DISABLED_WEB_FLOW is not True:
            _submit_log.critical(
                "SUBMIT BLOCKED: REAL_SUBMIT_DISABLED_WEB_FLOW was modified to %r — "
                "expected True. Submission refused.",
                _rc.REAL_SUBMIT_DISABLED_WEB_FLOW,
            )
            raise BrainAPIError(
                "SUBMIT INTEGRITY FAILURE: REAL_SUBMIT_DISABLED_WEB_FLOW was modified from its "
                "hardcoded True value. Submission refused."
            )
        from ...runtime_constants import _SUBMIT_GUARD_SENTINEL
        _expected_sentinel_hash = _hashlib.sha256(b"BRAIN_ALPHA_SUBMIT_GUARD_v1").hexdigest()
        _actual_sentinel_hash = _hashlib.sha256(str(_SUBMIT_GUARD_SENTINEL).encode()).hexdigest()
        if _actual_sentinel_hash != _expected_sentinel_hash:
            _submit_log.critical(
                "SUBMIT BLOCKED: _SUBMIT_GUARD_SENTINEL hash mismatch — expected "
                "BRAIN_ALPHA_SUBMIT_GUARD_v1, got %r.",
                _SUBMIT_GUARD_SENTINEL,
            )
            raise BrainAPIError(
                "SUBMIT INTEGRITY FAILURE: guard sentinel mismatch. Submission refused."
            )
        if not hasattr(_rc, "_SUBMIT_GUARD_SENTINEL") or not hasattr(_rc, "real_submit_test_override_enabled"):
            _submit_log.critical(
                "SUBMIT BLOCKED: runtime_constants missing required guard functions — "
                "module may have been tampered with."
            )
            raise BrainAPIError(
                "SUBMIT INTEGRITY FAILURE: guard function missing. Submission blocked."
            )
    except ImportError:
        _submit_log.critical("SUBMIT BLOCKED: failed to import runtime_constants — module integrity unknown.")
        raise BrainAPIError(
            "SUBMIT INTEGRITY FAILURE: cannot import runtime_constants. Submission blocked."
        )


def _normalized_check(item: Any, index: int) -> dict[str, Any]:
    if isinstance(item, dict):
        row = dict(_scrub(item))
    else:
        row = {"value": _scrub(item)}
    name = str(_first_value(row, ["name", "check", "title"], "") or f"check_{index + 1}")
    state = str(_first_value(row, ["result", "status"], "") or "").upper()
    if state in _CHECK_PASS_STATES:
        classification = "passed"
    elif state in _CHECK_FAIL_STATES:
        classification = "failed"
    elif state in _CHECK_PENDING_STATES:
        classification = "pending"
    else:
        classification = "unknown"
    row["name"] = name
    if state:
        row["result"] = state
    row["_classification"] = classification
    return row


def _check_result_from_response(data: Any) -> dict[str, Any]:
    checks = [_normalized_check(item, index) for index, item in enumerate(_check_items(data))]
    passed = [item for item in checks if item.get("_classification") == "passed"]
    failed = [item for item in checks if item.get("_classification") == "failed"]
    pending = [item for item in checks if item.get("_classification") == "pending"]
    unknown = [item for item in checks if item.get("_classification") == "unknown"]
    status = "UNKNOWN"
    if failed:
        status = "FAILED"
    elif pending:
        status = "PENDING"
    elif unknown or not checks:
        status = "UNKNOWN"
    elif passed and len(passed) == len(checks):
        status = "PASSED"
    complete = bool(checks) and not pending and not unknown
    clean_checks = [_without_internal_keys(item) for item in checks]
    return {
        "status": status,
        "complete": complete,
        "checks": clean_checks,
        "failed_checks": [_without_internal_keys(item) for item in failed],
        "pending_checks": [_without_internal_keys(item) for item in pending],
        "passed_checks": [_without_internal_keys(item) for item in passed],
        "unknown_checks": [_without_internal_keys(item) for item in unknown],
        "raw": _scrub(data),
    }


def _check_items(data: Any) -> list:
    rows = list(_items(data) or [])
    if not isinstance(data, dict):
        return rows
    for container_key in ("is", "inSample", "in_sample", "os", "outSample", "out_sample"):
        container = data.get(container_key)
        if isinstance(container, dict):
            checks = container.get("checks")
            if isinstance(checks, list):
                rows.extend(checks)
    return rows


def _without_internal_keys(item: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in item.items() if not str(key).startswith("_")}


def _bounded_concurrency(concurrency: int) -> int:
    try:
        value = int(concurrency)
    except (TypeError, ValueError):
        value = 1
    return max(1, min(_MAX_DEFAULT_CONCURRENT_OFFICIAL_JOBS, value))


def _simulation_input(row: dict[str, Any] | tuple[str, dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    if isinstance(row, tuple) and len(row) == 2:
        expression, settings = row
        return str(expression or "").strip(), dict(settings or {})
    if not isinstance(row, dict):
        raise BrainAPIError("concurrent_simulate items must be dicts or (expression, settings) tuples")
    expression = str(
        _first_value(row, ["expression", "regular", "code"], "")
        or _first_value(row.get("alpha") if isinstance(row.get("alpha"), dict) else {}, ["expression", "regular"], "")
    ).strip()
    settings = row.get("settings")
    if not isinstance(settings, dict):
        settings = row.get("simulation_settings") if isinstance(row.get("simulation_settings"), dict) else {}
    if not expression:
        raise BrainAPIError("concurrent_simulate item missing expression/regular")
    return expression, dict(settings)
