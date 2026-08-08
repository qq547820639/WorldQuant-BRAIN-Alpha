/**
 * useAppState — effects/connections sub-hooks.
 *
 * Aggregates the side-effect-heavy sub-hooks that drive the unified app
 * state machine:
 *   - usePhaseConnection    phase polling, connection flags, session handlers
 *   - useErrorNotifications globalData error → toast bridging
 *   - usePhaseManagement    phase derivation, sidebar groups, mobile nav
 *
 * Side-effect-only hooks: each returns its derived slice of state.
 */

import { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import type {
  BrainCredentials,
  Candidate,
  CardViewId,
  PhaseData,
  PhaseId,
  PhaseGroup,
} from '@/types';
import { useApi } from '@/hooks/useApi';
import type { ApiMeta } from '@/hooks/useApi';
import type { useGlobalData } from '@/hooks/useGlobalData';
import { usePhaseState } from '@/hooks/usePhaseState';
import type { PhaseApiStatus } from '@/hooks/usePhaseState';
import { reportIgnoredError } from '@/utils';
import { nextActionLabel, safeDisplayErrorMessage } from '@/helpers/errorExperience';
import {
  isActionableErrorPayload,
  recoveryActionLabel,
  type ActionableErrorPayload,
} from '@/types';
import type { NotifyFn } from './useAppStateState';

// ──────────────────────────────────────────────────────────────────────────
// usePhaseConnection
// ──────────────────────────────────────────────────────────────────────────

export interface PhaseConnectionOptions {
  setCredentials: Dispatch<SetStateAction<BrainCredentials>>;
  globalData: ReturnType<typeof useGlobalData>;
}

export interface PhaseConnectionResult {
  connectionOverride: boolean | null;
  connectionError: string | null;
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
  handleConnectionTested: (ok: boolean, err: string | null) => void;
  handleLocalSessionLoggedOut: () => void;
}

export function usePhaseConnection({
  setCredentials,
  globalData,
}: PhaseConnectionOptions): PhaseConnectionResult {
  const [connectionOverride, setConnectionOverride] = useState<boolean | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  const phaseApi = useApi<PhaseData>();

  useEffect(() => {
    void phaseApi.call('/api/phase_state');
    const interval = setInterval(() => {
      void phaseApi.call('/api/phase_state');
    }, 10_000);
    return () => clearInterval(interval);
  }, [phaseApi.call]);

  const phaseData = phaseApi.data;
  const phaseApiStatus: PhaseApiStatus = phaseData ? 'ready' : phaseApi.error ? 'error' : 'loading';
  const phaseConnected = Boolean(phaseData?.connected);
  const connected = Boolean(connectionOverride ?? phaseConnected) && !connectionError;
  const contextFresh = phaseData?.context_fresh ?? false;
  const candidatesCount = phaseData?.candidates_count ?? globalData.candidates.data?.total ?? 0;
  const scoredCount = phaseData?.scored_count ?? 0;
  const readinessPassed = phaseData?.readiness_passed ?? false;
  const managedCredentialsAvailable = Boolean(
    globalData.config.data?.config?.credentials?.managed_credentials_available
  );

  const handleConnectionTested = useCallback(
    (ok: boolean, err: string | null) => {
      setConnectionOverride(ok);
      setConnectionError(err);
      setCredentials((prev) => ({ ...prev, password: '' }));
      try {
        sessionStorage.removeItem('brain_alpha_connection_tested');
      } catch (storageErr) {
        reportIgnoredError('legacy connection sessionStorage cleanup failed', storageErr);
      }
      void phaseApi.call('/api/phase_state');
    },
    [phaseApi.call, setCredentials]
  );

  const handleLocalSessionLoggedOut = useCallback(() => {
    setCredentials({ username: '', password: '', token: '' });
    setConnectionOverride(false);
    setConnectionError(null);
    void phaseApi.call('/api/phase_state');
  }, [phaseApi.call, setCredentials]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 连接状态追平时重置 override（条件同步，已加判断避免无谓重渲染）
    if (connectionOverride === true && phaseConnected) setConnectionOverride(null);
    if (connectionOverride === false && !phaseConnected) setConnectionOverride(null);
  }, [connectionOverride, phaseConnected]);

  return {
    connectionOverride,
    connectionError,
    phaseApi,
    phaseData,
    phaseApiStatus,
    phaseConnected,
    connected,
    contextFresh,
    candidatesCount,
    scoredCount,
    readinessPassed,
    managedCredentialsAvailable,
    handleConnectionTested,
    handleLocalSessionLoggedOut,
  };
}

