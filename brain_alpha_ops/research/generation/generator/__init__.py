"""HypothesisDrivenGenerator — main hypothesis-driven alpha generation engine.

This package splits the original ``generator.py`` into focused sub-modules
while preserving the public API.  ``HypothesisDrivenGenerator`` and all
module-level constants are re-exported here so that
``from brain_alpha_ops.research.generation.generator import HypothesisDrivenGenerator``
continues to work unchanged.
"""

from ._constraints import _FORBIDDEN_PATTERN_SIMILARITY_THRESHOLD
from ._core import HypothesisDrivenGenerator

__all__ = ["HypothesisDrivenGenerator"]
