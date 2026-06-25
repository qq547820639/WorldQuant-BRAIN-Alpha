"""HypothesisDrivenGenerator — main hypothesis-driven alpha generation engine.

Backward-compatible re-export shim.  The implementation now lives in the
``generator/`` sub-package; this file re-exports the public API so that
existing import paths continue to work unchanged.
"""

from __future__ import annotations

from .generator._constraints import _FORBIDDEN_PATTERN_SIMILARITY_THRESHOLD
from .generator._core import HypothesisDrivenGenerator

__all__ = ["HypothesisDrivenGenerator"]
