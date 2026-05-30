/** Lightweight toast notification hook. */

import { useState, useCallback, useRef } from "react";
import type { Toast } from "@/types";

let toastIdCounter = 0;

export function useToast(maxToasts = 5) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const addToast = useCallback(
    (
      type: Toast["type"],
      message: string,
      durationMs = 5000,
      action?: { label: string; onClick: () => void },
    ) => {
      const id = `toast_${++toastIdCounter}_${Date.now()}`;
      const toast: Toast = {
        id,
        type,
        message,
        duration_ms: durationMs,
        action_label: action?.label,
        on_action: action?.onClick,
      };

      setToasts((prev) => {
        const next = [...prev, toast];
        return next.length > maxToasts ? next.slice(-maxToasts) : next;
      });

      if (durationMs > 0) {
        const timer = setTimeout(() => dismissToast(id), durationMs);
        timersRef.current.set(id, timer);
      }
      return id;
    },
    [maxToasts],
  );

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
    const timer = timersRef.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timersRef.current.delete(id);
    }
  }, []);

  return { toasts, addToast, dismissToast };
}
