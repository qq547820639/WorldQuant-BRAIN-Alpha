/**
 * useAppState — state foundation: shared types, backend-mirroring state
 * contract, and primitive UI state (useBaseState).
 *
 * This module aggregates the framework-agnostic state contract (mirrors the
 * backend 11-state candidate lifecycle), the AppState type surface, and the
 * foundational useState hook layer (useBaseState) that owns toasts, job &
 * global data wiring.
 *
 * NOTE: stateContract section is intentionally framework-agnostic (pure TS)
 * so it can be consumed by any panel, hook, test, or util without React.
 */

import { useState, useCallback, useEffect, useRef } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import type {
  BrainCredentials,
  Candidate,
  CardViewId,
  PhaseData,
  PhaseId,
  PhaseGroup,
} from '@/types';
import { useToast } from '@/hooks/useToast';
import { useJobState } from '@/hooks/useJobState';
import { useGlobalData } from '@/hooks/useGlobalData';
import { useApi } from '@/hooks/useApi';
import type { usePhaseState, PhaseApiStatus } from '@/hooks/usePhaseState';

// ──────────────────────────────────────────────────────────────────────────
// stateContract — shared, backend-mirroring state definitions
// ──────────────────────────────────────────────────────────────────────────

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

// ──────────────────────────────────────────────────────────────────────────
// types — AppState shared type definitions
// ──────────────────────────────────────────────────────────────────────────

/**
 * useAppState — shared type definitions
 *
 * Public surface: `AppState` (re-exported from index).
 * `SidebarBadges` is internal to this module.
 */

export interface SidebarBadges {
  candidates?: number;
  official_backtests?: string;
  scoring?: number;
  checkpoint_status?: number;
  cloud?: string;
}

export interface AppState {
  activeView: CardViewId;
  selectedCandidate: Candidate | null;
  credentials: BrainCredentials;
  sidebarOpen: boolean;
  expandedPhases: Set<string>;
  shortcutsHelpOpen: boolean;
  connectionOverride: boolean | null;
  connectionError: string | null;
  officialOpsAutoStart: boolean;
  toasts: ReturnType<typeof useToast>['toasts'];
  notify: (
    type: 'success' | 'error' | 'warning' | 'info',
    msg: string,
    action?: { label: string; onClick: () => void },
    secondaryAction?: { label: string; onClick: () => void }
  ) => void;
  dismissToast: (id: string) => void;
  jobState: ReturnType<typeof useJobState>;
  globalData: ReturnType<typeof useGlobalData>;
  phaseApi: ReturnType<typeof useApi<PhaseData>>;
  phaseData: PhaseData | null;
  phaseApiStatus: PhaseApiStatus;
  phaseConnected: boolean;
  connected: boolean;
  contextFresh: boolean;
  candidatesCount: number;
  scoredCount: number;
  readinessPassed: boolean;
  managedCredentialsAvailable: boolean;
  phaseState: ReturnType<typeof usePhaseState>['phaseState'];
  steps: ReturnType<typeof usePhaseState>['steps'];
  currentPhase: PhaseId;
  sidebarPhases: PhaseGroup[];
  sidebarBadges: SidebarBadges;
  setActiveView: (view: CardViewId) => void;
  setSelectedCandidate: (candidate: Candidate | null) => void;
  setCredentials: (credentials: BrainCredentials) => void;
  setSidebarOpen: (open: boolean) => void;
  setExpandedPhases: (phases: Set<string> | ((prev: Set<string>) => Set<string>)) => void;
  setShortcutsHelpOpen: (open: boolean) => void;
  setOfficialOpsAutoStart: (value: boolean) => void;
  handleTogglePhase: (phaseId: string) => void;
  handleNavigate: (view: CardViewId) => void;
  handleConnectionTested: (ok: boolean, err: string | null) => void;
  handleDashboardSyncStart: () => void;
  handleDashboardSyncOpen: () => void;
  handleOfficialSyncCompleted: () => void;
  handleOfficialReconnectRequested: () => void;
  handleCandidatePoolUpdated: () => void;
  handleLocalSessionLoggedOut: () => void;
  handleMobileNavigate: (target: PhaseId | 'tools') => void;
  openScoring: (candidate: Candidate) => void;
}

// ──────────────────────────────────────────────────────────────────────────
// useBaseState — foundational UI state, toasts, job & global data
// ──────────────────────────────────────────────────────────────────────────

/** Valid CardViewId strings used to validate hash values. */
const VALID_VIEWS = new Set<CardViewId>([
  'official_operations',
  'dashboard',
  'candidates',
  'official_backtests',
  'scoring',
  'quality_check',
  'submission_confirm',
  'config',
  'checkpoint_status',
  'cloud',
  'robustness',
]);

