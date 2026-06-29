/**
 * useBaseState — foundational UI state, toasts, job & global data.
 *
 * Owns the primitive useState hooks, the toast/notify layer, and
 * wires `useJobState` + `useGlobalData` which depend on `notify`/`credentials`.
 */

import { useState, useCallback, useEffect, useRef } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import type { BrainCredentials, Candidate, CardViewId } from '@/types';
import { useToast } from '@/hooks/useToast';
import { useJobState } from '@/hooks/useJobState';
import { useGlobalData } from '@/hooks/useGlobalData';

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

function readViewFromHash(): CardViewId {
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

  /** Wrap setActiveView so it also syncs the URL hash. */
  const setActiveView = useCallback((view: CardViewId | ((prev: CardViewId) => CardViewId)) => {
    setActiveViewRaw((prev) => {
      const next = typeof view === 'function' ? view(prev) : view;
      activeViewRef.current = next;
      window.location.hash = next;
      return next;
    });
  }, []);

  /** Respond to external hash changes (browser back/forward, manual edit). */
  useEffect(() => {
    const onHashChange = () => {
      const view = readViewFromHash();
      if (view !== activeViewRef.current) {
        activeViewRef.current = view;
        setActiveViewRaw(view);
      }
    };
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
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
