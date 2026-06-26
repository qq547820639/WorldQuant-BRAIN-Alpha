import json
import subprocess
import tomllib
from pathlib import Path
from types import SimpleNamespace

from brain_alpha_ops.config import RunConfig, write_run_config
from scripts import quality_gate
from scripts.final_release_gate import run_final_release_gate
from scripts.check_dependency_policy import check_dependency_policy
from scripts.check_module_size import check_module_size
from scripts.check_optional_tooling import check_optional_tooling
from scripts.check_text_encoding import check_text_encoding
from tests.production_api_stub import write_template_safe_official_context


def _config_path(tmp_path: Path) -> Path:
    config_path = tmp_path / "run_config.json"
    write_run_config(RunConfig(environment="production"), config_path)
    return config_path


def _complete_af_tracker(tmp_path: Path) -> Path:
    tracker = tmp_path / "implementation-tracker.md"
    rows = [
        "# Implementation Tracker",
        "",
        "tracked_items:",
    ]
    for index in range(6, 26):
        rows.append(f"- AF-{index:03d} | Module {index} | Release module {index} | done | verified")
    tracker.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return tracker


def _release_config_with_official_context(tmp_path: Path) -> Path:
    config = json.loads((Path(__file__).resolve().parents[1] / "config" / "run_config.json").read_text(encoding="utf-8"))
    config["ops"]["storage_dir"] = str(tmp_path / "data")
    config_path = tmp_path / "run_config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    fixture_config = SimpleNamespace(
        ops=SimpleNamespace(
            storage_dir=config["ops"]["storage_dir"],
            official_api=SimpleNamespace(context_cache_ttl_seconds=3600),
        )
    )
    write_template_safe_official_context(fixture_config)
    (tmp_path / "data" / "official_context_refresh_status.json").write_text(
        json.dumps({"schema_version": "official_context_refresh.v1", "ok": True, "status": "refreshed"}),
        encoding="utf-8",
    )
    return config_path


