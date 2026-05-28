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
    async (url: string, options?: RequestInit): Promise<ApiResponse<T> | null> => {
      setState((prev) => ({ ...prev, loading: true, error: null }));
      try {
        const res = await fetch(url, {
          headers: { "Content-Type": "application/json" },
          ...options,
        });
        const json: ApiResponse<T> = await res.json();
        if (!json.ok) {
          setState({ data: null, loading: false, error: json.error || json.error_code || "Request failed" });
          return json;
        }
        setState({ data: (json.data ?? json) as unknown as T, loading: false, error: null });
        return json;
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
