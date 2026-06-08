/**
 * EmptyState — centered empty state with icon, title, description, CTA, and hint.
 * Used across all modules when data is not yet available.
 */
import { memo, type ReactNode } from "react";

interface Props {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
  hint?: string;
}

function EmptyIcon() {
  return (
    <svg width="48" height="48" viewBox="0 0 48 48" fill="none" stroke="oklch(0.52 0.006 45)" strokeWidth="1" opacity="0.5">
      <rect x="8" y="8" width="32" height="32" rx="4" />
      <line x1="16" y1="18" x2="32" y2="18" />
      <line x1="16" y1="24" x2="28" y2="24" />
      <line x1="16" y1="30" x2="24" y2="30" />
    </svg>
  );
}

export default memo(function EmptyState({ icon, title, description, action, hint }: Props) {
  return (
    <div className="empty-state" role="status">
      <div className="empty-state-icon">
        {icon || <EmptyIcon />}
      </div>
      <h3 className="empty-state-title">{title}</h3>
      {description && <p className="empty-state-description">{description}</p>}
      {action && (
        <button type="button" className="btn btn-primary" onClick={action.onClick}>
          {action.label}
        </button>
      )}
      {hint && <p className="empty-state-hint">{hint}</p>}
    </div>
  );
});
