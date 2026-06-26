"""Main ``OfficialBrainAPI`` adapter class.

Composition file: combines the auth, simulation, and data-access mixins
with the core ``__init__``/property/utility methods on this class.
"""

from __future__ import annotations
from dataclasses import asdict

import http.cookiejar
import logging
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

from brain_alpha_ops.config import BrainSettings, OfficialAPIConfig
from brain_alpha_ops.secure_credentials import resolve_credentials

from ..cache import cache_key as _cache_key
from ..cache import cache_path as _cache_path
from ..cache import read_cache as _read_cache
from ..cache import write_cache as _write_cache
from ..official_validation import OfficialExpressionValidator
from ..pagination import (
    _standard_pagination_progress as _shared_standard_pagination_progress,
)
from ._helpers import (
    _OfficialAuthProfileClient,
    _OfficialContextDataClient,
    _OfficialRequestClient,
    _OfficialSimulationSubmissionClient,
)
from ._auth_mixin import _OfficialAuthMixin
from ._data_access_mixin import _OfficialDataAccessMixin
from ._simulation_mixin import _OfficialSimulationMixin

logger = logging.getLogger("brain_alpha_ops.brain_api.official")

# P2-2: removed the cross-instance _GLOBAL_LAST_REQUEST_AT / _GLOBAL_TIMESTAMP_LOCK
# pair.  Per-instance ``self._last_request_at`` is sufficient now that retry_delay
# uses exponential back-off with jitter; cross-process rate coordination is the
# BRAIN server's responsibility, not ours.
_standard_pagination_progress = _shared_standard_pagination_progress


# Backward-compat re-exports for Phase 3.x migration

class OfficialBrainAPI(_OfficialAuthMixin, _OfficialSimulationMixin, _OfficialDataAccessMixin):
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

    def set_market_scope(self, settings: BrainSettings | dict | None):
        # Keep dataset in the market scope so dataset selection continues to work.
        if isinstance(settings, BrainSettings):
            data = asdict(settings)
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
