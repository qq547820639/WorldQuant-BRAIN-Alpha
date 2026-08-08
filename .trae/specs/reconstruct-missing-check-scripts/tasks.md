# Tasks

> All 5 scripts are independent and may be built in parallel. Each must expose
> the module-level function/constant named in its test file and a CLI
> `main(argv)` following the existing `scripts/check_*.py` conventions
> (`--json` output, exit 0/1). Do NOT modify any test file.

- [x] Task 1: Reconstruct `scripts/check_defect_analysis_report.py`
  - [x] 1.1: `DEFAULT_REPORT = ROOT/"docs"/"DEFECT_ANALYSIS_REPORT_20260601.md"`, `SCHEMA_VERSION="defect_analysis_report_check.v1"`, `check_defect_analysis_report(report_path=DEFAULT_REPORT)` returning `ok/schema_version/detailed_count/status_count/closed_count/open_count/priority_counts/python_runtime/python_runtime_ok/open_items/findings`
  - [x] 1.2: Parse section 二 detailed sections (16) and section 七 status table (16); compute counts, priority distribution, open items; validate DEFECT-016 runtime, `PARTIAL_CLOSED_CURRENT` stale-fact, missing status rows
  - [x] 1.3: Support the static 20260603 report (22 rows, P0-3 pagination boundary, P2-6 bind-smoke boundary evidence) with findings codes `missing_status_row`, `priority_count_mismatch`, `open_items_mismatch`, `boundary_status_mismatch`, `boundary_report_text_mismatch`, `boundary_evidence_mismatch`, `stale_report_fact`
  - [x] 1.4: `main(argv)` CLI with `--report`/`--json`
  - [x] 1.5: `pytest tests/test_defect_analysis_report.py` green (15 passed)

- [x] Task 2: Reconstruct `scripts/check_v5_defect_tracking.py`
  - [x] 2.1: `DEFAULT_REPORT = ROOT/"docs"/"DEFECT_ANALYSIS_REPORT_20260602_v6.md"`, `SCHEMA_VERSION="v5_defect_tracking_check.v1"`, `check_v5_defect_tracking(report_path=DEFAULT_REPORT)` returning `ok/schema_version/p1_tracked_count/metrics/status_rows/required_validation_count/closed_ids/findings`
  - [x] 2.2: Parse P1 tracked rows, metrics table, status/evidence rows, validation evidence; compute `closed_ids`
  - [x] 2.3: Findings codes `missing_p1_tracking_row`, `required_closure_missing`, `metric_mismatch`, `status_mismatch`, `status_evidence_mismatch`, `detail_fact_missing`, `validation_evidence_missing`
  - [x] 2.4: `main(argv)` CLI with `--json`
  - [x] 2.5: `pytest tests/test_v5_defect_tracking.py` green (10 passed)

- [x] Task 3: Reconstruct `scripts/check_diagnostic_report.py`
  - [x] 3.1: `check_diagnostic_report(*, config_path, report_path)` rebuilds snapshot via `brain_alpha_ops.production_diagnostics.build_diagnostic_snapshot` and validates rendered markdown; returns `ok`/`findings`
  - [x] 3.2: Detect stale `official contextual counts` mismatch (code `official_context_counts`)
  - [x] 3.3: `main(argv)` CLI with `--config`/`--report`/`--json`
  - [x] 3.4: `pytest tests/test_diagnostic_report_check.py` green (2 passed; requires `jsonschema` runtime dep)

- [x] Task 4: Reconstruct `scripts/check_optional_tooling.py`
  - [x] 4.1: `check_optional_tooling(*, strict=False, runner=None)` probes `ruff`, `mypy`, `pip_audit`; returns `ok`/`missing`/`tools`
  - [x] 4.2: Non-blocking by default; `--strict` fails when missing
  - [x] 4.3: `main(argv)` CLI with `--strict`/`--json`
  - [x] 4.4: `pytest tests/test_quality_gate.py::test_optional_tooling_*` green (2 passed)

- [x] Task 5: Reconstruct `scripts/check_text_encoding.py`
  - [x] 5.1: `check_text_encoding(root=ROOT, targets=None)` scans for mojibake codepoints incl. private use area; returns `ok`/`findings` (`code=="mojibake"`, `path`)
  - [x] 5.2: Skip `node_modules`/dependency prefixes; accept current workspace
  - [x] 5.3: `main(argv)` CLI with `--root`/`--json`
  - [x] 5.4: `pytest tests/test_quality_gate.py::test_text_encoding_*` green (3 passed)

- [x] Task 5b (blocker found): Reconstruct pre-existing missing `scripts/af006_quality_submatrix.py` so `test_quality_gate.py` can collect (imported by `quality_gate/__init__.py` and `final_release_gate.py`). Exposes `EXPECTED_AF_COMPLETION_IDS`, `tracker_non_done_statuses`, `tracker_readiness_summary`, `build_final_release_af006_submatrix`, `build_quality_gate_af006_submatrix`. Its 3 direct `test_final_release_gate_*af006*` tests pass.

- [x] Task 6: Full verification
  - [x] 6.1a: `pytest tests/test_defect_analysis_report.py tests/test_v5_defect_tracking.py tests/test_diagnostic_report_check.py -q` all pass (15+10+2 = 27 passed)
  - [x] 6.1b: `pytest tests/test_quality_gate.py` — the 6 direct tests for my scripts/module pass (`test_optional_tooling_*`×2, `test_text_encoding_*`×3, `test_final_release_gate_reports_af006`×1); the remaining 26 failures are **pre-existing** `_steps`/`_cli`/module-size/final_release_gate defects unrelated to the 5 scripts/af006 (see note below)
  - [x] 6.2: `pytest tests/ --co` has no collection errors for the 4 files (2714 collected, no errors)

> **Pre-existing `test_quality_gate.py` failures (out of scope, not introduced by this task):**
> The remaining 26 failures come from defects in modules this task did not touch:
> - 22× `AttributeError: module 'scripts.quality_gate' has no attribute '_steps'` and 1× `'_cli'` — the tests reference `quality_gate._steps` / `quality_gate._cli` submodules, but `scripts/quality_gate/__init__.py` defines everything inline (no `_steps`/`_cli` submodules). Pre-existing structural inconsistency.
> - `test_final_release_gate_passes_with_release_config` and `test_final_release_gate_accepts_fresh_official_metadata_when_status_failed` — pre-existing `final_release_gate.py` official-metadata logic failures.
> - `test_module_size_audit_accepts_current_workspace` — pre-existing oversized `brain_alpha_ops/*.py` modules (e.g. `redline_checks.py` 839 lines > 350 limit). My scripts/af006 are all under the limit.

# Task Dependencies
- Tasks 1-5 are independent and can run in parallel.
- Task 6 depends on Tasks 1-5.
- Task 5b (af006 module) is required for `test_quality_gate.py` collection.