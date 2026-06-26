"""Re-export from the ``expression_ast`` subpackage for backward compatibility."""
from __future__ import annotations

from brain_alpha_ops.research.expression_ast._parser import *  # noqa: F401,F403
from brain_alpha_ops.research.expression_ast._profile import *  # noqa: F401,F403
from brain_alpha_ops.research.expression_ast._similarity import *  # noqa: F401,F403
from brain_alpha_ops.research.expression_ast._types import *  # noqa: F401,F403

# Explicitly re-export private symbols for test monkeypatch compatibility
from brain_alpha_ops.research.expression_ast._parser import (  # noqa: F401
    _canonical_child,
    _collect,
    _collect_operators,
    _fields_from_text,
    _fingerprint,
    _flatten,
    _is_identifier_token,
    _is_number,
    _max_depth,
    _node_count,
    _normalize_number,
    _operators_from_text,
    _paren_depth,
    _paren_depth_simple,
    _precedence,
    _tokenize,
    _windows_from_text,
    canonicalize,
    lexical_normalize,
    parse_expression,
)
from brain_alpha_ops.research.expression_ast._profile import (  # noqa: F401
    canonical_expression,
    expression_fingerprint,
    expression_key,
    expression_profile_summary,
    ordered_operators,
    profile_expression,
)
from brain_alpha_ops.research.expression_ast._similarity import (  # noqa: F401
    canonical_tokens,
    expression_similarity,
    _jaccard,
    _semantic_tokens,
    _window_bucket,
)
from brain_alpha_ops.research.expression_ast._types import (  # noqa: F401
    ExpressionParseError,
    ExpressionProfile,
    ExprNode,
    _LEXICAL_TOKEN_RE,
    _TOKEN_RE,
)

__all__ = [
    # Public API from _parser
    "canonicalize",
    "lexical_normalize",
    "parse_expression",
    # Public API from _profile
    "canonical_expression",
    "expression_fingerprint",
    "expression_key",
    "expression_profile_summary",
    "ordered_operators",
    "profile_expression",
    # Public API from _similarity
    "canonical_tokens",
    "expression_similarity",
    # Public API from _types
    "ExpressionParseError",
    "ExpressionProfile",
    "ExprNode",
    # Private symbols re-exported for test monkeypatch compatibility
    "_canonical_child",
    "_collect",
    "_collect_operators",
    "_fields_from_text",
    "_fingerprint",
    "_flatten",
    "_is_identifier_token",
    "_is_number",
    "_max_depth",
    "_node_count",
    "_normalize_number",
    "_operators_from_text",
    "_paren_depth",
    "_paren_depth_simple",
    "_precedence",
    "_tokenize",
    "_windows_from_text",
    "_jaccard",
    "_semantic_tokens",
    "_window_bucket",
    "_LEXICAL_TOKEN_RE",
    "_TOKEN_RE",
]
