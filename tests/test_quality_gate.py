from pathlib import Path

from scripts import quality_gate
from scripts.check_dependency_policy import check_dependency_policy
from scripts.check_optional_tooling import check_optional_tooling


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
        "frontend_inline_sync",
        "frontend_syntax",
        "secret_scan",
        "cache_metadata_audit",
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
        "frontend_inline_sync",
        "frontend_syntax",
        "secret_scan",
        "cache_metadata_audit",
        "pytest",
    ]
    assert "--include-all" in result["steps"][6]["command"]
    assert result["steps"][8]["command"][-1] == "tests/test_web.py"


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
    assert [step["name"] for step in result["steps"]] == ["config", "dependency_policy", "redline_verification", "frontend_inline_sync", "frontend_syntax", "secret_scan", "cache_metadata_audit"]
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
        "frontend_inline_sync",
        "frontend_syntax",
        "secret_scan",
        "cache_metadata_audit",
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
