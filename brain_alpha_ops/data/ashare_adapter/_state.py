"""Shared state for the ashare_adapter package.

Holds the logger, optional pyarrow handles, the daily numeric field tuple,
and a ``_pkg`` helper so submodules can read/write feature flags that live on
the public package module (and are therefore monkeypatch-able by tests).
"""
from __future__ import annotations

import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)

# ── Performance: try fast Parquet, fall back to CSV ──
try:
    import pyarrow as pa  # noqa: F401
    import pyarrow.parquet as pq  # noqa: F401
except ImportError:
    pa = None  # type: ignore[assignment]
    pq = None  # type: ignore[assignment]

_DAILY_NUMERIC_FIELDS = (
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "turnover_rate",
    "adj_factor",
)


def _pkg() -> Any:
    """Return the parent package module (``brain_alpha_ops.data.ashare_adapter``).

    Submodules call this to access the feature flags (``_PARQUET_AVAILABLE``,
    ``_BAOSTOCK_AVAILABLE``, ``_AKSHARE_AVAILABLE``) that are defined on the
    package ``__init__`` so that ``monkeypatch.setattr(ashare, ...)`` in tests
    continues to take effect.
    """
    return sys.modules["brain_alpha_ops.data.ashare_adapter"]
