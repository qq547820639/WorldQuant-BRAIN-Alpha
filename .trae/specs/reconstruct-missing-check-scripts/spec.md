# Reconstruct 5 Missing Check Scripts Spec

## Why

`scripts/` is missing 5 Python scripts that pytest tests import and the quality
gate invokes: `check_defect_analysis_report.py`, `check_v5_defect_tracking.py`,
`check_diagnostic_report.py`, `check_optional_tooling.py`, and
`check_text_encoding.py`. As a result the affected test files fail to collect
and the quality gate cannot run those steps. Reconstruct the scripts from the
test expectations and report documents so the affected tests collect and pass.

## What Changes

- Recreate `scripts/check_defect_analysis_report.py` — validate
  `docs/DEFECT_ANALYSIS_REPORT_20260601.md` and
  `docs/STATIC_ANALYSIS_DEFECT_REPORT_20260603.md` (counts, status-table
  consistency, priority distribution, open items, boundary evidence, Python
  runtime). CLI `--report`/`--json`.
- Recreate `scripts/check_v5_defect_tracking.py` — validate
  `docs/DEFECT_ANALYSIS_REPORT_20260602_v6.md` (P1 tracked rows, metrics,
  status/evidence rows, required validation evidence, closed ids). CLI `--json`.
- Recreate `scripts/check_diagnostic_report.py` — validate rendered
  `docs/ALPHA_PRODUCTION_DIAGNOSIS_20260620.md` against a fresh
  `build_diagnostic_snapshot` (stale official-context counts etc.). CLI
  `--config`/`--report`/`--json`.
- Recreate `scripts/check_optional_tooling.py` — report availability of
  `ruff`, `mypy`, `pip_audit`; non-blocking by default, `--strict` fails when
  missing. CLI `--strict`/`--json`.
- Recreate `scripts/check_text_encoding.py` — scan files for mojibake (private
  use area / invalid-UTF8 codepoints), skip `node_modules` and dependency
  prefixes. CLI `--root`/`--json`.
- Do NOT modify test files, delete tests, add `conftest.py` ignores, or change
  pytest config to skip them.

## Impact

- Affected specs: none (new spec).
- Affected code: 5 new files under `scripts/`; reused by
  `scripts/quality_gate/_steps.py` (steps `static_defect_analysis_report`,
  `v5_defect_tracking`, `optional_tooling`, `text_encoding_scan`,
  `diagnostic_report_sync`) and by `scripts/check_module_size.py` /
  `STATIC_ANALYSIS_TARGETS`.
- Affected tests: `tests/test_defect_analysis_report.py`,
  `tests/test_v5_defect_tracking.py`, `tests/test_diagnostic_report_check.py`,
  `tests/test_quality_gate.py`.

## ADDED Requirements

### Requirement: check_defect_analysis_report
`check_defect_analysis_report(report_path=DEFAULT_REPORT)` parses the markdown
report and returns a dict with `ok`, `schema_version ==
"defect_analysis_report_check.v1"`, `detailed_count`, `status_count`,
`closed_count`, `open_count`, `priority_counts`, `python_runtime`,
`python_runtime_ok`, `open_items`, `findings`.

#### Scenario: accepts current documents
- **WHEN** called with default report
- **THEN** `ok`, 16/16/16/0, `open_items==[]`, `findings==[]`
- **AND** called with `docs/STATIC_ANALYSIS_DEFECT_REPORT_20260603.md`
  yields 22/22/21/1, priority overview/detail/status all `{P0:4,P1:7,P2:6,P3:5}`,
  single open item `P0-3`/`TRACKED_DEFERRED`, `findings==[]`

#### Scenario: rejects drift
- **WHEN** a status row is removed / a priority total changes / an open item
  status changes / boundary evidence text changes
- **THEN** `ok is False` with codes `missing_status_row`,
  `priority_count_mismatch`, `open_items_mismatch`,
  `boundary_status_mismatch`, `boundary_report_text_mismatch`,
  `boundary_evidence_mismatch`, `stale_report_fact`

### Requirement: check_v5_defect_tracking
`check_v5_defect_tracking(report_path=DEFAULT_REPORT)` parses
`DEFECT_ANALYSIS_REPORT_20260602_v6.md` and returns `ok`,
`schema_version == "v5_defect_tracking_check.v1"`, `p1_tracked_count`,
`metrics`, `status_rows`, `required_validation_count`, `closed_ids`,
`findings`.

#### Scenario: accepts current document
- **WHEN** called with default report
- **THEN** `ok`, `p1_tracked_count==9`,
  `metrics["实际待修复"]["v6"]=="1"`, `status_rows["V5-013"]["v6_status"]=="FIXED"`,
  evidence contains `OfficialBrainAPI` and `React mirror-only`,
  `required_validation_count>=27`, `closed_ids` contains V5-002/006/007,
  `findings==[]`

#### Scenario: rejects drift
- **WHEN** a P1 row is missing / a required closure is not
  `CLOSED_CURRENT` / a metric or status or evidence changes
- **THEN** `ok is False` with codes `missing_p1_tracking_row`,
  `required_closure_missing`, `metric_mismatch`, `status_mismatch`,
  `status_evidence_mismatch`, `detail_fact_missing`, `validation_evidence_missing`

### Requirement: check_diagnostic_report
`check_diagnostic_report(*, config_path, report_path)` rebuilds a fresh snapshot
and validates the rendered markdown, returning `ok` and `findings`.

#### Scenario: accepts current snapshot
- **WHEN** report is freshly rendered from the same config
- **THEN** `ok` and `findings==[]`

#### Scenario: rejects stale counts
- **WHEN** report has stale `official context: fields=0, operators=0,
  datasets=0`
- **THEN** `ok is False` with a finding `official_context_counts`

### Requirement: check_optional_tooling
`check_optional_tooling(*, strict=False, runner=None)` probes `ruff`, `mypy`,
`pip_audit` and returns `ok`, `missing`, `tools`.

#### Scenario: non-blocking by default
- **WHEN** all tools missing and `strict=False`
- **THEN** `ok is True`, `missing == {"ruff","mypy","pip_audit"}`

#### Scenario: strict fails
- **WHEN** `strict=True` and some tools missing
- **THEN** `ok is False`, `missing` lists the missing tools

### Requirement: check_text_encoding
`check_text_encoding(root=ROOT, targets=None)` scans text/source files for
mojibake and returns `ok` and `findings` with `path` and `code=="mojibake"`.

#### Scenario: rejects mojibake
- **WHEN** a scanned file contains private-use-area codepoints
- **THEN** `ok is False` and first finding is `bad.md` / `mojibake`

#### Scenario: skips node_modules and accepts workspace
- **WHEN** targets include `node_modules` or the current workspace is scanned
- **THEN** `ok is True` and `findings==[]`

## MODIFIED Requirements

None.

## REMOVED Requirements

None.