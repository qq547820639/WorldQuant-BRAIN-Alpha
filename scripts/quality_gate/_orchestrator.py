"""``run_quality_gate`` orchestrator that assembles the ordered step list.

Split from the former ``scripts/quality_gate.py`` monolith (Task A5).
"""

from __future__ import annotations

from pathlib import Path

from scripts.af006_quality_submatrix import build_quality_gate_af006_submatrix

from ._constants import DEFAULT_CONFIG, DEFAULT_HTML, ROOT
from ._steps import (
    _brain_contract_validation,
    _cache_metadata_audit,
    _candidate_scientific_audit,
    _canonical_compliance,
    _compile_python,
    _dependency_audit,
    _dependency_policy,
    _diagnostic_report_sync,
    _diagnosis_gap_coverage,
    _final_release_gate,
    _frontend_inline_sync,
    _frontend_innerhtml_guard,
    _frontend_silent_catch_guard,
    _frontend_surface_parity,
    _frontend_syntax,
    _live_submit_readiness,
    _module_size_audit,
    _mypy_check,
    _official_context_validation,
    _optional_tooling,
    _parameter_traceability,
    _prod_defect_tracking,
    _python_silent_broad_exception_guard,
    _pytest,
    _react_build_env,
    _react_preview_smoke,
    _redline_verification,
    _review_gap_closure_tracker,
    _ruff_check,
    _secret_scan,
    _static_defect_analysis_report,
    _step,
    _text_encoding_scan,
    _tracked_data_inventory,
    _validate_config,
    _v5_defect_tracking,
    _web_console_contract,
)


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
