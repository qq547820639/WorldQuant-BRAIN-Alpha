"""Public schema for the web production configuration panel."""

from __future__ import annotations

import logging
from typing import Any

from brain_alpha_ops.data import OfficialDataLoader
from brain_alpha_ops.web_capability_registry import capability_settings_options

logger = logging.getLogger(__name__)


def _dataset_options() -> list[dict[str, Any]]:
    try:
        datasets = OfficialDataLoader.instance().get_datasets()
    except Exception:
        logger.warning(
            "failed to load datasets for config schema; returning empty options",
            exc_info=True,
        )
        return []
    rows: list[dict[str, Any]] = []
    for dataset in sorted(
        datasets,
        key=lambda item: (
            str(getattr(item, "category", "") or ""),
            str(getattr(item, "name", "") or ""),
            str(getattr(item, "id", "") or ""),
        ),
    ):
        dataset_id = str(getattr(dataset, "id", "") or "").strip()
        if not dataset_id:
            continue
        name = str(getattr(dataset, "name", "") or "").strip() or dataset_id
        try:
            field_count = int(getattr(dataset, "field_count", 0) or 0)
        except (TypeError, ValueError):
            field_count = 0
        rows.append(
            {
                "id": dataset_id,
                "name": name,
                "field_count": field_count,
                "category": str(getattr(dataset, "category", "") or ""),
                "label": _dataset_label(dataset_id, name, field_count),
            }
        )
    return rows


def _dataset_label(dataset_id: str, name: str, field_count: int) -> str:
    count = f", {field_count} fields" if field_count > 0 else ""
    return f"{dataset_id} - {name}{count}"


def public_config_schema() -> dict[str, Any]:
    """Return the auditable UI-to-backend contract for production config."""

    dataset_options = _dataset_options()
    settings_options = capability_settings_options(dataset_options)
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
        "dataset_options": dataset_options,
        "controls": [
            {"id": "region", "payload_path": "settings.region", "required": True},
            {"id": "universe", "payload_path": "settings.universe", "required": True},
            {"id": "delay", "payload_path": "settings.delay", "required": True},
            {"id": "neutralization", "payload_path": "settings.neutralization", "required": True},
            {
                "id": "dataset",
                "payload_path": "settings.dataset",
                "required": False,
                "options_source": "dataset_options",
            },
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
            "primary_actions": [
                "run-non-submit-proof",
                "refresh-official-context",
                "review-quality-gates",
                "review-submit-readiness",
            ],
            "mutually_exclusive_operations": ["production", "official_refresh", "quality_review", "submit_review"],
        },
    }
