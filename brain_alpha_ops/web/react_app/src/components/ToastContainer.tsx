/** Toast notification container with auto-dismiss. */

import type { Toast } from "@/types";

interface Props {
  toasts: Toast[];
  onDismiss: (id: string) => void;
}

const ICON_MAP: Record<Toast["type"], string> = {
  success: "✓",
  error: "✕",
  warning: "⚠",
  info: "ℹ",
};

const COLOR_MAP: Record<Toast["type"], string> = {
  success: "border-success/50 bg-success/10",
  error: "border-danger/50 bg-danger/10",
  warning: "border-warning/50 bg-warning/10",
  info: "border-brand-500/50 bg-brand-500/10",
};

export default function ToastContainer({ toasts, onDismiss }: Props) {
  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 left-4 right-4 z-50 flex flex-col gap-2 sm:left-auto sm:max-w-sm">
      {toasts.map((toast) => {
        const urgent = toast.type === "error";
        return (
          <div
            key={toast.id}
            className={`flex items-start gap-2 p-3 rounded-lg border backdrop-blur shadow-lg animate-slide-up ${COLOR_MAP[toast.type]}`}
            role={urgent ? "alert" : "status"}
            aria-live={urgent ? "assertive" : "polite"}
            aria-atomic="true"
          >
            <span className="text-sm font-bold mt-0.5" aria-hidden="true">{ICON_MAP[toast.type]}</span>
            <p className="text-sm text-gray-100 flex-1">{toast.message}</p>
            {toast.action_label && toast.on_action && (
              <button
                type="button"
                className="text-xs font-semibold text-gray-100 underline underline-offset-2"
                aria-label={`${toast.action_label}: ${toast.message}`}
                onClick={() => {
                  toast.on_action?.();
                  onDismiss(toast.id);
                }}
              >
                {toast.action_label}
              </button>
            )}
            <button
              type="button"
              className="text-xs text-gray-300 hover:text-white"
              aria-label="Dismiss notification"
              onClick={() => onDismiss(toast.id)}
            >
              x
            </button>
          </div>
        );
      })}
    </div>
  );
}
