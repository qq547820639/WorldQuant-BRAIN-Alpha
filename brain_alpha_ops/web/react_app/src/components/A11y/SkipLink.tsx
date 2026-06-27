/**
 * SkipLink — 跳过导航链接组件
 * 让键盘用户快速跳到主内容区域，符合 WCAG 2.4.1 标准
 * 默认视觉上隐藏，聚焦时才可见
 */
import { memo, useCallback } from 'react';

interface SkipLinkProps {
  targetId: string;
  label?: string;
  className?: string;
  smooth?: boolean;
}

export default memo(function SkipLink({
  targetId,
  label = '跳转到主要内容',
  className = '',
  smooth = true,
}: SkipLinkProps) {
  const handleClick = useCallback(
    (e: React.MouseEvent<HTMLAnchorElement>) => {
      e.preventDefault();
      const target = document.getElementById(targetId);
      if (target) {
        target.setAttribute('tabindex', '-1');
        target.focus({ preventScroll: !smooth });
        if (smooth) {
          target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
        const handleBlur = () => {
          target.removeAttribute('tabindex');
          target.removeEventListener('blur', handleBlur);
        };
        target.addEventListener('blur', handleBlur);
      }
    },
    [targetId, smooth]
  );

  return (
    <a
      href={`#${targetId}`}
      onClick={handleClick}
      className={`sr-only-focusable ${className}`}
      style={{
        position: 'absolute',
        left: '-9999px',
        top: 'auto',
        width: '1px',
        height: '1px',
        overflow: 'hidden',
        zIndex: 1000,
      }}
      onFocus={(e) => {
        e.currentTarget.style.left = '16px';
        e.currentTarget.style.top = '16px';
        e.currentTarget.style.width = 'auto';
        e.currentTarget.style.height = 'auto';
        e.currentTarget.style.padding = '8px 16px';
        e.currentTarget.style.background = 'var(--color-surface-elevated)';
        e.currentTarget.style.border = '1px solid var(--color-border-medium)';
        e.currentTarget.style.borderRadius = '6px';
        e.currentTarget.style.color = 'var(--color-text-primary)';
        e.currentTarget.style.fontSize = '14px';
        e.currentTarget.style.fontWeight = '500';
      }}
      onBlur={(e) => {
        e.currentTarget.style.left = '-9999px';
        e.currentTarget.style.top = 'auto';
        e.currentTarget.style.width = '1px';
        e.currentTarget.style.height = '1px';
        e.currentTarget.style.padding = '0';
        e.currentTarget.style.background = 'transparent';
        e.currentTarget.style.border = 'none';
      }}
    >
      {label}
    </a>
  );
});
