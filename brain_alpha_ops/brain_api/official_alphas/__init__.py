"""Re-export from the ``official_alphas`` subpackage for backward compatibility."""

from __future__ import annotations

from ._filter_mixin import _AlphaQueryFilterMixin
from ._helpers import (
    _ALPHA_FILTER_OPTION_KEYS,
    _DISCOVERY_OPTION_KEYS,
    _compat_blank,
    _is_user_alpha_transient_page_error,
    _pop_compat_alias,
)
from ._lifecycle_mixin import _AlphaQueryLifecycleMixin
from ._locate_mixin import _AlphaQueryLocateMixin


class AlphaQueryMixin(_AlphaQueryLocateMixin, _AlphaQueryFilterMixin, _AlphaQueryLifecycleMixin):
    """Composite ``AlphaQueryMixin`` combining locate, filter, and lifecycle mixins."""

    pass


__all__ = [
    "AlphaQueryMixin",
    "_compat_blank",
    "_pop_compat_alias",
    "_is_user_alpha_transient_page_error",
    "_DISCOVERY_OPTION_KEYS",
    "_ALPHA_FILTER_OPTION_KEYS",
]
