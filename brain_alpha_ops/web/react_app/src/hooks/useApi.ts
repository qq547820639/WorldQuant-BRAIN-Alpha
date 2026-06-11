/** Generic fetch hook with loading/error state management. */

import { useState, useCallback } from "react";
import { csrfHeaders, csrfToken, setCsrfToken, setStreamToken } from "@/utils/csrf";

const DEFAULT_REQUEST_TIMEOUT_MS = 120000;

/** Minimal API response envelope shared by all endpoints. */
export type ApiMeta = { ok: boolean; error?: string; error_code?: string };

interface UseApiState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

export function useApi<T = unknown>() {
  const [state, setState] = useState<UseApiState<T>>({
    data: null,
    loading: false,
    error: null,
  });

  // NOTE: call<R> returns R & ApiMeta (not ApiResponse<R>) so callers can
  // access endpoint-specific fields like task_id / job_id / candidates without
  // going through .data, matching the flat JSON shape the backend returns.
  const call = useCallback(
    async <R = T>(url: string, options?: RequestInit): Promise<(R & ApiMeta) | null> => {
      setState((prev) => ({ ...prev, loading: true, error: null }));
      const controller = options?.signal ? null : new AbortController();
      const timeout = controller
        ? window.setTimeout(() => controller.abort(), DEFAULT_REQUEST_TIMEOUT_MS)
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
                    setState({ data: null, loading: false, error: retryJson.error || retryJson.error_code || "Request failed" });
                    return normalizedRetry;
                  }
                  const retryRaw = retryJson as Record<string, unknown>;
                  setState({ data: (retryRaw.data !== undefined ? retryRaw.data : retryJson) as T, loading: false, error: null });
                  return normalizedRetry;
                }
                const retryError = await safeJson<R & ApiMeta>(res);
                if (retryError) {
                  refreshSessionTokens(retryError as Record<string, unknown>);
                  const retryMsg = retryError.error || retryError.error_code || `HTTP ${res.status}: ${res.statusText}`;
                  const normalizedRetryError = { ...retryError, ok: false } as R & ApiMeta;
                  setState({ data: null, loading: false, error: retryMsg });
                  return normalizedRetryError;
                }
              }
            }
            const msg = json.error || json.error_code || `HTTP ${res.status}: ${res.statusText}`;
            const normalized = { ...json, ok: false } as R & ApiMeta;
            setState({ data: null, loading: false, error: msg });
            return normalized;
          }
          const msg = `HTTP ${res.status}: ${res.statusText}`;
          setState({ data: null, loading: false, error: msg });
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
          setState({ data: null, loading: false, error: json.error || json.error_code || "Request failed" });
          return normalized;
        }
        // SAFETY: json is structurally R & ApiMeta; the backend returns flat JSON.
        // Extract .data if present, otherwise use the whole payload as the data portion.
        const raw = json as Record<string, unknown>;
        setState({ data: (raw.data !== undefined ? raw.data : json) as T, loading: false, error: null });
        return normalized;
      } catch (err) {
        const msg = isAbortError(err)
          ? "请求超时，请稍后重试。"
          : err instanceof Error ? err.message : "Network error";
        setState({ data: null, loading: false, error: msg });
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
    setState({ data: null, loading: false, error: null });
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

function isAbortError(err: unknown) {
  return err instanceof DOMException && err.name === "AbortError";
}

function canRecoverSession(url: string, method: string, payload: ApiMeta) {
  if (method !== "POST") return false;
  if (url === "/api/session") return false;
  const code = String(payload.error_code || payload.error || "");
  return code === "SESSION_INVALID" || code === "invalid local session";
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
