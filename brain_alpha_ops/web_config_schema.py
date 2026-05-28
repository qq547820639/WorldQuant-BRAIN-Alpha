"""Public schema for the web production configuration panel."""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.brain_api.canonical import CANONICAL_SETTINGS


def _sorted_values(values: set[Any]) -> list[Any]:
    return sorted(values)


def public_config_schema() -> dict[str, Any]:
    """Return the auditable UI-to-backend contract for production config."""

    settings_options = {key: _sorted_values(values) for key, values in CANONICAL_SETTINGS.items()}
    return {
        "schema_version": "web_config_schema.v1",
        "environment": {
            "allowed": ["production"],
            "default": "production",
        },
        "required_payload_fields": [
            "environment",
            "settings",
        ],
        "required_settings_fields": [
            "region",
            "universe",
            "delay",
            "neutralization",
            "instrumentType",
            "type",
            "decay",
            "truncation",
            "pasteurization",
            "nanHandling",
            "unitHandling",
            "language",
        ],
        "settings_options": settings_options,
        "controls": [
            {"id": "region", "payload_path": "settings.region", "required": True},
            {"id": "universe", "payload_path": "settings.universe", "required": True},
            {"id": "delay", "payload_path": "settings.delay", "required": True},
            {"id": "neutralization", "payload_path": "settings.neutralization", "required": True},
            {"id": "instrumentType", "payload_path": "settings.instrumentType", "required": True},
            {"id": "alphaType", "payload_path": "settings.type", "required": True},
            {"id": "decay", "payload_path": "settings.decay", "required": True},
            {"id": "truncation", "payload_path": "settings.truncation", "required": True},
            {"id": "pasteurization", "payload_path": "settings.pasteurization", "required": True},
            {"id": "nanHandling", "payload_path": "settings.nanHandling", "required": True},
            {"id": "unitHandling", "payload_path": "settings.unitHandling", "required": True},
            {"id": "language", "payload_path": "settings.language", "required": True},
            {"id": "syncRange", "payload_path": "syncRange", "required": False},
            {"id": "autoSubmitToggle", "payload_path": "autoSubmit", "required": False},
            {"id": "useAssistantGuidance", "payload_path": "useAssistantGuidance", "required": False},
            {
                "id": "assistantGuidanceMinConfidence",
                "payload_path": "assistantGuidanceMinConfidence",
                "required": False,
            },
            {
                "id": "assistantGuidanceScoreAdjustment",
                "payload_path": "assistantGuidanceScoreAdjustment",
                "required": False,
            },
            {
                "id": "assistantGuidanceScoreMinConfidence",
                "payload_path": "assistantGuidanceScoreMinConfidence",
                "required": False,
            },
            {
                "id": "assistantGuidanceScoreMinOutcomeCount",
                "payload_path": "assistantGuidanceScoreMinOutcomeCount",
                "required": False,
            },
            {
                "id": "assistantGuidanceScoreBonusCap",
                "payload_path": "assistantGuidanceScoreBonusCap",
                "required": False,
            },
            {
                "id": "assistantGuidanceScorePenaltyCap",
                "payload_path": "assistantGuidanceScorePenaltyCap",
                "required": False,
            },
            {"id": "strategyPluginsEnabled", "payload_path": "strategyPluginsEnabled", "required": False},
            {"id": "strategyPluginSpecs", "payload_path": "strategyPluginSpecs", "required": False},
        ],
        "operation_layout": {
            "primary_console": ["toggle-run", "sync-cloud", "check-batch", "submit-selected"],
            "mutually_exclusive_operations": ["production", "sync", "check", "submit"],
        },
    }
