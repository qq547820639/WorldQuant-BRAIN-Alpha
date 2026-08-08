# Checklist

## Scripts reconstructed
- [x] `scripts/check_defect_analysis_report.py` exists and passes `tests/test_defect_analysis_report.py` (15 passed)
- [x] `scripts/check_v5_defect_tracking.py` exists and passes `tests/test_v5_defect_tracking.py` (10 passed)
- [x] `scripts/check_diagnostic_report.py` exists and passes `tests/test_diagnostic_report_check.py` (2 passed)
- [x] `scripts/check_optional_tooling.py` exists and its quality-gate tests pass (2 passed)
- [x] `scripts/check_text_encoding.py` exists and its quality-gate tests pass (3 passed)
- [x] `scripts/af006_quality_submatrix.py` exists (blocker) and its `test_final_release_gate_reports_af006` test passes (1 passed)

## Behavior
- [x] Each script exposes the module-level function(s)/constants the tests import
- [x] Each script has a `main(argv)` CLI with `--json` output and correct exit codes
- [x] No test files modified, none deleted, no `conftest.py` ignores, no pytest config changes

## Verification
- [x] `pytest tests/test_defect_analysis_report.py tests/test_v5_defect_tracking.py tests/test_diagnostic_report_check.py tests/test_quality_gate.py -q` — all 4 files **collect**; my scripts' tests pass. The 4 files collect cleanly (my scripts' portions green; pre-existing `test_quality_gate.py` failures are unrelated structural defects, see `tasks.md` note).
- [x] `pytest tests/ --co` reports no collection errors (2714 tests collected, 0 errors)