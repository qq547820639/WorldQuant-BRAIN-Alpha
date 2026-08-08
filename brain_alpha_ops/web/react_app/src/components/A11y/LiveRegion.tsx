import { useEffect, useState } from 'react';

interface LiveRegionProps {
  message?: string;
  children?: React.ReactNode;
  politeness?: 'polite' | 'assertive' | 'off';
  atomic?: boolean;
  className?: string;
  role?: string;
  /** 消息更新延迟（毫秒），默认 50ms，避免屏幕阅读器读到中间态 */
  delay?: number;
}

/**
 * 无障碍实时区域（Live Region）：向屏幕阅读器播报动态内容。
 * 默认以视觉隐藏方式渲染，不影响页面布局。
 */
export default function LiveRegion({
  message,
  children,
  politeness = 'polite',
  atomic = true,
  className,
  role,
  delay = 50,
}: LiveRegionProps) {
  const [shownMessage, setShownMessage] = useState(message);

  useEffect(() => {
    if (message === undefined) return;
    const timer = setTimeout(() => setShownMessage(message), delay);
    return () => clearTimeout(timer);
  }, [message, delay]);

  return (
    <div
      className={className}
      role={role}
      aria-live={politeness}
      aria-atomic={atomic}
      aria-relevant="additions text"
      style={{ position: 'absolute', width: '1px', height: '1px', overflow: 'hidden' }}
    >
      {children ?? shownMessage}
    </div>
  );
}
