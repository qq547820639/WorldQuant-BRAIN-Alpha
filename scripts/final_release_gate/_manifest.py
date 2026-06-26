"""Redline summary and release-manifest hash computation.

Split from the former ``scripts/final_release_gate.py`` monolith
(deep-optimization-phase12, Task A4). Computes the redline boolean summary
from findings and the SHA-256 manifest hash over release-critical files.
The manifest now tracks the split subpackage files instead of the former
single ``scripts/final_release_gate.py`` module.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ._models import Finding, _add_finding


def _redline_summary(findings: list[Finding]) -> dict[str, bool]:
    codes = {finding.code for finding in findings}
    return {
        "no_custom_field_operator_extension": "CUSTOM_FIELD_OPERATOR_RISK" not in codes,
        "zero_threshold_drift": not any(code.startswith("THRESHOLD_DRIFT_") for code in codes),
        "dataset_id_fully_available": not any(
            code in {"DATASET_ID_EMPTY", "DATASET_STRATEGY_NOT_FIXED", "DATASET_ID_NOT_IN_OFFICIAL_CONTEXT"}
            or code.startswith("OFFICIAL_CONTEXT_DATASET_")
            for code in codes
        ),
        "full_parameter_traceability": not any(
            code in {"RUN_FOREVER_ENABLED", "MAX_CYCLES_NOT_BOUNDED"} for code in codes
        ),
        "full_factor_coverage": not any(
            code.startswith("OFFICIAL_CONTEXT_") or code in {"CLOUD_SYNC_CACHE_MISSING", "STALE_CONTEXT_ALLOWED"}
            for code in codes
        ),
        "code_strong_alignment": not any(
            code.startswith("OFFICIAL_API_DRIFT_")
            or code in {
                "CUSTOM_FIELD_OPERATOR_RISK",
                "CONFIG_NOT_LOADABLE",
                "ENVIRONMENT_NOT_PRODUCTION",
                "MANIFEST_FILE_MISSING",
            }
            for code in codes
        ),
        "official_api_alignment": not any(code.startswith("OFFICIAL_API_DRIFT_") for code in codes),
        "capability_registry_aligned": not any(code.startswith("CAPABILITY_REGISTRY_") for code in codes),
        "implementation_tracker_complete": not any(code.startswith("IMPLEMENTATION_TRACKER_") for code in codes),
    }


def _build_manifest_hash(
    repo_root: Path, config_path: Path, findings: list[Finding] | None = None
) -> str:
    tracked = [config_path, *(repo_root / path for path in (
        "pyproject.toml",
        "brain_alpha_ops/runner.py",
        "brain_alpha_ops/brain_api/official.py",
        "brain_alpha_ops/research/pipeline.py",
        "brain_alpha_ops/scoring/release_score_gate/__init__.py",
        "brain_alpha_ops/scoring/release_score_gate/_models.py",
        "brain_alpha_ops/scoring/release_score_gate/_checks.py",
        "brain_alpha_ops/scoring/release_score_gate/_decision.py",
        "brain_alpha_ops/scoring/release_score_gate/_helpers.py",
        "brain_alpha_ops/web/__init__.py",
        "brain_alpha_ops/web/config/web_capability_registry.py",
        "scripts/check_capability_registry.py",
        "scripts/final_release_gate/__init__.py",
        "scripts/final_release_gate/_models.py",
        "scripts/final_release_gate/_config.py",
        "scripts/final_release_gate/_checks.py",
        "scripts/final_release_gate/_context_checks.py",
        "scripts/final_release_gate/_tracker.py",
        "scripts/final_release_gate/_manifest.py",
        "scripts/final_release_gate/_runner.py",
    ))]
    digest = hashlib.sha256()
    for path in tracked:
        if not path.exists():
            if findings is not None:
                _add_finding(
                    findings,
                    "P1",
                    "MANIFEST_FILE_MISSING",
                    f"Release manifest file is missing: {path}",
                    str(path),
                )
            continue
        try:
            path_label = path.relative_to(repo_root).as_posix()
        except ValueError:
            path_label = path.as_posix()
        digest.update(path_label.encode("utf-8", errors="replace"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()
