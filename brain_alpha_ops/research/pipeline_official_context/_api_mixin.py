"""API-loading mixin for ``OfficialContextLoadService``.

Extracted from the original ``pipeline_official_context.py`` monolith. The
``_load_from_api`` method and its two private helpers
(``_active_dataset_from_context``, ``_context_degraded_reason``) live here
because they form a cohesive API-based fallback path and the method body
alone is large enough to warrant its own submodule.
"""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.brain_api.context_defaults import DEFAULT_FIELDS, DEFAULT_OPERATORS
from brain_alpha_ops.research.pipeline_helpers import merge_context_defaults

from brain_alpha_ops.research.pipeline_official_context._types import (
    OfficialContextLoadResult,
    logger,
)


def _active_dataset_from_context(settings: Any, fields: list[dict]) -> str:
    configured_dataset = str(getattr(settings, "dataset", "") or "").strip()
    if configured_dataset:
        return configured_dataset
    for field in fields:
        dataset_id = str(field.get("dataset") or field.get("dataset_id") or "").strip()
        if dataset_id:
            return dataset_id
    return ""


def _context_degraded_reason(
    *,
    fields_count: int,
    operators_count: int,
    used_default_fields: bool,
    used_default_operators: bool,
) -> str:
    reasons: list[str] = []
    if fields_count == 0:
        reasons.append("no official fields available")
    elif used_default_fields:
        reasons.append("fields loaded from local official cache")
    if operators_count == 0:
        reasons.append("no official operators available")
    elif used_default_operators:
        reasons.append("operators loaded from local official cache")
    return "; ".join(reasons)


