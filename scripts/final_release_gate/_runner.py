"""Run the final release readiness gate and CLI entry point.

Split from the former ``scripts/final_release_gate.py`` monolith
(deep-optimization-phase12, Task A4). Orchestrates the config, source,
context, capability, tracker, and manifest checks into a ``GateReport`` and
exposes the ``main`` CLI used by ``scripts/quality_gate.py``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ._checks import (
    _check_dataset_redline,
    _check_environment,
    _check_exact_thresholds,
    _check_official_api_alignment,
    _check_traceability_redline,
    _scan_custom_field_operator_expansion,
)
from ._config import (
    _check_config_loads,
    _load_config_json,
    _resolve_under_root,
    _validate_official_context,
)
from ._context_checks import (
    _check_capability_registry_redline,
    _check_official_context_redline,
    _check_refresh_status,
)
from ._manifest import _build_manifest_hash, _redline_summary
from ._models import DEFAULT_CONFIG, ROOT, SCHEMA_VERSION, Finding, GateReport
from ._tracker import _check_implementation_tracker_redline


def run_final_release_gate(
    repo_root: str | Path = ROOT,
    *,
    config_path: str | Path = DEFAULT_CONFIG,
    implementation_tracker_path: str | Path | None = None,
) -> GateReport:
    root = Path(repo_root).resolve()
    config_file = _resolve_under_root(root, config_path)
    tracker_file = (
        _resolve_under_root(root, implementation_tracker_path)
        if implementation_tracker_path is not None
        else root / ".codex" / "artifacts" / "implementation-tracker.md"
    )
    findings: list[Finding] = []
    raw_config = _load_config_json(config_file, findings)
    official_context = _validate_official_context(config_file, findings)

    _check_config_loads(config_file, findings)
    _check_environment(raw_config, findings)
    _scan_custom_field_operator_expansion(root, findings)
    _check_exact_thresholds(raw_config, findings)
    _check_dataset_redline(root, raw_config, findings)
    _check_traceability_redline(raw_config, findings)
    _check_official_context_redline(raw_config, findings, official_context=official_context)
    _check_official_api_alignment(raw_config, findings)
    _check_capability_registry_redline(findings)
    _check_refresh_status(root, raw_config, findings, official_context=official_context)
    implementation_tracker = _check_implementation_tracker_redline(tracker_file, findings)

    manifest_hash = _build_manifest_hash(root, config_file, findings)
    redlines = _redline_summary(findings)
    passed = not findings
    return GateReport(
        passed=passed,
        schema_version=SCHEMA_VERSION,
        config=str(config_file),
        manifest_hash=manifest_hash,
        redlines=redlines,
        findings=findings,
        official_context=official_context,
        implementation_tracker=implementation_tracker,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run final release readiness checks.")
    parser.add_argument("repo_root", nargs="?", default=str(ROOT), help="Repository root.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Run config to validate.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    report = run_final_release_gate(args.repo_root, config_path=args.config)
    payload = report.to_dict()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    elif report.passed:
        print(f"Final release gate passed. manifest_hash={report.manifest_hash}")
    else:
        print("Final release gate failed.")
        for finding in report.findings:
            print(f"[{finding.severity}] {finding.code}: {finding.message}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
