"""Official BRAIN API adapter.

This adapter intentionally uses only standard-library HTTP helpers so the
project can run without dependency installation. Endpoint templates are
configurable because BRAIN API shapes may change.

Key types are defined in brain_alpha_ops.types:
- OfficialMetrics: Metrics from BRAIN simulation/check results
- BrainAPIResponse: Standard API response structure
- SimulationResult: Result from simulation polling
"""

from __future__ import annotations

import http.cookiejar
import logging
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

from brain_alpha_ops.config import BrainSettings, OfficialAPIConfig
from brain_alpha_ops.secure_credentials import resolve_credentials
from brain_alpha_ops.types import BrainAPIResponse

from .cache import cache_key as _cache_key
from .cache import cache_path as _cache_path
from .cache import read_cache as _read_cache
from .cache import write_cache as _write_cache
from .official_auth import OfficialAuthProfileMixin
from .official_context import OfficialContextDataMixin
from .official_request import OfficialRequestMixin
from .official_simulation import OfficialSimulationSubmissionMixin
from .official_validation import OfficialExpressionValidator
from .pagination import (

    _standard_pagination_progress as _shared_standard_pagination_progress,
)

logger = logging.getLogger(__name__)

# P2-2: removed the cross-instance _GLOBAL_LAST_REQUEST_AT / _GLOBAL_TIMESTAMP_LOCK
# pair.  Per-instance ``self._last_request_at`` is sufficient now that retry_delay
# uses exponential back-off with jitter; cross-process rate coordination is the
# BRAIN server's responsibility, not ours.
_standard_pagination_progress = _shared_standard_pagination_progress


