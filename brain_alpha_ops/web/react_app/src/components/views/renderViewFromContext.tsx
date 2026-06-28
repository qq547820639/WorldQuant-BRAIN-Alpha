/**
 * renderViewFromContext — context-based renderer entry point (Workstream E2.1).
 *
 * Sibling to `renderView.tsx`. Consumes the unified app state from
 * `AppStateContext` and builds the legacy `RenderViewProps` shape internally,
 * then delegates to `renderActiveView()`. This eliminates the prop-drilling
 * from `App.tsx` that previously caused state drift between panels.
 *
 * Lives in a separate file from `renderView.tsx` only because `renderView.tsx`
 * is at the 400-line project limit and cannot grow further without violating
 * the hard size constraint. New page components can additionally read
 * directly from `useAppStateContext()` to opt out of the legacy prop
 * interface entirely.
 *
 * Must be rendered inside `<AppStateProvider>` (throws otherwise).
 */

import type React from 'react';
import { useAppStateContext } from '@/hooks/useAppState/AppStateContext';
import { renderActiveView, type RenderViewProps } from './renderView';

/**
 * Preferred renderer entry point. Reads the unified app state from context
 * and returns the active view's React node.
 */
export function renderActiveViewFromContext(): React.ReactNode {
  // eslint-disable-next-line react-hooks/rules-of-hooks -- render function invoked during a component's render phase; hook context is valid at runtime.
  const appState = useAppStateContext();
  const viewProps: RenderViewProps = {
    activeView: appState.activeView,
    selectedCandidate: appState.selectedCandidate,
    credentials: appState.credentials,
    notify: appState.notify,
    connected: appState.connected,
    contextFresh: appState.contextFresh,
    phaseApiStatus: appState.phaseApiStatus,
    managedCredentialsAvailable: appState.managedCredentialsAvailable,
    officialOpsAutoStart: appState.officialOpsAutoStart,
    jobState: appState.jobState,
    onOpenScoring: appState.openScoring,
    onNavigate: appState.handleNavigate,
    onConnectionTested: appState.handleConnectionTested,
    onCredentialsChange: appState.setCredentials,
    onDashboardSyncStart: appState.handleDashboardSyncStart,
    onDashboardSyncOpen: appState.handleDashboardSyncOpen,
    onOfficialSyncCompleted: appState.handleOfficialSyncCompleted,
    onOfficialReconnectRequested: appState.handleOfficialReconnectRequested,
    onCandidatePoolUpdated: appState.handleCandidatePoolUpdated,
    onLocalSessionLoggedOut: appState.handleLocalSessionLoggedOut,
    onAutoStartConsumed: () => appState.setOfficialOpsAutoStart(false),
    phaseData: appState.phaseData,
  };
  return renderActiveView(viewProps);
}
