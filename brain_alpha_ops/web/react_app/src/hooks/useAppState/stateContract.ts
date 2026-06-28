/**
 * stateContract — shared, backend-mirroring state definitions for Workstream E2.
 *
 * This module is the SINGLE source of truth for the frontend's view of the
 * candidate Alpha lifecycle. It mirrors the backend 11-state machine defined
 * in `brain_alpha_ops/candidate_lifecycle.py` (Workstream B):
 *
 *   draft → locally_scored → {gate_rejected, queued_for_simulation,
 *                              needs_optimization, archived}
 *   queued_for_simulation → simulating → {simulation_passed, simulation_failed}
 *   simulation_passed → {ready_for_review, submitted} → archived
 *
 * Dashboard / ConfigPanel / candidate pool / scoring / gate / simulation
 * queue / history / system config panels SHOULD import from this contract
 * instead of redefining lifecycle strings locally, so that state drift is
 * impossible and new code can rely on a single typed definition.
 *
 * NOTE: This file is intentionally framework-agnostic (pure TS) so it can be
 * consumed by any panel, hook, test, or util without pulling in React.
 */

/**
 * Canonical 11-state candidate lifecycle (mirrors backend `LifecycleState`).
 * Order matches the enum declaration in `candidate_lifecycle.py`.
 */
export type CandidateLifecycleState =
  | 'draft'
  | 'locally_scored'
  | 'gate_rejected'
  | 'queued_for_simulation'
  | 'simulating'
  | 'simulation_failed'
  | 'simulation_passed'
  | 'needs_optimization'
  | 'ready_for_review'
  | 'submitted'
  | 'archived';

/**
 * Ordered list of all canonical lifecycle states.
 * Useful for rendering state legends, filters, and audit trails.
 */
export const CANDIDATE_LIFECYCLE_STATES: readonly CandidateLifecycleState[] = [
  'draft',
  'locally_scored',
  'gate_rejected',
  'queued_for_simulation',
  'simulating',
  'simulation_failed',
  'simulation_passed',
  'needs_optimization',
  'ready_for_review',
  'submitted',
  'archived',
] as const;

/**
 * Legal-transition graph mirroring backend `_LEGAL_TRANSITIONS`.
 *
 * Each key is a `from_state`; the value is the set of `to_state`s that the
 * state machine accepts. Self-transitions are included where the backend
 * allows them (deferred / blocked sub-statuses).
 *
 * `archived` is a true terminal state (empty set).
 */
export const LEGAL_TRANSITIONS: Readonly<
  Record<CandidateLifecycleState, readonly CandidateLifecycleState[]>
> = {
  draft: ['locally_scored', 'gate_rejected', 'archived'],
  locally_scored: ['gate_rejected', 'queued_for_simulation', 'needs_optimization', 'archived'],
  gate_rejected: ['needs_optimization', 'archived'],
  queued_for_simulation: ['simulating', 'gate_rejected', 'queued_for_simulation'],
  simulating: ['simulation_passed', 'simulation_failed', 'simulating'],
  simulation_failed: ['needs_optimization', 'archived', 'queued_for_simulation'],
  simulation_passed: ['ready_for_review', 'submitted'],
  needs_optimization: ['locally_scored'],
  ready_for_review: ['submitted', 'archived', 'ready_for_review'],
  submitted: ['archived'],
  archived: [],
};

/**
 * Connection state for the BRAIN session / local cache.
 *
 * - `connected`    : live BRAIN session established
 * - `cache_only`   : no live session, but local cache is fresh enough to drive UI
 * - `disconnected` : no session AND no usable cache
 */
export type ConnectionState = 'connected' | 'cache_only' | 'disconnected';

/**
 * Quality-gate decision action (mirrors backend gate decision outcomes).
 *
 * - `continue_optimization`     : candidate sent back to optimization loop
 * - `discard_archive`           : candidate rejected and archived
 * - `queue_for_simulation`      : candidate promoted to the official sim queue
 * - `needs_human_confirmation`  : gate cannot auto-decide, requires human review
 */
export type GateDecisionAction =
  | 'continue_optimization'
  | 'discard_archive'
  | 'queue_for_simulation'
  | 'needs_human_confirmation';

// ── Type guards ───────────────────────────────────────────────────────────

/**
 * True if the state is a true terminal state with no legal outgoing
 * transitions (mirrors `CandidateLifecycle.is_terminal()`).
 */
export function isTerminalState(
  state: string | null | undefined
): state is CandidateLifecycleState {
  return state === 'archived';
}

/**
 * True if the candidate is actively in the official simulation pipeline
 * (queued or currently simulating). Mirrors the backend notion of an
 * "active backtest candidate" — a candidate that has a pending/running
 * official simulation and is not in an inactive state.
 */
export function isActiveBacktestState(
  state: string | null | undefined
): state is CandidateLifecycleState {
  return state === 'queued_for_simulation' || state === 'simulating';
}

/**
 * True if the candidate is in an inactive backtest state — i.e. the
 * simulation pipeline has given up on it (failed, gate-rejected, or
 * archived). Mirrors backend `_INACTIVE_ENUM_STATES`:
 *   {simulation_failed, gate_rejected, archived}.
 */
export function isInactiveBacktestState(
  state: string | null | undefined
): state is CandidateLifecycleState {
  return state === 'simulation_failed' || state === 'gate_rejected' || state === 'archived';
}

// ── Transition helpers ────────────────────────────────────────────────────

/**
 * Validate a transition against the legal-transition graph.
 * Returns true iff `from → to` is permitted by `LEGAL_TRANSITIONS`.
 */
export function isLegalTransition(from: string | null | undefined, to: string): boolean {
  if (!from) return false;
  const allowed = LEGAL_TRANSITIONS[from as CandidateLifecycleState];
  return Array.isArray(allowed) && allowed.includes(to);
}

/**
 * Return the list of states the candidate may legally move to from `from`.
 * Empty for terminal states. Always returns a fresh array (safe to mutate).
 */
export function legalNextStates(from: string): CandidateLifecycleState[] {
  const allowed = LEGAL_TRANSITIONS[from as CandidateLifecycleState];
  return Array.isArray(allowed) ? [...allowed] : [];
}
