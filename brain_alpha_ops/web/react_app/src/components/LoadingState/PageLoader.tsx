/**
 * PageLoader — 页面加载状态组件
 * 全屏/全容器居中的加载指示器
 */
import { memo } from 'react';
import Spinner from './Spinner';

interface PageLoaderProps {
  message?: string;
  size?: 'sm' | 'md' | 'lg' | 'xl';
  className?: string;
  minHeight?: string | number;
}

export default memo(function PageLoader({
  message,
  size = 'lg',
  className = '',
  minHeight = 200,
}: PageLoaderProps) {
  return (
    <div
      className={`flex flex-col items-center justify-center gap-4 ${className}`}
      style={{ minHeight: typeof minHeight === 'number' ? `${minHeight}px` : minHeight }}
    >
      <Spinner size={size} />
      {message && (
        <p className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
          {message}
        </p>
      )}
    </div>
  );
});
