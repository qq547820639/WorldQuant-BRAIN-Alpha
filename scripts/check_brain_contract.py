"""Validate the local system against the BRAIN production contract.

The check is intentionally offline and deterministic. It consumes the same
structured diagnosis used by the one-page report, then turns drift in red
lines, thresholds, official context lineage, scoring simulation, frontend sync,
and checkpoint history into machine-readable findings.

Extended checks:
  - Blocking/Warning/Info severity levels with per-level enforcement
  - Threshold zero-deviation check (CANONICAL_THRESHOLDS ↔ QualityThresholds)
  - Threshold version diff check
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_CONFIG = ROOT / "config" / "run_config.json"
STRICT_SEVERITIES = {"P0", "P1"}

# Maps CANONICAL_THRESHOLDS keys to QualityThresholds field names.
_CANONICAL_THRESHOLD_FIELDS = {
    "min_sharpe": "min_sharpe",
    "min_sharpe_delay0": "min_sharpe_delay0",
    "min_fitness": "min_fitness",
    "min_fitness_delay0": "min_fitness_delay0",
    "min_turnover": "min_turnover",
    "platform_max_turnover": "platform_max_turnover",
    "max_self_correlation": "max_self_correlation",
    "max_prod_correlation": "max_prod_correlation",
    "max_weight_concentration": "max_weight_concentration",
    "sub_universe_sharpe_min_ratio": "sub_universe_sharpe_min_ratio",
}

_EXPECTED_HARD_GATE_NAMES = frozenset({
    "sharpe", "fitness", "turnover_min", "turnover_platform",
    "self_correlation", "prod_correlation", "weight_concentration",
    "sub_universe_sharpe",
})

# Data-driven contract checks: (contract_key, code, severity, message, evidence_key)
_CONTRACT_CHECKS = (
    ("redlines_pass", "redlines", "P0", "Six technical red lines must pass.", None),
    ("thresholds_zero_deviation", "threshold_zero_deviation", "P0",
     "Configured thresholds must match canonical BRAIN thresholds exactly.", "thresholds"),
    ("official_context_loaded", "official_context_loaded", "P0",
     "Official fields/operators/datasets must all be loadable.", "official_context"),
    ("official_context_blocking_ok", "official_context_lineage", "P0",
     "Official context structure, hashes, and Dataset lineage must be blocking-clean.", "lineage"),
    ("dataset_field_counts_match", "dataset_field_count_lineage", "P0",
     "Sum of Dataset field_count must match the official field count.", "lineage"),
    ("scoring_zero_deviation", "scoring_zero_deviation", "P0",
     "API-shaped scoring simulation must have zero pass/fail deviation.", "deviation_details"),
    ("frontend_inline_synced", "frontend_inline_sync", "P1",
     "Generated web console must be synchronized with source modules.", "frontend_inline"),
    ("history_replay_ready", "history_replay_ready", "P1",
     "Checkpoint and run-history analytics must be available.", "history_replay"),
)


def check_brain_contract(
    *,
    config_path: str | Path = DEFAULT_CONFIG,
    strict_freshness: bool = False,
    include_threshold_zero_deviation: bool = True,
    threshold_snapshot_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return a structured BRAIN contract comparison result.

    Args:
        config_path: path to run_config.json
        strict_freshness: fail on stale or unrefreshed official context
        include_threshold_zero_deviation: verify thresholds match canonical values
        threshold_snapshot_path: optional path to previous threshold snapshot for diff
    """
    from brain_alpha_ops.brain_api.canonical import CANONICAL_SETTINGS
    from brain_alpha_ops.production_diagnostics import build_diagnostic_snapshot

    snapshot = build_diagnostic_snapshot(config_path)
    findings: list[dict[str, Any]] = []
    contract = snapshot.get("contract_comparison") or {}
    scoring = snapshot.get("scoring_probe") or {}
    validation = snapshot.get("official_context_validation") or {}
    refresh = snapshot.get("official_refresh") or {}

    evidence_map = {
        "thresholds": contract.get("thresholds"),
        "official_context": snapshot.get("official_context"),
        "lineage": validation.get("lineage"),
        "deviation_details": scoring.get("deviation_details"),
        "frontend_inline": snapshot.get("frontend_inline"),
        "history_replay": snapshot.get("history_replay"),
    }
    for contract_key, code, severity, message, evidence_key in _CONTRACT_CHECKS:
        _require(
            contract.get(contract_key), findings, code, severity, message,
            evidence=evidence_map.get(evidence_key) if evidence_key else None,
        )

    _check_settings_trace(scoring.get("settings_trace") or {}, CANONICAL_SETTINGS, findings)
    _check_threshold_trace(scoring.get("threshold_trace") or {}, findings)
    _check_official_refresh(refresh, validation, findings, strict_freshness=strict_freshness)

    threshold_zero_deviation = None
    if include_threshold_zero_deviation:
        threshold_zero_deviation = _check_threshold_zero_deviation(findings)

    threshold_diff = None
    if threshold_snapshot_path:
        threshold_diff = _check_threshold_version_diff(
            threshold_snapshot_path, scoring.get("threshold_trace") or {}, findings
        )

    blocking = [f for f in findings if f["severity"] in STRICT_SEVERITIES]
    if not strict_freshness:
        blocking = [f for f in blocking if f["severity"] == "P0"]
    redline = snapshot.get("redline") or {}
    return {
        "ok": not blocking,
        "schema_version": "brain_contract_check.v1",
        "config": str(config_path),
        "enforcement_mode": "strict_freshness" if strict_freshness else "blocking_only",
        "redline": {k: redline.get(k) for k in ("overall", "passed", "total_checks")},
        "official_context": snapshot.get("official_context"),
        "official_refresh": {
            k: refresh.get(k) for k in (
                "status", "stale_count", "last_attempt_status",
                "last_attempt_ok", "last_attempt_error",
            )
        },
        "scoring": {
            k: scoring.get(k) for k in (
                "api_status", "api_output_deviation", "hard_gate_count", "config_hash",
            )
        },
        "history_replay": snapshot.get("history_replay"),
        "findings": findings,
        "blocking_count": len(blocking),
        "threshold_zero_deviation": threshold_zero_deviation,
        "threshold_diff": threshold_diff,
    }


