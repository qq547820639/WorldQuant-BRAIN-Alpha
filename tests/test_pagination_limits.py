"""Tests for pagination limits and safety boundaries."""

from __future__ import annotations

import pytest

from brain_alpha_ops.brain_api.pagination_limits import (
    MAX_FIELDS_PAGES,
    MAX_DATASETS_PAGES,
    MAX_OPERATORS_PAGES,
    MAX_USER_ALPHAS_PAGES,
    MAX_FIELDS_ITEMS,
    MAX_DATASETS_ITEMS,
    MAX_OPERATORS_ITEMS,
    coerce_limit,
)


class TestPaginationLimits:
    def test_user_alphas_has_no_default_hard_page_limit(self):
        """User alpha history must not be truncated by an arbitrary cap."""
        assert MAX_USER_ALPHAS_PAGES is None

    def test_all_collections_have_limits(self):
        """All collectible types must have a page limit."""
        assert MAX_FIELDS_PAGES is not None and MAX_FIELDS_PAGES > 0
        assert MAX_DATASETS_PAGES is not None and MAX_DATASETS_PAGES > 0
        assert MAX_OPERATORS_PAGES is not None and MAX_OPERATORS_PAGES > 0

    def test_item_limits_set(self):
        assert MAX_FIELDS_ITEMS > 0
        assert MAX_DATASETS_ITEMS > 0
        assert MAX_OPERATORS_ITEMS > 0


class TestCoerceLimit:
    def test_int_passes_through(self):
        assert coerce_limit(50) == 50

    def test_none_returns_safety_default(self):
        assert coerce_limit(None, safety_default=25) == 25

    def test_none_no_default(self):
        assert coerce_limit(None) is None

    def test_string_coerced(self):
        assert coerce_limit("30") == 30

    def test_zero(self):
        assert coerce_limit(0) == 0
