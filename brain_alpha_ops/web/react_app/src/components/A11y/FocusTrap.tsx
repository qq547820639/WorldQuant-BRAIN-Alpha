/**
 * FocusTrap — 模态框焦点陷阱组件
 * 防止焦点移出对话框，确保键盘用户的可访问性
 * 支持初始焦点设置和关闭时焦点恢复
 */
import { memo, useEffect, useRef, useCallback, type ReactNode } from 'react';

interface FocusTrapProps {
  active?: boolean;
  children: ReactNode;
  initialFocusRef?: React.RefObject<HTMLElement>;
  restoreFocusRef?: React.RefObject<HTMLElement>;
  onEscape?: () => void;
  className?: string;
}

export default memo(function FocusTrap({
  active = true,
  children,
  initialFocusRef,
  restoreFocusRef,
  onEscape,
  className = '',
}: FocusTrapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  const getFocusableElements = useCallback(() => {
    if (!containerRef.current) return [];
    const focusableSelectors = [
      'a[href]:not([disabled])',
      'button:not([disabled])',
      'textarea:not([disabled])',
      'input:not([disabled])',
      'select:not([disabled])',
      '[tabindex]:not([tabindex="-1"])',
    ];
    return Array.from(
      containerRef.current.querySelectorAll<HTMLElement>(focusableSelectors.join(','))
    );
  }, []);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!active || e.key !== 'Tab') return;

      const focusableElements = getFocusableElements();
      if (focusableElements.length === 0) return;

      const firstElement = focusableElements[0];
      const lastElement = focusableElements[focusableElements.length - 1];

      if (e.shiftKey) {
        if (document.activeElement === firstElement) {
          e.preventDefault();
          lastElement.focus();
        }
      } else {
        if (document.activeElement === lastElement) {
          e.preventDefault();
          firstElement.focus();
        }
      }
    },
    [active, getFocusableElements]
  );

  const handleEscape = useCallback(
    (e: KeyboardEvent) => {
      if (!active || e.key !== 'Escape') return;
      onEscape?.();
    },
    [active, onEscape]
  );

  useEffect(() => {
    if (!active) return;

    previousFocusRef.current = document.activeElement as HTMLElement;

    if (initialFocusRef?.current) {
      initialFocusRef.current.focus();
    } else if (containerRef.current) {
      const focusableElements = getFocusableElements();
      if (focusableElements.length > 0) {
        focusableElements[0].focus();
      }
    }

    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('keydown', handleEscape);

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('keydown', handleEscape);

      const restoreTarget = restoreFocusRef?.current || previousFocusRef.current;
      if (restoreTarget && typeof restoreTarget.focus === 'function') {
        restoreTarget.focus();
      }
    };
  }, [active, initialFocusRef, restoreFocusRef, handleKeyDown, handleEscape, getFocusableElements]);

  return (
    <div ref={containerRef} className={className}>
      {children}
    </div>
  );
});
