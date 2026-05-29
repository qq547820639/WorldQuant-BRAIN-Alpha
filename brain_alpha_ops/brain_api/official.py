"""Official BRAIN API adapter.

This adapter intentionally uses only standard-library HTTP helpers so the
project can run without dependency installation. Endpoint templates are
configurable because BRAIN API shapes may change.
"""

from __future__ import annotations

import base64
import hashlib
import http.cookiejar
import json
import logging
import os
from pathlib import Path
import re
import threading
import time
import urllib.error
import urllib.request
from typing import Any

from brain_alpha_ops.config import BrainSettings, OfficialAPIConfig
from brain_alpha_ops.redaction import redact_error_message

from .base import BrainAPIError
from .official_helpers import (
    build_official_url,
    _first_value,
    build_simulation_payload,
    items as _items,
    looks_non_production_alpha_id as _looks_non_production_alpha_id,
    looks_partial_context_cache as _looks_partial_context_cache,
    merge_payloads as _merge,
    normal_alpha as _normal_alpha,
    normal_dataset as _normal_dataset,
    normal_field as _normal_field,
    normal_operator as _normal_operator,
    normalize_metrics,
    page_signature as _page_signature,
    parse_response as _parse,
    retry_after as _retry_after,
    retry_delay as _retry_delay,
    retryable_status as _retryable_status,
    scrub as _scrub,
    total_count as _total_count,
    dedupe_alpha_items as _dedupe_alpha_items,
    user_alpha_progress as _user_alpha_progress,
    user_alpha_offset_recovery as _user_alpha_offset_recovery,
)


logger = logging.getLogger(__name__)

# Pagination safety limits (M-07)
_MAX_FIELDS_PAGES = 200
_MAX_DATASETS_PAGES = 20
_MAX_OPERATORS_PAGES = 20
_MAX_FIELDS_ITEMS = 20_000
_MAX_DATASETS_ITEMS = 2_000
_MAX_OPERATORS_ITEMS = 2_000

_GLOBAL_LAST_REQUEST_AT = 0.0  # shared timestamp for cross-instance rate awareness
_GLOBAL_TIMESTAMP_LOCK = threading.RLock()


