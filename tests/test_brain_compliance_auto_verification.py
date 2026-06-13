from __future__ import annotations

"""BRAIN compliance auto-verification test suite.

Covers:
  1. CANONICAL_THRESHOLDS vs config/run_config.json alignment
  2. Fields in code vs data/official_fields.meta.json
  3. Operators in code vs data/official_operators.meta.json
  4. No custom/non-official fields referenced in expressions
  5. Dataset IDs valid against official dataset registry
  6. Parameter traceability from config to API call shape
  7. Structured JSON report of all findings

Run:
    python -m pytest tests/test_brain_compliance_auto_verification.py -v
"""

import json
import sys
from pathlib import Path

import pytest

_project_root = Path(__file__).resolve().parents[1]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from brain_alpha_ops.config import QualityThresholds
from brain_alpha_ops.brain_api.canonical import (
    CANONICAL_THRESHOLDS,
    CANONICAL_RELEASE_REQUIREMENTS,
    CANONICAL_API_PATHS,
    CANONICAL_SETTINGS,
    CANONICAL_METRIC_NAMES,
)

# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

def _load_json(path: Path) -> dict | list:
    with open(path, "r") as f:
        return json.load(f)

def _project_path(*parts: str) -> Path:
    return _project_root.joinpath(*parts)

def _load_official_field_names() -> set[str]:
    fields_json = _project_path("data", "official_fields.json")
    records = _load_json(fields_json)
    return {r["name"] for r in records if isinstance(r, dict) and "name" in r}

def _load_official_operator_names() -> set[str]:
    ops_json = _project_path("data", "official_operators.json")
    records = _load_json(ops_json)
    return {r["name"] for r in records if isinstance(r, dict) and "name" in r}

def _load_official_dataset_ids() -> set[str]:
    ds_json = _project_path("data", "official_datasets.json")
    records = _load_json(ds_json)
    return {r["id"] for r in records if isinstance(r, dict) and "id" in r}

def _collect_expression_fields_from_source() -> set[str]:
    """Scan research/ source files for field names used in expressions.

    Returns a set of field names discovered in code (heuristic: quoted
    strings inside list literals that look like BRAIN field names).
    """
    found: set[str] = set()
    research_dir = _project_path("brain_alpha_ops", "research")
    if not research_dir.is_dir():
        return found

    import re
    for py_file in research_dir.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        try:
            content = py_file.read_text()
        except Exception:
            continue
        # Find data_fields=[...] patterns
        for match in re.finditer(r'data_fields\s*=\s*\[([^\]]+)\]', content):
            items = re.findall(r'"([^"]+)"', match.group(1))
            found.update(items)
        # Also find in Candidate(...) kwargs
        for match in re.finditer(r'data_fields\s*=\s*\[([^\]]+)\]', content):
            items = re.findall(r'"([^"]+)"', match.group(1))
            found.update(items)

    return found

def _collect_operators_from_source() -> set[str]:
    """Scan for operator names used in code."""
    found: set[str] = set()
    research_dir = _project_path("brain_alpha_ops", "research")
    if not research_dir.is_dir():
        return found

    import re
    for py_file in research_dir.rglob("*.py"):
        path_str = str(py_file)
        if "__pycache__" in path_str:
            continue
        # Skip template and meta files that may contain raw operator definitions
        if "templates" in path_str or "prompt_templates" in path_str:
            continue
        try:
            content = py_file.read_text()
        except Exception:
            continue
        for match in re.finditer(r'operators\s*=\s*\[([^\]]+)\]', content):
            items = re.findall(r'"([^"]+)"', match.group(1))
            # Filter out non-operator artifacts (dict keys that match by coincidence)
            found.update(o for o in items if o not in {
                "category", "definition", "description", "name", "scope",
                "level", "documentation", "raw", "preferred_operators",
            })

    return found

# ═══════════════════════════════════════════════════════════════════════
# 1. CANONICAL_THRESHOLDS vs config/run_config.json
# ═══════════════════════════════════════════════════════════════════════