// ──────────────────────────────────────────────────────────────────────────
// useErrorNotifications
// ──────────────────────────────────────────────────────────────────────────

export interface ErrorNotificationsOptions {
  globalData: ReturnType<typeof useGlobalData>;
  notify: NotifyFn;
  phaseApiCall: ReturnType<typeof useApi<PhaseData>>['call'];
  setActiveView: Dispatch<SetStateAction<CardViewId>>;
  /**
   * Optional: invoked when an error response carries an actionable
   * payload.  Parent can render ``<ActionableError payload={...} />``.
   * Pass ``null`` to clear the page-level error when no actionable
   * error is currently active.
   */
  onActionableError?: (payload: ActionableErrorPayload | null) => void;
}

interface ToastAction {
  label: string;
  onClick: () => void;
}

/**
 * Build a toast action from a recovery_action_id (E3 actionable payload)
 * or fall back to the legacy next_action field.  Returns ``undefined``
 * when no actionable next step is available.
 */
function buildRecoveryAction(
  recoveryActionId: string | undefined,
  nextAction: string | undefined,
  label: string | undefined,
  ctx: {
    setActiveView: Dispatch<SetStateAction<CardViewId>>;
    globalData: ReturnType<typeof useGlobalData>;
    phaseApiCall: ReturnType<typeof useApi<PhaseData>>['call'];
    notify: NotifyFn;
    retryFn: () => void;
  }
): ToastAction | undefined {
  // E3: prefer recovery_action_id from the actionable payload.
  const actionId = recoveryActionId || nextAction;
  const actionLabel =
    label ||
    (recoveryActionId ? recoveryActionLabel(recoveryActionId) : null) ||
    nextActionLabel(nextAction);
  if (!actionId || !actionLabel) return undefined;

  switch (actionId) {
    case 'reconnect_session':
      return { label: actionLabel, onClick: () => ctx.setActiveView('dashboard') };
    case 'refresh_cache':
      return {
        label: actionLabel,
        onClick: () => {
          ctx.globalData.refreshAll();
          void ctx.phaseApiCall('/api/phase_state');
        },
      };
    case 'wait_and_retry':
      return {
        label: actionLabel,
        onClick: () => {
          ctx.notify('info', '5 秒后将自动重试…');
          setTimeout(() => ctx.retryFn(), 5000);
        },
      };
    case 'check_config':
      return { label: actionLabel, onClick: () => ctx.setActiveView('config') };
    case 'review_official_slots':
      return { label: actionLabel, onClick: () => ctx.setActiveView('official_backtests') };
    case 'fix_expression':
      return { label: actionLabel, onClick: () => ctx.setActiveView('candidates') };
    case 'resume_or_restart':
    case 'restart_flow':
      return { label: actionLabel, onClick: () => ctx.setActiveView('dashboard') };
    default:
      return { label: actionLabel, onClick: () => ctx.retryFn() };
  }
}

