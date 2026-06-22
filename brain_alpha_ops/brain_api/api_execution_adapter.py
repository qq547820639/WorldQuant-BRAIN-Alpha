"""ApiExecutionAdapter — wraps existing BrainAPI into AlphaExecutionBackend Protocol.

This adapter does NOT introduce new functionality — it maps the existing
``OfficialBrainAPI`` interface to the ``AlphaExecutionBackend`` Protocol
so that both API and Browser backends expose the same contract.

Usage::

    from brain_alpha_ops.brain_api.official import OfficialBrainAPI
    from brain_alpha_ops.brain_api.api_execution_adapter import ApiExecutionAdapter

    api = OfficialBrainAPI(...)
    backend: AlphaExecutionBackend = ApiExecutionAdapter(api)
    backend.authenticate({"username": "...", "password": "..."})
"""

from __future__ import annotations

import logging
from typing import Any

from brain_alpha_ops.execution_backend import ExecutionEvidence

logger = logging.getLogger(__name__)


class ApiExecutionAdapter:
    """Thin Protocol adapter: BrainAPI → AlphaExecutionBackend.

    Intended for dev tools, diagnostics, and offline analysis only.
    Production submit/check flows MUST use the Browser backend.
    """

    def __init__(self, api):
        """Wrap an existing BrainAPI instance.

        Args:
            api: An instance implementing ``BrainAPI`` (e.g. ``OfficialBrainAPI``).
        """
        self._api = api
        self._authenticated = False

    # ---- AlphaExecutionBackend Protocol methods ----

    def authenticate(self, credentials: dict[str, str]) -> dict[str, Any]:
        """Delegate authentication to underlying BrainAPI."""
        try:
            username = credentials.get("username", "")
            password = credentials.get("password", "")
            token = credentials.get("token", "")

            if token:
                self._api.authenticate(token=token)
            elif username and password:
                self._api.authenticate(username=username, password=password)
            else:
                return {"ok": False, "error": "Missing credentials"}

            self._authenticated = True
            return {"ok": True, "step": "auth.api_done"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def simulate_alpha(self, expression: str, settings: dict[str, Any]) -> dict[str, Any]:
        """Delegate simulation to underlying BrainAPI."""
        if not self._authenticated:
            return {"ok": False, "error": "Not authenticated"}

        try:
            result = self._api.simulate(expression, settings=settings)
            return {
                "ok": True,
                "expression": expression,
                "results": result,
                "transport": "api",
            }
        except Exception as e:
            return {"ok": False, "expression": expression, "error": str(e)}

    def check_alpha(self, alpha_id: str) -> dict[str, Any]:
        """Delegate check to underlying BrainAPI."""
        if not self._authenticated:
            return {"ok": False, "error": "Not authenticated"}

        try:
            result = self._api.check_alpha(alpha_id)
            return {
                "ok": True,
                "alpha_id": alpha_id,
                "checks": result,
                "transport": "api",
            }
        except Exception as e:
            return {"ok": False, "alpha_id": alpha_id, "error": str(e)}

    def submit_alpha(self, alpha_id: str) -> dict[str, Any]:
        """Delegate submit to underlying BrainAPI.

        **Warning**: This bypasses browser confirmation. Production code
        should use the Browser backend and respect
        ``REAL_SUBMIT_DISABLED_WEB_FLOW``.
        """
        if not self._authenticated:
            return {"ok": False, "error": "Not authenticated"}

        try:
            result = self._api.submit_alpha(alpha_id)
            return {
                "ok": True,
                "alpha_id": alpha_id,
                "result": result,
                "transport": "api",
            }
        except Exception as e:
            return {"ok": False, "alpha_id": alpha_id, "error": str(e)}

    def get_evidence(self) -> ExecutionEvidence:
        """API backend produces no browser evidence — returns empty record."""
        return ExecutionEvidence(transport="api")
