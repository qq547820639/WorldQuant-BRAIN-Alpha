/** Toast notification container — Terminal Precision design */
import type { Toast } from "@/types";

interface Props {
  toasts: Toast[];
  onDismiss: (id: string) => void;
}

const ICON_MAP: Record<Toast["type"], string> = {
  success: "\u2713",
  error: "\u2715",
  warning: "\u26A0",
  info: "\u2139",
};

const TOAST_CLASS: Record<Toast["type"], string> = {
  success: "toast-success",
  error: "toast-error",
  warning: "toast-warning",
  info: "toast-info",
};

const MAX_VISIBLE = 3;

export default function ToastContainer({ toasts, onDismiss }: Props) {
  if (toasts.length === 0) return null;
  const visible = toasts.slice(-MAX_VISIBLE);

  return (
    <div className="toast-container" role="region" aria-label="通知消息" aria-live="polite">
      {visible.map((toast) => {
        const urgent = toast.type === "error";
        return (
          <div
            key={toast.id}
            className={`toast ${TOAST_CLASS[toast.type]}`}
            role={urgent ? "alert" : "status"}
            aria-live={urgent ? "assertive" : "polite"}
            aria-atomic="true"
          >
            <span className="text-sm font-semibold shrink-0 mt-0.5" aria-hidden="true">
              {ICON_MAP[toast.type]}
            </span>
            <p className="flex-1 min-w-0 break-words text-sm">{toast.message}</p>
            {toast.secondary_action_label && toast.on_secondary_action && (
              <button
                type="button"
                className="text-xs font-semibold underline underline-offset-2 shrink-0"
                aria-label={`${toast.secondary_action_label}: ${toast.message}`}
                onClick={() => { toast.on_secondary_action?.(); onDismiss(toast.id); }}
              >
                {toast.secondary_action_label}
              </button>
            )}
            {toast.action_label && toast.on_action && (
              <button
                type="button"
                className="text-xs font-semibold underline underline-offset-2 shrink-0"
                aria-label={`${toast.action_label}: ${toast.message}`}
                onClick={() => { toast.on_action?.(); onDismiss(toast.id); }}
              >
                {toast.action_label}
              </button>
            )}
            <button
              type="button"
              className="text-xs opacity-60 hover:opacity-100 shrink-0"
              aria-label="关闭通知"
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