/**
 * W-004: activeView ↔ URL path mapping for BrowserRouter.
 * Only the four primary navigation surfaces get a real path entry;
 * other views keep working via internal state (forward compatible).
 */
const VIEW_TO_PATH: Partial<Record<CardViewId, string>> = {
  dashboard: '/',
  config: '/config',
  candidates: '/candidates',
  scoring: '/scoring',
};

const PATH_TO_VIEW: Record<string, CardViewId> = {
  '/': 'dashboard',
  '/config': 'config',
  '/candidates': 'candidates',
  '/scoring': 'scoring',
};

function readViewFromHash(): CardViewId {
  // Prioritize URL path (BrowserRouter) for forward-compatible routing.
  const pathView = PATH_TO_VIEW[window.location.pathname];
  if (pathView) return pathView;
  // Backward compat: legacy hash-based deep links.
  const hash = window.location.hash.replace('#', '');
  if (hash && VALID_VIEWS.has(hash as CardViewId)) {
    return hash as CardViewId;
  }
  return 'dashboard';
}

export type NotifyFn = (
  type: 'success' | 'error' | 'warning' | 'info',
  msg: string,
  action?: { label: string; onClick: () => void },
  secondaryAction?: { label: string; onClick: () => void }
) => void;

export interface BaseState {
  activeView: CardViewId;
  setActiveView: Dispatch<SetStateAction<CardViewId>>;
  selectedCandidate: Candidate | null;
  setSelectedCandidate: Dispatch<SetStateAction<Candidate | null>>;
  credentials: BrainCredentials;
  setCredentials: Dispatch<SetStateAction<BrainCredentials>>;
  sidebarOpen: boolean;
  setSidebarOpen: Dispatch<SetStateAction<boolean>>;
  expandedPhases: Set<string>;
  setExpandedPhases: Dispatch<SetStateAction<Set<string>>>;
  shortcutsHelpOpen: boolean;
  setShortcutsHelpOpen: Dispatch<SetStateAction<boolean>>;
  officialOpsAutoStart: boolean;
  setOfficialOpsAutoStart: Dispatch<SetStateAction<boolean>>;
  toasts: ReturnType<typeof useToast>['toasts'];
  notify: NotifyFn;
  dismissToast: (id: string) => void;
  jobState: ReturnType<typeof useJobState>;
  globalData: ReturnType<typeof useGlobalData>;
}

export function useBaseState(): BaseState {
  const [activeView, setActiveViewRaw] = useState<CardViewId>(readViewFromHash);
  const activeViewRef = useRef(activeView);

  /** Wrap setActiveView so it also syncs the URL path (W-004). */
  const setActiveView = useCallback((view: CardViewId | ((prev: CardViewId) => CardViewId)) => {
    setActiveViewRaw((prev) => {
      const next = typeof view === 'function' ? view(prev) : view;
      activeViewRef.current = next;
      const path = VIEW_TO_PATH[next];
      if (path && window.location.pathname !== path) {
        window.history.pushState({}, '', path);
      }
      return next;
    });
  }, []);

  /** Respond to external path changes (browser back/forward, manual edit). */
  useEffect(() => {
    const onPopState = () => {
      const view = readViewFromHash();
      if (view !== activeViewRef.current) {
        activeViewRef.current = view;
        setActiveViewRaw(view);
      }
    };
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);
  const [selectedCandidate, setSelectedCandidate] = useState<Candidate | null>(null);
  const [credentials, setCredentials] = useState<BrainCredentials>({
    username: '',
    password: '',
    token: '',
  });
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [expandedPhases, setExpandedPhases] = useState<Set<string>>(new Set(['connect']));
  const [shortcutsHelpOpen, setShortcutsHelpOpen] = useState(false);
  const [officialOpsAutoStart, setOfficialOpsAutoStart] = useState(false);
  const { toasts, addToast, dismissToast } = useToast();

  const notify = useCallback<NotifyFn>(
    (type, msg, action, secondaryAction) => {
      addToast(type, msg, 5000, action, secondaryAction);
    },
    [addToast]
  );

  const jobState = useJobState(notify, credentials);
  const globalData = useGlobalData();

  return {
    activeView,
    setActiveView,
    selectedCandidate,
    setSelectedCandidate,
    credentials,
    setCredentials,
    sidebarOpen,
    setSidebarOpen,
    expandedPhases,
    setExpandedPhases,
    shortcutsHelpOpen,
    setShortcutsHelpOpen,
    officialOpsAutoStart,
    setOfficialOpsAutoStart,
    toasts,
    notify,
    dismissToast,
    jobState,
    globalData,
  };
}
