/**
 * Spinner — 加载指示器组件
 * 多种尺寸和颜色，用于各种加载场景
 */
import { memo } from 'react';

type SpinnerSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl';

interface SpinnerProps {
  size?: SpinnerSize;
  color?: string;
  className?: string;
  label?: string;
}

const sizeMap: Record<SpinnerSize, number> = {
  xs: 12,
  sm: 16,
  md: 24,
  lg: 32,
  xl: 48,
};

export default memo(function Spinner({
  size = 'md',
  color,
  className = '',
  label = '加载中',
}: SpinnerProps) {
  const pixelSize = sizeMap[size];
  const strokeWidth = Math.max(2, pixelSize / 12);

  return (
    <span
      className={`inline-flex items-center justify-center ${className}`}
      role="status"
      aria-label={label}
    >
      <svg
        width={pixelSize}
        height={pixelSize}
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        style={{
          animation: 'spin 1s linear infinite',
        }}
        aria-hidden="true"
      >
        <circle
          cx="12"
          cy="12"
          r="10"
          stroke={color || 'var(--color-border-medium)'}
          strokeWidth={strokeWidth}
          fill="none"
          opacity="0.25"
        />
        <path
          d="M12 2a10 10 0 0 1 10 10"
          stroke={color || 'var(--color-primary)'}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          fill="none"
        />
      </svg>
      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </span>
  );
});
