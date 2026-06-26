"""Strategy plugin loading, summary, and notification helpers."""

from __future__ import annotations

from ..strategy_plugins import StrategyPluginRegistry


class PipelineStrategyPluginsMixin:
    def _load_strategy_plugins(self) -> StrategyPluginRegistry:
        if not getattr(self.config.budget, "strategy_plugins_enabled", False):
            return StrategyPluginRegistry()
        registry = StrategyPluginRegistry.from_specs(list(self.config.budget.strategy_plugin_specs or []))
        if registry.plugins:
            self._event(
                "strategy_plugins_loaded",
                f"Loaded strategy plugins: {', '.join(registry.names())}",
                data={"strategy_plugins": registry.summary()},
                level="INFO",
            )
        if registry.load_errors:
            self._event(
                "strategy_plugins_load_error",
                f"Strategy plugin load errors: {len(registry.load_errors)}",
                data={"strategy_plugins": registry.summary()},
                level="WARN",
            )
        return registry

    def _strategy_plugin_summary(self) -> dict:
        summary = self.strategy_plugins.summary()
        summary.update(
            {
                "enabled": bool(getattr(self.config.budget, "strategy_plugins_enabled", False)),
                "configured_specs": list(getattr(self.config.budget, "strategy_plugin_specs", []) or []),
            }
        )
        return summary

    def _notify_strategy_plugins(
        self,
        action: str,
        profile: dict,
        *,
        cycle: int,
        reason: str = "",
        **context: object,
    ) -> list[dict]:
        if not self.strategy_plugins.plugins:
            return []
        payload = {
            "cycle": int(cycle or 0),
            "reason": str(reason or ""),
            "active_profile": self.services.strategy._current_strategy_profile(),
            "active_profile_index": self.strategy_profile_index,
            "strategy_switch_count": self.strategy_switch_count,
            "official_results_since_strategy_switch": self.official_results_since_strategy_switch,
            "ready_since_strategy_switch": self.ready_since_strategy_switch,
            "official_rejections_since_strategy_switch": self.official_rejections_since_strategy_switch,
            "settings": self.config.settings.to_platform_dict()["settings"],
            **context,
        }
        rows = self.strategy_plugins.notify(action, profile=dict(profile or {}), context=payload)
        for row in rows:
            if row.get("status") == "error":
                self._event(
                    "strategy_plugin_error",
                    f"{row.get('plugin')} {action} failed: {row.get('error')}",
                    data={"strategy_plugin": row},
                    level="WARN",
                )
        return rows
