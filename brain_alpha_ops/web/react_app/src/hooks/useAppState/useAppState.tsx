/**
 * useAppState — App-level state management hook (composition root) +
 * AppStateContext (React Context Provider for the unified app state machine).
 *
 * Centralizes all core application state and logic that was previously in App.tsx.
 * This keeps App.tsx focused on rendering and layout.
 *
 * Sub-hooks (in useAppStateState.ts / useAppStateEffects.ts):
 *   - useBaseState          primitive UI state, toasts, job & global data
 *   - usePhaseConnection    phase polling, connection flags, session handlers
 *   - useErrorNotifications globalData error → toast bridging
 *   - usePhaseManagement    phase derivation, sidebar groups, mobile nav
 *   - useHandlers           navigation / sync / scoring handlers
 *
 * Workstream E2.1: eliminates prop-drilling state drift by exposing the
 * `AppState` produced by the `useAppState()` composition root through a
 * React Context. New code SHOULD consume state via `useAppStateContext()`
 * instead of receiving `viewProps` props; legacy page components may keep
 * their existing prop interfaces for backward compatibility.
 *
 * Provider placement: wraps the app once inside `App.tsx`. The composition
 * hook is invoked exactly once per app instance (was previously called
 * directly in `App.tsx`).
 */

import { createContext, useContext, type ReactNode } from 'react';
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts';
import { formatBacktestBadge, formatCloudBadge, cloudBadgeTotal } from '@/components/views/helpers';
import { useBaseState, type AppState, type SidebarBadges } from './useAppStateState';
import {
  usePhaseConnection,
  useErrorNotifications,
  usePhaseManagement,
  useHandlers,
} from './useAppStateEffects';

export type { AppState } from './useAppStateState';

export function useAppState(): AppState {
  const {
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
  } = useBaseState();

  const {
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
  } = usePhaseConnection({ setCredentials, globalData });

  useErrorNotifications({
    globalData,
    notify,
    phaseApiCall: phaseApi.call,
    setActiveView,
  });

  const {
    phaseState,
    steps,
    currentPhase,
    sidebarPhases,
    handleTogglePhase,
    handleMobileNavigate,
  } = usePhaseManagement({
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
  });

  const {
    handleNavigate,
    handleDashboardSyncStart,
    handleDashboardSyncOpen,
    handleOfficialSyncCompleted,
    handleOfficialReconnectRequested,
    handleCandidatePoolUpdated,
    openScoring,
  } = useHandlers({
    setActiveView,
    setSelectedCandidate,
    setOfficialOpsAutoStart,
    phaseApiCall: phaseApi.call,
    globalData,
  });

  useKeyboardShortcuts({
    onNavigateToDashboard: () => setActiveView('dashboard'),
    onNavigateToConfig: () => setActiveView('config'),
    onRefresh: () => {
      void phaseApi.call('/api/phase_state');
      globalData.refreshAll();
    },
    onShowHelp: () => setShortcutsHelpOpen(true),
    onEscape: () => {
      setSidebarOpen(false);
      setShortcutsHelpOpen(false);
    },
  });

  const sidebarBadges: SidebarBadges = {
    candidates: globalData.candidates.data?.total ?? globalData.candidates.data?.candidates?.length,
    official_backtests: globalData.slots.data
      ? formatBacktestBadge(globalData.slots.data)
      : undefined,
    cloud: globalData.cloud.data
      ? formatCloudBadge(cloudBadgeTotal(globalData.cloud.data))
      : undefined,
  };

  return {
    activeView,
    selectedCandidate,
    credentials,
    sidebarOpen,
    expandedPhases,
    shortcutsHelpOpen,
    connectionOverride,
    connectionError,
    officialOpsAutoStart,
    toasts,
    notify,
    dismissToast,
    jobState,
    globalData,
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
    phaseState,
    steps,
    currentPhase,
    sidebarPhases,
    sidebarBadges,
    setActiveView,
    setSelectedCandidate,
    setCredentials,
    setSidebarOpen,
    setExpandedPhases,
    setShortcutsHelpOpen,
    setOfficialOpsAutoStart,
    handleTogglePhase,
    handleNavigate,
    handleConnectionTested,
    handleDashboardSyncStart,
    handleDashboardSyncOpen,
    handleOfficialSyncCompleted,
    handleOfficialReconnectRequested,
    handleCandidatePoolUpdated,
    handleLocalSessionLoggedOut,
    handleMobileNavigate,
    openScoring,
  };
}

// ──────────────────────────────────────────────────────────────────────────
// AppStateContext — React Context Provider for the unified app state machine
// ──────────────────────────────────────────────────────────────────────────

/**
 * Context carrying the unified app state. `null` when consumed outside the
 * provider — `useAppStateContext()` throws in that case.
 */
export const AppStateContext = createContext<AppState | null>(null);

// Optional display name for React DevTools.
AppStateContext.displayName = 'AppStateContext';

export interface AppStateProviderProps {
  children: ReactNode;
}

/**
 * Provider component that owns the single `useAppState()` invocation and
 * exposes its return value via `AppStateContext`.
 *
 * Wrap the app once, near the root. Inside the provider, any component
 * can read the unified state via `useAppStateContext()`.
 */
export function AppStateProvider({ children }: AppStateProviderProps): JSX.Element {
  const appState = useAppState();
  return <AppStateContext.Provider value={appState}>{children}</AppStateContext.Provider>;
}

/**
 * Consumer hook for the unified app state.
 *
 * Throws a descriptive error when used outside of `<AppStateProvider>` to
 * surface mis-placed consumers immediately during development instead of
 * silently returning `null` and crashing downstream.
 */
export function useAppStateContext(): AppState {
  const ctx = useContext(AppStateContext);
  if (ctx === null) {
    throw new Error(
      'useAppStateContext() must be used inside <AppStateProvider>. ' +
        'Wrap the app root (or the relevant subtree) with <AppStateProvider> ' +
        'before consuming app state via context.'
    );
  }
  return ctx;
}

/**
 * Non-throwing variant for components that can render meaningfully before
 * the provider is mounted (e.g. static preview surfaces, storybook).
 * Returns `null` when no provider is present; callers must narrow.
 */
export function useOptionalAppStateContext(): AppState | null {
  return useContext(AppStateContext);
}
