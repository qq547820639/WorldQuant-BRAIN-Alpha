/**
 * ButtonLoader — 按钮内加载状态组件
 * 在按钮内显示加载指示器，替换按钮文字
 */
import { memo, type ReactNode } from 'react';
import Spinner from './Spinner';

interface ButtonLoaderProps {
  loading?: boolean;
  children: ReactNode;
  className?: string;
  size?: 'xs' | 'sm' | 'md';
}

export default memo(function ButtonLoader({
  loading = false,
  children,
  className = '',
  size = 'sm',
}: ButtonLoaderProps) {
  return (
    <span className={`inline-flex items-center justify-center gap-2 ${className}`}>
      {loading && <Spinner size={size} />}
      <span style={{ opacity: loading ? 0 : 1 }}>{children}</span>
    </span>
  );
});
