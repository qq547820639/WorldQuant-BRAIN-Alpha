"""GET and POST request dispatch functions."""

from __future__ import annotations

import json
import logging
from typing import Any

from brain_alpha_ops.config import load_run_config
from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.web_backtest_slots import (
    backtest_slots_payload as _shared_backtest_slots_payload,
)
from brain_alpha_ops.web_candidates.payloads import (
    annotate_candidate_rows as _annotate_candidate_rows,
)
from brain_alpha_ops.web_candidates.payloads import (
    candidate_main_pool as _candidate_main_pool,
)
from brain_alpha_ops.web_candidates.payloads import (
    candidate_pool_summary as _candidate_pool_summary,
)
from brain_alpha_ops.web_candidates.payloads import (
    candidate_summary as _candidate_rows_summary,
)
from brain_alpha_ops.web_candidates.payloads import (
    candidate_summary_from_iter as _candidate_rows_summary_from_iter,
)
from brain_alpha_ops.web_candidates.workflow import (
    candidate_workflow_plan as _candidate_workflow_plan,
)
from brain_alpha_ops.web_session import session_status as _web_session_status
from brain_alpha_ops.web_submit_readiness import (
    submit_readiness_payload as _build_submit_readiness_payload,
)

from ._helpers import (
    _backtest_slots_payload,
    _candidate_lifecycle_rows,
    _candidate_target_pool_size,
    _cloud_snapshot_payload,
    _iter_jsonl_records,
    _jsonl_payload,
    _latest_result_payload,
    _public_config,
    _query_limit,
    _query_text,
    _read_jsonl_records,
    _read_jsonl_tail,
    _status_payload,
    _submit_readiness_payload,
)
from ._post_handlers import (
    _handle_candidate_check,
    _handle_candidate_simulate,
    _handle_candidate_submit,
    _handle_config_update,
    _handle_pipeline_start,
    _handle_pipeline_stop,
)
from ..web_get_handlers import health_payload as _health_payload

logger = logging.getLogger(__name__)

# NOTE: The legacy ``dispatch_get`` / ``dispatch_post`` functions that lived
# here were removed as part of the dual-dispatch cleanup.  The canonical
# dispatch entry points now live in
# ``brain_alpha_ops.web.dispatch.web_handler_dispatch`` and use a
# ``(handler, parsed, ctx)`` signature.  The imports above are retained so
# that any code referencing this module's namespace continues to resolve.