export function useErrorNotifications({
  globalData,
  notify,
  phaseApiCall,
  setActiveView,
  onActionableError,
}: ErrorNotificationsOptions): void {
  const lastCandidatesErrorRef = useRef<string>('');
  const lastSlotsErrorRef = useRef<string>('');
  const lastCloudErrorRef = useRef<string>('');
  const lastConfigErrorRef = useRef<string>('');

  const buildAction = useCallback(
    (meta: ApiMeta | null, retryFn: () => void): ToastAction | undefined => {
      const actionable = meta?.actionable;
      const recoveryActionId = actionable?.recovery_action_id;
      const nextAction = meta?.user_error?.next_action || meta?.next_action;
      const label = meta?.user_error?.action_label;
      return buildRecoveryAction(recoveryActionId, nextAction, label, {
        setActiveView,
        globalData,
        phaseApiCall,
        notify,
        retryFn,
      });
    },
    [globalData, phaseApiCall, notify, setActiveView]
  );

  /**
   * Build the toast message for an error.  When the backend attached
   * an actionable payload, prefer its cause (more user-friendly than
   * the raw error string); otherwise fall back to safeDisplayErrorMessage.
   */
  const buildToastMessage = useCallback(
    (prefix: string, rawError: string, meta: ApiMeta | null): string => {
      const actionable = meta?.actionable;
      if (actionable && isActionableErrorPayload(actionable) && actionable.cause) {
        return `${prefix}: ${actionable.cause}`;
      }
      return `${prefix}: ${safeDisplayErrorMessage(rawError)}`;
    },
    []
  );

  // Surface the actionable payload to the parent for page-level rendering.
  const surfaceActionable = useCallback(
    (meta: ApiMeta | null) => {
      if (!onActionableError) return;
      const actionable = meta?.actionable;
      if (actionable && isActionableErrorPayload(actionable)) {
        onActionableError(actionable);
      }
    },
    [onActionableError]
  );

  useEffect(() => {
    const gd = globalData;
    if (gd.candidates.error && gd.candidates.error !== lastCandidatesErrorRef.current) {
      lastCandidatesErrorRef.current = gd.candidates.error;
      surfaceActionable(gd.candidates.lastErrorMeta);
      notify(
        'warning',
        buildToastMessage('候选数据加载失败', gd.candidates.error, gd.candidates.lastErrorMeta),
        buildAction(gd.candidates.lastErrorMeta, () => {
          gd.refreshAll();
        })
      );
    }
    if (gd.slots.error && gd.slots.error !== lastSlotsErrorRef.current) {
      lastSlotsErrorRef.current = gd.slots.error;
      surfaceActionable(gd.slots.lastErrorMeta);
      notify(
        'warning',
        buildToastMessage('回测槽位加载失败', gd.slots.error, gd.slots.lastErrorMeta),
        buildAction(gd.slots.lastErrorMeta, () => {
          gd.refreshAll();
        })
      );
    }
    if (gd.cloud.error && gd.cloud.error !== lastCloudErrorRef.current) {
      lastCloudErrorRef.current = gd.cloud.error;
      surfaceActionable(gd.cloud.lastErrorMeta);
      notify(
        'warning',
        buildToastMessage('云端快照加载失败', gd.cloud.error, gd.cloud.lastErrorMeta),
        buildAction(gd.cloud.lastErrorMeta, () => {
          gd.refreshAll();
        })
      );
    }
    if (gd.config.error && gd.config.error !== lastConfigErrorRef.current) {
      lastConfigErrorRef.current = gd.config.error;
      surfaceActionable(gd.config.lastErrorMeta);
      notify(
        'warning',
        buildToastMessage('配置状态加载失败', gd.config.error, gd.config.lastErrorMeta),
        buildAction(gd.config.lastErrorMeta, () => {
          gd.refreshAll();
        })
      );
    }
  }, [globalData, notify, buildAction, buildToastMessage, surfaceActionable]);
}

// ──────────────────────────────────────────────────────────────────────────
// usePhaseManagement
// ──────────────────────────────────────────────────────────────────────────

export interface PhaseManagementOptions {
  connected: boolean;
  contextFresh: boolean;
  candidatesCount: number;
  scoredCount: number;
  readinessPassed: boolean;
  activeView: CardViewId;
  phaseApiStatus: PhaseApiStatus;
  expandedPhases: Set<string>;
  setExpandedPhases: Dispatch<SetStateAction<Set<string>>>;
  setActiveView: Dispatch<SetStateAction<CardViewId>>;
}

export interface PhaseManagementResult {
  phaseState: ReturnType<typeof usePhaseState>['phaseState'];
  steps: ReturnType<typeof usePhaseState>['steps'];
  currentPhase: PhaseId;
  sidebarPhases: PhaseGroup[];
  handleTogglePhase: (phaseId: string) => void;
  handleMobileNavigate: (target: PhaseId | 'tools') => void;
}

