# AF022 Docs Readiness Matrix

**Task ID**: AF022-DOCS-READINESS-MATRIX
**Status**: In progress; this matrix advances AF-022 documentation planning only and does not mark AF-022 complete.
**Scope**: Map stabilized contracts and existing evidence to future user manual, developer guide, operator runbook, safety boundary, and final acceptance report prerequisites.
**Evidence boundary**: Repository documentation only. No real BRAIN submit, live official API call, credential handling, credential output, screenshots, product-code edits, or test edits were performed for this artifact.

## Claim Rules

- Compliance gate evidence may support documentation readiness only when it is traceable to current executable checks or explicitly labeled as historical.
- Submit readiness is never implied by local compliance evidence. A completion claim for any submit-capable workflow requires same-candidate `ready_to_submit=true`, complete real official evidence, low similarity, `decision_band=submit_candidate`, successful submit preflight, and explicit human confirmation.
- AF-022 can only be marked complete after all downstream documents listed here have current evidence, missing evidence closed or explicitly accepted as deferred, and final acceptance language avoids live-submit or production-readiness overclaiming.

## User Guide Prerequisites

| Stabilized contract / doc area | Current evidence | Missing evidence | Owner AF | Completion claim rule |
|---|---|---|---|---|
| Guided workflow: connect, sync, generate, score, check, submit review | `docs/ACCEPTANCE_REPORT_20260604.md` documents the six-step user workflow and user-facing state coverage. `docs/UX_ARCHITECTURE_REDESIGN_20260608.md` maps readiness review into the submission flow. | Fresh user-manual walkthrough that reflects the current UI labels, current screenshots if needed, and exact non-submit wording for blocked candidates. | AF-022 user manual | Claim "user guide ready" only after the walkthrough is reviewed against the current UI artifact and every submit-related step says review/confirmation, not automatic submit. |
| Configuration and market settings | `docs/BRAIN_OFFICIAL_COMPLIANCE_MAP.md` lists canonical production settings and threshold alignment. `docs/REVIEW_GAP_CLOSURE_20260530.md` records config edit/save evidence. | User-facing explanation of safe editable settings, invalid setting feedback, import/export behavior, and when operator help is required. | AF-022 user manual | Claim completion only when settings guidance is traceable to the canonical compliance map and does not authorize threshold drift. |
| Candidate table, scoring, and blockers | `docs/DEFECT_ANALYSIS_REPORT_20260602.md` records readiness blocker taxonomy and fail-closed diagnostics. `docs/QUANTGPT_COMPREHENSIVE_REVIEW_AND_UPGRADE_20260605.md` summarizes why current candidates remain non-submit. | Plain-language mapping from blocker codes to user actions, including no-action cases where evidence is missing or candidate quality is insufficient. | AF-022 user manual | Claim completion only when every blocker explanation preserves the rule that missing official evidence is not user-overridable submit evidence. |

## Developer Guide Prerequisites

| Stabilized contract / doc area | Current evidence | Missing evidence | Owner AF | Completion claim rule |
|---|---|---|---|---|
| Canonical BRAIN compliance gates | `docs/BRAIN_OFFICIAL_COMPLIANCE_MAP.md` maps redline, canonical compliance, official context, parameter traceability, final release, and live readiness checks. | Developer-guide section describing which scripts are normative, which are advisory, and how strict freshness differs from local non-submit validation. | AF-022 developer guide | Claim "developer guide ready" only after each gate command has an owner, expected pass/fail interpretation, and no guidance that bypasses strict official-context or submit-readiness gates. |
| Web/API interface contract | `docs/phase2_1_interface_contract.md` documents the Web API surface and labels submit routes as historical backend paths behind staged Web readiness review. | Current route table summary for developer readers, including payload ownership and compatibility boundaries after recent web facade changes. | AF-022 developer guide | Claim completion only when direct submit route examples remain clearly historical and maintainers are pointed to staged readiness and preflight paths. |
| Architecture and shared contracts | `docs/SYSTEM_ARCHITECTURE_V4_20260608.md`, `docs/BACKEND_ARCHITECTURE_V4_20260608.md`, and `docs/DEVELOPMENT_REVIEW_20260608.md` describe service boundaries and shared Protocol contracts. | Developer-guide crosswalk from stable contracts to modules/tests, plus notes for known technical debt that is not an AF-022 completion blocker. | AF-022 developer guide | Claim completion only when the guide distinguishes stable public contracts from implementation details and does not treat historical test debt as resolved without current evidence. |

## Operator Runbook Prerequisites

