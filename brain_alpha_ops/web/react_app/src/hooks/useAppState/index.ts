/**
 * useAppState — App-level state management hook (composition root).
 *
 * Centralizes all core application state and logic that was previously in App.tsx.
 * This keeps App.tsx focused on rendering and layout.
 *
 * Sub-hooks:
 *   - useBaseState          primitive UI state, toasts, job & global data
 *   - usePhaseConnection    phase polling, connection flags, session handlers
 *   - useErrorNotifications globalData error → toast bridging
 *   - usePhaseManagement    phase derivation, sidebar groups, mobile nav
 *   - useHandlers           navigation / sync / scoring handlers
 */

import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts';
import { formatBacktestBadge, formatCloudBadge, cloudBadgeTotal } from '@/components/views/helpers';
import { useBaseState } from './useBaseState';
import { usePhaseConnection } from './usePhaseConnection';
import { useErrorNotifications } from './useErrorNotifications';
import { usePhaseManagement } from './usePhaseManagement';
import { useHandlers } from './useHandlers';
import type { AppState, SidebarBadges } from './types';

export type { AppState } from './types';

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