def _require(
    passed: Any,
    findings: list[dict[str, Any]],
    code: str,
    severity: str,
    message: str,
    *,
    evidence: Any = None,
) -> None:
    if passed:
        return
    findings.append({"code": code, "severity": severity, "message": message, "evidence": evidence})


def _check_settings_trace(
    settings_trace: dict[str, Any],
    canonical_settings: dict[str, set[Any]],
    findings: list[dict[str, Any]],
) -> None:
    for key, allowed in canonical_settings.items():
        if key not in settings_trace:
            findings.append({
                "code": f"settings_trace_missing:{key}",
                "severity": "P1",
                "message": f"Scoring trace is missing BRAIN setting {key}.",
            })
            continue
        value = settings_trace.get(key)
        if value not in allowed:
            findings.append({
                "code": f"settings_trace_drift:{key}",
                "severity": "P0",
                "message": f"Scoring trace setting {key} is outside the canonical BRAIN set.",
                "evidence": {"value": value, "allowed": sorted(allowed, key=str)},
            })


def _check_threshold_trace(threshold_trace: dict[str, Any], findings: list[dict[str, Any]]) -> None:
    for key, row in threshold_trace.items():
        source = str((row or {}).get("source") or "")
        if source not in {"BRAIN_Official", "derived_from_SELF_CORRELATION"}:
            findings.append({
                "code": f"threshold_source_drift:{key}",
                "severity": "P0",
                "message": f"Threshold {key} is not traced to the BRAIN contract.",
                "evidence": row,
            })


def _check_official_refresh(
    refresh: dict[str, Any],
    validation: dict[str, Any],
    findings: list[dict[str, Any]],
    *,
    strict_freshness: bool,
) -> None:
    if validation.get("p1_count", 0):
        findings.append({
            "code": "official_context_refresh_p1", "severity": "P1",
            "message": "Official context metadata is stale or incomplete.",
            "evidence": {"p1_count": validation.get("p1_count"), "stale_count": refresh.get("stale_count"), "last_attempt_status": refresh.get("last_attempt_status")},
        })
    if refresh.get("last_attempt_ok") is False:
        findings.append({
            "code": "official_refresh_failed", "severity": "P1",
            "message": "Live official context refresh did not complete.",
            "evidence": {"status": refresh.get("last_attempt_status"), "error": refresh.get("last_attempt_error")},
        })
    if strict_freshness and refresh.get("last_attempt_ok") is not True:
        findings.append({
            "code": "strict_refresh_not_verified", "severity": "P1",
            "message": "Strict production mode requires a successful credential-backed official context refresh.",
            "evidence": {"status": refresh.get("last_attempt_status"), "error": refresh.get("last_attempt_error")},
        })


