import { memo, type ReactNode } from 'react';

/** Reusable action panel with status and buttons. */

interface Props {
  title: string;
  description: string;
  status: string;
  primaryLabel: string;
  disabled?: boolean;
  onPrimary?: () => void;
  secondaryLabel?: string;
  secondaryDisabled?: boolean;
  onSecondary?: () => void;
  children?: ReactNode;
}

function ActionPanel({
  title,
  description,
  status,
  primaryLabel,
  disabled = false,
  onPrimary,
  secondaryLabel,
  secondaryDisabled = false,
  onSecondary,
  children,
}: Props) {
  return (
    <div className="panel min-w-0">
      <div className="panel-header">
        <span className="font-medium">{title}</span>
        <span className="badge badge-neutral">{status}</span>
      </div>
      <div className="panel-body-padded space-y-3">
        <p className="text-sm text-text-secondary">{description}</p>
        {children}
        <div className="flex gap-2">
          {onPrimary && (
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={disabled}
              onClick={onPrimary}
            >
              {primaryLabel}
            </button>
          )}
          {secondaryLabel && onSecondary && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={secondaryDisabled}
              onClick={onSecondary}
            >
              {secondaryLabel}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default memo(ActionPanel);
