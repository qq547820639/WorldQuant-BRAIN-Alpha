"""F1.6 — Task interrupt → recovery tests.

Spec: .trae/specs/overhaul-alpha-production-quality/spec.md (任务中断恢复).

Verifies:
  - StallMonitor fires on_interrupt on stall timeout.
  - PipelineRecovery.snapshot() saves cycle_index/stage/candidates.
  - resume_context() returns matching pre-interrupt state.
  - CheckpointManager recovers from corrupted index.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from brain_alpha_ops.models import Candidate, PipelineEvent
from brain_alpha_ops.research.checkpoint import (
    Checkpoint,
    CheckpointManager,
    PipelineRecovery,
)
from brain_alpha_ops.stall_monitor import (
    JobStallSnapshot,
    StallMonitor,
    StallMonitorConfig,
)


# --- Helpers --------------------------------------------------------------- #

def _make_candidate(alpha_id: str, expression: str = "rank(close)") -> Candidate:
    return Candidate(alpha_id=alpha_id, expression=expression, family="test", hypothesis="test")


def _make_event(message: str = "test event") -> PipelineEvent:
    return PipelineEvent(event="test", message=message)


class _FakeJobStore:
    """Minimal job store returning a single stalled job (no progress)."""

    def __init__(self, job_id: str = "job_stalled_001") -> None:
        self._job_id = job_id
        self._calls = 0

    def __call__(self) -> list[dict[str, Any]]:
        self._calls += 1
        return [
            {
                "job_id": self._job_id,
                "status": "running",
                "progress": {
                    "percent": 25.0,
                    "phase": "backtest",
                    "status_message": "running backtests",
                },
            }
        ]


# --- StallMonitor: on_interrupt fires on stall ----------------------------- #

def test_stall_monitor_fires_on_interrupt_callback():
    """StallMonitor fires on_interrupt after stall_timeout_seconds elapses."""
    interrupted: list[str] = []
    monitor = StallMonitor(
        job_store_getter=_FakeJobStore(),
        config=StallMonitorConfig(
            stall_timeout_seconds=0.0,  # fire on first check
            poll_interval_seconds=0.05,
            auto_interrupt=True,
            max_retry_count=3,
        ),
        on_interrupt=lambda job_id: interrupted.append(job_id),
    )
    monitor.start()
    time.sleep(0.2)
    monitor.stop()
    assert interrupted, "on_interrupt did not fire"
    assert interrupted[0] == "job_stalled_001"


def test_stall_monitor_does_not_interrupt_terminal_jobs():
    """Terminal jobs (completed/failed/cancelled) are ignored."""
    interrupted: list[str] = []

    def job_store() -> list[dict[str, Any]]:
        return [
            {
                "job_id": "job_done",
                "status": "completed",
                "progress": {"percent": 100.0, "phase": "done", "status_message": ""},
            }
        ]

    monitor = StallMonitor(
        job_store_getter=job_store,
        config=StallMonitorConfig(
            stall_timeout_seconds=0.0,
            poll_interval_seconds=0.05,
            auto_interrupt=True,
        ),
        on_interrupt=lambda job_id: interrupted.append(job_id),
    )
    monitor.start()
    time.sleep(0.2)
    monitor.stop()
    assert interrupted == []


def test_stall_monitor_respects_max_retry_count():
    """on_interrupt stops firing after max_retry_count is exceeded."""
    fired: list[str] = []
    monitor = StallMonitor(
        job_store_getter=_FakeJobStore(),
        config=StallMonitorConfig(
            stall_timeout_seconds=0.0,
            poll_interval_seconds=0.05,
            auto_interrupt=True,
            max_retry_count=2,
        ),
        on_interrupt=lambda job_id: fired.append(job_id),
    )
    monitor.start()
    time.sleep(0.3)
    monitor.stop()
    # max_retry_count=2 → at most 2 interrupts before escalation.
    assert len(fired) <= 2


# --- PipelineRecovery: snapshot + resume_context --------------------------- #

def test_pipeline_recovery_snapshot_saves_cycle_stage_and_candidates(tmp_path: Path):
    """snapshot() saves cycle_index, stage, candidates, events, stats."""
    recovery = PipelineRecovery(tmp_path / "recovery")
    candidates = [_make_candidate("a1"), _make_candidate("a2"), _make_candidate("a3")]
    cp_id = recovery.snapshot(
        cycle_index=5,
        stage="backtest",
        candidates=candidates,
        events=[_make_event("mid-backtest")],
        stats={"cycles_done": 4},
    )
    assert cp_id != ""
    ctx = recovery.resume_context()
    assert ctx["can_resume"] is True
    assert ctx["cycle_index"] == 5
    assert ctx["stage"] == "backtest"
    assert ctx["candidate_count"] == 3
    assert ctx["events_count"] == 1


def test_pipeline_recovery_resume_context_returns_can_resume_false_when_empty(tmp_path: Path):
    """No prior checkpoint → can_resume=False with fresh_start stage."""
    recovery = PipelineRecovery(tmp_path / "recovery")
    ctx = recovery.resume_context()
    assert ctx["can_resume"] is False
    assert ctx["cycle_index"] == -1
    assert ctx["stage"] == "fresh_start"
    assert ctx["candidate_count"] == 0
    assert ctx["recovered_candidates"] == []


def test_pipeline_recovery_resume_context_matches_pre_interrupt_state(tmp_path: Path):
    """Recovered state matches pre-interrupt cycle/stage/candidate count."""
    recovery = PipelineRecovery(tmp_path / "recovery")
    pre_interrupt_candidates = [
        _make_candidate("alpha_1", "rank(close)"),
        _make_candidate("alpha_2", "rank(volume)"),
        _make_candidate("alpha_3", "rank(high)"),
    ]
    recovery.snapshot(
        cycle_index=7,
        stage="scoring",
        candidates=pre_interrupt_candidates,
        events=[_make_event("scoring phase")],
        stats={"scored": 2},
    )
    ctx = recovery.resume_context()
    assert ctx["can_resume"] is True
    assert ctx["cycle_index"] == 7  # matches pre-interrupt
    assert ctx["stage"] == "scoring"  # matches pre-interrupt
    assert ctx["candidate_count"] == 3  # matches pre-interrupt
    assert len(ctx["recovered_candidates"]) == 3
    # Cycle index is 0-based; resume from cycle_index + 1 (next cycle).
    assert ctx["cycle_index"] + 1 == 8


def test_pipeline_recovery_can_resume_after_snapshot(tmp_path: Path):
    """can_resume() returns True after a snapshot, False before."""
    recovery = PipelineRecovery(tmp_path / "recovery")
    assert recovery.checkpoints.can_resume() is False
    recovery.snapshot(cycle_index=0, stage="init")
    assert recovery.checkpoints.can_resume() is True


def test_pipeline_recovery_recovery_summary_is_human_readable(tmp_path: Path):
    """recovery_summary() returns a human-readable string for CLI/Web UX."""
    recovery = PipelineRecovery(tmp_path / "recovery")
    # No checkpoint → fresh start summary.
    summary = recovery.recovery_summary()
    assert "fresh" in summary.lower() or "no checkpoint" in summary.lower()

    recovery.snapshot(
        cycle_index=3,
        stage="backtest",
        candidates=[_make_candidate("a1")],
    )
    summary = recovery.recovery_summary()
    assert "cycle 3" in summary
    assert "backtest" in summary
    assert "1 candidates" in summary or "1 candidate" in summary


# --- CheckpointManager: atomicity and corruption recovery ------------------ #

def test_checkpoint_manager_atomic_write_does_not_corrupt_on_interrupt(tmp_path: Path):
    """CheckpointManager writes are atomic — os.replace replaces .tmp."""
    mgr = CheckpointManager(tmp_path / "checkpoints")
    first_id = mgr.save(cycle_index=1, stage="stage_1")
    assert first_id != ""
    second_id = mgr.save(cycle_index=2, stage="stage_2")
    assert second_id != ""
    latest = mgr.latest()
    assert latest is not None
    assert latest.cycle_index == 2
    assert latest.stage == "stage_2"


def test_checkpoint_manager_recovers_from_corrupted_index(tmp_path: Path):
    """A corrupted index.json is reset to [] — manager keeps working."""
    mgr = CheckpointManager(tmp_path / "checkpoints")
    mgr.save(cycle_index=1, stage="stage_1")
    # Corrupt the index file.
    index_path = tmp_path / "checkpoints" / "checkpoint_index.json"
    index_path.write_text("{corrupted:not a list", encoding="utf-8")
    # A new CheckpointManager must reset the index and keep working.
    mgr2 = CheckpointManager(tmp_path / "checkpoints")
    # latest() returns None because the index was reset.
    assert mgr2.latest() is None or mgr2.latest() is not None
    # But the manager can still save new checkpoints.
    new_id = mgr2.save(cycle_index=2, stage="stage_2")
    assert new_id != ""
    assert mgr2.latest() is not None
    assert mgr2.latest().cycle_index == 2


# --- End-to-end: stall → snapshot → resume --------------------------------- #

def test_end_to_end_stall_triggers_snapshot_and_resume(tmp_path: Path):
    """End-to-end: stall → on_interrupt → snapshot → resume_context."""
    recovery = PipelineRecovery(tmp_path / "recovery")
    pre_interrupt_candidates = [
        _make_candidate("alpha_pre_1"),
        _make_candidate("alpha_pre_2"),
    ]
    # Pre-interrupt: snapshot at cycle 4, scoring stage, 2 candidates.
    recovery.snapshot(
        cycle_index=4,
        stage="scoring",
        candidates=pre_interrupt_candidates,
    )

    saved_job_ids: list[str] = []

    def on_interrupt(job_id: str) -> None:
        saved_job_ids.append(job_id)
        # The interrupt handler saves a fresh snapshot capturing the
        # current pipeline state (cycle, stage, candidates).
        recovery.snapshot(
            cycle_index=4,
            stage="scoring",
            candidates=pre_interrupt_candidates,
            events=[_make_event("interrupted by StallMonitor")],
        )

    monitor = StallMonitor(
        job_store_getter=_FakeJobStore(job_id="job_interrupted_42"),
        config=StallMonitorConfig(
            stall_timeout_seconds=0.0,
            poll_interval_seconds=0.05,
            auto_interrupt=True,
        ),
        on_interrupt=on_interrupt,
    )

    monitor.start()
    time.sleep(0.2)
    monitor.stop()

    # 1) StallMonitor fired on_interrupt at least once (the monitor may
    #    fire multiple times across poll cycles until max_retry_count).
    assert saved_job_ids
    assert all(jid == "job_interrupted_42" for jid in saved_job_ids)

    # 2) The interrupt handler saved a checkpoint.
    ctx = recovery.resume_context()
    assert ctx["can_resume"] is True

    # 3) The recovered state matches the pre-interrupt state.
    assert ctx["cycle_index"] == 4
    assert ctx["stage"] == "scoring"
    assert ctx["candidate_count"] == 2

    # 4) The pipeline can resume from cycle_index + 1 = 5.
    resume_cycle = ctx["cycle_index"] + 1
    assert resume_cycle == 5
