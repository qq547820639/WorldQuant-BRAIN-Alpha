"""GuidedPipeline base class: lifecycle, progress, resume, and display."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.models import PipelineResult
from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.ux import guided as guided_storage
guided_display = guided_storage
from brain_alpha_ops.ux.guided import CheckpointData, PipelinePhase

from ._state import classify_error, logger


class GuidedPipelineBase:
    """Base class for GuidedPipeline providing lifecycle and progress management."""

    PHASES = [
        ("init", "准备连接"),
        ("context", "刷新官方资料"),
        ("redline", "合规预检"),
        ("generation", "生成候选"),
        ("validation", "复核本地质量"),
        ("simulation", "运行官方验证"),
        ("scoring", "评分归因"),
        ("gating", "质量门禁"),
        ("submission", "提交安全复核"),
        ("finalize", "完成并保存记录"),
    ]

    def __init__(self, run_config: RunConfig, *, stop_callback: Callable[[], bool] | None = None):
        self.run_config = run_config
        self.phases: dict[str, PipelinePhase] = {}
        self._progress_callback: Callable[[str, str, dict], None] | None = None
        self._stop_flag = False
        self._external_stop_callback = stop_callback
        self._storage_dir = Path(getattr(run_config.ops, "storage_dir", "data") or "data")
        self._checkpoint_dir = self._storage_dir / "checkpoints"
        self._history_dir = self._storage_dir / "run_history"
        self._last_result: PipelineResult | None = None

        # Initialize phases
        for phase_id, phase_desc in self.PHASES:
            self.phases[phase_id] = PipelinePhase(name=phase_id, description=phase_desc)

    def on_progress(self, callback: Callable[[str, str, dict], None]) -> "GuidedPipelineBase":
        """Register progress callback: callback(phase_id, status, data)."""
        self._progress_callback = callback
        return self

    def stop(self) -> None:
        """Signal guided pipeline to stop gracefully."""
        self._stop_flag = True

    def _should_stop(self) -> bool:
        if self._stop_flag:
            return True
        if not self._external_stop_callback:
            return False
        try:
            return bool(self._external_stop_callback())
        except Exception:
            logger.warning("guided pipeline external stop callback failed; continuing execution", exc_info=True)
            return False

    # ── Main Entry Point ──

    def run_guided(self) -> PipelineResult:
        """Run the complete guided pipeline with progress tracking."""
        run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        logger.info("GuidedPipeline started: %s", run_id)
        self._notify("init", "running", {"run_id": run_id})

        result = None
        try:
            # Phase 1: Init
            result = self._phase_init(run_id)

            # Phase 2: Context
            result = self._phase_context(result)

            # Phase 3: Redline
            result = self._phase_redline(result)

            # Phase 4-9: Core pipeline (wrapped)
            result = self._phase_core_pipeline(result)

            # Phase 10: Finalize
            result = self._phase_finalize(result)

        except Exception as e:
            error_info = classify_error(e)
            logger.error("Pipeline failed: %s — %s", error_info["type"], error_info["message"])
            self._notify("error", "failed", error_info)
            # Save checkpoint for resume
            self._save_checkpoint(run_id, "error", result)
            raise

        self._last_result = result
        return result

    def run(self) -> PipelineResult:
        """Backward-compatible alias for legacy internal automation."""
        return self.run_guided()

    def resume(self, run_id: str | None = None) -> PipelineResult:
        """Resume from the latest checkpoint when possible.

        The core pipeline already resumes persisted official backtests from the
        repository. Checkpoints preserve UX state and the latest snapshot; if a
        completed snapshot exists we return it, otherwise we start a guided run
        with persisted-backtest resume enabled.
        """
        checkpoint = self.load_checkpoint(run_id) if run_id else self.latest_checkpoint()
        if checkpoint:
            self._notify("resume", "running", checkpoint.to_dict())
            snapshot_result = self._result_from_snapshot(checkpoint.snapshot)
            if snapshot_result and checkpoint.phase_completed in {"finalize", "completed"}:
                self._last_result = snapshot_result
                self._notify("resume", "completed", {"run_id": checkpoint.run_id})
                return snapshot_result
        return self.run_guided()

    # ── Progress Notification ──

    def _notify(self, phase_id: str, status: str, data: dict) -> None:
        if self._progress_callback:
            try:
                self._progress_callback(phase_id, status, data)
            except Exception as exc:
                logger.warning(
                    "guided pipeline progress callback failed for phase=%s status=%s: %s",
                    phase_id,
                    status,
                    redact_error_message(exc),
                )

    # ── Checkpoint / Resume ──

    def _save_checkpoint(self, run_id: str, phase: str, result: PipelineResult | None = None) -> str:
        return guided_storage.save_checkpoint(self._checkpoint_dir, run_id, phase, result)

    def load_checkpoint(self, run_id: str) -> CheckpointData | None:
        return guided_storage.load_checkpoint(self._checkpoint_dir, run_id)

    def list_checkpoints(self) -> list[dict[str, Any]]:
        return guided_storage.list_checkpoints(self._checkpoint_dir)

    def latest_checkpoint(self) -> CheckpointData | None:
        return guided_storage.latest_checkpoint(self._checkpoint_dir)

    @staticmethod
    def _result_from_snapshot(snapshot: dict[str, Any]) -> PipelineResult | None:
        return guided_storage.result_from_snapshot(snapshot)

    # ── Run History ──

    def _save_run_record(self, result: PipelineResult) -> None:
        guided_storage.save_run_record(
            history_dir=self._history_dir,
            checkpoint_dir=self._checkpoint_dir,
            run_config=self.run_config,
            phases=self.phases.values(),
            result=result,
        )

    def list_history(self) -> list[dict[str, Any]]:
        return guided_storage.list_history(self._storage_dir, limit=10)

    def show_run(self, run_id: str) -> dict[str, Any] | None:
        return guided_storage.show_run(self._storage_dir, run_id)

    def history_analytics(self, *, limit: int = 10) -> dict[str, Any]:
        return guided_storage.history_analytics(self._storage_dir, limit=limit)

    # ── Progress Display ──

    def print_progress(self) -> None:
        """Print current progress to console."""
        guided_display.print_progress(self.phases)

    def print_summary(self, result: PipelineResult | None = None) -> None:
        """Print structured result summary."""
        guided_display.print_summary(self.phases, result or self._last_result)
