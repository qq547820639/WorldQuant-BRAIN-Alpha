/**
 * Generic application utilities: CSRF/request metadata, localStorage-backed
 * state persistence, debounce/throttle timing, and backtest-slot math.
 *
 * Merged from former `csrf.ts`, `resumeState.ts`, `starredCandidates.ts`,
 * `debounce.ts`, and `backtestSlots.ts`.
 */

import { reportIgnoredError } from './errors';
import type { BacktestSlotsResponse } from '@/types';

// ──────────────────────────────────────────────────────────────────────────
// CSRF / request metadata (former csrf.ts)
// ──────────────────────────────────────────────────────────────────────────

/** Read CSRF token from <meta> tag injected by the server. */
export function csrfToken(): string {
  const meta = document.querySelector<HTMLMetaElement>('meta[name="brain-alpha-csrf"]');
  const token = (meta?.content || '').trim();
  // Server replaces the __BRAIN_ALPHA_OPS_CSRF_TOKEN__ placeholder at serve time;
  // if the placeholder is still present the token was not properly injected.
  return token && !token.startsWith('__BRAIN_ALPHA_OPS') ? token : '';
}

export function setCsrfToken(token: string): void {
  setMetaToken('brain-alpha-csrf', token);
}

/** Read SSE stream token from <meta> tag injected by the server. */
export function streamToken(): string {
  const meta = document.querySelector<HTMLMetaElement>('meta[name="brain-alpha-stream"]');
  const token = (meta?.content || '').trim();
  return token && !token.startsWith('__BRAIN_ALPHA_OPS') ? token : '';
}

export function setStreamToken(token: string): void {
  setMetaToken('brain-alpha-stream', token);
}

/** Generate a unique request ID (crypto-based UUID if available). */
export function createRequestId(): string {
  if (window.crypto && typeof window.crypto.randomUUID === 'function') {
    return window.crypto.randomUUID();
  }
  return `req_${Date.now().toString(36)}_${Math.random().toString(36).slice(2)}`;
}

/** Build CSRF + request-ID headers for POST/PUT/PATCH/DELETE requests. */
export function csrfHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    'X-Brain-Alpha-Request-ID': createRequestId(),
    'X-Brain-Alpha-Request-Timestamp': String(Date.now()),
  };
  const token = csrfToken();
  if (token) headers['X-Brain-Alpha-CSRF'] = token;
  return headers;
}

function setMetaToken(name: string, token: string): void {
  const value = String(token || '').trim();
  if (!value) return;
  let meta = document.querySelector<HTMLMetaElement>(`meta[name="${name}"]`);
  if (!meta) {
    meta = document.createElement('meta');
    meta.name = name;
    document.head.appendChild(meta);
  }
  meta.content = value;
}

// ──────────────────────────────────────────────────────────────────────────
// Resume State — localStorage persistence for "一键恢复上次工作状态" (P0-4)
// (former resumeState.ts)
//
// Writes a minimal pipeline snapshot after key phase transitions so the user
// can resume where they left off on the next visit.
// ──────────────────────────────────────────────────────────────────────────

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

const RESUME_STORAGE_KEY = 'brain_alpha_resume_state';

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
    const raw = localStorage.getItem(RESUME_STORAGE_KEY);
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
    localStorage.setItem(RESUME_STORAGE_KEY, JSON.stringify(merged));
  } catch (err) {
    reportIgnoredError('resume state localStorage write failed', err);
  }
}

/** Remove resume state from localStorage (e.g. on first-run completion). */
export function clearResumeState(): void {
  try {
    localStorage.removeItem(RESUME_STORAGE_KEY);
  } catch (err) {
    reportIgnoredError('resume state localStorage clear failed', err);
  }
}

/** Returns true if there is a meaningful resume history (at least a past session date). */
export function hasResumeHistory(): boolean {
  const state = getResumeState();
  return Boolean(state.lastSessionDate);
}

// ──────────────────────────────────────────────────────────────────────────
// Starred candidates — LocalStorage-based favorite management
// (former starredCandidates.ts)
//
// Stores a Set of starred candidate alpha_ids in localStorage
// under the key "brain_alpha_starred_candidates".
// ──────────────────────────────────────────────────────────────────────────

const STARRED_STORAGE_KEY = 'brain_alpha_starred_candidates';

/** Read starred alpha_ids from localStorage. Returns a Set of strings. */
export function getStarred(): Set<string> {
  try {
    const raw = localStorage.getItem(STARRED_STORAGE_KEY);
    if (!raw) return new Set();
    const parsed: unknown = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return new Set(parsed.map(String).filter(Boolean));
    }
    return new Set();
  } catch {
    return new Set();
  }
}

