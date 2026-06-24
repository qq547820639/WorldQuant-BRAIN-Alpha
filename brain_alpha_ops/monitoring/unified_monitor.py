"""UnifiedMonitor — bridge browser health checks + backend job stall detection.

Combines ``BrowserMonitor`` (Playwright health) and ``StallMonitor`` (job
progress) into a single monitoring facade. Makes coordinated decisions:

- Browser heartbeat failure + job stall → CRITICAL → auto-interrupt
- Browser DOM broken → auto-heal (page refresh)
- Console errors → screenshot + DOM snapshot
- Network failures → retry or interrupt based on severity
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from brain_alpha_ops.redaction import redact_error_message

logger = logging.getLogger(__name__)


class Severity(Enum):
    OK = "ok"
    WARNING = "warning"
    DEGRADED = "degraded"
    CRITICAL = "critical"


@dataclass
class MonitorEvent:
    """Unified event emitted by the monitor."""
    severity: Severity
    source: str  # "browser" | "backend" | "unified"
    message: str
    timestamp: float = field(default_factory=time.time)
    details: dict[str, Any] = field(default_factory=dict)
    action: str = "log"  # "log" | "heal" | "retry" | "interrupt" | "snapshot"


@dataclass
class UnifiedHealth:
    """Aggregated health across all monitoring sources."""
    overall: Severity
    browser: dict[str, Any] | None = None
    backend: dict[str, Any] | None = None
    events: list[MonitorEvent] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    @property
    def healthy(self) -> bool:
        return self.overall in (Severity.OK, Severity.WARNING)

    @property
    def needs_interrupt(self) -> bool:
        return self.overall == Severity.CRITICAL


class UnifiedMonitor:
    """Unified monitoring across browser and backend job health.

    Usage::

        monitor = UnifiedMonitor(browser_monitor=bmon, stall_monitor=smon)
        health = monitor.check()
        if not health.healthy:
            monitor.heal(health)
    """

    def __init__(self, browser_monitor=None, stall_monitor=None):
        """Create unified monitor.

        Args:
            browser_monitor: ``BrowserMonitor`` instance (optional — for browser mode).
            stall_monitor: ``StallMonitor`` instance (optional — for job monitoring).
        """
        self._browser = browser_monitor
        self._stall = stall_monitor
        self._history: deque[UnifiedHealth] = deque(maxlen=1000)

    def check(self) -> UnifiedHealth:
        """Run all health checks and return unified status."""
        events: list[MonitorEvent] = []
        browser_health = None
        backend_health = None

        # — Browser health —
        if self._browser is not None:
            try:
                browser_health = self._browser.check_health()
                events.extend(self._translate_browser_health(browser_health))
            except Exception as e:
                events.append(MonitorEvent(
                    severity=Severity.CRITICAL,
                    source="browser",
                    message=f"Browser health check failed: {e}",
                    action="interrupt",
                ))

        # — Backend job health —
        if self._stall is not None:
            try:
                backend_health = self._stall.check()
                events.extend(self._translate_backend_health(backend_health))
            except Exception as e:
                events.append(MonitorEvent(
                    severity=Severity.WARNING,
                    source="backend",
                    message=f"Backend health check failed: {e}",
                    action="log",
                ))

        # — Cross-source correlation —
        if browser_health and backend_health:
            b_degraded = not browser_health.get("healthy", True)
            s_stalled = self._is_stalled(backend_health)
            if b_degraded and s_stalled:
                events.append(MonitorEvent(
                    severity=Severity.CRITICAL,
                    source="unified",
                    message="Browser degraded AND job stalled — critical failure",
                    action="interrupt",
                    details={"browser": browser_health, "backend": backend_health},
                ))

        # Determine overall severity
        severities = [e.severity for e in events]
        if Severity.CRITICAL in severities:
            overall = Severity.CRITICAL
        elif Severity.DEGRADED in severities:
            overall = Severity.DEGRADED
        elif Severity.WARNING in severities:
            overall = Severity.WARNING
        else:
            overall = Severity.OK

        health = UnifiedHealth(
            overall=overall,
            browser=browser_health,
            backend=backend_health,
            events=events,
        )
        self._history.append(health)
        return health

    def heal(self, health: UnifiedHealth) -> list[str]:
        """Attempt healing actions based on health events.

        Returns list of actions taken.
        """
        actions: list[str] = []
        for event in health.events:
            if event.action == "interrupt":
                if self._stall is not None:
                    self._stall.auto_interrupt()
                    actions.append("backend_interrupt")
            elif event.action == "heal" and self._browser is not None:
                try:
                    healed = self._browser.auto_heal(
                        health.browser or {}
                    )
                    if healed:
                        actions.append("browser_auto_heal")
                except Exception as e:
                    logger.warning("Auto-heal failed: %s", redact_error_message(e))
            elif event.action == "snapshot" and self._browser is not None:
                try:
                    runner = getattr(self._browser, "runner", None)
                    if runner is not None and hasattr(runner, "_take_screenshot"):
                        runner._take_screenshot(
                            f"monitor_event_{int(time.time())}"
                        )
                    actions.append("browser_snapshot")
                except Exception as e:
                    logger.warning("Browser snapshot capture failed: %s", redact_error_message(e))

        logger.info("Healing actions: %s", actions)
        return actions

    # ---- Private helpers ----

    @staticmethod
    def _translate_browser_health(browser_health: dict) -> list[MonitorEvent]:
        events: list[MonitorEvent] = []
        for issue in browser_health.get("issues", []):
            sev = issue.get("severity", "medium")
            severity = (
                Severity.CRITICAL if sev == "critical"
                else Severity.DEGRADED if sev == "high"
                else Severity.WARNING
            )
            action = (
                "heal" if issue.get("type") in ("dom_broken", "heartbeat_stale")
                else "snapshot" if issue.get("type") == "console_errors"
                else "log"
            )
            events.append(MonitorEvent(
                severity=severity,
                source="browser",
                message=issue.get("message", "Unknown browser issue"),
                action=action,
                details=issue,
            ))
        return events

    @staticmethod
    def _translate_backend_health(backend_health: dict) -> list[MonitorEvent]:
        events: list[MonitorEvent] = []
        stalled_jobs = backend_health.get("stalled_jobs", [])
        for job in stalled_jobs:
            events.append(MonitorEvent(
                severity=Severity.DEGRADED,
                source="backend",
                message=f"Job {job.get('job_id', '?')} stalled: {job.get('status', 'unknown')}",
                action="interrupt",
                details=job,
            ))
        if not stalled_jobs and not backend_health.get("healthy", True):
            events.append(MonitorEvent(
                severity=Severity.WARNING,
                source="backend",
                message="Backend health degraded",
                action="log",
            ))
        return events

    @staticmethod
    def _is_stalled(backend_health: dict) -> bool:
        return len(backend_health.get("stalled_jobs", [])) > 0