def _check_threshold_zero_deviation(findings: list[dict[str, Any]]) -> dict[str, Any]:
    """Verify QualityThresholds defaults match CANONICAL_THRESHOLDS exactly."""
    from brain_alpha_ops.brain_api.canonical import CANONICAL_THRESHOLDS
    from brain_alpha_ops.config import QualityThresholds
    from brain_alpha_ops.scoring.gates import OFFICIAL_HARD_GATE_NAMES

    defaults = QualityThresholds()
    deviations = []
    for canonical_key, qt_field in _CANONICAL_THRESHOLD_FIELDS.items():
        canonical_value = CANONICAL_THRESHOLDS[canonical_key]
        actual_value = getattr(defaults, qt_field)
        if actual_value != canonical_value:
            deviations.append({
                "key": canonical_key,
                "canonical": canonical_value,
                "actual": actual_value,
            })

    expected_gates = set(_EXPECTED_HARD_GATE_NAMES)
    missing_gates = expected_gates - OFFICIAL_HARD_GATE_NAMES
    extra_gates = OFFICIAL_HARD_GATE_NAMES - expected_gates

    if deviations:
        findings.append({"code": "threshold_value_deviation", "severity": "P0",
            "message": f"{len(deviations)} threshold(s) deviate from CANONICAL_THRESHOLDS.",
            "evidence": {"deviations": deviations}})
    if missing_gates or extra_gates:
        findings.append({"code": "hard_gate_name_mismatch", "severity": "P0",
            "message": "OFFICIAL_HARD_GATE_NAMES does not match the expected set.",
            "evidence": {"missing": sorted(missing_gates), "extra": sorted(extra_gates)}})

    return {
        "ok": not deviations and not missing_gates and not extra_gates,
        "deviations": deviations,
        "missing_gates": sorted(missing_gates),
        "extra_gates": sorted(extra_gates),
        "verified_thresholds": len(_CANONICAL_THRESHOLD_FIELDS),
    }


def _check_threshold_version_diff(
    snapshot_path: str | Path,
    current_trace: dict[str, Any],
    findings: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare current thresholds against a previous snapshot."""
    try:
        from brain_alpha_ops.registry_validation import compare_threshold_snapshots, snapshot_threshold_version

        snapshot_file = Path(snapshot_path)
        if not snapshot_file.is_file():
            findings.append({
                "code": "threshold_snapshot_missing",
                "severity": "WARNING",
                "message": f"Threshold snapshot file not found: {snapshot_path}",
            })
            return {"ok": False, "error": "file not found"}

        previous = json.loads(snapshot_file.read_text(encoding="utf-8"))
        current_thresholds = {
            key: entry.get("value") if isinstance(entry, dict) else entry
            for key, entry in current_trace.items()
        }
        current_snapshot = snapshot_threshold_version(current_thresholds)
        diff = compare_threshold_snapshots(previous, current_snapshot)

        if not diff["identical"]:
            changed_keys = [c["key"] for c in diff.get("changed", [])]
            findings.append({
                "code": "threshold_version_drift",
                "severity": "P1",
                "message": f"Threshold values changed since snapshot: {changed_keys[:10]}",
                "evidence": {
                    "changed": diff.get("changed", []),
                    "added": diff.get("added", []),
                    "removed": diff.get("removed", []),
                    "previous_hash": diff.get("snapshot_a_hash", ""),
                    "current_hash": diff.get("snapshot_b_hash", ""),
                },
            })
        return diff
    except Exception as exc:
        findings.append({
            "code": "threshold_diff_check_failed",
            "severity": "WARNING",
            "message": f"Threshold version diff check failed: {exc}",
        })
        return {"ok": False, "error": str(exc)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate local BRAIN production contract evidence.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Run config path.")
    parser.add_argument("--strict-freshness", action="store_true", help="Fail on stale or unrefreshed official context metadata.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--no-threshold-zero-deviation", action="store_true",
                        help="Skip the threshold zero-deviation check.")
    parser.add_argument("--threshold-snapshot", default=None,
                        help="Path to previous threshold snapshot for diff check.")
    args = parser.parse_args(argv)

    result = check_brain_contract(
        config_path=args.config,
        strict_freshness=args.strict_freshness,
        include_threshold_zero_deviation=not args.no_threshold_zero_deviation,
        threshold_snapshot_path=args.threshold_snapshot,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        status = "passed" if result["ok"] else "failed"
        print(f"BRAIN contract check {status} ({result['enforcement_mode']}).")
        for finding in result["findings"]:
            print(f"[{finding['severity']}] {finding['code']}: {finding['message']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
