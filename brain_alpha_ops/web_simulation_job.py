"""Shared SimJobStore adapter for simulation jobs.

Eliminates the duplicated _SimJobStore class that previously existed in both
web_handler_dispatch.py and web_routes.py, providing a single factory function
that creates the correct adapter for each backend.
"""

from __future__ import annotations

from typing import Any, Protocol


class JobStoreLike(Protocol):
    def update(self, job_id: str, **kwargs: Any) -> None: ...
    def is_cancelled(self, job_id: str) -> bool: ...


def create_sim_job_store(store: Any | None = None) -> JobStoreLike:
    """Create a SimJobStore adapter bridging simulate_candidates_job to a job store.

    Args:
        store: A store object with .update(jid, **kw) and .get(jid) methods
               (used by web_handler_dispatch.py), or None to use the
               web_jobs module-level functions (used by web_routes.py).

    Returns:
        An adapter implementing update(job_id, **kw) and is_cancelled(job_id).
    """
    if store is not None:
        class _StoreAdapter:
            def update(self, jid: str, **kw: Any) -> None:
                store.update(jid, **kw)

            def is_cancelled(self, jid: str) -> bool:
                row = store.get(jid) or {}
                return str(row.get("status", "")).lower() in ("cancelled", "stopped")

        return _StoreAdapter()

    class _WebJobsAdapter:
        def update(self, job_id: str, **kwargs: Any) -> None:
            from brain_alpha_ops.web_jobs import job_update
            job_update(job_id, **kwargs)

        def is_cancelled(self, job_id: str) -> bool:
            from brain_alpha_ops.web_jobs import is_cancelled
            return is_cancelled(job_id)

    return _WebJobsAdapter()
