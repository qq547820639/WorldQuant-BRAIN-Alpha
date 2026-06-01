"""Official BRAIN API adapter.

This adapter intentionally uses only standard-library HTTP helpers so the
project can run without dependency installation. Endpoint templates are
configurable because BRAIN API shapes may change.
"""

from __future__ import annotations

import http.cookiejar
import logging
import os
from pathlib import Path
import threading
import time
import urllib.request
from typing import Any

from brain_alpha_ops.config import BrainSettings, OfficialAPIConfig

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
from .official_validation import OfficialExpressionValidationMixin


logger = logging.getLogger(__name__)

# Pagination safety limits (M-07)
_MAX_FIELDS_PAGES = 200
_MAX_DATASETS_PAGES = 20
_MAX_OPERATORS_PAGES = 20
_MAX_USER_ALPHAS_PAGES = 500
_MAX_FIELDS_ITEMS = 20_000
_MAX_DATASETS_ITEMS = 2_000
_MAX_OPERATORS_ITEMS = 2_000

_GLOBAL_LAST_REQUEST_AT = 0.0  # shared timestamp for cross-instance rate awareness
_GLOBAL_TIMESTAMP_LOCK = threading.RLock()
_standard_pagination_progress = _shared_standard_pagination_progress


class OfficialBrainAPI(
    OfficialAuthProfileMixin,
    OfficialContextDataMixin,
    OfficialRequestMixin,
    OfficialExpressionValidationMixin,
    OfficialSimulationSubmissionMixin,
):
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
        self.username = username or os.getenv("BRAIN_USERNAME", "")
        self.password = password or os.getenv("BRAIN_PASSWORD", "")
        self.token = token or os.getenv("BRAIN_TOKEN", "")
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
        with self._request_lock:
            if interval <= 0:
                now = time.monotonic()
                with _GLOBAL_TIMESTAMP_LOCK:
                    _GLOBAL_LAST_REQUEST_AT = now
                self._last_request_at = now
                return
            with _GLOBAL_TIMESTAMP_LOCK:
                last_request_at = max(self._last_request_at, _GLOBAL_LAST_REQUEST_AT)
            elapsed = time.monotonic() - last_request_at
            if elapsed < interval:
                time.sleep(interval - elapsed)
            now = time.monotonic()
            self._last_request_at = now
            with _GLOBAL_TIMESTAMP_LOCK:
                _GLOBAL_LAST_REQUEST_AT = now

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
