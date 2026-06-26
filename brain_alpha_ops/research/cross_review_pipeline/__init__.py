"""Re-export from the ``cross_review_pipeline`` subpackage for backward compatibility."""
from __future__ import annotations

from brain_alpha_ops.research.cross_review_pipeline._decision import *  # noqa: F401,F403
from brain_alpha_ops.research.cross_review_pipeline._evidence import *  # noqa: F401,F403
from brain_alpha_ops.research.cross_review_pipeline._pipeline import *  # noqa: F401,F403
from brain_alpha_ops.research.cross_review_pipeline._types import *  # noqa: F401,F403

# Explicitly re-export private symbols for test monkeypatch compatibility
from brain_alpha_ops.research.cross_review_pipeline._decision import (  # noqa: F401
    ReviewDecisionEngine,
)
from brain_alpha_ops.research.cross_review_pipeline._evidence import (  # noqa: F401
    KnowledgeEvidenceChecker,
)
from brain_alpha_ops.research.cross_review_pipeline._pipeline import (  # noqa: F401
    CrossReviewPipeline,
)
from brain_alpha_ops.research.cross_review_pipeline._types import (  # noqa: F401
    REVIEW_PIPELINE_SCHEMA,
    EvidenceCheckResult,
    ReviewDecision,
    ReviewableCandidate,
    _dedup,
    _ensure_dict_response,
    _extract_claims,
)
