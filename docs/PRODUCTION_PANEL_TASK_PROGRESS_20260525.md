# Production Panel Task Progress - 2026-05-25

Scope: Continue the current executable checklist for the production configuration panel, frontend/backend config contract, Chinese localization, interaction layout, verification, and Windows EXE packaging.

## In Progress

None.

## Completed

- [x] BASELINE-1 Validated `config/run_config.json` structure through the production config validator.
- [x] BASELINE-2 Reviewed the current production panel and identified the single-button discoverability issue as a layout/state visibility problem, not a backend capability limit.
- [x] BASELINE-3 Confirmed current select options are backed by the canonical settings contract after the prior Unit Handling and Alpha Type fixes.
- [x] TASK-1 Frontend/backend configuration contract repair: the panel now emits canonical camelCase web payload keys, includes all visible strategy/guidance controls, and hydrates visible controls from `/api/config`.
- [x] TASK-2 Production panel layout completion: the sidebar now exposes a visible task console for production, cloud sync, official check, and selected submit actions with shared disabled-state reasons.
- [x] TASK-3 Chinese localization: user-facing production panel labels, environment badge, theme labels, strategy policy text, and view registry labels are localized while official enum values stay unchanged.
- [x] TASK-4 Contract tests: frontend module tests now cover payload key names, visible guidance/plugin controls, config hydration, and backend schema parsing; focused web suite passed with 162 tests.
- [x] TASK-5 Inline build sync and quality gate verification: generated `index.html` is in sync, production config validation passed, `quality_gate.py --skip-tests --json` passed, and full pytest passed with 678 tests.
- [x] TASK-6 Rebuild and smoke-test the Windows EXE after frontend changes: `dist/BrainAlphaOps.exe` was rebuilt, smoke-tested successfully, and checked over HTTP for the new task console, Chinese labels, config schema, and canonical `settings.type` contract.
- [x] TASK-7 Repair packaged official context delivery: the Windows build now copies official context JSON, metadata, and refresh status into `dist/data`; the loader also self-heals missing packaged official context from PyInstaller's bundled data without overwriting valid runtime files.
- [x] TASK-8 Release validation after packaged context repair: `dist/data` official-context validation passed with fields=7642, operators=66, datasets=16; `dist/BrainAlphaOps.exe --smoke-test --port 18772` returned ready; live EXE `/api/health` returned ready and `/` returned HTTP 200 without the prior official-context empty-load warning.
- [x] TASK-9 Repair packaged hypothesis library delivery: the Windows build now copies all hypothesis YAML files into `dist/brain_alpha_ops/research/hypotheses`; `HypothesisLibrary` self-heals missing packaged YAML files from PyInstaller data without overwriting valid runtime files; repeated empty-library warning spam is suppressed to one warning if the fallback ever has to run.
- [x] TASK-10 Release validation after hypothesis repair: release-directory hypothesis load returned 8 hypotheses, forced hypothesis-driven generation produced 3 candidates without `no hypotheses loaded`, full pytest passed with 688 tests, and live EXE `/api/health` returned ready with no official-context or empty-hypothesis warning in captured startup output.

## Pending

None.

## Deferred

- [ ] DEFER-1 Live BRAIN account submission validation remains manual by design; automated tests must not submit real alphas.
- [ ] DEFER-2 In-app browser screenshot verification was blocked by the browser client for localhost, and `npx` is not available for the Playwright CLI fallback. EXE smoke, HTTP/DOM checks, packaged context validation, hypothesis-generation checks, and captured EXE startup checks were completed instead.
