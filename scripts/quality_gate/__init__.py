"""Run local quality gates before handoff or packaging.

Public API is re-exported here from the ``scripts.quality_gate`` subpackage
(split from the former ``scripts/quality_gate.py`` monolith, Task A5).
External import paths are unchanged::

    from scripts.quality_gate import main, run_quality_gate
    python3 -m scripts.quality_gate --help
"""

from __future__ import annotations

import subprocess  # re-exported: tests monkeypatch ``quality_gate.subprocess.run``

from ._cli import main
from ._constants import (
    COMPILE_TARGETS,
    COVERAGE_PYTEST_ARGS,
    DEFAULT_CONFIG,
    DEFAULT_HTML,
    DEFAULT_SUBPROCESS_TIMEOUT_SECONDS,
    FRONTEND_INLINE_BUILDER,
    PYTEST_TIMEOUT_SECONDS,
    ROOT,
    STATIC_ANALYSIS_TARGETS,
    SUBPROCESS_ENV_ALLOWLIST,
)
from ._orchestrator import run_quality_gate
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
    _quality_gate_progress,
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
from ._subprocess import StepRunner, _run_python_module, _subprocess_env, _timeout_text

__all__ = [
    "COMPILE_TARGETS",
    "COVERAGE_PYTEST_ARGS",
    "DEFAULT_CONFIG",
    "DEFAULT_HTML",
    "DEFAULT_SUBPROCESS_TIMEOUT_SECONDS",
    "FRONTEND_INLINE_BUILDER",
    "PYTEST_TIMEOUT_SECONDS",
    "ROOT",
    "STATIC_ANALYSIS_TARGETS",
    "SUBPROCESS_ENV_ALLOWLIST",
    "StepRunner",
    "main",
    "run_quality_gate",
]
