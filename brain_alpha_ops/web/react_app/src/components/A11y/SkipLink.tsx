import { useState } from 'react';

interface SkipLinkProps {
  targetId: string;
  label?: string;
  className?: string;
  /** 平滑滚动并在滚动后聚焦目标，默认 true */
  smooth?: boolean;
}

const hiddenStyle: React.CSSProperties = {
  position: 'absolute',
  left: '-9999px',
  top: 'auto',
  width: '1px',
  height: '1px',
  overflow: 'hidden',
};

const visibleStyle: React.CSSProperties = {
  position: 'absolute',
  left: '16px',
  top: '16px',
  width: 'auto',
  height: 'auto',
  overflow: 'visible',
  zIndex: 9999,
};

/**
 * 跳转链接（Skip Link）：键盘用户聚焦时显示，点击后跳转到目标容器。
 */
export default function SkipLink({
  targetId,
  label = '跳转到主要内容',
  className,
  smooth = true,
}: SkipLinkProps) {
  const [focused, setFocused] = useState(false);

  const handleClick = (event: React.MouseEvent<HTMLAnchorElement>) => {
    if (event.defaultPrevented) return;
    const target = document.getElementById(targetId);
    if (!target) return;
    if (smooth) {
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      target.focus();
    } else {
      target.focus({ preventScroll: true });
    }
  };

  return (
    <a
      href={`#${targetId}`}
      className={className}
      style={focused ? visibleStyle : hiddenStyle}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      onClick={handleClick}
    >
      {label}
    </a>
  );
}
