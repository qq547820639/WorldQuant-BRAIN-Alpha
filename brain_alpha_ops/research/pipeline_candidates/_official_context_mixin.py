"""Official-context validation mixin for ``PipelineCandidatePoolMixin``.

Extracted from the original ``pipeline_candidates.py`` monolith. Holds the
``_OfficialContextMixin`` carrying cache refresh, active dataset field
resolution, and official context reason computation methods.
"""

from __future__ import annotations

from brain_alpha_ops.models import Candidate

from ..pipeline_official_context import (
    active_dataset_field_names,
    official_context_reasons,
    refresh_context_validation_cache,
)


class _OfficialContextMixin:
    """Official context validation helpers for ``PipelineCandidatePoolMixin``."""

    def _refresh_context_validation_cache(self, fields: list[dict], operators: list[dict]) -> None:
        state = refresh_context_validation_cache(fields, operators)
        self._context_field_names = state.field_names
        self._context_operator_names = state.operator_names
        self._dataset_field_names_cache = state.dataset_field_names_cache

    def _active_dataset_field_names(self) -> set[str]:
        return active_dataset_field_names(
            self._active_dataset_id,
            self._mapper,
            self._dataset_field_names_cache,
        )

    def _official_context_reasons(self, candidate: Candidate, fields: list[dict], operators: list[dict]) -> list[str]:
        if (fields and not self._context_field_names) or (operators and not self._context_operator_names):
            self._refresh_context_validation_cache(fields, operators)
        return official_context_reasons(
            candidate,
            available_fields=self._context_field_names,
            available_operators=self._context_operator_names,
            active_dataset_id=self._active_dataset_id,
            mapper=self._mapper,
            dataset_field_names_cache=self._dataset_field_names_cache,
        )
