import json
import os

from scripts.check_react_build_env import check_react_build_env, main


def _write_package_json(app_dir):
    app_dir.mkdir(parents=True)
    (app_dir / "package.json").write_text('{"scripts":{"build":"vite build"}}\n', encoding="utf-8")


def test_react_build_env_reports_missing_tooling_without_failing_by_default(tmp_path, monkeypatch):
    app_dir = tmp_path / "react_app"
    _write_package_json(app_dir)
    dist = app_dir / "dist"
    dist.mkdir()
    (dist / "index.html").write_text(
        '<div id="root"></div>__BRAIN_ALPHA_OPS_CSRF_TOKEN____BRAIN_ALPHA_OPS_STREAM_TOKEN__<script>React</script>',
        encoding="utf-8",
    )
    monkeypatch.setattr("scripts.check_react_build_env.shutil.which", lambda _name: "")

    result = check_react_build_env(app_dir)

    assert result["ok"] is True
    assert result["ready"] is False
    assert result["artifact"]["exists"] is True
    assert result["artifact"]["has_root_mount"] is True
    assert result["artifact"]["has_csrf_placeholder"] is True
    assert result["artifact"]["has_stream_placeholder"] is True
    assert result["artifact"]["contains_react_runtime"] is True
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


def test_react_build_env_reports_missing_dist_artifact_without_affecting_tooling_status(tmp_path, monkeypatch):
    app_dir = tmp_path / "react_app"
    _write_package_json(app_dir)
    monkeypatch.setattr("scripts.check_react_build_env.shutil.which", lambda _name: "")

    result = check_react_build_env(app_dir)

    assert result["ok"] is True
    assert result["artifact"]["exists"] is False
    assert result["artifact"]["bytes"] == 0


def test_react_build_env_reports_when_source_is_newer_than_dist(tmp_path, monkeypatch):
    app_dir = tmp_path / "react_app"
    _write_package_json(app_dir)
    dist = app_dir / "dist"
    src = app_dir / "src"
    dist.mkdir()
    src.mkdir()
    index = dist / "index.html"
    source = src / "App.tsx"
    index.write_text("<div id=\"root\"></div><script>React</script>", encoding="utf-8")
    source.write_text("export default function App() { return null; }\n", encoding="utf-8")
    old_time = 1_700_000_000
    new_time = old_time + 60

    os.utime(index, (old_time, old_time))
    os.utime(source, (new_time, new_time))
    monkeypatch.setattr("scripts.check_react_build_env.shutil.which", lambda _name: "")

    result = check_react_build_env(app_dir)

    assert result["artifact"]["source_files"] == 1
    assert result["artifact"]["latest_source_path"] == "src/App.tsx"
    assert result["artifact"]["source_newer_than_artifact"] is True
    assert result["artifact"]["recommendation"].startswith("React source is newer than dist/index.html")


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
        dist = cwd / "dist"
        dist.mkdir()
        (dist / "index.html").write_text(
            '<div id="root"></div>'
            '<meta name="brain-alpha-csrf" content="__BRAIN_ALPHA_OPS_CSRF_TOKEN__">'
            '<meta name="brain-alpha-stream" content="__BRAIN_ALPHA_OPS_STREAM_TOKEN__">'
            '<script type="module" src="/assets/index.js"></script>',
            encoding="utf-8",
        )
        return 0, "built", "", 0.01

    result = check_react_build_env(app_dir, strict=True, run_build=True, runner=runner)

    assert result["ok"] is True
    assert result["ready"] is True
    assert result["build"]["ok"] is True
    assert result["artifact"]["exists"] is True
    assert result["artifact"]["has_csrf_placeholder"] is True
    assert result["artifact"]["source_newer_than_artifact"] is False
    assert calls[0][0] == ["npm", "run", "build"]


def test_react_build_env_fails_run_build_when_artifact_contract_is_incomplete(tmp_path, monkeypatch):
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

    def runner(command, cwd, timeout):
        dist = cwd / "dist"
        dist.mkdir()
        (dist / "index.html").write_text('<div id="root"></div><script type="module" src="/assets/index.js"></script>', encoding="utf-8")
        return 0, "built", "", 0.01

    result = check_react_build_env(app_dir, strict=True, run_build=True, runner=runner)

    assert result["ok"] is False
    assert result["ready"] is False
    assert {finding["code"] for finding in result["findings"]} >= {
        "missing_react_csrf_placeholder",
        "missing_react_stream_placeholder",
    }


def test_react_build_env_main_prints_json(tmp_path, monkeypatch, capsys):
    app_dir = tmp_path / "react_app"
    _write_package_json(app_dir)
    monkeypatch.setattr("scripts.check_react_build_env.shutil.which", lambda _name: "")

    code = main(["--app-dir", str(app_dir), "--json"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "react_build_env.v1"
    assert payload["ready"] is False
