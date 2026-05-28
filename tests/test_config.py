import json
import os
from pathlib import Path
import sys
import tempfile

from brain_alpha_ops import config as config_mod
from brain_alpha_ops import web_config as web_config_mod
from brain_alpha_ops.brain_api.canonical import CANONICAL_API_PATHS, CANONICAL_SETTINGS
import pytest

from brain_alpha_ops.config import (
    ConfigValidationError,
    RunConfig,
    load_run_config,
    runtime_project_root,
    write_run_config,
)


def test_load_run_config_merges_nested_values():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "run_config.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "environment": "production",
                    "auto_submit": True,
                    "ops": {
                        "settings": {"region": "EUR", "universe": "TOP1000"},
                        "budget": {"max_cycles": 3, "max_candidates_per_cycle": 12},
                        "scoring": {
                            "assistant_guidance_score_adjustment_enabled": False,
                            "assistant_guidance_score_min_confidence": 0.75,
                            "assistant_guidance_score_min_outcome_count": 2,
                            "assistant_guidance_score_bonus_cap": 1.5,
                            "assistant_guidance_score_penalty_cap": 2.5,
                        },
                    },
                },
                handle,
            )

        config = load_run_config(path)
        assert config.environment == "production"
        assert config.auto_submit is True
        assert config.ops.settings.region == "EUR"
        assert config.ops.settings.universe == "TOP1000"
        assert config.ops.budget.max_cycles == 3
        assert config.ops.budget.max_candidates_per_cycle == 12
        assert config.ops.scoring.assistant_guidance_score_adjustment_enabled is False
        assert config.ops.scoring.assistant_guidance_score_min_confidence == 0.75
        assert config.ops.scoring.assistant_guidance_score_min_outcome_count == 2
        assert config.ops.scoring.assistant_guidance_score_bonus_cap == 1.5
        assert config.ops.scoring.assistant_guidance_score_penalty_cap == 2.5
        assert config.ops.thresholds.min_sharpe == 1.25


def test_load_run_config_fills_empty_dataset_from_official_cache(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "official_datasets.json").write_text(
        json.dumps([{"id": "ds_a"}, {"id": "pv1"}, {"id": "ds_b"}]),
        encoding="utf-8",
    )
    path = tmp_path / "run_config.json"
    path.write_text(
        json.dumps({"ops": {"storage_dir": str(data_dir), "settings": {"dataset": ""}}}),
        encoding="utf-8",
    )

    config = load_run_config(path)

    assert config.ops.settings.dataset == "pv1"
    assert config.ops.budget.dataset_strategy == "rotate"
    assert config.ops.budget.require_cloud_sync is True
    assert config.ops.official_api.allow_stale_context_on_rate_limit is True


def test_credentials_resolve_from_environment():
    old_user = os.environ.get("BRAIN_USERNAME")
    old_password = os.environ.get("BRAIN_PASSWORD")
    try:
        os.environ["BRAIN_USERNAME"] = "researcher"
        os.environ["BRAIN_PASSWORD"] = "secret"
        config = RunConfig()
        resolved = config.credentials.resolve()
        assert resolved["username"] == "researcher"
        assert resolved["password"] == "secret"
    finally:
        _restore_env("BRAIN_USERNAME", old_user)
        _restore_env("BRAIN_PASSWORD", old_password)


def test_write_run_config_round_trips():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "run_config.json")
        original = RunConfig()
        original.ops.settings.region = "CHN"
        written = write_run_config(original, path)
        loaded = load_run_config(written)
        assert loaded.ops.settings.region == "CHN"


def test_frozen_runtime_root_is_executable_directory(monkeypatch):
    exe_name = "BrainAlphaOps.exe" if sys.platform == "win32" else "BrainAlphaOps"
    exe_path = Path(tempfile.gettempdir()) / "BrainAlphaOps" / exe_name
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_path))
    monkeypatch.delenv("BRAIN_ALPHA_OPS_HOME", raising=False)
    assert runtime_project_root() == exe_path.parent.resolve()


def test_load_run_config_resolves_runtime_data_under_app_root(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        app_root = Path(tmp)
        config_path = app_root / "config" / "run_config.json"
        config_path.parent.mkdir()
        config_path.write_text(
            json.dumps({"ops": {"storage_dir": "data", "official_api": {"cache_dir": "data/api_cache"}}}),
            encoding="utf-8",
        )
        monkeypatch.setenv("BRAIN_ALPHA_OPS_HOME", str(app_root))
        monkeypatch.setattr(config_mod, "DEFAULT_RUN_CONFIG_PATH", config_path)
        loaded = load_run_config()
        assert loaded.ops.storage_dir == str((app_root / "data").resolve())
        assert loaded.ops.official_api.cache_dir == str((app_root / "data" / "api_cache").resolve())


def test_load_run_config_rejects_invalid_environment():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "run_config.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"environment": "paper"}, handle)

        with pytest.raises(ConfigValidationError, match="environment"):
            load_run_config(path)


def test_load_run_config_rejects_invalid_nested_numeric_range():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "run_config.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"web": {"port": 70000}}, handle)

        with pytest.raises(ConfigValidationError, match="web.port"):
            load_run_config(path)


def test_web_allow_remote_must_be_boolean():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "run_config.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"web": {"allow_remote": "yes"}}, handle)

        with pytest.raises(ConfigValidationError, match="web.allow_remote"):
            load_run_config(path)


def test_web_secure_cookies_must_be_boolean():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "run_config.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"web": {"secure_cookies": "yes"}}, handle)

        with pytest.raises(ConfigValidationError, match="web.secure_cookies"):
            load_run_config(path)


def test_web_admin_token_env_must_be_non_empty_string():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "run_config.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"web": {"admin_token_env": ""}}, handle)

        with pytest.raises(ConfigValidationError, match="web.admin_token_env"):
            load_run_config(path)


def test_load_run_config_rejects_invalid_scoring_weights():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "run_config.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "ops": {
                        "scoring": {
                            "prior_layer_weight": 0,
                            "empirical_layer_weight": 0,
                            "checklist_layer_weight": 0,
                        }
                    }
                },
                handle,
            )

        with pytest.raises(ConfigValidationError, match="layer_weights"):
            load_run_config(path)


