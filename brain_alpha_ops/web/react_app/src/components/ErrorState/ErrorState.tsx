/**
 * ErrorState — 统一错误状态组件
 * 多种严重级别和展示级别，用于各种错误场景
 */
import { memo, type ReactNode } from 'react';
import RetryButton from './RetryButton';

type ErrorSeverity = 'error' | 'warning' | 'info';
type ErrorDisplayLevel = 'inline' | 'card' | 'page';

interface ErrorStateProps {
  title: string;
  description?: string;
  details?: string;
  severity?: ErrorSeverity;
  displayLevel?: ErrorDisplayLevel;
  onRetry?: () => void;
  retryLoading?: boolean;
  retryLabel?: string;
  icon?: ReactNode;
  children?: ReactNode;
  className?: string;
}

const severityConfig = {
  error: {
    borderColor: 'var(--color-error-border)',
    bgColor: 'var(--color-error-bg-faint)',
    iconColor: 'var(--color-icon-error)',
    textColor: 'var(--color-error-text)',
    iconPath:
      'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z',
  },
  warning: {
    borderColor: 'var(--color-warning-border)',
    bgColor: 'var(--color-warning-bg)',
    iconColor: 'var(--color-icon-warning)',
    textColor: 'var(--color-warning-icon)',
    iconPath: 'M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z',
  },
  info: {
    borderColor: 'var(--color-info-border)',
    bgColor: 'var(--color-info-bg-faint)',
    iconColor: 'var(--color-icon-info)',
    textColor: 'var(--color-info-text)',
    iconPath:
      'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z',
  },
};

function ErrorIcon({ severity, size = 24 }: { severity: ErrorSeverity; size?: number }) {
  const config = severityConfig[severity];
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={config.iconColor}
      aria-hidden="true"
      focusable="false"
    >
      <path d={config.iconPath} />
    </svg>
  );
}

export default memo(function ErrorState({
  title,
  description,
  details,
  severity = 'error',
  displayLevel = 'card',
  onRetry,
  retryLoading = false,
  retryLabel = '重试',
  icon,
  children,
  className = '',
}: ErrorStateProps) {
  const config = severityConfig[severity];

  if (displayLevel === 'inline') {
    return (
      <div
        className={`inline-flex items-start gap-2 ${className}`}
        role="alert"
        style={{
          padding: '8px 12px',
          borderRadius: 6,
          background: config.bgColor,
          border: `1px solid ${config.borderColor}`,
        }}
      >
        <div style={{ flexShrink: 0, marginTop: 1 }}>
          {icon || <ErrorIcon severity={severity} size={18} />}
        </div>
        <div style={{ minWidth: 0 }}>
          <p style={{ fontSize: 13, fontWeight: 500, color: config.textColor, margin: 0 }}>
            {title}
          </p>
          {description && (
            <p
              style={{
                fontSize: 12,
                color: 'var(--color-text-muted)',
                marginTop: 4,
                marginBottom: 0,
              }}
            >
              {description}
            </p>
          )}
        </div>
      </div>
    );
  }

  if (displayLevel === 'page') {
    return (
      <div
        className={`flex flex-col items-center justify-center py-12 px-4 text-center ${className}`}
        role="alert"
      >
        <div className="mb-4">
          {icon || <ErrorIcon severity={severity} size={48} />}
        </div>
        <h3
          className="text-lg font-semibold mb-2"
          style={{ color: 'var(--color-text-bright)' }}
        >
          {title}
        </h3>
        {description && (
          <p className="text-sm mb-4 max-w-sm" style={{ color: 'var(--color-text-muted)' }}>
            {description}
          </p>
        )}
        {details && (
          <p className="text-xs mb-4 max-w-md" style={{ color: 'var(--color-text-dim)' }}>
            {details}
          </p>
        )}
        {onRetry && (
          <div className="mt-2">
            <RetryButton onRetry={onRetry} loading={retryLoading} label={retryLabel} />
          </div>
        )}
        {children && <div className="mt-4">{children}</div>}
      </div>
    );
  }

  return (
    <div
      className={`error-card ${className}`}
      role="alert"
      style={{
        border: `1px solid ${config.borderColor}`,
        borderRadius: 8,
        background: config.bgColor,
        padding: '16px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
        <div style={{ flexShrink: 0, marginTop: 2 }}>
          {icon || <ErrorIcon severity={severity} size={20} />}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <p
            style={{
              fontSize: 14,
              fontWeight: 500,
              color: config.textColor,
              marginBottom: description || details ? 8 : 0,
            }}
          >
            {title}
          </p>

          {description && (
            <p
              style={{
                fontSize: 13,
                color: 'var(--color-text-body)',
                lineHeight: 1.5,
                marginBottom: details ? 8 : 0,
              }}
            >
              {description}
            </p>
          )}

          {details && (
            <p
              style={{
                fontSize: 12,
                color: 'var(--color-text-muted)',
                lineHeight: 1.5,
              }}
            >
              {details}
            </p>
          )}

          {(onRetry || children) && (
            <div style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {onRetry && (
                <RetryButton onRetry={onRetry} loading={retryLoading} label={retryLabel} size="sm" />
              )}
              {children}
            </div>
          )}
        </div>
      </div>
    </div>
  );
});
