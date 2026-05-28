import json
from pathlib import Path
from types import SimpleNamespace

from scripts import quality_gate
from scripts.final_release_gate import run_final_release_gate
from scripts.check_dependency_policy import check_dependency_policy
from scripts.check_module_size import check_module_size
from scripts.check_optional_tooling import check_optional_tooling
from scripts.check_text_encoding import check_text_encoding
from tests.production_api_stub import write_template_safe_official_context


def test_quality_gate_runs_core_steps_and_skips_pytest(monkeypatch, tmp_path):
    calls = []

    def fake_run(args):
        calls.append(args)
        return True, {"command": args, "exit_code": 0, "duration_seconds": 0.01, "stdout": "", "stderr": ""}

    monkeypatch.setattr(quality_gate, "_run_python_module", fake_run)

    result = quality_gate.run_quality_gate(
        config_path=tmp_path / "run_config.json",
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
        "web_console_contract",
        "react_build_env",
        "text_encoding_scan",
        "official_context_validation",
        "module_size_audit",
        "secret_scan",
        "cache_metadata_audit",
        "diagnostic_report_sync",
    ]
    assert all("-m" not in call or "pytest" not in call for call in calls)


def test_quality_gate_includes_pytest_args_and_propagates_failure(monkeypatch, tmp_path):
    def fake_run(args):
        ok = not any(str(arg).endswith("scan_sensitive_artifacts.py") for arg in args)
        return ok, {"command": args, "exit_code": 0 if ok else 1, "duration_seconds": 0.01, "stdout": "", "stderr": ""}

    monkeypatch.setattr(quality_gate, "_run_python_module", fake_run)

    result = quality_gate.run_quality_gate(
        config_path=tmp_path / "run_config.json",
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
        "web_console_contract",
        "react_build_env",
        "text_encoding_scan",
        "official_context_validation",
        "module_size_audit",
        "secret_scan",
        "cache_metadata_audit",
        "diagnostic_report_sync",
        "pytest",
    ]
    assert "--include-all" in result["steps"][14]["command"]
    assert result["steps"][17]["command"][-1] == "tests/test_web.py"


def test_quality_gate_can_include_git_history_secret_scan(monkeypatch, tmp_path):
    def fake_run(args):
        return True, {"command": args, "exit_code": 0, "duration_seconds": 0.01, "stdout": "", "stderr": ""}

    monkeypatch.setattr(quality_gate, "_run_python_module", fake_run)

    result = quality_gate.run_quality_gate(
        config_path=tmp_path / "run_config.json",
        html_path=tmp_path / "index.html",
        include_all_secrets=True,
        include_git_history_secrets=True,
        skip_tests=True,
    )

    assert result["ok"] is True
    secret_scan_command = result["steps"][14]["command"]
    assert "--include-all" in secret_scan_command
    assert "--include-git-history" in secret_scan_command


def test_quality_gate_can_skip_compile(monkeypatch, tmp_path):
    calls = []

    def fake_run(args):
        calls.append(args)
        return True, {"command": args, "exit_code": 0, "duration_seconds": 0.01, "stdout": "", "stderr": ""}

    monkeypatch.setattr(quality_gate, "_run_python_module", fake_run)

    result = quality_gate.run_quality_gate(
        config_path=tmp_path / "run_config.json",
        html_path=tmp_path / "index.html",
        skip_compile=True,
        skip_tests=True,
    )

    assert result["ok"] is True
    assert [step["name"] for step in result["steps"]] == ["config", "dependency_policy", "redline_verification", "brain_contract_validation", "diagnosis_gap_coverage", "frontend_inline_sync", "frontend_syntax", "frontend_innerhtml_guard", "web_console_contract", "react_build_env", "text_encoding_scan", "official_context_validation", "module_size_audit", "secret_scan", "cache_metadata_audit", "diagnostic_report_sync"]
    assert not any("compileall" in call for call in calls)


def test_quality_gate_can_include_dependency_audit(monkeypatch, tmp_path):
    calls = []

    def fake_run(args):
        calls.append(args)
        return True, {"command": args, "exit_code": 0, "duration_seconds": 0.01, "stdout": "", "stderr": ""}

    monkeypatch.setattr(quality_gate, "_run_python_module", fake_run)

    result = quality_gate.run_quality_gate(
        config_path=tmp_path / "run_config.json",
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
        "web_console_contract",
        "react_build_env",
        "text_encoding_scan",
        "official_context_validation",
        "module_size_audit",
        "secret_scan",
        "cache_metadata_audit",
        "diagnostic_report_sync",
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
        config_path=tmp_path / "run_config.json",
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
        config_path=tmp_path / "run_config.json",
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


def test_quality_gate_can_require_react_build(monkeypatch, tmp_path):
    calls = []

    def fake_run(args):
        calls.append(args)
        return True, {"command": args, "exit_code": 0, "duration_seconds": 0.01, "stdout": "", "stderr": ""}

    monkeypatch.setattr(quality_gate, "_run_python_module", fake_run)

    result = quality_gate.run_quality_gate(
        config_path=tmp_path / "run_config.json",
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


def test_quality_gate_propagates_strict_react_build_failure(monkeypatch, tmp_path):
    def fake_run(args):
        ok = not any(str(arg).endswith("check_react_build_env.py") for arg in args)
        return ok, {"command": args, "exit_code": 0 if ok else 1, "duration_seconds": 0.01, "stdout": "", "stderr": ""}

    monkeypatch.setattr(quality_gate, "_run_python_module", fake_run)

    result = quality_gate.run_quality_gate(
        config_path=tmp_path / "run_config.json",
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
        config_path=tmp_path / "run_config.json",
        html_path=tmp_path / "index.html",
        final_release=True,
        skip_tests=True,
    )

    assert result["ok"] is True
    assert any("scripts/final_release_gate.py" in str(call) for call in calls)


def test_quality_gate_can_require_fresh_official_context(monkeypatch, tmp_path):
    calls = []

    def fake_run(args):
        calls.append(args)
        return True, {"command": args, "exit_code": 0, "duration_seconds": 0.01, "stdout": "", "stderr": ""}

    monkeypatch.setattr(quality_gate, "_run_python_module", fake_run)

    result = quality_gate.run_quality_gate(
        config_path=tmp_path / "run_config.json",
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


def test_text_encoding_scan_rejects_mojibake(tmp_path):
    clean = tmp_path / "README.md"
    bad = tmp_path / "bad.md"
    clean.write_text("云端同步正在进行。\n", encoding="utf-8")
    bad.write_text("".join(chr(codepoint) for codepoint in (0x6D5C, 0x6220, 0xE061)) + "\n", encoding="utf-8")

    result = check_text_encoding(tmp_path, ["README.md", "bad.md"])

    assert result["ok"] is False
    assert result["findings"][0]["path"] == "bad.md"
    assert result["findings"][0]["code"] == "mojibake"


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

    report = run_final_release_gate(config_path=config_path)

    assert report.passed is True
    assert report.redlines["code_strong_alignment"] is True
    assert report.redlines["dataset_id_fully_available"] is True
    assert report.redlines["full_factor_coverage"] is True
