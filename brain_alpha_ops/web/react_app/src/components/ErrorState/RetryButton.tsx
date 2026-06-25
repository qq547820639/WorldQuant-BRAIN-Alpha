/**
 * RetryButton — 带加载状态的重试按钮组件
 */
import { memo } from 'react';
import Spinner from '../LoadingState/Spinner';

interface RetryButtonProps {
  onRetry: () => void;
  loading?: boolean;
  label?: string;
  loadingLabel?: string;
  variant?: 'primary' | 'secondary' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
  className?: string;
  disabled?: boolean;
}

export default memo(function RetryButton({
  onRetry,
  loading = false,
  label = '重试',
  loadingLabel = '重试中...',
  variant = 'primary',
  size = 'md',
  className = '',
  disabled = false,
}: RetryButtonProps) {
  const baseStyles: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    borderRadius: 6,
    fontWeight: 500,
    cursor: loading || disabled ? 'not-allowed' : 'pointer',
    border: '1px solid var(--color-border-medium)',
    transition: 'all 0.15s ease',
  };

  const sizeStyles: Record<string, React.CSSProperties> = {
    sm: { padding: '4px 12px', fontSize: 13 },
    md: { padding: '6px 16px', fontSize: 14 },
    lg: { padding: '8px 20px', fontSize: 15 },
  };

  const variantStyles: Record<string, React.CSSProperties> = {
    primary: {
      background: 'var(--color-primary)',
      color: 'var(--color-text-on-primary)',
      borderColor: 'var(--color-primary)',
    },
    secondary: {
      background: 'var(--color-surface-elevated)',
      color: 'var(--color-text-primary)',
    },
    ghost: {
      background: 'transparent',
      color: 'var(--color-text-primary)',
      borderColor: 'transparent',
    },
  };

  return (
    <button
      type="button"
      onClick={onRetry}
      disabled={loading || disabled}
      className={className}
      style={{
        ...baseStyles,
        ...sizeStyles[size],
        ...variantStyles[variant],
        opacity: loading || disabled ? 0.7 : 1,
      }}
      aria-busy={loading}
    >
      {loading && <Spinner size="xs" color="currentColor" />}
      <span>{loading ? loadingLabel : label}</span>
    </button>
  );
});
