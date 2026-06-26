"""Web console contract reader for E2E report."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from brain_alpha_ops.redaction import redact_text
from brain_alpha_ops.e2e_report._constants import _display_path, logger

def _read_web_console_contract(root: Path) -> dict[str, Any]:
    html_path = root / "brain_alpha_ops" / "web" / "index.html"
    if not html_path.is_file():
        return {
            "ok": False,
            "schema_version": "web_console_contract_check.v1",
            "html": _display_path(html_path, root),
            "facts": {},
            "findings": [{"code": "missing_html", "expected": str(html_path), "message": "HTML file does not exist"}],
        }
    try:
        from scripts.check_web_console_contract import check_web_console_contract
    except Exception as exc:  # pragma: no cover - defensive for packaged use without scripts.
        logger.warning("web console contract checker unavailable while building E2E summary", exc_info=True)
        return {
            "ok": False,
            "schema_version": "web_console_contract_check.v1",
            "html": _display_path(html_path, root),
            "facts": {},
            "findings": [
                {
                    "code": "checker_unavailable",
                    "expected": "scripts.check_web_console_contract",
                    "message": redact_text(exc, max_length=240),
                }
            ],
        }
    result = check_web_console_contract(html_path)
    result["html"] = _display_path(Path(result.get("html") or html_path), root)
    return result
