import json

from brain_alpha_ops.e2e_report import build_e2e_artifact_summary, render_markdown_summary
from scripts.summarize_e2e_artifacts import main


def test_e2e_artifact_summary_indexes_and_redacts_artifacts(tmp_path):
    evidence_dir = tmp_path / "data" / "e2e_screenshots"
    evidence_dir.mkdir(parents=True)
    (evidence_dir / "01-page.png").write_bytes(b"\x89PNG\r\n")
    (evidence_dir / "01-page.dom.txt").write_text("<input type=password>\n", encoding="utf-8")
    (evidence_dir / "console-2026.log").write_text(
        "[ERROR] auth failed for researcher@example.com token=SECRET456\n"
        "[WARNING] Authorization: Bearer secret-token-value-123456789\n",
        encoding="utf-8",
    )
    (evidence_dir / "production-summary.json").write_text(
        json.dumps(
            {
                "service_url": "http://127.0.0.1:8765/",
                "connection": {"ok": True, "environment": "production", "email": "researcher@example.com"},
                "authorization": "Bearer secret-token-value-123456789",
                "production_run": {"job_id": "job_0002", "status": "stopped", "submitted_this_run": 0},
            }
        ),
        encoding="utf-8",
    )
    data_dir = tmp_path / "data"
    (data_dir / "jobs_sync.json").write_text(
        json.dumps(
            {
                "version": 1,
                "jobs": {
                    "job_0001": {
                        "status": "completed",
                        "updated_at": 10,
                        "error": "",
                        "progress": {"message": "synced as researcher@example.com"},
                        "result": {"summary": {"api_key": "secret-api-key-12345", "count": 3}},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    payload = build_e2e_artifact_summary(root=tmp_path)
    blob = json.dumps(payload, ensure_ascii=False)

    assert payload["ok"] is True
    assert payload["schema_version"] == "e2e_artifact_summary.v1"
    assert payload["file_counts"]["screenshot"] == 1
    assert payload["file_counts"]["console_log"] == 1
    assert payload["console_logs"][0]["notable_count"] == 2
    assert "preview_lines" not in payload["console_logs"][0]
    assert payload["job_ledgers"][0]["latest_job"]["status"] == "completed"
    assert "researcher@example.com" not in blob
    assert "SECRET456" not in blob
    assert "secret-token-value" not in blob
    assert "secret-api-key" not in blob
    assert "***@***" in blob
    assert "<redacted>" in blob


def test_render_markdown_summary_contains_core_sections(tmp_path):
    evidence_dir = tmp_path / "data" / "e2e_screenshots"
    evidence_dir.mkdir(parents=True)
    (evidence_dir / "01-page.png").write_bytes(b"\x89PNG\r\n")

    markdown = render_markdown_summary(build_e2e_artifact_summary(root=tmp_path))

    assert "# E2E Artifact Summary" in markdown
    assert "## Evidence Files" in markdown
    assert "## Sensitive Handling" in markdown
    assert "screenshot" in markdown


def test_summarize_e2e_artifacts_cli_writes_json_and_markdown(tmp_path, capsys):
    evidence_dir = tmp_path / "data" / "e2e_screenshots"
    evidence_dir.mkdir(parents=True)
    (evidence_dir / "01-page.png").write_bytes(b"\x89PNG\r\n")
    output_json = tmp_path / "docs" / "summary.json"
    output_md = tmp_path / "docs" / "summary.md"

    code = main(
        [
            "--root",
            str(tmp_path),
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
            "--json",
        ]
    )

    assert code == 0
    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert stdout_payload["schema_version"] == "e2e_artifact_summary.v1"
    assert file_payload["schema_version"] == "e2e_artifact_summary.v1"
    assert "E2E Artifact Summary" in output_md.read_text(encoding="utf-8")
