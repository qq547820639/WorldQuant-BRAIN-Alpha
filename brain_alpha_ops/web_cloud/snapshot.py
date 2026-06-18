"""Cloud alpha snapshot and context refresh."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Iterable

from brain_alpha_ops.brain_api.official_helpers import looks_non_production_alpha_id
from brain_alpha_ops.brain_api.user_alpha_sync import list_user_alphas_for_sync
from brain_alpha_ops.config import load_run_config, runtime_project_root
from brain_alpha_ops.data.cache_metadata import (
    read_context_cache_metadata,
    write_context_cache_metadata,
)
from brain_alpha_ops.jsonl import (
    find_jsonl_record_reverse,
    iter_jsonl_records,
    read_jsonl_records,
    read_jsonl_tail,
    read_jsonl_tail_with_stats,
)
from brain_alpha_ops.redaction import redact_error_message, redact_text

logger = logging.getLogger(__name__)

# ── Centralized constants (source of truth: runtime_constants.py) ──
from brain_alpha_ops.runtime_constants import CloudDefaults

CLOUD_SYNC_STALE_SECONDS = CloudDefaults.CLOUD_SYNC_STALE_SECONDS
CONTEXT_CACHE_MANIFEST_SCHEMA = CloudDefaults.CONTEXT_CACHE_MANIFEST_SCHEMA
OFFICIAL_CONTEXT_FILES = (
    ("fields_count", "official_fields.json"),
    ("operators_count", "official_operators.json"),
    ("datasets_count", "official_datasets.json"),
)

LoadConfig = Callable[[], Any]
RuntimeRoot = Callable[[], Path]
SafeErrorMessage = Callable[[Exception], str]


def _safe_error_message(exc: Exception) -> str:
    return redact_error_message(exc)


def storage_jsonl_path(filename: str, *, load_config: LoadConfig = load_run_config) -> Path:
    config = load_config()
    return Path(config.ops.storage_dir) / filename


def read_storage_jsonl(filename: str, *, limit: int | None = 500, load_config: LoadConfig = load_run_config) -> list[dict[str, Any]]:
    # When limit=None the caller explicitly wants ALL records — pass max_rows=None
    # to read_jsonl_records to remove the safety cap. The caller (e.g. cloud
    # alpha snapshot) is expected to have enough memory for the full dataset.
    max_rows: int | None = None if limit is None else limit or 10_000
    return read_jsonl_records(storage_jsonl_path(filename, load_config=load_config), limit=limit, max_rows=max_rows)


def read_storage_jsonl_stats(filename: str, *, limit: int = 500, load_config: LoadConfig = load_run_config) -> dict[str, Any]:
    return read_jsonl_tail_with_stats(storage_jsonl_path(filename, load_config=load_config), limit=limit).to_dict()


def cloud_alpha_snapshot(
    limit: int | None = None,
    *,
    load_config: LoadConfig = load_run_config,
    runtime_root: RuntimeRoot = runtime_project_root,
    safe_error_message: SafeErrorMessage = _safe_error_message,
    stale_seconds: int = CLOUD_SYNC_STALE_SECONDS,
) -> dict[str, Any]:
    cache_path: Path | None = storage_jsonl_path("cloud_alphas.jsonl", load_config=load_config)
    all_rows = dedupe_cloud_alpha_rows(iter_jsonl_records(cache_path))
    rows = _bounded_rows(all_rows, limit)
    source = "storage"
    if not all_rows:
        cache_path = latest_cached_user_alpha_path(load_config=load_config)
        all_rows = dedupe_cloud_alpha_rows(latest_cached_user_alphas(limit=None, load_config=load_config))
        rows = _bounded_rows(all_rows, limit)
        source = "api_cache" if all_rows else "empty"
    summary = cloud_alpha_summary(
        all_rows,
        load_config=load_config,
        runtime_root=runtime_root,
        safe_error_message=safe_error_message,
    )
    summary["source"] = source
    summary["returned_count"] = len(rows)
    summary["display_limit"] = limit
    loaded_at, age_seconds = path_modified_at(cache_path if rows else None)
    summary["loaded_at"] = loaded_at
    summary["age_seconds"] = age_seconds
    summary["is_stale"] = bool(age_seconds is not None and age_seconds > stale_seconds)
    return {"alphas": rows, "summary": summary}


def cloud_alpha_cache_probe(
    *,
    load_config: LoadConfig = load_run_config,
    stale_seconds: int = CLOUD_SYNC_STALE_SECONDS,
) -> dict[str, Any]:
    """Return a lightweight cloud Alpha cache readiness summary.

    This intentionally avoids the full snapshot path, which parses, dedupes,
    sorts, and summarizes the entire JSONL file. Phase readiness only needs to
    know whether a usable production Alpha cache exists; exact counts remain
    owned by ``cloud_alpha_snapshot``.
    """
    cache_path = storage_jsonl_path("cloud_alphas.jsonl", load_config=load_config)
    row = find_jsonl_record_reverse(cache_path, predicate=is_production_cloud_alpha_row)
    if row is not None:
        loaded_at, age_seconds = path_modified_at(cache_path)
        return {
            "ok": True,
            "source": "storage",
            "loaded_at": loaded_at,
            "age_seconds": int(age_seconds or 0),
            "is_stale": bool(age_seconds is not None and age_seconds > stale_seconds),
        }

    api_cache_path = latest_cached_user_alpha_path(load_config=load_config)
    api_rows = dedupe_cloud_alpha_rows(latest_cached_user_alphas(limit=None, load_config=load_config))
    api_count = len(api_rows)
    loaded_at, age_seconds = path_modified_at(api_cache_path if api_count else None)
    return {
        "ok": api_count > 0,
        "count": api_count,
        "total": api_count,
        "source": "api_cache" if api_count else "empty",
        "loaded_at": loaded_at,
        "age_seconds": int(age_seconds or 0),
        "is_stale": bool(age_seconds is not None and age_seconds > stale_seconds),
    }


def _bounded_rows(rows: list[dict[str, Any]], limit: int | None) -> list[dict[str, Any]]:
    if limit is None:
        return rows
    return rows[: max(1, int(limit or 1))]


def dedupe_cloud_alpha_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    no_id: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        alpha_id = cloud_alpha_id(row)
        if not alpha_id:
            no_id.append(row)
            continue
        if looks_non_production_alpha_id(alpha_id):
            continue
        latest[alpha_id] = row
    deduped = list(latest.values()) + no_id
    deduped.sort(key=cloud_row_sort_key, reverse=True)
    return deduped


def is_production_cloud_alpha_row(row: dict[str, Any]) -> bool:
    alpha_id = cloud_alpha_id(row)
    return bool(alpha_id and not looks_non_production_alpha_id(alpha_id))


def latest_cached_user_alphas(
    limit: int | None = None,
    *,
    load_config: LoadConfig = load_run_config,
    max_files: int | None = None,
) -> list[dict[str, Any]]:
    for path in cached_user_alpha_paths(load_config=load_config, max_files=max_files):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("failed to read cached user alpha file %s", redact_text(path, max_length=180))
            continue
        rows = extract_alpha_rows(data)
        if rows:
            return rows if limit is None else rows[-max(1, int(limit or 1)):]
    return []


def latest_cached_user_alpha_path(
    *,
    load_config: LoadConfig = load_run_config,
    max_files: int | None = None,
) -> Path | None:
    for path in cached_user_alpha_paths(load_config=load_config, max_files=max_files):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("failed to read cached user alpha file %s", redact_text(path, max_length=180))
            continue
        if extract_alpha_rows(data):
            return path
    return None


def cached_user_alpha_paths(
    *,
    load_config: LoadConfig = load_run_config,
    max_files: int | None = None,
) -> list[Path]:
    config = load_config()
    cache_dir = Path(config.ops.official_api.cache_dir)
    if not cache_dir.is_absolute():
        cache_dir = Path.cwd() / cache_dir
    try:
        candidates = []
        for path in cache_dir.glob("user_alphas_*.json"):
            try:
                candidates.append((path.stat().st_mtime, path))
            except OSError:
                continue
        ordered = [path for _mtime, path in sorted(candidates, reverse=True)]
        if max_files is None:
            return ordered
        return ordered[: max(1, int(max_files or 1))]
    except OSError:
        logger.warning("failed to list cached user alpha files from %s", redact_text(cache_dir, max_length=180))
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
            metadata[filename] = enrich_context_cache_metadata(meta, rows=rows)
    if metadata:
        counts["context_cache_metadata"] = metadata
        counts["context_cache_manifest"] = context_cache_manifest(
            metadata,
            expected_files=[filename for _key, filename in OFFICIAL_CONTEXT_FILES],
        )
    return counts


def enrich_context_cache_metadata(
    metadata: dict[str, Any],
    *,
    rows: list[dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
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
    if rows is not None:
        actual_count = len(rows)
        declared_count = _metadata_int(enriched.get("record_count"))
        declared_sha = str(enriched.get("sha256") or "").strip()
        actual_sha = context_items_hash(rows) if actual_count else ""
        record_count_matches = declared_count == actual_count
        sha256_matches = bool(declared_sha) and declared_sha == actual_sha
        integrity_errors: list[str] = []
        if actual_count <= 0:
            integrity_errors.append("empty_context_file")
        if not record_count_matches:
            integrity_errors.append("record_count_mismatch")
        if not sha256_matches:
            integrity_errors.append("sha256_mismatch")
        if not bool(enriched.get("complete")):
            integrity_errors.append("metadata_incomplete")
        enriched["metadata_record_count"] = declared_count
        enriched["record_count"] = actual_count
        enriched["actual_sha256"] = actual_sha
        enriched["record_count_matches"] = record_count_matches
        enriched["sha256_matches"] = sha256_matches
        enriched["integrity_ok"] = not integrity_errors
        enriched["integrity_errors"] = integrity_errors
        # A cache is complete only when the metadata still describes the file
        # currently on disk. TTL staleness is reported separately as is_stale.
        enriched["complete"] = not integrity_errors
    return enriched


def context_items_hash(items: list[dict[str, Any]]) -> str:
    payload = json.dumps(items, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def _metadata_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


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
    invalid_files = [
        filename
        for filename in expected_files
        if filename in metadata and not bool(metadata.get(filename, {}).get("complete"))
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
        "invalid_files": invalid_files,
        "record_counts": record_counts,
        "record_count_total": sum(record_counts.values()),
        "complete": not missing_files and not invalid_files,
        "is_stale": bool(missing_files or stale_files or invalid_files),
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
            logger.warning(
                "failed to read official context file %s: %s",
                redact_text(path, max_length=180),
                safe_error_message(exc),
            )
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
            data_dir = CloudDefaults.OFFICIAL_CONTEXT_DATA_DIR
        OfficialDataLoader.instance().refresh(data_dir)


def save_official_context_json(
    filename: str,
    items: list[dict[str, Any]],
    *,
    load_config: LoadConfig = load_run_config,
    runtime_root: RuntimeRoot = runtime_project_root,
) -> None:
    ttl_seconds = CloudDefaults.CONTEXT_CACHE_TTL_SECONDS
    try:
        run_config = load_config()
        data_dir = Path(run_config.ops.storage_dir)
        ttl_seconds = int(run_config.ops.official_api.context_cache_ttl_seconds)
    except Exception as exc:
        logger.warning(
            "failed to resolve configured storage dir while saving official context: %s; falling back to runtime root",
            redact_error_message(exc),
        )
        data_dir = runtime_root() / CloudDefaults.OFFICIAL_CONTEXT_DATA_DIR
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

"""Cloud/context refresh service used by web candidate checks."""

import logging
from typing import Any, Callable, Protocol

from brain_alpha_ops.official_context_datasets import list_official_datasets_or_derive
from brain_alpha_ops.research.repository import ResearchRepository

logger = logging.getLogger(__name__)


class JobStoreLike(Protocol):
    def update(self, job_id: str, **kwargs: Any) -> None:
        ...


OfficialContextCounts = Callable[[], dict[str, Any]]
DatasetsFromFields = Callable[[list[dict[str, Any]]], list[dict[str, Any]]]
PersistOfficialContext = Callable[[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]], None]
SafeErrorMessage = Callable[[Exception], str]


def _cloud_refresh_progress_message(progress: dict[str, Any]) -> str:
    scanned = int(progress.get("scanned", 0) or 0)
    reference = int(
        progress.get("api_reported_total")
        or progress.get("filter_window_count")
        or 0
    )
    page = int(progress.get("pages_fetched") or progress.get("page_number") or 0)
    reference_text = (
        f"接口分页参考数 {reference} 条，不是云端 Alpha 总量"
        if reference > 0
        else "接口分页参考数仍在确认"
    )
    page_text = f"；当前第 {page} 页" if page else ""
    return f"云端 Alpha 分页拉取中：已拉取 {scanned} 条；{reference_text}{page_text}。"


def refresh_cloud_context_for_check_service(
    api: Any,
    repo: ResearchRepository,
    sync_range: str,
    job_id: str,
    total: int,
    mode: str,
    region: str = "",
    *,
    refresh_remote: bool = False,
    store: JobStoreLike,
    official_context_file_counts: OfficialContextCounts,
    datasets_from_fields: DatasetsFromFields,
    persist_official_context: PersistOfficialContext,
    safe_error_message: SafeErrorMessage,
) -> tuple[list[dict[str, Any]], str]:
    context_errors: list[str] = []
    context_warnings: list[str] = []

    def on_dataset_fallback(message: str, exc: Exception) -> None:
        context_warnings.append(f"datasets refresh fallback: {message}: {safe_error_message(exc)}")

    if not refresh_remote:
        rows = repo.latest_cloud_alphas()
        counts = official_context_file_counts()
        store.update(
            job_id,
            status="running",
            progress={
                "phase": "cloud_sync",
                "status_code": "CHECK_LOCAL_CACHE",
                "mode": mode,
                "range": sync_range,
                "total": total,
                "checked": 0,
                "submittable": 0,
                "blocked": 0,
                "failed": 0,
                "cloud_scanned": len(rows),
                "cloud_saved_count": len(rows),
                **counts,
                "message": f"Using local cloud cache for checks: {len(rows)} rows.",
                "items": [],
            },
        )
        if not rows:
            return [], "local cloud cache empty; run manual sync first"
        return rows, ""

    try:
        rows = list_user_alphas_for_sync(
            api,
            sync_range,
            progress_callback=lambda progress: store.update(
                job_id,
                status="running",
                progress={
                    "phase": "cloud_sync",
                    "status_code": "CHECK_CLOUD_SYNC",
                    "mode": mode,
                    "range": sync_range,
                    "total": total,
                    "checked": 0,
                    "submittable": 0,
                    "blocked": 0,
                    "failed": 0,
                    "cloud_scanned": int(progress.get("scanned", 0) or 0),
                    "cloud_api_reported_total": int(progress.get("api_reported_total", 0) or 0),
                    "cloud_filter_window_count": int(
                        progress.get("filter_window_count")
                        or progress.get("api_reported_total")
                        or 0
                    ),
                    "cloud_page_size": int(progress.get("page_size", 0) or 0),
                    "cloud_page_limit": int(progress.get("page_limit", 0) or 0),
                    "cloud_pages_fetched": int(progress.get("pages_fetched") or progress.get("page_number") or 0),
                    "cloud_expected_pages": int(progress.get("expected_pages", 0) or 0),
                    "cloud_next_offset": int(progress.get("next_offset", 0) or 0),
                    "message": _cloud_refresh_progress_message(progress),
                    "items": [],
                },
            ),
        )
    except Exception as exc:
        message = safe_error_message(exc)
        logger.warning(
            "cloud alpha refresh failed for check job_id=%s range=%s: %s",
            job_id,
            sync_range,
            message,
            exc_info=True,
        )
        return [], message

    fields: list[dict[str, Any]] = []
    operators: list[dict[str, Any]] = []
    fields_count = 0
    operators_count = 0
    try:
        fields = api.list_fields("all", region)
        fields_count = len(fields)
        store.update(
            job_id,
            status="running",
            progress={
                "phase": "cloud_sync",
                "status_code": "CHECK_CONTEXT_FIELDS",
                "mode": mode,
                "range": sync_range,
                "total": total,
                "checked": 0,
                "submittable": 0,
                "blocked": 0,
                "failed": 0,
                "message": f"Updated official fields cache: {fields_count} rows.",
                "items": [],
            },
        )
    except Exception as exc:
        message = safe_error_message(exc)
        logger.warning(
            "official fields refresh failed for check job_id=%s range=%s: %s",
            job_id,
            sync_range,
            message,
            exc_info=True,
        )
        context_errors.append(f"fields refresh failed: {message}")

    try:
        operators = api.list_operators("all")
        operators_count = len(operators)
        store.update(
            job_id,
            status="running",
            progress={
                "phase": "cloud_sync",
                "status_code": "CHECK_CONTEXT_OPERATORS",
                "mode": mode,
                "range": sync_range,
                "total": total,
                "checked": 0,
                "submittable": 0,
                "blocked": 0,
                "failed": 0,
                "message": f"Updated official operators cache: {operators_count} rows.",
                "items": [],
            },
        )
    except Exception as exc:
        message = safe_error_message(exc)
        logger.warning(
            "official operators refresh failed for check job_id=%s range=%s: %s",
            job_id,
            sync_range,
            message,
            exc_info=True,
        )
        context_errors.append(f"operators refresh failed: {message}")

    try:
        datasets = (
            list_official_datasets_or_derive(
                api,
                fields,
                region=region,
                datasets_from_fields=datasets_from_fields,
                fallback_warning=on_dataset_fallback,
            )
            if fields_count > 0
            else []
        )
        persist_official_context(
            fields if fields_count > 0 else [],
            operators if operators_count > 0 else [],
            datasets,
        )
        if context_warnings:
            store.update(
                job_id,
                status="running",
                progress={
                    "phase": "cloud_sync",
                    "status_code": "CHECK_CONTEXT_WARNING",
                    "mode": mode,
                    "range": sync_range,
                    "total": total,
                    "checked": 0,
                    "submittable": 0,
                    "blocked": 0,
                    "failed": 0,
                    "context_warnings": context_warnings,
                    "message": "; ".join(context_warnings),
                    "items": [],
                },
            )
    except Exception as exc:
        message = safe_error_message(exc)
        logger.warning(
            "persist official context failed for check job_id=%s range=%s: %s",
            job_id,
            sync_range,
            message,
            exc_info=True,
        )
        context_errors.append(f"persist context failed: {message}")

    repo.merge_cloud_alphas(rows, sync_range=sync_range)
    store.update(
        job_id,
        status="running",
        progress={
            "phase": "cloud_sync",
            "status_code": "CHECK_CONTEXT_WARNING" if context_warnings else "CHECK_CLOUD_SYNC_SAVED",
            "mode": mode,
            "range": sync_range,
            "total": total,
            "checked": 0,
            "submittable": 0,
            "blocked": 0,
            "failed": 0,
            "cloud_saved_count": len(rows),
            "context_warnings": context_warnings,
            "message": (
                f"{'; '.join(context_warnings)}；本地已保存 {len(rows)} 条云端 Alpha，继续执行提交前复核。"
                if context_warnings
                else f"本地已保存 {len(rows)} 条云端 Alpha，继续执行提交前复核。"
            ),
            "items": [],
        },
    )
    error_msg = "; ".join(context_errors)[:500] if context_errors else ""
    return rows, error_msg
