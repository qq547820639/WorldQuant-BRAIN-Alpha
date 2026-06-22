"""Browser-first execution layer for BRAIN Web interactions.

Provides:
- ``BrainBrowserRunner`` — Playwright-driven browser session for real BRAIN Web UI
- ``BrowserMonitor`` — health checks + auto-healing for browser sessions
- ``BrowserExecutionAdapter`` — adapter implementing ``AlphaExecutionBackend`` Protocol

All browser functionality depends on the optional ``playwright`` dependency.
Install with: ``pip install -e ".[browser]"`` then ``playwright install chromium``.
"""

from __future__ import annotations


def _register_browser_backend() -> None:
    """Lazily register the browser execution backend.

    Called on first import of this package. Fails gracefully if playwright
    is not installed, logging a warning instead of crashing.
    """
    try:
        from brain_alpha_ops.browser.execution_adapter import BrowserExecutionAdapter
        from brain_alpha_ops.execution_backend import register_backend

        def _factory():
            return BrowserExecutionAdapter(
                headless=True,
                evidence_dir="artifacts",
            )

        register_backend("browser", _factory)
    except ImportError as e:
        import logging
        logging.getLogger(__name__).warning(
            "Browser execution backend not available: %s. "
            "Install with: pip install -e '.[browser]' && playwright install chromium",
            e,
        )


# Auto-register on import
_register_browser_backend()