| Stabilized contract / doc area | Current evidence | Missing evidence | Owner AF | Completion claim rule |
|---|---|---|---|---|
| Startup and local validation | `docs/ACCEPTANCE_REPORT_20260604.md` lists validate-only, parameter traceability, core tests, frontend innerHTML, and official context checks. `docs/BRAIN_OFFICIAL_COMPLIANCE_MAP.md` lists release-level compliance gates. | Runbook-ready command order with expected outputs, failure triage, and explicit "do not continue" stop points. | AF-022 operator runbook | Claim runbook readiness only after each command has pass/fail handling and no step requires credentials unless the runbook says how to provide them without recording or displaying them. |
| Official context freshness and metadata | `docs/BRAIN_OFFICIAL_COMPLIANCE_MAP.md` records official cache metadata and maintenance rules. Older acceptance evidence also records metadata freshness as a follow-up risk. | Current refresh procedure, freshness expiry interpretation, and handoff path when credentials or network are unavailable. | AF-022 operator runbook | Claim completion only when freshness refresh is documented as an operator action and stale context cannot be mistaken for submit readiness. |
| Submit preflight and human confirmation | `docs/BRAIN_OFFICIAL_COMPLIANCE_MAP.md` and `docs/DEFECT_ANALYSIS_REPORT_20260602.md` state that submit remains blocked without same-candidate evidence and explicit confirmation. | Step-by-step non-submit preflight review, manual confirmation checklist, evidence retention rules, and abort conditions for unclear status. | AF-022 operator runbook | Claim completion only when the runbook requires real official Alpha ID, complete official metrics, official PASS, low similarity, `submit_candidate`, local backtest not failed, successful preflight, and explicit human confirmation before any real submit. |

## Safety And Non-Submit Boundary Prerequisites

| Stabilized contract / doc area | Current evidence | Missing evidence | Owner AF | Completion claim rule |
|---|---|---|---|---|
| Non-submit default posture | `docs/BRAIN_OFFICIAL_COMPLIANCE_MAP.md` says local compliance does not imply submit readiness. `docs/GOAL_COMPLETION_AUDIT_20260605.md` records `ready_to_submit=false` evidence and the no-submit boundary. | Consolidated safety-boundary page that product, developer, and operator docs can all reference. | AF-022 safety boundaries | Claim safety docs ready only when the page states local-only validation, fail-closed behavior, and human confirmation rules without exception. |
| Credential and sensitive-data handling | `.codex/artifacts/README.md` forbids storing credentials in coordination artifacts. Existing acceptance docs note token memory use and redaction safety. | Safety doc section for docs authors: do not paste credentials, screenshots, cookies, tokens, private account data, or unredacted official account output. | AF-022 safety boundaries | Claim completion only when all downstream docs use redacted examples and none require saving, printing, or screenshotting credentials. |
| Stub, mock, and local evidence limits | `docs/DEFECT_ANALYSIS_REPORT_20260602.md` records fail-closed handling for non-production Alpha IDs and local-only candidate evidence. | Explicit wording for which evidence is local-only, historical, mocked, or official, including examples of claims that are not allowed. | AF-022 safety boundaries | Claim completion only when any local/mock/stub evidence is labeled non-submit and cannot be cited as production submit proof. |

## Final Acceptance Report Prerequisites

| Stabilized contract / doc area | Current evidence | Missing evidence | Owner AF | Completion claim rule |
|---|---|---|---|---|
| Acceptance basis and evidence index | `docs/ACCEPTANCE_REPORT_20260604.md`, `docs/DELIVERY_COMPLETION_AUDIT_20260528.md`, and `docs/BRAIN_OFFICIAL_COMPLIANCE_MAP.md` provide historical acceptance, delivery audit, and compliance-map evidence. | Updated acceptance evidence index with current dates, exact commands, outputs, owner sign-off, and stale-vs-current labels. | AF-022 final acceptance report | Claim final report readiness only after current evidence is refreshed or clearly labeled historical, with no unverified "done" or "production ready to submit" language. |
| Known gaps and deferred items | Existing acceptance and review-gap docs list metadata freshness, test debt, frontend parity, and manual live-submit follow-ups as known limitations. | Current gap table that separates blocking gaps, accepted deferred gaps, and non-blocking follow-ups for AF-022 documentation completion. | AF-022 final acceptance report | Claim completion only when every known gap has owner, severity, current status, and a rule explaining whether it blocks AF-022 docs completion. |
| Final non-submit and submit-readiness statement | Current docs consistently say no real submit is claimable without same-candidate official evidence and explicit confirmation. | Final acceptance wording approved by safety/operator owners, including the exact boundary between software/docs readiness and real BRAIN submission readiness. | AF-022 final acceptance report | Claim final acceptance only if the report says AF-022 documentation readiness is separate from live BRAIN submit readiness, and AF-022 is not marked done until all prerequisite docs satisfy their claim rules. |

## Trace Requests

- `TR-AF022-USER-001`: Verify current UI labels and screenshots before drafting the user manual.
- `TR-AF022-DEV-001`: Confirm the current normative gate list and route-contract owners before drafting the developer guide.
- `TR-AF022-OPS-001`: Confirm operator command order, credential-safe refresh procedure, and stop conditions before drafting the runbook.
- `TR-AF022-SAFE-001`: Review the consolidated non-submit and credential-boundary wording before downstream docs reuse it.
- `TR-AF022-ACCEPT-001`: Refresh or label all final acceptance evidence before any AF-022 completion claim.

## Transfer Note

Recommended next transfer target: AF-022 documentation lead, with safety/operator review before any final acceptance wording is promoted.
