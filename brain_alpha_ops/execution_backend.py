from __future__ import annotations

import os
import logging
from dataclasses import dataclass, field
from typing import Protocol, Any, Callable

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# Data types
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ExecutionEvidence:
    transport: str  # "browser" or "api"
    screenshots: list[str] = field(default_factory=list)
    dom_snapshots: list[str] = field(default_factory=list)
    har_path: str | None = None
    console_logs: list[dict[str, Any]] = field(default_factory=list)
    network_logs: list[dict[str, Any]] = field(default_factory=list)

# ═══════════════════════════════════════════════════════════════════════════
# Protocol
# ═══════════════════════════════════════════════════════════════════════════

class AlphaExecutionBackend(Protocol):
    """Execution backend Protocol — all BRAIN interactions must go through this interface.

    Implementations:
        - ``ApiExecutionBackend`` — uses ``OfficialBrainAPI`` (dev/tools only)
        - ``BrowserExecutionAdapter`` — uses Playwright to drive real BRAIN Web UI
    """
    def authenticate(self, credentials: dict[str, str]) -> dict[str, Any]: ...
    def simulate_alpha(self, expression: str, settings: dict[str, Any]) -> dict[str, Any]: ...
    def check_alpha(self, alpha_id: str) -> dict[str, Any]: ...
    def submit_alpha(self, alpha_id: str) -> dict[str, Any]: ...
    def get_evidence(self) -> ExecutionEvidence: ...

# ═══════════════════════════════════════════════════════════════════════════
# Backend Registry — select backend at runtime based on env / config
# ═══════════════════════════════════════════════════════════════════════════

BackendFactory = Callable[[], AlphaExecutionBackend]

# Environment variable that overrides the default backend selection.
# Set to "api" to force API-only mode (development / CI), or "browser" for production.
ENV_EXECUTION_BACKEND = "BRAIN_ALPHA_EXECUTION_BACKEND"

DEFAULT_BACKEND: str = "browser"
"""Default backend for production — must be ``"browser"`` to satisfy hard constraints."""

_registry: dict[str, BackendFactory] = {}
"""Registry of backend name → lazy factory function."""


def register_backend(name: str, factory: BackendFactory) -> None:
    """Register a backend factory under a name.

    Callers should register backends at import time::

        from brain_alpha_ops.execution_backend import register_backend
        register_backend("api", lambda: ApiExecutionBackend())
    """
    _registry[name] = factory
    logger.debug("Registered execution backend: %s", name)


def get_backend(name: str | None = None) -> AlphaExecutionBackend:
    """Return the active execution backend instance.

    Resolution order:
        1. Explicit ``name`` argument
        2. ``BRAIN_ALPHA_EXECUTION_BACKEND`` env var
        3. ``DEFAULT_BACKEND`` (``"browser"`` in production)

    Raises:
        RuntimeError: if the resolved backend name is not in the registry.

    Returns:
        An instance that satisfies ``AlphaExecutionBackend`` Protocol.
    """
    backend_name = name or os.environ.get(ENV_EXECUTION_BACKEND, DEFAULT_BACKEND)

    factory = _registry.get(backend_name)
    if factory is None:
        registered = list(_registry.keys())
        raise RuntimeError(
            f"Unknown execution backend: {backend_name!r}. "
            f"Registered backends: {registered}. "
            f"Set {ENV_EXECUTION_BACKEND}=browser or call register_backend() first."
        )

    logger.info("Activating execution backend: %s", backend_name)
    return factory()


def list_backends() -> list[str]:
    """Return the names of all registered backends."""
    return list(_registry.keys())
