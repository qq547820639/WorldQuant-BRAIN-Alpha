from __future__ import annotations

"""Regression guard: prevent ``data/official_*.json`` from silently shrinking.

P3-19 (2026-06-13): a previous bug allowed the official context cache to
drift down to a few hundred fields when a partial refresh succeeded
without raising. The current cache has 8599 fields, 67 operators, and
20 datasets (see ``data/official_*meta.json``).

These tests load the real ``data/`` directory and assert that we still
have a meaningful catalog. The thresholds are conservative so the test
only fails if the cache actually breaks — not on every BRAIN release
that adds a few more fields.
"""

import json
from pathlib import Path

import pytest

from brain_alpha_ops.data.loader import OfficialDataLoader

DATA_DIR = Path("data")
FIELDS_PATH = DATA_DIR / "official_fields.json"
OPERATORS_PATH = DATA_DIR / "official_operators.json"
DATASETS_PATH = DATA_DIR / "official_datasets.json"
FIELDS_META = DATA_DIR / "official_fields.meta.json"

# Lower bounds are 50% of the current snapshot so we have plenty of
# headroom for the BRAIN team to remove retired fields without breaking
# the test, while still catching catastrophic data loss.
MIN_FIELDS = 4000
MIN_OPERATORS = 30
MIN_DATASETS = 10

def _meta_record_count(meta_path: Path) -> int | None:
    if not meta_path.is_file():
        return None
    try:
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return int(payload.get("record_count") or 0)

@pytest.mark.skipif(not FIELDS_PATH.is_file(), reason="official context not loaded in this environment")
def test_official_fields_count_meets_minimum():
    """At least MIN_FIELDS fields must be present."""
    payload = json.loads(FIELDS_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, list)
    assert len(payload) >= MIN_FIELDS, (
        f"official_fields.json dropped below the safe floor: "
        f"got {len(payload)} records, expected >= {MIN_FIELDS}"
    )

@pytest.mark.skipif(not OPERATORS_PATH.is_file(), reason="official operators not loaded")
def test_official_operators_count_meets_minimum():
    payload = json.loads(OPERATORS_PATH.read_text(encoding="utf-8"))
    assert len(payload) >= MIN_OPERATORS, (
        f"official_operators.json dropped below the safe floor: "
        f"got {len(payload)}, expected >= {MIN_OPERATORS}"
    )

@pytest.mark.skipif(not DATASETS_PATH.is_file(), reason="official datasets not loaded")
def test_official_datasets_count_meets_minimum():
    payload = json.loads(DATASETS_PATH.read_text(encoding="utf-8"))
    assert len(payload) >= MIN_DATASETS, (
        f"official_datasets.json dropped below the safe floor: "
        f"got {len(payload)}, expected >= {MIN_DATASETS}"
    )

@pytest.mark.skipif(not FIELDS_PATH.is_file(), reason="official context not loaded in this environment")
def test_meta_record_count_matches_json_payload():
    """The meta file's ``record_count`` must agree with the JSON list length."""
    meta_count = _meta_record_count(FIELDS_META)
    if meta_count is None:
        pytest.skip("official_fields.meta.json not present")
    payload = json.loads(FIELDS_PATH.read_text(encoding="utf-8"))
    assert meta_count == len(payload), (
        f"official_fields.meta.json claims {meta_count} records but the "
        f"JSON file has {len(payload)}; meta and payload have drifted"
    )

@pytest.mark.skipif(not FIELDS_PATH.is_file(), reason="official context not loaded in this environment")
def test_official_data_loader_loads_above_minimum():
    """End-to-end: the singleton loader must report at least MIN_FIELDS fields."""
    loader = OfficialDataLoader()
    loader.load_all(str(DATA_DIR))
    assert loader.field_count >= MIN_FIELDS, (
        f"OfficialDataLoader loaded {loader.field_count} fields, "
        f"expected >= {MIN_FIELDS}"
    )
    assert loader.operator_count >= MIN_OPERATORS
    assert loader.dataset_count >= MIN_DATASETS
