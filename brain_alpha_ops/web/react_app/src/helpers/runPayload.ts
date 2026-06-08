/** Shared helpers for job monitoring — used by both useJobState hook and JobMonitor component */

import type { BrainCredentials, JobStatus } from "@/types";

/** Check if credentials are filled in.
 *  NOTE: Uses `||` semantics — filling only the password field without username is NOT considered "having credentials".
 *  This is intentional: the BRAIN API requires at minimum a username (email). */
export function hasCredentials(credentials?: BrainCredentials): boolean {
  return Boolean(credentials?.username?.trim() || credentials?.password || credentials?.token?.trim());
}

/** Check if job status is in a terminal (completed) state */
export function isTerminalStatus(status: string | undefined): boolean {
  return ["completed", "completed_with_warnings", "failed", "stopped", "cancelled", "canceled"]
    .includes(String(status || "").toLowerCase());
}

/** Build the request payload for /api/run */
export function buildRunPayload(resume: boolean, credentials?: BrainCredentials): Record<string, string | boolean> {
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
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  return typeof v.status === "string" || typeof v.job_id === "string" || typeof v.phase === "string";
}

/** Extract jobId from an API response with various possible shapes */
export function extractJobId(result: unknown): string {
  if (!result || typeof result !== "object") return "";
  const r = result as Record<string, unknown>;
  return String(r.job_id || r.task_id || "");
}

/** Format a validation ID for compact display */
export function shortValidationId(value: string): string {
  const text = String(value || "").trim();
  return text.length <= 12 ? text : `${text.slice(0, 6)}...${text.slice(-4)}`;
}
