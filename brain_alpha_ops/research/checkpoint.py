"""Research pipeline checkpoint and resume system.

Provides checkpoint state tracking for long-running alpha generation pipelines.
Supports atomic writes, graceful degradation, and automatic rollback on failure.

Key concepts:
- Each checkpoint marks a recovery point (cycle boundary, stage boundary)
- Checkpoints are atomic writes to prevent corruption
- Resume logic uses the latest valid checkpoint
- Compatible with both guided and automated pipeline modes
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from brain_alpha_ops.models import Candidate, PipelineEvent

logger = logging.getLogger(__name__)


@dataclass
class Checkpoint:
    """Serializable pipeline checkpoint."""
    checkpoint_id: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    cycle_index: int = 0
    stage: str = "idle"
    candidates: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    stats: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Checkpoint":
        known = {"checkpoint_id", "timestamp", "cycle_index", "stage",
                 "candidates", "events", "metadata", "stats"}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


class CheckpointManager:
    """Manage pipeline checkpoints with atomic writes and recovery.

    Usage:
        mgr = CheckpointManager("data/checkpoints")
        mgr.save(cp)

        if mgr.can_resume():
            last = mgr.latest()
            pipeline.resume_from(last.cycle_index)
    """

    MAX_CHECKPOINTS = 20
    CHECKPOINT_FILE_PATTERN = "checkpoint_{index:04d}.json"
    INDEX_FILE = "checkpoint_index.json"

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._index_lock = __import__("threading").Lock()
        self._ensure_index()

    def save(
        self,
        cycle_index: int,
        stage: str,
        candidates: list[Candidate] | None = None,
        events: list[PipelineEvent] | None = None,
        metadata: dict[str, Any] | None = None,
        stats: dict[str, Any] | None = None,
    ) -> str:
        """Save a checkpoint atomically.

        Returns the checkpoint ID on success, empty string on failure.
        """
        cp = Checkpoint(
            checkpoint_id=f"cp_{int(time.time())}_{cycle_index:04d}",
            cycle_index=cycle_index,
            stage=stage,
            candidates=[c.to_dict() for c in (candidates or [])],
            events=[e.to_dict() for e in (events or [])],
            metadata=dict(metadata or {}),
            stats=dict(stats or {}),
        )
        return self._atomic_write(cp)

    def latest(self) -> Checkpoint | None:
        """Return the most recent valid checkpoint, or None."""
        entries = self._load_index()
        if not entries:
            return None
        for entry in reversed(entries):
            cp = self._load_checkpoint(entry)
            if cp is not None:
                return cp
        return None

    def can_resume(self) -> bool:
        """Return True if there's a valid checkpoint to resume from."""
        return self.latest() is not None

    def list_all(self) -> list[dict[str, Any]]:
        """List all checkpoint metadata."""
        return list(self._load_index())

    def clear(self) -> int:
        """Remove all checkpoints. Returns count of removed files."""
        removed = 0
        for entry in self._load_index():
            filepath = self.directory / entry.get("filename", "")
            if filepath.exists():
                try:
                    filepath.unlink()
                    removed += 1
                except OSError:
                    pass
        index_path = self.directory / self.INDEX_FILE
        if index_path.exists():
            try:
                index_path.unlink()
            except OSError:
                pass
        return removed

    # ── Internal ──

    def _atomic_write(self, cp: Checkpoint) -> str:
        filename = self.CHECKPOINT_FILE_PATTERN.format(index=cp.cycle_index)
        filepath = self.directory / filename
        tmp_path = filepath.with_suffix(filepath.suffix + ".tmp")

        try:
            payload = json.dumps(cp.to_dict(), ensure_ascii=False, indent=2)
            tmp_path.write_text(payload, encoding="utf-8")
            os.replace(tmp_path, filepath)
        except OSError as exc:
            logger.error("CheckpointManager: failed to write checkpoint %s: %s", filepath, exc)
            try:
                tmp_path.unlink()
            except OSError:
                pass
            return ""

        self._register_index_entry(cp, filename)
        self._prune_old()
        return cp.checkpoint_id

    def _ensure_index(self) -> None:
        index_path = self.directory / self.INDEX_FILE
        if not index_path.exists():
            index_path.write_text("[]", encoding="utf-8")

    def _load_index(self) -> list[dict[str, Any]]:
        index_path = self.directory / self.INDEX_FILE
        if not index_path.exists():
            return []
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("CheckpointManager: corrupted index: %s", exc)
            return []

    def _save_index(self, entries: list[dict[str, Any]]) -> None:
        index_path = self.directory / self.INDEX_FILE
        tmp = index_path.with_suffix(index_path.suffix + ".tmp")
        try:
            payload = json.dumps(entries, ensure_ascii=False, indent=2)
            tmp.write_text(payload, encoding="utf-8")
            os.replace(tmp, index_path)
        except OSError as exc:
            logger.error("CheckpointManager: failed to save index: %s", exc)
            try:
                tmp.unlink()
            except OSError:
                pass

    def _register_index_entry(self, cp: Checkpoint, filename: str) -> None:
        with self._index_lock:
            entries = self._load_index()
            entry = {
                "checkpoint_id": cp.checkpoint_id,
                "timestamp": cp.timestamp,
                "cycle_index": cp.cycle_index,
                "stage": cp.stage,
                "filename": filename,
                "candidate_count": len(cp.candidates),
                "event_count": len(cp.events),
            }
            # Update existing entry or append
            existing = next(
                (i for i, e in enumerate(entries) if e.get("cycle_index") == cp.cycle_index),
                None,
            )
            if existing is not None:
                entries[existing] = entry
            else:
                entries.append(entry)
            # Keep sorted by cycle_index
            entries.sort(key=lambda e: e["cycle_index"])
            self._save_index(entries)

    def _load_checkpoint(self, entry: dict[str, Any]) -> Checkpoint | None:
        filename = entry.get("filename", "")
        filepath = self.directory / filename
        if not filepath.exists():
            return None
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            return Checkpoint.from_dict(data)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("CheckpointManager: failed to load %s: %s", filepath, exc)
            return None

    def _prune_old(self) -> None:
        """Remove oldest checkpoints when exceeding MAX_CHECKPOINTS."""
        entries = self._load_index()
        if len(entries) <= self.MAX_CHECKPOINTS:
            return
        to_remove = entries[: len(entries) - self.MAX_CHECKPOINTS]
        for entry in to_remove:
            filepath = self.directory / entry.get("filename", "")
            if filepath.exists():
                try:
                    filepath.unlink()
                except OSError:
                    pass
        remaining = entries[len(entries) - self.MAX_CHECKPOINTS:]
        self._save_index(remaining)


