"""OfficialSimulationSubmissionMixin: simulation submission, polling, and checks."""

from __future__ import annotations

import time
import urllib.parse
from concurrent.futures import TimeoutError as FuturesTimeoutError, ThreadPoolExecutor, as_completed
from typing import Any, Callable, Iterable

from ..base import BrainAPIError
from ..official_helpers import (
    _first_value,
    build_official_url,
    build_simulation_payload,
    normalize_metrics,
)
from ..official_helpers import (
    items as _items,
)
from ..official_helpers import (
    looks_non_production_alpha_id as _looks_non_production_alpha_id,
)
from ..official_helpers import (
    merge_payloads as _merge,
)
from ..official_helpers import (
    retry_after as _retry_after,
)
from ..official_helpers import (
    scrub as _scrub,
)
from ._helpers import (
    _CHECK_FAIL_STATES,
    _CHECK_PASS_STATES,
    _CHECK_PENDING_STATES,
    _MAX_DEFAULT_CONCURRENT_OFFICIAL_JOBS,
    _bounded_concurrency,
    _check_result_from_response,
    _simulation_input,
    _verify_submit_guard,
)


class OfficialSimulationSubmissionMixin:
    def submit_simulation(self, expression: str, settings: dict) -> str:
        body = build_simulation_payload(expression, settings)
        data, headers = self._request("POST", self.config.simulations_path, body=body)
        location = headers.get("Location") or headers.get("location")
        sim_id = location or _first_value(data, ["id", "simulation_id", "location"], "")
        if not sim_id:
            raise BrainAPIError(f"simulation submission did not return a location/id: {_scrub(data)}")
        if str(sim_id).startswith(("http://", "https://")):
            normalized = build_official_url(self.config.base_url, str(sim_id), None)
            parsed = urllib.parse.urlparse(normalized)
            sim_id = urllib.parse.urlunparse(("", "", parsed.path or "/", "", parsed.query, ""))
        return str(sim_id)

    def poll_simulation(self, simulation_id: str) -> str:
        status, _retry_after_seconds = self._poll_simulation_once(simulation_id)
        return status

    def _poll_simulation_once(self, simulation_id: str) -> tuple[str, float | None]:
        data, _headers = self._request("GET", simulation_id)
        status = str(_first_value(data, ["status", "state"], "")).upper()
        if status in {"COMPLETE", "COMPLETED", "DONE"} or _first_value(data, ["alpha", "alpha_id", "alphaId"], ""):
            return "COMPLETED", _retry_after(_headers)
        if status in {"FAILED", "ERROR"}:
            return "FAILED", _retry_after(_headers)
        return "RUNNING", _retry_after(_headers)

    def fetch_result(self, simulation_id: str) -> dict:
        data, _headers = self._request("GET", simulation_id)
        alpha_id = _first_value(data, ["alpha", "alpha_id", "alphaId"], "")
        if isinstance(alpha_id, dict):
            alpha_id = _first_value(alpha_id, ["id", "alpha_id", "alphaId"], "")
        alpha_payload = {}
        if alpha_id:
            try:
                alpha_payload, _headers = self._request(
                    "GET",
                    self.config.alpha_path_template.format(alpha_id=alpha_id),
                )
            except BrainAPIError:
                alpha_payload = {}
        merged = _merge(data, alpha_payload)
        metrics = normalize_metrics(merged)
        if alpha_id:
            metrics["official_alpha_id"] = str(alpha_id)
        return {
            "simulation_id": simulation_id,
            "alpha_id": str(alpha_id or ""),
            "metrics": metrics,
            "raw": _scrub(merged),
        }

    def check_alpha(self, alpha_id: str) -> dict:
        if not alpha_id:
            raise BrainAPIError("cannot check an alpha without alpha_id")
        path = self.config.alpha_check_path_template.format(alpha_id=alpha_id)
        data, _headers = self._request("GET", path)
        return _check_result_from_response(data)

    def concurrent_simulate(
        self,
        alphas: Iterable[dict[str, Any] | tuple[str, dict[str, Any]]],
        concurrency: int = _MAX_DEFAULT_CONCURRENT_OFFICIAL_JOBS,
        *,
        return_exceptions: bool = False,
        timeout: float = 300,
    ) -> list[dict[str, Any] | BaseException]:
        rows = list(alphas or [])
        if not rows:
            return []
        worker_count = _bounded_concurrency(concurrency)
        results: list[dict[str, Any] | None] = [None] * len(rows)
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                executor.submit(self._simulate_one_alpha_payload, index, row, return_exceptions=return_exceptions): index
                for index, row in enumerate(rows)
            }
            for future in as_completed(futures):
                index = futures[future]
                try:
                    results[index] = future.result(timeout=timeout)
                except FuturesTimeoutError:
                    future.cancel()
                    timeout_exc = FuturesTimeoutError(f"simulation timed out after {timeout}s")
                    results[index] = timeout_exc if return_exceptions else {
                        "ok": False,
                        "index": index,
                        "status": "TIMEOUT",
                        "error": f"simulation timed out after {timeout}s",
                    }
                except Exception as exc:  # pragma: no cover - defensive; worker already wraps expected failures
                    results[index] = exc if return_exceptions else {
                        "ok": False,
                        "index": index,
                        "status": "ERROR",
                        "error": str(_scrub(str(exc))),
                    }
        return [row or {"ok": False, "index": index, "status": "ERROR", "error": "missing result"} for index, row in enumerate(results)]

    def concurrent_check(
        self,
        alpha_ids: Iterable[str],
        concurrency: int = _MAX_DEFAULT_CONCURRENT_OFFICIAL_JOBS,
        *,
        return_exceptions: bool = False,
        timeout: float = 300,
    ) -> list[dict[str, Any] | BaseException]:
        ids = [str(alpha_id or "").strip() for alpha_id in (alpha_ids or [])]
        if not ids:
            return []
        worker_count = _bounded_concurrency(concurrency)
        results: list[dict[str, Any] | None] = [None] * len(ids)
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                executor.submit(self._check_one_alpha_id, index, alpha_id, return_exceptions=return_exceptions): index
                for index, alpha_id in enumerate(ids)
            }
            for future in as_completed(futures):
                index = futures[future]
                try:
                    results[index] = future.result(timeout=timeout)
                except FuturesTimeoutError:
                    future.cancel()
                    timeout_exc = FuturesTimeoutError(f"check timed out after {timeout}s")
                    results[index] = timeout_exc if return_exceptions else {
                        "ok": False,
                        "index": index,
                        "alpha_id": ids[index],
                        "status": "TIMEOUT",
                        "complete": False,
                        "error": f"check timed out after {timeout}s",
                    }
                except Exception as exc:  # pragma: no cover - defensive; worker already wraps expected failures
                    results[index] = exc if return_exceptions else {
                        "ok": False,
                        "index": index,
                        "alpha_id": ids[index],
                        "status": "ERROR",
                        "complete": False,
                        "error": str(_scrub(str(exc))),
                    }
        return [row or {"ok": False, "index": index, "alpha_id": ids[index], "status": "ERROR", "complete": False, "error": "missing result"} for index, row in enumerate(results)]

    def _simulate_one_alpha_payload(
        self,
        index: int,
        row: dict[str, Any] | tuple[str, dict[str, Any]],
        *,
        return_exceptions: bool = False,
    ) -> dict[str, Any]:
        try:
            expression, settings = _simulation_input(row)
            simulation_id = self.submit_simulation(expression, settings)
            status = self.poll_until_complete(simulation_id)
            result = self.fetch_result(simulation_id) if status == "COMPLETED" else {}
            return {
                "ok": status == "COMPLETED",
                "index": index,
                "status": status,
                "simulation_id": simulation_id,
                "expression": expression,
                "result": result,
            }
        except Exception as exc:
            if return_exceptions:
                raise
            return {
                "ok": False,
                "index": index,
                "status": "ERROR",
                "error": str(_scrub(str(exc))),
            }

    def _check_one_alpha_id(self, index: int, alpha_id: str, *, return_exceptions: bool = False) -> dict[str, Any]:
        try:
            check = self.check_alpha(alpha_id)
            return {
                "ok": check.get("status") == "PASSED" and check.get("complete") is True,
                "index": index,
                "alpha_id": alpha_id,
                **check,
            }
        except Exception as exc:
            if return_exceptions:
                raise
            return {
                "ok": False,
                "index": index,
                "alpha_id": alpha_id,
                "status": "ERROR",
                "complete": False,
                "error": str(_scrub(str(exc))),
            }

    def submit_alpha(self, alpha_id: str, expression: str, settings: dict, *, bodyless: bool = True) -> dict:
        import logging as _logging

        _submit_log = _logging.getLogger("brain_alpha_ops.brain_api.submit")

        # ── Guard integrity check ───────────────────────────────────────
        # Verify the runtime_constants module hasn't been tampered with.
        # Fail-closed: if we can't verify, block the submission.
        # Uses hash-based verification so monkeypatching the sentinel string
        # alone is insufficient — the attacker must also override the hash
        # comparison function.
        _verify_submit_guard(_submit_log)

        # ── Standard guard check ────────────────────────────────────────
        from ...runtime_constants import REAL_SUBMIT_DISABLED_WEB_FLOW, real_submit_test_override_enabled
        force_real_submit = real_submit_test_override_enabled()
        if REAL_SUBMIT_DISABLED_WEB_FLOW and not force_real_submit:
            _submit_log.warning(
                "submit_alpha() blocked: REAL_SUBMIT_DISABLED_WEB_FLOW=True, "
                "force_real_submit=%s, alpha_id=%s",
                force_real_submit, alpha_id,
            )
            raise BrainAPIError(
                "REAL_SUBMIT_DISABLED_WEB_FLOW: official submit_alpha() is blocked at the API layer. "
                "Use the web console's pre-submit review + independent approval path. "
                "Tests can bypass only with explicit test approval env."
            )
        _submit_log.info(
            "submit_alpha() guard passed — proceeding with submission: alpha_id=%s, bodyless=%s",
            alpha_id, bodyless,
        )
        if not alpha_id or not str(alpha_id).strip():
            raise BrainAPIError("cannot submit alpha without a valid alpha_id")
        if bodyless is not True:
            raise BrainAPIError("official alpha submit requests must be bodyless; expression/settings stay in the local ledger")
        if _looks_non_production_alpha_id(alpha_id):
            raise BrainAPIError(f"refusing to submit non-production alpha_id through OfficialBrainAPI: {alpha_id}")
        check = self.check_alpha(alpha_id)
        if check["status"] != "PASSED" or check.get("complete") is not True:
            raise BrainAPIError(f"official pre-submit check failed: {check}")
        path = self.config.alpha_submit_path_template.format(alpha_id=alpha_id)
        data, _headers = self._request(
            "POST",
            path,
            body=None,
        )
        submit_check = _check_result_from_response(data)
        if submit_check["checks"] and submit_check["status"] != "PASSED":
            raise BrainAPIError(f"official submit response check failed: {submit_check}")
        response_status = str(_first_value(data, ["status", "state", "result"], "") or "").upper()
        if response_status in _CHECK_FAIL_STATES or response_status in _CHECK_PENDING_STATES:
            raise BrainAPIError(f"official submit response not final success: {_scrub(data)}")
        return {
            "status": response_status or "SUBMITTED",
            "alpha_id": alpha_id,
            "pre_submit_check": check,
            "submit_check": submit_check if submit_check["checks"] else {},
            "request_body_sent": not bodyless,
            "raw": _scrub(data),
        }

    def check_prod_correlation(self, expression: str, settings: dict | None = None) -> dict:
        # F-012: fail-closed — API failure must propagate, not be swallowed
        # into a warning dict. Returning a warning let callers treat the
        # prod-correlation gate as passing when the check was actually
        # unavailable, which is unsafe for a submission gate.
        body: dict[str, object] = {"expression": expression}
        if settings:
            body["settings"] = settings
        data, _headers = self._request(
            "POST",
            self.config.alpha_correlations_path,
            body=body,
        )
        max_corr = _first_value(
            data,
            ["maxCorrelation", "max_correlation", "prodCorrelation", "prod_correlation"],
            None,
        )
        related = data.get("relatedAlphas") or data.get("related_alphas") or data.get("alphas")
        return {
            "status": "ok",
            "max_correlation": abs(float(max_corr)) if max_corr is not None else None,
            "related_alphas": related if isinstance(related, list) else None,
            "warning": None,
        }

    def poll_until_complete(self, simulation_id: str, *, stop_check: Callable[[], bool] | None = None) -> str:
        """Poll simulation until COMPLETED, FAILED, or TIMEOUT.

        P1-3: accepts optional stop_check callable. When provided, the polling
        loop calls stop_check() before each poll attempt and returns
        "STOPPED" if it returns True.
        """
        for _attempt in range(self.config.poll_attempts):
            if stop_check is not None and stop_check():
                return "STOPPED"
            self._throttle()
            status, retry_after_seconds = self._poll_simulation_once(simulation_id)
            if status in {"COMPLETED", "FAILED"}:
                return status
            sleep_seconds = retry_after_seconds if retry_after_seconds is not None else self.config.poll_interval_seconds
            time.sleep(max(0.0, float(sleep_seconds)))
        return "TIMEOUT"
