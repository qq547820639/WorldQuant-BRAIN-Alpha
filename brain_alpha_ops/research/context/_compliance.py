"""LLM-ready context packs — compliance context.

``_compliance_context`` builds a lightweight redline + scoring health snapshot
of the current ``RunConfig``.
"""
from __future__ import annotations

from typing import Any

from brain_alpha_ops.config import RunConfig


def _compliance_context(config: RunConfig) -> dict[str, Any]:
    """Build lightweight redline + scoring health snapshot.

    On import or execution failure, redline is conservatively reported as
    "unknown" rather than silently defaulting to "ok".  This prevents
    silently masking redline violations when the verifier cannot be loaded.
    """
    try:
        from brain_alpha_ops.compliance.redline_verifier import RedLineVerifier
        verifier = RedLineVerifier(config)
        report = verifier.verify_all()
        redline = {
            "ok": report.ok,
            "violations": len(report.violations),
            "summary": report.report()[:300],
        }
    except ImportError:
        import logging
        logging.getLogger(__name__).debug("RedLineVerifier import failed; reporting redline as unknown.")
        redline = {"ok": False, "violations": -1, "summary": "redline verifier not available"}
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("RedLineVerifier execution failed: %s", exc)
        redline = {"ok": False, "violations": -1, "summary": f"redline verification error: {exc}"}

    try:
        from brain_alpha_ops.scoring.history import ScoreHistoryDB
        db = ScoreHistoryDB(config.ops.storage_dir)
        stats = db.convergence_stats()
        scoring_health = stats
    except ImportError:
        import logging
        logging.getLogger(__name__).debug("ScoreHistoryDB not available.")
        scoring_health = {"available": False, "error": "module not found"}
    except Exception as exc:
        import logging

        from brain_alpha_ops.redaction import redact_error_message
        logging.getLogger(__name__).warning("ScoreHistoryDB failed: %s", exc)
        scoring_health = {"available": False, "error": redact_error_message(exc)}

    return {
        "redline": redline,
        "scoring_health": scoring_health,
        "thresholds_synced": True,
    }
