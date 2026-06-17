"""Validate production defect tracking evidence for the 2026-06-02 report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_live_submit_readiness import check_live_submit_readiness  # noqa: E402
from brain_alpha_ops.config import ConfigValidationError, load_run_config  # noqa: E402


DEFAULT_REPORT = ROOT / "docs" / "DEFECT_ANALYSIS_REPORT_20260602.md"
DEFAULT_CONFIG = ROOT / "config" / "run_config.json"
DEFAULT_JOBS = ROOT / "data" / "jobs_production.json"
SCHEMA_VERSION = "prod_defect_tracking_check.v1"
REQUIRED_PROD_IDS = tuple(f"PROD-{index:03d}" for index in range(1, 26))
REQUIRED_PROD_007_SNIPPETS = (
    "local_backtest_failed",
    "submission.local_backtest.pass_local=false",
    "official metrics",
    "pass_fail=PASS",
    "decision_band=submit_candidate",
    "不降低",
    "ready_to_submit=false",
    "eligible_count=0",
    "不能声明已有可提交 Alpha",
)
REQUIRED_PROD_012_SNIPPETS = (
    "bad_signal_slots=0",
    "require_official_pass",
    "require_official_metrics",
    "decision_band=submit_candidate",
    "pass_fail=PASS",
    "ready_to_submit=false",
    "eligible_count=0",
    "不能声明已有可提交 Alpha",
)
REQUIRED_PROD_013_SNIPPETS = (
    "std=4",
    "bad_std=[]",
    "不降低",
    "pass_fail=PASS",
    "ready_to_submit=false",
    "eligible_count=0",
    "不能声明已有可提交 Alpha",
)
REQUIRED_PROD_014_SNIPPETS = (
    "official_pass_fail",
    "decision_band_submit_candidate",
    "SUBMITTABLE",
    "BLOCKED",
    "pass_fail=PASS",
    "decision_band=submit_candidate",
    "不降低",
    "ready_to_submit=false",
    "eligible_count=0",
    "不能声明已有可提交 Alpha",
)
REQUIRED_PROD_015_SNIPPETS = (
    "max_generation_attempts=5",
    "GenerationPhaseService",
    "去重后继续补足",
    "requested=30",
    "generated=30",
    "high_similarity_pairs=0",
    "parse_failures=0",
    "submit_candidate",
    "不降低",
    "pass_fail=PASS",
    "ready_to_submit=false",
    "eligible_count=0",
    "不能声明已有可提交 Alpha",
)
REQUIRED_PROD_016_SNIPPETS = (
    "prod_stub_alpha",
    "looks_non_production_alpha_id",
    "non_production_source_reasons",
    "NON_PRODUCTION_ALPHA_ID",
    "non_production_official_alpha_id",
    "stub",
    "本地 stub",
    "fail-closed",
    "不降低",
    "pass_fail=PASS",
    "ready_to_submit=false",
    "eligible_count=0",
    "不能声明已有可提交 Alpha",
)
REQUIRED_PROD_017_SNIPPETS = (
    "_reject_high_cloud_similarity_before_official",
    "HIGH_CLOUD_SIMILARITY_REJECTED",
    "official validation",
    "官方验证",
    "不降低",
    "pass_fail=PASS",
    "ready_to_submit=false",
    "eligible_count=0",
    "不能声明已有可提交 Alpha",
)
REQUIRED_PROD_018_SNIPPETS = (
    "HypothesisDrivenGenerator.generate",
    "duplicate_expression_skipped",
    "requested=30",
    "generated=30",
    "fallback_count=0",
    "submit_candidate",
    "不降低",
    "pass_fail=PASS",
    "ready_to_submit=false",
    "eligible_count=0",
    "不能声明已有可提交 Alpha",
)
REQUIRED_PROD_019_SNIPPETS = (
    "high_turnover",
    "local_backtest_failed",
    "expression_key",
    "expression_fingerprint",
    "expression_similarity",
    "forbidden_patterns",
    "不降低",
    "pass_fail=PASS",
    "ready_to_submit=false",
    "eligible_count=0",
    "不能声明已有可提交 Alpha",
)
REQUIRED_PROD_020_SNIPPETS = (
    "HypothesisDrivenGenerator._expression_forbidden",
    "_generate_bare_fallback",
    "forbidden_patterns",
    "expression_key",
    "expression_fingerprint",
    "expression_similarity",
    "_FORBIDDEN_PATTERN_SIMILARITY_THRESHOLD=0.90",
    "test_generator_knowledge_constraints_block_fallback_fingerprint_and_similarity",
    "不降低",
    "pass_fail=PASS",
    "ready_to_submit=false",
    "eligible_count=0",
    "不能声明已有可提交 Alpha",
)
REQUIRED_PROD_021_SNIPPETS = (
    "candidates_count",
    "candidates_preview",
    "candidates_submission_evidence",
    "candidate_pool_truncated",
    "test_live_submit_readiness_uses_submission_evidence_outside_compacted_preview",
    "test_compact_runtime_result_keeps_submission_evidence_outside_preview",
    "不降低",
    "pass_fail=PASS",
    "ready_to_submit=false",
    "eligible_count=0",
    "不能声明已有可提交 Alpha",
)
REQUIRED_PROD_022_SNIPPETS = (
    "production_gap_summary",
    "official_validation_without_simulation",
    "local_only_candidate_jobs",
    "latest_candidate_local_backtest_failed",
    "latest_candidate_high_cloud_similarity",
    "candidate_family_missing_official_metrics",
    "job_family_blocking_reason_counts",
    "test_live_submit_readiness_reports_production_gap_summary",
    "不降低",
    "pass_fail=PASS",
    "ready_to_submit=false",
    "eligible_count=0",
    "不能声明已有可提交 Alpha",
)
REQUIRED_PROD_023_SNIPPETS = (
    "rank(ts_delta(returns, N))",
    "is_high_turnover_generation_risk",
    "direct_returns_delta_window",
    "test_generation_risk_blocks_direct_returns_delta_without_blocking_other_returns_usage",
    "test_candidate_generator_blocks_direct_returns_delta_risk",
    "test_bare_fallback_deduplicates_single_field_batch",
    "不降低",
    "pass_fail=PASS",
    "ready_to_submit=false",
    "eligible_count=0",
    "不能声明已有可提交 Alpha",
)
REQUIRED_PROD_024_SNIPPETS = (
    "_candidate_submission_audit_evidence",
    "candidates_submission_evidence",
    "auditable candidate",
    "candidate_pool_truncated",
    "test_live_submit_readiness_reports_truncated_candidate_preview_with_incomplete_evidence",
    "test_compact_runtime_result_keeps_submission_evidence_outside_preview",
    "不降低",
    "pass_fail=PASS",
    "ready_to_submit=false",
    "eligible_count=0",
    "不能声明已有可提交 Alpha",
)
REQUIRED_PROD_025_SNIPPETS = (
    "readiness_gate_invariants",
    "missing_official_alpha_id",
    "non_production_official_alpha_id",
    "missing_official_metrics",
    "missing_official_metric_fields",
    "official_pass_fail_not_pass",
    "official_sharpe_below_threshold",
    "official_fitness_below_threshold",
    "official_turnover_above_threshold",
    "official_self_correlation_above_threshold",
    "official_prod_correlation_above_threshold",
    "official_weight_concentration_above_threshold",
    "decision_band_not_submit_candidate",
    "local_backtest_failed",
    "missing_cloud_similarity",
    "high_cloud_similarity",
    "test_live_submit_readiness_requires_official_metrics_above_config_thresholds",
    "test_live_submit_readiness_requires_complete_official_release_metrics",
    "test_prod_defect_tracking_rejects_readiness_gate_invariant_relaxation",
    "不降低",
    "pass_fail=PASS",
    "ready_to_submit=false",
    "eligible_count=0",
    "不能声明已有可提交 Alpha",
)
REQUIRED_VALIDATION_SNIPPETS = (
    "tests/test_hypothesis_driven_generator.py::test_dynamic_theme_generation_seeds_high_structure_templates",
    "tests/test_hypothesis_driven_generator.py tests/test_scoring_gate.py tests/test_official_scoring_system.py",
    "Local non-submit generation probe for `analyst4` / `fundamental6` / `model16` / `news12` / `pv1`",
    "tests/test_generation_phase.py tests/test_budget_and_policy.py",
    "Local non-submit generation refill probe for `analyst4` / `fundamental6` / `model16` / `news12` / `pv1`",
    "scripts/check_live_submit_readiness.py --json",
    "test_generator_retries_after_duplicate_expression_skips",
    "Local non-submit direct generator refill probe",
    "test_live_submit_readiness_blocks_failed_local_backtest",
    "test_pipeline_local_prefilter_rejects_failed_local_backtest",
    "test_forbidden_patterns_block_expression_fingerprint_and_similarity",
    "test_generator_knowledge_constraints_block_fallback_fingerprint_and_similarity",
    "test_live_submit_readiness_uses_submission_evidence_outside_compacted_preview",
    "test_compact_runtime_result_keeps_submission_evidence_outside_preview",
    "test_live_submit_readiness_reports_production_gap_summary",
    "test_generation_risk_blocks_direct_returns_delta_without_blocking_other_returns_usage",
    "test_candidate_generator_blocks_direct_returns_delta_risk",
    "test_live_submit_readiness_reports_truncated_candidate_preview_with_incomplete_evidence",
    "test_prod_defect_tracking_rejects_readiness_gate_invariant_relaxation",
    "test_prod_defect_tracking_rejects_stale_tracker_claimable_evidence",
    "completion_claimable=true",
    "completion_blockers=[]",
)
EXPECTED_THRESHOLDS = {
    "min_sharpe": 1.25,
    "min_fitness": 1.0,
    "platform_max_turnover": 0.70,
    "max_self_correlation": 0.70,
    "require_official_pass": True,
    "require_official_metrics": True,
}
EXPECTED_SUBMISSION_POLICY = {
    "max_expression_similarity": 0.9,
    "require_pre_submit_check_passed": True,
}
EXPECTED_GENERATION_CONFIG = {
    "max_generation_attempts": 5,
}


def check_prod_defect_tracking(
    report_path: str | Path = DEFAULT_REPORT,
    *,
    config_path: str | Path = DEFAULT_CONFIG,
    jobs_path: str | Path = DEFAULT_JOBS,
    readiness_validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = Path(report_path)
    findings: list[dict[str, str]] = []
    try:
        text = report.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {
            "ok": False,
            "schema_version": SCHEMA_VERSION,
            "report": str(report),
            "findings": [_finding("missing_report", str(report), "production defect report does not exist")],
        }

    rows = _tracking_rows(text, findings)
    rows_by_id = {row["id"]: row for row in rows}
    for defect_id in REQUIRED_PROD_IDS:
        if defect_id not in rows_by_id:
            findings.append(_finding("missing_prod_tracking_row", defect_id, "PROD tracking row is missing"))

    prod_007 = rows_by_id.get("PROD-007")
    if prod_007 is not None:
        if prod_007["status"] != "CLOSED_CURRENT":
            findings.append(_finding("prod_007_status", "CLOSED_CURRENT", "PROD-007 must be tracked as closed for current code"))
        prod_007_text = " | ".join(prod_007.values())
        for snippet in REQUIRED_PROD_007_SNIPPETS:
            if snippet not in prod_007_text:
                findings.append(_finding("prod_007_evidence", snippet, "PROD-007 row is missing required evidence"))

    prod_012 = rows_by_id.get("PROD-012")
    if prod_012 is not None:
        if prod_012["status"] != "CLOSED_CURRENT":
            findings.append(_finding("prod_012_status", "CLOSED_CURRENT", "PROD-012 must be tracked as closed for current code"))
        prod_012_text = " | ".join(prod_012.values())
        for snippet in REQUIRED_PROD_012_SNIPPETS:
            if snippet not in prod_012_text:
                findings.append(_finding("prod_012_evidence", snippet, "PROD-012 row is missing required evidence"))

    prod_013 = rows_by_id.get("PROD-013")
    if prod_013 is not None:
        if prod_013["status"] != "CLOSED_CURRENT":
            findings.append(_finding("prod_013_status", "CLOSED_CURRENT", "PROD-013 must be tracked as closed for current code"))
        prod_013_text = " | ".join(prod_013.values())
        for snippet in REQUIRED_PROD_013_SNIPPETS:
            if snippet not in prod_013_text:
                findings.append(_finding("prod_013_evidence", snippet, "PROD-013 row is missing required evidence"))

    prod_014 = rows_by_id.get("PROD-014")
    if prod_014 is not None:
        if prod_014["status"] != "CLOSED_CURRENT":
            findings.append(_finding("prod_014_status", "CLOSED_CURRENT", "PROD-014 must be tracked as closed for current code"))
        prod_014_text = " | ".join(prod_014.values())
        for snippet in REQUIRED_PROD_014_SNIPPETS:
            if snippet not in prod_014_text:
                findings.append(_finding("prod_014_evidence", snippet, "PROD-014 row is missing required evidence"))

    prod_015 = rows_by_id.get("PROD-015")
    if prod_015 is not None:
        if prod_015["status"] != "CLOSED_CURRENT":
            findings.append(_finding("prod_015_status", "CLOSED_CURRENT", "PROD-015 must be tracked as closed for current code"))
        prod_015_text = " | ".join(prod_015.values())
        for snippet in REQUIRED_PROD_015_SNIPPETS:
            if snippet not in prod_015_text:
                findings.append(_finding("prod_015_evidence", snippet, "PROD-015 row is missing required evidence"))

    prod_016 = rows_by_id.get("PROD-016")
    if prod_016 is not None:
        if prod_016["status"] != "CLOSED_CURRENT":
            findings.append(_finding("prod_016_status", "CLOSED_CURRENT", "PROD-016 must be tracked as closed for current code"))
        prod_016_text = " | ".join(prod_016.values())
        for snippet in REQUIRED_PROD_016_SNIPPETS:
            if snippet not in prod_016_text:
                findings.append(_finding("prod_016_evidence", snippet, "PROD-016 row is missing required evidence"))

    prod_017 = rows_by_id.get("PROD-017")
    if prod_017 is not None:
        if prod_017["status"] != "CLOSED_CURRENT":
            findings.append(_finding("prod_017_status", "CLOSED_CURRENT", "PROD-017 must be tracked as closed for current code"))
        prod_017_text = " | ".join(prod_017.values())
        for snippet in REQUIRED_PROD_017_SNIPPETS:
            if snippet not in prod_017_text:
                findings.append(_finding("prod_017_evidence", snippet, "PROD-017 row is missing required evidence"))

    prod_018 = rows_by_id.get("PROD-018")
    if prod_018 is not None:
        if prod_018["status"] != "CLOSED_CURRENT":
            findings.append(_finding("prod_018_status", "CLOSED_CURRENT", "PROD-018 must be tracked as closed for current code"))
        prod_018_text = " | ".join(prod_018.values())
        for snippet in REQUIRED_PROD_018_SNIPPETS:
            if snippet not in prod_018_text:
                findings.append(_finding("prod_018_evidence", snippet, "PROD-018 row is missing required evidence"))

    prod_019 = rows_by_id.get("PROD-019")
    if prod_019 is not None:
        if prod_019["status"] != "CLOSED_CURRENT":
            findings.append(_finding("prod_019_status", "CLOSED_CURRENT", "PROD-019 must be tracked as closed for current code"))
        prod_019_text = " | ".join(prod_019.values())
        for snippet in REQUIRED_PROD_019_SNIPPETS:
            if snippet not in prod_019_text:
                findings.append(_finding("prod_019_evidence", snippet, "PROD-019 row is missing required evidence"))

    prod_020 = rows_by_id.get("PROD-020")
    if prod_020 is not None:
        if prod_020["status"] != "CLOSED_CURRENT":
            findings.append(_finding("prod_020_status", "CLOSED_CURRENT", "PROD-020 must be tracked as closed for current code"))
        prod_020_text = " | ".join(prod_020.values())
        for snippet in REQUIRED_PROD_020_SNIPPETS:
            if snippet not in prod_020_text:
                findings.append(_finding("prod_020_evidence", snippet, "PROD-020 row is missing required evidence"))

    prod_021 = rows_by_id.get("PROD-021")
    if prod_021 is not None:
        if prod_021["status"] != "CLOSED_CURRENT":
            findings.append(_finding("prod_021_status", "CLOSED_CURRENT", "PROD-021 must be tracked as closed for current code"))
        prod_021_text = " | ".join(prod_021.values())
        for snippet in REQUIRED_PROD_021_SNIPPETS:
            if snippet not in prod_021_text:
                findings.append(_finding("prod_021_evidence", snippet, "PROD-021 row is missing required evidence"))

    prod_022 = rows_by_id.get("PROD-022")
    if prod_022 is not None:
        if prod_022["status"] != "CLOSED_CURRENT":
            findings.append(_finding("prod_022_status", "CLOSED_CURRENT", "PROD-022 must be tracked as closed for current code"))
        prod_022_text = " | ".join(prod_022.values())
        for snippet in REQUIRED_PROD_022_SNIPPETS:
            if snippet not in prod_022_text:
                findings.append(_finding("prod_022_evidence", snippet, "PROD-022 row is missing required evidence"))

    prod_023 = rows_by_id.get("PROD-023")
    if prod_023 is not None:
        if prod_023["status"] != "CLOSED_CURRENT":
            findings.append(_finding("prod_023_status", "CLOSED_CURRENT", "PROD-023 must be tracked as closed for current code"))
        prod_023_text = " | ".join(prod_023.values())
        for snippet in REQUIRED_PROD_023_SNIPPETS:
            if snippet not in prod_023_text:
                findings.append(_finding("prod_023_evidence", snippet, "PROD-023 row is missing required evidence"))

    prod_024 = rows_by_id.get("PROD-024")
    if prod_024 is not None:
        if prod_024["status"] != "CLOSED_CURRENT":
            findings.append(_finding("prod_024_status", "CLOSED_CURRENT", "PROD-024 must be tracked as closed for current code"))
        prod_024_text = " | ".join(prod_024.values())
        for snippet in REQUIRED_PROD_024_SNIPPETS:
            if snippet not in prod_024_text:
                findings.append(_finding("prod_024_evidence", snippet, "PROD-024 row is missing required evidence"))

    prod_025 = rows_by_id.get("PROD-025")
    if prod_025 is not None:
        if prod_025["status"] != "CLOSED_CURRENT":
            findings.append(_finding("prod_025_status", "CLOSED_CURRENT", "PROD-025 must be tracked as closed for current code"))
        prod_025_text = " | ".join(prod_025.values())
        for snippet in REQUIRED_PROD_025_SNIPPETS:
            if snippet not in prod_025_text:
                findings.append(_finding("prod_025_evidence", snippet, "PROD-025 row is missing required evidence"))

    for snippet in REQUIRED_VALIDATION_SNIPPETS:
        if snippet not in text:
            findings.append(_finding("validation_evidence_missing", snippet, "report is missing validation evidence"))

    config_summary = _check_config_thresholds(config_path, findings)
    readiness = readiness_validation if readiness_validation is not None else check_live_submit_readiness(jobs_path)
    _check_readiness(readiness, findings)
    _check_readiness_gate_invariants(findings)

    return {
        "ok": not findings,
        "schema_version": SCHEMA_VERSION,
        "report": str(report),
        "tracked_prod_count": sum(1 for defect_id in REQUIRED_PROD_IDS if defect_id in rows_by_id),
        "config": str(config_path),
        "config_summary": config_summary,
        "readiness": {
            "ok": bool(readiness.get("ok")),
            "ready_to_submit": bool(readiness.get("ready_to_submit")),
            "eligible_count": int(readiness.get("eligible_count") or 0),
            "ledger_eligible_count": int(readiness.get("ledger_eligible_count") or 0),
            "job_family_eligible_count": int(readiness.get("job_family_eligible_count") or 0),
        },
        "findings": findings,
    }


def _tracking_rows(text: str, findings: list[dict[str, str]]) -> list[dict[str, str]]:
    section = _section(text, "Codex 实施追踪")
    if not section:
        findings.append(_finding("missing_tracking_section", "Codex 实施追踪", "tracking section is missing"))
        return []
    rows: list[dict[str, str]] = []
    in_table = False
    for line in section.splitlines():
        if not line.startswith("|"):
            if in_table:
                break
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 4 and cells[0] == "缺陷" and cells[1] == "当前状态":
            in_table = True
            continue
        if in_table and cells and set(cells[0]) <= {"-", ":"}:
            continue
        if not in_table:
            continue
        if len(cells) < 4:
            findings.append(_finding("malformed_tracking_row", line, "tracking row has too few cells"))
            continue
        match = re.match(r"^(PROD-\d{3})\b", cells[0])
        if not match:
            continue
        rows.append(
            {
                "id": match.group(1),
                "defect": cells[0],
                "status": cells[1],
                "evidence": cells[2],
                "next_action": "|".join(cells[3:]).strip(),
            }
        )
    return rows


def _section(text: str, heading: str) -> str:
    marker = f"## {heading}"
    start = text.find(marker)
    if start < 0:
        return ""
    next_heading = text.find("\n## ", start + len(marker))
    return text[start:] if next_heading < 0 else text[start:next_heading]


def _check_config_thresholds(config_path: str | Path, findings: list[dict[str, str]]) -> dict[str, Any]:
    path = Path(config_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        findings.append(_finding("missing_config", str(path), "config file does not exist"))
        return {}
    except json.JSONDecodeError as exc:
        findings.append(_finding("invalid_config_json", str(path), f"config JSON is invalid: {exc}"))
        return {}

    ops = payload.get("ops") if isinstance(payload, dict) else {}
    thresholds = ops.get("thresholds") if isinstance(ops, dict) else {}
    submission_policy = ops.get("submission_policy") if isinstance(ops, dict) else {}
    summary: dict[str, Any] = {}
    for key, expected in EXPECTED_THRESHOLDS.items():
        actual = thresholds.get(key)
        summary[key] = actual
        if actual != expected:
            findings.append(_finding("threshold_mismatch", f"{key}={expected!r}", "configured threshold was changed"))
    for key, expected in EXPECTED_SUBMISSION_POLICY.items():
        actual = submission_policy.get(key)
        summary[key] = actual
        if actual != expected:
            findings.append(_finding("submission_policy_mismatch", f"{key}={expected!r}", "submission policy was changed"))
    try:
        runtime_config = load_run_config(path)
    except ConfigValidationError as exc:
        findings.append(_finding("invalid_runtime_config", "load_run_config succeeds", str(exc)))
    else:
        for key, expected in EXPECTED_GENERATION_CONFIG.items():
            actual = getattr(runtime_config.ops.budget, key)
            summary[key] = actual
            if actual != expected:
                findings.append(
                    _finding("generation_config_mismatch", f"{key}={expected!r}", "generation recovery config was changed")
                )
    return summary


def _check_readiness(readiness: dict[str, Any], findings: list[dict[str, str]]) -> None:
    if not readiness.get("ok"):
        findings.append(_finding("readiness_not_ok", "ok=true", "live submit readiness audit failed"))
    expected_zero_fields = ("eligible_count", "ledger_eligible_count", "job_family_eligible_count")
    if readiness.get("ready_to_submit"):
        findings.append(_finding("unexpected_ready_to_submit", "ready_to_submit=false", "report claims no eligible alpha"))
    for field in expected_zero_fields:
        if int(readiness.get(field) or 0) != 0:
            findings.append(_finding("unexpected_eligible_count", f"{field}=0", "report claims no eligible alpha"))
    best_candidate = readiness.get("best_candidate") if isinstance(readiness.get("best_candidate"), dict) else {}
    if best_candidate.get("local_backtest_passed") is False:
        reasons = best_candidate.get("blocking_reasons") if isinstance(best_candidate.get("blocking_reasons"), list) else []
        if "local_backtest_failed" not in reasons:
            findings.append(
                _finding(
                    "missing_local_backtest_blocker",
                    "local_backtest_failed",
                    "failed local backtest must be reflected in live submit readiness blockers",
                )
            )


def _base_gate_candidate() -> dict[str, Any]:
    return {
        "alpha_id": "alpha_gate_invariant",
        "official_alpha_id": "ab12cd34ef56",
        "lifecycle_status": "submission_ready",
        "gate": {"submission_ready": True},
        "scorecard": {"total_score": 91.0, "decision_band": "submit_candidate"},
        "official_metrics": {
            "official_alpha_id": "ab12cd34ef56",
            "pass_fail": "PASS",
            "sharpe": 1.6,
            "fitness": 1.2,
            "turnover": 0.25,
            "correlation": 0.2,
            "weight_concentration": 0.05,
        },
        "cloud_correlation_risk": {"level": "low", "max_similarity": 0.1},
        "submission": {"local_backtest": {"pass_local": True}},
    }


def _readiness_invariant_candidate(reason: str) -> dict[str, Any]:
    candidate = _base_gate_candidate()
    if reason == "not_submission_ready":
        candidate["lifecycle_status"] = "official_validation_passed"
        candidate["gate"] = {"submission_ready": False}
    elif reason == "decision_band_not_submit_candidate":
        candidate["scorecard"] = {"total_score": 66.9, "decision_band": "research_only"}
    elif reason == "local_backtest_failed":
        candidate["submission"] = {"local_backtest": {"pass_local": False}}
    elif reason == "missing_official_alpha_id":
        candidate["official_alpha_id"] = ""
        candidate["official_metrics"] = dict(candidate["official_metrics"], official_alpha_id="")
    elif reason == "non_production_official_alpha_id":
        candidate["official_alpha_id"] = "prod_stub_alpha_0001"
        candidate["official_metrics"] = dict(candidate["official_metrics"], official_alpha_id="prod_stub_alpha_0001")
    elif reason == "missing_official_metrics":
        candidate["official_metrics"] = {}
    elif reason == "official_pass_fail_not_pass":
        candidate["official_metrics"] = dict(candidate["official_metrics"], pass_fail="FAIL")
    elif reason == "missing_official_metric_fields":
        candidate["official_metrics"] = {
            "official_alpha_id": "ab12cd34ef56",
            "pass_fail": "PASS",
        }
    elif reason == "official_sharpe_below_threshold":
        candidate["official_metrics"] = dict(candidate["official_metrics"], sharpe=0.8)
    elif reason == "official_fitness_below_threshold":
        candidate["official_metrics"] = dict(candidate["official_metrics"], fitness=0.7)
    elif reason == "official_turnover_above_threshold":
        candidate["official_metrics"] = dict(candidate["official_metrics"], turnover=0.95)
    elif reason == "official_self_correlation_above_threshold":
        candidate["official_metrics"] = dict(
            candidate["official_metrics"],
            correlation=None,
            self_correlation=0.95,
            prod_correlation=0.2,
        )
    elif reason == "official_prod_correlation_above_threshold":
        candidate["official_metrics"] = dict(
            candidate["official_metrics"],
            correlation=None,
            self_correlation=0.2,
            prod_correlation=0.95,
        )
    elif reason == "official_weight_concentration_above_threshold":
        candidate["official_metrics"] = dict(candidate["official_metrics"], weight_concentration=0.2)
    elif reason == "missing_cloud_similarity":
        candidate["cloud_correlation_risk"] = {}
    elif reason == "high_cloud_similarity":
        candidate["cloud_correlation_risk"] = {"level": "high", "max_similarity": 0.9}
    return candidate


def _write_readiness_case(path: Path, candidate: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "jobs": {
                    "job_0001": {
                        "status": "stopped",
                        "result": {"summary": {"submission_ready": 1}},
                        "progress": {"data": {"candidates": [candidate]}},
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def _check_readiness_gate_invariants(findings: list[dict[str, str]]) -> None:
    invariant_reasons = (
        "not_submission_ready",
        "decision_band_not_submit_candidate",
        "local_backtest_failed",
        "missing_official_alpha_id",
        "non_production_official_alpha_id",
        "missing_official_metrics",
        "missing_official_metric_fields",
        "official_pass_fail_not_pass",
        "official_sharpe_below_threshold",
        "official_fitness_below_threshold",
        "official_turnover_above_threshold",
        "official_self_correlation_above_threshold",
        "official_prod_correlation_above_threshold",
        "official_weight_concentration_above_threshold",
        "missing_cloud_similarity",
        "high_cloud_similarity",
    )
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_root = Path(tmp_dir)
        for reason in invariant_reasons:
            path = tmp_root / f"{reason}.json"
            _write_readiness_case(path, _readiness_invariant_candidate(reason))
            result = check_live_submit_readiness(path)
            if result.get("ready_to_submit") or int(result.get("eligible_count") or 0) != 0:
                findings.append(
                    _finding(
                        "readiness_gate_invariant_ready",
                        f"{reason} blocks eligibility",
                        "readiness gate allowed a candidate that violates official submit standards",
                    )
                )
            best_candidate = result.get("best_candidate") if isinstance(result.get("best_candidate"), dict) else {}
            reasons = best_candidate.get("blocking_reasons") if isinstance(best_candidate.get("blocking_reasons"), list) else []
            if reason not in reasons:
                findings.append(
                    _finding(
                        "readiness_gate_invariant_reason",
                        reason,
                        "readiness gate did not report the expected official submit standard blocker",
                    )
                )


def _finding(code: str, expected: str, message: str) -> dict[str, str]:
    return {"code": code, "expected": expected, "message": message}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check production defect tracking evidence.")
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="Path to production defect report.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Run config path.")
    parser.add_argument("--jobs", default=str(DEFAULT_JOBS), help="Production jobs ledger path.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    result = check_prod_defect_tracking(args.report, config_path=args.config, jobs_path=args.jobs)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status = "ok" if result["ok"] else "failed"
        print(f"production defect tracking {status}: {result['report']}")
        for finding in result["findings"]:
            print(f"[{finding['code']}] {finding['expected']}: {finding['message']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
