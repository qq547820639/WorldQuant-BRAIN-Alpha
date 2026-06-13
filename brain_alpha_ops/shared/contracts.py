"""Cross-context service contracts using typing.Protocol.

All interfaces defined here are structural — any object that satisfies
the protocol can be used. No import-time coupling to implementations.

P3-5: added ``enforce_protocol`` for runtime enforcement.  ``@runtime_checkable``
Protocol still allows isinstance() checks, but the helper makes the
contract explicit at construction sites (e.g. ``enforce_protocol(store,
JobStore)`` in DI wiring) so an accidental drop of a method is caught
immediately rather than at first call.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

def enforce_protocol(obj: Any, protocol: type) -> None:
    """Raise ``TypeError`` if ``obj`` does not satisfy ``protocol``.

    Cheap structural check: looks for every method name declared on the
    protocol.  Use at construction time, not in hot loops.
    """
    if not isinstance(protocol, type):
        raise TypeError(f"enforce_protocol: protocol must be a class, got {type(protocol).__name__}")
    method_names = [
        name
        for name in dir(protocol)
        if not name.startswith("_")
        and callable(getattr(protocol, name, None))
    ]
    missing = [name for name in method_names if not callable(getattr(obj, name, None))]
    if missing:
        raise TypeError(
            f"object {type(obj).__name__!r} does not satisfy "
            f"{protocol.__name__}: missing {missing!r}"
        )

# ── Phase State Provider ────────────────────────────────────

@runtime_checkable
class PhaseStateProvider(Protocol):
    """Provides phase progression state for frontend PhaseShell."""

    def get_phase_state(self) -> dict[str, Any]:
        """
        Returns phase state dict consumed by frontend usePhaseState().

        Fields:
            current_phase: "connect" | "discover" | "evaluate" | "ready"
            connected: bool
            context_fresh: bool
            candidates_count: int
            scored_count: int
            readiness_passed: bool
            sync: { in_progress, scanned, total, elapsed_seconds, stalled }
            connection: { status, last_tested_at, credential_source }
            readiness: { eligible_count, ready }
        """
        ...

# ── Progress Reporter ───────────────────────────────────────

@runtime_checkable
class ProgressReporter(Protocol):
    """Reports job progress from research/web context to UI layer."""

    def report(
        self,
        phase: str,
        message: str,
        *,
        percent: float | None = None,
        scanned: int = 0,
        total: int = 0,
        elapsed_seconds: float = 0,
        eta_seconds: float | None = None,
    ) -> None: ...

    def is_cancelled(self) -> bool: ...

# ── Data Layer Interfaces ───────────────────────────────────

@runtime_checkable
class CloudCache(Protocol):
    """Read-only view of cloud alpha snapshot cache."""

    def count(self) -> int: ...
    def last_sync_at(self) -> float | None: ...
    def is_fresh(self, max_age_seconds: float = 86400) -> bool: ...

@runtime_checkable
class JobStore(Protocol):
    """Generic background job storage."""

    def create(self, data: dict[str, Any] | None = None) -> str: ...
    def get(self, job_id: str) -> dict[str, Any] | None: ...
    def update(self, job_id: str, **kwargs: Any) -> None: ...
    def cancel(self, job_id: str) -> None: ...
    def is_cancelled(self, job_id: str) -> bool: ...
    def latest_active(self) -> tuple[str, dict[str, Any]] | None: ...
    def list_all(self) -> list[tuple[str, dict[str, Any]]]: ...

# ── Event Publisher (v4.1) ──────────────────────────────────

@runtime_checkable
class EventPublisher(Protocol):
    """Publishes domain events for cross-context communication."""

    def publish(self, event_type: str, payload: dict[str, Any]) -> None: ...
    def subscribe(self, event_type: str, handler: Any) -> None: ...
    def unsubscribe(self, event_type: str, handler: Any) -> None: ...