def test_quality_gate_subprocess_env_filters_sensitive_values(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("PYTHONPATH", "/tmp/custom-pythonpath")
    monkeypatch.setenv("BRAIN_PASSWORD", "super-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")

    env = quality_gate._subprocess_env()

    assert env["PATH"] == "/usr/bin"
    assert env["PYTHONUTF8"] == "1"
    assert env["PYTHONPYCACHEPREFIX"].replace("\\", "/").endswith(".pytest_cache_runtime/pycache")
    assert env["PYTHONPATH"].replace("\\", "/").endswith("/tmp/custom-pythonpath")
    assert "BRAIN_PASSWORD" not in env
    assert "OPENAI_API_KEY" not in env


def test_quality_gate_run_python_module_sets_timeout_and_reports_timeout(monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured.update(kwargs)
        raise subprocess.TimeoutExpired(command, timeout=7, output="partial stdout", stderr=b"partial stderr")

    monkeypatch.setattr(quality_gate.subprocess, "run", fake_run)

    ok, detail = quality_gate._run_python_module(["slow.py"], timeout_seconds=7)

    assert ok is False
    assert captured["timeout"] == 7
    assert "BRAIN_PASSWORD" not in captured["env"]
    assert detail["exit_code"] == 124
    assert detail["timeout_seconds"] == 7
    assert detail["stdout"] == "partial stdout"
    assert detail["stderr"] == "partial stderr"


def test_quality_gate_runs_core_steps_and_skips_pytest(monkeypatch, tmp_path):
    calls = []

    def fake_run(args):
        calls.append(args)
        return True, {"command": args, "exit_code": 0, "duration_seconds": 0.01, "stdout": "", "stderr": ""}

    monkeypatch.setattr(quality_gate, "_run_python_module", fake_run)

    result = quality_gate.run_quality_gate(
        config_path=_config_path(tmp_path),
        html_path=tmp_path / "index.html",
        skip_tests=True,
    )

    assert result["ok"] is True
    assert [step["name"] for step in result["steps"]] == [
        "python_compile",
        "config",
        "dependency_policy",
        "redline_verification",
        "brain_contract_validation",
        "diagnosis_gap_coverage",
        "frontend_inline_sync",
        "frontend_syntax",
        "frontend_innerhtml_guard",
        "frontend_silent_catch_guard",
        "python_silent_broad_exception_guard",
        "web_console_contract",
        "frontend_surface_parity",
        "react_build_env",
        "text_encoding_scan",
        "tracked_data_inventory",
        "candidate_scientific_audit",
        "official_context_validation",
        "module_size_audit",
        "secret_scan",
        "cache_metadata_audit",
        "diagnostic_report_sync",
        "review_gap_closure_tracker",
        "static_defect_analysis_report",
        "v5_defect_tracking",
        "prod_defect_tracking",
    ]
    assert all("-m" not in call or "pytest" not in call for call in calls)
    assert any(
        call == [
            "scripts/check_defect_analysis_report.py",
            "--report",
            "docs/STATIC_ANALYSIS_DEFECT_REPORT_20260603.md",
            "--json",
        ]
        for call in calls
    )
    assert any(call == ["scripts/check_v5_defect_tracking.py", "--json"] for call in calls)
    assert any(call == ["scripts/check_prod_defect_tracking.py", "--json"] for call in calls)


def test_quality_gate_includes_pytest_args_and_propagates_failure(monkeypatch, tmp_path):
    def fake_run(args, **_kwargs):
        ok = not any(str(arg).endswith("scan_sensitive_artifacts.py") for arg in args)
        detail = {"command": args, "exit_code": 0 if ok else 1, "duration_seconds": 0.01, "stdout": "", "stderr": ""}
        if not ok:
            detail["actionable_ok"] = False
        return ok, detail

    monkeypatch.setattr(quality_gate, "_run_python_module", fake_run)

    result = quality_gate.run_quality_gate(
        config_path=_config_path(tmp_path),
        html_path=tmp_path / "index.html",
        include_all_secrets=True,
        pytest_args=["tests/test_web.py"],
    )

    assert result["ok"] is False
    assert [step["name"] for step in result["steps"]] == [
        "python_compile",
        "config",
        "dependency_policy",
        "redline_verification",
        "brain_contract_validation",
        "diagnosis_gap_coverage",
        "frontend_inline_sync",
        "frontend_syntax",
        "frontend_innerhtml_guard",
        "frontend_silent_catch_guard",
        "python_silent_broad_exception_guard",
        "web_console_contract",
        "frontend_surface_parity",
        "react_build_env",
        "text_encoding_scan",
        "tracked_data_inventory",
        "candidate_scientific_audit",
        "official_context_validation",
        "module_size_audit",
        "secret_scan",
        "cache_metadata_audit",
        "diagnostic_report_sync",
        "review_gap_closure_tracker",
        "static_defect_analysis_report",
        "v5_defect_tracking",
        "prod_defect_tracking",
        "pytest",
    ]
    secret_scan_step = next(step for step in result["steps"] if step["name"] == "secret_scan")
    pytest_step = next(step for step in result["steps"] if step["name"] == "pytest")
    assert "--include-all" in secret_scan_step["command"]
    assert pytest_step["command"][-1] == "tests/test_web.py"


def test_quality_gate_can_include_git_history_secret_scan(monkeypatch, tmp_path):
    def fake_run(args):
        return True, {"command": args, "exit_code": 0, "duration_seconds": 0.01, "stdout": "", "stderr": ""}

    monkeypatch.setattr(quality_gate, "_run_python_module", fake_run)

    result = quality_gate.run_quality_gate(
        config_path=_config_path(tmp_path),
        html_path=tmp_path / "index.html",
        include_all_secrets=True,
        include_git_history_secrets=True,
        skip_tests=True,
    )

    assert result["ok"] is True
    secret_scan_command = next(step for step in result["steps"] if step["name"] == "secret_scan")["command"]
    assert "--include-all" in secret_scan_command
    assert "--include-git-history" in secret_scan_command


def test_quality_gate_can_skip_compile(monkeypatch, tmp_path):
    calls = []

    def fake_run(args):
        calls.append(args)
        return True, {"command": args, "exit_code": 0, "duration_seconds": 0.01, "stdout": "", "stderr": ""}

    monkeypatch.setattr(quality_gate, "_run_python_module", fake_run)

    result = quality_gate.run_quality_gate(
        config_path=_config_path(tmp_path),
        html_path=tmp_path / "index.html",
        skip_compile=True,
        skip_tests=True,
    )

    assert result["ok"] is True
    assert [step["name"] for step in result["steps"]] == ["config", "dependency_policy", "redline_verification", "brain_contract_validation", "diagnosis_gap_coverage", "frontend_inline_sync", "frontend_syntax", "frontend_innerhtml_guard", "frontend_silent_catch_guard", "python_silent_broad_exception_guard", "web_console_contract", "frontend_surface_parity", "react_build_env", "text_encoding_scan", "tracked_data_inventory", "candidate_scientific_audit", "official_context_validation", "module_size_audit", "secret_scan", "cache_metadata_audit", "diagnostic_report_sync", "review_gap_closure_tracker", "static_defect_analysis_report", "v5_defect_tracking", "prod_defect_tracking"]
    assert not any("compileall" in call for call in calls)


def test_quality_gate_can_include_dependency_audit(monkeypatch, tmp_path):
    calls = []

    def fake_run(args):
        calls.append(args)
        return True, {"command": args, "exit_code": 0, "duration_seconds": 0.01, "stdout": "", "stderr": ""}

    monkeypatch.setattr(quality_gate, "_run_python_module", fake_run)

    result = quality_gate.run_quality_gate(
        config_path=_config_path(tmp_path),
        html_path=tmp_path / "index.html",
        dependency_audit=True,
        skip_tests=True,
    )

    assert result["ok"] is True
    assert [step["name"] for step in result["steps"]] == [
        "python_compile",
        "config",
        "dependency_policy",
        "redline_verification",
        "brain_contract_validation",
        "diagnosis_gap_coverage",
        "frontend_inline_sync",
        "frontend_syntax",
        "frontend_innerhtml_guard",
        "frontend_silent_catch_guard",
        "python_silent_broad_exception_guard",
        "web_console_contract",
        "frontend_surface_parity",
        "react_build_env",
        "text_encoding_scan",
        "tracked_data_inventory",
        "candidate_scientific_audit",
        "official_context_validation",
        "module_size_audit",
        "secret_scan",
        "cache_metadata_audit",
        "diagnostic_report_sync",
        "review_gap_closure_tracker",
        "static_defect_analysis_report",
        "v5_defect_tracking",
        "prod_defect_tracking",
        "dependency_audit",
    ]
    assert any("pip_audit" in call for call in calls)


def test_quality_gate_can_include_optional_tooling(monkeypatch, tmp_path):
    calls = []

    def fake_run(args):
        calls.append(args)
        return True, {"command": args, "exit_code": 0, "duration_seconds": 0.01, "stdout": "", "stderr": ""}

    monkeypatch.setattr(quality_gate, "_run_python_module", fake_run)

    result = quality_gate.run_quality_gate(
        config_path=_config_path(tmp_path),
        html_path=tmp_path / "index.html",
        optional_tooling=True,
        skip_tests=True,
    )

    assert result["ok"] is True
    assert [step["name"] for step in result["steps"]][-1] == "optional_tooling"
    assert any(any("check_optional_tooling.py" in str(arg) for arg in call) for call in calls)
    assert any("brain_alpha_ops.compliance.redline_verifier" in call for call in calls)


def test_quality_gate_can_include_static_analysis(monkeypatch, tmp_path):
    calls = []

    def fake_run(args):
        calls.append(args)
        return True, {"command": args, "exit_code": 0, "duration_seconds": 0.01, "stdout": "", "stderr": ""}

    monkeypatch.setattr(quality_gate, "_run_python_module", fake_run)

    result = quality_gate.run_quality_gate(
        config_path=_config_path(tmp_path),
        html_path=tmp_path / "index.html",
        optional_tooling=True,
        strict_optional_tooling=True,
        ruff=True,
        mypy=True,
        skip_tests=True,
    )

    assert result["ok"] is True
    assert [step["name"] for step in result["steps"]][-3:] == ["optional_tooling", "ruff", "mypy"]
    assert any("--strict" in call for call in calls if "check_optional_tooling.py" in str(call))
    assert any("ruff" in call for call in calls)
    assert any("mypy" in call for call in calls)
    assert any("scripts/check_review_gap_closure_tracker.py" in call for call in calls if "ruff" in call)
    assert any("scripts/check_review_gap_closure_tracker.py" in call for call in calls if "mypy" in call)
    assert any("scripts/check_defect_analysis_report.py" in call for call in calls if "ruff" in call)
    assert any("scripts/check_defect_analysis_report.py" in call for call in calls if "mypy" in call)
    assert any("scripts/check_v5_defect_tracking.py" in call for call in calls if "ruff" in call)
    assert any("scripts/check_v5_defect_tracking.py" in call for call in calls if "mypy" in call)
    assert any("scripts/check_prod_defect_tracking.py" in call for call in calls if "ruff" in call)
    assert any("scripts/check_prod_defect_tracking.py" in call for call in calls if "mypy" in call)
    assert any("scripts/check_frontend_innerhtml.py" in call for call in calls if "ruff" in call)
    assert any("scripts/check_frontend_innerhtml.py" in call for call in calls if "mypy" in call)
    assert any("scripts/check_frontend_silent_catches.py" in call for call in calls if "ruff" in call)
    assert any("scripts/check_frontend_silent_catches.py" in call for call in calls if "mypy" in call)
    assert any("scripts/check_python_silent_broad_exceptions.py" in call for call in calls if "ruff" in call)
    assert any("scripts/check_python_silent_broad_exceptions.py" in call for call in calls if "mypy" in call)
    assert any("tests/test_review_gap_closure_tracker.py" in call for call in calls if "ruff" in call)
    assert any("tests/test_review_gap_closure_tracker.py" in call for call in calls if "mypy" in call)
    assert any("tests/test_defect_analysis_report.py" in call for call in calls if "ruff" in call)
    assert any("tests/test_defect_analysis_report.py" in call for call in calls if "mypy" in call)
    assert any("tests/test_v5_defect_tracking.py" in call for call in calls if "ruff" in call)
    assert any("tests/test_v5_defect_tracking.py" in call for call in calls if "mypy" in call)
    assert any("tests/test_prod_defect_tracking.py" in call for call in calls if "ruff" in call)
    assert any("tests/test_prod_defect_tracking.py" in call for call in calls if "mypy" in call)
    assert any("tests/test_frontend_innerhtml_guard.py" in call for call in calls if "ruff" in call)
    assert any("tests/test_frontend_innerhtml_guard.py" in call for call in calls if "mypy" in call)
    assert any("tests/test_frontend_silent_catches_guard.py" in call for call in calls if "ruff" in call)
    assert any("tests/test_frontend_silent_catches_guard.py" in call for call in calls if "mypy" in call)
    assert any("tests/test_python_silent_broad_exceptions_guard.py" in call for call in calls if "ruff" in call)
    assert any("tests/test_python_silent_broad_exceptions_guard.py" in call for call in calls if "mypy" in call)


def test_quality_gate_can_require_react_build(monkeypatch, tmp_path):
    calls = []

    def fake_run(args):
        calls.append(args)
        return True, {"command": args, "exit_code": 0, "duration_seconds": 0.01, "stdout": "", "stderr": ""}

    monkeypatch.setattr(quality_gate, "_run_python_module", fake_run)

    result = quality_gate.run_quality_gate(
        config_path=_config_path(tmp_path),
        html_path=tmp_path / "index.html",
        strict_react_build=True,
        run_react_build=True,
        skip_tests=True,
    )

    assert result["ok"] is True
    react_calls = [call for call in calls if "check_react_build_env.py" in str(call)]
    assert react_calls
    assert "--strict" in react_calls[0]
    assert "--run-build" in react_calls[0]


def test_quality_gate_can_include_react_preview_smoke(monkeypatch, tmp_path):
    calls = []

    def fake_run(args):
        calls.append(args)
        return True, {"command": args, "exit_code": 0, "duration_seconds": 0.01, "stdout": "", "stderr": ""}

    monkeypatch.setattr(quality_gate, "_run_python_module", fake_run)

    result = quality_gate.run_quality_gate(
        config_path=_config_path(tmp_path),
        html_path=tmp_path / "index.html",
        react_preview_smoke=True,
        skip_tests=True,
    )

    assert result["ok"] is True
    assert "react_preview_smoke" in [step["name"] for step in result["steps"]]
    smoke_call = next(call for call in calls if call[:4] == ["launch_web.py", "--smoke-test", "--frontend", "react"])
    assert smoke_call == ["launch_web.py", "--smoke-test", "--frontend", "react", "--port", "0"]


def test_quality_gate_runs_frontend_surface_parity_and_forwards_strict_flags(monkeypatch, tmp_path):
    calls = []

    def fake_run(args):
        calls.append(args)
        return True, {"command": args, "exit_code": 0, "duration_seconds": 0.01, "stdout": "", "stderr": ""}

    monkeypatch.setattr(quality_gate, "_run_python_module", fake_run)

    result = quality_gate.run_quality_gate(
        config_path=_config_path(tmp_path),
        html_path=tmp_path / "index.html",
        fail_on_frontend_surface_gaps=True,
        fail_on_unmapped_frontend_surface_plan=True,
        fail_on_unimplemented_frontend_surface_plan=True,
        fail_on_stale_frontend_surface_plan=True,
        skip_tests=True,
    )

    assert result["ok"] is True
    parity_step = next(step for step in result["steps"] if step["name"] == "frontend_surface_parity")
    assert parity_step["command"] == [
        "scripts/check_frontend_surface_parity.py",
        "--json",
        "--fail-on-gaps",
        "--fail-on-unmapped-plan",
        "--fail-on-unimplemented-plan",
        "--fail-on-stale-plan",
    ]


def test_quality_gate_can_fail_on_runtime_generated_data(monkeypatch, tmp_path):
    calls = []

    def fake_run(args):
        calls.append(args)
        return True, {"command": args, "exit_code": 0, "duration_seconds": 0.01, "stdout": "", "stderr": ""}

    monkeypatch.setattr(quality_gate, "_run_python_module", fake_run)

    result = quality_gate.run_quality_gate(
        config_path=_config_path(tmp_path),
        html_path=tmp_path / "index.html",
        fail_on_runtime_generated_data=True,
        skip_tests=True,
    )

    assert result["ok"] is True
    inventory_call = next(call for call in calls if any("check_tracked_data_inventory.py" in str(arg) for arg in call))
    assert "--fail-on-runtime-generated" in inventory_call


def test_quality_gate_can_fail_on_changed_runtime_generated_data(monkeypatch, tmp_path):
    calls = []

    def fake_run(args):
        calls.append(args)
        return True, {"command": args, "exit_code": 0, "duration_seconds": 0.01, "stdout": "", "stderr": ""}

    monkeypatch.setattr(quality_gate, "_run_python_module", fake_run)

    result = quality_gate.run_quality_gate(
        config_path=_config_path(tmp_path),
        html_path=tmp_path / "index.html",
        fail_on_changed_runtime_generated_data=True,
        skip_tests=True,
    )

    assert result["ok"] is True
    inventory_call = next(call for call in calls if any("check_tracked_data_inventory.py" in str(arg) for arg in call))
    assert "--fail-on-changed-runtime-generated" in inventory_call


def test_quality_gate_can_fail_on_unresolved_tracked_data_boundary(monkeypatch, tmp_path):
    calls = []

    def fake_run(args):
        calls.append(args)
        return True, {"command": args, "exit_code": 0, "duration_seconds": 0.01, "stdout": "", "stderr": ""}

    monkeypatch.setattr(quality_gate, "_run_python_module", fake_run)

    result = quality_gate.run_quality_gate(
        config_path=_config_path(tmp_path),
        html_path=tmp_path / "index.html",
        fail_on_unresolved_tracked_data_boundary=True,
        skip_tests=True,
    )

    assert result["ok"] is True
    inventory_call = next(call for call in calls if any("check_tracked_data_inventory.py" in str(arg) for arg in call))
    assert "--fail-on-unresolved-boundary" in inventory_call


def test_quality_gate_can_fail_on_stale_tracked_data_boundary(monkeypatch, tmp_path):
    calls = []

    def fake_run(args):
        calls.append(args)
        return True, {"command": args, "exit_code": 0, "duration_seconds": 0.01, "stdout": "", "stderr": ""}

    monkeypatch.setattr(quality_gate, "_run_python_module", fake_run)

    result = quality_gate.run_quality_gate(
        config_path=_config_path(tmp_path),
        html_path=tmp_path / "index.html",
        fail_on_stale_tracked_data_boundary=True,
        skip_tests=True,
    )

    assert result["ok"] is True
    inventory_call = next(call for call in calls if any("check_tracked_data_inventory.py" in str(arg) for arg in call))
    assert "--fail-on-stale-boundary" in inventory_call


def test_quality_gate_propagates_strict_react_build_failure(monkeypatch, tmp_path):
    def fake_run(args):
        ok = not any(str(arg).endswith("check_react_build_env.py") for arg in args)
        return ok, {"command": args, "exit_code": 0 if ok else 1, "duration_seconds": 0.01, "stdout": "", "stderr": ""}

    monkeypatch.setattr(quality_gate, "_run_python_module", fake_run)

    result = quality_gate.run_quality_gate(
        config_path=_config_path(tmp_path),
        html_path=tmp_path / "index.html",
        strict_react_build=True,
        skip_tests=True,
    )

    assert result["ok"] is False
    assert [step for step in result["steps"] if step["name"] == "react_build_env"][0]["ok"] is False


def test_quality_gate_can_include_final_release_gate(monkeypatch, tmp_path):
    calls = []

    def fake_run(args):
        calls.append(args)
        return True, {"command": args, "exit_code": 0, "duration_seconds": 0.01, "stdout": "", "stderr": ""}

    monkeypatch.setattr(quality_gate, "_run_python_module", fake_run)

    result = quality_gate.run_quality_gate(
        config_path=_config_path(tmp_path),
        html_path=tmp_path / "index.html",
        final_release=True,
        skip_tests=True,
    )

    assert result["ok"] is True
    assert any("scripts/final_release_gate.py" in str(call) for call in calls)


def test_quality_gate_final_release_enforces_coverage(monkeypatch, tmp_path):
    calls = []
    kwargs_seen = []

    def fake_run(args, **kwargs):
        calls.append(args)
        kwargs_seen.append(kwargs)
        return True, {"command": args, "exit_code": 0, "duration_seconds": 0.01, "stdout": "", "stderr": ""}

    monkeypatch.setattr(quality_gate, "_run_python_module", fake_run)

    result = quality_gate.run_quality_gate(
        config_path=_config_path(tmp_path),
        html_path=tmp_path / "index.html",
        final_release=True,
    )

    assert result["ok"] is True
    pytest_call = next(call for call in calls if call[:2] == ["-m", "pytest"])
    assert pytest_call == ["-m", "pytest", "--cov=brain_alpha_ops", "--cov-report=term", "--cov-fail-under=80"]
    pytest_index = calls.index(pytest_call)
    assert kwargs_seen[pytest_index]["timeout_seconds"] == quality_gate.PYTEST_TIMEOUT_SECONDS


def test_quality_gate_final_release_includes_brain_compliance_stop_rules(monkeypatch, tmp_path):
    calls = []

    def fake_run(args, **_kwargs):
        calls.append(args)
        return True, {"command": args, "exit_code": 0, "duration_seconds": 0.01, "stdout": "", "stderr": ""}

    monkeypatch.setattr(quality_gate, "_run_python_module", fake_run)
    config_path = _config_path(tmp_path)

    result = quality_gate.run_quality_gate(
        config_path=config_path,
        html_path=tmp_path / "index.html",
        final_release=True,
        skip_tests=True,
    )

    assert result["ok"] is True
    step_names = [step["name"] for step in result["steps"]]
    assert step_names.index("canonical_compliance") < step_names.index("parameter_traceability")
    assert step_names.index("parameter_traceability") < step_names.index("live_submit_readiness")
    assert step_names.index("live_submit_readiness") < step_names.index("final_release_gate")
    assert [
        "scripts/verify_canonical_compliance.py",
        "--config",
        str(config_path),
        "--json",
        "--strict",
    ] in calls
    assert ["-m", "scripts.check_parameter_traceability", "--config", str(config_path), "--json"] in calls
    assert ["scripts/check_live_submit_readiness.py", "--config", str(config_path), "--json"] in calls
    assert ["scripts/final_release_gate.py", "--config", str(config_path), "--json"] in calls


def test_quality_gate_reports_af006_non_submit_verification_submatrix(monkeypatch, tmp_path):
    def fake_run(args, **_kwargs):
        return True, {"command": args, "exit_code": 0, "duration_seconds": 0.01, "stdout": "", "stderr": ""}

    monkeypatch.setattr(quality_gate, "_run_python_module", fake_run)
    config_path = _config_path(tmp_path)

    result = quality_gate.run_quality_gate(
        config_path=config_path,
        html_path=tmp_path / "index.html",
        final_release=True,
        react_preview_smoke=True,
        skip_tests=True,
    )

    submatrix = result["af006_non_submit_verification_submatrix"]
    axis_by_id = {axis["id"]: axis for axis in submatrix["axes"]}
    assert submatrix["schema_version"] == "af006_non_submit_verification_submatrix.v1"
    assert submatrix["task_id"] == "AF006-CI-E2E-SUBMATRIX-V2"
    assert submatrix["mode"] == "local-only/non-submit"
    assert submatrix["submit_ready_source"] == "scripts/check_live_submit_readiness.py --config config/run_config.json --json"
    assert submatrix["submit_ready_claim_allowed"] is False
    assert submatrix["real_brain_submit_executed"] is False
    assert submatrix["ok"] is True
    assert set(axis_by_id) == {"ci", "e2e", "mobile", "security"}
    assert "live_submit_readiness" in axis_by_id["ci"]["present_optional_steps"]
    assert "react_preview_smoke" in axis_by_id["e2e"]["present_optional_steps"]
    assert "frontend_surface_parity" in axis_by_id["mobile"]["present_required_steps"]
    assert "secret_scan" in axis_by_id["security"]["present_required_steps"]


def test_quality_gate_final_release_can_require_live_submit_ready(monkeypatch, tmp_path):
    calls = []

    def fake_run(args, **_kwargs):
        calls.append(args)
        return True, {"command": args, "exit_code": 0, "duration_seconds": 0.01, "stdout": "", "stderr": ""}

    monkeypatch.setattr(quality_gate, "_run_python_module", fake_run)
    config_path = _config_path(tmp_path)

    result = quality_gate.run_quality_gate(
        config_path=config_path,
        html_path=tmp_path / "index.html",
        final_release=True,
        require_live_submit_ready=True,
        skip_tests=True,
    )

    assert result["ok"] is True
    assert [
        "scripts/check_live_submit_readiness.py",
        "--config",
        str(config_path),
        "--json",
        "--require-ready",
    ] in calls


def test_quality_gate_can_enable_coverage_without_final_release(monkeypatch, tmp_path):
    calls = []
    kwargs_seen = []

    def fake_run(args, **kwargs):
        calls.append(args)
        kwargs_seen.append(kwargs)
        return True, {"command": args, "exit_code": 0, "duration_seconds": 0.01, "stdout": "", "stderr": ""}

    monkeypatch.setattr(quality_gate, "_run_python_module", fake_run)

    result = quality_gate.run_quality_gate(
        config_path=_config_path(tmp_path),
        html_path=tmp_path / "index.html",
        coverage=True,
        pytest_args=["tests/test_web.py"],
    )

    assert result["ok"] is True
    pytest_call = next(call for call in calls if call[:2] == ["-m", "pytest"])
    assert pytest_call == [
        "-m",
        "pytest",
        "--cov=brain_alpha_ops",
        "--cov-report=term",
        "--cov-fail-under=80",
        "tests/test_web.py",
    ]
    pytest_index = calls.index(pytest_call)
    assert kwargs_seen[pytest_index]["timeout_seconds"] == quality_gate.PYTEST_TIMEOUT_SECONDS


def test_quality_gate_main_parses_coverage_and_preview_flags(monkeypatch, tmp_path, capsys):
    captured = {}

    def fake_run_quality_gate(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "steps": []}

    monkeypatch.setattr(quality_gate, "run_quality_gate", fake_run_quality_gate)

    code = quality_gate.main(
        [
            "--config",
            str(tmp_path / "run_config.json"),
            "--html",
            str(tmp_path / "index.html"),
            "--coverage",
            "--react-preview-smoke",
            "--fail-on-frontend-surface-gaps",
            "--fail-on-unmapped-frontend-surface-plan",
            "--fail-on-unimplemented-frontend-surface-plan",
            "--fail-on-stale-frontend-surface-plan",
            "--fail-on-runtime-generated-data",
            "--fail-on-changed-runtime-generated-data",
            "--fail-on-unresolved-tracked-data-boundary",
            "--fail-on-stale-tracked-data-boundary",
            "--skip-tests",
            "--json",
        ]
    )

    assert code == 0
    assert captured["coverage"] is True
    assert captured["react_preview_smoke"] is True
    assert captured["fail_on_frontend_surface_gaps"] is True
    assert captured["fail_on_unmapped_frontend_surface_plan"] is True
    assert captured["fail_on_unimplemented_frontend_surface_plan"] is True
    assert captured["fail_on_stale_frontend_surface_plan"] is True
    assert captured["fail_on_runtime_generated_data"] is True
    assert captured["fail_on_changed_runtime_generated_data"] is True
    assert captured["fail_on_unresolved_tracked_data_boundary"] is True
    assert captured["fail_on_stale_tracked_data_boundary"] is True
    assert captured["skip_tests"] is True
    assert captured["config_path"] == tmp_path / "run_config.json"
    assert captured["html_path"] == tmp_path / "index.html"
    assert '"ok": true' in capsys.readouterr().out


def test_quality_gate_can_require_fresh_official_context(monkeypatch, tmp_path):
    calls = []

    def fake_run(args):
        calls.append(args)
        return True, {"command": args, "exit_code": 0, "duration_seconds": 0.01, "stdout": "", "stderr": ""}

    monkeypatch.setattr(quality_gate, "_run_python_module", fake_run)

    result = quality_gate.run_quality_gate(
        config_path=_config_path(tmp_path),
        html_path=tmp_path / "index.html",
        strict_official_context=True,
        skip_tests=True,
    )

    assert result["ok"] is True
    official_call = next(call for call in calls if any("check_official_context.py" in str(arg) for arg in call))
    contract_call = next(call for call in calls if any("check_brain_contract.py" in str(arg) for arg in call))
    assert "--strict-freshness" in official_call
    assert "--strict-freshness" in contract_call


def test_optional_tooling_reports_missing_as_non_blocking_by_default():
    def fake_runner(args):
        return (1, "", "missing", 0.01)

    result = check_optional_tooling(runner=fake_runner)

    assert result["ok"] is True
    assert set(result["missing"]) == {"ruff", "mypy", "pip_audit"}
    assert result["tools"]["ruff"]["status"] == "missing"


def test_optional_tooling_strict_mode_fails_when_missing():
    def fake_runner(args):
        return (0, "ruff 1.0", "", 0.01) if "ruff" in args else (1, "", "missing", 0.01)

    result = check_optional_tooling(strict=True, runner=fake_runner)

    assert result["ok"] is False
    assert result["missing"] == ["mypy", "pip_audit"]


def test_dependency_policy_rejects_unbounded_runtime_dependencies(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\n'
        'dependencies = ["requests>=2.32.4", "pkg @ https://example.invalid/pkg.whl"]\n',
        encoding="utf-8",
    )

    result = check_dependency_policy(pyproject)

    codes = {finding["code"] for finding in result["findings"]}
    assert result["ok"] is False
    assert "missing_runtime_upper_bound" in codes
    assert "direct_reference" in codes


def test_dependency_policy_accepts_project_pyproject():
    result = check_dependency_policy(Path(__file__).resolve().parents[1] / "pyproject.toml")

    assert result["ok"] is True
    assert result["findings"] == []


def test_research_calibration_wrapper_exports_auto_calibrate():
    from brain_alpha_ops.research.calibration import auto_calibrate_if_stalled

    assert callable(auto_calibrate_if_stalled)


def test_text_encoding_scan_rejects_mojibake(tmp_path):
    clean = tmp_path / "README.md"
    bad = tmp_path / "bad.md"
    clean.write_text("云端同步正在进行。\n", encoding="utf-8")
    bad.write_text("".join(chr(codepoint) for codepoint in (0x6D5C, 0x6220, 0xE061)) + "\n", encoding="utf-8")

    result = check_text_encoding(tmp_path, ["README.md", "bad.md"])

    assert result["ok"] is False
    assert result["findings"][0]["path"] == "bad.md"
    assert result["findings"][0]["code"] == "mojibake"


def test_text_encoding_scan_skips_node_modules(tmp_path):
    source_root = tmp_path / "brain_alpha_ops"
    dependency_file = source_root / "web" / "react_app" / "node_modules" / "pkg" / "README.md"
    source_file = source_root / "module.py"
    dependency_file.parent.mkdir(parents=True)
    source_file.write_text("print('ok')\n", encoding="utf-8")
    dependency_file.write_text(f"{chr(0xFFFD)} dependency fixture\n", encoding="utf-8")

    result = check_text_encoding(tmp_path, ["brain_alpha_ops"])

    assert result["ok"] is True
    assert result["findings"] == []


def test_text_encoding_scan_accepts_current_workspace():
    result = check_text_encoding(Path(__file__).resolve().parents[1])

    assert result["ok"] is True
    assert result["findings"] == []


def test_module_size_audit_rejects_files_above_limit(tmp_path):
    package = tmp_path / "brain_alpha_ops"
    package.mkdir()
    package.joinpath("large.py").write_text("\n".join("print('x')" for _ in range(4)), encoding="utf-8")

    result = check_module_size(tmp_path, ["brain_alpha_ops"], default_limit=3, baseline_limits={})

    assert result["ok"] is False
    assert result["findings"][0]["path"] == "brain_alpha_ops/large.py"
    assert result["findings"][0]["code"] == "module_line_limit_exceeded"


def test_module_size_audit_accepts_current_workspace():
    result = check_module_size(Path(__file__).resolve().parents[1])

    assert result["ok"] is True
    assert result["findings"] == []
    assert result["hotspots"]


def test_final_release_gate_passes_with_release_config(tmp_path):
    config = json.loads((Path(__file__).resolve().parents[1] / "config" / "run_config.json").read_text(encoding="utf-8"))
    config["ops"]["storage_dir"] = str(tmp_path / "data")
    config_path = tmp_path / "run_config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    fixture_config = SimpleNamespace(
        ops=SimpleNamespace(
            storage_dir=config["ops"]["storage_dir"],
            official_api=SimpleNamespace(context_cache_ttl_seconds=3600),
        )
    )
    write_template_safe_official_context(fixture_config)
    (tmp_path / "data" / "official_context_refresh_status.json").write_text(
        json.dumps({"schema_version": "official_context_refresh.v1", "ok": True, "status": "refreshed"}),
        encoding="utf-8",
    )

    report = run_final_release_gate(
        config_path=config_path,
        implementation_tracker_path=_complete_af_tracker(tmp_path),
    )

    assert report.passed is True
    assert report.redlines["code_strong_alignment"] is True
    assert report.redlines["dataset_id_fully_available"] is True
    assert report.redlines["full_factor_coverage"] is True
    assert report.redlines["capability_registry_aligned"] is True


def test_final_release_gate_blocks_cache_first_without_official_context_cache(tmp_path):
    config = json.loads((Path(__file__).resolve().parents[1] / "config" / "run_config.json").read_text(encoding="utf-8"))
    config["ops"]["storage_dir"] = str(tmp_path / "data")
    config["ops"]["budget"]["require_cloud_sync"] = False
    config_path = tmp_path / "run_config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    report = run_final_release_gate(config_path=config_path)

    assert report.passed is False
    assert report.redlines["full_factor_coverage"] is False
    assert any(finding.code == "CLOUD_SYNC_CACHE_MISSING" for finding in report.findings)


def test_final_release_gate_accepts_fresh_official_metadata_when_status_failed(tmp_path):
    config = json.loads((Path(__file__).resolve().parents[1] / "config" / "run_config.json").read_text(encoding="utf-8"))
    config["ops"]["storage_dir"] = str(tmp_path / "data")
    config_path = tmp_path / "run_config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    fixture_config = SimpleNamespace(
        ops=SimpleNamespace(
            storage_dir=config["ops"]["storage_dir"],
            official_api=SimpleNamespace(context_cache_ttl_seconds=3600),
        )
    )
    write_template_safe_official_context(fixture_config)
    (tmp_path / "data" / "official_context_refresh_status.json").write_text(
        json.dumps({"schema_version": "official_context_refresh.v1", "ok": False, "status": "failed"}),
        encoding="utf-8",
    )

    report = run_final_release_gate(
        config_path=config_path,
        implementation_tracker_path=_complete_af_tracker(tmp_path),
    )

    assert report.passed is True
    assert not any(finding.code == "OFFICIAL_REFRESH_NOT_VERIFIED" for finding in report.findings)


