/**
 * ErrorCard — unified error display card with severity levels.
 * Used across all modules for consistent error presentation.
 */
import { memo } from "react";

interface ErrorCardProps {
  title: string;
  details?: string;
  reason?: string;
  severity?: "error" | "warning" | "info";
  onRetry?: () => void;
  className?: string;
}

const severityConfig = {
  error: {
    borderColor: "var(--color-error-border)",
    bgColor: "var(--color-error-bg-faint)",
    iconColor: "var(--color-icon-error)",
    textColor: "var(--color-error-text)",
    iconPath: "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z",
    iconLabel: "错误",
  },
  warning: {
    borderColor: "var(--color-warning-border)",
    bgColor: "var(--color-warning-bg)",
    iconColor: "var(--color-icon-warning)",
    textColor: "var(--color-warning-icon)",
    iconPath: "M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z",
    iconLabel: "警告",
  },
  info: {
    borderColor: "var(--color-info-border)",
    bgColor: "var(--color-info-bg-faint)",
    iconColor: "var(--color-icon-info)",
    textColor: "var(--color-info-text)",
    iconPath: "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z",
    iconLabel: "信息",
  },
};

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

function WarningIcon({ color }: { color: string }) {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill={color}
      aria-hidden="true"
      focusable="false"
    >
      <path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z" />
    </svg>
  );
}

function InfoIcon({ color }: { color: string }) {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill={color}
      aria-hidden="true"
      focusable="false"
    >
      <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z" />
    </svg>
  );
}

const iconMap = {
  error: XCircleIcon,
  warning: WarningIcon,
  info: InfoIcon,
};

export default memo(function ErrorCard({
  title,
  details,
  reason,
  severity = "error",
  onRetry,
  className = "",
}: ErrorCardProps) {
  const config = severityConfig[severity];
  const IconComponent = iconMap[severity];

  return (
    <div
      className={`error-card ${className}`}
      role="alert"
      style={{
        border: `1px solid ${config.borderColor}`,
        borderRadius: 8,
        background: config.bgColor,
        padding: "16px",
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
        <div style={{ flexShrink: 0, marginTop: 2 }}>
          <IconComponent color={config.iconColor} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <p
            style={{
              fontSize: 14,
              fontWeight: 500,
              color: config.textColor,
              marginBottom: details || reason ? 8 : 0,
            }}
          >
            {title}
          </p>

          {details && (
            <p
              style={{
                fontSize: 13,
                color: "var(--color-text-body)",
                lineHeight: 1.5,
                marginBottom: reason ? 8 : 0,
              }}
            >
              {details}
            </p>
          )}

          {reason && (
            <p
              style={{
                fontSize: 12,
                color: "var(--color-text-muted)",
                lineHeight: 1.5,
              }}
            >
              原因：{reason}
            </p>
          )}

          {onRetry && (
            <button
              type="button"
              className="btn btn-sm"
              onClick={onRetry}
              style={{
                marginTop: 12,
                background: "var(--color-surface-elevated)",
                border: "0.5px solid var(--color-border-medium)",
                color: "var(--color-text-primary)",
              }}
            >
              重试
            </button>
          )}
        </div>
      </div>
    </div>
  );
});
