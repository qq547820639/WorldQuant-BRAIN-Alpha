"""Strategy plugin registry and loader."""

from __future__ import annotations

from dataclasses import dataclass, field
import importlib
from typing import Any

from .strategy_lifecycle import StrategyLifecyclePlugin


REQUIRED_PLUGIN_METHODS = ("propose", "validate", "mutate", "retire")


@dataclass
class StrategyPluginRegistry:
    plugins: dict[str, StrategyLifecyclePlugin] = field(default_factory=dict)
    load_errors: list[dict[str, str]] = field(default_factory=list)
    runtime_events: list[dict[str, Any]] = field(default_factory=list)
    runtime_errors: list[dict[str, str]] = field(default_factory=list)

    @classmethod
    def from_specs(cls, specs: list[str]) -> "StrategyPluginRegistry":
        registry = cls()
        for spec in specs:
            try:
                registry.register(load_strategy_plugin(spec), spec=spec)
            except Exception as exc:
                registry.load_errors.append({"spec": str(spec), "error": str(exc)})
        return registry

    def register(self, plugin: StrategyLifecyclePlugin, *, spec: str = "") -> None:
        name = str(getattr(plugin, "name", "") or spec or plugin.__class__.__name__).strip()
        if not name:
            raise ValueError("strategy plugin name is required")
        missing = [method for method in REQUIRED_PLUGIN_METHODS if not callable(getattr(plugin, method, None))]
        if missing:
            raise ValueError(f"strategy plugin '{name}' missing methods: {', '.join(missing)}")
        self.plugins[name] = plugin

    def get(self, name: str) -> StrategyLifecyclePlugin | None:
        return self.plugins.get(name)

    def names(self) -> list[str]:
        return sorted(self.plugins)

    def notify(
        self,
        action: str,
        *,
        profile: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if action not in REQUIRED_PLUGIN_METHODS:
            raise ValueError(f"unsupported strategy plugin action: {action}")
        rows: list[dict[str, Any]] = []
        for name, plugin in self.plugins.items():
            try:
                method = getattr(plugin, action)
                if action == "propose":
                    result = method(dict(context or {}))
                else:
                    result = method(dict(profile or {}), dict(context or {}))
                row = {
                    "plugin": name,
                    "action": action,
                    "status": "ok",
                    "result": result if isinstance(result, dict) else {"value": result},
                }
                rows.append(row)
                self.runtime_events.append(row)
            except Exception as exc:
                row = {"plugin": name, "action": action, "error": str(exc)}
                self.runtime_errors.append(row)
                rows.append({"plugin": name, "action": action, "status": "error", "error": str(exc)})
        self.runtime_events = self.runtime_events[-100:]
        self.runtime_errors = self.runtime_errors[-100:]
        return rows

    def summary(self) -> dict[str, Any]:
        return {
            "schema_version": "strategy_plugin_registry.v1",
            "enabled_count": len(self.plugins),
            "plugin_names": self.names(),
            "load_errors": list(self.load_errors),
            "runtime_events": list(self.runtime_events[-50:]),
            "runtime_errors": list(self.runtime_errors[-50:]),
        }


def load_strategy_plugin(spec: str) -> StrategyLifecyclePlugin:
    module_name, sep, attr_name = str(spec or "").partition(":")
    if not module_name or not sep or not attr_name:
        raise ValueError("strategy plugin spec must be in 'module:object' format")
    module = importlib.import_module(module_name)
    plugin = getattr(module, attr_name)
    if isinstance(plugin, type):
        plugin = plugin()
    return plugin
