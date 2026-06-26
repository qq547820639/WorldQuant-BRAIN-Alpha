/**
 * ActionableError — Workstream E3 structured error card.
 *
 * Renders an ActionableErrorPayload (cause / impact / suggested action /
 * recovery entry) instead of a raw stacktrace or blank page.  When the
 * payload is missing or malformed, falls back to the existing ErrorCard
 * so older callers keep working (backward compatibility).
 *
 * Accessibility:
 *   - role="alert" + aria-live="assertive" so screen readers announce.
 *   - The recovery button is a real <button> (keyboard-focusable).
 */
import { memo, useCallback, type CSSProperties } from 'react';
import ErrorCard from './ErrorCard';
import type { CardViewId } from '@/types';
import {
  isActionableErrorPayload,
  recoveryActionLabel,
  buildActionableError,
  classifyError,
  type ActionableErrorPayload,
  type ErrorKind,
  type ErrorSeverity,
} from '@/types/errors';

// ── Severity styling (mirrors ErrorCard's severityConfig) ────────────────

interface SeverityStyle {
  border: string;
  bg: string;
  badgeBg: string;
  badgeText: string;
  iconColor: string;
  textColor: string;
}

const SEVERITY_STYLES: Record<ErrorSeverity, SeverityStyle> = {
  error: {
    border: 'var(--color-error-border)',
    bg: 'var(--color-error-bg-faint)',
    badgeBg: 'var(--color-error-bg)',
    badgeText: 'var(--color-error-text)',
    iconColor: 'var(--color-icon-error)',
    textColor: 'var(--color-error-text)',
  },
  warning: {
    border: 'var(--color-warning-border)',
    bg: 'var(--color-warning-bg)',
    badgeBg: 'var(--color-warning-bg)',
    badgeText: 'var(--color-warning-icon)',
    iconColor: 'var(--color-icon-warning)',
    textColor: 'var(--color-warning-icon)',
  },
  info: {
    border: 'var(--color-info-border)',
    bg: 'var(--color-info-bg-faint)',
    badgeBg: 'var(--color-info-bg)',
    badgeText: 'var(--color-info-text)',
    iconColor: 'var(--color-icon-info)',
    textColor: 'var(--color-info-text)',
  },
};

// ── kind → display label (for the colored kind badge) ────────────────────

const KIND_LABELS: Record<ErrorKind, string> = {
  login_expired: '登录失效',
  cache_unavailable: '缓存不可用',
  official_rate_limited: '官方限流',
  simulation_concurrency_exceeded: '并发超限',
  dataset_missing: 'Dataset 缺失',
  field_non_compliant: '字段不合规',
  expression_invalid: '表达式非法',
  network_timeout: '网络超时',
  task_cancelled: '任务取消',
  queue_blocked: '队列阻塞',
  local_service_unavailable: '本地服务未启动',
};

// ── Recovery URL → CardViewId mapping ─────────────────────────────────────
// Routes that map to an actual CardViewId get routed via onNavigate;
// routes that require a side-effect (e.g. /operations/refresh) are
// surfaced via onRecoveryAction when provided by the parent.

const RECOVERY_URL_TO_VIEW: Record<string, CardViewId> = {
  '/config': 'config',
  '/candidates': 'candidates',
  '/dashboard': 'dashboard',
  '/backtests': 'official_backtests',
};

export interface ActionableErrorProps {
  /** Structured payload from the backend (payload.actionable). */
  payload?: ActionableErrorPayload | null;
  /**
   * Optional raw error to classify on the frontend side when no
   * payload is supplied.  Ignored when ``payload`` is present.
   */
  error?: unknown;
  /** Optional additional context to merge into the fallback payload. */
  context?: Record<string, unknown>;
  /** Navigate to a CardViewId (used by recovery_url). */
  onNavigate?: (view: CardViewId) => void;
  /** Side-effect handler for recovery_action_id values that are not pure navigation. */
  onRecoveryAction?: (actionId: string, payload: ActionableErrorPayload) => void;
  /** Extra className for the outer container. */
  className?: string;
  /** Optional title override (defaults to kind label). */
  title?: string;
}

function XCircleIcon({ color }: { color: string }) {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill={color}
      aria-hidden="true"
      focusable="false"
    >
      <path d="M12 2C6.47 2 2 6.47 2 12s4.47 10 10 10 10-4.47 10-10S17.53 2 12 2zm5 13.59L15.59 17 12 13.41 8.41 17 7 15.59 10.59 12 7 8.41 8.41 7 12 10.59 15.59 7 17 8.41 13.41 12 17 15.59z" />
    </svg>
  );
}