def test_load_run_config_rejects_invalid_decision_thresholds():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "run_config.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "ops": {
                        "scoring": {
                            "decision_thresholds": {
                                "submit": 60,
                                "optimize": 80,
                                "research": 50,
                            }
                        }
                    }
                },
                handle,
            )

        with pytest.raises(ConfigValidationError, match="decision_thresholds"):
            load_run_config(path)


def test_load_run_config_rejects_bad_generation_mode_ratio():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "run_config.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"ops": {"budget": {"generation_mode_ratio": "70/-20/10"}}}, handle)

        with pytest.raises(ConfigValidationError, match="generation_mode_ratio"):
            load_run_config(path)


def test_load_run_config_rejects_invalid_official_api_url():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "run_config.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"ops": {"official_api": {"base_url": "file:///tmp/api"}}}, handle)

        with pytest.raises(ConfigValidationError, match="base_url"):
            load_run_config(path)


def test_load_run_config_requires_https_official_api_url_in_production():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "run_config.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "environment": "production",
                    "ops": {"official_api": {"base_url": "http://api.worldquantbrain.com"}},
                },
                handle,
            )

        with pytest.raises(ConfigValidationError, match="must use https"):
            load_run_config(path)


def test_load_run_config_rejects_non_production_environment():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "run_config.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "environment": "mock",
                    "ops": {"official_api": {"base_url": "https://api.worldquantbrain.com"}},
                },
                handle,
            )

        with pytest.raises(ConfigValidationError, match="environment"):
            load_run_config(path)


def test_load_run_config_accepts_release_dataset_strategies():
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp) / "data"
        data_dir.mkdir()
        (data_dir / "official_datasets.json").write_text(
            json.dumps([{"id": "pv1", "name": "Price Volume", "field_count": 24}]),
            encoding="utf-8",
        )
        path = Path(tmp) / "run_config.json"
        path.write_text(
            json.dumps(
                {
                    "environment": "production",
                    "ops": {
                        "storage_dir": str(data_dir),
                        "settings": {"dataset": "pv1"},
                        "budget": {
                            "dataset_strategy": "fixed",
                            "require_cloud_sync": True,
                            "run_forever": False,
                        },
                        "official_api": {"allow_stale_context_on_rate_limit": False},
                    },
                }
            ),
            encoding="utf-8",
        )

        config = load_run_config(path)

        assert config.ops.settings.dataset == "pv1"
        assert config.ops.budget.dataset_strategy == "fixed"
        assert config.ops.budget.require_cloud_sync is True
        assert config.ops.budget.run_forever is False
        assert config.ops.official_api.allow_stale_context_on_rate_limit is False


def test_config_and_web_settings_enums_use_canonical_contract():
    assert config_mod._VALID_REGIONS == CANONICAL_SETTINGS["region"]
    assert config_mod._VALID_UNIVERSES == CANONICAL_SETTINGS["universe"]
    assert config_mod._VALID_DELAYS == CANONICAL_SETTINGS["delay"]
    assert config_mod._VALID_NEUTRALIZATIONS == CANONICAL_SETTINGS["neutralization"]
    assert config_mod._VALID_ALPHA_TYPES == CANONICAL_SETTINGS["type"]
    assert config_mod._VALID_UNIT_HANDLING == CANONICAL_SETTINGS["unitHandling"]

    assert web_config_mod._VALID_REGIONS == CANONICAL_SETTINGS["region"]
    assert web_config_mod._VALID_UNIVERSES == CANONICAL_SETTINGS["universe"]
    assert web_config_mod._VALID_DELAYS == CANONICAL_SETTINGS["delay"]
    assert web_config_mod._VALID_NEUTRALIZATIONS == CANONICAL_SETTINGS["neutralization"]
    assert web_config_mod._VALID_TYPES == CANONICAL_SETTINGS["type"]


def test_official_api_paths_use_canonical_contract():
    config = RunConfig().ops.official_api
    assert config.authentication_path == CANONICAL_API_PATHS["authentication"]
    assert config.simulations_path == CANONICAL_API_PATHS["simulations"]
    assert config.data_sets_path == CANONICAL_API_PATHS["data_sets"]
    assert config.data_fields_path == CANONICAL_API_PATHS["data_fields"]
    assert config.operators_path == CANONICAL_API_PATHS["operators"]


def _restore_env(name, value):
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value
