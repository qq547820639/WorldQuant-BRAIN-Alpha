"""Run local quality gates before handoff or packaging."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.af006_quality_submatrix import build_quality_gate_af006_submatrix

DEFAULT_CONFIG = ROOT / "config" / "run_config.json"
DEFAULT_HTML = ROOT / "brain_alpha_ops" / "web" / "react_app" / "dist" / "index.html"
DEFAULT_SUBPROCESS_TIMEOUT_SECONDS = 300
PYTEST_TIMEOUT_SECONDS = 900
COVERAGE_PYTEST_ARGS = ["--cov=brain_alpha_ops", "--cov-report=term", "--cov-fail-under=80"]
SUBPROCESS_ENV_ALLOWLIST = {
    "CI",
    "COMSPEC",
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LOGNAME",
    "PATH",
    "PATHEXT",
    "PYTHONHOME",
    "PYTHONIOENCODING",
    "PYTHONNOUSERSITE",
    "PYTHONPATH",
    "PYTHONUTF8",
    "RUNNER_OS",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "TMPDIR",
    "USER",
    "VIRTUAL_ENV",
}
COMPILE_TARGETS = [
    "brain_alpha_ops",
    "scripts",
    "tests",
    "build_prod.py",
    "calibrate_weights.py",
    "fetch_official_context.py",
    "launch_web.py",
    "test_api_format.py",
    "test_api_root.py",
    "test_auth.py",
    "test_datasets_api.py",
    "validate_data.py",
    "_launch_monitor.py",
    "_status.py",
]
FRONTEND_INLINE_BUILDER = ROOT / "brain_alpha_ops" / "build_inline.py"
STATIC_ANALYSIS_TARGETS = [
    "brain_alpha_ops/build_inline.py",
    "brain_alpha_ops/web_config.py",
    "brain_alpha_ops/web_assistant_snapshots.py",
    "brain_alpha_ops/web_check_batch_job.py",
    "brain_alpha_ops/web_check_availability.py",
    "brain_alpha_ops/web_candidate_audit.py",
    "brain_alpha_ops/web_candidate_check.py",
    "brain_alpha_ops/web_candidate_decisions.py",
    "brain_alpha_ops/web_candidate_generation.py",
    "brain_alpha_ops/web_candidate_optimization.py",
    "brain_alpha_ops/web_candidate_payloads.py",
    "brain_alpha_ops/web_candidate_selection.py",
    "brain_alpha_ops/web_cloud_snapshot.py",
    "brain_alpha_ops/web_cloud_context_refresh.py",
    "brain_alpha_ops/web_get_handlers.py",
    "brain_alpha_ops/web_handler_dispatch.py",
    "brain_alpha_ops/web_post_handlers.py",
    "brain_alpha_ops/web_run_job.py",
    "brain_alpha_ops/web_runtime_state.py",
    "brain_alpha_ops/web_security.py",
    "brain_alpha_ops/web_server_lifecycle.py",
    "brain_alpha_ops/web_review_api.py",
    "brain_alpha_ops/web_sqlite_indexes.py",
    "brain_alpha_ops/web_submission_batch.py",
    "brain_alpha_ops/web_submission_single.py",
    "brain_alpha_ops/web_sync_job.py",
    "brain_alpha_ops/web_sync_payload.py",
    "brain_alpha_ops/task_executor.py",
    "brain_alpha_ops/research/anti_overfit.py",
    "brain_alpha_ops/research/batch_backtest_coordinator.py",
    "brain_alpha_ops/research/dataset_selection.py",
    "brain_alpha_ops/research/expression_engine.py",
    "brain_alpha_ops/research/experience_feedback.py",
    "brain_alpha_ops/research/generation_phase.py",
    "brain_alpha_ops/research/knowledge_base.py",
    "brain_alpha_ops/research/llm_review.py",
    "brain_alpha_ops/research/official_workflow.py",
    "brain_alpha_ops/research/research_cycle_orchestrator.py",
    "brain_alpha_ops/research/record_sqlite_index.py",
    "brain_alpha_ops/research/rolling_validation.py",
    "brain_alpha_ops/research/robustness_policy.py",
    "brain_alpha_ops/research/sqlite_index_manifest.py",
    "brain_alpha_ops/research/strategy_plugins.py",
    "brain_alpha_ops/research/strategy_switch.py",
    "brain_alpha_ops/research/production_context.py",
    "brain_alpha_ops/scoring/release_score_gate.py",
    "brain_alpha_ops/data/official_context_validation.py",
    "scripts/check_dependency_policy.py",
    "scripts/check_brain_contract.py",
    "scripts/check_diagnostic_report.py",
    "scripts/check_diagnosis_gap_coverage.py",
    "scripts/final_release_gate.py",
    "scripts/check_web_console_contract.py",
    "scripts/check_frontend_innerhtml.py",
    "scripts/check_frontend_silent_catches.py",
    "scripts/check_react_build_env.py",
    "scripts/check_module_size.py",
    "scripts/check_optional_tooling.py",
    "scripts/check_official_context.py",
    "scripts/check_python_silent_broad_exceptions.py",
    "scripts/check_frontend_surface_parity.py",
    "scripts/check_review_gap_closure_tracker.py",
    "scripts/check_defect_analysis_report.py",
    "scripts/check_v5_defect_tracking.py",
    "scripts/check_prod_defect_tracking.py",
    "scripts/check_text_encoding.py",
    "scripts/check_tracked_data_inventory.py",
    "scripts/check_candidate_scientific_audit.py",
    "scripts/quality_gate.py",
    "tests/test_frontend_surface_parity.py",
    "tests/test_quality_gate.py",
    "tests/test_review_gap_closure_tracker.py",
    "tests/test_defect_analysis_report.py",
    "tests/test_v5_defect_tracking.py",
    "tests/test_prod_defect_tracking.py",
    "tests/test_tracked_data_inventory.py",
    "tests/test_candidate_scientific_audit_check.py",
    "tests/test_strategy_plugins.py",
    "tests/test_production_context.py",
    "tests/test_official_context_validation.py",
    "tests/test_web_assistant_snapshots.py",
    "tests/test_web_build_inline.py",
    "tests/test_web_console_contract.py",
    "tests/test_frontend_innerhtml_guard.py",
    "tests/test_frontend_silent_catches_guard.py",
    "tests/test_python_silent_broad_exceptions_guard.py",
    "tests/test_react_build_env_check.py",
    "tests/test_web_check_batch_job.py",
    "tests/test_web_check_availability.py",
    "tests/test_web_candidate_check.py",
    "tests/test_web_candidate_scientific_audit.py",
    "tests/test_web_candidate_generation.py",
    "tests/test_web_candidate_optimization.py",
    "tests/test_web_candidate_payloads.py",
    "tests/test_web_candidate_selection.py",
    "tests/test_web_cloud_snapshot.py",
    "tests/test_web_cloud_context_refresh.py",
    "tests/test_web_get_handlers.py",
    "tests/test_web_handler_dispatch.py",
    "tests/test_web_post_handlers.py",
    "tests/test_web_run_job.py",
    "tests/test_web_runtime_state.py",
    "tests/test_web_security.py",
    "tests/test_web_server_lifecycle.py",
    "tests/test_web_review_api.py",
    "tests/test_web_sqlite_indexes.py",
    "tests/test_web_submission_batch.py",
    "tests/test_web_submission_single.py",
    "tests/test_web_submission_safety.py",
    "tests/test_web_sync_job.py",
    "tests/test_web_sync_payload.py",
    "tests/test_anti_overfit.py",
    "tests/test_batch_backtest_coordinator.py",
    "tests/test_dataset_selection.py",
    "tests/test_expression_engine.py",
    "tests/test_experience_feedback.py",
    "tests/test_generation_phase.py",
    "tests/test_knowledge_base.py",
    "tests/test_llm_review.py",
    "tests/test_official_workflow.py",
    "tests/test_research_cycle_orchestrator.py",
    "tests/test_record_sqlite_index.py",
    "tests/test_rolling_validation.py",
    "tests/test_robustness_policy.py",
    "tests/test_strategy_switch.py",
    "tests/test_task_executor.py",
]

StepRunner = Callable[[], tuple[bool, dict]]


def _subprocess_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key in SUBPROCESS_ENV_ALLOWLIST}
    local_deps = ROOT / ".codex_pydeps"
    pycache_prefix = ROOT / ".pytest_cache_runtime" / "pycache"
    pycache_prefix.mkdir(parents=True, exist_ok=True)
    python_paths: list[str] = []
    if local_deps.exists():
        python_paths.append(str(local_deps))
    existing = env.get("PYTHONPATH", "")
    if existing:
        python_paths.append(existing)
    if python_paths:
        env["PYTHONPATH"] = os.pathsep.join(python_paths)
    env.setdefault("PYTHONUTF8", "1")
    env["PYTHONPYCACHEPREFIX"] = str(pycache_prefix)
    return env


def _run_python_module(
    args: list[str],
    *,
    timeout_seconds: int | float = DEFAULT_SUBPROCESS_TIMEOUT_SECONDS,
) -> tuple[bool, dict]:
    started = time.perf_counter()
    command = [sys.executable, *args]
    try:
        proc = subprocess.run(
            command,
            cwd=str(ROOT),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            env=_subprocess_env(),
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        duration = round(time.perf_counter() - started, 3)
        stdout = _timeout_text(exc.stdout)
        stderr = _timeout_text(exc.stderr, f"command timed out after {timeout_seconds}s")
        return False, {
            "command": command,
            "exit_code": 124,
            "duration_seconds": duration,
            "timeout_seconds": timeout_seconds,
            "stdout": stdout[-4000:],
            "stderr": stderr[-4000:],
        }
    return proc.returncode == 0, {
        "command": command,
        "exit_code": proc.returncode,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "timeout_seconds": timeout_seconds,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
    }


def _timeout_text(value: str | bytes | None, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


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
    return _run_python_module(args)


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
    return _run_python_module(["scripts/check_parameter_traceability.py", "--config", str(config_path), "--json"])


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
            str(ROOT / "docs" / "ALPHA_PRODUCTION_DIAGNOSIS_20260522.md"),
            "--json",
        ]
    )


def _review_gap_closure_tracker() -> tuple[bool, dict]:
    return _run_python_module(["scripts/check_review_gap_closure_tracker.py", "--json"])


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


def run_quality_gate(
    *,
    config_path: Path = DEFAULT_CONFIG,
    html_path: Path = DEFAULT_HTML,
    include_all_secrets: bool = False,
    include_git_history_secrets: bool = False,
    dependency_audit: bool = False,
    optional_tooling: bool = False,
    skip_compile: bool = False,
    skip_tests: bool = False,
    coverage: bool = False,
    pytest_args: list[str] | None = None,
    ruff: bool = False,
    mypy: bool = False,
    strict_optional_tooling: bool = False,
    strict_official_context: bool = False,
    strict_react_build: bool = False,
    run_react_build: bool = False,
    react_preview_smoke: bool = False,
    fail_on_frontend_surface_gaps: bool = False,
    fail_on_unmapped_frontend_surface_plan: bool = False,
    fail_on_unimplemented_frontend_surface_plan: bool = False,
    fail_on_stale_frontend_surface_plan: bool = False,
    fail_on_runtime_generated_data: bool = False,
    fail_on_changed_runtime_generated_data: bool = False,
    fail_on_unresolved_tracked_data_boundary: bool = False,
    fail_on_stale_tracked_data_boundary: bool = False,
    final_release: bool = False,
    require_live_submit_ready: bool = False,
) -> dict:
    steps = []
    if not skip_compile:
        steps.append(_step("python_compile", _compile_python))
    steps.extend([
        _step("config", lambda: _validate_config(config_path)),
        _step("dependency_policy", _dependency_policy),
        _step("redline_verification", lambda: _redline_verification(config_path)),
        _step("brain_contract_validation", lambda: _brain_contract_validation(config_path, strict=strict_official_context)),
        _step("diagnosis_gap_coverage", lambda: _diagnosis_gap_coverage(config_path, strict=strict_official_context)),
    ])
    if final_release:
        steps.extend([
            _step("canonical_compliance", lambda: _canonical_compliance(config_path)),
            _step("parameter_traceability", lambda: _parameter_traceability(config_path)),
            _step("live_submit_readiness", lambda: _live_submit_readiness(config_path, require_ready=require_live_submit_ready)),
        ])
        steps.append(_step("final_release_gate", lambda: _final_release_gate(config_path)))
    steps.extend([
        _step("frontend_inline_sync", _frontend_inline_sync),
        _step("frontend_syntax", lambda: _frontend_syntax(html_path)),
        _step("frontend_innerhtml_guard", _frontend_innerhtml_guard),
        _step("frontend_silent_catch_guard", _frontend_silent_catch_guard),
        _step("python_silent_broad_exception_guard", _python_silent_broad_exception_guard),
        _step("web_console_contract", lambda: _web_console_contract(html_path)),
        _step(
            "frontend_surface_parity",
            lambda: _frontend_surface_parity(
                fail_on_gaps=fail_on_frontend_surface_gaps,
                fail_on_unmapped_plan=fail_on_unmapped_frontend_surface_plan,
                fail_on_unimplemented_plan=fail_on_unimplemented_frontend_surface_plan,
                fail_on_stale_plan=fail_on_stale_frontend_surface_plan,
            ),
        ),
        _step("react_build_env", lambda: _react_build_env(strict=strict_react_build, run_build=run_react_build)),
    ])
    if react_preview_smoke:
        steps.append(_step("react_preview_smoke", _react_preview_smoke))
    steps.extend([
        _step("text_encoding_scan", _text_encoding_scan),
        _step(
            "tracked_data_inventory",
            lambda: _tracked_data_inventory(
                fail_on_runtime_generated=fail_on_runtime_generated_data,
                fail_on_changed_runtime_generated=fail_on_changed_runtime_generated_data,
                fail_on_unresolved_boundary=fail_on_unresolved_tracked_data_boundary,
                fail_on_stale_boundary=fail_on_stale_tracked_data_boundary,
            ),
        ),
        _step("candidate_scientific_audit", _candidate_scientific_audit),
        _step("official_context_validation", lambda: _official_context_validation(config_path, strict=strict_official_context)),
        _step("module_size_audit", _module_size_audit),
        _step("secret_scan", lambda: _secret_scan(include_all_secrets, include_git_history_secrets)),
        _step("cache_metadata_audit", _cache_metadata_audit),
        _step("diagnostic_report_sync", lambda: _diagnostic_report_sync(config_path)),
        _step("review_gap_closure_tracker", _review_gap_closure_tracker),
        _step("static_defect_analysis_report", _static_defect_analysis_report),
        _step("v5_defect_tracking", _v5_defect_tracking),
        _step("prod_defect_tracking", _prod_defect_tracking),
    ])
    if dependency_audit:
        steps.append(_step("dependency_audit", _dependency_audit))
    if optional_tooling:
        steps.append(_step("optional_tooling", lambda: _optional_tooling(strict=strict_optional_tooling)))
    if ruff:
        steps.append(_step("ruff", _ruff_check))
    if mypy:
        steps.append(_step("mypy", _mypy_check))
    if not skip_tests:
        steps.append(_step("pytest", lambda: _pytest(pytest_args or [], coverage=coverage or final_release)))
    af006_submatrix = build_quality_gate_af006_submatrix(steps)
    return {
        "ok": all(step["ok"] for step in steps),
        "schema_version": "quality_gate.v1",
        "root": str(ROOT),
        "steps": steps,
        "af006_non_submit_verification_submatrix": af006_submatrix,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run local BRAIN Alpha Ops quality gates.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Run config path to validate.")
    parser.add_argument("--html", default=str(DEFAULT_HTML), help="Built Web HTML path to syntax-check.")
    parser.add_argument("--include-all-secrets", action="store_true", help="Scan all text-like files for secrets.")
    parser.add_argument("--include-git-history-secrets", action="store_true", help="Also scan Git history for known leaked secret hashes.")
    parser.add_argument("--dependency-audit", action="store_true", help="Run pip-audit when installed.")
    parser.add_argument("--optional-tooling", action="store_true", help="Report optional ruff/mypy/pip-audit availability without enforcing it.")
    parser.add_argument("--strict-optional-tooling", action="store_true", help="Fail optional tooling check when ruff/mypy/pip-audit are missing.")
    parser.add_argument("--strict-official-context", action="store_true", help="Fail when official fields/operators/datasets metadata is stale.")
    parser.add_argument("--strict-react-build", action="store_true", help="Fail when React build prerequisites are missing.")
    parser.add_argument("--run-react-build", action="store_true", help="Run npm run build after React build prerequisites are available.")
    parser.add_argument("--react-preview-smoke", action="store_true", help="Smoke-test the built React artifact through launch_web.py --frontend react.")
    parser.add_argument("--fail-on-frontend-surface-gaps", action="store_true", help="Fail when inline production views and React mirror tabs have navigation gaps.")
    parser.add_argument("--fail-on-unmapped-frontend-surface-plan", action="store_true", help="Fail when an inline view has no frontend surface parity plan entry.")
    parser.add_argument("--fail-on-unimplemented-frontend-surface-plan", action="store_true", help="Fail when frontend surface parity plan entries are still planned.")
    parser.add_argument("--fail-on-stale-frontend-surface-plan", action="store_true", help="Fail when the frontend surface parity plan references removed inline views.")
    parser.add_argument(
        "--fail-on-runtime-generated-data",
        action="store_true",
        help="Fail when tracked data files match known runtime-generated paths.",
    )
    parser.add_argument(
        "--fail-on-changed-runtime-generated-data",
        action="store_true",
        help="Fail when tracked runtime-generated data files have local changes.",
    )
    parser.add_argument(
        "--fail-on-unresolved-tracked-data-boundary",
        action="store_true",
        help="Fail when tracked runtime-generated data lacks explicit keep/remove decisions.",
    )
    parser.add_argument(
        "--fail-on-stale-tracked-data-boundary",
        action="store_true",
        help="Fail when the tracked data boundary plan references files that are no longer tracked.",
    )
    parser.add_argument("--final-release", action="store_true", help="Run fail-closed final release readiness checks.")
    parser.add_argument("--ruff", action="store_true", help="Run ruff on the incremental static-analysis target set.")
    parser.add_argument("--mypy", action="store_true", help="Run mypy on the incremental static-analysis target set.")
    parser.add_argument("--skip-compile", action="store_true", help="Skip Python compileall syntax checks.")
    parser.add_argument("--skip-tests", action="store_true", help="Skip pytest for a fast preflight.")
    parser.add_argument("--coverage", action="store_true", help="Run pytest with the configured 80%% coverage threshold.")
    parser.add_argument(
        "--require-live-submit-ready",
        action="store_true",
        help="When --final-release is used, fail unless check_live_submit_readiness.py reports an eligible candidate.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER, help="Optional pytest args after --.")
    args = parser.parse_args(argv)

    pytest_args = list(args.pytest_args or [])
    if pytest_args and pytest_args[0] == "--":
        pytest_args = pytest_args[1:]
    result = run_quality_gate(
        config_path=Path(args.config),
        html_path=Path(args.html),
        include_all_secrets=args.include_all_secrets,
        include_git_history_secrets=args.include_git_history_secrets,
        dependency_audit=args.dependency_audit,
        optional_tooling=args.optional_tooling,
        strict_optional_tooling=args.strict_optional_tooling,
        strict_official_context=args.strict_official_context,
        strict_react_build=args.strict_react_build,
        run_react_build=args.run_react_build,
        react_preview_smoke=args.react_preview_smoke,
        fail_on_frontend_surface_gaps=args.fail_on_frontend_surface_gaps,
        fail_on_unmapped_frontend_surface_plan=args.fail_on_unmapped_frontend_surface_plan,
        fail_on_unimplemented_frontend_surface_plan=args.fail_on_unimplemented_frontend_surface_plan,
        fail_on_stale_frontend_surface_plan=args.fail_on_stale_frontend_surface_plan,
        fail_on_runtime_generated_data=args.fail_on_runtime_generated_data,
        fail_on_changed_runtime_generated_data=args.fail_on_changed_runtime_generated_data,
        fail_on_unresolved_tracked_data_boundary=args.fail_on_unresolved_tracked_data_boundary,
        fail_on_stale_tracked_data_boundary=args.fail_on_stale_tracked_data_boundary,
        final_release=args.final_release,
        require_live_submit_ready=args.require_live_submit_ready,
        ruff=args.ruff,
        mypy=args.mypy,
        skip_compile=args.skip_compile,
        skip_tests=args.skip_tests,
        coverage=args.coverage,
        pytest_args=pytest_args,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for step in result["steps"]:
            status = "PASS" if step["ok"] else "FAIL"
            print(f"[{status}] {step['name']} ({step.get('duration_seconds', 0)}s)")
            if not step["ok"]:
                output = (step.get("stdout") or "") + (step.get("stderr") or "")
                if output.strip():
                    print(output.strip()[-2000:])
        print("Quality gate passed." if result["ok"] else "Quality gate failed.")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