class OfficialBrainAPI:
    def __init__(
        self,
        config: OfficialAPIConfig | None = None,
        *,
        username: str = "",
        password: str = "",
        token: str = "",
    ):
        self.config = config or OfficialAPIConfig()
        self.username = username or os.getenv("BRAIN_USERNAME", "")
        self.password = password or os.getenv("BRAIN_PASSWORD", "")
        self.token = token or os.getenv("BRAIN_TOKEN", "")
        self._cookie_jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self._cookie_jar))
        default_scope = BrainSettings()
        self._market_scope = {
            "instrumentType": default_scope.instrumentType,
            "region": default_scope.region,
            "delay": int(default_scope.delay),
            "universe": default_scope.universe,
            "dataset": default_scope.dataset,  # P1 修复：添加 dataset 字段
        }
        self._prefer_cookie_auth = False
        self._last_request_at = 0.0
        self._request_lock = threading.RLock()
        self._cache_lock = threading.Lock()

    def set_market_scope(self, settings: BrainSettings | dict | None):
        # =========================================================================
        # P1 修复：添加 dataset 字段传递，确保数据集选择器正确工作
        # =========================================================================
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
            "dataset": str(data.get("dataset", self._market_scope.get("dataset", ""))),  # P1 修复
        }

    def authenticate(self) -> dict:
        if self.token and not (self.username and self.password):
            return {"status": "ok", "auth": "token"}
        if not self.username or not self.password:
            raise BrainAPIError("production mode requires BRAIN_USERNAME/BRAIN_PASSWORD or BRAIN_TOKEN")

        # Try Basic Auth first, fall back to JSON body on 401
        for method_name, build_request in [
            ("basic", lambda: (
                "POST", self.config.authentication_path,
                {"Authorization": f"Basic {base64.b64encode(f'{self.username}:{self.password}'.encode('utf-8')).decode('ascii')}"},
                None,  # no body
            )),
            ("json_body", lambda: (
                "POST", self.config.authentication_path,
                {"X-Auth-Mode": "json"},  # signal to _request to skip Basic auth header
                {"email": self.username, "password": self.password},  # try 'email' key (BRAIN API convention)
            )),
            ("json_body_username", lambda: (
                "POST", self.config.authentication_path,
                {"X-Auth-Mode": "json"},
                {"username": self.username, "password": self.password},
            )),
        ]:
            try:
                method, path, headers, body = build_request()
                data, _headers = self._request(method, path, headers=headers, body=body)
                token = _first_value(data, ["token", "access_token"], "")
                if token:
                    self.token = str(token)
                if self._has_session_cookie():
                    self._prefer_cookie_auth = True
                    return {"status": "ok", "auth": "session_cookie", "response": _scrub(data)}
                if token:
                    return {"status": "ok", "auth": "token", "response": _scrub(data)}
                # If we got a response but no token, try next method
            except BrainAPIError as exc:
                if exc.status_code in (401, 400):
                    continue  # try next auth method
                raise

        raise BrainAPIError("authentication did not provide token or session cookie; check credentials")

    def get_user_profile(self) -> dict:
        """Fetch current user profile from BRAIN /users/self endpoint.

        Returns user tier (e.g., Consultant, Pre-Consultant), level, points,
        and other profile fields as defined by the BRAIN API.

        The response is cached in memory for the session lifetime.

        Returns:
            {
                "tier": str,           # e.g. "Consultant", "Pre-Consultant"
                "level": int | None,   # consultant level (if applicable)
                "points": float | None, # accumulated points/score
                "username": str,       # user email/identifier
                "raw": dict,           # full API response (scrubbed)
           }
        """
        # Check cache
        if hasattr(self, '_cached_profile') and self._cached_profile:
            return self._cached_profile

        try:
            data, _headers = self._request("GET", self.config.user_profile_path)
        except BrainAPIError as exc:
            return {
                "error": f"Failed to fetch user profile: {exc}",
                "tier": "unknown",
                "level": None,
                "points": None,
                "username": self.username,
                "raw": {},
            }

        scrubbed = _scrub(data)
        # Extract profile fields — field names sourced from BRAIN platform conventions
        tier = str(_first_value(data,
            ["tier", "userTier", "tierName", "consultantTier", "accountType"], ""))
        level = _first_value(data,
            ["level", "userLevel", "consultantLevel", "currentLevel"], None)
        points = _first_value(data,
            ["points", "score", "totalPoints", "totalScore", "accumulatedPoints"], None)

        # IQC / beginner accounts have no tier — classify as "BASIC"
        if not tier or tier in ("unknown", "None", ""):
            genius = _first_value(data, ["geniusLevel"], None)
            if genius is not None:
                tier = f"IQC-{genius}"
            elif data.get("approved") and not data.get("tier"):
                tier = "BASIC"
            else:
                tier = "BASIC"

        # Account tier for runtime feature gating (SECTOR/MARKET neutralization etc)
        account_tier = "ADVANCED" if tier not in ("BASIC", "unknown", "") and "IQC" not in str(tier) else "BASIC"

        profile = {
            "tier": tier,
            "account_tier": account_tier,
            "level": int(level) if level is not None else None,
            "points": float(points) if points is not None else None,
            "username": str(_first_value(data,
                ["username", "email", "userEmail", "login"], self.username)),
            "raw": scrubbed,
        }
        self._cached_profile = profile
        return profile

    def list_fields(self, query: str = "all", region: str = "", dataset: str = "", progress_callback=None) -> list[dict]:
        scope_region = region or self._market_scope.get("region", "USA")
        params = {
            "instrumentType": self._market_scope.get("instrumentType", "EQUITY"),
            "region": scope_region,
            "delay": int(self._market_scope.get("delay", 1)),
            "universe": self._market_scope.get("universe", "TOP3000"),
            "limit": 50,
            "offset": 0,
        }
        if dataset or self._market_scope.get("dataset"):
            params["dataset"] = dataset or self._market_scope.get("dataset", "")
        if query and query != "all":
            params["search"] = query
        cache_key = self._cache_key("fields", params)
        cached = self._read_cache(cache_key)
        if cached["fresh"] and not _looks_partial_context_cache("fields", cached["items"], cached.get("total", 0), params["limit"]):
            if progress_callback:
                progress_callback({"scanned": len(cached["items"]), "total": cached.get("total") or len(cached["items"]), "cached": True})
            return cached["items"]
        try:
            items = []
            page_params = dict(params)
            total = 0
            seen_page_signatures: set[str] = set()
            for _page in range(1, _MAX_FIELDS_PAGES + 1):
                data, _headers = self._request("GET", self.config.data_fields_path, query=page_params)
                page_items = [_normal_field(item) for item in _items(data)]
                page_signature = _page_signature(page_items, keys=("name", "category"))
                if page_items and page_signature in seen_page_signatures:
                    logger.warning(
                        "fields pagination stopped on repeated page signature, offset=%s items=%d total=%d",
                        page_params.get("offset", 0),
                        len(items),
                        total,
                    )
                    if progress_callback:
                        progress_callback(
                            {
                                "scanned": len(items),
                                "total": total,
                                "page_size": len(page_items),
                                "offset": int(page_params.get("offset", 0)),
                                "truncated": True,
                                "warning": "repeated_page",
                            }
                        )
                    break
                if page_items:
                    seen_page_signatures.add(page_signature)
                items.extend(page_items)
                total = _total_count(data) or total
                if progress_callback:
                    progress_callback(
                        {
                            "scanned": len(items),
                            "total": total,
                            "page_size": len(page_items),
                            "offset": int(page_params.get("offset", 0)),
                        }
                    )
                if total and len(items) >= total:
                    break
                if len(items) >= _MAX_FIELDS_ITEMS:
                    logger.warning("fields pagination reached max item limit (%d), total=%d", _MAX_FIELDS_ITEMS, total)
                    items = items[:_MAX_FIELDS_ITEMS]
                    break
                if len(page_items) < int(page_params["limit"]):
                    break
                page_params["offset"] = int(page_params.get("offset", 0)) + int(page_params["limit"])
            else:
                logger.warning("fields pagination reached max pages limit (%d), items=%d total=%d", _MAX_FIELDS_PAGES, len(items), total)
            self._write_cache(cache_key, items, max(total, len(items)))
            return items
        except BrainAPIError as exc:
            if self.config.allow_stale_context_on_rate_limit and exc.status_code == 429 and cached["items"]:
                return cached["items"]
            raise

    def list_datasets(self, query: str = "all", region: str = "", progress_callback=None) -> list[dict]:
        """Fetch official BRAIN data sets from the published /data-sets API."""
        scope_region = region or self._market_scope.get("region", "USA")
        params = {
            "instrumentType": self._market_scope.get("instrumentType", "EQUITY"),
            "region": scope_region,
            "delay": int(self._market_scope.get("delay", 1)),
            "universe": self._market_scope.get("universe", "TOP3000"),
            "limit": 50,
            "offset": 0,
        }
        if query and query != "all":
            params["search"] = query
        cache_key = self._cache_key("datasets", params)
        cached = self._read_cache(cache_key)
        if cached["fresh"] and not _looks_partial_context_cache("datasets", cached["items"], cached.get("total", 0), params["limit"]):
            if progress_callback:
                progress_callback({"scanned": len(cached["items"]), "total": cached.get("total") or len(cached["items"]), "cached": True})
            return cached["items"]
        try:
            items = []
            page_params = dict(params)
            total = 0
            seen_page_signatures: set[str] = set()
            for _page in range(1, _MAX_DATASETS_PAGES + 1):
                data, _headers = self._request("GET", self.config.data_sets_path, query=page_params)
                page_items = [
                    row
                    for row in (_normal_dataset(item) for item in _items(data))
                    if row.get("id")
                ]
                page_signature = _page_signature(page_items, keys=("id", "name"))
                if page_items and page_signature in seen_page_signatures:
                    logger.warning(
                        "datasets pagination stopped on repeated page signature, offset=%s items=%d total=%d",
                        page_params.get("offset", 0),
                        len(items),
                        total,
                    )
                    if progress_callback:
                        progress_callback(
                            {
                                "scanned": len(items),
                                "total": total,
                                "page_size": len(page_items),
                                "offset": int(page_params.get("offset", 0)),
                                "truncated": True,
                                "warning": "repeated_page",
                            }
                        )
                    break
                if page_items:
                    seen_page_signatures.add(page_signature)
                items.extend(page_items)
                total = _total_count(data) or total
                if progress_callback:
                    progress_callback(
                        {
                            "scanned": len(items),
                            "total": total,
                            "page_size": len(page_items),
                            "offset": int(page_params.get("offset", 0)),
                        }
                    )
                if total and len(items) >= total:
                    break
                if len(items) >= _MAX_DATASETS_ITEMS:
                    logger.warning("datasets pagination reached max item limit (%d), total=%d", _MAX_DATASETS_ITEMS, total)
                    items = items[:_MAX_DATASETS_ITEMS]
                    break
                if len(page_items) < int(page_params["limit"]):
                    break
                page_params["offset"] = int(page_params.get("offset", 0)) + int(page_params["limit"])
            else:
                logger.warning("datasets pagination reached max pages limit (%d), items=%d total=%d", _MAX_DATASETS_PAGES, len(items), total)
            items = _dedupe_alpha_items(items)
            self._write_cache(cache_key, items, max(total, len(items)))
            return items
        except BrainAPIError as exc:
            if self.config.allow_stale_context_on_rate_limit and exc.status_code == 429 and cached["items"]:
                return cached["items"]
            raise

    def list_operators(self, query: str = "all", progress_callback=None) -> list[dict]:
        params = {"search": query if query != "all" else "", "limit": 100, "offset": 0}
        cache_key = self._cache_key("operators", params)
        cached = self._read_cache(cache_key)
        if cached["fresh"] and not _looks_partial_context_cache("operators", cached["items"], cached.get("total", 0), params["limit"]):
            if progress_callback:
                progress_callback({"scanned": len(cached["items"]), "total": cached.get("total") or len(cached["items"]), "cached": True})
            return cached["items"]
        try:
            items = []
            page_params = dict(params)
            total = 0
            seen_page_signatures: set[str] = set()
            for _page in range(1, _MAX_OPERATORS_PAGES + 1):
                data, _headers = self._request("GET", self.config.operators_path, query=page_params)
                page_items = [_normal_operator(item) for item in _items(data)]
                page_signature = _page_signature(page_items, keys=("name", "category"))
                if page_items and page_signature in seen_page_signatures:
                    logger.warning(
                        "operators pagination stopped on repeated page signature, offset=%s items=%d total=%d",
                        page_params.get("offset", 0),
                        len(items),
                        total,
                    )
                    if progress_callback:
                        progress_callback(
                            {
                                "scanned": len(items),
                                "total": total,
                                "page_size": len(page_items),
                                "offset": int(page_params.get("offset", 0)),
                                "truncated": True,
                                "warning": "repeated_page",
                            }
                        )
                    break
                if page_items:
                    seen_page_signatures.add(page_signature)
                items.extend(page_items)
                total = _total_count(data) or total
                if progress_callback:
                    progress_callback(
                        {
                            "scanned": len(items),
                            "total": total,
                            "page_size": len(page_items),
                            "offset": int(page_params.get("offset", 0)),
                        }
                    )
                if total and len(items) >= total:
                    break
                if len(items) >= _MAX_OPERATORS_ITEMS:
                    logger.warning("operators pagination reached max item limit (%d), total=%d", _MAX_OPERATORS_ITEMS, total)
                    items = items[:_MAX_OPERATORS_ITEMS]
                    break
                if len(page_items) < int(page_params["limit"]):
                    break
                page_params["offset"] = int(page_params.get("offset", 0)) + int(page_params["limit"])
            else:
                logger.warning("operators pagination reached max pages limit (%d), items=%d total=%d", _MAX_OPERATORS_PAGES, len(items), total)
            self._write_cache(cache_key, items, total)
            return items
        except BrainAPIError as exc:
            if self.config.allow_stale_context_on_rate_limit and exc.status_code == 429 and cached["items"]:
                return cached["items"]
            raise

    def list_user_alphas(self, sync_range: str = "3d", progress_callback=None) -> list[dict]:
        params = {"limit": 100, "offset": 0}
        if sync_range in {"3d", "7d"}:
            params["days"] = 3 if sync_range == "3d" else 7
        cache_key = self._cache_key("user_alphas", params)
        cached = self._read_cache(cache_key)
        if cached["fresh"]:
            if progress_callback:
                progress_callback(_user_alpha_progress(
                    sync_range,
                    cached["items"],
                    cached.get("total") or len(cached["items"]),
                    cached=True,
                    stale=False,
                ))
            return cached["items"]
        try:
            items = []
            page_params = dict(params)
            total = 0
            seen_page_signatures: set[str] = set()
            while True:
                try:
                    data, _headers = self._request("GET", self.config.user_alphas_path, query=page_params)
                except BrainAPIError as exc:
                    recovery = _user_alpha_offset_recovery(
                        exc,
                        items,
                        page_params,
                        sync_range=sync_range,
                        total=total,
                    )
                    if not recovery:
                        raise
                    page_params = recovery["page_params"]
                    seen_page_signatures.clear()
                    if progress_callback:
                        progress_callback(recovery["progress"])
                    continue
                page_items = [_normal_alpha(item) for item in _items(data)]
                page_signature = _page_signature(page_items, keys=("id", "expression", "created_at"))
                if page_items and page_signature in seen_page_signatures:
                    logger.warning(
                        "user_alphas pagination stopped on repeated page signature, offset=%s items=%d total=%d",
                        page_params.get("offset", 0),
                        len(items),
                        total,
                    )
                    if progress_callback:
                        progress_callback(_user_alpha_progress(sync_range, items, total, page_size=len(page_items), offset=int(page_params.get("offset", 0)), truncated=True, warning="repeated_page"))
                    break
                if page_items:
                    seen_page_signatures.add(page_signature)
                items.extend(page_items)
                total = max(_total_count(data) or 0, total, len(items))
                if progress_callback:
                    progress_callback(_user_alpha_progress(sync_range, items, total, page_size=len(page_items), offset=int(page_params.get("offset", 0))))
                if not page_items:
                    break
                if len(page_items) < int(page_params["limit"]):
                    break
                page_params["offset"] = int(page_params.get("offset", 0)) + int(page_params["limit"])
            self._write_cache(cache_key, items, total)
            return items
        except BrainAPIError as exc:
            if self.config.allow_stale_context_on_rate_limit and exc.status_code == 429 and cached["items"]:
                if progress_callback:
                    progress_callback(_user_alpha_progress(sync_range, cached["items"], cached.get("total") or len(cached["items"]), cached=True, stale=True, warning=redact_error_message(exc)))
                return cached["items"]
            raise

    def validate_expression(self, expression: str, settings: dict,
                            known_operators: set | None = None,
                            known_fields: set | None = None) -> dict:
        """Validate expression before simulation submission.

        Checks (local pre-check, BRAIN compiles through simulation submission):
          1. Balanced parentheses
          2. Non-empty expression
          3. Operator existence (against official BRAIN /operators API)
          4. Field existence (against official BRAIN /data-fields API)
          5. Expression length (advisory, >250 chars = WARNING)
          6. Function completeness (no dangling commas, no bare operators)
          7. Nesting depth (advisory, >6 = WARNING)
          8. NUL byte / non-printable character detection (P2-4)
          9. Empty function call detection (e.g. "ts_mean()")
        """
        errors = []
        warnings = []

        # ── P2-4: Null / non-printable character detection ──
        if not isinstance(expression, str):
            return {"status": "FAIL", "errors": ["Expression must be a string"]}
        if "\x00" in expression:
            errors.append("Expression contains null bytes")

        # Basic structure
        if not expression.strip():
            return {"status": "FAIL", "errors": ["Empty expression"]}

        if expression.count("(") != expression.count(")"):
            return {"status": "FAIL", "errors": ["Unbalanced parentheses"]}

        # Length check (advisory)
        if len(expression) > 250:
            warnings.append(f"Expression length {len(expression)} > 250 (may cause compile issues)")

        # Function completeness: check for dangling commas, incomplete function calls
        if re.search(r",\s*\)", expression):
            errors.append("Dangling comma before closing parenthesis")
        if re.search(r"\(\s*,", expression):
            errors.append("Leading comma after opening parenthesis")
        if re.search(r",\s*,", expression):
            errors.append("Consecutive commas in function arguments")

        # ── P2-4: Empty function calls ──
        if re.search(r"\b\w+\s*\(\s*\)", expression):
            warnings.append("Empty function call detected — ensure all functions have arguments")

        # ── P2-4: Unmatched quotes ──
        if expression.count('"') % 2 != 0 or expression.count("'") % 2 != 0:
            warnings.append("Unmatched quotes in expression")

        # Nesting depth
        depth = 0
        max_depth = 0
        for char in expression:
            if char == "(":
                depth += 1
                max_depth = max(max_depth, depth)
            elif char == ")":
                depth -= 1
                if depth < 0:
                    errors.append("Unmatched closing parenthesis — depth went negative")
                    break
        if max_depth > 6:
            warnings.append(f"Nesting depth {max_depth} > 6 (may reduce interpretability)")

        # P2-1: operator existence check (against official operator list)
        # Auto-load from OfficialDataLoader when not explicitly provided
        _known_ops: set = known_operators or set()
        _known_flds: set = known_fields or set()
        if not _known_ops or not _known_flds:
            try:
                from brain_alpha_ops.data import OfficialDataLoader
                loader = OfficialDataLoader.instance()
                if not _known_ops:
                    _known_ops = {op.name.lower() for op in loader.get_operators() if op.name}
                if not _known_flds:
                    _known_flds = {f.id.lower() for f in loader.get_fields() if f.id}
            except Exception:
                import logging
                logging.getLogger(__name__).warning(
                    "OfficialDataLoader unavailable — skipping local field/operator validation", exc_info=True)

        if _known_ops:
            used_ops = re.findall(r"\b([a-zA-Z_]\w*)\s*\(", expression)
            for op in used_ops:
                if op not in _known_ops and op.lower() not in _known_ops:
                    errors.append(f"Unknown operator: {op}")
            if len(set(used_ops)) > 8:
                warnings.append(f"High operator count: {len(set(used_ops))} unique operators (BRAIN 建议 <= 8)")

        # P2-1: field existence check (against official field list)
        if _known_flds:
            tokens = re.findall(r"\b([a-zA-Z_]\w+)\b", expression)
            field_tokens = [t for t in tokens if t.lower() in _known_flds]
            if not field_tokens:
                errors.append("No known BRAIN data fields found in expression")

        if errors:
            return {"status": "FAIL", "errors": errors, "warnings": warnings}
        return {"status": "PASS", "errors": [], "warnings": warnings,
                "note": "simulation submission will confirm official BRAIN compile"}

    def submit_simulation(self, expression: str, settings: dict) -> str:
        body = build_simulation_payload(expression, settings)
        data, headers = self._request("POST", self.config.simulations_path, body=body)
        location = headers.get("Location") or headers.get("location")
        sim_id = location or _first_value(data, ["id", "simulation_id", "location"], "")
        if not sim_id:
            raise BrainAPIError(f"simulation submission did not return a location/id: {_scrub(data)}")
        if str(sim_id).startswith(("http://", "https://")):
            build_official_url(self.config.base_url, str(sim_id), None)
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

    # ── P2: PROD_CORRELATION check ──
    def check_prod_correlation(self, expression: str, settings: dict | None = None) -> dict:
        """Check production correlation for an alpha expression via BRAIN API.

        Calls the official /alphas/correlations/check endpoint to assess
        correlation with existing production alphas.  Replaces the previous
        local-only prod_correlation estimation.

        Returns:
            {
                "status": "ok" | "error",
                "max_correlation": float | None,
                "related_alphas": [dict] | None,
                "warning": str | None,
            }
        """
        body: dict[str, object] = {"expression": expression}
        if settings:
            body["settings"] = settings
        try:
            data, _headers = self._request(
                "POST",
                self.config.alpha_correlations_path,
                body=body,
            )
            max_corr = _first_value(data, ["maxCorrelation", "max_correlation", "prodCorrelation", "prod_correlation"], None)
            related = data.get("relatedAlphas") or data.get("related_alphas") or data.get("alphas")
            return {
                "status": "ok",
                "max_correlation": abs(float(max_corr)) if max_corr is not None else None,
                "related_alphas": related if isinstance(related, list) else None,
                "warning": None,
            }
        except BrainAPIError as exc:
            # Correlation check is optional — don't block on failure
            return {
                "status": "error",
                "max_correlation": None,
                "related_alphas": None,
                "warning": f"PROD_CORRELATION API check unavailable: {exc}",
            }

    def poll_until_complete(self, simulation_id: str) -> str:
        for _attempt in range(self.config.poll_attempts):
            status = self.poll_simulation(simulation_id)
            if status in {"COMPLETED", "FAILED"}:
                return status
            time.sleep(self.config.poll_interval_seconds)
        return "TIMEOUT"

    def _request(
        self,
        method: str,
        path_or_url: str,
        *,
        body: dict | None = None,
        query: dict | None = None,
        headers: dict | None = None,
    ) -> tuple[Any, dict]:
        url = build_official_url(self.config.base_url, path_or_url, query)
        payload = None if body is None else json.dumps(body).encode("utf-8")
        attempts = max(1, int(self.config.rate_limit_retry_attempts) + 1)
        if self.token and (self._has_session_cookie() or (self.username and self.password)):
            attempts = max(attempts, 2)
        last_error: BrainAPIError | None = None
        for attempt in range(attempts):
            request_headers = {"Content-Type": "application/json", "Accept": "application/json"}
            auth_mode = "none"

            # Merge caller-supplied headers FIRST so we can detect X-Auth-Mode
            caller_headers = dict(headers or {})
            skip_auto_auth = caller_headers.pop("X-Auth-Mode", "") == "json"

            if self._prefer_cookie_auth and self._has_session_cookie():
                auth_mode = "cookie"
            elif self.token and not skip_auto_auth:
                request_headers["Authorization"] = f"Bearer {self.token}"
                auth_mode = "bearer"
            elif self.username and self.password and not skip_auto_auth:
                request_headers["Authorization"] = f"Basic {self._basic_auth()}"
                auth_mode = "basic"
            request_headers.update(caller_headers)
            self._throttle()
            req = urllib.request.Request(url, data=payload, headers=request_headers, method=method)
            try:
                with self._open(req, timeout=self.config.timeout_seconds) as resp:
                    raw = resp.read().decode("utf-8")
                    return _parse(raw), dict(resp.headers.items())
            except urllib.error.HTTPError as exc:
                raw = exc.read().decode("utf-8", errors="replace")
                parsed = _parse(raw)
                rate_limit_text = json.dumps(parsed, ensure_ascii=False, default=str)
                concurrency_limit = "CONCURRENT_SIMULATION_LIMIT_EXCEEDED" in rate_limit_text
                if (
                    _retryable_status(exc.code)
                    and self.config.rate_limit_retry_attempts > 0
                    and attempt < attempts - 1
                    and not concurrency_limit
                ):
                    time.sleep(_retry_delay(exc.headers, attempt, self.config.rate_limit_backoff_seconds))
                    continue
                if exc.code == 401 and auth_mode == "bearer" and attempt < attempts - 1:
                    self.token = ""
                    if self._has_session_cookie():
                        self._prefer_cookie_auth = True
                    continue
                # Log auth context separately for internal diagnostics without
                # embedding it in the user-facing error message, which could
                # leak internal authentication state to logs / API responses.
                logger.debug(
                    "API auth context: method=%s path=%s auth_mode=%s "
                    "has_cookie=%s has_user_pass=%s",
                    method,
                    path_or_url,
                    auth_mode,
                    self._has_session_cookie(),
                    bool(self.username and self.password),
                )
                last_error = BrainAPIError(
                    f"HTTP {exc.code}: {_scrub(parsed)}",
                    status_code=exc.code,
                    payload=_scrub(parsed),
                    retry_after=_retry_after(exc.headers),
                )
                raise last_error from exc
            except urllib.error.URLError as exc:
                last_error = BrainAPIError(f"network error: {exc}")
                if self.config.rate_limit_retry_attempts > 0 and attempt < attempts - 1:
                    time.sleep(_retry_delay(None, attempt, self.config.rate_limit_backoff_seconds))
                    continue
                raise last_error from exc
        if last_error is not None:
            raise BrainAPIError(
                f"request failed after retries: {redact_error_message(last_error)}",
                status_code=last_error.status_code,
                payload=getattr(last_error, "payload", None),
                retry_after=getattr(last_error, "retry_after", None),
            ) from last_error
        raise BrainAPIError("request failed after retries")

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

    def _basic_auth(self) -> str:
        return base64.b64encode(f"{self.username}:{self.password}".encode("utf-8")).decode("ascii")

    def _has_session_cookie(self) -> bool:
        return any(True for _ in self._cookie_jar)

    def _cache_key(self, kind: str, params: dict) -> str:
        raw = json.dumps({"kind": kind, "params": params}, sort_keys=True, ensure_ascii=False)
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        return f"{kind}_{digest}.json"

    def _cache_path(self, name: str) -> Path:
        return Path(self.config.cache_dir) / name

    def _read_cache(self, name: str) -> dict:
        path = self._cache_path(name)
        if not path.exists():
            return {"items": [], "fresh": False}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            age = time.time() - float(data.get("created_at", 0.0))
            return {
                "items": data.get("items", []),
                "total": int(data.get("total", 0) or 0),
                "fresh": age <= max(0, int(self.config.context_cache_ttl_seconds)),
                "age_seconds": max(0, int(age)),
            }
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {"items": [], "fresh": False}

    def _write_cache(self, name: str, items: list[dict], total: int = 0):
        path = self._cache_path(name)
        tmp: Path | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(
                {"created_at": time.time(), "items": items, "total": int(total or len(items))},
                ensure_ascii=False,
                indent=2,
            )
            tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
            with self._cache_lock:
                tmp.write_text(payload, encoding="utf-8")
                tmp.replace(path)
        except OSError as exc:
            logger.warning("failed to write official API cache %s: %s", path, redact_error_message(exc))
            if tmp is not None:
                try:
                    tmp.unlink()
                except Exception as cleanup_exc:
                    logger.debug("failed to remove temporary cache file %s: %s", tmp, redact_error_message(cleanup_exc))
            return
