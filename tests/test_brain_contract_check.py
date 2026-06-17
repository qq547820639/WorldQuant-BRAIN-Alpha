from scripts.check_brain_contract import check_brain_contract

from brain_alpha_ops.config import RunConfig, write_run_config
from tests.production_api_stub import write_template_safe_official_context


def test_brain_contract_check_passes_blocking_mode_with_structural_context(tmp_path):
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path / "data")
    config.ops.settings.dataset = "pv1"
    config_path = tmp_path / "run_config.json"
    write_run_config(config, config_path)
    _write_context(config)

    result = check_brain_contract(config_path=config_path)

    assert result["ok"] is True  # contract check passes with current context
    assert result["schema_version"] == "brain_contract_check.v1"
    # stub context now passes clean - no blocking redlines found


def test_brain_contract_check_strict_mode_blocks_unverified_refresh(tmp_path):
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path / "data")
    config.ops.settings.dataset = "pv1"
    config_path = tmp_path / "run_config.json"
    write_run_config(config, config_path)
    _write_context(config)

    result = check_brain_contract(config_path=config_path, strict_freshness=True)

    assert result["ok"] is False
    assert result["blocking_count"] >= 1
    assert any(item["code"] == "strict_refresh_not_verified" for item in result["findings"])


def _write_context(config: RunConfig) -> None:
    write_template_safe_official_context(config)
