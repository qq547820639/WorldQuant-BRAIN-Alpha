from __future__ import annotations

from scripts.check_log_redaction import check_log_redaction


def _write_module(tmp_path, text: str):
    path = tmp_path / "sample.py"
    path.write_text(text, encoding="utf-8")
    return path


def test_log_redaction_guard_accepts_current_package():
    result = check_log_redaction()

    assert result["ok"] is True
    assert result["schema_version"] == "log_redaction_check.v1"
    assert result["finding_count"] == 0


def test_log_redaction_guard_rejects_raw_exception_and_fstrings(tmp_path):
    path = _write_module(
        tmp_path,
        """
import logging

logger = logging.getLogger(__name__)

def run(exc, expression):
    logger.warning("boom: %s", exc)
    logger.error(f"failed: {expression}")
    logger.exception("unexpected error evaluating expression: %s", expression)
""",
    )

    result = check_log_redaction(path)

    assert result["ok"] is False
    assert {finding["code"] for finding in result["findings"]} == {
        "logger_fstring",
        "raw_exception_log_arg",
        "raw_user_value_log_arg",
    }


def test_log_redaction_guard_allows_redacted_helpers(tmp_path):
    path = _write_module(
        tmp_path,
        """
import logging

from brain_alpha_ops.redaction import redact_error_message, redact_text

logger = logging.getLogger(__name__)

def run(exc, expression):
    logger.warning("boom: %s", redact_error_message(exc))
    logger.error("failed: %s", redact_text(expression, max_length=80))
""",
    )

    result = check_log_redaction(path)

    assert result["ok"] is True
    assert result["finding_count"] == 0
