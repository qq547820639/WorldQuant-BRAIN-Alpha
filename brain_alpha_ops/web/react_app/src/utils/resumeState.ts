/**
 * Resume State — localStorage persistence for "一键恢复上次工作状态" (P0-4).
 *
 * Writes a minimal pipeline snapshot after key phase transitions so the user
 * can resume where they left off on the next visit.
 */

import { reportIgnoredError } from '@/utils/reportIgnoredError';

// ── Types ──────────────────────────────────────────────────────────────────

export interface ResumeState {
  /** ISO date string of the last session. */
  lastSessionDate: string;
  /** Last known phase: connect | discover | evaluate | ready */
  lastPhase: string;
  /** Job ID of the last pipeline run. */
  lastPipelineJob: string | null;
  /** Candidate pool size at last save. */
  lastPoolSize: number;
  /** ISO timestamp of the last successful sync. */
  lastSyncTime: string | null;
  /** Whether the BRAIN connection was healthy at last check. */
  lastConnectionOk: boolean;
  /** Last error message (cleared on success). */
  lastError: string | null;
  /** Total production-validation cycles completed. */
  totalCyclesCompleted: number;
}

// ── Constants ──────────────────────────────────────────────────────────────

const STORAGE_KEY = 'brain_alpha_resume_state';

const DEFAULT_STATE: ResumeState = {
  lastSessionDate: '',
  lastPhase: 'connect',
  lastPipelineJob: null,
  lastPoolSize: 0,
  lastSyncTime: null,
  lastConnectionOk: false,
  lastError: null,
  totalCyclesCompleted: 0,
};

// ── Public API ─────────────────────────────────────────────────────────────

/** Read the current resume state from localStorage. Returns defaults for missing fields. */
export function getResumeState(): ResumeState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULT_STATE };
    const parsed = JSON.parse(raw) as Partial<ResumeState>;
    return {
      lastSessionDate:
        typeof parsed.lastSessionDate === 'string'
          ? parsed.lastSessionDate
          : DEFAULT_STATE.lastSessionDate,
      lastPhase: typeof parsed.lastPhase === 'string' ? parsed.lastPhase : DEFAULT_STATE.lastPhase,
      lastPipelineJob:
        typeof parsed.lastPipelineJob === 'string'
          ? parsed.lastPipelineJob
          : DEFAULT_STATE.lastPipelineJob,
      lastPoolSize:
        typeof parsed.lastPoolSize === 'number' && Number.isFinite(parsed.lastPoolSize)
          ? parsed.lastPoolSize
          : DEFAULT_STATE.lastPoolSize,
      lastSyncTime:
        typeof parsed.lastSyncTime === 'string' ? parsed.lastSyncTime : DEFAULT_STATE.lastSyncTime,
      lastConnectionOk:
        typeof parsed.lastConnectionOk === 'boolean'
          ? parsed.lastConnectionOk
          : DEFAULT_STATE.lastConnectionOk,
      lastError: typeof parsed.lastError === 'string' ? parsed.lastError : DEFAULT_STATE.lastError,
      totalCyclesCompleted:
        typeof parsed.totalCyclesCompleted === 'number' &&
        Number.isFinite(parsed.totalCyclesCompleted)
          ? parsed.totalCyclesCompleted
          : DEFAULT_STATE.totalCyclesCompleted,
    };
  } catch (err) {
    reportIgnoredError('resume state localStorage read failed', err);
    return { ...DEFAULT_STATE };
  }
}

/**
 * Merge partial state into the existing resume state and persist to localStorage.
 *
 * Usage:
 *   saveResumeState({ lastPhase: "discover", lastPoolSize: 42 });
 *   saveResumeState({ lastError: "sync failed", lastConnectionOk: false });
 */
export function saveResumeState(partial: Partial<ResumeState>): void {
  try {
    const current = getResumeState();
    const merged: ResumeState = {
      ...current,
      ...partial,
      // Always bump session date when saving
      lastSessionDate: new Date().toISOString(),
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(merged));
  } catch (err) {
    reportIgnoredError('resume state localStorage write failed', err);
  }
}

/** Remove resume state from localStorage (e.g. on first-run completion). */
export function clearResumeState(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch (err) {
    reportIgnoredError('resume state localStorage clear failed', err);
  }
}

/** Returns true if there is a meaningful resume history (at least a past session date). */
export function hasResumeHistory(): boolean {
  const state = getResumeState();
  return Boolean(state.lastSessionDate);
}
