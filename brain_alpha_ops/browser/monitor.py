from __future__ import annotations
import time
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

@dataclass
class MonitorConfig:
    heartbeat_interval: float = 10.0
    max_heartbeat_age: float = 15.0
    max_consecutive_errors: int = 3
    max_network_failures: int = 3
    auto_heal_attempts: int = 2

class BrowserMonitor:
    """Monitors browser session health and triggers auto-healing."""

    def __init__(self, runner, config: MonitorConfig | None = None):
        self.runner = runner
        self.config = config or MonitorConfig()
        self._consecutive_errors = 0
        self._network_failures = 0
        self._heal_attempts = 0
        self._last_heartbeat = time.time()

    def check_health(self) -> dict[str, Any]:
        """Run all health checks and return status."""
        issues = []

        heartbeat_ok = self.runner.heartbeat()
        if not heartbeat_ok:
            issues.append({"type": "heartbeat", "severity": "high", "message": "Browser page not responding"})

        age = time.time() - self.runner.state.last_heartbeat_ts
        if age > self.config.max_heartbeat_age:
            issues.append({"type": "heartbeat_stale", "severity": "medium", "message": f"Heartbeat stale for {age:.1f}s"})

        recent_errors = [e for e in self.runner.state.console_logs if e["type"] == "error"]
        if len(recent_errors) > self.config.max_consecutive_errors:
            issues.append({"type": "console_errors", "severity": "high", "message": f"{len(recent_errors)} console errors"})
            self._consecutive_errors = len(recent_errors)

        failed_requests = [r for r in self.runner.state.network_logs if r.get("phase") == "response" and r.get("status", 200) >= 400]
        if len(failed_requests) > self.config.max_network_failures:
            issues.append({"type": "network_failures", "severity": "high", "message": f"{len(failed_requests)} failed requests"})
            self._network_failures = len(failed_requests)

        try:
            root_exists = self.runner._page.locator("#root").count() > 0
            if not root_exists:
                issues.append({"type": "dom_broken", "severity": "critical", "message": "Root DOM element missing"})
        except Exception as e:
            issues.append({"type": "dom_check_failed", "severity": "high", "message": str(e)})

        health = {
            "healthy": len([i for i in issues if i["severity"] in ("high", "critical")]) == 0,
            "issues": issues,
            "heartbeat_age": age,
            "consecutive_errors": self._consecutive_errors,
            "network_failures": self._network_failures,
        }
        return health

    def auto_heal(self, health: dict[str, Any]) -> bool:
        """Attempt automatic healing based on health issues."""
        if self._heal_attempts >= self.config.auto_heal_attempts:
            logger.warning("Max heal attempts reached, aborting")
            return False

        self._heal_attempts += 1
        for issue in health.get("issues", []):
            if issue["type"] == "dom_broken":
                logger.info("Healing: refreshing page")
                try:
                    self.runner._page.reload(wait_until="domcontentloaded")
                    return True
                except Exception:
                    pass
            elif issue["type"] == "heartbeat_stale":
                logger.info("Healing: clicking page to trigger activity")
                try:
                    self.runner._page.mouse.click(100, 100)
                    return True
                except Exception:
                    pass
        return False
