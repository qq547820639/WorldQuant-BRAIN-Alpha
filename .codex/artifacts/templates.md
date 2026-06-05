# State File Templates

Use these minimal templates when a live state file is missing.

## `intent-anchor.md`

```markdown
# Intent Anchor

original_goal:

success_criteria:
-

hard_constraints:
-

unacceptable_outcomes:
-

adjustable_range:
-

updated_at:
```

## `phase-state.md`

```markdown
# Phase State

current_phase:

completed_phases:
-

blocked_items:
-

next_action:
```

## `understanding.md`

```markdown
# Understanding

source_map:
- source_id:
  path:
  lines:
  commit:

claims:
- claim_id:
  claim:
  source_id:
  confidence:

uncertainties:
-
```

## `decision-log.md`

```markdown
# Decision Log

major_decisions:
- decision:
  rationale:
  rejected_options:
  source_refs:
```

## `risk-register.md`

```markdown
# Risk Register

active_risks:
- risk:
  level:
  mitigation:

escalation_required: false
```

## `agent-threads.md`

```markdown
# Agent Threads

active:
-

completed:
-

closed:
-

stuck_or_orphaned:
-
```
