"""GuidedPipeline phase implementations mixin."""

from __future__ import annotations

import threading
import time

from brain_alpha_ops.models import PipelineResult

from ._state import classify_error, logger, _pkg


class _PhasesMixin:
    """Mixin providing phase implementations for GuidedPipeline."""

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
            from brain_alpha_ops.brain_api.context_defaults import (
                _DEFAULTS_CACHE,
                _ensure_loaded,
            )
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
                pipeline_result = _pkg().run_pipeline_from_config(
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
                f"生成 {summary.get('total_candidates', 0)} 个候选"
            )
            self.phases["simulation"].complete(
                f"官方仿真 {summary.get('officially_simulated', 0)} 个"
            )
            self.phases["validation"].complete(
                f"官方预验证 {summary.get('official_validation_passed', 0)}/"
                f"{summary.get('official_validation_attempted', 0)} 通过"
            )
            self.phases["submission"].complete(
                f"提交 {summary.get('auto_submitted', 0)} 个"
            )
            self.phases["scoring"].complete(
                f"评分分布: {summary.get('score_distribution', {})}"
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
