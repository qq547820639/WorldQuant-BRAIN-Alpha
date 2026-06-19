/** Generic fetch hook with loading/error state management. */

import { useState, useCallback } from "react";
import { apiErrorMessage, isSessionInvalidPayload, networkErrorMessage } from "@/helpers/errorExperience";
import { csrfHeaders, csrfToken, setCsrfToken, setStreamToken } from "@/utils/csrf";
import { saveResumeState } from "@/utils/resumeState";

// P2-22 fix: raised from 120s to 600s (10 min) because BRAIN
// sync/simulate operations routinely take several minutes.
const DEFAULT_REQUEST_TIMEOUT_MS = 600000;

/** Minimal API response envelope shared by all endpoints. */
export type ApiMeta = {
  ok: boolean;
  error?: string;
  error_code?: string;
  user_error?: {
    kind?: string;
    title?: string;
    message?: string;
    impact?: string;
    suggested_action?: string;
    action_label?: string;
    next_action?: string;
    severity?: string;
    recoverable?: boolean;
    retryable?: boolean;
    detail?: string;
  };
  user_error_kind?: string;
  user_message?: string;
  next_action?: string;
  recoverable?: boolean;
  retryable?: boolean;
  status_kind?: string;
  terminal?: boolean;
  interrupted?: boolean;
};

interface UseApiState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  /** P1-4: metadata from the last error response (next_action, recoverable, etc.) */
  lastErrorMeta: ApiMeta | null;
}

export function useApi<T = unknown>() {
  const [state, setState] = useState<UseApiState<T>>({
    data: null,
    loading: false,
    error: null,
    lastErrorMeta: null,
  });

  // NOTE: call<R> returns R & ApiMeta (not ApiResponse<R>) so callers can
  // access endpoint-specific fields like task_id / job_id / candidates without
  // going through .data, matching the flat JSON shape the backend returns.
  const call = useCallback(
    async <R = T>(url: string, options?: RequestInit): Promise<(R & ApiMeta) | null> => {
      setState((prev) => ({ ...prev, loading: true, error: null, lastErrorMeta: null }));
      let controller: AbortController | null = options?.signal ? null : new AbortController();
      let timeout: number | null = controller
        ? window.setTimeout(() => controller!.abort(), DEFAULT_REQUEST_TIMEOUT_MS)
        : null;
      try {
        const method = String(options?.method || "GET").toUpperCase();
        const request = () => fetch(url, {
          ...options,
          credentials: "same-origin",
          headers: requestHeaders(options, method),
          signal: options?.signal ?? controller?.signal,
        });
        let res = await request();
        if (!res.ok) {
          const json = await safeJson<R & ApiMeta>(res);
          if (json) {
            refreshSessionTokens(json as Record<string, unknown>);
            if (canRecoverSession(url, method, json)) {
              const recovered = await bootstrapSession();
              if (recovered) {
                // P0-3 [C6]: reset controller before retry to avoid deadlock.
                // The original controller's timeout fired during session
                // recovery; a new one lets the retry run its full timeout.
                if (controller && !options?.signal) {
                  controller = new AbortController();
                  if (timeout) window.clearTimeout(timeout);
                  timeout = window.setTimeout(() => controller!.abort(), DEFAULT_REQUEST_TIMEOUT_MS);
                }
                res = await request();
                if (res.ok) {
                  const retryJson = await res.json() as R & ApiMeta;
                  refreshSessionTokens(retryJson as Record<string, unknown>);
                  const retryOk = retryJson.ok !== false && !(
                    retryJson.ok === undefined &&
                    Boolean(retryJson.error || retryJson.error_code)
                  );
                  const normalizedRetry = { ...retryJson, ok: retryOk } as R & ApiMeta;
                  if (!retryOk) {
                    setState({ data: null, loading: false, error: apiErrorMessage(retryJson), lastErrorMeta: retryJson });
                    return normalizedRetry;
                  }
                  const retryRaw = retryJson as Record<string, unknown>;
                  setState({ data: (retryRaw.data !== undefined ? retryRaw.data : retryJson) as T, loading: false, error: null, lastErrorMeta: null });
                  if (method === "POST") {
                    saveResumeState({ lastConnectionOk: true, lastError: null });
                  }
                  return normalizedRetry;
                }
                const retryError = await safeJson<R & ApiMeta>(res);
                if (retryError) {
                  refreshSessionTokens(retryError as Record<string, unknown>);
                  const retryMsg = apiErrorMessage(retryError, `HTTP ${res.status}: ${res.statusText}`);
                  const normalizedRetryError = { ...retryError, ok: false } as R & ApiMeta;
                  setState({ data: null, loading: false, error: retryMsg, lastErrorMeta: retryError });
                  return normalizedRetryError;
                }
              }
            }
            const msg = apiErrorMessage(json, `HTTP ${res.status}: ${res.statusText}`);
            const normalized = { ...json, ok: false } as R & ApiMeta;
            setState({ data: null, loading: false, error: msg, lastErrorMeta: json });
            return normalized;
          }
          const msg = `HTTP ${res.status}: ${res.statusText}`;
          setState({ data: null, loading: false, error: msg, lastErrorMeta: null });
          return null;
        }
        const json = await res.json() as R & ApiMeta;
        refreshSessionTokens(json as Record<string, unknown>);
        const ok = json.ok !== false && !(
          json.ok === undefined &&
          Boolean(json.error || json.error_code)
        );
        const normalized = { ...json, ok } as R & ApiMeta;
        if (!ok) {
          setState({ data: null, loading: false, error: apiErrorMessage(json), lastErrorMeta: json });
          return normalized;
        }
        // SAFETY: json is structurally R & ApiMeta; the backend returns flat JSON.
        // Extract .data if present, otherwise use the whole payload as the data portion.
        const raw = json as Record<string, unknown>;
        setState({ data: (raw.data !== undefined ? raw.data : json) as T, loading: false, error: null, lastErrorMeta: null });
        // P0-4: persist connection health after every successful POST
        if (method === "POST") {
          saveResumeState({ lastConnectionOk: true, lastError: null });
        }
        return normalized;
      } catch (err) {
        const msg = networkErrorMessage(err);
        setState({ data: null, loading: false, error: msg, lastErrorMeta: null });
        return null;
      } finally {
        if (timeout !== null) {
          window.clearTimeout(timeout);
        }
      }
    },
    [],
  );

  const reset = useCallback(() => {
    setState({ data: null, loading: false, error: null, lastErrorMeta: null });
  }, []);

  return { ...state, call, reset };
}