class _BoundOfficialAPIComponent:
    def __init__(self, api: "OfficialBrainAPI"):
        object.__setattr__(self, "_api", api)

    def __getattr__(self, name: str) -> Any:
        try:
            api = object.__getattribute__(self, "_api")
        except AttributeError as exc:
            raise AttributeError(name) from exc
        return getattr(api, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_api":
            object.__setattr__(self, name, value)
            return
        setattr(self._api, name, value)


class _OfficialAuthProfileClient(OfficialAuthProfileMixin, _BoundOfficialAPIComponent):
    pass


class _OfficialContextDataClient(OfficialContextDataMixin, _BoundOfficialAPIComponent):
    pass


class _OfficialRequestClient(OfficialRequestMixin, _BoundOfficialAPIComponent):
    pass


class _OfficialSimulationSubmissionClient(OfficialSimulationSubmissionMixin, _BoundOfficialAPIComponent):
    pass


# Backward-compat re-exports for Phase 3.x migration

class OfficialBrainAPI:
    """Main interface for WorldQuant BRAIN API operations.

    This class provides a complete API client for interacting with the
    WorldQuant BRAIN platform, including authentication, data discovery,
    alpha management, simulation, and submission.

    Usage:
        api = OfficialBrainAPI(token="your_token")
        api.authenticate()
        fields = api.list_fields()
        result = api.submit_simulation("rank(close)", settings)

    Attributes:
        config: API configuration (endpoints, timeouts, cache settings)
        username: BRAIN account username
        password: BRAIN account password (never stored on disk)
        token: BRAIN API token for authentication
    """

    def __init__(
        self,
        config: OfficialAPIConfig | None = None,
        *,
        username: str = "",
        password: str = "",
        token: str = "",
        disable_proxy: bool = False,
    ):
        self.config = config or OfficialAPIConfig()
        self._credentials = resolve_credentials(username=username, password=password, token=token)
        self._cookie_jar = http.cookiejar.CookieJar()
        opener_handlers: list[Any] = [urllib.request.HTTPCookieProcessor(self._cookie_jar)]
        if disable_proxy:
            opener_handlers.insert(0, urllib.request.ProxyHandler({}))
        self._opener = urllib.request.build_opener(*opener_handlers)
        default_scope = BrainSettings()
        self._market_scope = {
            "instrumentType": default_scope.instrumentType,
            "region": default_scope.region,
            "delay": int(default_scope.delay),
            "universe": default_scope.universe,
            "dataset": default_scope.dataset,  # P1 fix: include dataset
        }
        self._prefer_cookie_auth = False
        self._last_request_at = 0.0
        self._request_lock = threading.RLock()
        self._cache_lock = threading.Lock()
        self._auth_profile = _OfficialAuthProfileClient(self)
        self._context_data = _OfficialContextDataClient(self)
        self._request_client = _OfficialRequestClient(self)
        self._simulation_submission = _OfficialSimulationSubmissionClient(self)
        self._expression_validator = OfficialExpressionValidator()

    @property
    def username(self) -> str:
        return self._credentials.username

    @username.setter
    def username(self, value: str) -> None:
        self._credentials.username = value or ""

    @property
    def password(self) -> str:
        return self._credentials.password

    @password.setter
    def password(self, value: str) -> None:
        self._credentials.password = value or ""

    @property
    def token(self) -> str:
        return self._credentials.token

    @token.setter
    def token(self, value: str) -> None:
        self._credentials.token = value or ""

    def validate_expression(
        self,
        expression: str,
        settings: dict,
        known_operators: set | None = None,
        known_fields: set | None = None,
    ) -> dict:
        return self._expression_validator.validate_expression(
            expression,
            settings,
            known_operators=known_operators,
            known_fields=known_fields,
        )

    def authenticate(self) -> dict:
        return self._auth_profile.authenticate()

    def get_user_profile(self) -> dict:
        return self._auth_profile.get_user_profile()

    def _basic_auth(self) -> str:
        return self._auth_profile._basic_auth()

    def _has_session_cookie(self) -> bool:
        return self._auth_profile._has_session_cookie()

    def _request(
        self,
        method: str,
        path_or_url: str,
        *,
        body: dict | None = None,
        query: dict | None = None,
        headers: dict | None = None,
        allow_auth_retry: bool = True,
    ) -> tuple[Any, dict]:
        return self._request_client._request(
            method,
            path_or_url,
            body=body,
            query=query,
            headers=headers,
            allow_auth_retry=allow_auth_retry,
        )

    def list_fields(
        self,
        query: str = "all",
        region: str = "",
        dataset: str = "",
        progress_callback=None,
    ) -> list[dict]:
        """List all available data fields from BRAIN platform.

        Args:
            query: Search query (default: "all" for all fields)
            region: Geographic region filter (e.g., "USA", "JAPAN")
            dataset: Dataset ID filter
            progress_callback: Optional callback for pagination progress

        Returns:
            List of field dictionaries with id, name, category, etc.
        """
        return self._context_data.list_fields(
            query,
            region,
            dataset=dataset,
            progress_callback=progress_callback,
        )

    def list_datasets(
        self,
        query: str = "all",
        region: str = "",
        progress_callback=None,
    ) -> list[dict]:
        return self._context_data.list_datasets(query, region, progress_callback=progress_callback)

    def list_operators(self, query: str = "all", progress_callback=None) -> list[dict]:
        return self._context_data.list_operators(query, progress_callback=progress_callback)

    def list_data_categories(self, progress_callback=None) -> list[dict]:
        return self._context_data.list_data_categories(progress_callback=progress_callback)

    def search_datasets_limited(
        self,
        query: str = "all",
        region: str = "",
        *,
        limit: int = 50,
        offset: int = 0,
        **filters,
    ) -> dict:
        return self._context_data.search_datasets_limited(
            query,
            region,
            **filters,
            limit=limit,
            offset=offset,
        )

    def discover_datasets_limited(
        self,
        query: str = "all",
        region: str = "",
        *,
        options: dict[str, Any] | None = None,
        **filters,
    ) -> dict:
        return self._context_data.discover_datasets_limited(
            query,
            region,
            options=options,
            **filters,
        )

    def search_datasets(
        self,
        query: str = "all",
        region: str = "",
        *,
        limit: int = 50,
        offset: int = 0,
        progress_callback=None,
        **filters,
    ) -> list[dict]:
        return self._context_data.search_datasets(
            query,
            region,
            **filters,
            limit=limit,
            offset=offset,
            progress_callback=progress_callback,
        )

    def discover_datasets(
        self,
        query: str = "all",
        region: str = "",
        *,
        options: dict[str, Any] | None = None,
        progress_callback=None,
        **filters,
    ) -> list[dict]:
        return self._context_data.discover_datasets(
            query,
            region,
            options=options,
            progress_callback=progress_callback,
            **filters,
        )

    def search_fields_limited(
        self,
        query: str = "all",
        region: str = "",
        dataset: str = "",
        *,
        limit: int = 50,
        offset: int = 0,
        **filters,
    ) -> dict:
        return self._context_data.search_fields_limited(
            query,
            region,
            dataset=dataset,
            **filters,
            limit=limit,
            offset=offset,
        )

    def discover_fields_limited(
        self,
        query: str = "all",
        region: str = "",
        dataset: str = "",
        *,
        dataset_id: str = "",
        options: dict[str, Any] | None = None,
        **filters,
    ) -> dict:
        return self._context_data.discover_fields_limited(
            query,
            region,
            dataset=dataset,
            dataset_id=dataset_id,
            options=options,
            **filters,
        )

    def search_fields(
        self,
        query: str = "all",
        region: str = "",
        dataset: str = "",
        *,
        limit: int = 50,
        offset: int = 0,
        progress_callback=None,
        **filters,
    ) -> list[dict]:
        return self._context_data.search_fields(
            query,
            region,
            dataset=dataset,
            **filters,
            limit=limit,
            offset=offset,
            progress_callback=progress_callback,
        )

    def discover_fields(
        self,
        query: str = "all",
        region: str = "",
        dataset: str = "",
        *,
        dataset_id: str = "",
        options: dict[str, Any] | None = None,
        progress_callback=None,
        **filters,
    ) -> list[dict]:
        return self._context_data.discover_fields(
            query,
            region,
            dataset=dataset,
            dataset_id=dataset_id,
            options=options,
            progress_callback=progress_callback,
            **filters,
        )

    def locate_dataset(self, dataset_id: str) -> dict:
        return self._context_data.locate_dataset(dataset_id)

    def locate_field(self, field_id: str) -> dict:
        return self._context_data.locate_field(field_id)

    def locate_alpha(self, alpha_id: str) -> dict:
        return self._context_data.locate_alpha(alpha_id)

    def get_dataset(self, dataset_id: str = "", *, id: str = "") -> dict:
        return self._context_data.get_dataset(dataset_id, id=id)

    def get_field(self, field_id: str = "", *, id: str = "") -> dict:
        return self._context_data.get_field(field_id, id=id)

    def get_alpha(self, alpha_id: str = "", *, id: str = "") -> dict:
        return self._context_data.get_alpha(alpha_id, id=id)

    def filter_alphas_limited(self, **filters) -> dict:
        return self._context_data.filter_alphas_limited(**filters)

    def query_alphas_limited(self, *, options: dict[str, Any] | None = None, **filters) -> dict:
        return self._context_data.query_alphas_limited(options=options, **filters)

    def filter_alphas(self, progress_callback=None, **filters) -> list[dict]:
        return self._context_data.filter_alphas(progress_callback=progress_callback, **filters)

    def patch_properties(
        self,
        alpha_id: str,
        *,
        name: str | None = None,
        alpha_type: str | None = None,
        decay: int | None = None,
        neutralization: str | None = None,
        pasteurization: str | None = None,
        truncation: Any = None,
        unit_handling: str | None = None,
        nan_handling: str | None = None,
        hidden: bool | None = None,
        favorite: bool | None = None,
        category: str | None = None,
        color: str | None = None,
        tag: str | None = None,
        stage: str | None = None,
        **extra: Any,
    ) -> dict:
        return self._context_data.patch_properties(
            alpha_id,
            name=name,
            alpha_type=alpha_type,
            decay=decay,
            neutralization=neutralization,
            pasteurization=pasteurization,
            truncation=truncation,
            unit_handling=unit_handling,
            nan_handling=nan_handling,
            hidden=hidden,
            favorite=favorite,
            category=category,
            color=color,
            tag=tag,
            stage=stage,
            **extra,
        )

    def query_alphas(
        self,
        progress_callback=None,
        *,
        options: dict[str, Any] | None = None,
        **filters,
    ) -> list[dict]:
        return self._context_data.query_alphas(
            progress_callback=progress_callback,
            options=options,
            **filters,
        )

    def list_user_alphas(
        self,
        sync_range: str = "all",
        progress_callback=None,
        *,
        force_refresh: bool = False,
    ) -> list[dict]:
        return self._context_data.list_user_alphas(
            sync_range,
            progress_callback=progress_callback,
            force_refresh=force_refresh,
        )

    def submit_simulation(self, expression: str, settings: dict) -> str:
        """Submit an alpha expression for simulation.

        Args:
            expression: Alpha expression (e.g., "rank(ts_delta(close, 20))")
            settings: Simulation settings (region, delay, universe, etc.)

        Returns:
            Simulation ID for polling results

        Raises:
            BrainAPIError: If submission fails
        """
        return self._simulation_submission.submit_simulation(expression, settings)

    def poll_simulation(self, simulation_id: str) -> str:
        """Poll simulation status once.

        Args:
            simulation_id: ID from submit_simulation()

        Returns:
            Status string: "RUNNING", "COMPLETED", or "FAILED"
        """
        return self._simulation_submission.poll_simulation(simulation_id)

    def fetch_result(self, simulation_id: str) -> BrainAPIResponse:
        """Fetch simulation results after completion.

        Args:
            simulation_id: ID from submit_simulation()

        Returns:
            BrainAPIResponse with simulation_id, alpha_id, metrics, and raw data
        """
        return self._simulation_submission.fetch_result(simulation_id)

    def concurrent_simulate(self, alphas, concurrency: int = 3, *, return_exceptions: bool = False) -> list:
        """Simulate multiple alphas concurrently.

        Args:
            alphas: List of (expression, settings) tuples or dicts
            concurrency: Max concurrent simulations
            return_exceptions: If True, return exceptions instead of raising

        Returns:
            List of simulation results
        """
        return self._simulation_submission.concurrent_simulate(
            alphas,
            concurrency=concurrency,
            return_exceptions=return_exceptions,
        )

    def concurrent_check(self, alpha_ids, concurrency: int = 3, *, return_exceptions: bool = False) -> list:
        return self._simulation_submission.concurrent_check(
            alpha_ids,
            concurrency=concurrency,
            return_exceptions=return_exceptions,
        )

    def check_alpha(self, alpha_id: str) -> BrainAPIResponse:
        """Check alpha submission readiness.

        Args:
            alpha_id: BRAIN alpha ID

        Returns:
            BrainAPIResponse with status ("PASSED"/"FAILED"), checks, and details
        """
        return self._simulation_submission.check_alpha(alpha_id)

    def submit_alpha(self, alpha_id: str, expression: str, settings: dict, *, bodyless: bool = True) -> BrainAPIResponse:
        """Submit alpha to BRAIN platform.

        WARNING: This performs a REAL submission. In production, use the
        web console's pre-submit review + HIL confirmation flow instead.

        Args:
            alpha_id: BRAIN alpha ID
            expression: Alpha expression
            settings: Submission settings
            bodyless: Must be True (body sent via pre-submit check)

        Returns:
            BrainAPIResponse with submission status and details

        Raises:
            BrainAPIError: If submission is blocked or fails
        """
        return self._simulation_submission.submit_alpha(alpha_id, expression, settings, bodyless=bodyless)

    def check_prod_correlation(
        self,
        expression: str,
        settings: dict | None = None,
    ) -> dict:
        """Check correlation with existing production alphas.

        Args:
            expression: Alpha expression to check
            settings: Optional settings override

        Returns:
            Dict with max_correlation, related_alphas, warning
        """
        return self._simulation_submission.check_prod_correlation(expression, settings)

    def poll_until_complete(self, simulation_id: str) -> str:
        """Poll simulation until completion or timeout.

        Args:
            simulation_id: ID from submit_simulation()

        Returns:
            "COMPLETED", "FAILED", or "TIMEOUT"
        """
        return self._simulation_submission.poll_until_complete(simulation_id)

    def set_market_scope(self, settings: BrainSettings | dict | None):
        # Keep dataset in the market scope so dataset selection continues to work.
        if isinstance(settings, BrainSettings):
            data = settings.__dict__
        elif isinstance(settings, dict):
            data = settings
        else:
            data = {}
        self._market_scope = {
            "instrumentType": str(data.get("instrumentType", self._market_scope.get("instrumentType", "EQUITY"))),
            "region": str(data.get("region", self._market_scope.get("region", "USA"))),
            "delay": int(data.get("delay", self._market_scope.get("delay", 1))),
            "universe": str(data.get("universe", self._market_scope.get("universe", "TOP3000"))),
            "dataset": str(data.get("dataset", self._market_scope.get("dataset", ""))),  # P1 fix
        }

    def _throttle(self):
        interval = max(0.0, float(self.config.min_request_interval_seconds))
        if interval <= 0:
            return
        with self._request_lock:
            now = time.monotonic()
            elapsed = now - self._last_request_at
            wait_time = max(0.0, interval - elapsed)
            # Pre-reserve the slot so concurrent threads see the updated time.
            self._last_request_at = now + wait_time
        if wait_time > 0:
            time.sleep(wait_time)

    def _open(self, req: urllib.request.Request, *, timeout: int):
        return self._opener.open(req, timeout=timeout)

    def _cache_key(self, kind: str, params: dict) -> str:
        return _cache_key(kind, params)

    def _cache_path(self, name: str) -> Path:
        return _cache_path(self.config, name)

    def _read_cache(self, name: str) -> dict:
        return _read_cache(
            self.config,
            name,
            cache_path_builder=lambda _config, cache_name: self._cache_path(cache_name),
            log=logger,
            cache_lock=self._cache_lock,
        )

    def _write_cache(self, name: str, items: list[dict], total: int = 0):
        return _write_cache(
            self.config,
            self._cache_lock,
            name,
            items,
            total,
            cache_path_builder=lambda _config, cache_name: self._cache_path(cache_name),
            log=logger,
        )



# ---- Backward-compat re-export for Phase 3.x migration ----
from .official_helpers import build_simulation_payload, looks_non_production_alpha_id as _looks_non_production_alpha_id  # noqa: F401  # backward-compat re-export

from .official_helpers import normalize_metrics  # noqa: F401
from brain_alpha_ops.brain_api.base import BrainAPIError  # noqa: F401
