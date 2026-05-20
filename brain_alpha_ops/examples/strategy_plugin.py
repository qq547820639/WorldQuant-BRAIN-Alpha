"""Example strategy lifecycle plugin.

Use the spec below in the web console or config file:

brain_alpha_ops.examples.strategy_plugin:ConservativeMeanReversionPlugin
"""

from __future__ import annotations

from typing import Any


class ConservativeMeanReversionPlugin:
    """Small example plugin that nudges profiles toward conservative reversion."""

    name = "conservative_mean_reversion"

    def propose(self, context: dict[str, Any]) -> dict[str, Any]:
        cycle = int(context.get("cycle") or 0)
        return {
            "profile": {
                "name": "plugin_mean_reversion",
                "family": "mean_reversion",
                "decay": 8 + min(cycle % 4, 3),
                "neutralization": "SUBINDUSTRY",
            },
            "reason": "prefer slower, neutralized reversion candidates",
        }

    def validate(self, profile: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        ready_rate = float(context.get("ready_rate") or 0.0)
        official_results = int(context.get("official_results") or 0)
        return {
            "keep": ready_rate >= 0.05 or official_results < 12,
            "ready_rate": round(ready_rate, 4),
            "official_results": official_results,
        }

    def mutate(self, profile: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        child = dict(profile or {})
        child["name"] = str(child.get("name") or "plugin_profile") + "_mutated"
        child["decay"] = max(2, int(child.get("decay") or 8) - 1)
        child["mutation_reason"] = str(context.get("reason") or "low_ready_rate")
        return {"profile": child}

    def retire(self, profile: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return {
            "retire": True,
            "profile": str((profile or {}).get("name") or "unknown"),
            "reason": str(context.get("reason") or "strategy_lifecycle"),
        }
