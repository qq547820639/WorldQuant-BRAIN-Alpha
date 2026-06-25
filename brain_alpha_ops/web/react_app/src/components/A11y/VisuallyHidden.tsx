/**
 * VisuallyHidden — 屏幕阅读器专用文本组件
 * 视觉上隐藏，但对屏幕阅读器等辅助技术可见
 * 支持多种 HTML 标签
 */
import { memo, type ElementType, type ReactNode } from 'react';

type VisuallyHiddenTag = 'span' | 'div' | 'p' | 'label' | 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'h6';

interface VisuallyHiddenProps<T extends VisuallyHiddenTag = 'span'> {
  as?: T;
  children: ReactNode;
  className?: string;
  htmlFor?: string;
  id?: string;
}

const visuallyHiddenStyle: React.CSSProperties = {
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

export default memo(function VisuallyHidden<T extends VisuallyHiddenTag = 'span'>({
  as,
  children,
  className = '',
  ...rest
}: VisuallyHiddenProps<T>) {
  const Component = (as || 'span') as ElementType;
  return (
    <Component className={className} style={visuallyHiddenStyle} {...rest}>
      {children}
    </Component>
  );
}) as <T extends VisuallyHiddenTag = 'span'>(props: VisuallyHiddenProps<T>) => JSX.Element;
