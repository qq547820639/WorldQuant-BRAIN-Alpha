"""BrainAPIBridge — wraps an AlphaExecutionBackend to satisfy the BrainAPI Protocol.

This bridge allows the pipeline to transparently use any execution backend
(browser or API) through the same ``api: BrainAPI`` interface it already expects.
"""

from __future__ import annotations

import logging
from typing import Any

from brain_alpha_ops.brain_api.base import BrainAPI, BrainAPIError
from brain_alpha_ops.execution_backend import AlphaExecutionBackend

logger = logging.getLogger(__name__)


class BrainAPIBridge:
    """Adapts AlphaExecutionBackend to the BrainAPI Protocol.

    Delegates simulation/check/submit to the execution backend.
    Data-fetching methods (list_fields, search_*, etc.) delegate to the
    underlying API instance when available, or raise NotImplementedError
    for browser-only backends that don't support bulk data queries.
    """

    def __init__(self, backend: AlphaExecutionBackend, *, api: Any = None):
        """Args:
            backend: The execution backend to delegate to.
            api: Optional underlying BrainAPI for data-fetching methods
                (list_fields, search_*, filter_alphas, etc.). If None,
                data-fetching methods raise BrainAPIError.
        """
        self._backend = backend
        self._api = api
        self._authenticated = False

    # ---- BrainAPI Protocol: auth ----

    def authenticate(self, **kwargs) -> dict:
        import os
        credentials = {}
        if "username" in kwargs:
            credentials["username"] = kwargs["username"]
        if "password" in kwargs:
            credentials["password"] = kwargs["password"]
        if "token" in kwargs:
            credentials["token"] = kwargs["token"]
        # Fall back to environment variables if no credentials provided
        if not credentials:
            username = os.environ.get("BRAIN_USERNAME", "")
            password = os.environ.get("BRAIN_PASSWORD", "")
            token = os.environ.get("BRAIN_TOKEN", "")
            if username:
                credentials["username"] = username
            if password:
                credentials["password"] = password
            if token:
                credentials["token"] = token
        result = self._backend.authenticate(credentials)
        self._authenticated = result.get("ok", False)
        if not self._authenticated:
            raise BrainAPIError(result.get("error", "Authentication failed"), error_code="AUTH_INVALID")
        return result

    # ---- BrainAPI Protocol: simulation ----

    def submit_simulation(self, expression: str, settings: dict) -> str:
        result = self._backend.simulate_alpha(expression, settings)
        if not result.get("ok"):
            raise BrainAPIError(result.get("error", "Simulation failed"))
        return result.get("simulation_id", result.get("results", {}).get("simulationId", ""))

    def poll_simulation(self, simulation_id: str) -> str:
        if self._api is not None and hasattr(self._api, "poll_simulation"):
            return self._api.poll_simulation(simulation_id)
        raise BrainAPIError("poll_simulation not supported by browser backend")

    def fetch_result(self, simulation_id: str) -> dict:
        if self._api is not None and hasattr(self._api, "fetch_result"):
            return self._api.fetch_result(simulation_id)
        raise BrainAPIError("fetch_result not supported by browser backend")

    def concurrent_simulate(self, alphas, concurrency: int = 3, *, return_exceptions: bool = False) -> list:
        results = []
        for alpha in alphas:
            try:
                expr = alpha.expression if hasattr(alpha, "expression") else alpha.get("expression", "")
                settings = alpha.settings if hasattr(alpha, "settings") else alpha.get("settings", {})
                r = self._backend.simulate_alpha(expr, settings)
                results.append(r)
            except Exception as e:
                if return_exceptions:
                    results.append(e)
                else:
                    raise
        return results

    # ---- BrainAPI Protocol: check ----

    def check_alpha(self, alpha_id: str) -> dict:
        result = self._backend.check_alpha(alpha_id)
        if not result.get("ok"):
            raise BrainAPIError(result.get("error", "Check failed"))
        return result

    def concurrent_check(self, alpha_ids, concurrency: int = 3, *, return_exceptions: bool = False) -> list:
        results = []
        for alpha_id in alpha_ids:
            try:
                r = self._backend.check_alpha(alpha_id)
                results.append(r)
            except Exception as e:
                if return_exceptions:
                    results.append(e)
                else:
                    raise
        return results

    # ---- BrainAPI Protocol: submit ----

    def submit_alpha(self, alpha_id: str, expression: str, settings: dict, *, bodyless: bool = True) -> dict:
        result = self._backend.submit_alpha(alpha_id)
        if not result.get("ok"):
            raise BrainAPIError(result.get("error", "Submit failed"))
        return result

    # ---- BrainAPI Protocol: data queries (delegate to underlying API) ----

    def _require_api(self, method: str):
        if self._api is None:
            raise BrainAPIError(
                f"{method} requires an underlying API instance. "
                "Use 'api' or 'auto' execution mode for data queries."
            )
        return self._api

    def get_user_profile(self) -> dict:
        return self._require_api("get_user_profile").get_user_profile()

    def list_fields(self, query: str = "all", region: str = "", dataset: str = "", progress_callback=None) -> list[dict]:
        return self._require_api("list_fields").list_fields(query, region, dataset, progress_callback)

    def list_datasets(self, query: str = "all", region: str = "", progress_callback=None) -> list[dict]:
        return self._require_api("list_datasets").list_datasets(query, region, progress_callback)

    def list_operators(self, query: str = "all", progress_callback=None) -> list[dict]:
        return self._require_api("list_operators").list_operators(query, progress_callback)

    def list_data_categories(self, progress_callback=None) -> list[dict]:
        return self._require_api("list_data_categories").list_data_categories(progress_callback)

    def search_datasets_limited(self, query: str = "all", region: str = "", *, limit: int = 50, offset: int = 0, **filters) -> dict:
        return self._require_api("search_datasets_limited").search_datasets_limited(query, region, limit=limit, offset=offset, **filters)

    def search_datasets(self, query: str = "all", region: str = "", *, limit: int = 50, offset: int = 0, progress_callback=None, **filters) -> list[dict]:
        return self._require_api("search_datasets").search_datasets(query, region, limit=limit, offset=offset, progress_callback=progress_callback, **filters)

    def search_fields_limited(self, query: str = "all", region: str = "", dataset: str = "", *, limit: int = 50, offset: int = 0, **filters) -> dict:
        return self._require_api("search_fields_limited").search_fields_limited(query, region, dataset, limit=limit, offset=offset, **filters)

    def search_fields(self, query: str = "all", region: str = "", dataset: str = "", *, limit: int = 50, offset: int = 0, progress_callback=None, **filters) -> list[dict]:
        return self._require_api("search_fields").search_fields(query, region, dataset, limit=limit, offset=offset, progress_callback=progress_callback, **filters)

    def locate_dataset(self, dataset_id: str) -> dict:
        return self._require_api("locate_dataset").locate_dataset(dataset_id)

    def locate_field(self, field_id: str) -> dict:
        return self._require_api("locate_field").locate_field(field_id)

    def locate_alpha(self, alpha_id: str) -> dict:
        return self._require_api("locate_alpha").locate_alpha(alpha_id)

    def filter_alphas_limited(self, **filters) -> dict:
        return self._require_api("filter_alphas_limited").filter_alphas_limited(**filters)

    def filter_alphas(self, progress_callback=None, **filters) -> list[dict]:
        return self._require_api("filter_alphas").filter_alphas(progress_callback=progress_callback, **filters)

    def list_user_alphas(self, sync_range: str = "all", progress_callback=None, *, force_refresh: bool = False) -> list[dict]:
        return self._require_api("list_user_alphas").list_user_alphas(sync_range, progress_callback, force_refresh=force_refresh)

    def validate_expression(self, expression: str, settings: dict) -> dict:
        if self._api is not None and hasattr(self._api, "validate_expression"):
            return self._api.validate_expression(expression, settings)
        raise BrainAPIError("validate_expression not supported by browser backend")
