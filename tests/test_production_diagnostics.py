import json

from brain_alpha_ops.cli import main
from brain_alpha_ops.config import RunConfig, write_run_config
from brain_alpha_ops.production_diagnostics import (
    build_diagnostic_snapshot,
    render_one_page_markdown,
)
from brain_alpha_ops.web_cloud_snapshot import save_official_context_json
from tests.production_api_stub import write_template_safe_official_context


def test_production_diagnostic_snapshot_has_gap_matrix(tmp_path):
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path / "data")
    config_path = tmp_path / "run_config.json"
    write_run_config(config, config_path)

    snapshot = build_diagnostic_snapshot(config_path)

    assert snapshot["schema_version"] == "production_diagnosis.v1"
    assert snapshot["contract_comparison"]["thresholds_zero_deviation"] is True
    assert snapshot["scoring_probe"]["zero_deviation"] is True
    assert snapshot["history_replay"]["capability"] == "ready"
    assert snapshot["official_refresh"]["schema_version"] == "official_refresh_status.v1"
    assert snapshot["official_context_validation"]["schema_version"] == "official_context_validation.v1"
    assert snapshot["parameter_audit"]["schema_version"] == "parameter_audit_snapshot.v1"
    assert snapshot["parameter_audit"]["thresholds_zero_deviation"] is True
    assert snapshot["contract_comparison"]["history_replay_ready"] is True
    assert snapshot["contract_comparison"]["parameter_audit_complete"] is True
    assert snapshot["frontend_inline"]["css_replaced"] == 1
    assert snapshot["frontend_inline"]["css_sources"] == ["css/app.css"]
    assert [row["dimension"] for row in snapshot["gap_matrix"]] == [
        "Functional closure",
        "Technical compliance",
        "Parameter accuracy",
        "Data lineage",
        "Experience",
        "Scoring",
    ]
    assert snapshot["priority_items"]
    assert any(item["area"] == "official refresh" for item in snapshot["priority_items"])


def test_production_diagnostic_markdown_renders_one_page_sections(tmp_path):
    config = RunConfig(environment="production")
    config_path = tmp_path / "run_config.json"
    write_run_config(config, config_path)
    snapshot = build_diagnostic_snapshot(config_path)

    markdown = render_one_page_markdown(snapshot)

    assert "# Alpha Production Diagnosis and Gap Matrix" in markdown
    assert "## Gap Matrix" in markdown
    assert "Official refresh:" in markdown
    assert "Parameter audit:" in markdown
    assert "Context validation:" in markdown
    assert "History replay:" in markdown
    assert "## Current Execution Checklist" in markdown
    assert "QuantGPT-Aligned Upgrade Plan" in markdown
    assert "Functional closure" in markdown


def test_cli_diagnose_can_emit_json_and_write_markdown(tmp_path, capsys):
    config = RunConfig(environment="production")
    config_path = tmp_path / "run_config.json"
    output_path = tmp_path / "diagnosis.md"
    write_run_config(config, config_path)

    code = main(["diagnose", "--config", str(config_path), "--json", "--output", str(output_path)])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "production_diagnosis.v1"
    assert output_path.is_file()
    assert "Gap Matrix" in output_path.read_text(encoding="utf-8")


def test_production_diagnostic_counts_official_metadata_records(tmp_path):
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path / "data")
    config_path = tmp_path / "run_config.json"
    write_run_config(config, config_path)
    save_official_context_json("official_fields.json", [{"name": "close"}, {"name": "volume"}], load_config=lambda: config)
    save_official_context_json("official_operators.json", [{"name": "rank"}], load_config=lambda: config)
    save_official_context_json("official_datasets.json", [{"id": "pv1", "name": "Price Volume", "field_count": 2}], load_config=lambda: config)

    snapshot = build_diagnostic_snapshot(config_path)

    assert snapshot["official_context"] == {"fields": 2, "operators": 1, "datasets": 1}
    assert snapshot["official_context_validation"]["lineage"]["field_count_sum_matches"] is True
    assert "fields=2, operators=1, datasets=1" in render_one_page_markdown(snapshot)


def test_production_diagnostic_report_clears_refresh_todos_after_success(tmp_path):
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path / "data")
    config_path = tmp_path / "run_config.json"
    write_run_config(config, config_path)
    write_template_safe_official_context(config)
    status_path = tmp_path / "data" / "official_context_refresh_status.json"
    status_path.write_text(
        json.dumps(
            {
                "schema_version": "official_context_refresh.v1",
                "ok": True,
                "status": "refreshed",
                "counts": {"fields": 2, "operators": 1, "datasets": 1},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    snapshot = build_diagnostic_snapshot(config_path)
    markdown = render_one_page_markdown(snapshot)

    assert snapshot["official_refresh"]["last_attempt_ok"] is True
    assert not any(item["area"] == "official refresh" for item in snapshot["priority_items"])
    assert "No parameter-accuracy gap in the current evidence record." in markdown
    assert "### Unfinished\n- None in the current local code checklist." in markdown
