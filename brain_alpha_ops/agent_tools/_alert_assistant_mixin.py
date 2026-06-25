"""Mixin: alert routing, assistant context building, and anti-overfit /
rolling-validation handlers.

These handlers are thin wrappers around the shared ``agent_research_tools``
implementations.  They are split out of ``BrainAlphaToolbox`` so that the
core class stays under the module-size budget and each concern lives in its
own file.
"""
from __future__ import annotations

from typing import Any

from brain_alpha_ops.agent_research_tools import (
    assistant_response_guidance_tool,
    build_assistant_context_tool,
    build_assistant_request_tool,
    cross_review_assistant_response_tool,
    parse_assistant_response_tool,
    route_alert_from_args,
    run_anti_overfit_tool,
    run_rolling_validation_tool,
    send_alert_tool,
)
from brain_alpha_ops.shared_bounds import required_text


class _AlertAssistantToolsMixin:
    """Handlers for alerts, assistant workflow, and validation tools."""

    def _send_alert(self, args: dict[str, Any]) -> dict[str, Any]:
        title = required_text(args, "title")
        message = required_text(args, "message")
        severity = str(args.get("severity", "info") or "info").strip() or "info"
        channel = str(args.get("channel", "local") or "local").strip() or "local"
        webhook_url = str(args.get("webhook_url", "") or "").strip()
        metadata = dict(args.get("metadata") or {})
        return send_alert_tool(
            self.run_config.ops.storage_dir,
            title=title,
            message=message,
            severity=severity,
            channel=channel,
            webhook_url=webhook_url,
            metadata=metadata,
        )

    def _route_alert(self, args: dict[str, Any]) -> dict[str, Any]:
        return route_alert_from_args(self.run_config.ops.storage_dir, args)

    def _build_assistant_context(self, args: dict[str, Any]) -> dict[str, Any]:
        return build_assistant_context_tool(self.run_config, args)

    def _build_assistant_request(self, args: dict[str, Any]) -> dict[str, Any]:
        return build_assistant_request_tool(self.run_config, args)

    def _parse_assistant_response(self, args: dict[str, Any]) -> dict[str, Any]:
        return parse_assistant_response_tool(args)

    def _assistant_response_guidance(self, args: dict[str, Any]) -> dict[str, Any]:
        return assistant_response_guidance_tool(args)

    def _run_anti_overfit(self, args: dict[str, Any]) -> dict[str, Any]:
        return run_anti_overfit_tool(args)

    def _run_rolling_validation(self, args: dict[str, Any]) -> dict[str, Any]:
        return run_rolling_validation_tool(args)

    def _cross_review_assistant_response(self, args: dict[str, Any]) -> dict[str, Any]:
        return cross_review_assistant_response_tool(args)