class _OfficialContextAPIMixin:
    """Mixin providing the API-based official context loading path.

    The mixin is intentionally minimal: it only carries the ``_load_from_api``
    method (and the helper functions above which are private to that path).
    ``OfficialContextLoadService`` inherits from it in ``_service``.
    """

    def _load_from_api(self, context_warning: str) -> OfficialContextLoadResult:
        self.progress(
            "context",
            0,
            3,
            "Loading official field list.",
            data={
                "context_load": {
                    "status": "running",
                    "status_code": "CONTEXT_FIELDS",
                    "current": 0,
                    "total": 3,
                    "fields_count": 0,
                    "operators_count": 0,
                }
            },
        )
        fields: list[dict] = []
        operators: list[dict] = []
        try:
            fields = self.api.list_fields(
                "all",
                self.config.settings.region,
                dataset=self.config.settings.dataset,
                progress_callback=lambda progress: self.progress(
                    "context",
                    1,
                    3,
                    f"Loading official field list: {progress.get('scanned', 0)} / {progress.get('total') or 'pending total'}.",
                    data={
                        "context_load": {
                            "status": "running",
                            "status_code": "CONTEXT_FIELDS",
                            "current": 1,
                            "total": 3,
                            "fields_count": int(progress.get("scanned", 0) or 0),
                            "fields_total": int(progress.get("total", 0) or 0),
                            "operators_count": 0,
                            "cached": bool(progress.get("cached")),
                        }
                    },
                ),
            )
            self.progress(
                "context",
                2,
                3,
                "Loading official operator list.",
                data={
                    "context_load": {
                        "status": "running",
                        "status_code": "CONTEXT_OPERATORS",
                        "current": 2,
                        "total": 3,
                        "fields_count": len(fields),
                        "operators_count": 0,
                    }
                },
            )
            operators = self.api.list_operators(
                "all",
                progress_callback=lambda progress: self.progress(
                    "context",
                    2,
                    3,
                    f"Loading official operator list: {progress.get('scanned', 0)} / {progress.get('total') or 'pending total'}.",
                    data={
                        "context_load": {
                            "status": "running",
                            "status_code": "CONTEXT_OPERATORS",
                            "current": 2,
                            "total": 3,
                            "fields_count": len(fields),
                            "operators_count": int(progress.get("scanned", 0) or 0),
                            "operators_total": int(progress.get("total", 0) or 0),
                            "cached": bool(progress.get("cached")),
                        }
                    },
                ),
            )
        except BrainAPIError as exc:
            if exc.status_code == 429:
                context_warning = (
                    "Official context API is rate-limited; local generation and ranking will continue, "
                    "and official calls will resume after the retry pause."
                )
                self.halt_official_calls(f"{context_warning} {exc}")
                self.event("official_context_deferred", context_warning, level="WARN")
                self.progress(
                    "official_deferred",
                    0,
                    1,
                    context_warning,
                    data={"retry_seconds": self.config.budget.official_retry_pause_seconds},
                )
                # F-034 fix: return early with cached defaults — do not fall
                # through into the normal ``context_loaded`` event/progress
                # path which would overwrite the deferred status and re-enter
                # official-call paths that were just halted.
                fallback_fields = list(DEFAULT_FIELDS)
                fallback_operators = list(DEFAULT_OPERATORS)
                try:
                    self.generator.update_context(fallback_fields, fallback_operators)
                except Exception:
                    logger.warning("generator.update_context failed during 429 fallback", exc_info=True)
                return OfficialContextLoadResult(
                    fields=fallback_fields,
                    operators=fallback_operators,
                    context_summary={
                        "fields_count": len(fallback_fields),
                        "operators_count": len(fallback_operators),
                        "source": "official_api_or_cache",
                        "warning": (
                            context_warning
                            + " Using locally cached official field context; successful login refreshes the official field cache."
                            + " Using locally cached official operator context; successful login refreshes the official operator cache."
                        ),
                        "active_dataset_id": "",
                        "degraded": True,
                        "degraded_reason": "official context API rate-limited (429)",
                    },
                    generator=self.generator,
                    active_dataset_id="",
                )
            else:
                raise
        used_default_fields = False
        used_default_operators = False
        if not fields:
            fields = list(DEFAULT_FIELDS)
            used_default_fields = True
            context_warning = (
                (context_warning + " " if context_warning else "")
                + "Using locally cached official field context; successful login refreshes the official field cache."
            )
        if not operators:
            operators = list(DEFAULT_OPERATORS)
            used_default_operators = True
            context_warning = (
                (context_warning + " " if context_warning else "")
                + "Using locally cached official operator context; successful login refreshes the official operator cache."
            )
        fields = merge_context_defaults(fields, DEFAULT_FIELDS)
        operators = merge_context_defaults(operators, DEFAULT_OPERATORS)
        self.generator.update_context(fields, operators)
        from brain_alpha_ops.research.generator import update_known_fields

        update_known_fields(fields)
        active_dataset_id = _active_dataset_from_context(self.config.settings, fields)
        if active_dataset_id and hasattr(self.generator, "set_dataset"):
            self.generator.set_dataset(active_dataset_id)
        degraded = used_default_fields or used_default_operators or not fields or not operators
        context_summary = {
            "fields_count": len(fields),
            "operators_count": len(operators),
            "source": "official_api_or_cache",
            "warning": context_warning,
            "active_dataset_id": active_dataset_id,
            "degraded": degraded,
            "degraded_reason": _context_degraded_reason(
                fields_count=len(fields),
                operators_count=len(operators),
                used_default_fields=used_default_fields,
                used_default_operators=used_default_operators,
            ),
            "operator_usage_note": (
                "Available operators are validated through the official /operators API or local official cache; "
                "the live BRAIN documentation remains authoritative."
            ),
        }
        self.event(
            "context_degraded" if degraded else "context_loaded",
            f"Loaded {len(fields)} fields and {len(operators)} operators."
            if not degraded else
            f"Official context degraded: {len(fields)} fields and {len(operators)} operators available.",
            level="WARN" if degraded else "INFO",
        )
        self.progress(
            "context",
            3,
            3,
            f"Context loaded: {len(fields)} fields, {len(operators)} operators.",
            data={
                "official_context": context_summary,
                "context_load": {
                    "status": "degraded" if degraded else "synced",
                    "status_code": "CONTEXT_DEGRADED" if degraded else "CONTEXT_READY",
                    "current": 3,
                    "total": 3,
                    "fields_count": len(fields),
                    "operators_count": len(operators),
                },
            },
        )
        return OfficialContextLoadResult(
            fields=fields,
            operators=operators,
            context_summary=context_summary,
            generator=self.generator,
            active_dataset_id=active_dataset_id,
        )
