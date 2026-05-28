# E2E Artifact Summary

- Schema: `e2e_artifact_summary.v1`
- Generated at: `2026-05-28T08:09:14.112688+00:00`
- Evidence directory: `data/e2e_screenshots`
- Indexed files: `49`
- Overall status: `PASS`

## Evidence Files

| Category | Count |
|---|---:|
| console_log | 1 |
| dom_snapshot | 21 |
| screenshot | 24 |
| summary_json | 3 |

## Job Ledgers

| Ledger | Jobs | Latest status | Latest job | Error |
|---|---:|---|---|---|
| data/jobs_sync.json | 5 | completed | job_0005 | - |
| data/jobs_production.json | 8 | stopped | job_0008 | - |
| data/jobs_check.json | 1 | failed | job_0001 | production mode requires BRAIN_USERNAME/BRAIN_PASSWORD or BRAIN_TOKEN |

## Browser Summaries

| File | Service | Connection | Production run | Submitted |
|---|---|---|---|---:|
| data/e2e_screenshots/20260528-production-e2e-summary.json | http://127.0.0.1:18766/ | True production | stopped job_0008 | 0 |
| data/e2e_screenshots/chrome-api-summary.json | - |   |   | 0 |
| data/e2e_screenshots/chrome-ui-walkthrough-summary.json | - |   |   | 0 |

## Historical Console Notes

- These lines come from captured E2E logs; the current shipped HTML contract is checked separately below.
- `data/e2e_screenshots/console-2026-05-28T03-47-28-618Z.log`: lines=3, notable=1, severities=error=1, verbose=2

## Current Web Contract

- Status: `PASS`
- Favicon links: `1`
- Connection form: `form`
- Password field inside form: `True`
- Test connection button: `type=submit, action=test-connection`
- Lifecycle wiring: `PASS`

## Sensitive Handling

- Redaction applied: `True`
- Redacted keys: `-`
- Full credential values are not copied into this summary.
