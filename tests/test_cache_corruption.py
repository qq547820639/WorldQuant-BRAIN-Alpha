"""F1.1 — Cache corruption tests.

Spec ref: .trae/specs/overhaul-alpha-production-quality/spec.md
  Scenario: 缓存损坏测试 — ``official_fields.json`` 损坏 → 系统检测到损坏，
  进入"需要人工确认"状态，不崩溃。

Verifies that:
  - Corrupted ``official_fields.json`` / ``official_operators.json`` /
    ``official_datasets.json`` is detected by ``ProductionHealthMonitor`` and
    the registry degrades gracefully (no crash).
  - Missing files are tolerated as a "fresh start" state, not corruption.
  - CapabilityResolutionError surfaces a "needs human confirmation" hint.

The cache files are simulated under ``tmp_path`` and the registry is reset
between tests so each scenario builds from a fresh state.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from brain_alpha_ops.data.capability_registry import (
    CapabilityRegistry,
    CapabilityResolutionError,
    build_registry_from_official_context,
    get_registry,
    reset_registry,
)
from brain_alpha_ops.monitoring.production_health import ProductionHealthMonitor
from brain_alpha_ops.monitoring.unified_monitor import Severity


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

_VALID_FIELDS = [
    {
        "id": "close",
        "name": "close",
        "description": "Closing price",
        "dataset": {"id": "model77", "name": "Analysts' Factor Model"},
        "dataset_id": "model77",
        "category": "model",
        "type": "MATRIX",
        "dateUpdated": "2026-01-01",
    }
]
_VALID_OPERATORS = [
    {"name": "rank", "category": "Cross-sectional", "definition": "rank(x)"}
]
_VALID_DATASETS = [
    {"id": "model77", "name": "Analysts' Factor Model", "field_count": 1}
]


def _write_valid_cache(data_dir: Path) -> None:
    (data_dir / "official_fields.json").write_text(
        json.dumps(_VALID_FIELDS), encoding="utf-8"
    )
    (data_dir / "official_operators.json").write_text(
        json.dumps(_VALID_OPERATORS), encoding="utf-8"
    )
    (data_dir / "official_datasets.json").write_text(
        json.dumps(_VALID_DATASETS), encoding="utf-8"
    )


def _write_corrupted(path: Path) -> None:
    """Write a file that looks like JSON but fails json.loads()."""
    path.write_text("{not valid json: trailing garbage", encoding="utf-8")


@pytest.fixture(autouse=True)
def _reset_registry_between_tests():
    """Ensure each test rebuilds the registry from its own tmp_path."""
    reset_registry()
    yield
    reset_registry()


# --------------------------------------------------------------------------- #
# Capability registry: graceful degradation
# --------------------------------------------------------------------------- #

def test_corrupted_official_fields_does_not_crash_registry(tmp_path: Path):
    """Corrupted official_fields.json → loader logs and skips, no crash."""
    _write_corrupted(tmp_path / "official_fields.json")
    (tmp_path / "official_operators.json").write_text(
        json.dumps(_VALID_OPERATORS), encoding="utf-8"
    )
    (tmp_path / "official_datasets.json").write_text(
        json.dumps(_VALID_DATASETS), encoding="utf-8"
    )

    registry = build_registry_from_official_context(tmp_path)

    assert isinstance(registry, CapabilityRegistry)
    # Fields are missing (corrupted file skipped), but operators/datasets load.
    assert registry.fields() == set()
    assert "rank" in registry.operators()
    assert "model77" in registry.datasets()


def test_corrupted_official_operators_does_not_crash_registry(tmp_path: Path):
    _write_corrupted(tmp_path / "official_operators.json")
    (tmp_path / "official_fields.json").write_text(
        json.dumps(_VALID_FIELDS), encoding="utf-8"
    )
    (tmp_path / "official_datasets.json").write_text(
        json.dumps(_VALID_DATASETS), encoding="utf-8"
    )

    registry = build_registry_from_official_context(tmp_path)

    assert "close" in registry.fields()
    assert registry.operators() == set()  # corrupted → empty
    assert "model77" in registry.datasets()


def test_corrupted_official_datasets_does_not_crash_registry(tmp_path: Path):
    _write_corrupted(tmp_path / "official_datasets.json")
    (tmp_path / "official_fields.json").write_text(
        json.dumps(_VALID_FIELDS), encoding="utf-8"
    )
    (tmp_path / "official_operators.json").write_text(
        json.dumps(_VALID_OPERATORS), encoding="utf-8"
    )

    registry = build_registry_from_official_context(tmp_path)

    assert "close" in registry.fields()
    assert "rank" in registry.operators()
    assert registry.datasets() == set()  # corrupted → empty


def test_missing_files_degrade_to_empty_registry(tmp_path: Path):
    """No official_*.json files at all → empty registry, no exception.

    This mirrors the "first run, cache not yet fetched" state which must NOT
    be treated as corruption.
    """
    registry = build_registry_from_official_context(tmp_path)

    assert isinstance(registry, CapabilityRegistry)
    assert registry.fields() == set()
    assert registry.operators() == set()
    assert registry.datasets() == set()
    assert len(registry) == 0


def test_missing_capability_surfaces_human_confirmation_hint(tmp_path: Path):
    """A missing capability lookup raises CapabilityResolutionError whose
    message explicitly says "needs human confirmation" — surfacing the
    "需要人工确认" state to upstream code rather than silently guessing.
    """
    _write_valid_cache(tmp_path)
    registry = build_registry_from_official_context(tmp_path)

    with pytest.raises(CapabilityResolutionError) as exc_info:
        registry.get("nonexistent_field", kind="field")

    message = str(exc_info.value)
    assert "needs human confirmation" in message
    assert "nonexistent_field" in message


def test_get_registry_singleton_survives_partial_corruption(
    tmp_path: Path, monkeypatch
):
    """get_registry() must not crash when one of the cache files is
    corrupted; it falls back to defaults and the corrupted kind is empty.
    """
    _write_corrupted(tmp_path / "official_fields.json")
    (tmp_path / "official_operators.json").write_text(
        json.dumps(_VALID_OPERATORS), encoding="utf-8"
    )
    (tmp_path / "official_datasets.json").write_text(
        json.dumps(_VALID_DATASETS), encoding="utf-8"
    )

    # Redirect the data dir used by get_registry()'s private helper.
    import brain_alpha_ops.data.capability_registry as reg_pkg

    monkeypatch.setattr(reg_pkg, "_resolve_data_dir", lambda: tmp_path)

    registry = get_registry()
    # Fields empty (corrupted), operators/datasets present, defaults present.
    assert registry.fields() == set()
    assert "rank" in registry.operators()
    # Default BrainSettings capabilities (region/universe/...) are present.
    assert any(e.kind == "region" for e in registry.entries)


# --------------------------------------------------------------------------- #
# ProductionHealthMonitor: cache_state detection
# --------------------------------------------------------------------------- #

def test_health_monitor_detects_corrupted_official_fields(tmp_path: Path):
    """ProductionHealthMonitor.check_cache_state flags corrupted
    official_fields.json as DEGRADED with a restore action.
    """
    _write_corrupted(tmp_path / "official_fields.json")
    monitor = ProductionHealthMonitor()

    check = monitor.check_cache_state(str(tmp_path))

    assert check.severity == Severity.DEGRADED
    assert "official cache file(s) corrupted" in check.message
    assert "official_fields.json" in check.message
    assert "restore" in check.suggested_action
    corrupted = check.context_snapshot["corrupted_files"]
    assert any(c["file"] == "official_fields.json" for c in corrupted)


def test_health_monitor_detects_corrupted_official_operators(tmp_path: Path):
    _write_corrupted(tmp_path / "official_operators.json")
    monitor = ProductionHealthMonitor()

    check = monitor.check_cache_state(str(tmp_path))

    assert check.severity == Severity.DEGRADED
    assert "official_operators.json" in check.message
    assert any(
        c["file"] == "official_operators.json"
        for c in check.context_snapshot["corrupted_files"]
    )


def test_health_monitor_detects_corrupted_official_datasets(tmp_path: Path):
    _write_corrupted(tmp_path / "official_datasets.json")
    monitor = ProductionHealthMonitor()

    check = monitor.check_cache_state(str(tmp_path))

    assert check.severity == Severity.DEGRADED
    assert "official_datasets.json" in check.message
    assert any(
        c["file"] == "official_datasets.json"
        for c in check.context_snapshot["corrupted_files"]
    )


def test_health_monitor_detects_multiple_corrupted_files(tmp_path: Path):
    _write_corrupted(tmp_path / "official_fields.json")
    _write_corrupted(tmp_path / "official_operators.json")
    monitor = ProductionHealthMonitor()

    check = monitor.check_cache_state(str(tmp_path))

    assert check.severity == Severity.DEGRADED
    corrupted = check.context_snapshot["corrupted_files"]
    assert len(corrupted) == 2
    assert {c["file"] for c in corrupted} == {
        "official_fields.json",
        "official_operators.json",
    }


def test_health_monitor_treats_missing_files_as_ok(tmp_path: Path):
    """Missing files (fresh-start state) must NOT be flagged as corruption."""
    monitor = ProductionHealthMonitor()

    check = monitor.check_cache_state(str(tmp_path))

    assert check.severity == Severity.OK
    assert check.context_snapshot["checked_files"] == []


def test_health_monitor_reports_ok_when_all_files_valid(tmp_path: Path):
    _write_valid_cache(tmp_path)
    monitor = ProductionHealthMonitor()

    check = monitor.check_cache_state(str(tmp_path))

    assert check.severity == Severity.OK
    checked = check.context_snapshot["checked_files"]
    assert "official_fields.json" in checked
    assert "official_operators.json" in checked
    assert "official_datasets.json" in checked


# --------------------------------------------------------------------------- #
# End-to-end: corruption detection + registry degradation together
# --------------------------------------------------------------------------- #

def test_corruption_detected_and_registry_degrades_without_crash(
    tmp_path: Path, monkeypatch
):
    """End-to-end: a corrupted cache is detected by the health monitor AND
    the registry still returns (with the corrupted kind empty), so the
    pipeline can surface a "needs human confirmation" state without crashing.
    """
    _write_corrupted(tmp_path / "official_fields.json")
    (tmp_path / "official_operators.json").write_text(
        json.dumps(_VALID_OPERATORS), encoding="utf-8"
    )
    (tmp_path / "official_datasets.json").write_text(
        json.dumps(_VALID_DATASETS), encoding="utf-8"
    )

    # 1) Health monitor detects corruption.
    monitor = ProductionHealthMonitor()
    health = monitor.check_cache_state(str(tmp_path))
    assert health.severity == Severity.DEGRADED

    # 2) Registry still builds (degraded) without raising.
    registry = build_registry_from_official_context(tmp_path)
    assert registry.fields() == set()
    assert "rank" in registry.operators()

    # 3) A field lookup now surfaces the "needs human confirmation" hint
    #    rather than silently returning a wrong answer.
    with pytest.raises(CapabilityResolutionError) as exc_info:
        registry.get("close", kind="field")
    assert "needs human confirmation" in str(exc_info.value)
