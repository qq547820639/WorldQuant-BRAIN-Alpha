"""Guided user experience layer for progress, feedback, resume, and history.

GuidedPipeline — wraps AlphaResearchPipeline with:
  1. Step-by-step process guidance with progress indicators
  2. Real-time status feedback via callback mechanism
  3. Actionable error messages with fix suggestions
  4. Structured result presentation for the Web console
  5. Checkpoint/resume mechanism for long-running pipelines
  6. Historical run browser and replay capability

"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.error_knowledge import classify_ux_error as _unified_classify
from brain_alpha_ops.models import PipelineEvent, PipelineResult
from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.runner import run_pipeline_from_config
from brain_alpha_ops.ux import guided_display, guided_storage
from brain_alpha_ops.ux.guided_formatting import format_candidate_summary, format_error_for_user, format_pipeline_progress
from brain_alpha_ops.ux.guided_models import CheckpointData, PipelinePhase, RunRecord

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# Error Classification & Actionable Messages
# ═══════════════════════════════════════════════════════════════════════

def classify_error(error: Exception) -> dict[str, str]:
    """Classify an error and return actionable guidance."""
    try:
        info = _unified_classify(error)
        return {
            "type": info.error_code or type(error).__name__,
            "message": redact_error_message(error, max_length=200),
            "fix": info.fix_hint or "未知错误。请在页面事件记录中查看提示，或让维护者查看诊断信息。",
            "retry": "yes" if info.retryable else ("maybe" if info.retryable is None else "no"),
        }
    except Exception:
        logger.warning("guided pipeline error classification fallback failed", exc_info=True)
        return {
            "type": type(error).__name__,
            "message": redact_error_message(error, max_length=200),
            "fix": "未知错误。请在页面事件记录中查看提示，或让维护者查看诊断信息。",
            "retry": "maybe",
        }

# ═══════════════════════════════════════════════════════════════════════
# Guided Pipeline
# ═══════════════════════════════════════════════════════════════════════

class GuidedPipeline:
    """Guided UX pipeline wrapper around the standard pipeline.

    """

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

    def on_progress(self, callback: Callable[[str, str, dict], None]) -> "GuidedPipeline":
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

    # ── Phase Implementations ──

    def _phase_init(self, run_id: str) -> PipelineResult:
        phase = self.phases["init"]
        phase.start()
        self._notify("init", "running", {})

        # Validate environment
        env = self.run_config.environment
        creds = self.run_config.credentials.resolve()
        has_auth = bool(creds.get("username") or creds.get("token"))

        if env == "production" and not has_auth:
            raise RuntimeError(
                "生产环境需要 BRAIN 凭据。请在 Web 控制台填写并测试 BRAIN 账户，"
                "或请维护者检查托管凭证。"
            )

        if env == "production":
            phase.complete(f"环境: production, 认证: {'已配置' if has_auth else '未配置'}")
        else:
            phase.complete(f"环境: {env} (模拟模式)")

        self._notify("init", "completed", {"environment": env})
        return PipelineResult(run_id=run_id, candidates=[], events=[], summary={})

    def _phase_context(self, result: PipelineResult) -> PipelineResult:
        phase = self.phases["context"]
        phase.start()
        self._notify("context", "running", {})

        try:
            from brain_alpha_ops.brain_api.context_defaults import _ensure_loaded, _DEFAULTS_CACHE
            _ensure_loaded()
            fields_count = len(_DEFAULTS_CACHE.get("fields", []))
            ops_count = len(_DEFAULTS_CACHE.get("operators", []))

            if fields_count == 0:
                phase.fail("BRAIN 上下文为空 — 请在 Web 控制台刷新官方能力集")
                self._notify("context", "failed", {"error": "empty_context"})
                return result

            phase.complete(f"字段: {fields_count} 个, 算子: {ops_count} 个")
            self._notify("context", "completed", {
                "fields_count": fields_count,
                "operators_count": ops_count,
            })
        except Exception as e:
            logger.warning("guided pipeline context phase failed", exc_info=True)
            phase.fail(str(e))
            self._notify("context", "failed", classify_error(e))

        return result

    def _phase_redline(self, result: PipelineResult) -> PipelineResult:
        phase = self.phases["redline"]
        phase.start()
        self._notify("redline", "running", {})

        try:
            from brain_alpha_ops.compliance.redline_verifier import RedLineVerifier
            verifier = RedLineVerifier(self.run_config)
            report = verifier.verify_all()

            if report.overall == "FAIL":
                blocking = [v for v in report.violations if v.severity == "BLOCKING"]
                phase.fail(f"红线验证失败: {len(blocking)} 个阻断项")
                self._notify("redline", "failed", {
                    "overall": report.overall,
                    "violations": len(report.violations),
                    "blocking": len(blocking),
                })
                phase.warnings.extend(
                    f"[{v.redline_id}] {v.check_name}: {v.fix_guidance}" for v in blocking
                )
                raise RuntimeError(
                    f"TECH_REDLINE_BLOCKED: {len(blocking)} blocking violations detected"
                )
            else:
                phase.complete(f"通过: {report.passed}/{report.total_checks} 项")
                self._notify("redline", "completed", {
                    "overall": report.overall,
                    "passed": report.passed,
                })
        except ImportError as e:
            phase.fail("红线验证模块不可用")
            self._notify("redline", "failed", {"error": str(e)})
            raise RuntimeError("TECH_REDLINE_BLOCKED: redline verifier unavailable") from e
        except Exception as e:
            logger.warning("guided pipeline redline phase failed", exc_info=True)
            phase.fail(str(e))
            self._notify("redline", "failed", classify_error(e))
            raise

        return result

    def _phase_core_pipeline(self, result: PipelineResult) -> PipelineResult:
        """Wrap core pipeline with progress callbacks (Phase 4)."""
        _t0 = time.time()
        PHASE4_TIMEOUT_SECONDS = int(
            getattr(self.run_config.ops.budget, "phase4_timeout_seconds", 0) or 300
        )
        logger.info(
            "core_pipeline phase 4 start — timeout=%ds",
            PHASE4_TIMEOUT_SECONDS,
        )
        logger.info("core_pipeline phase 4 start — budget keys: %s",
                    sorted(k for k in dir(self.run_config.ops.budget) if not k.startswith("_")))
        for phase_id in ["generation", "validation", "simulation", "scoring", "gating", "submission"]:
            phase = self.phases[phase_id]
            phase.start()
            self._notify(phase_id, "running", {})

        class _Phase4Timeout(Exception):
            pass

        # Threading-based timeout — reliable in multi-threaded contexts
        _timeout_result: list = []
        _timeout_done = threading.Event()

        def _run_within_timeout():
            try:
                logger.info("core_pipeline init done — calling run_pipeline_from_config")
                pipeline_result = run_pipeline_from_config(
                    self.run_config,
                    progress_callback=progress_callback,
                    stop_callback=stop_callback,
                )
                _timeout_result.append(pipeline_result)
            except Exception as exc:
                _timeout_result.append(exc)
            finally:
                _timeout_done.set()

        try:
            def progress_callback(event) -> None:
                if isinstance(event, dict):
                    phase = self._phase_id_from_core_progress(str(event.get("phase") or ""))
                    status = str(event.get("status") or "progress")
                    self._notify(phase, status, dict(event))
                elif hasattr(event, "event") and hasattr(event, "level"):
                    phase_map = {
                        "generation": "generation",
                        "validation": "validation",
                        "simulation": "simulation",
                        "score": "scoring",
                        "gate": "gating",
                        "submit": "submission",
                    }
                    matched = "generation"
                    for key, pid in phase_map.items():
                        if key in (event.event or "").lower():
                            matched = pid
                            break
                    self._notify(matched, "progress", {
                        "event": event.event,
                        "alpha_id": event.alpha_id,
                        "message": event.message,
                    })

            def stop_callback() -> bool:
                return self._should_stop()

            thread = threading.Thread(target=_run_within_timeout, daemon=True)
            thread.start()
            thread.join(timeout=PHASE4_TIMEOUT_SECONDS)

            if not _timeout_done.is_set():
                elapsed = time.time() - _t0
                logger.error(
                    "core_pipeline phase 4 TIMEOUT after %.1fs (limit=%ds) — thread still running",
                    elapsed, PHASE4_TIMEOUT_SECONDS,
                )
                raise _Phase4Timeout(
                    f"phase 4 timeout after {elapsed:.1f}s (limit={PHASE4_TIMEOUT_SECONDS}s)"
                )

            if not _timeout_result:
                raise RuntimeError("core_pipeline phase 4 returned no result")

            raw = _timeout_result[0]
            if isinstance(raw, Exception):
                raise raw
            pipeline_result = raw

            # Update phases with results
            summary = pipeline_result.summary
            self.phases["generation"].complete(
                f"生成 {summary.get("total_candidates", 0)} 个候选"
            )
            self.phases["simulation"].complete(
                f"官方仿真 {summary.get("officially_simulated", 0)} 个"
            )
            self.phases["validation"].complete(
                f"官方预验证 {summary.get("official_validation_passed", 0)}/"
                f"{summary.get("official_validation_attempted", 0)} 通过"
            )
            self.phases["submission"].complete(
                f"提交 {summary.get("auto_submitted", 0)} 个"
            )
            self.phases["scoring"].complete(
                f"评分分布: {summary.get("score_distribution", {})}"
            )
            gate_summary = summary.get("gate_summary") or {}
            ready = summary.get("submission_ready", 0)
            self.phases["gating"].complete(
                f"门禁可提交 {ready} 个; 分布 {gate_summary}"
            )

            elapsed = time.time() - _t0
            logger.info(
                "core_pipeline phase 4 completed in %.1fs — %d candidates, %d simulated, %d submitted",
                elapsed,
                summary.get("total_candidates", 0),
                summary.get("officially_simulated", 0),
                summary.get("auto_submitted", 0),
            )
            return pipeline_result

        except Exception:
            elapsed = time.time() - _t0
            logger.warning(
                "guided pipeline core pipeline phase failed after %.1fs",
                elapsed, exc_info=True,
            )
            for pid in ["generation", "validation", "simulation", "scoring", "gating", "submission"]:
                if self.phases[pid].status == "running":
                    self.phases[pid].fail("核心流水线异常终止")
            raise

    @staticmethod
    def _phase_id_from_core_progress(phase: str) -> str:
        normalized = (phase or "").lower()
        phase_map = (
            ("generation", ("generation", "production", "candidate")),
            ("validation", ("validation", "local_scoring", "prefilter")),
            ("simulation", ("simulation", "backtest", "official")),
            ("scoring", ("score",)),
            ("gating", ("gate",)),
            ("submission", ("submit",)),
            ("finalize", ("completed", "stopped", "failed")),
        )
        for phase_id, keys in phase_map:
            if any(key in normalized for key in keys):
                return phase_id
        return "generation"

    def _phase_finalize(self, result: PipelineResult) -> PipelineResult:
        phase = self.phases["finalize"]
        phase.start()
        self._notify("finalize", "running", {})

        try:
            summary = result.summary
            phase.complete(
                f"运行完成 — 候选 {summary.get('total_candidates', 0)} 个, "
                f"仿真 {summary.get('officially_simulated', 0)} 个, "
                f"提交 {summary.get('auto_submitted', 0)} 个"
            )

            # Save run record
            self._save_run_record(result)

            self._notify("finalize", "completed", {
                "summary": summary,
            })
        except Exception as e:
            logger.warning("guided pipeline finalize phase failed", exc_info=True)
            phase.fail(str(e))

        return result

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