/** Toggle the star status of an alpha_id. Returns the new starred state. */
export function toggleStar(alphaId: string): boolean {
  const starred = getStarred();
  const isCurrentlyStarred = starred.has(alphaId);
  if (isCurrentlyStarred) {
    starred.delete(alphaId);
  } else {
    starred.add(alphaId);
  }
  try {
    localStorage.setItem(STARRED_STORAGE_KEY, JSON.stringify([...starred]));
  } catch {
    console.warn('starredCandidates: localStorage full or unavailable');
  }
  return !isCurrentlyStarred;
}

/** Check if an alpha_id is starred. */
export function isStarred(alphaId: string): boolean {
  return getStarred().has(alphaId);
}

/** Get the count of starred candidates. */
export function getStarredCount(): number {
  return getStarred().size;
}

// ──────────────────────────────────────────────────────────────────────────
// Debounce / throttle (former debounce.ts)
// ──────────────────────────────────────────────────────────────────────────

/**
 * Creates a debounced version of a function that delays invoking
 * the function until after the specified delay.
 *
 * @param fn - The function to debounce
 * @param delay - The delay in milliseconds (default: 300)
 * @returns A debounced version of the function
 */
export function debounce<T extends (...args: Parameters<T>) => ReturnType<T>>(
  fn: T,
  delay: number = 300
): (...args: Parameters<T>) => void {
  let timeoutId: ReturnType<typeof setTimeout> | null = null;

  return function (...args: Parameters<T>) {
    if (timeoutId) {
      clearTimeout(timeoutId);
    }

    timeoutId = setTimeout(() => {
      fn(...args);
      timeoutId = null;
    }, delay);
  };
}

/**
 * Creates a throttled version of a function that only invokes
 * the function at most once per specified delay.
 *
 * @param fn - The function to throttle
 * @param limit - The time limit in milliseconds (default: 300)
 * @returns A throttled version of the function
 */
export function throttle<T extends (...args: Parameters<T>) => ReturnType<T>>(
  fn: T,
  limit: number = 300
): (...args: Parameters<T>) => void {
  let inThrottle = false;

  return function (...args: Parameters<T>) {
    if (!inThrottle) {
      fn(...args);
      inThrottle = true;
      setTimeout(() => {
        inThrottle = false;
      }, limit);
    }
  };
}

/**
 * Cleans up any pending timeout (useful for cleanup in useEffect)
 * @param timeoutId - The timeout ID to clear
 */
export function clearDebounce(timeoutId: ReturnType<typeof setTimeout> | null): void {
  if (timeoutId) {
    clearTimeout(timeoutId);
  }
}

// ──────────────────────────────────────────────────────────────────────────
// Backtest slot helpers (former backtestSlots.ts)
// ──────────────────────────────────────────────────────────────────────────

export const ACTIVE_BACKTEST_SLOT_STATUSES = new Set([
  'SUBMITTED',
  'RUNNING',
  'PENDING',
  'STARTING',
  'RATE_LIMITED',
  'POLL_ERROR',
  'CAPACITY_WAIT',
]);

export function isActiveBacktestSlotStatus(status: unknown) {
  const text = String((status as string | number | boolean | null | undefined) || '').toUpperCase();
  return ACTIVE_BACKTEST_SLOT_STATUSES.has(text);
}

export function backtestSlotLimit(
  payload: Pick<BacktestSlotsResponse, 'slot_limit' | 'queue_summary'> | null | undefined,
  fallback = 3
) {
  const fromPayload = Number(payload?.slot_limit);
  const fromSummary = Number(payload?.queue_summary?.slot_limit);
  const value = Number.isFinite(fromPayload) && fromPayload > 0 ? fromPayload : fromSummary;
  if (Number.isFinite(value) && value > 0) return Math.max(3, Math.trunc(value));
  return Math.max(0, Math.trunc(fallback));
}

export function backtestActiveCount(
  payload: Pick<BacktestSlotsResponse, 'active_count' | 'slots'> | null | undefined
) {
  const fromPayload = Number(payload?.active_count);
  if (Number.isFinite(fromPayload) && fromPayload >= 0) return Math.trunc(fromPayload);
  const slots = Array.isArray(payload?.slots) ? payload.slots : [];
  return slots.filter((slot) => isActiveBacktestSlotStatus(slot.status)).length;
}
