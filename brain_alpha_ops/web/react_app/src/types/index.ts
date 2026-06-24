/** Core TypeScript type definitions for the BRAIN Alpha Ops web console. */

import type { SSECandidateEventData } from "./api";

export * from "./api";
export * from "./scoring";
export * from "./candidate";
export * from "./config";
export * from "./cloud";
export * from "./ui";

// ── Type Guards ──────────────────────────────────────────────────────────

/** Narrow unknown JSON to a plain object (not null, not array). */
export function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

/** Narrow SSE event.data to SSECandidateEventData. */
export function isSSECandidateData(data: unknown): data is SSECandidateEventData {
  return isRecord(data);
}