function ActionableErrorImpl({
  payload,
  error,
  context,
  onNavigate,
  onRecoveryAction,
  className = '',
  title,
}: ActionableErrorProps) {
  // Resolve the actionable payload: prefer the supplied payload, fall
  // back to classifying the error on the frontend, then fall back to
  // a generic network_timeout payload.
  let actionable: ActionableErrorPayload | null = null;
  if (payload && isActionableErrorPayload(payload)) {
    actionable = payload;
  } else if (error != null) {
    const kind = classifyError(error);
    actionable = buildActionableError(kind, context);
  }

  // Backward compatibility: when no actionable payload can be derived,
  // delegate to ErrorCard so we never show a blank or "unknown" error.
  if (!actionable) {
    const fallbackTitle = title || '操作异常';
    const fallbackDetails =
      typeof error === 'string' ? error : error instanceof Error ? error.message : '';
    return (
      <ErrorCard
        title={fallbackTitle}
        details={fallbackDetails}
        severity="error"
        className={className}
      />
    );
  }

  const style = SEVERITY_STYLES[actionable.severity] || SEVERITY_STYLES.error;
  const kindLabel = title || KIND_LABELS[actionable.kind] || actionable.kind;
  const recoveryLabel = recoveryActionLabel(actionable.recovery_action_id);

  const handleRecovery = useCallback(() => {
    if (!actionable) return;
    const view = RECOVERY_URL_TO_VIEW[actionable.recovery_url];
    if (view && onNavigate) {
      onNavigate(view);
      return;
    }
    // Non-navigation recovery (e.g. /operations/refresh, wait_and_retry).
    if (onRecoveryAction) {
      onRecoveryAction(actionable.recovery_action_id, actionable);
    }
  }, [actionable, onNavigate, onRecoveryAction]);

  const containerStyle: CSSProperties = {
    border: `1px solid ${style.border}`,
    borderRadius: 8,
    background: style.bg,
    padding: '16px',
  };

  // retry_after is surfaced in context for official_rate_limited.
  const retryAfter = actionable.context?.retry_after;
  const retryAfterText =
    typeof retryAfter === 'number' && retryAfter > 0
      ? `预计 ${Math.ceil(retryAfter)} 秒后恢复`
      : null;

  return (
    <div
      className={`actionable-error-card ${className}`}
      role="alert"
      aria-live="assertive"
      aria-atomic="true"
      style={containerStyle}
      data-error-kind={actionable.kind}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
        <div style={{ flexShrink: 0, marginTop: 2 }}>
          <XCircleIcon color={style.iconColor} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
            <span
              style={{
                display: 'inline-block',
                padding: '2px 8px',
                borderRadius: 4,
                fontSize: 12,
                fontWeight: 600,
                background: style.badgeBg,
                color: style.badgeText,
              }}
            >
              {kindLabel}
            </span>
            {retryAfterText && (
              <span
                style={{
                  display: 'inline-block',
                  padding: '2px 8px',
                  borderRadius: 4,
                  fontSize: 12,
                  background: 'var(--color-surface-deep)',
                  color: 'var(--color-text-muted)',
                }}
              >
                {retryAfterText}
              </span>
            )}
          </div>

          <p
            style={{
              fontSize: 14,
              fontWeight: 500,
              color: style.textColor,
              marginBottom: 8,
              lineHeight: 1.5,
            }}
          >
            {actionable.cause}
          </p>

          {actionable.impact_scope && (
            <p
              style={{
                fontSize: 13,
                color: 'var(--color-text-body)',
                lineHeight: 1.5,
                marginBottom: 8,
              }}
            >
              <span
                style={{
                  display: 'inline-block',
                  padding: '1px 6px',
                  borderRadius: 3,
                  fontSize: 11,
                  background: 'var(--color-surface-deep)',
                  color: 'var(--color-text-muted)',
                  marginRight: 6,
                }}
              >
                影响范围
              </span>
              {actionable.impact_scope}
            </p>
          )}

          {actionable.suggested_action && (
            <p
              style={{
                fontSize: 13,
                color: 'var(--color-text-body)',
                lineHeight: 1.5,
                marginBottom: recoveryLabel ? 12 : 0,
              }}
            >
              <span
                style={{
                  display: 'inline-block',
                  padding: '1px 6px',
                  borderRadius: 3,
                  fontSize: 11,
                  background: 'var(--color-surface-deep)',
                  color: 'var(--color-text-muted)',
                  marginRight: 6,
                }}
              >
                建议操作
              </span>
              {actionable.suggested_action}
            </p>
          )}

          {recoveryLabel && (
            <button
              type="button"
              className="btn btn-sm"
              onClick={handleRecovery}
              style={{
                marginTop: 4,
                background: 'var(--color-surface-elevated)',
                border: '0.5px solid var(--color-border-medium)',
                color: 'var(--color-text-primary)',
              }}
            >
              {recoveryLabel}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

const ActionableError = memo(ActionableErrorImpl);
export default ActionableError;
