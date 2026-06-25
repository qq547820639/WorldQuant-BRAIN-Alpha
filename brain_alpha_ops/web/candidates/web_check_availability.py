"""Re-export from the ``web_check_availability`` subpackage for backward compatibility.

The original monolithic ``web_check_availability.py`` was split into the
``brain_alpha_ops.web.candidates.web_check_availability`` subpackage. This
module remains as a thin re-export shim so that any legacy imports of the form
``from brain_alpha_ops.web.candidates.web_check_availability import X``
(plus the ``brain_alpha_ops.web_check_availability`` bridge alias) continue
to work.

Note: when both a package (``web_check_availability/``) and a module
(``web_check_availability.py``) share the same name, Python loads the
package. This file therefore only runs if it is loaded explicitly by file
path. It is kept intentionally minimal.
"""

from __future__ import annotations

# Re-export the full public API surface of the subpackage.
from brain_alpha_ops.web.candidates.web_check_availability import *  # noqa: F401,F403

# Explicitly re-export private symbols so test monkeypatch/patch against
# ``brain_alpha_ops.web.candidates.web_check_availability._xxx`` keeps working
# when this shim is loaded directly by path.
from brain_alpha_ops.web.candidates.web_check_availability._availability import (  # noqa: F401
    _cloud_self_correlation_check_context,
    _submission_decision_band,
)
from brain_alpha_ops.web.candidates.web_check_availability._batch_helpers import (  # noqa: F401
    _store_is_cancelled,
    _timing_payload,
    _update_check_batch_cancelled,
)
from brain_alpha_ops.web.candidates.web_check_availability._batch_job import (  # noqa: F401
    run_check_batch_job_service,
)
from brain_alpha_ops.web.candidates.web_check_availability._risk_explanations import (  # noqa: F401
    _default_resolution_steps,
    _float,
    _int,
    _risk_level,
)