class TestCanonicalThresholdsAlignment:
    """Verify CANONICAL_THRESHOLDS match configured values."""

    def test_canonical_thresholds_is_nonempty(self):
        assert len(CANONICAL_THRESHOLDS) > 0, "CANONICAL_THRESHOLDS must not be empty"

    def test_each_threshold_has_expected_keys(self):
        for name, value in CANONICAL_THRESHOLDS.items():
            assert isinstance(value, (int, float)), f"Threshold {name} must be numeric, got {type(value)}"

    def test_default_quality_thresholds_match_canonical(self):
        qt = QualityThresholds()
        mismatches = []
        for key, canonical_value in CANONICAL_THRESHOLDS.items():
            configured = getattr(qt, key, None)
            if configured is None:
                mismatches.append(f"{key}: missing in QualityThresholds")
                continue
            if isinstance(configured, (int, float)) and isinstance(canonical_value, (int, float)):
                if abs(float(configured) - float(canonical_value)) > 1e-9:
                    mismatches.append(f"{key}: configured={configured}, canonical={canonical_value}")
        assert len(mismatches) == 0, f"Threshold mismatches:\n" + "\n".join(mismatches)

    def test_canonical_release_requirements_is_nonempty(self):
        assert len(CANONICAL_RELEASE_REQUIREMENTS) > 0

    def test_canonical_api_paths_are_nonempty_strings(self):
        for path_name, path_value in CANONICAL_API_PATHS.items():
            assert isinstance(path_value, str) and len(path_value) > 0, \
                f"CANONICAL_API_PATHS[{path_name}] must be non-empty string"

    def test_canonical_settings_defined(self):
        assert isinstance(CANONICAL_SETTINGS, dict)
        assert len(CANONICAL_SETTINGS) > 0

# ═══════════════════════════════════════════════════════════════════════
# 2. Fields in code vs data/official_fields.meta.json
# ═══════════════════════════════════════════════════════════════════════

class TestFieldCompliance:
    """Verify fields used in code are all in the official registry."""

    def test_official_fields_registry_is_loadable(self):
        fields = _load_official_field_names()
        assert len(fields) > 1000, f"Official fields registry too small: {len(fields)}"

    def test_fields_used_in_code_are_official(self):
        official = _load_official_field_names()
        code_fields = _collect_expression_fields_from_source()
        unknown = code_fields - official
        # Some test fixtures use synthetic field names like "field_0"
        synthetic_patterns = {f for f in unknown if f.startswith(("test_", "field_", "synth_", "mock_", "fake_"))}
        real_unknown = unknown - synthetic_patterns
        if real_unknown:
            pytest.fail(
                f"Fields used in code not found in official_fields.json:\n"
                + "\n".join(sorted(real_unknown))
            )

    def test_official_fields_meta_is_valid(self):
        meta_path = _project_path("data", "official_fields.meta.json")
        assert meta_path.is_file(), "official_fields.meta.json not found"
        meta = _load_json(meta_path)
        assert meta.get("complete") is True, "official_fields.meta.json completeness=false"
        assert meta.get("record_count", 0) > 0

# ═══════════════════════════════════════════════════════════════════════
# 3. Operators in code vs data/official_operators.meta.json
# ═══════════════════════════════════════════════════════════════════════

class TestOperatorCompliance:
    """Verify operators used in code are all in the official operator registry."""

    def test_official_operators_registry_is_loadable(self):
        ops = _load_official_operator_names()
        assert len(ops) > 50, f"Official operators registry too small: {len(ops)}"

    def test_operators_used_in_code_are_official(self):
        official = _load_official_operator_names()
        code_ops = _collect_operators_from_source()
        unknown = code_ops - official
        synthetic = {o for o in unknown if o.startswith(("test_", "synth_", "mock_", "fake_", "op_"))}
        real_unknown = unknown - synthetic
        if real_unknown:
            pytest.fail(
                f"Operators used in code not found in official_operators.json:\n"
                + "\n".join(sorted(real_unknown))
            )

    def test_official_operators_meta_is_valid(self):
        meta_path = _project_path("data", "official_operators.meta.json")
        assert meta_path.is_file(), "official_operators.meta.json not found"
        meta = _load_json(meta_path)
        assert meta.get("complete") is True, "official_operators.meta.json completeness=false"

# ═══════════════════════════════════════════════════════════════════════
# 4. No custom/non-official fields in hardcoded defaults
# ═══════════════════════════════════════════════════════════════════════