def test_final_release_gate_blocks_incomplete_af_tracker(tmp_path):
    config = json.loads((Path(__file__).resolve().parents[1] / "config" / "run_config.json").read_text(encoding="utf-8"))
    config["ops"]["storage_dir"] = str(tmp_path / "data")
    config_path = tmp_path / "run_config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    fixture_config = SimpleNamespace(
        ops=SimpleNamespace(
            storage_dir=config["ops"]["storage_dir"],
            official_api=SimpleNamespace(context_cache_ttl_seconds=3600),
        )
    )
    write_template_safe_official_context(fixture_config)
    (tmp_path / "data" / "official_context_refresh_status.json").write_text(
        json.dumps({"schema_version": "official_context_refresh.v1", "ok": True, "status": "refreshed"}),
        encoding="utf-8",
    )
    tracker = tmp_path / "implementation-tracker.md"
    tracker.write_text(
        "\n".join(
            [
                "# Implementation Tracker",
                "",
                "tracked_items:",
                "- AF-006 | Module 6 | Testing | in_progress | still open",
                "- AF-007 | Module 7 | Context | done | verified",
                "- AF-008 | Module 8 | Agents | done | verified",
                "- AF-009 | Module 9 | Config | done | verified",
                "- AF-010 | Module 10 | Scoring | done | verified",
                "- AF-010 | Module 10 duplicate | Scoring | done | duplicate",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = run_final_release_gate(
        config_path=config_path,
        implementation_tracker_path=tracker,
    )

    codes = {finding.code for finding in report.findings}
    assert report.passed is False
    assert report.redlines["implementation_tracker_complete"] is False
    assert "IMPLEMENTATION_TRACKER_AF_NOT_DONE" in codes
    assert "IMPLEMENTATION_TRACKER_AF_MISSING" in codes
    assert "IMPLEMENTATION_TRACKER_AF_DUPLICATE" in codes
    assert report.implementation_tracker["completion_claimable"] is False
    assert "AF-006" in report.implementation_tracker["non_done_statuses"]
    assert "AF-021" in report.implementation_tracker["missing_ids"]


def test_final_release_gate_reports_af_gate_matrix_without_claiming_completion(tmp_path):
    config_path = _release_config_with_official_context(tmp_path)
    tracker = tmp_path / "implementation-tracker.md"
    statuses = {
        **{index: "in_progress" for index in (6, 7, 8, 15, 16, 17, 18, 19, 20, 21, 23, 24)},
        **{index: "done" for index in range(9, 15)},
        22: "planned",
        25: "blocked",
    }
    rows = [
        "# Implementation Tracker",
        "",
        "tracked_items:",
    ]
    for index in range(6, 26):
        status = statuses[index]
        rows.append(f"- AF-{index:03d} | Module {index} | Release module {index} | {status} | evidence")
    rows.extend(["", "gap_map:", "- AF-023 is the next recommended slice: report-only artifact guidance"])
    tracker.write_text("\n".join(rows) + "\n", encoding="utf-8")

    report = run_final_release_gate(
        config_path=config_path,
        implementation_tracker_path=tracker,
    )

    summary = report.implementation_tracker["readiness_summary"]
    matrix_by_id = {row["id"]: row for row in report.implementation_tracker["gate_matrix"]}
    assert report.passed is False
    assert report.redlines["implementation_tracker_complete"] is False
    assert summary["completion_ratio"] == "6/20"
    assert summary["done_count"] == 6
    assert summary["remaining_count"] == 14
    assert summary["status_counts"] == {"blocked": 1, "done": 6, "in_progress": 12, "planned": 1}
    assert summary["blocked_ids"] == ["AF-025"]
    assert summary["next_actionable_ids"][0] == "AF-006"
    assert "AF-025" not in summary["next_actionable_ids"]
    assert summary["completion_claimable"] is False
    assert report.implementation_tracker["parse_errors"] == []
    assert matrix_by_id["AF-006"]["release_blocking"] is True
    assert matrix_by_id["AF-006"]["reason"] == "in_progress"
    assert matrix_by_id["AF-009"]["release_blocking"] is False
    assert matrix_by_id["AF-009"]["reason"] == "ready"
    assert matrix_by_id["AF-025"]["release_blocking"] is True
    assert matrix_by_id["AF-025"]["reason"] == "blocked"


def test_final_release_gate_reports_af006_non_submit_verification_submatrix(tmp_path):
    config_path = _release_config_with_official_context(tmp_path)

    report = run_final_release_gate(
        config_path=config_path,
        implementation_tracker_path=_complete_af_tracker(tmp_path),
    )

    submatrix = report.implementation_tracker["af006_non_submit_verification_submatrix"]
    axis_by_id = {axis["id"]: axis for axis in submatrix["axes"]}
    assert submatrix["schema_version"] == "af006_non_submit_verification_submatrix.v1"
    assert submatrix["task_id"] == "AF006-CI-E2E-SUBMATRIX-V2"
    assert submatrix["tracker_status"] == "done"
    assert submatrix["mode"] == "local-only/non-submit"
    assert submatrix["submit_ready_source"] == "scripts/check_live_submit_readiness.py --config config/run_config.json --json"
    assert submatrix["submit_ready_claim_allowed"] is False
    assert submatrix["real_brain_submit_executed"] is False
    assert set(axis_by_id) == {"ci", "e2e", "mobile", "security"}
    assert "live_submit_readiness" in axis_by_id["ci"]["release_gate_signals"]
    assert "react_preview_smoke" in axis_by_id["e2e"]["quality_gate_signals"]
    assert "brain_alpha_ops/web/react_app/src/components/MobileTabBar.tsx" in axis_by_id["mobile"]["source_files"]
    assert "secret_scan" in axis_by_id["security"]["quality_gate_signals"]


def test_final_release_gate_blocks_malformed_af_tracker_rows(tmp_path):
    config = json.loads((Path(__file__).resolve().parents[1] / "config" / "run_config.json").read_text(encoding="utf-8"))
    config["ops"]["storage_dir"] = str(tmp_path / "data")
    config_path = tmp_path / "run_config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    fixture_config = SimpleNamespace(
        ops=SimpleNamespace(
            storage_dir=config["ops"]["storage_dir"],
            official_api=SimpleNamespace(context_cache_ttl_seconds=3600),
        )
    )
    write_template_safe_official_context(fixture_config)
    (tmp_path / "data" / "official_context_refresh_status.json").write_text(
        json.dumps({"schema_version": "official_context_refresh.v1", "ok": True, "status": "refreshed"}),
        encoding="utf-8",
    )
    tracker = tmp_path / "implementation-tracker.md"
    rows = [
        "# Implementation Tracker",
        "",
        "tracked_items:",
    ]
    for index in range(6, 26):
        if index == 6:
            rows.append("- AF-006 | Module 6 | Testing | done")
        elif index == 7:
            rows.append("- AF-007 |  | Context | done | verified")
        else:
            rows.append(f"- AF-{index:03d} | Module {index} | Release module {index} | done | verified")
    tracker.write_text("\n".join(rows) + "\n", encoding="utf-8")

    report = run_final_release_gate(
        config_path=config_path,
        implementation_tracker_path=tracker,
    )

    codes = {finding.code for finding in report.findings}
    assert report.passed is False
    assert report.redlines["implementation_tracker_complete"] is False
    assert "IMPLEMENTATION_TRACKER_PARSE_ERROR" in codes
    assert "IMPLEMENTATION_TRACKER_AF_MISSING" in codes
    assert report.implementation_tracker["completion_claimable"] is False
    assert "AF-006" in report.implementation_tracker["missing_ids"]
    assert "AF-007" in report.implementation_tracker["missing_ids"]
    assert report.implementation_tracker["parse_errors"]


def test_final_release_gate_blocks_failed_status_when_official_metadata_is_stale(tmp_path):
    config = json.loads((Path(__file__).resolve().parents[1] / "config" / "run_config.json").read_text(encoding="utf-8"))
    config["ops"]["storage_dir"] = str(tmp_path / "data")
    config_path = tmp_path / "run_config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    fixture_config = SimpleNamespace(
        ops=SimpleNamespace(
            storage_dir=config["ops"]["storage_dir"],
            official_api=SimpleNamespace(context_cache_ttl_seconds=3600),
        )
    )
    write_template_safe_official_context(fixture_config)
    fields_meta_path = tmp_path / "data" / "official_fields.meta.json"
    fields_meta = json.loads(fields_meta_path.read_text(encoding="utf-8"))
    fields_meta["expires_at"] = "2000-01-01T00:00:00+00:00"
    fields_meta_path.write_text(json.dumps(fields_meta), encoding="utf-8")
    (tmp_path / "data" / "official_context_refresh_status.json").write_text(
        json.dumps({"schema_version": "official_context_refresh.v1", "ok": False, "status": "failed"}),
        encoding="utf-8",
    )

    report = run_final_release_gate(config_path=config_path)

    assert report.passed is False
    assert any(finding.code == "OFFICIAL_REFRESH_NOT_VERIFIED" for finding in report.findings)


def test_final_release_gate_blocks_prod_correlation_threshold_drift(tmp_path):
    config = json.loads((Path(__file__).resolve().parents[1] / "config" / "run_config.json").read_text(encoding="utf-8"))
    config["ops"]["storage_dir"] = str(tmp_path / "data")
    config["ops"]["thresholds"]["max_prod_correlation"] = 0.95
    config_path = tmp_path / "run_config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    fixture_config = SimpleNamespace(
        ops=SimpleNamespace(
            storage_dir=config["ops"]["storage_dir"],
            official_api=SimpleNamespace(context_cache_ttl_seconds=3600),
        )
    )
    write_template_safe_official_context(fixture_config)
    (tmp_path / "data" / "official_context_refresh_status.json").write_text(
        json.dumps({"schema_version": "official_context_refresh.v1", "ok": True, "status": "refreshed"}),
        encoding="utf-8",
    )

    report = run_final_release_gate(config_path=config_path)

    assert report.passed is False
    assert report.redlines["zero_threshold_drift"] is False
    assert any(
        finding.code == "THRESHOLD_DRIFT_MAX_PROD_CORRELATION"
        for finding in report.findings
    )