async function safeJson<R>(res: Response): Promise<R | null> {
  try {
    return await res.json() as R;
  } catch {
    return null;
  }
}

function refreshSessionTokens(payload: Record<string, unknown>) {
  const csrf = typeof payload.csrf_token === "string" ? payload.csrf_token : "";
  const stream = typeof payload.stream_token === "string" ? payload.stream_token : "";
  if (csrf) setCsrfToken(csrf);
  if (stream) setStreamToken(stream);
}

function canRecoverSession(url: string, method: string, payload: ApiMeta) {
  if (url === "/api/session") return false;
  if (!["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"].includes(method)) return false;
  return isSessionInvalidPayload(payload);
}

async function bootstrapSession() {
  try {
    const res = await fetch("/api/session", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
    });
    const json = await safeJson<Record<string, unknown>>(res);
    if (!res.ok || !json || json.ok === false) return false;
    refreshSessionTokens(json);
    return true;
  } catch {
    return false;
  }
}

function requestHeaders(options: RequestInit | undefined, method: string): HeadersInit {
  const headers: Record<string, string> = {};
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    headers["Content-Type"] = "application/json";
    Object.assign(headers, csrfHeaders());
  } else {
    const csrf = csrfToken();
    if (csrf) headers["X-Brain-Alpha-CSRF"] = csrf;
  }
  const incoming = options?.headers || {};
  if (incoming instanceof Headers) {
    incoming.forEach((value, key) => { headers[key] = value; });
  } else if (Array.isArray(incoming)) {
    incoming.forEach(([key, value]) => { headers[key] = String(value); });
  } else {
    Object.assign(headers, incoming as Record<string, string>);
  }
  return headers;
}
