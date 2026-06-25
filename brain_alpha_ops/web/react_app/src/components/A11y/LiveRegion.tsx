/**
 * LiveRegion — ARIA 实时区域组件
 * 用于动态内容通知，屏幕阅读器会自动播报内容变化
 * 支持 polite 和 assertive 两种礼貌级别
 */
import { memo, useEffect, useState, type ReactNode } from 'react';

type AriaLive = 'polite' | 'assertive' | 'off';

interface LiveRegionProps {
  message?: string;
  politeness?: AriaLive;
  atomic?: boolean;
  relevant?: 'additions' | 'removals' | 'text' | 'all' | 'additions text';
  children?: ReactNode;
  className?: string;
  role?: 'status' | 'alert' | 'log' | 'marquee' | 'timer' | 'region';
}

export default memo(function LiveRegion({
  message,
  politeness = 'polite',
  atomic = true,
  relevant = 'additions text',
  children,
  className = '',
  role,
}: LiveRegionProps) {
  const [displayMessage, setDisplayMessage] = useState(message || '');

  useEffect(() => {
    if (message !== undefined) {
      setDisplayMessage('');
      const timer = setTimeout(() => {
        setDisplayMessage(message);
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [message]);

  const liveRegionStyle: React.CSSProperties = {
    position: 'absolute',
    width: '1px',
    height: '1px',
    padding: 0,
    margin: '-1px',
    overflow: 'hidden',
    clip: 'rect(0, 0, 0, 0)',
    whiteSpace: 'nowrap',
    border: 0,
  };

  return (
    <div
      className={className}
      style={liveRegionStyle}
      aria-live={politeness}
      aria-atomic={atomic}
      aria-relevant={relevant}
      role={role}
    >
      {children || displayMessage}
    </div>
  );
});
