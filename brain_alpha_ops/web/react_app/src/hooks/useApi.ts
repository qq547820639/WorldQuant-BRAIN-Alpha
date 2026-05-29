/** Generic fetch hook with loading/error state management. */

import { useState, useCallback } from "react";
import type { ApiResponse } from "@/types";

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

  const call = useCallback(
    async <R = T>(url: string, options?: RequestInit): Promise<ApiResponse<R> | null> => {
      setState((prev) => ({ ...prev, loading: true, error: null }));
      try {
        const method = String(options?.method || "GET").toUpperCase();
        const res = await fetch(url, {
          credentials: "same-origin",
          ...options,
          headers: requestHeaders(options, method),
        });
        const json: ApiResponse<R> = await res.json();
        const ok = json.ok !== false && !json.error && !json.error_code;
        const normalized = { ...json, ok };
        if (!ok) {
          setState({ data: null, loading: false, error: json.error || json.error_code || "Request failed" });
          return normalized as ApiResponse<R>;
        }
        setState({ data: (json.data ?? json) as unknown as T, loading: false, error: null });
        return normalized as ApiResponse<R>;
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Network error";
        setState({ data: null, loading: false, error: msg });
        return null;
      }
    },
    [],
  );

  const reset = useCallback(() => {
    setState({ data: null, loading: false, error: null });
  }, []);

  return { ...state, call, reset };
}

function requestHeaders(options: RequestInit | undefined, method: string): HeadersInit {
  const headers: Record<string, string> = {};
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    headers["Content-Type"] = "application/json";
  }
  const incoming = options?.headers || {};
  if (incoming instanceof Headers) {
    incoming.forEach((value, key) => { headers[key] = value; });
  } else if (Array.isArray(incoming)) {
    incoming.forEach(([key, value]) => { headers[key] = String(value); });
  } else {
    Object.assign(headers, incoming as Record<string, string>);
  }
  const csrf = csrfToken();
  if (csrf) headers["X-Brain-Alpha-CSRF"] = csrf;
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    headers["X-Brain-Alpha-Request-ID"] = createRequestId();
    headers["X-Brain-Alpha-Request-Timestamp"] = String(Date.now());
  }
  return headers;
}

function csrfToken() {
  const meta = document.querySelector<HTMLMetaElement>('meta[name="brain-alpha-csrf"]');
  const fromMeta = meta?.content || "";
  const fromWindow = String((window as unknown as { __BRAIN_ALPHA_OPS_CSRF_TOKEN__?: string }).__BRAIN_ALPHA_OPS_CSRF_TOKEN__ || "");
  const token = fromMeta || fromWindow;
  return token && !token.startsWith("__BRAIN_ALPHA_OPS") ? token : "";
}

function createRequestId() {
  if (window.crypto && typeof window.crypto.randomUUID === "function") {
    return window.crypto.randomUUID();
  }
  return `req_${Date.now().toString(36)}_${Math.random().toString(36).slice(2)}`;
}
