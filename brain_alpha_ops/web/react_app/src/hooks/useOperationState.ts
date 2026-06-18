/** Unified operation state management for CandidateTable actions. */

import { useState, useCallback } from "react";

export type OperationState = "idle" | "loading" | "progress" | "success" | "error";

export interface OperationStateEntry {
  state: OperationState;
  error: string | null;
}

export interface UseOperationStateReturn {
  get: (key: string) => OperationStateEntry;
  setIdle: (key: string) => void;
  setLoading: (key: string) => void;
  setProgress: (key: string) => void;
  setSuccess: (key: string) => void;
  setError: (key: string, error: string) => void;
  isBusy: (key: string) => boolean;
  anyBusy: () => boolean;
}

const INITIAL_STATE: OperationStateEntry = { state: "idle", error: null };

export function useOperationState(keys: string[]): UseOperationStateReturn {
  const [states, setStates] = useState<Record<string, OperationStateEntry>>(() => {
    const initial: Record<string, OperationStateEntry> = {};
    for (const key of keys) {
      initial[key] = { ...INITIAL_STATE };
    }
    return initial;
  });

  const get = useCallback((key: string) => states[key] || INITIAL_STATE, [states]);

  const setIdle = useCallback((key: string) => {
    setStates((prev) => ({ ...prev, [key]: { state: "idle", error: null } }));
  }, []);

  const setLoading = useCallback((key: string) => {
    setStates((prev) => ({ ...prev, [key]: { state: "loading", error: null } }));
  }, []);

  const setProgress = useCallback((key: string) => {
    setStates((prev) => ({ ...prev, [key]: { state: "progress", error: null } }));
  }, []);

  const setSuccess = useCallback((key: string) => {
    setStates((prev) => ({ ...prev, [key]: { state: "success", error: null } }));
  }, []);

  const setError = useCallback((key: string, error: string) => {
    setStates((prev) => ({ ...prev, [key]: { state: "error", error } }));
  }, []);

  const isBusy = useCallback((key: string) => {
    const s = states[key]?.state;
    return s === "loading" || s === "progress";
  }, [states]);

  const anyBusy = useCallback(() => {
    return Object.values(states).some((s) => s.state === "loading" || s.state === "progress");
  }, [states]);

  return { get, setIdle, setLoading, setProgress, setSuccess, setError, isBusy, anyBusy };
}
