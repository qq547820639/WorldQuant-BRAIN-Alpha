"""Backend registration — called once at startup to populate the backend registry.

This module is intentionally separate from ``__init__.py`` to keep the root
package import light (no playwright/BrainAPI import at package load time).

Call ``register_all_backends()`` early in your application (e.g., in
``launch_web.py`` or ``brain_alpha_ops/__init__._configure_backends()``).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def register_all_backends() -> list[str]:
    """Register all available execution backends.

    Lazily imports each adapter only when called. Failures (e.g., missing
    playwright) are logged as warnings and do not crash the application.

    Returns:
        List of successfully registered backend names.
    """
    registered: list[str] = []

    # API backend (always available — depends only on BrainAPI)
    try:
        from brain_alpha_ops.brain_api.api_execution_adapter import ApiExecutionAdapter
        from brain_alpha_ops.execution_backend import register_backend

        register_backend("api", lambda: ApiExecutionAdapter(_get_brain_api()))
        registered.append("api")
        logger.debug("Registered execution backend: api")
    except Exception as e:
        logger.warning("Failed to register API execution backend: %s", e)

    # Browser backend (optional — depends on playwright)
    try:
        from brain_alpha_ops.browser.execution_adapter import BrowserExecutionAdapter
        from brain_alpha_ops.execution_backend import register_backend

        register_backend("browser", lambda: BrowserExecutionAdapter(headless=True))
        registered.append("browser")
        logger.debug("Registered execution backend: browser")
    except ImportError as e:
        logger.warning(
            "Browser execution backend not available (missing playwright). "
            "Install with: pip install -e '.[browser]' && playwright install chromium. "
            "Error: %s",
            e,
        )
    except Exception as e:
        logger.warning("Failed to register browser execution backend: %s", e)

    return registered


# Lazy BrainAPI singleton — only created when the api backend is first used.
_api_instance = None


def _get_brain_api():
    """Lazily create the API backend's BrainAPI instance."""
    global _api_instance
    if _api_instance is not None:
        return _api_instance

    from brain_alpha_ops.brain_api.official import OfficialBrainAPI
    _api_instance = OfficialBrainAPI()
    return _api_instance
