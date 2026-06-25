/**
 * useBaseState — foundational UI state, toasts, job & global data.
 *
 * Owns the primitive useState hooks, the toast/notify layer, and
 * wires `useJobState` + `useGlobalData` which depend on `notify`/`credentials`.
 */

import { useState, useCallback } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import type { BrainCredentials, Candidate, CardViewId } from '@/types';
import { useToast } from '@/hooks/useToast';
import { useJobState } from '@/hooks/useJobState';
import { useGlobalData } from '@/hooks/useGlobalData';

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
  const [activeView, setActiveView] = useState<CardViewId>('dashboard');
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
