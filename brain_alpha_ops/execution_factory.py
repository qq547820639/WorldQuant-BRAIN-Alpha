"""Execution backend factory — selects the appropriate backend based on config.

Modes:
- ``"browser"``: Always use Playwright browser (production)
- ``"api"``: Always use OfficialBrainAPI (development/diagnostic)
- ``"auto"``: Use browser if playwright is installed, else fall back to API

Environment variable ``BRAIN_ALPHA_OPS_EXECUTION_MODE`` overrides the mode parameter.
"""

from __future__ import annotations

import os
import logging
from typing import Any

from brain_alpha_ops.execution_backend import AlphaExecutionBackend

logger = logging.getLogger(__name__)

ENV_EXECUTION_MODE = "BRAIN_ALPHA_OPS_EXECUTION_MODE"
_ENV_EXECUTION_MODE_LEGACY = "BRAIN_ALPHA_EXECUTION_BACKEND"


def create_execution_backend(
    mode: str = "auto",
    browser_config: dict[str, Any] | None = None,
) -> AlphaExecutionBackend:
    """Create the appropriate execution backend.

    Args:
        mode: One of ``"browser"``, ``"api"``, or ``"auto"``.
            Can be overridden by the ``BRAIN_ALPHA_OPS_EXECUTION_MODE`` env var.
        browser_config: Optional config dict for the browser backend
            (``base_url``, ``headless``, ``evidence_dir``, etc.).

    Returns:
        An instance satisfying the ``AlphaExecutionBackend`` Protocol.
    """
    resolved_mode = os.environ.get(ENV_EXECUTION_MODE) or os.environ.get(_ENV_EXECUTION_MODE_LEGACY) or mode

    if resolved_mode == "browser" or (resolved_mode == "auto" and _playwright_available()):
        return _create_browser_backend(browser_config or {})
    return _create_api_backend()


def _playwright_available() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def _create_browser_backend(config: dict[str, Any]) -> AlphaExecutionBackend:
    from brain_alpha_ops.browser.execution_adapter import BrowserExecutionAdapter

    return BrowserExecutionAdapter(
        base_url=config.get("base_url", "https://brain.worldquant.com"),
        headless=config.get("headless", True),
        evidence_dir=config.get("evidence_dir", "artifacts"),
    )


def _create_api_backend() -> AlphaExecutionBackend:
    from brain_alpha_ops.brain_api.api_execution_adapter import ApiExecutionAdapter
    from brain_alpha_ops.brain_api.official import OfficialBrainAPI

    api = OfficialBrainAPI()
    return ApiExecutionAdapter(api)
