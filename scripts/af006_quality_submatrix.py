"""Shared AF-006 CI/E2E/Mobile/Security verification submatrix helpers.

Used by both ``quality_gate`` (``build_quality_gate_af006_submatrix``) and
``final_release_gate`` (``build_final_release_af006_submatrix``) to report the
AF-006 non-submit verification submatrix without ever claiming a real brain
submit was executed.
"""

AF006_AXIS_DEFINITIONS = [
    {
        "id": "ci",
        "name": "Continuous Integration",
        "release_gate_signals": [
            "live_submit_readiness",
            "brain_contract_validation",
            "official_context_validation",
            "secret_scan",
        ],
        "quality_gate_signals": [
            "live_submit_readiness",
            "brain_contract_validation",
            "official_context_validation",
        ],
        "source_files": [],
    },
    {
        "id": "e2e",
        "name": "End-to-end",
        "release_gate_signals": [
            "react_preview_smoke",
            "frontend_surface_parity",
        ],
        "quality_gate_signals": [
            "react_preview_smoke",
            "frontend_syntax",
            "web_console_contract",
        ],
        "source_files": [],
    },
    {
        "id": "mobile",
        "name": "Mobile",
        "release_gate_signals": [
            "frontend_surface_parity",
            "react_preview_smoke",
        ],
        "quality_gate_signals": [
            "frontend_surface_parity",
        ],
        "source_files": [
            "brain_alpha_ops/web/react_app/src/components/MobileTabBar.tsx",
        ],
    },
    {
        "id": "security",
        "name": "Security",
        "release_gate_signals": [
            "secret_scan",
            "dependency_policy",
        ],
        "quality_gate_signals": [
            "secret_scan",
        ],
        "source_files": [],
    },
]

# Quality-gate step names bucketed per axis as required (must be present) or
# optional (nice to have). Used to derive the submatrix from the step list.
_AXIS_STEP_MAP = {
    "ci": {
        "required": {
            "config",
            "python_compile",
            "dependency_policy",
            "redline_verification",
            "brain_contract_validation",
            "official_context_validation",
            "candidate_scientific_audit",
        },
        "optional": {
            "live_submit_readiness",
            "dependency_audit",
            "optional_tooling",
            "ruff",
            "mypy",
        },
    },
    "e2e": {
        "required": {
            "frontend_inline_sync",
            "frontend_syntax",
            "frontend_innerhtml_guard",
            "frontend_silent_catch_guard",
            "web_console_contract",
            "frontend_surface_parity",
            "react_build_env",
            "text_encoding_scan",
        },
        "optional": {
            "react_preview_smoke",
        },
    },
    "mobile": {
        "required": {
            "frontend_surface_parity",
            "web_console_contract",
            "react_build_env",
        },
        "optional": {
            "react_preview_smoke",
        },
    },
    "security": {
        "required": {
            "secret_scan",
            "dependency_policy",
            "candidate_scientific_audit",
        },
        "optional": {
            "dependency_audit",
        },
    },
}

_SUBMIT_READY_SOURCE = (
    "scripts/check_live_submit_readiness.py --config config/run_config.json --json"
)

# AF-006 through AF-025 are the modules the final release must track.
EXPECTED_AF_COMPLETION_IDS = tuple(f"AF-{index:03d}" for index in range(6, 26))


def tracker_non_done_statuses(expected_ids, status_by_id) -> dict[str, str]:
    """Return {af_id: status} for every expected id that is present and not done."""
    return {
        af_id: status
        for af_id in expected_ids
        if (status := status_by_id.get(af_id)) is not None and status != "done"
    }


def tracker_readiness_summary(expected_ids, status_by_id) -> dict[str, object]:
    """Compute completion ratio, status counts, blocked and next-actionable ids."""
    present = {af_id: status_by_id[af_id] for af_id in expected_ids if af_id in status_by_id}
    done_count = sum(1 for status in present.values() if status == "done")
    total = len(expected_ids)
    status_counts: dict[str, int] = {}
    for status in present.values():
        status_counts[status] = status_counts.get(status, 0) + 1
    blocked_ids = sorted(af_id for af_id, status in present.items() if status == "blocked")
    next_actionable_ids = [
        af_id for af_id, status in present.items() if status not in ("done", "blocked")
    ]
    return {
        "completion_ratio": f"{done_count}/{total}",
        "done_count": done_count,
        "remaining_count": total - done_count,
        "status_counts": status_counts,
        "blocked_ids": blocked_ids,
        "next_actionable_ids": next_actionable_ids,
        "completion_claimable": done_count == total and len(present) == total,
    }


def build_final_release_af006_submatrix(af006_status=None) -> dict[str, object]:
    """Build the AF-006 non-submit verification submatrix for the final release gate."""
    return {
        "schema_version": "af006_non_submit_verification_submatrix.v1",
        "task_id": "AF006-CI-E2E-SUBMATRIX-V2",
        "tracker_status": af006_status or "unknown",
        "mode": "local-only/non-submit",
        "submit_ready_source": _SUBMIT_READY_SOURCE,
        "submit_ready_claim_allowed": False,
        "real_brain_submit_executed": False,
        "axes": list(AF006_AXIS_DEFINITIONS),
    }


def build_quality_gate_af006_submatrix(steps) -> dict[str, object]:
    """Build the AF-006 non-submit verification submatrix from the step list."""
    present = {step["name"] for step in steps}
    axes = []
    for axis_id, mapping in _AXIS_STEP_MAP.items():
        required = mapping["required"]
        optional = mapping["optional"]
        axes.append(
            {
                "id": axis_id,
                "required_total": len(required),
                "optional_total": len(optional),
                "present_required_steps": sorted(required & present),
                "present_optional_steps": sorted(optional & present),
                "missing_required_steps": sorted(required - present),
            }
        )
    ok = all(not axis["missing_required_steps"] for axis in axes)
    return {
        "schema_version": "af006_non_submit_verification_submatrix.v1",
        "task_id": "AF006-CI-E2E-SUBMATRIX-V2",
        "mode": "local-only/non-submit",
        "submit_ready_source": _SUBMIT_READY_SOURCE,
        "submit_ready_claim_allowed": False,
        "real_brain_submit_executed": False,
        "ok": ok,
        "axes": axes,
    }