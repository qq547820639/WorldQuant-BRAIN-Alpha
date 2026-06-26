"""Re-export from the ``theme_engine`` subpackage for backward compatibility.

The original monolithic ``theme_engine.py`` was split into the
``brain_alpha_ops.research.theme_engine`` subpackage. This module re-exports
the full public API surface so legacy imports continue to work.

Sub-modules:
  - ``_template``  : ``ThemeTemplate`` dataclass + window/group constants +
                     ``PRODUCTION_STRUCTURE_SKELETONS``
  - ``_skeletons`` : ``TEMPLATE_SKELETONS`` dict (52+ templates by category)
  - ``_helpers``   : ``_normalize_operator_aliases``, ``_build_category_map``,
                     ``_build_auto_skeletons_impl``
  - ``_engine``    : ``DynamicThemeEngine`` class
"""
from __future__ import annotations

# Re-export everything from sub-modules
from brain_alpha_ops.research.theme_engine._template import (  # noqa: F401
    DEFAULT_GROUPS,
    DEFAULT_WINDOWS,
    PRODUCTION_STRUCTURE_SKELETONS,
    ThemeTemplate,
)
from brain_alpha_ops.research.theme_engine._skeletons import (  # noqa: F401
    TEMPLATE_SKELETONS,
)
from brain_alpha_ops.research.theme_engine._helpers import (  # noqa: F401
    _build_auto_skeletons_impl,
    _build_category_map,
    _normalize_operator_aliases,
)
from brain_alpha_ops.research.theme_engine._engine import (  # noqa: F401
    DynamicThemeEngine,
)

__all__ = [
    "ThemeTemplate",
    "TEMPLATE_SKELETONS",
    "PRODUCTION_STRUCTURE_SKELETONS",
    "DEFAULT_WINDOWS",
    "DEFAULT_GROUPS",
    "DynamicThemeEngine",
    "_normalize_operator_aliases",
    "_build_category_map",
    "_build_auto_skeletons_impl",
]
