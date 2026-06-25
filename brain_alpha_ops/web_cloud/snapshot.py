"""Re-export from the ``snapshot`` subpackage for backward compatibility.

The original monolithic ``snapshot.py`` was split into the
``brain_alpha_ops.web_cloud.snapshot`` subpackage. This module remains as a
thin re-export shim so that any legacy imports of the form
``from brain_alpha_ops.web_cloud.snapshot import X`` continue to work.

Note: when both a package (``snapshot/``) and a module (``snapshot.py``) share
the same name, Python loads the package. This file therefore only runs if it
is loaded explicitly by file path. It is kept intentionally minimal.
"""

from __future__ import annotations

# Re-export the full public API surface of the subpackage.
from brain_alpha_ops.web_cloud.snapshot import *  # noqa: F401,F403

# Explicitly re-export private symbols so test monkeypatch/patch against
# ``brain_alpha_ops.web_cloud.snapshot._xxx`` keeps working when this shim is
# loaded directly by path.
from brain_alpha_ops.web_cloud.snapshot._cloud_alpha import _bounded_rows  # noqa: F401
from brain_alpha_ops.web_cloud.snapshot._constants import _safe_error_message  # noqa: F401
from brain_alpha_ops.web_cloud.snapshot._official_context_read import _metadata_int  # noqa: F401
from brain_alpha_ops.web_cloud.snapshot._refresh_service import (  # noqa: F401
    _cloud_refresh_progress_message,
)
