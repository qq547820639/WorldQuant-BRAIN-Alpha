"""Re-export from the ``generator`` subpackage for backward compatibility.

The original monolithic ``generator.py`` was split into the
``brain_alpha_ops.research.generator`` subpackage. This module re-exports the full
public API surface so legacy imports continue to work.
"""
from __future__ import annotations

# Re-export everything from sub-modules
from brain_alpha_ops.research.generator._filters import *  # noqa: F401,F403
from brain_alpha_ops.research.generator._generator import *  # noqa: F401,F403
from brain_alpha_ops.research.generator._helpers import *  # noqa: F401,F403

# Explicitly re-export private symbols so test monkeypatch against
# ``brain_alpha_ops.research.generator._private_symbol`` keeps working.
from brain_alpha_ops.research.generator._filters import (  # noqa: F401
    FORBIDDEN_PATTERN_SIMILARITY_THRESHOLD,
    _build_official_field_pool,
    _expression_forbidden,
    _expression_satisfies_strict_preferred_constraints,
    _is_observability_avoided,
    _official_preferred_fields,
    set_experience_guidance,
    set_knowledge_constraints,
    set_observability_guidance,
)
from brain_alpha_ops.research.generator._generator import (  # noqa: F401
    CandidateGenerator,
    LocalQualityConfig,
    _expression_operators_are_official,
    _get_default_windows,
    _load_official_operator_names,
    _load_operators_windows,
    expression_windows_within_constraints,
    extract_fields,
    extract_operators,
    local_quality,
    mutate_expression,
    nesting_depth,
)
from brain_alpha_ops.research.generator._helpers import (  # noqa: F401
    _BUILTIN_FALLBACK_TEMPLATES,
    _generate_dynamic,
    _generate_fallback,
    _load_fallback_templates,
    _MAX_EXPRESSION_LENGTH,
    _safe_float,
    update_known_fields,
)
