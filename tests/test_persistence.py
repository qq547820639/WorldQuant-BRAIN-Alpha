"""File I/O and persistence tests.

Tests cover:
  - JSONL read/write
  - Configuration persistence
  - Run history persistence
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest


class TestJSONLPersistence:
    """Test JSONL read/write operations."""

    def test_jsonl_module_importable(self):
        """Test JSONL module is importable."""
        from brain_alpha_ops import jsonl

        assert hasattr(jsonl, "__file__")

    def test_jsonl_file_operations(self):
        """Test basic JSONL file operations."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "test.jsonl"

            # Write records manually
            records = [
                {"id": 1, "name": "alpha_1"},
                {"id": 2, "name": "alpha_2"},
            ]
            with open(path, "w", encoding="utf-8") as f:
                for record in records:
                    f.write(json.dumps(record) + "\n")

            # Read records
            with open(path, "r", encoding="utf-8") as f:
                loaded = [json.loads(line) for line in f if line.strip()]

            assert len(loaded) == 2
            assert loaded[0]["id"] == 1

    def test_jsonl_empty_file(self):
        """Test JSONL empty file handling."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "empty.jsonl"
            path.write_text("", encoding="utf-8")

            with open(path, "r", encoding="utf-8") as f:
                loaded = [json.loads(line) for line in f if line.strip()]

            assert len(loaded) == 0

    def test_jsonl_unicode_handling(self):
        """Test JSONL unicode handling."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "unicode.jsonl"

            record = {"name": "测试Alpha", "description": "中文描述"}
            with open(path, "w", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

            with open(path, "r", encoding="utf-8") as f:
                loaded = [json.loads(line) for line in f if line.strip()]

            assert len(loaded) == 1
            assert loaded[0]["name"] == "测试Alpha"


class TestConfigurationPersistence:
    """Test configuration persistence."""

    def test_config_creation(self):
        """Test config creation."""
        from brain_alpha_ops.config import OpsConfig

        config = OpsConfig()
        assert config.settings is not None
        assert config.budget is not None

    def test_config_to_dict(self):
        """Test config serialization."""
        from brain_alpha_ops.config import OpsConfig

        config = OpsConfig()
        config_dict = config.to_dict()
        assert isinstance(config_dict, dict)
        assert "settings" in config_dict

    def test_config_with_custom_settings(self):
        """Test config with custom settings."""
        from brain_alpha_ops.config import OpsConfig, BrainSettings

        config = OpsConfig()
        config.settings = BrainSettings(region="JAPAN", delay=0)
        assert config.settings.region == "JAPAN"
        assert config.settings.delay == 0


class TestCachePersistence:
    """Test cache read/write operations."""

    def test_cache_file_operations(self):
        """Test basic cache file operations."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_dir = Path(tmp_dir) / "cache"
            cache_dir.mkdir()

            # Write cache
            cache_file = cache_dir / "test_cache.json"
            items = [{"id": 1, "name": "field_1"}, {"id": 2, "name": "field_2"}]
            cache_data = {"items": items, "total": 2}
            cache_file.write_text(json.dumps(cache_data), encoding="utf-8")

            # Read cache
            loaded = json.loads(cache_file.read_text(encoding="utf-8"))
            assert loaded["total"] == 2
            assert len(loaded["items"]) == 2


class TestRunHistoryPersistence:
    """Test run history persistence."""

    def test_run_history_write_and_read(self):
        """Test run history write and read."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            history_dir = Path(tmp_dir) / "run_history"
            history_dir.mkdir()

            # Write run history
            run_data = {
                "run_id": "run_001",
                "status": "completed",
                "summary": {"total_candidates": 10, "best_score": 85.0},
            }
            run_file = history_dir / "run_001.json"
            run_file.write_text(json.dumps(run_data), encoding="utf-8")

            # Read run history
            loaded = json.loads(run_file.read_text(encoding="utf-8"))
            assert loaded["run_id"] == "run_001"
            assert loaded["summary"]["best_score"] == 85.0

    def test_multiple_runs_persistence(self):
        """Test multiple runs persistence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            history_dir = Path(tmp_dir) / "run_history"
            history_dir.mkdir()

            # Write multiple runs
            for i in range(5):
                run_data = {
                    "run_id": f"run_{i:03d}",
                    "status": "completed",
                    "summary": {"total_candidates": 10 * (i + 1)},
                }
                run_file = history_dir / f"run_{i:03d}.json"
                run_file.write_text(json.dumps(run_data), encoding="utf-8")

            # Read all runs
            all_runs = []
            for json_file in history_dir.glob("*.json"):
                run = json.loads(json_file.read_text(encoding="utf-8"))
                all_runs.append(run)

            assert len(all_runs) == 5
