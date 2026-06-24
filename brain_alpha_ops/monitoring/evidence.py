"""Evidence archival for browser interactions."""
from __future__ import annotations
import os
import json
import time
import shutil
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

class EvidenceArchival:
    """Archives browser interaction evidence (screenshots, DOM, HAR, logs)."""
    
    def __init__(self, evidence_dir: str = "artifacts/evidence", retention_days: int = 30):
        self.evidence_dir = Path(evidence_dir)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.retention_days = retention_days
    
    def archive_session(self, session_id: str, evidence: dict[str, Any]) -> str:
        """Archive evidence from a browser session."""
        import re
        sanitized = re.sub(r'[^a-zA-Z0-9_\-]', '_', session_id)
        session_dir = self.evidence_dir / sanitized
        session_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy screenshots
        screenshots_dir = session_dir / "screenshots"
        screenshots_dir.mkdir(exist_ok=True)
        for i, path in enumerate(evidence.get("screenshots", [])):
            if os.path.exists(path):
                shutil.copy2(path, screenshots_dir / f"{i:03d}_{os.path.basename(path)}")
        
        # Copy DOM snapshots
        dom_dir = session_dir / "dom_snapshots"
        dom_dir.mkdir(exist_ok=True)
        for i, path in enumerate(evidence.get("dom_snapshots", [])):
            if os.path.exists(path):
                shutil.copy2(path, dom_dir / f"{i:03d}_{os.path.basename(path)}")
        
        # Save logs as JSON
        for log_type in ["console_logs", "network_logs", "errors"]:
            if evidence.get(log_type):
                with open(session_dir / f"{log_type}.json", "w") as f:
                    json.dump(evidence[log_type], f, indent=2, default=str)
        
        # Save metadata
        metadata = {
            "session_id": session_id,
            "archived_at": time.time(),
            "transport": evidence.get("transport", "unknown"),
            "screenshot_count": len(evidence.get("screenshots", [])),
            "dom_snapshot_count": len(evidence.get("dom_snapshots", [])),
            "console_log_count": len(evidence.get("console_logs", [])),
            "error_count": len(evidence.get("errors", [])),
        }
        with open(session_dir / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)
        
        logger.info("Archived evidence for session %s to %s", session_id, session_dir)
        return str(session_dir)
    
    def cleanup_old(self):
        """Remove evidence older than retention period."""
        cutoff = time.time() - (self.retention_days * 86400)
        for session_dir in self.evidence_dir.iterdir():
            if session_dir.is_dir():
                metadata_path = session_dir / "metadata.json"
                if metadata_path.exists():
                    with open(metadata_path) as f:
                        metadata = json.load(f)
                    if metadata.get("archived_at", 0) < cutoff:
                        shutil.rmtree(session_dir)
                        logger.info("Cleaned up old evidence: %s", session_dir.name)
    
    def list_sessions(self) -> list[dict]:
        """List all archived sessions."""
        sessions = []
        for session_dir in self.evidence_dir.iterdir():
            if session_dir.is_dir():
                metadata_path = session_dir / "metadata.json"
                if metadata_path.exists():
                    with open(metadata_path) as f:
                        sessions.append(json.load(f))
        return sorted(sessions, key=lambda s: s.get("archived_at", 0), reverse=True)