def test_final_release_gate_maps_official_context_lineage_to_dataset_redline(tmp_path):
    config = json.loads((Path(__file__).resolve().parents[1] / "config" / "run_config.json").read_text(encoding="utf-8"))
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    config["ops"]["storage_dir"] = str(data_dir)
    config_path = tmp_path / "run_config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    (data_dir / "official_fields.json").write_text(
        json.dumps([{"id": "close", "dataset": {"id": "pv1"}}]),
        encoding="utf-8",
    )
    (data_dir / "official_operators.json").write_text(
        json.dumps([{"name": "rank"}, {"name": "ts_delta"}]),
        encoding="utf-8",
    )
    (data_dir / "official_datasets.json").write_text(
        json.dumps([{"id": "pv1", "name": "Price Volume", "field_count": 2}]),
        encoding="utf-8",
    )
    (data_dir / "official_context_refresh_status.json").write_text(
        json.dumps({"schema_version": "official_context_refresh.v1", "ok": True, "status": "refreshed"}),
        encoding="utf-8",
    )

    report = run_final_release_gate(config_path=config_path)

    assert report.passed is False
    assert report.redlines["dataset_id_fully_available"] is False
    assert any(finding.code == "OFFICIAL_CONTEXT_DATASET_FIELD_COUNT_MISMATCH" for finding in report.findings)
