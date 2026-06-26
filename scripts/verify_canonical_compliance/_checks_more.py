"""Canonical compliance checks for runtime/data-derived values.

Contains checks 4-6:
* Scoring simulation zero deviation
* Field/operator no custom extension
* Dataset ID availability
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ._config import _context_validation_for_data_dir


# ═══════════════════════════════════════════════════════════════════════
# Check 4: Scoring Simulation Zero Deviation
# ═══════════════════════════════════════════════════════════════════════

def _check_scoring_simulation(run_config: Any) -> dict[str, Any]:
    """Verify scoring system produces zero-deviation API output."""
    from brain_alpha_ops.config import BrainSettings
    from brain_alpha_ops.models import Candidate
    from brain_alpha_ops.scoring.official_scoring import OfficialScoringSystem

    # Build a diagnostic probe candidate
    probe = Candidate(
        alpha_id="canonical_compliance_probe",
        expression="rank(ts_delta(close, 20)) + rank(ts_mean(volume / adv20, 20))",
        family="Hybrid",
        hypothesis="Cross-sectional price momentum confirmed by liquidity participation",
        data_fields=["close", "volume", "adv20"],
        operators=["rank", "ts_delta", "ts_mean"],
        dataset_id="fundamental6",
        local_quality={"passed": True, "score": 85},
        official_metrics={
            "pass_fail": "PASS",
            "sharpe": 1.6,
            "fitness": 1.012,
            "turnover": 0.2,
            "returns": 0.08,
            "drawdown": 0.05,
            "correlation": 0.2,
            "prod_correlation": 0.2,
            "weight_concentration": 0.04,
            "sub_universe_sharpe": 1.3,
            "subUniverseSize": 1000,
            "alphaSize": 1000,
            "margin": 5.0,
        },
    )
    probe.official_alpha_id = "canonical_compliance_probe_official"

    scoring_system = OfficialScoringSystem(run_config.ops)
    result = scoring_system.evaluate(probe)

    return {
        "name": "scoring_simulation_zero_deviation",
        "passed": result.api_output_deviation == 0.0,
        "details": {
            "api_status": result.simulated_api_output.get("status"),
            "zero_deviation": result.api_output_deviation == 0.0,
            "deviation_value": result.api_output_deviation,
            "deviation_details": result.deviation_details,
            "total_score": result.total_score,
            "decision_band": result.decision_band,
            "passed_gate": result.passed_gate,
            "config_hash": result.config_hash,
            "threshold_trace": result.threshold_trace,
            "settings_trace": result.settings_trace,
        },
        "deviations": result.deviation_details,
    }


# ═══════════════════════════════════════════════════════════════════════
# Check 5: Field/Operator No Custom Extension
# ═══════════════════════════════════════════════════════════════════════

def _check_no_custom_extension(run_config: Any) -> dict[str, Any]:
    """Verify field/operator definitions are from official BRAIN context only."""
    from brain_alpha_ops.compliance.redline_helpers import (
        _verify_generator_templates_against_official_context,
    )
    from brain_alpha_ops.data.loader import OfficialDataLoader

    data_dir = Path(run_config.ops.storage_dir)
    loader = OfficialDataLoader()
    loader.load_all(data_dir)

    fields = loader.get_fields()
    operators = loader.get_operators()

    field_count = len(fields)
    operator_count = len(operators)

    # Check that all field IDs are non-empty strings
    valid_fields = [
        f for f in fields if isinstance(f.id, str) and f.id.strip()
    ]
    invalid_field_count = field_count - len(valid_fields)

    # Check that all operators have names
    valid_operators = [
        o for o in operators if isinstance(o.name, str) and o.name.strip()
    ]
    invalid_operator_count = operator_count - len(valid_operators)

    deviations = []
    if field_count == 0:
        deviations.append("No official fields loaded — run fetch_official_context.py")
    if operator_count == 0:
        deviations.append("No official operators loaded — run fetch_official_context.py")
    if invalid_field_count:
        deviations.append(f"{invalid_field_count} fields have invalid/missing IDs")
    if invalid_operator_count:
        deviations.append(f"{invalid_operator_count} operators have invalid/missing names")

    template_result = _verify_generator_templates_against_official_context(data_dir)
    if not template_result.get("ok"):
        deviations.append(
            "CandidateGenerator fallback templates reference fields/operators "
            "outside the official context"
        )

    return {
        "name": "no_custom_extension",
        "passed": (
            field_count > 0
            and operator_count > 0
            and invalid_field_count == 0
            and invalid_operator_count == 0
            and bool(template_result.get("ok"))
        ),
        "details": {
            "field_count": field_count,
            "operator_count": operator_count,
            "valid_fields": len(valid_fields),
            "valid_operators": len(valid_operators),
            "invalid_field_count": invalid_field_count,
            "invalid_operator_count": invalid_operator_count,
            "generator_template_check": template_result,
        },
        "deviations": deviations,
    }


# ═══════════════════════════════════════════════════════════════════════
# Check 6: Dataset ID Availability
# ═══════════════════════════════════════════════════════════════════════

def _check_dataset_ids(data_dir: Path) -> dict[str, Any]:
    """Verify all official dataset IDs are available and valid."""
    datasets_path = data_dir / "official_datasets.json"
    deviations = []

    if not datasets_path.exists():
        return {
            "name": "dataset_id_availability",
            "passed": False,
            "details": {"path": str(datasets_path)},
            "deviations": ["official_datasets.json not found"],
            "dataset_ids": [],
        }

    try:
        datasets = json.loads(datasets_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {
            "name": "dataset_id_availability",
            "passed": False,
            "details": {"path": str(datasets_path), "error": str(exc)},
            "deviations": [f"Failed to parse official_datasets.json: {exc}"],
            "dataset_ids": [],
        }

    if not isinstance(datasets, list):
        deviations.append("official_datasets.json is not a list")
        return {
            "name": "dataset_id_availability",
            "passed": False,
            "details": {"path": str(datasets_path)},
            "deviations": deviations,
            "dataset_ids": [],
        }

    ids = [d.get("id", "") for d in datasets if isinstance(d, dict)]
    valid_ids = [i for i in ids if isinstance(i, str) and i.strip()]
    missing_ids = len(ids) - len(valid_ids)
    duplicate_ids = len(valid_ids) - len(set(valid_ids))

    if len(valid_ids) < 10:
        deviations.append(f"Only {len(valid_ids)} valid dataset IDs (expected >= 10)")
    if missing_ids:
        deviations.append(f"{missing_ids} datasets missing valid IDs")
    if duplicate_ids:
        deviations.append(f"{duplicate_ids} duplicate dataset IDs detected")

    context_validation = _context_validation_for_data_dir(data_dir)
    blocking_findings = [
        item
        for item in context_validation.get("findings", [])
        if item.get("severity") == "BLOCKING"
    ]
    for finding in blocking_findings:
        deviations.append(
            f"{finding.get('code', 'official_context')}: "
            f"{finding.get('message', 'official context validation failed')}"
        )

    return {
        "name": "dataset_id_availability",
        "passed": (
            len(valid_ids) >= 10
            and missing_ids == 0
            and duplicate_ids == 0
            and not blocking_findings
        ),
        "details": {
            "total": len(datasets),
            "valid_ids": len(valid_ids),
            "missing_ids": missing_ids,
            "duplicate_ids": duplicate_ids,
            "official_context_blocking_count": len(blocking_findings),
            "official_context_lineage": context_validation.get("lineage", {}),
        },
        "deviations": deviations,
        "dataset_ids": valid_ids,
    }
