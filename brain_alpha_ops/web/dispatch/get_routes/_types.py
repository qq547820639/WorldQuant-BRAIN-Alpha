"""Route handler type and Route dataclass for the web console."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

# ═══════════════════════ Route Handler Type ═══════════════════════════
RouteHandler = Callable[[Any, str, dict], None]


@dataclass(frozen=True)
class Route:
    handler: str
    requires_session: bool = True
    category: str = "api"
