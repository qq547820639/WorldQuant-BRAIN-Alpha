from __future__ import annotations
import time
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from brain_alpha_ops.redaction import redact_error_message

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

        age = time.time() - getattr(self.runner.state, "last_heartbeat_ts", time.time())
        if age > self.config.max_heartbeat_age:
            issues.append({"type": "heartbeat_stale", "severity": "medium", "message": f"Heartbeat stale for {age:.1f}s"})

        recent_errors = [e for e in self.runner.state.console_logs if e["type"] == "error"]
        if len(recent_errors) > self.config.max_consecutive_errors:
            issues.append({"type": "console_errors", "severity": "high", "message": f"{len(recent_errors)} console errors"})
            self._consecutive_errors = len(recent_errors)
        else:
            self._consecutive_errors = 0

        failed_requests = [r for r in self.runner.state.network_logs if r.get("phase") == "response" and r.get("status", 200) >= 400]
        if len(failed_requests) > self.config.max_network_failures:
            issues.append({"type": "network_failures", "severity": "high", "message": f"{len(failed_requests)} failed requests"})
            self._network_failures = len(failed_requests)

        try:
            page = getattr(self.runner, "_page", None)
            if page is not None:
                root_exists = page.locator("#root").count() > 0
            else:
                root_exists = False
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
            "classification": self.classify_fail_closed(issues),
        }
        return health

    def classify_fail_closed(self, issues: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Classify browser health into actionable interrupt decisions."""
        issues = list(issues or [])
        responses = [
            row
            for row in getattr(self.runner.state, "network_logs", [])
            if isinstance(row, dict) and row.get("phase") == "response"
        ]
        if any(row.get("status") == 429 for row in responses):
            return {
                "status": "blocked",
                "code": "BROWSER_RATE_LIMITED",
                "retryable": True,
                "message": "BROWSER_RATE_LIMITED: stop side-effecting browser flow and back off",
            }
        if any(isinstance(row.get("status"), int) and row.get("status") >= 500 for row in responses):
            return {
                "status": "blocked",
                "code": "BROWSER_SERVER_ERROR",
                "retryable": True,
                "message": "BROWSER_SERVER_ERROR: stop side-effecting browser flow",
            }
        if any(issue.get("severity") == "critical" for issue in issues):
            return {
                "status": "blocked",
                "code": "BROWSER_CRITICAL_HEALTH",
                "retryable": False,
                "message": "Critical browser health issue blocks the flow",
            }
        if any(issue.get("severity") == "high" for issue in issues):
            return {
                "status": "warning",
                "code": "BROWSER_DEGRADED",
                "retryable": True,
                "message": "Browser health is degraded",
            }
        return {"status": "ok", "code": "OK", "retryable": False, "message": "Browser health ok"}

    def auto_heal(self, health: dict[str, Any]) -> bool:
        """Attempt automatic healing based on health issues."""
        if self._heal_attempts >= self.config.auto_heal_attempts:
            logger.warning("Max heal attempts reached, aborting")
            return False

        self._heal_attempts += 1
        healed = False
        for issue in health.get("issues", []):
            if issue.get("type") == "dom_broken":
                logger.info("Healing: refreshing page")
                try:
                    page = getattr(self.runner, "_page", None)
                    if page is not None:
                        page.reload(wait_until="domcontentloaded")
                    healed = True
                except Exception as exc:
                    logger.warning("Browser auto-heal reload failed: %s", redact_error_message(exc))
            elif issue.get("type") == "heartbeat_stale":
                logger.info("Healing: clicking page center to trigger activity")
                try:
                    page = getattr(self.runner, "_page", None)
                    if page is not None:
                        page.mouse.click(960, 540)
                    healed = True
                except Exception as exc:
                    logger.warning("Browser auto-heal click failed: %s", redact_error_message(exc))
        return healed
