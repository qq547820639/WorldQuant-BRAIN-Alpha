"""Shared AF-006 local-only/non-submit verification summaries."""

from __future__ import annotations

from typing import Any


AF006_NON_SUBMIT_SUBMATRIX_SCHEMA_VERSION = "af006_non_submit_verification_submatrix.v1"
AF006_SUBMIT_READY_SOURCE = "scripts/check_live_submit_readiness.py --config config/run_config.json --json"
EXPECTED_AF_COMPLETION_IDS = tuple(f"AF-{index:03d}" for index in range(6, 26))

AF006_NON_SUBMIT_VERIFICATION_AXES: tuple[dict[str, Any], ...] = (
    {
        "id": "ci",
        "label": "CI and release gate coverage",
        "required_steps": (
            "config",
            "dependency_policy",
            "redline_verification",
            "brain_contract_validation",
            "diagnosis_gap_coverage",
            "official_context_validation",
            "module_size_audit",
            "static_defect_analysis_report",
            "v5_defect_tracking",
            "prod_defect_tracking",
        ),
        "optional_steps": (
            "canonical_compliance",
            "parameter_traceability",
            "live_submit_readiness",
            "final_release_gate",
            "pytest",
        ),
        "source_files": (
            "scripts/quality_gate.py",
            "scripts/final_release_gate.py",
            "tests/test_quality_gate.py",
        ),
    },
    {
        "id": "e2e",
        "label": "Local non-submit E2E and browser smoke coverage",
        "required_steps": (
            "frontend_inline_sync",
            "frontend_syntax",
            "web_console_contract",
            "frontend_surface_parity",
            "react_build_env",
        ),
        "optional_steps": ("react_preview_smoke", "pytest"),
        "source_files": (
            "scripts/browser_react_artifact_smoke.mjs",
            "tests/test_react_api_contract_static.py",
            "tests/test_web_frontend_modules.py",
        ),
    },
    {
        "id": "mobile",
        "label": "Mobile/static responsive contract coverage",
        "required_steps": ("frontend_surface_parity", "react_build_env"),
        "optional_steps": ("react_preview_smoke", "pytest"),
        "source_files": (
            "brain_alpha_ops/web/react_app/src/components/MobileTabBar.tsx",
            "tests/test_react_api_contract_static.py",
            "tests/test_web_frontend_modules.py",
        ),
    },
    {
        "id": "security",
        "label": "Secret, payload, and exception-boundary coverage",
        "required_steps": (
            "dependency_policy",
            "frontend_innerhtml_guard",
            "frontend_silent_catch_guard",
            "python_silent_broad_exception_guard",
            "tracked_data_inventory",
            "candidate_scientific_audit",
            "secret_scan",
        ),
        "optional_steps": ("dependency_audit", "pytest"),
        "source_files": (
            "scripts/scan_sensitive_artifacts.py",
            "scripts/check_frontend_silent_catches.py",
            "tests/test_react_api_contract_static.py",
            "tests/test_web_frontend_modules.py",
        ),
    },
)


def build_quality_gate_af006_submatrix(steps: list[dict[str, Any]]) -> dict[str, Any]:
    step_by_name = {str(step.get("name") or ""): step for step in steps}
    axes: list[dict[str, Any]] = []
    for axis in AF006_NON_SUBMIT_VERIFICATION_AXES:
        required_steps = list(axis["required_steps"])
        optional_steps = list(axis["optional_steps"])
        missing_required_steps = [name for name in required_steps if name not in step_by_name]
        failing_required_steps = [
            name
            for name in required_steps
            if name in step_by_name and step_by_name[name].get("ok") is not True
        ]
        axes.append({
            "id": axis["id"],
            "label": axis["label"],
            "mode": "local-only/non-submit",
            "source_files": list(axis["source_files"]),
            "required_steps": required_steps,
            "optional_steps": optional_steps,
            "present_required_steps": [name for name in required_steps if name in step_by_name],
            "present_optional_steps": [name for name in optional_steps if name in step_by_name],
            "missing_required_steps": missing_required_steps,
            "failing_required_steps": failing_required_steps,
            "ok": not missing_required_steps and not failing_required_steps,
        })
    return {
        "schema_version": AF006_NON_SUBMIT_SUBMATRIX_SCHEMA_VERSION,
        "task_id": "AF006-CI-E2E-SUBMATRIX-V2",
        "mode": "local-only/non-submit",
        "submit_ready_source": AF006_SUBMIT_READY_SOURCE,
        "submit_ready_claim_allowed": False,
        "real_brain_submit_executed": False,
        "axes": axes,
        "ok": all(axis["ok"] for axis in axes),
    }


def build_final_release_af006_submatrix(af006_status: str | None) -> dict[str, Any]:
    return {
        "schema_version": AF006_NON_SUBMIT_SUBMATRIX_SCHEMA_VERSION,
        "task_id": "AF006-CI-E2E-SUBMATRIX-V2",
        "af_id": "AF-006",
        "tracker_status": af006_status or "missing",
        "mode": "local-only/non-submit",
        "submit_ready_source": AF006_SUBMIT_READY_SOURCE,
        "submit_ready_claim_allowed": False,
        "real_brain_submit_executed": False,
        "axes": [
            {
                "id": axis["id"],
                "label": axis["label"],
                "mode": "local-only/non-submit",
                "quality_gate_signals": [*axis["required_steps"], *axis["optional_steps"]],
                "release_gate_signals": list(axis["optional_steps"]),
                "source_files": list(axis["source_files"]),
            }
            for axis in AF006_NON_SUBMIT_VERIFICATION_AXES
        ],
    }


def tracker_non_done_statuses(expected_ids: list[str], status_by_id: dict[str, str]) -> dict[str, str]:
    return {
        af_id: status_by_id[af_id]
        for af_id in expected_ids
        if af_id in status_by_id and status_by_id[af_id] != "done"
    }


def tracker_readiness_summary(expected_ids: list[str], status_by_id: dict[str, str]) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    non_done_ids: list[str] = []
    blocked_ids: list[str] = []
    next_actionable_ids: list[str] = []
    for af_id in expected_ids:
        status = status_by_id.get(af_id, "missing")
        status_counts[status] = status_counts.get(status, 0) + 1
        if status == "done":
            continue
        non_done_ids.append(af_id)
        if status == "blocked":
            blocked_ids.append(af_id)
        else:
            next_actionable_ids.append(af_id)
    total_expected = len(expected_ids)
    done_count = status_counts.get("done", 0)
    return {
        "done_count": done_count,
        "remaining_count": total_expected - done_count,
        "total_expected": total_expected,
        "completion_ratio": f"{done_count}/{total_expected}",
        "status_counts": dict(sorted(status_counts.items())),
        "non_done_ids": non_done_ids,
        "blocked_ids": blocked_ids,
        "next_actionable_ids": next_actionable_ids,
        "completion_claimable": done_count == total_expected,
    }
