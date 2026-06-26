"""Composite ``AlphaQueryMixin`` combining locate, filter, and lifecycle mixins."""

from __future__ import annotations

from ._filter_mixin import _AlphaQueryFilterMixin
from ._lifecycle_mixin import _AlphaQueryLifecycleMixin
from ._locate_mixin import _AlphaQueryLocateMixin


class AlphaQueryMixin(_AlphaQueryLocateMixin, _AlphaQueryFilterMixin, _AlphaQueryLifecycleMixin):
    pass
