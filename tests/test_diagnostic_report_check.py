from brain_alpha_ops.config import RunConfig, write_run_config
from brain_alpha_ops.production_diagnostics import build_diagnostic_snapshot, render_one_page_markdown
from scripts.check_diagnostic_report import check_diagnostic_report


def test_diagnostic_report_check_accepts_current_snapshot(tmp_path):
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path / "data")
    config_path = tmp_path / "run_config.json"
    report_path = tmp_path / "diagnosis.md"
    write_run_config(config, config_path)
    snapshot = build_diagnostic_snapshot(config_path)
    report_path.write_text(render_one_page_markdown(snapshot), encoding="utf-8")

    result = check_diagnostic_report(config_path=config_path, report_path=report_path)

    assert result["ok"] is True
    assert result["findings"] == []


def test_diagnostic_report_check_rejects_stale_counts(tmp_path):
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path / "data")
    config_path = tmp_path / "run_config.json"
    report_path = tmp_path / "diagnosis.md"
    write_run_config(config, config_path)
    report_path.write_text("# Alpha Production Diagnosis and Gap Matrix\n\nOfficial context: fields=0, operators=0, datasets=0\n", encoding="utf-8")

    result = check_diagnostic_report(config_path=config_path, report_path=report_path)

    assert result["ok"] is False
    assert any(item["code"] == "official_context_counts" for item in result["findings"])
