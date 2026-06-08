/** Generic fetch hook with loading/error state management. */

import { useState, useCallback } from "react";
import { csrfHeaders, csrfToken } from "@/utils/csrf";

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
        const res = await fetch(url, {
          ...options,
          credentials: "same-origin",
          headers: requestHeaders(options, method),
          signal: options?.signal ?? controller?.signal,
        });
        if (!res.ok) {
          const msg = `HTTP ${res.status}: ${res.statusText}`;
          setState({ data: null, loading: false, error: msg });
          return null;
        }
        const json = await res.json() as R & ApiMeta;
        const ok = json.ok !== false && !json.error && !json.error_code;
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

function isAbortError(err: unknown) {
  return err instanceof DOMException && err.name === "AbortError";
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
