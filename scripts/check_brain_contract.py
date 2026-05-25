"""Validate the local system against the BRAIN production contract.

The check is intentionally offline and deterministic. It consumes the same
structured diagnosis used by the one-page report, then turns drift in red
lines, thresholds, official context lineage, scoring simulation, frontend sync,
and checkpoint history into machine-readable findings.
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


def check_brain_contract(
    *,
    config_path: str | Path = DEFAULT_CONFIG,
    strict_freshness: bool = False,
) -> dict[str, Any]:
    """Return a structured BRAIN contract comparison result."""
    from brain_alpha_ops.brain_api.canonical import CANONICAL_SETTINGS
    from brain_alpha_ops.production_diagnostics import build_diagnostic_snapshot

    snapshot = build_diagnostic_snapshot(config_path)
    findings: list[dict[str, Any]] = []
    contract = snapshot.get("contract_comparison") or {}
    scoring = snapshot.get("scoring_probe") or {}
    validation = snapshot.get("official_context_validation") or {}
    refresh = snapshot.get("official_refresh") or {}

    _require(contract.get("redlines_pass"), findings, "redlines", "P0", "Six technical red lines must pass.")
    _require(
        contract.get("thresholds_zero_deviation"),
        findings,
        "threshold_zero_deviation",
        "P0",
        "Configured thresholds must match canonical BRAIN thresholds exactly.",
        evidence=contract.get("thresholds"),
    )
    _require(
        contract.get("official_context_loaded"),
        findings,
        "official_context_loaded",
        "P0",
        "Official fields/operators/datasets must all be loadable.",
        evidence=snapshot.get("official_context"),
    )
    _require(
        contract.get("official_context_blocking_ok"),
        findings,
        "official_context_lineage",
        "P0",
        "Official context structure, hashes, and Dataset lineage must be blocking-clean.",
        evidence=validation.get("lineage"),
    )
    _require(
        contract.get("dataset_field_counts_match"),
        findings,
        "dataset_field_count_lineage",
        "P0",
        "Sum of Dataset field_count must match the official field count.",
        evidence=validation.get("lineage"),
    )
    _require(
        contract.get("scoring_zero_deviation"),
        findings,
        "scoring_zero_deviation",
        "P0",
        "API-shaped scoring simulation must have zero pass/fail deviation.",
        evidence=scoring.get("deviation_details"),
    )
    _require(
        contract.get("frontend_inline_synced"),
        findings,
        "frontend_inline_sync",
        "P1",
        "Generated web console must be synchronized with source modules.",
        evidence=snapshot.get("frontend_inline"),
    )
    _require(
        contract.get("history_replay_ready"),
        findings,
        "history_replay_ready",
        "P1",
        "Checkpoint and run-history analytics must be available.",
        evidence=snapshot.get("history_replay"),
    )

    _check_settings_trace(scoring.get("settings_trace") or {}, CANONICAL_SETTINGS, findings)
    _check_threshold_trace(scoring.get("threshold_trace") or {}, findings)
    _check_official_refresh(refresh, validation, findings, strict_freshness=strict_freshness)

    blocking = [finding for finding in findings if finding["severity"] in STRICT_SEVERITIES]
    if not strict_freshness:
        blocking = [finding for finding in blocking if finding["severity"] == "P0"]
    return {
        "ok": not blocking,
        "schema_version": "brain_contract_check.v1",
        "config": str(config_path),
        "enforcement_mode": "strict_freshness" if strict_freshness else "blocking_only",
        "redline": {
            "overall": (snapshot.get("redline") or {}).get("overall"),
            "passed": (snapshot.get("redline") or {}).get("passed"),
            "total_checks": (snapshot.get("redline") or {}).get("total_checks"),
        },
        "official_context": snapshot.get("official_context"),
        "official_refresh": {
            "status": refresh.get("status"),
            "stale_count": refresh.get("stale_count"),
            "last_attempt_status": refresh.get("last_attempt_status"),
            "last_attempt_ok": refresh.get("last_attempt_ok"),
            "last_attempt_error": refresh.get("last_attempt_error"),
        },
        "scoring": {
            "api_status": scoring.get("api_status"),
            "api_output_deviation": scoring.get("api_output_deviation"),
            "hard_gate_count": scoring.get("hard_gate_count"),
            "config_hash": scoring.get("config_hash"),
        },
        "history_replay": snapshot.get("history_replay"),
        "findings": findings,
        "blocking_count": len(blocking),
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
            findings.append(
                {
                    "code": f"settings_trace_missing:{key}",
                    "severity": "P1",
                    "message": f"Scoring trace is missing BRAIN setting {key}.",
                }
            )
            continue
        value = settings_trace.get(key)
        if value not in allowed:
            findings.append(
                {
                    "code": f"settings_trace_drift:{key}",
                    "severity": "P0",
                    "message": f"Scoring trace setting {key} is outside the canonical BRAIN set.",
                    "evidence": {"value": value, "allowed": sorted(allowed, key=str)},
                }
            )


def _check_threshold_trace(threshold_trace: dict[str, Any], findings: list[dict[str, Any]]) -> None:
    for key, row in threshold_trace.items():
        source = str((row or {}).get("source") or "")
        if source not in {"BRAIN_Official", "derived_from_SELF_CORRELATION"}:
            findings.append(
                {
                    "code": f"threshold_source_drift:{key}",
                    "severity": "P0",
                    "message": f"Threshold {key} is not traced to the BRAIN contract.",
                    "evidence": row,
                }
            )


def _check_official_refresh(
    refresh: dict[str, Any],
    validation: dict[str, Any],
    findings: list[dict[str, Any]],
    *,
    strict_freshness: bool,
) -> None:
    if validation.get("p1_count", 0):
        findings.append(
            {
                "code": "official_context_refresh_p1",
                "severity": "P1",
                "message": "Official context metadata is stale or incomplete.",
                "evidence": {
                    "p1_count": validation.get("p1_count"),
                    "stale_count": refresh.get("stale_count"),
                    "last_attempt_status": refresh.get("last_attempt_status"),
                },
            }
        )
    if refresh.get("last_attempt_ok") is False:
        findings.append(
            {
                "code": "official_refresh_failed",
                "severity": "P1",
                "message": "Live official context refresh did not complete.",
                "evidence": {
                    "status": refresh.get("last_attempt_status"),
                    "error": refresh.get("last_attempt_error"),
                },
            }
        )
    if strict_freshness and refresh.get("last_attempt_ok") is not True:
        findings.append(
            {
                "code": "strict_refresh_not_verified",
                "severity": "P1",
                "message": "Strict production mode requires a successful credential-backed official context refresh.",
                "evidence": {
                    "status": refresh.get("last_attempt_status"),
                    "error": refresh.get("last_attempt_error"),
                },
            }
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate local BRAIN production contract evidence.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Run config path.")
    parser.add_argument("--strict-freshness", action="store_true", help="Fail on stale or unrefreshed official context metadata.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    result = check_brain_contract(config_path=args.config, strict_freshness=args.strict_freshness)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    elif result["ok"]:
        print(f"BRAIN contract check passed ({result['enforcement_mode']}).")
        for finding in result["findings"]:
            print(f"[{finding['severity']}] {finding['code']}: {finding['message']}")
    else:
        print(f"BRAIN contract check failed ({result['enforcement_mode']}).")
        for finding in result["findings"]:
            print(f"[{finding['severity']}] {finding['code']}: {finding['message']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