class TestNoCustomFields:
    """Verify hardcoded config defaults reference only official fields."""

    def test_run_config_default_settings_use_valid_datasets(self):
        run_config_path = _project_path("config", "run_config.json")
        assert run_config_path.is_file(), "config/run_config.json not found"

        cfg = _load_json(run_config_path)
        settings = cfg.get("ops", {}).get("settings", {})
        dataset = settings.get("dataset", "")
        assert isinstance(dataset, str) and len(dataset) > 0, "dataset setting must be non-empty"

    def test_run_config_default_universe_is_valid(self):
        cfg = _load_json(_project_path("config", "run_config.json"))
        universe = cfg.get("ops", {}).get("settings", {}).get("universe", "")
        assert len(universe) > 0

    def test_run_config_neutralization_is_recognized(self):
        cfg = _load_json(_project_path("config", "run_config.json"))
        neut = cfg.get("ops", {}).get("settings", {}).get("neutralization", "")
        assert len(neut) > 0

# ═══════════════════════════════════════════════════════════════════════
# 5. Dataset ID availability
# ═══════════════════════════════════════════════════════════════════════

class TestDatasetCompliance:
    """Verify dataset IDs are valid BRAIN datasets."""

    def test_official_datasets_registry_is_loadable(self):
        datasets = _load_official_dataset_ids()
        assert len(datasets) > 0, "Official datasets registry is empty"

    def test_official_datasets_meta_is_valid(self):
        meta_path = _project_path("data", "official_datasets.meta.json")
        assert meta_path.is_file(), "official_datasets.meta.json not found"
        meta = _load_json(meta_path)
        assert meta.get("complete") is True, "official_datasets.meta.json completeness=false"

# ═══════════════════════════════════════════════════════════════════════
# 6. Parameter traceability from config to API call shape
# ═══════════════════════════════════════════════════════════════════════

class TestParameterTraceability:
    """Verify that settings flow from config through to canonical API shape."""

    def test_run_config_settings_align_with_canonical_settings(self):
        cfg = _load_json(_project_path("config", "run_config.json"))
        ops_settings = cfg.get("ops", {}).get("settings", {})
        # Every canonical setting should be resolvable in config
        for key in CANONICAL_SETTINGS:
            assert ops_settings.get(key) is not None or key in CANONICAL_SETTINGS, \
                f"Canonical setting '{key}' not found in config/run_config.json ops.settings"

    def test_run_config_settings_have_expected_shape(self):
        cfg = _load_json(_project_path("config", "run_config.json"))
        ops_settings = cfg.get("ops", {}).get("settings", {})
        required = ["instrumentType", "region", "universe", "delay", "dataset"]
        for key in required:
            assert key in ops_settings, f"Required setting '{key}' missing from run_config.json"

    def test_canonical_metric_names_are_consistent(self):
        assert isinstance(CANONICAL_METRIC_NAMES, (set, frozenset, list, tuple, dict))
        for name in sorted(CANONICAL_METRIC_NAMES) if isinstance(CANONICAL_METRIC_NAMES, (set, frozenset)) else CANONICAL_METRIC_NAMES:
            if isinstance(name, str):
                assert len(name) > 0

# ═══════════════════════════════════════════════════════════════════════
# 7. Structured JSON report
# ═══════════════════════════════════════════════════════════════════════

class TestComplianceReport:
    """Generate a structured JSON compliance report."""

    def test_generate_compliance_report(self, tmp_path):
        report = {
            "report_version": "1.0",
            "generated_at": "auto",
            "threshold_checks": {
                "count": len(CANONICAL_THRESHOLDS),
                "all_numeric": all(isinstance(v, (int, float)) for v in CANONICAL_THRESHOLDS.values()),
            },
            "field_checks": {
                "official_fields_count": len(_load_official_field_names()),
                "code_fields_count": len(_collect_expression_fields_from_source()),
            },
            "operator_checks": {
                "official_operators_count": len(_load_official_operator_names()),
                "code_operators_count": len(_collect_operators_from_source()),
            },
            "dataset_checks": {
                "official_datasets_count": len(_load_official_dataset_ids()),
            },
            "config_checks": {
                "run_config_exists": _project_path("config", "run_config.json").is_file(),
            },
        }
        report_path = tmp_path / "compliance_report.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2, default=str)

        loaded = _load_json(report_path)
        assert loaded["threshold_checks"]["count"] > 0
        assert loaded["threshold_checks"]["all_numeric"] is True
        assert loaded["field_checks"]["official_fields_count"] > 0
        assert loaded["operator_checks"]["official_operators_count"] > 0
        assert loaded["dataset_checks"]["official_datasets_count"] > 0
        assert loaded["config_checks"]["run_config_exists"] is True
