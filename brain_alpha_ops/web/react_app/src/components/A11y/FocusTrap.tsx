import { useEffect, useRef } from 'react';

interface FocusTrapProps {
  /** 是否启用焦点陷阱，默认 false */
  active?: boolean;
  /** 激活时初始聚焦的元素 ref */
  initialFocusRef?: React.RefObject<HTMLElement | null>;
  /** 按下 Escape 时回调 */
  onEscape?: () => void;
  className?: string;
  children: React.ReactNode;
}

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * 焦点陷阱：激活时限制 Tab 焦点在容器内循环，并在取消激活时恢复焦点。
 */
export default function FocusTrap({
  active = false,
  initialFocusRef,
  onEscape,
  className,
  children,
}: FocusTrapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const prevFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!active) return;
    prevFocusRef.current = document.activeElement as HTMLElement | null;

    const getFocusables = (): HTMLElement[] => {
      if (!containerRef.current) return [];
      return Array.from(
        containerRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
      ).filter((el) => el.isConnected);
    };

    const focusables = getFocusables();
    const target =
      initialFocusRef?.current && focusables.includes(initialFocusRef.current)
        ? initialFocusRef.current
        : focusables[0];
    target?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onEscape?.();
        return;
      }
      if (event.key !== 'Tab') return;
      const current = getFocusables();
      if (current.length === 0) return;
      const currentIndex = current.indexOf(document.activeElement as HTMLElement);
      event.preventDefault();
      if (event.shiftKey) {
        const prev = currentIndex <= 0 ? current.length - 1 : currentIndex - 1;
        current[prev]?.focus();
      } else {
        const next = currentIndex >= current.length - 1 ? 0 : currentIndex + 1;
        current[next]?.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      prevFocusRef.current?.focus();
    };
  }, [active, initialFocusRef, onEscape]);

  return (
    <div ref={containerRef} className={className}>
      {children}
    </div>
  );
}
