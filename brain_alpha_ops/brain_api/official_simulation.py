"""Simulation and submission methods for the official BRAIN API adapter."""

from __future__ import annotations

import time
import urllib.parse

from .base import BrainAPIError
from .official_helpers import (
    _first_value,
    build_official_url,
    build_simulation_payload,
    items as _items,
    looks_non_production_alpha_id as _looks_non_production_alpha_id,
    merge_payloads as _merge,
    normalize_metrics,
    scrub as _scrub,
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
        data, _headers = self._request("GET", simulation_id)
        status = str(_first_value(data, ["status", "state"], "")).upper()
        if status in {"COMPLETE", "COMPLETED", "DONE"} or _first_value(data, ["alpha", "alpha_id", "alphaId"], ""):
            return "COMPLETED"
        if status in {"FAILED", "ERROR"}:
            return "FAILED"
        return "RUNNING"

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
        failed = [
            item
            for item in (_items(data) or _first_value(data, ["checks"], []))
            if isinstance(item, dict)
            and str(_first_value(item, ["status", "result"], "")).upper() in {"FAIL", "FAILED"}
        ]
        return {"status": "FAILED" if failed else "PASSED", "failed_checks": failed, "raw": _scrub(data)}

    def submit_alpha(self, alpha_id: str, expression: str, settings: dict) -> dict:
        if not alpha_id or not str(alpha_id).strip():
            raise BrainAPIError("cannot submit alpha without a valid alpha_id")
        if _looks_non_production_alpha_id(alpha_id):
            raise BrainAPIError(f"refusing to submit non-production alpha_id through OfficialBrainAPI: {alpha_id}")
        check = self.check_alpha(alpha_id)
        if check["status"] != "PASSED":
            raise BrainAPIError(f"official pre-submit check failed: {check}")
        path = self.config.alpha_submit_path_template.format(alpha_id=alpha_id)
        data, _headers = self._request(
            "POST",
            path,
            body={"alpha_id": alpha_id, "expression": expression, "settings": settings},
        )
        return {
            "status": str(_first_value(data, ["status", "state"], "SUBMITTED")).upper(),
            "alpha_id": alpha_id,
            "pre_submit_check": check,
            "raw": _scrub(data),
        }

    def check_prod_correlation(self, expression: str, settings: dict | None = None) -> dict:
        body: dict[str, object] = {"expression": expression}
        if settings:
            body["settings"] = settings
        try:
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
        except BrainAPIError as exc:
            return {
                "status": "error",
                "max_correlation": None,
                "related_alphas": None,
                "warning": f"PROD_CORRELATION API check unavailable: {exc}",
            }

    def poll_until_complete(self, simulation_id: str) -> str:
        for _attempt in range(self.config.poll_attempts):
            self._throttle()
            status = self.poll_simulation(simulation_id)
            if status in {"COMPLETED", "FAILED"}:
                return status
            time.sleep(self.config.poll_interval_seconds)
        return "TIMEOUT"
