/**
 * AppStateContext — React Context Provider for the unified app state machine.
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
import { useAppState } from './index';
import type { AppState } from './types';

// Re-export the type so consumers can `import type { AppState }` from here
// without reaching into `./types` directly.
export type { AppState } from './types';

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
  return (
    <AppStateContext.Provider value={appState}>{children}</AppStateContext.Provider>
  );
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
