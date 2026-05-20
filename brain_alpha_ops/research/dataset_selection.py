"""Dataset selection service for research cycles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


DATASET_SELECTION_SCHEMA_VERSION = "dataset_selection.v1"

EventCallback = Callable[..., None]


@dataclass(frozen=True)
class DatasetSelectionResult:
    action: str
    dataset_id: str = ""
    reason: str = ""
    event: str = ""
    level: str = "INFO"

    @property
    def should_continue(self) -> bool:
        return self.action == "continue"

    @property
    def should_skip(self) -> bool:
        return self.action == "skip"

    @property
    def should_break(self) -> bool:
        return self.action == "break"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": DATASET_SELECTION_SCHEMA_VERSION,
            "action": self.action,
            "dataset_id": self.dataset_id,
            "reason": self.reason,
            "event": self.event,
            "level": self.level,
        }


class DatasetSelectionService:
    """Choose the active dataset and apply it to generator/settings."""

    def __init__(
        self,
        *,
        selector: Any = None,
        loader: Any = None,
        generator: Any,
        settings: Any,
        strategy: str = "rotate",
        event: EventCallback | None = None,
    ) -> None:
        self.selector = selector
        self.loader = loader
        self.generator = generator
        self.settings = settings
        self.strategy = strategy or "rotate"
        self.event = event

    def select(self) -> DatasetSelectionResult:
        if self.selector and getattr(self.selector, "available_datasets", None):
            dataset_ids = list(self.selector.select(self.strategy) or [])
            dataset_id = str(dataset_ids[0] if dataset_ids else "")
            if dataset_id:
                self._apply(dataset_id)
            return DatasetSelectionResult(action="continue", dataset_id=dataset_id)

        if self.selector:
            result = DatasetSelectionResult(
                action="skip",
                reason="No datasets available; skipping generation cycle.",
                event="dataset_skip_cycle",
                level="WARN",
            )
            self._emit(result)
            return result

        if self.loader:
            dataset_ids = [str(item.id) for item in self.loader.get_datasets()]
            if dataset_ids:
                dataset_id = dataset_ids[0]
                self._apply(dataset_id)
                result = DatasetSelectionResult(
                    action="continue",
                    dataset_id=dataset_id,
                    reason=f"DatasetSelector unavailable; using first loader dataset: {dataset_id}",
                    event="dataset_fallback_loader",
                    level="WARN",
                )
                self._emit(result)
                return result
            result = DatasetSelectionResult(
                action="skip",
                reason="No datasets available from loader or selector; skipping generation cycle.",
                event="dataset_skip_cycle",
                level="WARN",
            )
            self._emit(result)
            return result

        result = DatasetSelectionResult(
            action="break",
            reason=(
                "No OfficialDataLoader or DatasetSelector available; pipeline cannot generate alphas. "
                "Run pipeline with valid credentials to populate data/official_*.json."
            ),
            event="dataset_skip_cycle",
            level="ERROR",
        )
        self._emit(result)
        return result

    def _apply(self, dataset_id: str) -> None:
        self.generator.set_dataset(dataset_id)
        self.settings.dataset = dataset_id

    def _emit(self, result: DatasetSelectionResult) -> None:
        if self.event and result.event:
            self.event(result.event, result.reason, level=result.level)
