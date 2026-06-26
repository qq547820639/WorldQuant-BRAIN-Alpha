"""Candidate file IO helpers for Web candidate simulation state."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from brain_alpha_ops.research.repository import ResearchRepository

_CANDIDATES_FILE_LOCK = threading.Lock()


def load_candidates(storage_dir: str) -> list[dict[str, Any]]:
    if not Path(storage_dir).is_dir():
        return []
    repo = ResearchRepository(storage_dir)
    path = repo._safe_storage_path("candidates.jsonl")
    with _CANDIDATES_FILE_LOCK:
        with repo._file_lock("candidates.jsonl"):
            return _read_candidates_unlocked(path)


def _read_candidates_unlocked(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def save_candidates(storage_dir: str, candidates: list[dict[str, Any]]) -> None:
    repo = ResearchRepository(storage_dir)
    path = repo._safe_storage_path("candidates.jsonl")
    with _CANDIDATES_FILE_LOCK:
        with repo._file_lock("candidates.jsonl"):
            current = _read_candidates_unlocked(path)
            merged = _merge_candidate_rows(current, candidates)
            tmp = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
            with tmp.open("w", encoding="utf-8") as f:
                for row in merged:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
            tmp.replace(path)


def candidate_update_row(candidate: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    update: dict[str, Any] = {}
    alpha_id = candidate.get("alpha_id")
    official_alpha_id = candidate.get("official_alpha_id")
    expression = candidate.get("expression")
    if alpha_id not in (None, ""):
        update["alpha_id"] = alpha_id
    elif official_alpha_id not in (None, ""):
        update["official_alpha_id"] = official_alpha_id
    elif expression not in (None, ""):
        update["expression"] = expression
        dataset = candidate.get("dataset_id")
        if dataset not in (None, ""):
            update["dataset_id"] = dataset
    for key in fields:
        if key in candidate:
            update[key] = candidate[key]
    return update


def save_candidate_update(storage_dir: str, candidate: dict[str, Any], fields: list[str]) -> None:
    update = candidate_update_row(candidate, fields)
    if update:
        save_candidates(storage_dir, [update])


def _merge_candidate_rows(current: list[dict[str, Any]], updates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    positions: dict[str, int] = {}
    for row in current:
        if not isinstance(row, dict):
            continue
        clean = dict(row)
        key = _candidate_merge_key(clean)
        if key and key not in positions:
            positions[key] = len(merged)
        merged.append(clean)
    for row in updates:
        if not isinstance(row, dict):
            continue
        clean = dict(row)
        key = _candidate_merge_key(clean)
        if key and key in positions:
            merged[positions[key]] = {**merged[positions[key]], **clean}
            continue
        if key:
            positions[key] = len(merged)
        merged.append(clean)
    return merged


def _candidate_merge_key(candidate: dict[str, Any]) -> str:
    for field in ("alpha_id", "official_alpha_id", "expression"):
        value = str(candidate.get(field) or "").strip()
        if value:
            if field == "expression":
                dataset = str(candidate.get("dataset_id") or "").strip()
                return f"{field}:{value}:dataset:{dataset}"
            return f"{field}:{value}"
    return ""


def append_backtest_record(storage_dir: str, record: dict[str, Any]) -> None:
    repo = ResearchRepository(storage_dir)
    path = repo._safe_storage_path("backtests.jsonl")
    with repo._file_lock("backtests.jsonl"):
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
