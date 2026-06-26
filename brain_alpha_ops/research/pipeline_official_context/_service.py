"""``OfficialContextLoadService`` class assembly.

Extracted from the original ``pipeline_official_context.py`` monolith. The
service orchestrates loading the official BRAIN context either from cached
JSON files or from the live API. The API-based ``_load_from_api`` path is
provided by ``_OfficialContextAPIMixin`` (see ``_api_mixin``) and is mixed
in here to keep this file under the per-submodule line budget while
preserving the public class API.
"""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.brain_api.context_defaults import DEFAULT_FIELDS, DEFAULT_OPERATORS

from brain_alpha_ops.research.iterative_optimizer import IterativeOptimizer
from brain_alpha_ops.research.pipeline_official_context._api_mixin import (
    _OfficialContextAPIMixin,
)
from brain_alpha_ops.research.pipeline_official_context._types import (
    EventCallback,
    HaltCallback,
    OfficialContextLoadResult,
    ProgressCallback,
    logger,
)
from brain_alpha_ops.research.pipeline_official_context._validators import (
    configured_official_context_files_exist,
)


class OfficialContextLoadService(_OfficialContextAPIMixin):
    def __init__(
        self,
        *,
        config: Any,
        api: Any,
        generator: Any,
        local_data_dir_existed_at_start: bool,
        progress: ProgressCallback,
        event: EventCallback,
        halt_official_calls: HaltCallback,
    ) -> None:
        self.config = config
        self.api = api
        self.generator = generator
        self.local_data_dir_existed_at_start = local_data_dir_existed_at_start
        self.progress = progress
        self.event = event
        self.halt_official_calls = halt_official_calls

    def load(self) -> OfficialContextLoadResult:
        try:
            return self._load_from_json()
        except Exception as exc:
            context_warning = f"Official JSON load failed ({exc}), falling back to API..."
            logger.warning(
                "official context JSON load failed; falling back to API",
                exc_info=True,
            )
        return self._load_from_api(context_warning)

    def _load_from_json(self) -> OfficialContextLoadResult:
        from brain_alpha_ops.data import OfficialDataLoader

        loader = OfficialDataLoader.instance()
        refresh_result = loader.refresh(self.config.storage_dir, max_retries=1)
        if refresh_result.get("status") == "refresh_failed" and not configured_official_context_files_exist(
            self.config.storage_dir
        ):
            raise RuntimeError("official context JSON files are missing or empty")
        fields = [
            {
                "id": field.id,
                "name": field.id,
                "category": field.category,
                "delay": field.delay,
                "coverage": field.coverage,
                "type": field.type,
                "dataset": field.dataset.id if field.dataset else "",
            }
            for field in loader.get_fields()
        ]
        operators = [
            {
                "name": operator.name,
                "category": operator.category,
                "definition": operator.definition,
                "description": operator.description,
            }
            for operator in loader.get_operators()
        ]
        if not fields and not operators:
            if self.local_data_dir_existed_at_start:
                warning = (
                    "Local data directory exists but official context files are empty; "
                    "using local official defaults until manual sync."
                )
                fields = list(DEFAULT_FIELDS)
                operators = list(DEFAULT_OPERATORS)
                self.generator.update_context(fields, operators)
                self.event("context_manual_sync_required", warning, level="WARN")
                return OfficialContextLoadResult(
                    fields=fields,
                    operators=operators,
                    context_summary={
                        "fields_count": len(fields),
                        "operators_count": len(operators),
                        "source": "builtin_context_manual_sync_required",
                        "warning": warning,
                    },
                    generator=self.generator,
                    loader=loader,
                )
            raise RuntimeError("official context JSON files are missing or empty")
        self.event("context_loaded_from_json", f"Loaded {len(fields)} fields, {len(operators)} operators from official_*.json")
        self.generator.update_context(fields, operators)
        result = OfficialContextLoadResult(
            fields=fields,
            operators=operators,
            context_summary={
                "fields_count": len(fields),
                "operators_count": len(operators),
                "source": "official_json_files",
                "warning": "",
            },
            generator=self.generator,
            loader=loader,
        )
        self._wire_advanced_components(result)
        self.event("context_loaded", f"Loaded {len(fields)} fields and {len(operators)} operators.")
        return result

    def _wire_advanced_components(self, result: OfficialContextLoadResult) -> None:
        try:
            from brain_alpha_ops.data import FieldDatasetMapper
            from brain_alpha_ops.research.dataset_selector import DatasetSelector
            from brain_alpha_ops.research.hypothesis_driven_generator import (
                HypothesisDrivenGenerator,
            )
            from brain_alpha_ops.research.hypothesis_library import HypothesisLibrary
            from brain_alpha_ops.research.theme_engine import DynamicThemeEngine

            mapper = FieldDatasetMapper()
            mapper.build(result.loader)
            theme_engine = DynamicThemeEngine(result.loader)
            theme_engine.build_categories()
            selector = DatasetSelector()
            selector.initialize(result.loader)
            if not selector.available_datasets:
                self.event(
                    "dataset_unavailable",
                    "DatasetSelector initialized but no datasets available. "
                    "Check data/official_datasets.json or BRAIN API connectivity.",
                    level="WARN",
                )
            hypothesis_dir = getattr(
                self.config.budget,
                "hypothesis_library_dir",
                "brain_alpha_ops/research/hypotheses",
            )
            hypothesis_library = HypothesisLibrary(hypothesis_dir).load_all()
            ratio = getattr(self.config.budget, "generation_mode_ratio", "70/20/10")
            generator = HypothesisDrivenGenerator(
                loader=result.loader,
                mapper=mapper,
                theme_engine=theme_engine,
                selector=selector,
                library=hypothesis_library,
                ratio_str=ratio,
            )
            generator.update_context(result.fields, result.operators)
            active_dataset_id = ""
            strategy = getattr(self.config.budget, "dataset_strategy", "rotate")
            if str(strategy).lower() in {"fixed", "locked", "specific"} and getattr(self.config.settings, "dataset", ""):
                dataset_ids = selector.select(strategy, dataset_ids=[self.config.settings.dataset])
            else:
                dataset_ids = selector.select(strategy)
            if dataset_ids:
                active_dataset_id = dataset_ids[0]
                generator.set_dataset(active_dataset_id)
                if hasattr(self.config.settings, "dataset"):
                    self.config.settings.dataset = active_dataset_id
            result.mapper = mapper
            result.theme_engine = theme_engine
            result.selector = selector
            result.hypothesis_library = hypothesis_library
            result.generator = generator
            result.active_dataset_id = active_dataset_id
            result.optimizer = IterativeOptimizer(loader=result.loader, mapper=mapper)
            self.event(
                "advanced_components_wired",
                f"DatasetSelector(strategy={strategy}), DynamicThemeEngine, FieldDatasetMapper ready. "
                f"Active dataset: {active_dataset_id or '(none)'}",
            )
        except Exception as exc:
            logger.warning("advanced official context components unavailable; using base generator context", exc_info=True)
            self.event(
                "advanced_components_fallback",
                f"Could not wire advanced components: {exc}. "
                "DatasetSelector/DynamicThemeEngine/FieldDatasetMapper unavailable - "
                "generator will use full field pool from OfficialDataLoader.",
                level="ERROR",
            )
