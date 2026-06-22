"""Pipeline evidence integration — mount EvidenceArchival into execution flow.

Provides a lightweight hook so that any pipeline stage (simulation, check,
submit) can automatically archive browser interaction evidence without
adding boilerplate to each mixin.

Usage::

    from brain_alpha_ops.monitoring.pipeline_evidence import capture_evidence

    with capture_evidence(session_id="alpha_abc123", backend=backend) as archive:
        result = backend.simulate_alpha(expression, settings)
        # evidence is auto-archived on exit
"""

from __future__ import annotations

import uuid
import logging
from contextlib import contextmanager
from typing import Any

from brain_alpha_ops.execution_backend import ExecutionEvidence
from brain_alpha_ops.monitoring.evidence import EvidenceArchival

logger = logging.getLogger(__name__)

# Singleton archival instance — created lazily
_archiver: EvidenceArchival | None = None


def get_archiver(evidence_dir: str = "artifacts/evidence") -> EvidenceArchival:
    """Return the singleton EvidenceArchival instance."""
    global _archiver
    if _archiver is None:
        _archiver = EvidenceArchival(evidence_dir=evidence_dir)
    return _archiver


@contextmanager
def capture_evidence(
    session_id: str | None = None,
    *,
    backend=None,
    archiver: EvidenceArchival | None = None,
):
    """Context manager that auto-archives backend evidence on exit.

    Args:
        session_id: Unique session identifier (auto-generated if None).
        backend: An ``AlphaExecutionBackend`` instance to collect evidence from.
        archiver: ``EvidenceArchival`` instance (uses singleton if None).

    Yields:
        The ``EvidenceArchival`` instance, for manual archiving if needed.
    """
    sid = session_id or f"session_{uuid.uuid4().hex[:12]}"
    arc = archiver or get_archiver()
    try:
        yield arc
    finally:
        if backend is not None:
            try:
                evidence = backend.get_evidence()
                evidence_dict = _execution_evidence_to_dict(evidence)
                arc.archive_session(sid, evidence_dict)
                logger.info("Auto-archived evidence for session: %s", sid)
            except Exception as e:
                logger.warning("Failed to auto-archive evidence: %s", e)


def archive_execution_evidence(
    session_id: str,
    evidence: ExecutionEvidence,
    archiver: EvidenceArchival | None = None,
) -> str:
    """Archive a single ExecutionEvidence record.

    Args:
        session_id: Unique session identifier.
        evidence: ``ExecutionEvidence`` dataclass instance.
        archiver: ``EvidenceArchival`` instance (uses singleton if None).

    Returns:
        Path to the archived session directory.
    """
    arc = archiver or get_archiver()
    evidence_dict = _execution_evidence_to_dict(evidence)
    return arc.archive_session(session_id, evidence_dict)


def _execution_evidence_to_dict(evidence: ExecutionEvidence) -> dict[str, Any]:
    """Convert ExecutionEvidence dataclass to dict for archival."""
    return {
        "transport": evidence.transport,
        "screenshots": list(evidence.screenshots),
        "dom_snapshots": list(evidence.dom_snapshots),
        "har_path": evidence.har_path or "",
        "console_logs": list(evidence.console_logs),
        "network_logs": list(evidence.network_logs),
    }
