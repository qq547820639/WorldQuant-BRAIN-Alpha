"""Validation for persisted official BRAIN context files."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from brain_alpha_ops.config import load_run_config, runtime_project_root
from brain_alpha_ops.data.cache_metadata import CONTEXT_CACHE_METADATA_SCHEMA, metadata_path_for


OFFICIAL_CONTEXT_VALIDATION_SCHEMA = "official_context_validation.v1"
EXPECTED_CONTEXT_FILES = {
    "official_fields.json": ("fields", ("id", "name")),
    "official_operators.json": ("operators", ("name",)),
    "official_datasets.json": ("datasets", ("id",)),
}


def validate_official_context(
    *,
    config_path: str | Path | None = None,
    data_dir: str | Path | None = None,
    require_metadata: bool = True,
    require_official_source: bool = True,
) -> dict[str, Any]:
    """Validate official fields/operators/datasets plus cache lineage metadata."""
    root = _resolve_data_dir(config_path=config_path, data_dir=data_dir)
    files: dict[str, dict[str, Any]] = {}
    findings: list[dict[str, Any]] = []
    loaded: dict[str, list[dict[str, Any]]] = {}

    for filename, (kind, identity_keys) in EXPECTED_CONTEXT_FILES.items():
        path = root / filename
        rows, file_findings = _load_rows(path)
        findings.extend(file_findings)
        loaded[filename] = rows
        metadata = _read_metadata(path)
        file_summary = _file_summary(
            path,
            kind=kind,
            rows=rows,
            metadata=metadata,
            identity_keys=identity_keys,
            require_metadata=require_metadata,
            require_official_source=require_official_source,
        )
        files[filename] = file_summary
        findings.extend(file_summary.pop("_findings"))

    lineage = _lineage_summary(loaded)
    findings.extend(lineage.pop("_findings"))

    blocking_count = sum(1 for finding in findings if finding.get("severity") == "BLOCKING")
    p1_count = sum(1 for finding in findings if finding.get("severity") == "P1")
    return {
        "ok": not findings,
        "blocking_ok": blocking_count == 0,
        "blocking_count": blocking_count,
        "p1_count": p1_count,
        "schema_version": OFFICIAL_CONTEXT_VALIDATION_SCHEMA,
        "data_dir": str(root),
        "files": files,
        "lineage": lineage,
        "findings": findings,
    }


def _resolve_data_dir(*, config_path: str | Path | None, data_dir: str | Path | None) -> Path:
    if data_dir is not None:
        target = Path(data_dir)
    else:
        try:
            target = Path(load_run_config(config_path).ops.storage_dir)
        except Exception:
            target = runtime_project_root() / "data"
    if not target.is_absolute():
        target = runtime_project_root() / target
    return target.resolve()


def _load_rows(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [], [_finding("missing_file", path, f"{path.name} is missing")]
    except json.JSONDecodeError as exc:
        return [], [_finding("invalid_json", path, f"{path.name} is not valid JSON: {exc}")]
    except OSError as exc:
        return [], [_finding("read_error", path, f"{path.name} could not be read: {exc}")]
    if not isinstance(payload, list):
        return [], [_finding("invalid_shape", path, f"{path.name} must contain a JSON array")]
    rows = [row for row in payload if isinstance(row, dict)]
    findings: list[dict[str, Any]] = []
    if len(rows) != len(payload):
        findings.append(_finding("non_object_rows", path, f"{path.name} contains non-object rows"))
    if not rows:
        findings.append(_finding("empty_context_file", path, f"{path.name} has no records"))
    return rows, findings


def _file_summary(
    path: Path,
    *,
    kind: str,
    rows: list[dict[str, Any]],
    metadata: dict[str, Any],
    identity_keys: tuple[str, ...],
    require_metadata: bool,
    require_official_source: bool,
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    identifiers = [_identifier(row, identity_keys) for row in rows]
    identifiers = [item for item in identifiers if item]
    duplicate_ids = sorted(item for item, count in Counter(identifiers).items() if count > 1)
    missing_identity_count = max(0, len(rows) - len(identifiers))
    if missing_identity_count:
        findings.append(
            _finding(
                "missing_identity",
                path,
                f"{path.name} has {missing_identity_count} rows without any of {', '.join(identity_keys)}",
            )
        )
    if duplicate_ids:
        findings.append(
            _finding(
                "duplicate_identity",
                path,
                f"{path.name} has duplicate official identifiers: {', '.join(duplicate_ids[:10])}",
            )
        )

    if kind == "datasets":
        for row in rows:
            missing = [key for key in ("id", "name", "field_count") if key not in row]
            if missing:
                findings.append(
                    _finding(
                        "dataset_shape_incomplete",
                        path,
                        f"dataset {row.get('id') or '?'} is missing {', '.join(missing)}",
                    )
                )
            if "field_count" in row and _int_or_none(row.get("field_count")) is None:
                findings.append(
                    _finding(
                        "dataset_field_count_invalid",
                        path,
                        f"dataset {row.get('id') or '?'} has a non-numeric field_count",
                    )
                )

    metadata_summary = _metadata_summary(
        path,
        rows=rows,
        metadata=metadata,
        require_metadata=require_metadata,
        require_official_source=require_official_source,
    )
    findings.extend(metadata_summary.pop("_findings"))
    return {
        "path": str(path),
        "kind": kind,
        "record_count": len(rows),
        "identity_count": len(identifiers),
        "duplicate_identity_count": len(duplicate_ids),
        "missing_identity_count": missing_identity_count,
        "metadata": metadata_summary,
        "_findings": findings,
    }


def _metadata_summary(
    path: Path,
    *,
    rows: list[dict[str, Any]],
    metadata: dict[str, Any],
    require_metadata: bool,
    require_official_source: bool,
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    if not metadata:
        if require_metadata:
            findings.append(_finding("missing_metadata", path, f"{metadata_path_for(path).name} is missing", severity="P1"))
        return {
            "present": False,
            "source": "",
            "record_count": 0,
            "complete": False,
            "sha256_matches": False,
            "is_stale": True,
            "_findings": findings,
        }

    expected_sha = _items_hash(rows)
    sha_matches = str(metadata.get("sha256") or "") == expected_sha
    record_count_matches = int(metadata.get("record_count", -1) or -1) == len(rows)
    source = str(metadata.get("source") or "unknown")
    schema_ok = metadata.get("schema_version") == CONTEXT_CACHE_METADATA_SCHEMA
    complete = bool(metadata.get("complete"))
    expires_at = _parse_timestamp(metadata.get("expires_at"))
    is_stale = bool(expires_at and expires_at <= datetime.now(timezone.utc))

    if not schema_ok:
        findings.append(_finding("metadata_schema_mismatch", path, f"{metadata_path_for(path).name} schema is not current"))
    if require_official_source and source != "official_api":
        findings.append(_finding("metadata_source_not_official", path, f"{path.name} source is {source}, expected official_api", severity="P1"))
    if not record_count_matches:
        findings.append(_finding("metadata_record_count_mismatch", path, f"{path.name} metadata record_count does not match the JSON file"))
    if not sha_matches:
        findings.append(_finding("metadata_hash_mismatch", path, f"{path.name} metadata sha256 does not match the JSON file"))
    if not complete:
        findings.append(_finding("metadata_incomplete", path, f"{path.name} metadata is not marked complete", severity="P1"))
    if is_stale:
        findings.append(_finding("metadata_stale", path, f"{path.name} metadata has expired", severity="P1"))

    return {
        "present": True,
        "source": source,
        "record_count": int(metadata.get("record_count", 0) or 0),
        "complete": complete,
        "sha256_matches": sha_matches,
        "record_count_matches": record_count_matches,
        "schema_ok": schema_ok,
        "saved_at": str(metadata.get("saved_at") or ""),
        "expires_at": str(metadata.get("expires_at") or ""),
        "is_stale": is_stale,
        "_findings": findings,
    }


def _lineage_summary(loaded: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    fields = loaded.get("official_fields.json", [])
    datasets = loaded.get("official_datasets.json", [])
    field_count = len(fields)
    dataset_field_count_sum = sum(_int_or_none(row.get("field_count")) or 0 for row in datasets)
    dataset_refs = _dataset_refs_from_fields(fields)
    dataset_ids = {str(row.get("id") or "").strip() for row in datasets if str(row.get("id") or "").strip()}
    missing_dataset_refs = sorted(dataset_refs - dataset_ids)
    findings: list[dict[str, Any]] = []

    field_count_sum_matches = dataset_field_count_sum == field_count if datasets and field_count else False
    if datasets and field_count and not field_count_sum_matches:
        findings.append(
            {
                "code": "dataset_field_count_mismatch",
                "path": "official_datasets.json",
                "severity": "BLOCKING",
                "message": (
                    "sum(official_datasets.field_count) does not match official_fields record count "
                    f"({dataset_field_count_sum} != {field_count})"
                ),
            }
        )
    if missing_dataset_refs:
        findings.append(
            {
                "code": "field_dataset_reference_missing",
                "path": "official_fields.json",
                "severity": "BLOCKING",
                "message": f"field metadata references datasets not present in official_datasets.json: {missing_dataset_refs[:10]}",
            }
        )

    return {
        "field_count": field_count,
        "dataset_count": len(datasets),
        "dataset_field_count_sum": dataset_field_count_sum,
        "field_count_sum_matches": field_count_sum_matches,
        "field_dataset_reference_count": len(dataset_refs),
        "missing_field_dataset_references": missing_dataset_refs,
        "_findings": findings,
    }


def _dataset_refs_from_fields(fields: list[dict[str, Any]]) -> set[str]:
    refs: set[str] = set()
    for field in fields:
        raw = field.get("dataset")
        if isinstance(raw, dict):
            dataset_id = str(raw.get("id") or "").strip()
        else:
            dataset_id = str(field.get("dataset_id") or raw or "").strip()
        if dataset_id:
            refs.add(dataset_id)
    return refs


def _read_metadata(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(metadata_path_for(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _identifier(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _items_hash(items: list[dict[str, Any]]) -> str:
    payload = json.dumps(items, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _finding(code: str, path: Path, message: str, *, severity: str = "BLOCKING") -> dict[str, Any]:
    return {
        "code": code,
        "path": str(path),
        "severity": severity,
        "message": message,
    }
