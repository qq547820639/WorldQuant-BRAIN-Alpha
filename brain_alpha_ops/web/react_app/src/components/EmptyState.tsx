/**
 * EmptyState — centered empty state with icon, title, description, and CTA slot.
 * Used across all modules when data is not yet available.
 */
import { memo, type ReactNode } from "react";

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  children?: ReactNode;
  className?: string;
}

function EmptyIcon() {
  return (
    <svg
      width="48"
      height="48"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      style={{ color: "var(--color-text-dim)" }}
      aria-hidden="true"
      focusable="false"
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M20 13V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7m16 0v5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-5m16 0h-2.586a1 1 0 0 0-.707.293l-2.414 2.414a1 1 0 0 1-.707.293h-3.172a1 1 0 0 1-.707-.293l-2.414-2.414A1 1 0 0 0 6.586 13H4" />
    </svg>
  );
}

export default memo(function EmptyState({ icon, title, description, children, className = "" }: EmptyStateProps) {
  return (
    <div className={`flex flex-col items-center justify-center py-12 px-4 text-center ${className}`} role="status">
      <div className="mb-4" style={{ color: "var(--color-text-dim)" }}>
        {icon || <EmptyIcon />}
      </div>
      <h3 className="text-lg font-semibold mb-1" style={{ color: "var(--color-text-bright)" }}>{title}</h3>
      {description && <p className="text-sm mb-4 max-w-sm" style={{ color: "var(--color-text-muted)" }}>{description}</p>}
      {children && <div className="mt-2">{children}</div>}
    </div>
  );
});
