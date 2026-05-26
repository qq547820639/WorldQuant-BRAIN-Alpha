"""Official BRAIN context loading helpers for the research pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.brain_api.context_defaults import DEFAULT_FIELDS, DEFAULT_OPERATORS
from brain_alpha_ops.models import Candidate

from .iterative_optimizer import IterativeOptimizer
from .pipeline_helpers import merge_context_defaults


ProgressCallback = Callable[..., None]
EventCallback = Callable[..., None]
HaltCallback = Callable[[str], None]

GENERAL_DATASET_FIELDS = {"returns", "sector", "industry", "subindustry", "market"}


@dataclass
class OfficialContextLoadResult:
    fields: list[dict]
    operators: list[dict]
    context_summary: dict[str, Any]
    generator: Any
    loader: Any = None
    mapper: Any = None
    theme_engine: Any = None
    selector: Any = None
    hypothesis_library: Any = None
    optimizer: Any = None
    active_dataset_id: str = ""


@dataclass
class OfficialContextValidationState:
    field_names: set[str]
    operator_names: set[str]
    dataset_field_names_cache: dict[str, set[str]]


def configured_official_context_files_exist(storage_dir: str | Path) -> bool:
    root = Path(storage_dir)
    return any(
        (root / filename).is_file()
        for filename in ("official_fields.json", "official_operators.json", "official_datasets.json")
    )


def refresh_context_validation_cache(fields: list[dict], operators: list[dict]) -> OfficialContextValidationState:
    field_names: set[str] = set()
    for item in fields:
        for key in ("id", "name"):
            value = str(item.get(key, "")).strip().lower()
            if value:
                field_names.add(value)
    operator_names = {
        str(item.get("name", "")).strip().lower()
        for item in operators
        if item.get("name")
    }
    return OfficialContextValidationState(
        field_names=field_names,
        operator_names=operator_names,
        dataset_field_names_cache={},
    )


def active_dataset_field_names(dataset_id: str, mapper: Any, cache: dict[str, set[str]]) -> set[str]:
    dataset = str(dataset_id or "")
    if not dataset or not mapper:
        return set()
    cached = cache.get(dataset)
    if cached is not None:
        return cached
    try:
        fields = {str(field).lower() for field in mapper.fields_for(dataset)}
    except Exception:
        fields = set()
    cache[dataset] = fields
    return fields


def official_context_reasons(
    candidate: Candidate,
    *,
    available_fields: set[str],
    available_operators: set[str],
    active_dataset_id: str,
    mapper: Any,
    dataset_field_names_cache: dict[str, set[str]],
) -> list[str]:
    reasons: list[str] = []
    if available_fields:
        missing_fields = sorted(field for field in candidate.data_fields if field.lower() not in available_fields)
        if missing_fields:
            reasons.append("fields unavailable in current official context: " + ", ".join(missing_fields))
    if available_operators:
        missing_operators = sorted(operator for operator in candidate.operators if operator.lower() not in available_operators)
        if missing_operators:
            reasons.append("operators unavailable in current official context: " + ", ".join(missing_operators))
    if active_dataset_id and mapper:
        dataset_fields = active_dataset_field_names(active_dataset_id, mapper, dataset_field_names_cache)
        for field in candidate.data_fields:
            if field.lower() not in dataset_fields and field.lower() not in GENERAL_DATASET_FIELDS:
                reasons.append(
                    f"field '{field}' not in active dataset '{active_dataset_id}'. "
                    "Expression may use fields from wrong dataset."
                )
                break
    return reasons


class OfficialContextLoadService:
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
            from brain_alpha_ops.research.hypothesis_driven_generator import HypothesisDrivenGenerator
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
            self.event(
                "advanced_components_fallback",
                f"Could not wire advanced components: {exc}. "
                "DatasetSelector/DynamicThemeEngine/FieldDatasetMapper unavailable - "
                "generator will use full field pool from OfficialDataLoader.",
                level="ERROR",
            )

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
            else:
                raise
        if not fields:
            fields = list(DEFAULT_FIELDS)
            context_warning = (
                (context_warning + " " if context_warning else "")
                + "Using locally cached official field context; successful login refreshes the official field cache."
            )
        if not operators:
            operators = list(DEFAULT_OPERATORS)
            context_warning = (
                (context_warning + " " if context_warning else "")
                + "Using locally cached official operator context; successful login refreshes the official operator cache."
            )
        fields = merge_context_defaults(fields, DEFAULT_FIELDS)
        operators = merge_context_defaults(operators, DEFAULT_OPERATORS)
        self.generator.update_context(fields, operators)
        from brain_alpha_ops.research.generator import update_known_fields

        update_known_fields(fields)
        context_summary = {
            "fields_count": len(fields),
            "operators_count": len(operators),
            "source": "official_api_or_cache",
            "warning": context_warning,
            "operator_usage_note": (
                "Available operators are validated through the official /operators API or local official cache; "
                "the live BRAIN documentation remains authoritative."
            ),
        }
        self.event("context_loaded", f"Loaded {len(fields)} fields and {len(operators)} operators.")
        self.progress(
            "context",
            3,
            3,
            f"Context loaded: {len(fields)} fields, {len(operators)} operators.",
            data={
                "official_context": context_summary,
                "context_load": {
                    "status": "synced",
                    "status_code": "CONTEXT_READY",
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
        )
