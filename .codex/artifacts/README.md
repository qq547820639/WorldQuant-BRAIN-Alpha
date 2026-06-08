# `.codex/artifacts` contract

This directory stores local live coordination state for Codex agents. It is not business data and must not contain secrets.

## State Files

- `intent-anchor.md`: objective, success criteria, hard constraints, stop conditions, validation commands, out-of-scope items, updated time
- `phase-state.md`: current phase, completed phases, blocked items, next action
- `understanding.md`: source map, claims with source IDs and confidence, uncertainties
- `decision-log.md`: major decisions, rationale, rejected options
- `risk-register.md`: active risks, level, mitigations, escalation flag
- `agent-threads.md`: active, completed, closed, stuck or orphaned agent threads

## Recovery Order

Restore tasks by reading this README first, then:

1. `phase-state.md`: current phase, completed phases, next action, blockers.
2. `intent-anchor.md`: objective, success criteria, hard constraints, stop conditions.
3. `decision-log.md`: key decisions, rationale, rejected options.
4. `risk-register.md`: active risks, severity, mitigations.
5. `agent-threads.md`: created, completed, closed, stuck or orphaned subagents.
6. `understanding.md`: source map, trace IDs, claims, uncertainties.

If `phase-state.md` conflicts with `intent-anchor.md`, the anchor wins. Record the resolution in `decision-log.md`.
If a state file is missing, mark it as missing and recreate only the minimal template needed for the current task.

## Goal Sync

When `/goal` is created or updated, mirror these fields into `intent-anchor.md`:

- `objective`
- `success_criteria`
- `constraints`
- `stop_conditions`
- `validation_commands`
- `out_of_scope`

Final delivery must check both the active `/goal` and `intent-anchor.md` against the actual result.

## Append-only Rules

Runtime artifacts should append a new section for the current turn instead of overwriting older sections.

### Status Labels

Historical content must be labeled by current confidence:

- `confirmed`: verified in the current turn and still valid.
- `stale`: outdated and not safe to use as current fact.
- `superseded`: replaced by a newer conclusion.
- `unknown`: not currently verified.

### Superseding Older Content

When a new conclusion replaces an old one, append a new section instead of deleting the old section. Include:

- `supersedes: <old_section_id>`
- `reason: <why it is replaced>`
- `confirmed_by: <file, command, reviewer result, or user confirmation>`

### Forbidden

Do not:

- overwrite old conclusions without recording why
- delete history just to make the state look clean
- treat old business state as current fact without checking it
- mark `unknown` as `confirmed` before verification

## Ownership

- Principal and `context-management` read/write these files in Phase 0 and Phase 5.
- Specialist skills contribute outputs, reviews, findings, and artifacts; they do not own scheduling policy.
- `impeccable` may contribute `impeccable_review` content for UI/UX or final quality review, but persistence remains here.

## Safety

Do not store passwords, cookies, API tokens, credentials, official submission credentials, private account data, or unredacted sensitive material. Store redacted references or access requirements instead.
