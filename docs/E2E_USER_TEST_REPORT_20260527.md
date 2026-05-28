# BRAIN Alpha Ops Web E2E User Test Report

- Test date: 2026-05-27
- Test mode: Real browser operation against the local Web console
- Local URL: http://127.0.0.1:18765/
- Browser surface: Codex in-app browser
- Scope: Main user journey, form interaction, navigation, data interaction, loading/error feedback, and safety state
- Screenshot: `docs/e2e_screenshots/browser_e2e_final_sanitized_20260527.png`

## Executive Summary

The Web console loaded successfully and the primary layout is usable: status bar, connection form, task console, stage navigation, table/chart switch, search filter, plugin controls, and research/data audit views are all reachable through real browser interactions.

The strongest product issue found in this E2E pass is the cloud sync experience: after a successful connection test, cloud sync entered a long-running scan state, locked conflicting actions, and eventually showed a timeout message: "云端同步失败：云端同步超时，后台任务仍未完成 | 0% | 0/0 | 新增 0". The message is visible and non-crashing, but it lacks a cancel/retry action and does not explain the next best user step.

## Environment And Setup

| Item | Result |
|---|---|
| Local service startup | Passed after running outside the sandbox so the service could bind to a localhost port |
| Page load | Passed |
| Page title | BRAIN Alpha Ops |
| Sensitive field cleanup | Passed after keyboard-based clearing |
| Browser console errors | None captured |

## Scenario Results

| Scenario | User Action | Result | Notes |
|---|---|---|---|
| Initial page load | Opened local Web console | Passed | Page rendered status bar, control panel, task navigation, and candidate empty state. |
| Connection form | Entered credentials and clicked "测试连接" | Passed | UI displayed "连接成功". |
| Cloud sync | Clicked "同步云端" | Failed with handled timeout | UI locked conflicting actions and later showed a readable timeout message. |
| Conflict-state feedback | Observed controls during sync | Passed | Production, sync, check, and submit actions were temporarily disabled while sync was running. |
| Data audit navigation | Opened Cloud Data and Lifecycle views | Passed | Headings updated to "云端数据" and "生命周期". |
| Research navigation | Opened Research Memory, Knowledge Base, Observability, Prompt Ledger, SQLite Index, Robustness | Passed | All target headings updated correctly. |
| Search filter | Entered `rank` in the result search box | Passed | Search value was applied and empty-state copy updated to the filtered no-data state. |
| View switch | Switched between table and chart | Passed with limitation | Chart view showed "Chart.js 未加载，当前视图暂无可绘制数据。"; table view restored correctly. |
| Empty check path | Clicked "检查达标" without candidates | Passed | UI remained stable and showed empty/no-candidate state rather than crashing. |
| Strategy plugin settings | Enabled plugin toggle, filled plugin spec, disabled toggle | Passed with caveat | Textarea enabled/disabled correctly; disabled textarea retains the previous value but states plugin is off. |
| Submit safety | Observed submit controls | Passed | Submit buttons remained disabled with no candidate selected. |

## Safety Boundary

The E2E pass did not trigger "开始生产搜索" after the read-only sync timeout, and did not attempt submit. Those actions can consume official BRAIN simulation/submission resources in production mode. The UI-level availability, disabled submit state, empty-state check flow, and conflict-locking behavior were verified instead.

## Experience Pain Points

1. Cloud sync timeout needs stronger recovery affordance.
   The UI explains that sync timed out, but there is no visible cancel, retry, view logs, or "what to do next" action near the timeout message.

2. Header connection state remains ambiguous.
   After "连接成功", the top bar still showed `offline --` during the observed session. Users may not know whether API auth succeeded, cloud sync failed, or the connection state is stale.

3. Long-running sync progress is too coarse.
   The sync stayed on "扫描" / 0% for an extended period. The page says it is not frozen, which helps, but the progress detail does not identify which API call or item range is being scanned.

4. Chart empty state depends on Chart.js availability.
   The chart tab handles missing Chart.js gracefully, but the message reads like a technical dependency issue. A user-oriented fallback could say that chart visualization is unavailable and the table remains usable.

5. Disabled plugin spec retains stale value.
   This is not functionally unsafe because the UI says plugin loading is off, but users may wonder whether the retained spec will still be used.

## Recommendations

| Priority | Recommendation | Expected User Benefit |
|---|---|---|
| P1 | Add retry/cancel/log actions to cloud sync timeout state | Users can recover without guessing or restarting the service. |
| P1 | Synchronize top-bar connection status with successful test connection and failed sync separately | Users can distinguish API auth success from data sync failure. |
| P1 | Show current sync phase and last successful API step | Reduces anxiety during long-running scans. |
| P2 | Replace Chart.js missing message with user-first fallback copy | Makes chart limitation understandable to non-technical users. |
| P2 | Clear or visually mark plugin spec as inactive when plugin toggle is off | Prevents ambiguity around retained disabled values. |

## Final State

- Active view: 稳健性
- Sensitive input visible: No
- Submit state: Disabled
- Last observed major error: Cloud sync timeout
- Overall E2E verdict: Pass with P1 UX issue in cloud sync recovery
