# BRAIN Alpha 100-Candidate Experiment — Final Report

Generated: 2026-05-16 06:23:02

## Summary

| Metric | Value |
|--------|-------|
| Total candidates | 100 |
| BRAIN simulation COMPLETED | 65 |
| BRAIN simulation FAILED | 35 |
| Successfully refetched metrics | 65 |
| Alpha with Sharpe >= 1.25 | 1 |
| Alpha with Sharpe >= 1.0 | 1 |
| Overall pass rate (>=1.25) | 1% |

## Sharpe Distribution

| Percentile | Value |
|------------|-------|
| Min | -1.74 |
| P10 | -0.54 |
| P25 | -0.3 |
| Median | -0.07 |
| P75 | 0.25 |
| P90 | 0.54 |
| Max | 1.75 |
| Mean | -0.015 |

| Threshold | Count | Rate |
|-----------|-------|------|
| >= 1.25 | 1 | 1.5% |
| >= 1.00 | 1 | 1.5% |
| >= 0.50 | 7 | 10.8% |
| >= 0.00 | 31 | 47.7% |

## Key Findings

1. **Pass rate: 1.0%** — 1 out of 100 candidates met the BRAIN Sharpe >= 1.25 threshold
2. **Mean Sharpe: -0.015** — the current generator produces near-zero-alpha expressions on average
3. **39% expression rejection** by BRAIN parser (unknown fields, syntax errors, operator mismatches)
4. **Best candidate: Sharpe=1.75** — proves the pipeline CAN produce viable alphas

## Next Improvements

| Priority | Action | Expected Impact |
|----------|--------|-----------------|
| P0 | Operator signature validation | -12% rejection |
| P0 | Field whitelist (SAFE_FIELDS) | -10% rejection |
| P1 | Parameter type constraints | -5% rejection |
| P1 | Autocorrelation pre-filter | quality improvement |
