import json

import pytest

import run_pipeline
from brain_alpha_ops.config import RunConfig, write_run_config


def test_run_pipeline_help_does_not_load_config(monkeypatch, capsys):
    def fail_load_config(_path):
        raise AssertionError("help must not load production config")

    monkeypatch.setattr(run_pipeline, "load_run_config", fail_load_config)

    with pytest.raises(SystemExit) as exc:
        run_pipeline.main(["--help"])

    assert exc.value.code == 0
    output = capsys.readouterr().out
    assert "--validate-only" in output
    assert "--config" in output


def test_run_pipeline_validate_only_skips_pipeline(tmp_path, monkeypatch, capsys):
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path / "data")
    config_path = tmp_path / "run_config.json"
    write_run_config(config, config_path)

    def fail_run_pipeline(_run_config):
        raise AssertionError("validate-only must not start the pipeline")

    monkeypatch.setattr(run_pipeline, "run_pipeline_from_config", fail_run_pipeline)

    code = run_pipeline.main(["--config", str(config_path), "--validate-only", "--json"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["mode"] == "validate-only"
    assert payload["config"] == str(config_path)
    assert payload["environment"] == "production"


def test_run_pipeline_positional_config_path_still_runs(tmp_path, monkeypatch, capsys):
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path / "data")
    config_path = tmp_path / "run_config.json"
    write_run_config(config, config_path)
    seen = {}

    class Result:
        run_id = "run_test"
        summary = {"total_candidates": 1}

        def to_dict(self):
            return {"ok": True, "run_id": self.run_id, "summary": self.summary}

    def fake_run_pipeline(run_config):
        seen["storage_dir"] = run_config.ops.storage_dir
        return Result()

    monkeypatch.setattr(run_pipeline, "run_pipeline_from_config", fake_run_pipeline)

    code = run_pipeline.main([str(config_path), "--json"])

    assert code == 0
    assert seen["storage_dir"] == str(tmp_path / "data")
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["run_id"] == "run_test"


def test_run_pipeline_rejects_duplicate_config_arguments(tmp_path):
    config_path = tmp_path / "run_config.json"

    with pytest.raises(SystemExit) as exc:
        run_pipeline.main([str(config_path), "--config", str(config_path)])

    assert exc.value.code == 2
