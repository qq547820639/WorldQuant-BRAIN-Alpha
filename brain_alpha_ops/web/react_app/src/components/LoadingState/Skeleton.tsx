/**
 * Enhanced Skeleton — 增强版骨架屏组件
 * 多种变体和配置选项
 */
import { memo } from 'react';
import BaseSkeleton from '../Skeleton';

type SkeletonVariant = 'text' | 'card' | 'avatar' | 'table-row' | 'circle' | 'rectangle';

interface SkeletonProps {
  variant?: SkeletonVariant;
  width?: string | number;
  height?: string | number;
  className?: string;
  count?: number;
  gap?: number;
}

export default memo(function Skeleton({
  variant = 'text',
  width,
  height,
  className = '',
  count = 1,
  gap = 8,
}: SkeletonProps) {
  const skeletonStyle = { backgroundColor: 'var(--color-border-subtle)' };

  if (count > 1) {
    return (
      <div className="space-y-2" style={{ gap }}>
        {Array.from({ length: count }).map((_, i) => (
          <Skeleton key={i} variant={variant} width={width} height={height} className={className} />
        ))}
      </div>
    );
  }

  const baseClass = 'animate-pulse';

  if (variant === 'circle') {
    const size = typeof width === 'number' ? width : 40;
    return (
      <div
        className={`${baseClass} rounded-full ${className}`}
        style={{
          ...skeletonStyle,
          width: typeof size === 'number' ? `${size}px` : size,
          height: typeof size === 'number' ? `${size}px` : size,
        }}
      />
    );
  }

  if (variant === 'rectangle') {
    return (
      <div
        className={`${baseClass} rounded ${className}`}
        style={{
          ...skeletonStyle,
          width: typeof width === 'number' ? `${width}px` : width || '100%',
          height: typeof height === 'number' ? `${height}px` : height || '100px',
        }}
      />
    );
  }

  return <BaseSkeleton variant={variant as 'card' | 'text' | 'avatar' | 'table-row'} className={className} />;
});