class PipelineRecovery:
    """High-level pipeline recovery orchestration.

    Coordinates checkpoint manager with the research pipeline, providing:
    - Checkpoint-based recovery after crashes
    - Progress summary for user feedback
    - Automatic state reconciliation after resume
    """

    def __init__(self, storage_dir: str | Path):
        self.storage_dir = Path(storage_dir)
        self.checkpoint_dir = self.storage_dir / "checkpoints"
        self.checkpoints = CheckpointManager(self.checkpoint_dir)

    def resume_context(self) -> dict[str, Any]:
        """Build a resume context dict for pipeline initialization.

        Returns:
            {
                "can_resume": bool,
                "cycle_index": int,       # 0-based: resume from cycle_index+1
                "stage": str,
                "candidate_count": int,
                "recovered_candidates": list[dict],
                "events_count": int,
            }
        """
        latest = self.checkpoints.latest()
        if latest is None:
            return {
                "can_resume": False,
                "cycle_index": -1,
                "stage": "fresh_start",
                "candidate_count": 0,
                "recovered_candidates": [],
                "events_count": 0,
            }
        return {
            "can_resume": True,
            "cycle_index": latest.cycle_index,
            "stage": latest.stage,
            "candidate_count": len(latest.candidates),
            "recovered_candidates": latest.candidates,
            "events_count": len(latest.events),
            "checkpoint_id": latest.checkpoint_id,
            "metadata": latest.metadata,
            "stats": latest.stats,
        }

    def snapshot(
        self,
        cycle_index: int,
        stage: str,
        candidates: list[Candidate] | None = None,
        events: list[PipelineEvent] | None = None,
        stats: dict[str, Any] | None = None,
    ) -> str:
        """Convenience wrapper that always snapshots metadata too."""
        metadata = {
            "snapshot_time": datetime.now(timezone.utc).isoformat(),
            "pid": os.getpid(),
        }
        return self.checkpoints.save(
            cycle_index=cycle_index,
            stage=stage,
            candidates=candidates,
            events=events,
            metadata=metadata,
            stats=stats,
        )

    def recovery_summary(self) -> str:
        """Human-readable recovery status for CLI/Web UX."""
        ctx = self.resume_context()
        if not ctx["can_resume"]:
            return "No checkpoint found — starting fresh pipeline."
        return (
            f"Checkpoint found: cycle {ctx['cycle_index']} ({ctx['stage']}), "
            f"{ctx['candidate_count']} candidates, {ctx['events_count']} events. "
            f"Resuming from next cycle."
        )
