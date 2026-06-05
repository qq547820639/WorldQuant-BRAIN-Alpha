# `.codex/artifacts` contract

This directory stores local live coordination state for Codex agents. It is not business data and must not contain secrets.

## State Files

- `intent-anchor.md`: original goal, success criteria, hard constraints, unacceptable outcomes, adjustable range, updated time
- `phase-state.md`: current phase, completed phases, blocked items, next action
- `understanding.md`: source map, claims with source IDs and confidence, uncertainties
- `decision-log.md`: major decisions, rationale, rejected options
- `risk-register.md`: active risks, level, mitigations, escalation flag
- `agent-threads.md`: active, completed, closed, stuck or orphaned agent threads

## Ownership

- Principal and `context-management` read/write these files in Phase 0 and Phase 5.
- Specialist skills contribute outputs, reviews, findings, and artifacts; they do not own scheduling policy.
- `impeccable` may contribute `impeccable_review` content for UI/UX or final quality review, but persistence remains here.

## Safety

Do not store passwords, cookies, API tokens, credentials, official submission credentials, private account data, or unredacted sensitive material. Store redacted references or access requirements instead.
