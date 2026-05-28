import json

from scripts.check_react_build_env import check_react_build_env, main


def _write_package_json(app_dir):
    app_dir.mkdir(parents=True)
    (app_dir / "package.json").write_text('{"scripts":{"build":"vite build"}}\n', encoding="utf-8")


def test_react_build_env_reports_missing_tooling_without_failing_by_default(tmp_path, monkeypatch):
    app_dir = tmp_path / "react_app"
    _write_package_json(app_dir)
    monkeypatch.setattr("scripts.check_react_build_env.shutil.which", lambda _name: "")

    result = check_react_build_env(app_dir)

    assert result["ok"] is True
    assert result["ready"] is False
    assert {finding["code"] for finding in result["findings"]} >= {
        "missing_node",
        "missing_npm",
        "missing_lockfile",
        "missing_node_modules",
    }


def test_react_build_env_strict_mode_fails_when_prerequisites_are_missing(tmp_path, monkeypatch):
    app_dir = tmp_path / "react_app"
    _write_package_json(app_dir)
    monkeypatch.setattr("scripts.check_react_build_env.shutil.which", lambda _name: "")

    result = check_react_build_env(app_dir, strict=True)

    assert result["ok"] is False
    assert result["ready"] is False


def test_react_build_env_runs_build_when_prerequisites_are_ready(tmp_path, monkeypatch):
    app_dir = tmp_path / "react_app"
    _write_package_json(app_dir)
    (app_dir / "package-lock.json").write_text("{}\n", encoding="utf-8")
    for package in ["react", "react-dom", "typescript", "vite"]:
        (app_dir / "node_modules" / package).mkdir(parents=True)
    (app_dir / "node_modules" / "@vitejs" / "plugin-react").mkdir(parents=True)
    monkeypatch.setattr(
        "scripts.check_react_build_env.shutil.which",
        lambda name: f"/usr/local/bin/{name}" if name in {"node", "npm"} else "",
    )
    calls = []

    def runner(command, cwd, timeout):
        calls.append((command, cwd, timeout))
        return 0, "built", "", 0.01

    result = check_react_build_env(app_dir, strict=True, run_build=True, runner=runner)

    assert result["ok"] is True
    assert result["ready"] is True
    assert result["build"]["ok"] is True
    assert calls[0][0] == ["npm", "run", "build"]


def test_react_build_env_main_prints_json(tmp_path, monkeypatch, capsys):
    app_dir = tmp_path / "react_app"
    _write_package_json(app_dir)
    monkeypatch.setattr("scripts.check_react_build_env.shutil.which", lambda _name: "")

    code = main(["--app-dir", str(app_dir), "--json"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "react_build_env.v1"
    assert payload["ready"] is False
