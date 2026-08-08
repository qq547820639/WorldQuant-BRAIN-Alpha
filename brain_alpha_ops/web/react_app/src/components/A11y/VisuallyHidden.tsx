import * as React from 'react';

type VisuallyHiddenTag = 'span' | 'div' | 'p' | 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'h6' | 'label';

interface VisuallyHiddenProps extends React.HTMLAttributes<HTMLElement> {
  as?: VisuallyHiddenTag;
}

const visuallyHiddenStyle: React.CSSProperties = {
  position: 'absolute',
  width: '1px',
  height: '1px',
  padding: '0px',
  overflow: 'hidden',
  clip: 'rect(0px, 0px, 0px, 0px)',
  whiteSpace: 'nowrap',
  border: '0px',
};

/**
 * 视觉隐藏组件：内容对可见用户隐藏，但对屏幕阅读器仍可访问。
 */
export default function VisuallyHidden({ as: Tag = 'span', style, ...rest }: VisuallyHiddenProps) {
  return <Tag {...rest} style={{ ...visuallyHiddenStyle, ...style }} />;
}
