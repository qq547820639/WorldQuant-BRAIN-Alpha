/** Loading progress bar component */
import { memo, type ReactNode } from 'react';

interface LoadingProgressProps {
  /** Current progress value (for determinate progress) */
  value?: number;
  /** Maximum progress value (for determinate progress) */
  max?: number;
  /** Label text to display */
  label?: string;
  /** Show indeterminate progress bar */
  indeterminate?: boolean;
  /** Additional CSS classes */
  className?: string;
}

export default memo(function LoadingProgress({
  value = 0,
  max = 100,
  label,
  indeterminate = false,
  className = '',
}: LoadingProgressProps) {
  const percent = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  const isDeterminate = !indeterminate && value !== undefined;

  return (
    <div className={`flex flex-col gap-1.5 ${className}`}>
      {(label || isDeterminate) && (
        <div className="flex justify-between items-center text-sm">
          {label && <span className="text-text-secondary">{label}</span>}
          {isDeterminate && (
            <span className="text-accent font-medium tabular-nums">{Math.round(percent)}%</span>
          )}
        </div>
      )}
      <div
        className="h-2 bg-surface-2 rounded-full overflow-hidden"
        role="progressbar"
        aria-valuenow={isDeterminate ? Math.round(percent) : undefined}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label || '加载进度'}
      >
        {indeterminate ? (
          <div className="h-full bg-accent rounded-full animate-pulse w-full" />
        ) : (
          <div
            className="h-full bg-accent rounded-full transition-all duration-300 ease-out"
            style={{ width: `${percent}%` }}
          />
        )}
      </div>
    </div>
  );
});

interface ProgressFeedbackProps {
  /** Whether content is loading */
  loading: boolean;
  /** Child content */
  children: ReactNode;
}

/** Simple wrapper that shows children when not loading */
export const ProgressFeedback = memo(function ProgressFeedback({
  loading,
  children,
}: ProgressFeedbackProps) {
  if (!loading) return <>{children}</>;
  return (
    <div className="animate-pulse">
      <div className="h-4 bg-surface-2 rounded w-3/4 mb-2" />
      <div className="h-4 bg-surface-2 rounded w-1/2" />
    </div>
  );
});
