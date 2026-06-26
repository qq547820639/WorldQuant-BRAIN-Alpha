"""Runtime, config, job and session binding imports for the web facade.

Re-export shim that pulls runtime/config/job/session helpers from the
consolidated bindings modules so ``build_web_facade_bindings`` can wire them
into the namespace. Extracted from the former ``web_facade_bindings.py``
monolith (deep-optimization-phase12, Task B8).
"""

from __future__ import annotations

from brain_alpha_ops.web_config_bindings import (
    config_from_payload as _config_from_payload,
)
from brain_alpha_ops.web_config_bindings import (
    load_run_config_provider as _load_run_config_provider,
)
from brain_alpha_ops.web_config_bindings import (
    run_config_from_payload as _run_config_from_payload,
)
from brain_alpha_ops.web_config_bindings import (
    runtime_project_root_provider as _runtime_project_root_provider,
)
from brain_alpha_ops.web_config_bindings import (
    save_run_config_payload as _save_run_config_payload,
)
from brain_alpha_ops.web_job_bindings import (
    active_auxiliary_operation as _active_auxiliary_operation,
)
from brain_alpha_ops.web_job_bindings import (
    job_registry as _job_registry,
)
from brain_alpha_ops.web_job_bindings import (
    job_registry_view as _job_registry_view,
)
from brain_alpha_ops.web_job_bindings import (
    rate_limit_request as _rate_limit_request,
)
from brain_alpha_ops.web_job_bindings import (
    submit_background_job as _submit_background_job,
)
from brain_alpha_ops.web_runtime_bindings import (
    alpha_lifecycle_history as _alpha_lifecycle_history,
)
from brain_alpha_ops.web_runtime_bindings import (
    compute_run_stats as _compute_run_stats,
)
from brain_alpha_ops.web_runtime_bindings import (
    find_free_port as _find_free_port,
)
from brain_alpha_ops.web_runtime_bindings import (
    handler_dispatch_context as _handler_dispatch_context,
)
from brain_alpha_ops.web_runtime_bindings import (
    lifecycle_from_job as _lifecycle_from_job,
)
from brain_alpha_ops.web_runtime_bindings import (
    lookup_sse_job as _lookup_sse_job,
)
from brain_alpha_ops.web_runtime_bindings import (
    main as _main,
)
from brain_alpha_ops.web_runtime_bindings import (
    maybe_archive_lifecycle as _maybe_archive_lifecycle,
)
from brain_alpha_ops.web_runtime_bindings import (
    run_job as _run_job,
)
from brain_alpha_ops.web_runtime_bindings import (
    serve as _serve,
)
from brain_alpha_ops.web_runtime_bindings import (
    shutdown_server as _shutdown_server,
)
from brain_alpha_ops.web_runtime_bindings import (
    smoke_test_server as _smoke_test_server,
)
from brain_alpha_ops.web_runtime_bindings import (
    test_connection as _test_connection,
)
from brain_alpha_ops.web_session_bindings import (
    configure_session_policy as _configure_session_policy,
)
from brain_alpha_ops.web_session_bindings import (
    normalize_host as _normalize_host,
)

__all__ = [
    "_active_auxiliary_operation",
    "_alpha_lifecycle_history",
    "_compute_run_stats",
    "_config_from_payload",
    "_configure_session_policy",
    "_find_free_port",
    "_handler_dispatch_context",
    "_job_registry",
    "_job_registry_view",
    "_lifecycle_from_job",
    "_load_run_config_provider",
    "_lookup_sse_job",
    "_main",
    "_maybe_archive_lifecycle",
    "_normalize_host",
    "_rate_limit_request",
    "_run_config_from_payload",
    "_run_job",
    "_runtime_project_root_provider",
    "_save_run_config_payload",
    "_serve",
    "_shutdown_server",
    "_smoke_test_server",
    "_submit_background_job",
    "_test_connection",
]
