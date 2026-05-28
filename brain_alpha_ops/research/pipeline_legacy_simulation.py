"""Legacy direct simulation helpers retained for compatibility tests."""

from __future__ import annotations

import time

from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.redaction import redact_error_message

from .pipeline_helpers import blocked_gate as _blocked_gate


class PipelineLegacySimulationMixin:
    def _simulate_batch(self, candidates: list[Candidate]) -> list[Candidate]:
        submitted: list[Candidate] = []
        total = len(candidates)
        if not candidates:
            self._progress("official_simulation", 0, 1, "候选池中暂时没有满足回测门槛的 Alpha。")
            return submitted

        self._progress(
            "simulation_submit",
            0,
            total,
            f"已选择排名前 {total} 的 Alpha，准备逐个提交官方回测任务。",
            data={"backtests": self._backtest_snapshot(candidates)},
        )
        for index, candidate in enumerate(candidates, start=1):
            self._progress("simulation_submit", index - 1, total, f"提交回测任务 {index}/{total}：{candidate.alpha_id}", candidate.alpha_id)
            settings = self.config.settings.to_platform_dict()["settings"]
            candidate.submission["settings"] = dict(settings)
            try:
                sim_id = self.api.submit_simulation(candidate.expression, settings)
            except BrainAPIError as exc:
                self._handle_simulation_submit_error(exc, candidate, candidates[index:], submitted)
                break
            candidate.simulation_id = sim_id
            candidate.lifecycle_status = "simulation_submitted"
            candidate.submission["backtest_batch_rank"] = index
            submitted.append(candidate)
            self.backtests_submitted += 1
            self._progress(
                "simulation_submit",
                index,
                total,
                f"回测任务 {index}/{total} 已提交：{sim_id}",
                candidate.alpha_id,
                data={"backtests": self._backtest_snapshot(candidates)},
            )

        real_submitted = [candidate for candidate in submitted if candidate.simulation_id]
        if real_submitted:
            self._wait_for_simulation_batch(real_submitted)
        return submitted

    def _handle_simulation_submit_error(
        self,
        exc: BrainAPIError,
        candidate: Candidate,
        remaining: list[Candidate],
        submitted: list[Candidate],
    ):
        error_text = redact_error_message(exc)
        if "CONCURRENT_SIMULATION_LIMIT_EXCEEDED" in error_text:
            status = "SIMULATION_DEFERRED_CONCURRENCY_LIMIT"
            reason = "official concurrent simulation limit exceeded; retry after running BRAIN simulations finish"
        elif exc.status_code == 429:
            status = "SIMULATION_DEFERRED_RATE_LIMIT"
            retry_after = f"; retry_after={exc.retry_after}" if exc.retry_after is not None else ""
            reason = f"official API rate limit reached{retry_after}; defer remaining official calls"
        else:
            candidate.lifecycle_status = "simulation_request_failed"
            candidate.gate = _blocked_gate("SIMULATION_REQUEST_FAILED", [error_text])
            submitted.append(candidate)
            self._event("official_simulation_failed", "; ".join(candidate.gate["failed_reasons"]), candidate.alpha_id)
            return

        self._halt_official_calls(reason)
        for item in [candidate] + remaining:
            item.lifecycle_status = status.lower()
            item.gate = _blocked_gate(status, [reason])
            submitted.append(item)
        self._event("official_simulation_halted", reason, candidate.alpha_id)
        self._progress("official_deferred", 0, 1, reason, candidate.alpha_id, data={"backtests": self._backtest_snapshot(submitted)})

    def _wait_for_simulation_batch(self, candidates: list[Candidate]):
        api_config = getattr(self.api, "config", None)
        attempts = max(1, int(getattr(api_config, "poll_attempts", 1)))
        interval = max(0.0, float(getattr(api_config, "poll_interval_seconds", 0.0)))
        running = {candidate.simulation_id: candidate for candidate in candidates if candidate.simulation_id}
        completed_count = 0

        for attempt in range(1, attempts + 1):
            for sim_id, candidate in list(running.items()):
                try:
                    status = self.api.poll_simulation(sim_id)
                except BrainAPIError as exc:
                    if exc.status_code == 429:
                        self._halt_official_calls(f"official simulation polling rate limit reached; retry later: {redact_error_message(exc)}")
                        candidate.lifecycle_status = "simulation_poll_deferred_rate_limit"
                        candidate.gate = _blocked_gate("SIMULATION_POLL_DEFERRED_RATE_LIMIT", [self.official_halt_reason])
                        self._event("official_simulation_poll_deferred", self.official_halt_reason, candidate.alpha_id, level="WARN")
                        return
                    candidate.lifecycle_status = "simulation_poll_failed"
                    candidate.gate = _blocked_gate("SIMULATION_POLL_FAILED", [redact_error_message(exc)])
                    del running[sim_id]
                    completed_count += 1
                    continue

                candidate.submission["simulation_status"] = status
                if status == "COMPLETED":
                    try:
                        result = self.api.fetch_result(sim_id)
                    except BrainAPIError as exc:
                        if exc.status_code == 429:
                            self._halt_official_calls(f"official simulation result rate limit reached; retry later: {redact_error_message(exc)}")
                            candidate.lifecycle_status = "simulation_result_deferred_rate_limit"
                            candidate.gate = _blocked_gate("SIMULATION_RESULT_DEFERRED_RATE_LIMIT", [self.official_halt_reason])
                            self._event("official_simulation_result_deferred", self.official_halt_reason, candidate.alpha_id, level="WARN")
                            return
                        candidate.lifecycle_status = "simulation_result_failed"
                        candidate.gate = _blocked_gate("SIMULATION_RESULT_FAILED", [redact_error_message(exc)])
                        del running[sim_id]
                        completed_count += 1
                        continue
                    candidate.official_alpha_id = result.get("alpha_id", "") or result.get("metrics", {}).get("official_alpha_id", "")
                    candidate.official_metrics = result.get("metrics", {})
                    candidate.lifecycle_status = "official_simulated"
                    self.officially_simulated_count += 1
                    del running[sim_id]
                    completed_count += 1
                elif status == "FAILED":
                    candidate.lifecycle_status = "simulation_failed"
                    candidate.gate = _blocked_gate("SIMULATION_FAILED", [status])
                    del running[sim_id]
                    completed_count += 1
                else:
                    candidate.lifecycle_status = "simulation_running"

            self._progress(
                "simulation_wait",
                completed_count,
                len(candidates),
                f"等待回测结果：完成 {completed_count}/{len(candidates)}，轮询 {attempt}/{attempts}。",
                data={
                    "backtests": self._backtest_snapshot(candidates),
                    "completed": completed_count,
                },
            )
            if not running:
                return
            if attempt < attempts and interval:
                if not self._sleep_with_stop(interval):
                    return

        for candidate in running.values():
            candidate.lifecycle_status = "simulation_timeout"
            candidate.gate = _blocked_gate("SIMULATION_TIMEOUT", ["official simulation did not finish before poll timeout"])

    def _should_remove_after_official_result(self, candidate: Candidate) -> bool:
        if not candidate.official_metrics:
            return candidate.lifecycle_status in {
                "simulation_failed",
                "simulation_poll_failed",
                "simulation_request_failed",
                "simulation_result_failed",
                "simulation_timeout",
            }
        if candidate.gate.get("submission_ready"):
            candidate.lifecycle_status = "submission_ready"
            return False
        candidate.lifecycle_status = "official_standard_rejected"
        if not candidate.gate:
            candidate.gate = _blocked_gate("OFFICIAL_STANDARD_REJECTED", ["official metrics did not pass configured quality gate"])
        return True
