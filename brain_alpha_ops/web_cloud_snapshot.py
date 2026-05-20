"""Cloud alpha and local storage snapshot helpers for the web API."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import logging
from pathlib import Path
import time
from typing import Any, Callable

from brain_alpha_ops.config import load_run_config, runtime_project_root
from brain_alpha_ops.data.cache_metadata import read_context_cache_metadata, write_context_cache_metadata
from brain_alpha_ops.jsonl import read_jsonl_tail, read_jsonl_tail_with_stats


logger = logging.getLogger(__name__)

CLOUD_SYNC_STALE_SECONDS = 24 * 60 * 60
CONTEXT_CACHE_MANIFEST_SCHEMA = "official_context_cache_manifest.v1"
OFFICIAL_CONTEXT_FILES = (
    ("fields_count", "official_fields.json"),
    ("operators_count", "official_operators.json"),
    ("datasets_count", "official_datasets.json"),
)

LoadConfig = Callable[[], Any]
RuntimeRoot = Callable[[], Path]
SafeErrorMessage = Callable[[Exception], str]


def _safe_error_message(exc: Exception) -> str:
    return str(exc)


def storage_jsonl_path(filename: str, *, load_config: LoadConfig = load_run_config) -> Path:
    config = load_config()
    return Path(config.ops.storage_dir) / filename


def read_storage_jsonl(filename: str, *, limit: int = 500, load_config: LoadConfig = load_run_config) -> list[dict[str, Any]]:
    return read_jsonl_tail(storage_jsonl_path(filename, load_config=load_config), limit=limit)


def read_storage_jsonl_stats(filename: str, *, limit: int = 500, load_config: LoadConfig = load_run_config) -> dict[str, Any]:
    return read_jsonl_tail_with_stats(storage_jsonl_path(filename, load_config=load_config), limit=limit).to_dict()


def cloud_alpha_snapshot(
    limit: int = 10000,
    *,
    load_config: LoadConfig = load_run_config,
    runtime_root: RuntimeRoot = runtime_project_root,
    safe_error_message: SafeErrorMessage = _safe_error_message,
    stale_seconds: int = CLOUD_SYNC_STALE_SECONDS,
) -> dict[str, Any]:
    cache_path: Path | None = storage_jsonl_path("cloud_alphas.jsonl", load_config=load_config)
    rows = dedupe_cloud_alpha_rows(read_storage_jsonl("cloud_alphas.jsonl", limit=limit, load_config=load_config))
    source = "storage"
    if not rows:
        cache_path = latest_cached_user_alpha_path(load_config=load_config)
        rows = dedupe_cloud_alpha_rows(latest_cached_user_alphas(limit=limit, load_config=load_config))
        source = "api_cache" if rows else "empty"
    rows = drop_mock_rows_if_real(rows)
    summary = cloud_alpha_summary(
        rows,
        load_config=load_config,
        runtime_root=runtime_root,
        safe_error_message=safe_error_message,
    )
    summary["source"] = source
    loaded_at, age_seconds = path_modified_at(cache_path if rows else None)
    summary["loaded_at"] = loaded_at
    summary["age_seconds"] = age_seconds
    summary["is_stale"] = bool(age_seconds is not None and age_seconds > stale_seconds)
    return {"alphas": rows, "summary": summary}


def dedupe_cloud_alpha_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    no_id: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        alpha_id = cloud_alpha_id(row)
        if not alpha_id:
            no_id.append(row)
            continue
        latest[alpha_id] = row
    deduped = list(latest.values()) + no_id
    deduped.sort(key=cloud_row_sort_key, reverse=True)
    return deduped


def latest_cached_user_alphas(limit: int = 10000, *, load_config: LoadConfig = load_run_config) -> list[dict[str, Any]]:
    for path in cached_user_alpha_paths(load_config=load_config):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rows = extract_alpha_rows(data)
        if rows:
            return rows[-limit:]
    return []


def latest_cached_user_alpha_path(*, load_config: LoadConfig = load_run_config) -> Path | None:
    for path in cached_user_alpha_paths(load_config=load_config):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if extract_alpha_rows(data):
            return path
    return None


def cached_user_alpha_paths(*, load_config: LoadConfig = load_run_config) -> list[Path]:
    config = load_config()
    cache_dir = Path(config.ops.official_api.cache_dir)
    if not cache_dir.is_absolute():
        cache_dir = Path.cwd() / cache_dir
    try:
        return sorted(cache_dir.glob("user_alphas_*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    except OSError:
        return []


def path_modified_at(path: Path | None) -> tuple[str, int | None]:
    if not path:
        return "", None
    try:
        modified_at = path.stat().st_mtime
    except OSError:
        return "", None
    return datetime.fromtimestamp(modified_at, timezone.utc).isoformat(), max(0, int(time.time() - modified_at))


def extract_alpha_rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("results", "alphas", "data", "items"):
        value = data.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def official_context_file_counts(
    *,
    load_config: LoadConfig = load_run_config,
    runtime_root: RuntimeRoot = runtime_project_root,
    safe_error_message: SafeErrorMessage = _safe_error_message,
) -> dict[str, Any]:
    counts: dict[str, Any] = {}
    metadata: dict[str, dict[str, Any]] = {}
    for key, filename in OFFICIAL_CONTEXT_FILES:
        rows = read_official_context_json(
            filename,
            load_config=load_config,
            runtime_root=runtime_root,
            safe_error_message=safe_error_message,
        )
        counts[key] = len(rows) if isinstance(rows, list) else 0
        meta = read_official_context_metadata(
            filename,
            load_config=load_config,
            runtime_root=runtime_root,
            safe_error_message=safe_error_message,
        )
        if meta:
            metadata[filename] = enrich_context_cache_metadata(meta)
    if metadata:
        counts["context_cache_metadata"] = metadata
        counts["context_cache_manifest"] = context_cache_manifest(
            metadata,
            expected_files=[filename for _key, filename in OFFICIAL_CONTEXT_FILES],
        )
    return counts


def enrich_context_cache_metadata(metadata: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    enriched = dict(metadata)
    current = now or datetime.now(timezone.utc)
    saved_at = parse_cache_timestamp(enriched.get("saved_at"))
    expires_at = parse_cache_timestamp(enriched.get("expires_at"))
    age_seconds = max(0, int((current - saved_at).total_seconds())) if saved_at else None
    expires_in_seconds = int((expires_at - current).total_seconds()) if expires_at else None
    is_expired = bool(expires_at and expires_at <= current)
    enriched["age_seconds"] = age_seconds
    enriched["expires_in_seconds"] = expires_in_seconds
    enriched["is_expired"] = is_expired
    enriched["is_stale"] = is_expired
    return enriched


def context_cache_manifest(
    metadata: dict[str, dict[str, Any]],
    *,
    expected_files: list[str],
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    missing_files = [filename for filename in expected_files if filename not in metadata]
    stale_files = [
        filename
        for filename, meta in metadata.items()
        if bool(meta.get("is_stale") or meta.get("is_expired"))
    ]
    record_counts = {
        filename: int(meta.get("record_count", 0) or 0)
        for filename, meta in metadata.items()
    }
    files_digest_payload = {
        filename: {
            "sha256": meta.get("sha256", ""),
            "record_count": meta.get("record_count", 0),
            "complete": bool(meta.get("complete")),
            "saved_at": meta.get("saved_at", ""),
            "expires_at": meta.get("expires_at", ""),
            "is_stale": bool(meta.get("is_stale")),
        }
        for filename, meta in sorted(metadata.items())
    }
    digest = sha256(
        json.dumps(files_digest_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": CONTEXT_CACHE_MANIFEST_SCHEMA,
        "generated_at": current.isoformat(),
        "expected_files": list(expected_files),
        "files": metadata,
        "file_count": len(metadata),
        "missing_files": missing_files,
        "stale_files": stale_files,
        "expired_files": stale_files,
        "record_counts": record_counts,
        "record_count_total": sum(record_counts.values()),
        "complete": not missing_files and all(bool(metadata.get(filename, {}).get("complete")) for filename in expected_files),
        "is_stale": bool(missing_files or stale_files),
        "sha256": digest,
    }


def parse_cache_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def read_official_context_metadata(
    filename: str,
    *,
    load_config: LoadConfig = load_run_config,
    runtime_root: RuntimeRoot = runtime_project_root,
    safe_error_message: SafeErrorMessage = _safe_error_message,
) -> dict[str, Any]:
    roots: list[Path] = []
    try:
        roots.append(Path(load_config().ops.storage_dir))
    except Exception as exc:
        logger.warning("failed to resolve configured storage dir for official context metadata: %s", safe_error_message(exc))
    roots.extend([
        runtime_root() / "data",
        Path(__file__).resolve().parents[1] / "data",
    ])
    seen: set[Path] = set()
    for root in roots:
        path = root / filename
        if path in seen:
            continue
        seen.add(path)
        metadata = read_context_cache_metadata(path)
        if metadata:
            return metadata
    return {}


def read_official_context_json(
    filename: str,
    *,
    load_config: LoadConfig = load_run_config,
    runtime_root: RuntimeRoot = runtime_project_root,
    safe_error_message: SafeErrorMessage = _safe_error_message,
) -> list[dict[str, Any]]:
    roots: list[Path] = []
    try:
        roots.append(Path(load_config().ops.storage_dir))
    except Exception as exc:
        logger.warning("failed to resolve configured storage dir for official context: %s", safe_error_message(exc))
    roots.extend([
        runtime_root() / "data",
        Path(__file__).resolve().parents[1] / "data",
    ])
    seen: set[Path] = set()
    for root in roots:
        path = root / filename
        if path in seen:
            continue
        seen.add(path)
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("failed to read official context file %s: %s", path, safe_error_message(exc))
            continue
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def cloud_alpha_summary(
    rows: list[dict[str, Any]],
    *,
    load_config: LoadConfig = load_run_config,
    runtime_root: RuntimeRoot = runtime_project_root,
    safe_error_message: SafeErrorMessage = _safe_error_message,
) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    submitted = 0
    passed_unsubmitted = 0
    failed_unsubmitted = 0
    for row in rows:
        status = str(row.get("status", "")).strip().upper()
        metrics = row.get("metrics") or {}
        pass_fail = str(metrics.get("pass_fail", "")).strip().upper()
        status_counts[status or "UNKNOWN"] = status_counts.get(status or "UNKNOWN", 0) + 1
        if status in {"ACTIVE", "SUBMITTED", "PRODUCTION", "CONDUCTED"}:
            submitted += 1
        elif status == "UNSUBMITTED" and pass_fail == "PASS":
            passed_unsubmitted += 1
        elif status == "UNSUBMITTED" and (pass_fail == "FAIL" or metrics.get("failure_reason")):
            failed_unsubmitted += 1
    return {
        "status": "loaded" if rows else "empty",
        "status_code": "CLOUD_CACHE_LOADED" if rows else "CLOUD_CACHE_EMPTY",
        "range": "local-cache",
        "count": len(rows),
        "scanned": len(rows),
        "total": len(rows),
        "added": 0,
        "skipped": 0,
        "failed": 0,
        "submitted_count": submitted,
        "passed_unsubmitted_count": passed_unsubmitted,
        "failed_unsubmitted_count": failed_unsubmitted,
        "status_counts": status_counts,
        **official_context_file_counts(
            load_config=load_config,
            runtime_root=runtime_root,
            safe_error_message=safe_error_message,
        ),
    }


def drop_mock_rows_if_real(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    real = [row for row in rows if not cloud_alpha_id(row).startswith("mock_")]
    return real or rows


def cloud_alpha_id(row: dict[str, Any]) -> str:
    return str(row.get("id") or row.get("alpha_id") or "")


def cloud_row_sort_key(row: dict[str, Any]) -> str:
    return str(row.get("timestamp") or row.get("updated_at") or row.get("created_at") or "")


def datasets_from_fields(
    fields: list[dict[str, Any]],
    *,
    load_config: LoadConfig = load_run_config,
    runtime_root: RuntimeRoot = runtime_project_root,
    safe_error_message: SafeErrorMessage = _safe_error_message,
) -> list[dict[str, Any]]:
    datasets: dict[str, dict[str, Any]] = {}
    for field in fields or []:
        if not isinstance(field, dict):
            continue
        raw_dataset = field.get("dataset")
        if isinstance(raw_dataset, dict):
            dataset_id = str(raw_dataset.get("id") or "").strip()
            dataset_name = str(raw_dataset.get("name") or dataset_id).strip()
        else:
            dataset_id = str(field.get("dataset_id") or raw_dataset or "").strip()
            dataset_name = dataset_id
        if not dataset_id:
            continue
        row = datasets.setdefault(dataset_id, {"id": dataset_id, "name": dataset_name or dataset_id, "field_count": 0})
        row["field_count"] = int(row.get("field_count", 0) or 0) + 1
        if dataset_name and row.get("name") == dataset_id:
            row["name"] = dataset_name
    if not datasets:
        return read_official_context_json(
            "official_datasets.json",
            load_config=load_config,
            runtime_root=runtime_root,
            safe_error_message=safe_error_message,
        )
    return sorted(datasets.values(), key=lambda item: (-int(item.get("field_count", 0) or 0), str(item.get("id", ""))))


def persist_official_context(
    fields: list[dict[str, Any]],
    operators: list[dict[str, Any]],
    datasets: list[dict[str, Any]],
    *,
    load_config: LoadConfig = load_run_config,
    runtime_root: RuntimeRoot = runtime_project_root,
    safe_error_message: SafeErrorMessage = _safe_error_message,
) -> None:
    if fields:
        save_official_context_json(
            "official_fields.json",
            fields,
            load_config=load_config,
            runtime_root=runtime_root,
        )
    if operators:
        save_official_context_json(
            "official_operators.json",
            operators,
            load_config=load_config,
            runtime_root=runtime_root,
        )
    if datasets:
        save_official_context_json(
            "official_datasets.json",
            datasets,
            load_config=load_config,
            runtime_root=runtime_root,
        )
    if fields or operators or datasets:
        from brain_alpha_ops.data.loader import OfficialDataLoader

        try:
            data_dir = str(Path(load_config().ops.storage_dir))
        except Exception as exc:
            logger.warning("failed to resolve configured storage dir after official context persist: %s", safe_error_message(exc))
            data_dir = "data"
        OfficialDataLoader.instance().refresh(data_dir)


def save_official_context_json(
    filename: str,
    items: list[dict[str, Any]],
    *,
    load_config: LoadConfig = load_run_config,
    runtime_root: RuntimeRoot = runtime_project_root,
) -> None:
    ttl_seconds = 86400
    try:
        run_config = load_config()
        data_dir = Path(run_config.ops.storage_dir)
        ttl_seconds = int(run_config.ops.official_api.context_cache_ttl_seconds)
    except Exception:
        data_dir = runtime_root() / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    target = data_dir / filename
    tmp = data_dir / f".{filename}.tmp"
    tmp.write_text(json.dumps(items, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(target)
    write_context_cache_metadata(
        target,
        items,
        source="official_api",
        ttl_seconds=ttl_seconds,
    )
