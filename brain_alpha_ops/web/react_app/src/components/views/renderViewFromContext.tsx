/**
 * ActiveViewRenderer — context-based renderer component (Workstream E2.1).
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
 *
 * W-007: previously a render function that called hooks (rules-of-hooks
 * violation suppressed via eslint-disable). Promoted to a standard component
 * so hook invocation is valid and no eslint-disable is needed.
 */

import type { RenderViewProps } from './renderView';
import { renderActiveView } from './renderView';
import { useAppStateContext } from '@/hooks/useAppState/useAppState';

/**
 * Preferred renderer component. Reads the unified app state from context
 * and renders the active view's React node.
 */
export function ActiveViewRenderer() {
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
