"""Audit the production inline console and React mirror navigation surfaces.

This check is intentionally read-only. It makes the dual-frontend gap visible
without changing which frontend is served by default. Use ``--fail-on-gaps``
only when React is expected to be ready for promotion to the single surface.

Re-export shim. The implementation has been split into the
``scripts.check_frontend_surface_parity`` subpackage (Task A10 of
deep-optimization-phase12). The public API is re-exported here so
``from scripts.check_frontend_surface_parity import ...`` continues to
resolve to the package directory (Python prefers the package ``__init__.py``
over the sibling ``scripts/check_frontend_surface_parity.py`` shim when
both exist). The thin ``scripts/check_frontend_surface_parity.py`` shim
remains only to preserve ``python scripts/check_frontend_surface_parity.py``
direct CLI invocation, including the ``sys.path`` bootstrap for
``brain_alpha_ops``.
"""

from __future__ import annotations

from ._audit import check_frontend_surface_parity
from ._cli import main
from ._constants import (
    DEFAULT_INLINE_REGISTRY,
    DEFAULT_PARITY_PLAN,
    DEFAULT_REACT_APP,
    ROOT,
    VALID_PLAN_STATUSES,
    VALID_REACT_ONLY_STATUSES,
)
from ._extractors import (
    _extract_inline_titles,
    _extract_inline_view_order,
    _extract_react_card_config,
    _extract_sidebar_nav_items,
    _finding,
    _read_text,
    _string_literals,
    extract_inline_views,
    extract_react_tabs,
)
from ._plan_summary import (
    _empty_plan_summary,
    _plan_entry_error,
    _plan_summary,
    _react_only_entry_error,
    _react_only_policy_summary,
    _retired_inline_plan_summary,
)

__all__ = [
    "ROOT",
    "DEFAULT_INLINE_REGISTRY",
    "DEFAULT_REACT_APP",
    "DEFAULT_PARITY_PLAN",
    "VALID_PLAN_STATUSES",
    "VALID_REACT_ONLY_STATUSES",
    "check_frontend_surface_parity",
    "extract_inline_views",
    "extract_react_tabs",
    "main",
    # Private symbols re-exported for tests and other modules that
    # historically imported them from the monolith.
    "_extract_inline_titles",
    "_extract_inline_view_order",
    "_extract_react_card_config",
    "_extract_sidebar_nav_items",
    "_finding",
    "_read_text",
    "_string_literals",
    "_empty_plan_summary",
    "_plan_entry_error",
    "_plan_summary",
    "_react_only_entry_error",
    "_react_only_policy_summary",
    "_retired_inline_plan_summary",
]
