"""Configuration for the account-safety-first research pipeline."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from brain_alpha_ops.config_domain_validation import (
    _VALID_ALPHA_TYPES,
    _VALID_DATASET_STRATEGIES,
    _VALID_DELAYS,
    _VALID_ENVIRONMENT,
    _VALID_MARKET_REGIMES,
    _VALID_NEUTRALIZATIONS,
    _VALID_ON_OFF,
    _VALID_REGIONS,
    _VALID_UNIT_HANDLING,
    _VALID_UNIVERSES,
)
from brain_alpha_ops.config_domain_validation import (
    validate_budget as _validate_budget,
)
from brain_alpha_ops.config_domain_validation import (
    validate_credentials as _validate_credentials,
)
from brain_alpha_ops.config_domain_validation import (
    validate_official_api as _validate_official_api,
)
from brain_alpha_ops.config_domain_validation import (
    validate_ops as _validate_ops,
)
from brain_alpha_ops.config_domain_validation import (
    validate_scoring as _validate_scoring,
)
from brain_alpha_ops.config_domain_validation import (
    validate_settings as _validate_settings,
)
from brain_alpha_ops.config_domain_validation import (
    validate_submission_policy as _validate_submission_policy,
)
from brain_alpha_ops.config_domain_validation import (
    validate_thresholds as _validate_thresholds,
)
from brain_alpha_ops.config_domain_validation import (
    validate_web as _validate_web,
)
from brain_alpha_ops.config_models import (
    BrainSettings,
    CredentialConfig,
    OfficialAPIConfig,
    OpsConfig,
    QualityThresholds,
    ResearchBudget,
    RunConfig,
    ScoringConfig,
    SubmissionPolicy,
    WebConfig,
)
from brain_alpha_ops.config_update import update_dataclass_from_mapping
from brain_alpha_ops.config_validation_helpers import require_bool


def _is_dataset_id_in_official_cache(dataset_id: str, storage_dir: str) -> bool:
    """Check whether *dataset_id* appears in the local official_datasets.json cache.

    Returns True when the ID is found in the cache, meaning it is a recognized
    BRAIN dataset short name (e.g. "pv1", "analyst4").  Returns False when the
    cache cannot be read or the ID is not present.
    """
    datasets_path = Path(storage_dir) / "official_datasets.json"
    if not datasets_path.is_file():
        # First-time setup: cache not yet downloaded; allow the ID.
        # We cannot reject an ID we haven't had a chance to validate against.
        return True
    try:
        with open(datasets_path, encoding="utf-8") as fh:
            datasets = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return False
    if not isinstance(datasets, list):
        return False
    for ds in datasets:
        if isinstance(ds, dict) and ds.get("id") == dataset_id:
            return True
    return False

from brain_alpha_ops.dataset_defaults import resolve_default_dataset_id

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN_CONFIG_PATH = PROJECT_ROOT / "config" / "run_config.json"

logger = logging.getLogger(__name__)


class ConfigValidationError(ValueError):
    """Raised when run_config.json contains unsupported or unsafe values."""


def runtime_project_root() -> Path:
    """Return the persistent application root for source and frozen builds."""
    override = os.getenv("BRAIN_ALPHA_OPS_HOME", "").strip()
    if override:
        return Path(override).expanduser().resolve()

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return PROJECT_ROOT


def default_run_config_path() -> Path:
    runtime_path = runtime_project_root() / "config" / "run_config.json"
    return runtime_path if runtime_path.is_file() else DEFAULT_RUN_CONFIG_PATH


def resolve_runtime_path(value: str | Path, *, base: Path | None = None) -> str:
    path = Path(value).expanduser()
    if path.is_absolute():
        return str(path)
    return str(((base or runtime_project_root()) / path).resolve())


def load_run_config(path: str | Path | None = None) -> RunConfig:
    config_path = Path(path) if path else default_run_config_path()
    if not config_path.exists():
        return _normalize_runtime_paths(validate_run_config(RunConfig()))

    # ── Step 1: parse JSON with explicit error wrapping ──
    try:
        raw_text = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigValidationError(
            f"无法读取配置文件 {config_path}: {exc}"
        ) from exc
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ConfigValidationError(
            f"配置文件 JSON 格式错误 {config_path}: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise ConfigValidationError(
            f"配置文件根元素必须是 JSON 对象，实际类型: {type(data).__name__} — {config_path}"
        )

    # ── Step 2: jsonschema structural validation ──
    from brain_alpha_ops.config_schema import validate_config_with_jsonschema
    schema_errors = validate_config_with_jsonschema(data)
    if schema_errors:
        raise ConfigValidationError(
            "配置文件结构不符合 schema 要求 ("
            + "; ".join(schema_errors[:6])
            + (" 等" if len(schema_errors) > 6 else "")
            + f")\n配置文件: {config_path}"
        )

    # ── Step 3: dataclass population + procedural validation ──
    config = _update_dataclass(RunConfig(), data)
    complete_schema_errors = validate_config_with_jsonschema(config.to_dict())
    if complete_schema_errors:
        raise ConfigValidationError(
            "配置文件结构不符合 schema 要求 ("
            + "; ".join(complete_schema_errors[:6])
            + (" 等" if len(complete_schema_errors) > 6 else "")
            + f")\n配置文件: {config_path}"
        )
    return _normalize_runtime_paths(validate_run_config(config))


def load_ops_config(path: str | Path | None = None) -> OpsConfig:
    return load_run_config(path).ops


def write_run_config(config: RunConfig, path: str | Path | None = None) -> Path:
    validate_run_config(config, skip_cache_check=True)
    config_path = Path(path) if path else default_run_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    # Sanitize credentials before persisting — never write secrets to disk
    data = config.to_dict()
    if isinstance(data.get("credentials"), dict):
        data["credentials"]["username"] = ""
        data["credentials"]["password"] = ""
        data["credentials"]["token"] = ""
    config_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return config_path


def validate_run_config(config: RunConfig, *, skip_cache_check: bool = False) -> RunConfig:
    """Validate the supported run configuration surface.

    The loader intentionally ignores unknown JSON keys for forward
    compatibility, but known keys must keep the types and ranges expected by
    the pipeline, web console, and official API adapter.
    """
    if not isinstance(config, RunConfig):
        raise ConfigValidationError("run_config must be a RunConfig instance")

    errors: list[str] = []
    if str(config.environment).lower() != "production":
        errors.append(f"environment must be 'production', got: {config.environment}")
    require_bool(errors, "auto_submit", config.auto_submit)
    _validate_credentials(errors, config.credentials)
    _validate_web(errors, config.web)
    dataset = getattr(config.ops.settings, "dataset", "")
    resolved = dataset.strip() if isinstance(dataset, str) and dataset.strip() else ""
    if not resolved:
        try:
            resolved = resolve_default_dataset_id(config.ops.storage_dir, runtime_root=runtime_project_root)
        except Exception as exc:
            logger.warning("failed to resolve default dataset_id; leaving validation to fail closed", exc_info=True)
            errors.append(f"failed to resolve default dataset_id: {exc}")
            resolved = ""
    if not resolved:
        errors.append("resolved default dataset_id is empty")
    # Only mutate settings if resolution succeeded; pure validation otherwise.
    if resolved:
        config.ops.settings.dataset = resolved
        # Validate that the dataset_id is a known BRAIN dataset short name
        # (e.g. "pv1", "analyst4"), a UUID, or the special value "all".
        # Unknown IDs cause all BRAIN API calls to fail silently; catching
        # them here gives the user a clear error message.
        import re
        _UUID_RE = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
        cache_ok = _is_dataset_id_in_official_cache(resolved, config.ops.storage_dir) if not skip_cache_check else True
        if (
            resolved.lower() not in ("all", "")
            and not _UUID_RE.match(resolved)
            and not cache_ok
        ):
            errors.append(
                f"dataset_id '{resolved}' is not a recognized BRAIN dataset ID; "
                "check run_config.json → ops.settings.dataset"
            )
    _validate_ops(errors, config.ops)
    if errors:
        raise ConfigValidationError("Invalid run configuration: " + "; ".join(errors))
    return config


def _normalize_runtime_paths(config: RunConfig, base: Path | None = None) -> RunConfig:
    base = (base or runtime_project_root()).resolve()
    config.ops.storage_dir = resolve_runtime_path(config.ops.storage_dir, base=base)
    config.ops.official_api.cache_dir = resolve_runtime_path(config.ops.official_api.cache_dir, base=base)
    if config.ops.budget.hypothesis_library_dir:
        config.ops.budget.hypothesis_library_dir = resolve_runtime_path(
            config.ops.budget.hypothesis_library_dir,
            base=base,
        )
    return config


def _update_dataclass(instance, data: dict[str, Any], *, _path: str = ""):
    return update_dataclass_from_mapping(
        instance,
        data,
        path=_path,
        error_cls=ConfigValidationError,
        logger=logger,
    )
