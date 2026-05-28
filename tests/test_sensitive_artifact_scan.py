import json
import os

from scripts.scan_sensitive_artifacts import scan_artifacts, scan_git_history, main


def test_scan_artifacts_reports_redacted_findings_in_default_locations(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "run.jsonl").write_text(
        'event=auth Authorization: Bearer secret-token-value-123456789\n',
        encoding="utf-8",
    )
    (tmp_path / "notes.py").write_text("password = 'not-scanned-by-default'\n", encoding="utf-8")

    result = scan_artifacts(tmp_path)

    assert result["ok"] is False
    assert result["schema_version"] == "sensitive_artifact_scan.v1"
    assert result["checked"] == 1
    assert result["findings"][0]["type"] == "auth_header"
    assert result["findings"][0]["path"] == f"data{os.sep}run.jsonl"
    assert "secret-token-value" not in result["findings"][0]["snippet"]
    assert "Authorization: <redacted>" in result["findings"][0]["snippet"]


def test_scan_sensitive_artifacts_json_cli_can_fail_on_findings(tmp_path, capsys):
    dummy_value = "super-" + "private-token-12345"
    (tmp_path / "server.err.log").write_text(f"token={dummy_value}\n", encoding="utf-8")

    code = main(["--root", str(tmp_path), "--json", "--fail-on-findings"])

    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["findings"][0]["type"] == "secret_key"
    assert "super-private-token" not in payload["findings"][0]["snippet"]
    assert "token=<redacted>" in payload["findings"][0]["snippet"]


def test_scan_sensitive_artifacts_json_cli_passes_when_clean(tmp_path, capsys):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "run.json").write_text('{"status":"ok"}\n', encoding="utf-8")

    code = main(["--root", str(tmp_path), "--json", "--fail-on-findings"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["checked"] == 1
    assert payload["findings"] == []


def test_scan_artifacts_does_not_flag_plain_session_descriptions(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "fields.json").write_text(
        '{"description":"Difference in percent return over the session: close - last"}\n',
        encoding="utf-8",
    )
    (data_dir / "auth.json").write_text('{"session_id":"secret-session-id-12345"}\n', encoding="utf-8")

    result = scan_artifacts(tmp_path)

    assert result["ok"] is False
    assert len(result["findings"]) == 1
    assert result["findings"][0]["path"] == f"data{os.sep}auth.json"
    assert result["findings"][0]["type"] == "secret_key"


def test_scan_artifacts_include_all_skips_tooling_and_code_references(tmp_path):
    hidden_dep = tmp_path / ".codex_pydeps" / "pkg"
    hidden_dep.mkdir(parents=True)
    hidden_dep.joinpath("parser.py").write_text("token = current_token\n", encoding="utf-8")
    (tmp_path / "app.py").write_text(
        "password = os.getenv('BRAIN_PASSWORD', '')\n"
        "self.token = token\n",
        encoding="utf-8",
    )
    dummy_value = "sk-live-" + "private-1234567890"
    (tmp_path / "leak.py").write_text(f"api_key = '{dummy_value}'\n", encoding="utf-8")

    result = scan_artifacts(tmp_path, include_all=True)

    assert result["ok"] is False
    assert len(result["findings"]) == 1
    assert result["findings"][0]["path"] == "leak.py"
    assert result["findings"][0]["type"] == "secret_key"


def test_scan_artifacts_include_all_scans_tests_and_skips_placeholder_cookies(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    dummy_value = "realish-" + "private-token-12345"
    tests_dir.joinpath("test_secret_scan.py").write_text(f"token='{dummy_value}'\n", encoding="utf-8")
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    docs_dir.joinpath("api.md").write_text(
        "`Set-Cookie: app_session=<id>; HttpOnly; SameSite=Strict`\n",
        encoding="utf-8",
    )
    docs_dir.joinpath("csrf.md").write_text(
        'const CSRF_TOKEN = "__BRAIN_ALPHA_OPS_CSRF_TOKEN__";\n',
        encoding="utf-8",
    )

    result = scan_artifacts(tmp_path, include_all=True)

    assert result["ok"] is False
    assert len(result["findings"]) == 1
    assert result["findings"][0]["path"] == f"tests{os.sep}test_secret_scan.py"


def test_scan_artifacts_include_all_scans_shell_scripts(tmp_path):
    dummy_value = "super-" + "private-password-12345"
    (tmp_path / "launch.ps1").write_text(f'$env:BRAIN_PASSWORD = "{dummy_value}"\n', encoding="utf-8")

    result = scan_artifacts(tmp_path, include_all=True)

    assert result["ok"] is False
    assert result["findings"][0]["path"] == "launch.ps1"
    assert result["findings"][0]["type"] == "secret_key"
    assert "super-private-password" not in result["findings"][0]["snippet"]


def test_scan_artifacts_include_all_skips_codebuddy_notes(tmp_path):
    notes_dir = tmp_path / ".codebuddy" / "memory"
    notes_dir.mkdir(parents=True)
    account = "5478" + "20639" + "@qq.com"
    password = "Ph" + "360" + "098."
    notes_dir.joinpath("2026-05-28.md").write_text(
        f"hardcoded credentials ({account} / {password}) in 15+ YML files\n",
        encoding="utf-8",
    )

    result = scan_artifacts(tmp_path, include_all=True)

    assert result["ok"] is True
    assert result["findings"] == []


def test_scan_artifacts_samples_large_text_files(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    filler = "x" * 4096
    (data_dir / "events.jsonl").write_text(
        filler + "\n" + "profile email=researcher@example.com Authorization: Bearer secret-token-value-123456789\n",
        encoding="utf-8",
    )

    result = scan_artifacts(tmp_path, max_bytes=1024)

    assert result["ok"] is False
    assert result["findings"][0]["path"] == f"data{os.sep}events.jsonl"
    assert "researcher@example.com" not in result["findings"][0]["snippet"]
    assert "secret-token-value" not in result["findings"][0]["snippet"]


def test_scan_git_history_detects_known_secret_hashes(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    import subprocess

    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test User"], check=True)
    leak = "5478" + "20639"
    (repo / "leak.txt").write_text(f"{leak}\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "leak.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "leak"], check=True)

    result = scan_git_history(repo)

    assert result["ok"] is False
    assert result["schema_version"] == "git_history_sensitive_scan.v1"
    assert result["findings"][0]["type"] == "known_secret_hash_git_history"
    assert result["findings"][0]["secret_label"] == "known_brain_account_identifier_sha256"
