import { useEffect, useRef, type FC } from "react";

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description?: string;
  confirmText?: string;
  cancelText?: string;
  variant?: "default" | "danger";
  onConfirm: () => void;
  onCancel: () => void;
}

const ConfirmDialog: FC<ConfirmDialogProps> = ({
  open,
  title,
  description,
  confirmText = "确认",
  cancelText = "取消",
  variant = "default",
  onConfirm,
  onCancel,
}) => {
  const dialogRef = useRef<HTMLDivElement>(null);
  const confirmButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;

    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const timer = setTimeout(() => {
      confirmButtonRef.current?.focus();
    }, 50);

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onCancel();
      }
    };

    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.body.style.overflow = originalOverflow;
      document.removeEventListener("keydown", handleKeyDown);
      clearTimeout(timer);
    };
  }, [open, onCancel]);

  const handleBackdropClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) {
      onCancel();
    }
  };

  if (!open) return null;

  const confirmButtonClass =
    variant === "danger" ? "btn btn-danger" : "btn btn-primary";

  return (
    <div
      className="fixed inset-0 z-[999] flex items-center justify-center"
      style={{
        background: "var(--color-overlay-strong)",
        backdropFilter: "blur(3px)",
        animation: "fade-in-overlay 0.2s ease-out",
      }}
      onClick={handleBackdropClick}
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-dialog-title"
      aria-describedby={description ? "confirm-dialog-description" : undefined}
    >
      <div
        ref={dialogRef}
        className="relative w-full max-w-[420px] mx-4"
        style={{
          background: "var(--color-surface-deep)",
          border: "0.5px solid var(--color-border-default)",
          borderRadius: 8,
          boxShadow: "0 12px 40px rgba(0, 0, 0, 0.5)",
          animation: "dialog-in 0.25s cubic-bezier(0.16, 1, 0.3, 1)",
        }}
      >
        <div className="px-5 pt-5 pb-4">
          <h2
            id="confirm-dialog-title"
            className="text-sm font-semibold text-text-primary leading-tight"
          >
            {title}
          </h2>
          {description && (
            <p id="confirm-dialog-description" className="mt-2 text-xs text-text-secondary leading-relaxed">
              {description}
            </p>
          )}
        </div>

        <div
          className="flex items-center justify-end gap-2 px-5 py-3"
          style={{
            borderTop: "0.5px solid var(--color-border-default)",
            background: "var(--color-surface-1)",
            borderRadius: "0 0 8px 8px",
          }}
        >
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={onCancel}
          >
            {cancelText}
          </button>
          <button
            ref={confirmButtonRef}
            type="button"
            className={confirmButtonClass}
            onClick={onConfirm}
          >
            {confirmText}
          </button>
        </div>
      </div>

      <style>{`
        @keyframes fade-in-overlay {
          from { opacity: 0; }
          to   { opacity: 1; }
        }
        @keyframes dialog-in {
          from {
            opacity: 0;
            transform: translateY(8px) scale(0.98);
          }
          to {
            opacity: 1;
            transform: translateY(0) scale(1);
          }
        }
        @media (prefers-reduced-motion: reduce) {
          @keyframes fade-in-overlay {
            from { opacity: 1; }
            to   { opacity: 1; }
          }
          @keyframes dialog-in {
            from { opacity: 1; transform: none; }
            to   { opacity: 1; transform: none; }
          }
        }
      `}</style>
    </div>
  );
};

export default ConfirmDialog;
