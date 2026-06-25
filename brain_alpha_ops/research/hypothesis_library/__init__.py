"""Hypothesis Library — structured market hypothesis definitions and experience-weighted management.

Provides:
  - Dataclasses: Hypothesis, ExpressionFamily, FieldCategoryDef, AdaptationConfig,
    FailureMode, Rationale, ExperienceWeights, GenerationMeta
  - HypothesisLibrary: YAML-based loading, querying, and experience weight management
  - File-repair helpers: ensure_hypothesis_library_files, PACKAGED_HYPOTHESIS_LIBRARY_FILES

Usage::

    from brain_alpha_ops.research.hypothesis_library import HypothesisLibrary

    library = HypothesisLibrary("brain_alpha_ops/research/hypotheses").load_all()
    all_h = library.get_all()
    momentum_h = library.get_by_id("earnings_revision_momentum")
    library.update_weights("earnings_revision_momentum",
                           field_cat_weights={"earnings_estimate_revision": 1.5},
                           expr_fam_weights={"revision_diff": 1.3},
                           window_weights={3: 1.2})
"""

from __future__ import annotations

from ._file_repair import (
    DEFAULT_HYPOTHESIS_LIBRARY_RELATIVE_DIR,
    PACKAGED_HYPOTHESIS_LIBRARY_FILES,
    _bundled_hypothesis_root,
    _safe_load_yaml,
    _yaml_file_is_usable,
    ensure_hypothesis_library_files,
)
from ._minimal_yaml import _minimal_yaml_load
from .library import HypothesisLibrary
from .models import (
    AdaptationConfig,
    ExperienceWeights,
    ExpressionFamily,
    FailureMode,
    FieldCategoryDef,
    GenerationMeta,
    Hypothesis,
    Rationale,
)

__all__ = [
    "DEFAULT_HYPOTHESIS_LIBRARY_RELATIVE_DIR",
    "PACKAGED_HYPOTHESIS_LIBRARY_FILES",
    "AdaptationConfig",
    "ExperienceWeights",
    "ExpressionFamily",
    "FailureMode",
    "FieldCategoryDef",
    "GenerationMeta",
    "Hypothesis",
    "HypothesisLibrary",
    "Rationale",
    "ensure_hypothesis_library_files",
]
