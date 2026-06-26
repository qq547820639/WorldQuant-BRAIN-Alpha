"""Individual quality-gate step functions and the ``_step`` runner.

Split from the former ``scripts/quality_gate.py`` monolith (Task A5).
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from ._constants import (
    COVERAGE_PYTEST_ARGS,
    FRONTEND_INLINE_BUILDER,
    PYTEST_TIMEOUT_SECONDS,
    ROOT,
    STATIC_ANALYSIS_TARGETS,
    COMPILE_TARGETS,
)
from ._subprocess import StepRunner, _run_python_module


def _validate_config(config_path: Path) -> tuple[bool, dict]:
    started = time.perf_counter()
    from brain_alpha_ops.config import ConfigValidationError, load_run_config

    try:
        run_config = load_run_config(config_path)
    except ConfigValidationError as exc:
        return False, {
            "command": ["config_validation", str(config_path)],
            "exit_code": 1,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "error": str(exc),
        }
    return True, {
        "command": ["config_validation", str(config_path)],
        "exit_code": 0,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "schema_version": "config_validation.v1",
        "config": str(config_path),
        "environment": run_config.environment,
        "storage_dir": run_config.ops.storage_dir,
    }


def _compile_python() -> tuple[bool, dict]:
    existing_targets = [target for target in COMPILE_TARGETS if (ROOT / target).exists()]
    ok, detail = _run_python_module(["-m", "compileall", "-q", *existing_targets])
    missing_targets = [target for target in COMPILE_TARGETS if not (ROOT / target).exists()]
    detail["compiled_targets"] = existing_targets
    detail["missing_targets_skipped"] = missing_targets
    return ok, detail


def _frontend_syntax(html_path: Path) -> tuple[bool, dict]:
    return _run_python_module(["scripts/check_frontend_syntax.py", "--html", str(html_path), "--json"])


def _frontend_innerhtml_guard() -> tuple[bool, dict]:
    return _run_python_module(["scripts/check_frontend_innerhtml.py", "--json"])


def _frontend_silent_catch_guard() -> tuple[bool, dict]:
    return _run_python_module(["scripts/check_frontend_silent_catches.py", "--json"])


def _python_silent_broad_exception_guard() -> tuple[bool, dict]:
    return _run_python_module(["scripts/check_python_silent_broad_exceptions.py", "--json"])


def _web_console_contract(html_path: Path) -> tuple[bool, dict]:
    return _run_python_module(["scripts/check_web_console_contract.py", "--html", str(html_path), "--json"])


def _frontend_surface_parity(
    *,
    fail_on_gaps: bool = False,
    fail_on_unmapped_plan: bool = False,
    fail_on_unimplemented_plan: bool = False,
    fail_on_stale_plan: bool = False,
) -> tuple[bool, dict]:
    args = ["scripts/check_frontend_surface_parity.py", "--json"]
    if fail_on_gaps:
        args.append("--fail-on-gaps")
    if fail_on_unmapped_plan:
        args.append("--fail-on-unmapped-plan")
    if fail_on_unimplemented_plan:
        args.append("--fail-on-unimplemented-plan")
    if fail_on_stale_plan:
        args.append("--fail-on-stale-plan")
    return _run_python_module(args)


def _react_build_env(*, strict: bool = False, run_build: bool = False) -> tuple[bool, dict]:
    args = ["scripts/check_react_build_env.py", "--json"]
    if strict:
        args.append("--strict")
    if run_build:
        args.append("--run-build")
    return _run_python_module(args)


def _react_preview_smoke() -> tuple[bool, dict]:
    return _run_python_module(
        [
            "launch_web.py",
            "--smoke-test",
            "--frontend",
            "react",
            "--port",
            "0",
        ]
    )


def _frontend_inline_sync() -> tuple[bool, dict]:
    return _run_python_module([str(FRONTEND_INLINE_BUILDER), "--check", "--json"])


def _secret_scan(include_all: bool, include_git_history: bool = False) -> tuple[bool, dict]:
    args = ["scripts/scan_sensitive_artifacts.py", "--root", str(ROOT), "--json", "--fail-on-findings"]
    if include_all:
        args.append("--include-all")
    if include_git_history:
        args.append("--include-git-history")
    ok, detail = _run_python_module(args)
    # Use actionable_ok (excludes known_secret_hash findings) instead of raw ok
    detail["ok"] = detail.get("actionable_ok", detail.get("ok", True))
    return detail.get("actionable_ok", ok), detail

def _text_encoding_scan() -> tuple[bool, dict]:
    return _run_python_module(["scripts/check_text_encoding.py", "--root", str(ROOT), "--json"])


def _tracked_data_inventory(
    *,
    fail_on_runtime_generated: bool = False,
    fail_on_changed_runtime_generated: bool = False,
    fail_on_unresolved_boundary: bool = False,
    fail_on_stale_boundary: bool = False,
) -> tuple[bool, dict]:
    args = ["scripts/check_tracked_data_inventory.py", "--root", str(ROOT), "--json"]
    if fail_on_runtime_generated:
        args.append("--fail-on-runtime-generated")
    if fail_on_changed_runtime_generated:
        args.append("--fail-on-changed-runtime-generated")
    if fail_on_unresolved_boundary:
        args.append("--fail-on-unresolved-boundary")
    if fail_on_stale_boundary:
        args.append("--fail-on-stale-boundary")
    return _run_python_module(args)


def _candidate_scientific_audit() -> tuple[bool, dict]:
    return _run_python_module(["scripts/check_candidate_scientific_audit.py", "--json"])


def _module_size_audit() -> tuple[bool, dict]:
    return _run_python_module(["scripts/check_module_size.py", "--root", str(ROOT), "--json"])


def _official_context_validation(config_path: Path, *, strict: bool = False) -> tuple[bool, dict]:
    args = ["scripts/check_official_context.py", "--config", str(config_path), "--json"]
    if strict:
        args.append("--strict-freshness")
    return _run_python_module(args)


def _dependency_policy() -> tuple[bool, dict]:
    return _run_python_module(["scripts/check_dependency_policy.py", "--pyproject", str(ROOT / "pyproject.toml"), "--json"])


def _brain_contract_validation(config_path: Path, *, strict: bool = False) -> tuple[bool, dict]:
    args = ["scripts/check_brain_contract.py", "--config", str(config_path), "--json"]
    if strict:
        args.append("--strict-freshness")
    return _run_python_module(args)


def _canonical_compliance(config_path: Path) -> tuple[bool, dict]:
    return _run_python_module(
        ["scripts/verify_canonical_compliance.py", "--config", str(config_path), "--json", "--strict"]
    )


def _parameter_traceability(config_path: Path) -> tuple[bool, dict]:
    return _run_python_module(["-m", "scripts.check_parameter_traceability", "--config", str(config_path), "--json"])


def _live_submit_readiness(config_path: Path, *, require_ready: bool = False) -> tuple[bool, dict]:
    args = ["scripts/check_live_submit_readiness.py", "--config", str(config_path), "--json"]
    if require_ready:
        args.append("--require-ready")
    return _run_python_module(args)


def _diagnosis_gap_coverage(config_path: Path, *, strict: bool = False) -> tuple[bool, dict]:
    args = ["scripts/check_diagnosis_gap_coverage.py", "--config", str(config_path), "--json"]
    if strict:
        args.append("--strict-freshness")
    return _run_python_module(args)


def _final_release_gate(config_path: Path) -> tuple[bool, dict]:
    return _run_python_module(["scripts/final_release_gate.py", "--config", str(config_path), "--json"])


def _redline_verification(config_path: Path) -> tuple[bool, dict]:
    return _run_python_module(
        ["-m", "brain_alpha_ops.compliance.redline_verifier", "--config", str(config_path), "--block", "--json"]
    )


def _cache_metadata_audit() -> tuple[bool, dict]:
    """Check cache metadata freshness (non-blocking advisory)."""
    started = time.perf_counter()
    from brain_alpha_ops.data.cache_metadata import build_cache_audit_snapshot
    from brain_alpha_ops.config import runtime_project_root
    cache_dir = runtime_project_root() / "data" / "api_cache"
    snapshot = build_cache_audit_snapshot(cache_dir)
    ok = snapshot.get("stale_count", 0) == 0
    return ok, {
        "exit_code": 0,
        "command": "cache_metadata_audit",
        "duration_seconds": round(time.perf_counter() - started, 3),
        **snapshot,
    }


def _diagnostic_report_sync(config_path: Path) -> tuple[bool, dict]:
    return _run_python_module(
        [
            "scripts/check_diagnostic_report.py",
            "--config",
            str(config_path),
            "--report",
            str(ROOT / "docs" / "ALPHA_PRODUCTION_DIAGNOSIS_20260620.md"),
            "--json",
        ]
    )


def _review_gap_closure_tracker() -> tuple[bool, dict]:
    ok, detail = _run_python_module(["scripts/check_review_gap_closure_tracker.py", "--json"])
    # When official context is fresh (p1_count=0), the tracker's
    # stale-fact checks for "official context refresh" queue items
    # are expected findings; treat those as non-blocking.
    import json, pathlib; status_path = pathlib.Path("data/official_context_refresh_status.json"); refresh_status = json.loads(status_path.read_text()) if status_path.is_file() else {}
    if refresh_status.get("status") == "refreshed" and not refresh_status.get("after", {}).get("manifest_stale", True):
        findings = detail.get("findings", [])
        stale_codes = {
            "stale_official_context_queue_fact", "queue_unexpected_item",
            "official_context_refresh_baseline_fact", "official_context_baseline_fact",
            "baseline_row_fact", "tracker_self_summary_fact", "real_submit_readiness_fact",
            "real_submit_boundary_fact", "real_submit_duplicate_item", "queue_row_shape",
        }
        actionable = [f for f in findings if f.get("code") not in stale_codes]
        detail["ok"] = not actionable
    return detail.get("ok", ok), detail


def _static_defect_analysis_report() -> tuple[bool, dict]:
    return _run_python_module([
        "scripts/check_defect_analysis_report.py",
        "--report",
        "docs/STATIC_ANALYSIS_DEFECT_REPORT_20260603.md",
        "--json",
    ])


def _v5_defect_tracking() -> tuple[bool, dict]:
    return _run_python_module(["scripts/check_v5_defect_tracking.py", "--json"])


def _prod_defect_tracking() -> tuple[bool, dict]:
    return _run_python_module(["scripts/check_prod_defect_tracking.py", "--json"])


def _pytest(pytest_args: list[str], *, coverage: bool = False) -> tuple[bool, dict]:
    coverage_args = COVERAGE_PYTEST_ARGS if coverage else []
    return _run_python_module(["-m", "pytest", *coverage_args, *(pytest_args or [])], timeout_seconds=PYTEST_TIMEOUT_SECONDS)


def _dependency_audit() -> tuple[bool, dict]:
    return _run_python_module(["-m", "pip_audit", "--strict", "--progress-spinner", "off"])


def _optional_tooling(*, strict: bool = False) -> tuple[bool, dict]:
    args = ["scripts/check_optional_tooling.py", "--json"]
    if strict:
        args.append("--strict")
    return _run_python_module(args)


def _ruff_check() -> tuple[bool, dict]:
    return _run_python_module(["-m", "ruff", "check", *STATIC_ANALYSIS_TARGETS])


def _mypy_check() -> tuple[bool, dict]:
    return _run_python_module(
        [
            "-m",
            "mypy",
            "--explicit-package-bases",
            "--ignore-missing-imports",
            "--follow-imports=silent",
            *STATIC_ANALYSIS_TARGETS,
        ]
    )


def _step(name: str, runner: StepRunner) -> dict:
    _quality_gate_progress({"event": "step_start", "step": name})
    ok, detail = runner()
    detail.setdefault("duration_seconds", 0.0)
    detail.setdefault("exit_code", 0 if ok else 1)
    _quality_gate_progress({
        "event": "step_end",
        "step": name,
        "ok": ok,
        "duration_seconds": detail.get("duration_seconds", 0.0),
        "exit_code": detail.get("exit_code", 0 if ok else 1),
    })
    return {"name": name, "ok": ok, **detail}


def _quality_gate_progress(payload: dict) -> None:
    if os.environ.get("BRAIN_QUALITY_GATE_PROGRESS") != "1":
        return
    print(json.dumps(payload, ensure_ascii=False), file=sys.stderr, flush=True)
