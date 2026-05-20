"""Run local quality gates before handoff or packaging."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DEFAULT_CONFIG = ROOT / "config" / "run_config.json"
DEFAULT_HTML = ROOT / "brain_alpha_ops" / "web" / "index.html"
COMPILE_TARGETS = [
    "brain_alpha_ops",
    "scripts",
    "tests",
    "build_prod.py",
    "calibrate_weights.py",
    "fetch_official_context.py",
    "launch_web.py",
    "run_pipeline.py",
    "test_api_format.py",
    "test_api_root.py",
    "test_auth.py",
    "test_datasets_api.py",
    "validate_data.py",
    "_launch_monitor.py",
    "_status.py",
]
FRONTEND_INLINE_BUILDER = ROOT / "brain_alpha_ops" / "web" / "build_inline.py"
STATIC_ANALYSIS_TARGETS = [
    "brain_alpha_ops/build_inline.py",
    "brain_alpha_ops/web/build_inline.py",
    "brain_alpha_ops/web_config.py",
    "brain_alpha_ops/web_assistant_snapshots.py",
    "brain_alpha_ops/web_check_batch_job.py",
    "brain_alpha_ops/web_check_availability.py",
    "brain_alpha_ops/web_candidate_check.py",
    "brain_alpha_ops/web_candidate_generation.py",
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
    "scripts/check_dependency_policy.py",
    "scripts/check_optional_tooling.py",
    "scripts/quality_gate.py",
    "tests/test_quality_gate.py",
    "tests/test_strategy_plugins.py",
    "tests/test_production_context.py",
    "tests/test_web_assistant_snapshots.py",
    "tests/test_web_build_inline.py",
    "tests/test_web_check_batch_job.py",
    "tests/test_web_check_availability.py",
    "tests/test_web_candidate_check.py",
    "tests/test_web_candidate_generation.py",
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
    env = os.environ.copy()
    local_deps = ROOT / ".codex_pydeps"
    python_paths: list[str] = []
    if local_deps.exists():
        python_paths.append(str(local_deps))
    existing = env.get("PYTHONPATH", "")
    if existing:
        python_paths.append(existing)
    if python_paths:
        env["PYTHONPATH"] = os.pathsep.join(python_paths)
    env.setdefault("PYTHONUTF8", "1")
    return env


def _run_python_module(args: list[str]) -> tuple[bool, dict]:
    started = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, *args],
        cwd=str(ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        env=_subprocess_env(),
    )
    return proc.returncode == 0, {
        "command": [sys.executable, *args],
        "exit_code": proc.returncode,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
    }


def _validate_config(config_path: Path) -> tuple[bool, dict]:
    return _run_python_module(["-m", "brain_alpha_ops.cli", "validate-config", "--config", str(config_path)])


def _compile_python() -> tuple[bool, dict]:
    return _run_python_module(["-m", "compileall", "-q", *COMPILE_TARGETS])


def _frontend_syntax(html_path: Path) -> tuple[bool, dict]:
    return _run_python_module(["scripts/check_frontend_syntax.py", "--html", str(html_path), "--json"])


def _frontend_inline_sync() -> tuple[bool, dict]:
    return _run_python_module([str(FRONTEND_INLINE_BUILDER), "--check", "--json"])


def _secret_scan(include_all: bool) -> tuple[bool, dict]:
    args = ["scripts/scan_sensitive_artifacts.py", "--root", str(ROOT), "--json", "--fail-on-findings"]
    if include_all:
        args.append("--include-all")
    return _run_python_module(args)


def _dependency_policy() -> tuple[bool, dict]:
    return _run_python_module(["scripts/check_dependency_policy.py", "--pyproject", str(ROOT / "pyproject.toml"), "--json"])


def _redline_verification() -> tuple[bool, dict]:
    return _run_python_module(["-m", "brain_alpha_ops.compliance.redline_verifier", "--block", "--json"])


def _cache_metadata_audit() -> tuple[bool, dict]:
    """Check cache metadata freshness (non-blocking advisory)."""
    from brain_alpha_ops.data.cache_metadata import build_cache_audit_snapshot
    from brain_alpha_ops.config import runtime_project_root
    cache_dir = runtime_project_root() / "data" / "api_cache"
    snapshot = build_cache_audit_snapshot(cache_dir)
    ok = snapshot.get("stale_count", 0) == 0
    return ok, {"exit_code": 0, "command": "cache_metadata_audit", **snapshot}


def _pytest(pytest_args: list[str]) -> tuple[bool, dict]:
    return _run_python_module(["-m", "pytest", *(pytest_args or [])])


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
            "--ignore-missing-imports",
            "--follow-imports=silent",
            *STATIC_ANALYSIS_TARGETS,
        ]
    )


def _step(name: str, runner: StepRunner) -> dict:
    ok, detail = runner()
    return {"name": name, "ok": ok, **detail}


def run_quality_gate(
    *,
    config_path: Path = DEFAULT_CONFIG,
    html_path: Path = DEFAULT_HTML,
    include_all_secrets: bool = False,
    dependency_audit: bool = False,
    optional_tooling: bool = False,
    skip_compile: bool = False,
    skip_tests: bool = False,
    pytest_args: list[str] | None = None,
    ruff: bool = False,
    mypy: bool = False,
    strict_optional_tooling: bool = False,
) -> dict:
    steps = []
    if not skip_compile:
        steps.append(_step("python_compile", _compile_python))
    steps.extend([
        _step("config", lambda: _validate_config(config_path)),
        _step("dependency_policy", _dependency_policy),
        _step("redline_verification", _redline_verification),
        _step("frontend_inline_sync", _frontend_inline_sync),
        _step("frontend_syntax", lambda: _frontend_syntax(html_path)),
        _step("secret_scan", lambda: _secret_scan(include_all_secrets)),
        _step("cache_metadata_audit", _cache_metadata_audit),
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
        steps.append(_step("pytest", lambda: _pytest(pytest_args or [])))
    return {
        "ok": all(step["ok"] for step in steps),
        "schema_version": "quality_gate.v1",
        "root": str(ROOT),
        "steps": steps,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run local BRAIN Alpha Ops quality gates.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Run config path to validate.")
    parser.add_argument("--html", default=str(DEFAULT_HTML), help="Built Web HTML path to syntax-check.")
    parser.add_argument("--include-all-secrets", action="store_true", help="Scan all text-like files for secrets.")
    parser.add_argument("--dependency-audit", action="store_true", help="Run pip-audit when installed.")
    parser.add_argument("--optional-tooling", action="store_true", help="Report optional ruff/mypy/pip-audit availability without enforcing it.")
    parser.add_argument("--strict-optional-tooling", action="store_true", help="Fail optional tooling check when ruff/mypy/pip-audit are missing.")
    parser.add_argument("--ruff", action="store_true", help="Run ruff on the incremental static-analysis target set.")
    parser.add_argument("--mypy", action="store_true", help="Run mypy on the incremental static-analysis target set.")
    parser.add_argument("--skip-compile", action="store_true", help="Skip Python compileall syntax checks.")
    parser.add_argument("--skip-tests", action="store_true", help="Skip pytest for a fast preflight.")
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
        dependency_audit=args.dependency_audit,
        optional_tooling=args.optional_tooling,
        strict_optional_tooling=args.strict_optional_tooling,
        ruff=args.ruff,
        mypy=args.mypy,
        skip_compile=args.skip_compile,
        skip_tests=args.skip_tests,
        pytest_args=pytest_args,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for step in result["steps"]:
            status = "PASS" if step["ok"] else "FAIL"
            print(f"[{status}] {step['name']} ({step['duration_seconds']}s)")
            if not step["ok"]:
                output = (step.get("stdout") or "") + (step.get("stderr") or "")
                if output.strip():
                    print(output.strip()[-2000:])
        print("Quality gate passed." if result["ok"] else "Quality gate failed.")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
