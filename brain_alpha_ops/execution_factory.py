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
from typing import Any, TYPE_CHECKING

from brain_alpha_ops.execution_backend import AlphaExecutionBackend

if TYPE_CHECKING:
    from brain_alpha_ops.config import RunConfig

logger = logging.getLogger(__name__)

ENV_EXECUTION_MODE = "BRAIN_ALPHA_OPS_EXECUTION_MODE"
_ENV_EXECUTION_MODE_LEGACY = "BRAIN_ALPHA_EXECUTION_BACKEND"


def create_execution_backend(
    mode: str = "auto",
    browser_config: dict[str, Any] | None = None,
    *,
    run_config: "RunConfig | None" = None,
) -> AlphaExecutionBackend:
    """Create the appropriate execution backend.

    Args:
        mode: One of ``"browser"``, ``"api"``, or ``"auto"``.
            Can be overridden by the ``BRAIN_ALPHA_OPS_EXECUTION_MODE`` env var.
        browser_config: Optional config dict for the browser backend
            (``base_url``, ``headless``, ``evidence_dir``, etc.).
        run_config: Optional :class:`RunConfig` used to construct the
            backend with credentials and official API settings. When
            provided, the API backend is built from the run_config's
            credentials and OfficialAPIConfig rather than a bare
            ``OfficialBrainAPI()`` that relies on env vars.

    Returns:
        An instance satisfying the ``AlphaExecutionBackend`` Protocol.
    """
    resolved_mode = os.environ.get(ENV_EXECUTION_MODE) or os.environ.get(_ENV_EXECUTION_MODE_LEGACY) or mode

    if resolved_mode == "browser":
        return _create_browser_backend(browser_config or {}, run_config)
    if resolved_mode == "auto" and _playwright_available():
        return _create_browser_backend(browser_config or {}, run_config)
    # F-032: surface the silent fallback. Previously "auto" mode fell back
    # to the API backend with no log, masking the missing playwright
    # dependency in production deployments that expected the browser
    # submit flow to be active.
    if resolved_mode == "auto":
        logger.warning(
            "playwright unavailable, falling back to API backend "
            "(mode=auto could not start the browser submit flow)"
        )
    return _create_api_backend(run_config)


def _playwright_available() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def _create_browser_backend(
    config: dict[str, Any],
    run_config: "RunConfig | None" = None,
) -> AlphaExecutionBackend:
    from brain_alpha_ops.browser.execution_adapter import BrowserExecutionAdapter

    kwargs: dict[str, Any] = {
        "base_url": config.get("base_url", "https://brain.worldquant.com"),
        "headless": config.get("headless", True),
        "evidence_dir": config.get("evidence_dir", "artifacts"),
    }
    if run_config is not None:
        credentials = run_config.credentials.resolve()
        if credentials.get("username"):
            kwargs["username"] = credentials["username"]
        if credentials.get("password"):
            kwargs["password"] = credentials["password"]
    return BrowserExecutionAdapter(**kwargs)


def _create_api_backend(run_config: "RunConfig | None" = None) -> AlphaExecutionBackend:
    from brain_alpha_ops.brain_api.api_execution_adapter import ApiExecutionAdapter
    from brain_alpha_ops.brain_api.official import OfficialBrainAPI

    if run_config is not None:
        credentials = run_config.credentials.resolve()
        api = OfficialBrainAPI(run_config.ops.official_api, **credentials)
        api.set_market_scope(run_config.ops.settings)
    else:
        api = OfficialBrainAPI()
    return ApiExecutionAdapter(api)
