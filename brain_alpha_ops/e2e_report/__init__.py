"""Re-export from the ``e2e_report`` subpackage for backward compatibility."""
from __future__ import annotations

from brain_alpha_ops.e2e_report._constants import *  # noqa: F401,F403
from brain_alpha_ops.e2e_report._evidence import *  # noqa: F401,F403
from brain_alpha_ops.e2e_report._ledger import *  # noqa: F401,F403
from brain_alpha_ops.e2e_report._contract import *  # noqa: F401,F403
from brain_alpha_ops.e2e_report._summary import *  # noqa: F401,F403

from brain_alpha_ops.e2e_report._constants import (  # noqa: F401
    _display_path,
    _markdown_cell,
    _numeric,
    _read_text,
    _resolve_under_root,
    logger,
)
from brain_alpha_ops.e2e_report._evidence import (  # noqa: F401
    _classify_evidence_file,
    _console_line_severity,
    _index_evidence_files,
    _is_notable_console_line,
    _read_console_logs,
    _read_summary_jsons,
)
from brain_alpha_ops.e2e_report._ledger import (  # noqa: F401
    _compact_value,
    _is_result_summary_key,
    _read_job_ledger,
    _summarize_job,
    _summarize_leaf,
    _summarize_result,
)
from brain_alpha_ops.e2e_report._contract import _read_web_console_contract  # noqa: F401

__all__ = [
    # Public constants from _constants
    "SCHEMA_VERSION",
    "DEFAULT_EVIDENCE_DIR",
    "DEFAULT_JOB_LEDGER_PATHS",
    "IMAGE_SUFFIXES",
    "TEXT_PREVIEW_BYTES",
    "CONSOLE_PREVIEW_LINES",
    "JOB_PREVIEW_LIMIT",
    "LIST_PREVIEW_LIMIT",
    "SKIPPED_RESULT_KEYS",
    "RESULT_SUMMARY_KEYWORDS",
    "logger",
    # Public API from _summary
    "build_e2e_artifact_summary",
    "render_markdown_summary",
    # Private symbols re-exported for test monkeypatch compatibility
    "_display_path",
    "_markdown_cell",
    "_numeric",
    "_read_text",
    "_resolve_under_root",
    "_classify_evidence_file",
    "_console_line_severity",
    "_index_evidence_files",
    "_is_notable_console_line",
    "_read_console_logs",
    "_read_summary_jsons",
    "_compact_value",
    "_is_result_summary_key",
    "_read_job_ledger",
    "_summarize_job",
    "_summarize_leaf",
    "_summarize_result",
    "_read_web_console_contract",
]
