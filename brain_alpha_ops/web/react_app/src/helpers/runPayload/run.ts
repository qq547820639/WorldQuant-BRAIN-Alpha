/** Run payload construction and miscellaneous job helpers. */

import { isRecord, type BrainCredentials, type JobStatus } from '@/types';

/** Check if credentials are filled in.
 *  P1-13 fix: the original `||` chain actually made password-only count as
 *  "having credentials" (contrary to the comment).  Switched to explicit
 *  AND for username+password so the BRAIN API (which requires at minimum a
 *  username) rejects password-only entries.  Token-only auth is still
 *  supported as an alternative to username+password. */
export function hasCredentials(credentials?: BrainCredentials): boolean {
  return Boolean(
    (credentials?.username?.trim() && credentials?.password) || credentials?.token?.trim()
  );
}

/** Build the request payload for /api/run */
export function buildRunPayload(
  resume: boolean,
  credentials?: BrainCredentials
): Record<string, string | boolean> {
  const payload: Record<string, string | boolean> = resume
    ? { resume: true, autoSubmit: false, auto_submit: false }
    : { autoSubmit: false, auto_submit: false };
  if (credentials?.username?.trim()) payload.username = credentials.username.trim();
  if (credentials?.password) payload.password = credentials.password;
  if (credentials?.token?.trim()) payload.token = credentials.token.trim();
  return payload;
}

/** Type guard: check if an unknown value is a valid JobStatus */
export function isJobStatus(value: unknown): value is JobStatus {
  if (!isRecord(value)) return false;
  return (
    typeof value.status === 'string' ||
    typeof value.job_id === 'string' ||
    typeof value.phase === 'string'
  );
}

/** Extract jobId from an API response with various possible shapes */
export function extractJobId(result: unknown): string {
  if (!isRecord(result)) return '';
  const raw = (result.job_id || result.task_id) as string | number | boolean | null | undefined;
  return String(raw || '');
}

/** Format a validation ID for compact display */
export function shortValidationId(value: string): string {
  const text = String(value || '').trim();
  return text.length <= 12 ? text : `${text.slice(0, 6)}...${text.slice(-4)}`;
}
