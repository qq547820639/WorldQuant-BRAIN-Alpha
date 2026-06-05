"""Official BRAIN API adapter.

This adapter intentionally uses only standard-library HTTP helpers so the
project can run without dependency installation. Endpoint templates are
configurable because BRAIN API shapes may change.
"""

from __future__ import annotations

import http.cookiejar
import logging
from pathlib import Path
import threading
import time
import urllib.request
from typing import Any

from brain_alpha_ops.config import BrainSettings, OfficialAPIConfig
from brain_alpha_ops.secure_credentials import resolve_credentials

from .base import BrainAPIError
from .official_auth import OfficialAuthProfileMixin
from .cache import cache_key as _cache_key
from .cache import cache_path as _cache_path
from .cache import read_cache as _read_cache
from .cache import write_cache as _write_cache
from .official_context import OfficialContextDataMixin
from .official_helpers import (
    build_simulation_payload,
    looks_non_production_alpha_id as _looks_non_production_alpha_id,
    normalize_metrics,
)
from .pagination import _standard_pagination_progress as _shared_standard_pagination_progress
from .official_request import OfficialRequestMixin
from .official_simulation import OfficialSimulationSubmissionMixin
from .official_validation import OfficialExpressionValidator


logger = logging.getLogger(__name__)

_GLOBAL_LAST_REQUEST_AT = 0.0  # shared timestamp for cross-instance rate awareness
_GLOBAL_TIMESTAMP_LOCK = threading.RLock()
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


class OfficialBrainAPI:
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
    ) -> tuple[Any, dict]:
        return self._request_client._request(
            method,
            path_or_url,
            body=body,
            query=query,
            headers=headers,
        )

    def list_fields(
        self,
        query: str = "all",
        region: str = "",
        dataset: str = "",
        progress_callback=None,
    ) -> list[dict]:
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

    def list_user_alphas(
        self,
        sync_range: str = "3d",
        progress_callback=None,
    ) -> list[dict]:
        return self._context_data.list_user_alphas(sync_range, progress_callback=progress_callback)

    def submit_simulation(self, expression: str, settings: dict) -> str:
        return self._simulation_submission.submit_simulation(expression, settings)

    def poll_simulation(self, simulation_id: str) -> str:
        return self._simulation_submission.poll_simulation(simulation_id)

    def fetch_result(self, simulation_id: str) -> dict:
        return self._simulation_submission.fetch_result(simulation_id)

    def check_alpha(self, alpha_id: str) -> dict:
        return self._simulation_submission.check_alpha(alpha_id)

    def submit_alpha(self, alpha_id: str, expression: str, settings: dict) -> dict:
        return self._simulation_submission.submit_alpha(alpha_id, expression, settings)

    def check_prod_correlation(
        self,
        expression: str,
        settings: dict | None = None,
    ) -> dict:
        return self._simulation_submission.check_prod_correlation(expression, settings)

    def poll_until_complete(self, simulation_id: str) -> str:
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
        global _GLOBAL_LAST_REQUEST_AT
        interval = max(0.0, float(self.config.min_request_interval_seconds))
        if interval <= 0:
            return
        # P1-1: Use a single global lock to prevent TOCTOU race.
        # Pre-reserve the next slot inside the lock, then sleep outside.
        wait_time = 0.0
        with _GLOBAL_TIMESTAMP_LOCK:
            now = time.monotonic()
            last_request_at = max(self._last_request_at, _GLOBAL_LAST_REQUEST_AT)
            elapsed = now - last_request_at
            if elapsed < interval:
                wait_time = interval - elapsed
            # Pre-reserve the slot so concurrent threads see the updated time.
            _GLOBAL_LAST_REQUEST_AT = now + wait_time
            self._last_request_at = _GLOBAL_LAST_REQUEST_AT
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
