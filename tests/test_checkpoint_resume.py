"""Tests for checkpoint/resume system and user-facing error messages."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_project_root = Path(__file__).resolve().parents[1]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from brain_alpha_ops.research.checkpoint import (
    Checkpoint,
    CheckpointManager,
    PipelineRecovery,
)
from brain_alpha_ops.ux.user_messages import (
    get_message,
    classify_expression_error,
    web_actionable_error,
    MESSAGE_CATALOG,
    UserMessage,
)
from brain_alpha_ops.models import Candidate


class TestCheckpointManager:
    def test_save_and_latest(self, tmp_path):
        """Save a checkpoint and retrieve it."""
        mgr = CheckpointManager(tmp_path / "checkpoints")
        cp_id = mgr.save(cycle_index=0, stage="generation")
        assert cp_id != ""
        latest = mgr.latest()
        assert latest is not None
        assert latest.cycle_index == 0
        assert latest.stage == "generation"

    def test_can_resume(self, tmp_path):
        """can_resume should be True after save, False on empty."""
        mgr = CheckpointManager(tmp_path / "checkpoints")
        assert not mgr.can_resume()
        mgr.save(cycle_index=1, stage="backtest")
        assert mgr.can_resume()

    def test_multiple_cycles(self, tmp_path):
        """Multiple checkpoints should track latest cycle."""
        mgr = CheckpointManager(tmp_path / "checkpoints")
        mgr.save(cycle_index=0, stage="generation")
        mgr.save(cycle_index=1, stage="backtest")
        mgr.save(cycle_index=2, stage="scoring")
        latest = mgr.latest()
        assert latest is not None
        assert latest.cycle_index == 2

    def test_save_with_candidates(self, tmp_path):
        """Checkpoint should persist candidate data."""
        mgr = CheckpointManager(tmp_path / "checkpoints")
        candidates = [
            Candidate(
                alpha_id="test_1",
                expression="rank(close)",
                family="Momentum",
                hypothesis="Test hypothesis",
            ),
            Candidate(
                alpha_id="test_2",
                expression="ts_mean(close, 20)",
                family="Trend",
                hypothesis="Moving average",
            ),
        ]
        cp_id = mgr.save(
            cycle_index=0,
            stage="generation",
            candidates=candidates,
            stats={"generated_count": 2, "passed_validation": 2},
        )
        assert cp_id != ""
        latest = mgr.latest()
        assert latest is not None
        assert len(latest.candidates) == 2
        assert latest.stats.get("generated_count") == 2

    def test_clear(self, tmp_path):
        """Clear should remove all checkpoints."""
        mgr = CheckpointManager(tmp_path / "checkpoints")
        mgr.save(cycle_index=0, stage="generation")
        mgr.save(cycle_index=1, stage="backtest")
        assert mgr.can_resume()
        removed = mgr.clear()
        assert removed >= 1
        assert not mgr.can_resume()

    def test_list_all(self, tmp_path):
        """list_all should return checkpoint metadata."""
        mgr = CheckpointManager(tmp_path / "checkpoints")
        mgr.save(cycle_index=0, stage="generation")
        mgr.save(cycle_index=1, stage="scoring")
        entries = mgr.list_all()
        assert len(entries) >= 2
        for entry in entries:
            assert "checkpoint_id" in entry
            assert "cycle_index" in entry
            assert "stage" in entry

    def test_prune_old_checkpoints(self, tmp_path):
        """When exceeding MAX_CHECKPOINTS, oldest should be removed."""
        mgr = CheckpointManager(tmp_path / "checkpoints")
        mgr.MAX_CHECKPOINTS = 5
        for i in range(10):
            mgr.save(cycle_index=i, stage=f"stage_{i}")
        latest = mgr.latest()
        assert latest is not None
        # Oldest cycles (0-4) should have been pruned
        assert latest.cycle_index >= 5

    def test_graceful_corrupt_index(self, tmp_path):
        """Corrupt index files should not crash the manager."""
        index_path = tmp_path / "checkpoints" / "checkpoint_index.json"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text("not valid json {{{", encoding="utf-8")
        mgr = CheckpointManager(tmp_path / "checkpoints")
        assert not mgr.can_resume()
        # Should still be able to save new checkpoints
        cp_id = mgr.save(cycle_index=0, stage="recovery")
        assert cp_id != ""

    def test_missing_checkpoint_file(self, tmp_path):
        """Missing checkpoint file should not crash latest()."""
        mgr = CheckpointManager(tmp_path / "checkpoints")
        cp_id = mgr.save(cycle_index=0, stage="test")
        assert cp_id != ""
        # Manually delete the file
        for f in (tmp_path / "checkpoints").iterdir():
            if f.suffix == ".json" and "checkpoint" in f.name:
                f.unlink()
        # latest() should return None gracefully
        latest = mgr.latest()
        assert latest is None


class TestPipelineRecovery:
    def test_fresh_start(self, tmp_path):
        """Resume context on fresh install should indicate can_resume=False."""
        recovery = PipelineRecovery(tmp_path / "data")
        ctx = recovery.resume_context()
        assert ctx["can_resume"] is False
        assert ctx["cycle_index"] == -1
        assert ctx["stage"] == "fresh_start"

    def test_recovery_summary_fresh(self, tmp_path):
        """Recovery summary on fresh install should indicate starting fresh."""
        recovery = PipelineRecovery(tmp_path / "data")
        summary = recovery.recovery_summary()
        assert "fresh" in summary.lower() or "No checkpoint" in summary

    def test_resume_after_snapshot(self, tmp_path):
        """After snapshot, resume context should return correct cycle."""
        recovery = PipelineRecovery(tmp_path / "data")
        candidates = [
            Candidate("alpha_1", "rank(close)", "Momentum", "Test"),
        ]
        cp_id = recovery.snapshot(
            cycle_index=3,
            stage="scoring",
            candidates=candidates,
            stats={"total": 1},
        )
        assert cp_id != ""
        ctx = recovery.resume_context()
        assert ctx["can_resume"] is True
        assert ctx["cycle_index"] == 3
        assert len(ctx["recovered_candidates"]) == 1

    def test_recovery_summary_after_snapshot(self, tmp_path):
        """Recovery summary after snapshot should include cycle info."""
        recovery = PipelineRecovery(tmp_path / "data")
        recovery.snapshot(cycle_index=5, stage="backtest", stats={"total": 10})
        summary = recovery.recovery_summary()
        assert "cycle 5" in summary.lower()
        assert "resuming" in summary.lower()


class TestUserMessages:
    def test_all_codes_have_messages(self):
        """Every error code in MESSAGE_CATALOG should have valid fields."""
        for code, msg in MESSAGE_CATALOG.items():
            assert msg.title, f"Missing title for {code}"
            assert msg.detail, f"Missing detail for {code}"
            assert msg.suggestion, f"Missing suggestion for {code}"
            assert msg.severity in {"error", "warning", "info"}

    def test_get_message_known_code(self):
        """Known error codes should return pre-defined messages."""
        msg = get_message("AUTH_FAILED")
        assert msg.error_code == "AUTH_FAILED"
        assert msg.severity == "error"
        assert "认证" in msg.title

    def test_get_message_unknown_code(self):
        """Unknown error codes should return generic fallback."""
        msg = get_message("SOME_UNKNOWN_ERROR_XYZ")
        assert msg.error_code == "SOME_UNKNOWN_ERROR_XYZ"
        assert msg.severity == "error"
        assert "操作异常" == msg.title

    def test_get_message_with_fallback_detail(self):
        """Fallback detail should be used for unknown codes."""
        msg = get_message("UNKNOWN", fallback_detail="Custom error detail")
        assert "Custom error detail" in msg.detail

    def test_web_actionable_error(self):
        """web_actionable_error should produce JSON-compatible payload."""
        payload = web_actionable_error("AUTH_FAILED", "Test detail")
        assert payload["ok"] is False
        assert payload["error_code"] == "AUTH_FAILED"
        assert "error" in payload
        assert "title" in payload["error"]
        assert "suggestion" in payload["error"]

    def test_web_actionable_error_with_context(self):
        """Extra context should be included in payload."""
        payload = web_actionable_error(
            "VALIDATION_FAILED",
            "Expression not valid",
            context={"expression": "rank(close)", "field": "close"},
        )
        assert "context" in payload
        assert payload["context"]["expression"] == "rank(close)"

    def test_classify_expression_error_empty(self):
        """Empty expression should return EXPRESSION_EMPTY."""
        result = classify_expression_error(ValueError("empty"), expression="")
        assert result["error_code"] == "EXPRESSION_EMPTY"

    def test_classify_expression_error_unbalanced(self):
        """Unbalanced parens should return EXPRESSION_UNBALANCED_PARENS."""
        result = classify_expression_error(
            ValueError("test"), expression="rank(close"
        )
        assert result["error_code"] == "EXPRESSION_UNBALANCED_PARENS"

    def test_classify_expression_error_unknown_operator(self):
        """Unknown operator message should route to EXPRESSION_UNKNOWN_OPERATOR."""
        result = classify_expression_error(
            ValueError("Unknown operator: some_op"), expression="some_op(close)"
        )
        assert result["error_code"] == "EXPRESSION_UNKNOWN_OPERATOR"

    def test_classify_expression_error_null_bytes(self):
        """Null bytes should route to EXPRESSION_NULL_BYTES."""
        result = classify_expression_error(
            ValueError("null"), expression="rank(c\x00lose)"
        )
        assert result["error_code"] == "EXPRESSION_NULL_BYTES"

    def test_user_message_dataclass(self):
        """UserMessage should be constructible and have all fields."""
        msg = UserMessage(
            title="测试",
            detail="Test detail",
            suggestion="Test suggestion",
            severity="warning",
            error_code="TEST",
        )
        assert msg.title == "测试"
        assert msg.severity == "warning"


class TestCheckpointSerialization:
    def test_checkpoint_to_dict_and_back(self):
        """Checkpoint should survive to_dict/from_dict roundtrip."""
        cp = Checkpoint(
            checkpoint_id="cp_test_123",
            cycle_index=5,
            stage="generation",
            stats={"count": 10},
        )
        d = cp.to_dict()
        restored = Checkpoint.from_dict(d)
        assert restored.checkpoint_id == "cp_test_123"
        assert restored.cycle_index == 5
        assert restored.stage == "generation"

    def test_checkpoint_json_serializable(self):
        """Checkpoint.to_dict() should be JSON-serializable."""
        cp = Checkpoint(checkpoint_id="json_test", cycle_index=0, stage="idle")
        json_str = json.dumps(cp.to_dict(), ensure_ascii=False)
        parsed = json.loads(json_str)
        assert parsed["checkpoint_id"] == "json_test"
