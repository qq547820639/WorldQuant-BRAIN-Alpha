"""Authentication and profile helpers for the official BRAIN API adapter."""

from __future__ import annotations

import base64

from .base import BrainAPIError
from .official_helpers import _first_value, scrub as _scrub


class OfficialAuthProfileMixin:
    def authenticate(self) -> dict:
        if self.token and not (self.username and self.password):
            return {"status": "ok", "auth": "token"}
        if not self.username or not self.password:
            raise BrainAPIError("production mode requires BRAIN_USERNAME/BRAIN_PASSWORD or BRAIN_TOKEN")

        for _method_name, build_request in [
            ("basic", lambda: (
                "POST",
                self.config.authentication_path,
                {"Authorization": f"Basic {self._basic_auth()}"},
                None,
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
            except BrainAPIError as exc:
                if exc.status_code in (401, 400):
                    # 401 = correct format, wrong credentials — stop
                    if exc.status_code == 401:
                        break
                    continue
                raise

        raise BrainAPIError("BRAIN API authentication failed: invalid credentials (HTTP 401). Check username/password or generate a new token.")

    def get_user_profile(self) -> dict:
        """Fetch current user profile from BRAIN /users/self endpoint."""
        if hasattr(self, "_cached_profile") and self._cached_profile:
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
        tier = str(_first_value(
            data,
            ["tier", "userTier", "tierName", "consultantTier", "accountType"],
            "",
        ))
        level = _first_value(data, ["level", "userLevel", "consultantLevel", "currentLevel"], None)
        points = _first_value(data, ["points", "score", "totalPoints", "totalScore", "accumulatedPoints"], None)

        if not tier or tier in ("unknown", "None", ""):
            genius = _first_value(data, ["geniusLevel"], None)
            if genius is not None:
                tier = f"IQC-{genius}"
            elif data.get("approved") and not data.get("tier"):
                tier = "BASIC"
            else:
                tier = "BASIC"

        account_tier = "ADVANCED" if tier not in ("BASIC", "unknown", "") and "IQC" not in str(tier) else "BASIC"

        profile = {
            "tier": tier,
            "account_tier": account_tier,
            "level": int(level) if level is not None else None,
            "points": float(points) if points is not None else None,
            "username": str(_first_value(data, ["username", "email", "userEmail", "login"], self.username)),
            "raw": scrubbed,
        }
        self._cached_profile = profile
        return profile

    def _basic_auth(self) -> str:
        return base64.b64encode(f"{self.username}:{self.password}".encode("utf-8")).decode("ascii")

    def _has_session_cookie(self) -> bool:
        return any(True for _ in self._cookie_jar)