export function usePhaseManagement({
  connected,
  contextFresh,
  candidatesCount,
  scoredCount,
  readinessPassed,
  activeView,
  phaseApiStatus,
  expandedPhases,
  setExpandedPhases,
  setActiveView,
}: PhaseManagementOptions): PhaseManagementResult {
  const { phaseState, steps, currentPhase } = usePhaseState({
    connected,
    contextFresh,
    candidatesCount,
    scoredCount,
    readinessPassed,
    activeView,
    phaseStatus: phaseApiStatus,
  });

  useEffect(() => {
    setExpandedPhases((prev) => {
      const next = new Set(prev);
      next.add(currentPhase);
      return next;
    });
  }, [currentPhase, setExpandedPhases]);

  const handleTogglePhase = useCallback(
    (phaseId: string) => {
      setExpandedPhases((prev) => {
        const next = new Set(prev);
        if (next.has(phaseId)) next.delete(phaseId);
        else next.add(phaseId);
        return next;
      });
    },
    [setExpandedPhases]
  );

  const sidebarPhases = useMemo(() => {
    return Object.values(phaseState.phases).map((pg) => ({
      ...pg,
      expanded: expandedPhases.has(pg.id),
    }));
  }, [phaseState.phases, expandedPhases]);

  const handleMobileNavigate = useCallback(
    (target: PhaseId | 'tools') => {
      if (target === 'tools') {
        setActiveView('dashboard');
      } else {
        const phase = phaseState.phases[target];
        if (phase && phase.items.length > 0) {
          setActiveView(phase.items[0].id);
        }
      }
    },
    [phaseState.phases, setActiveView]
  );

  return {
    phaseState,
    steps,
    currentPhase,
    sidebarPhases,
    handleTogglePhase,
    handleMobileNavigate,
  };
}

// ──────────────────────────────────────────────────────────────────────────
// useHandlers
// ──────────────────────────────────────────────────────────────────────────

export interface HandlersOptions {
  setActiveView: Dispatch<SetStateAction<CardViewId>>;
  setSelectedCandidate: Dispatch<SetStateAction<Candidate | null>>;
  setOfficialOpsAutoStart: Dispatch<SetStateAction<boolean>>;
  phaseApiCall: ReturnType<typeof useApi<PhaseData>>['call'];
  globalData: ReturnType<typeof useGlobalData>;
}

export interface HandlersResult {
  handleNavigate: (view: CardViewId) => void;
  handleDashboardSyncStart: () => void;
  handleDashboardSyncOpen: () => void;
  handleOfficialSyncCompleted: () => void;
  handleOfficialReconnectRequested: () => void;
  handleCandidatePoolUpdated: () => void;
  openScoring: (candidate: Candidate) => void;
}

export function useHandlers({
  setActiveView,
  setSelectedCandidate,
  setOfficialOpsAutoStart,
  phaseApiCall,
  globalData,
}: HandlersOptions): HandlersResult {
  const handleNavigate = useCallback(
    (view: CardViewId) => {
      setActiveView(view);
    },
    [setActiveView]
  );

  const handleDashboardSyncStart = useCallback(() => {
    setOfficialOpsAutoStart(true);
    setActiveView('official_operations');
  }, [setOfficialOpsAutoStart, setActiveView]);

  const handleDashboardSyncOpen = useCallback(() => {
    setOfficialOpsAutoStart(false);
    setActiveView('official_operations');
  }, [setOfficialOpsAutoStart, setActiveView]);

  const handleOfficialSyncCompleted = useCallback(() => {
    void phaseApiCall('/api/phase_state');
    globalData.refreshAll();
  }, [phaseApiCall, globalData]);

  const handleOfficialReconnectRequested = useCallback(() => {
    setActiveView('dashboard');
  }, [setActiveView]);

  const handleCandidatePoolUpdated = useCallback(() => {
    globalData.refreshAll();
    void phaseApiCall('/api/phase_state');
  }, [phaseApiCall, globalData]);

  const openScoring = useCallback(
    (candidate: Candidate) => {
      setSelectedCandidate(candidate);
      setActiveView('scoring');
    },
    [setSelectedCandidate, setActiveView]
  );

  return {
    handleNavigate,
    handleDashboardSyncStart,
    handleDashboardSyncOpen,
    handleOfficialSyncCompleted,
    handleOfficialReconnectRequested,
    handleCandidatePoolUpdated,
    openScoring,
  };
}
