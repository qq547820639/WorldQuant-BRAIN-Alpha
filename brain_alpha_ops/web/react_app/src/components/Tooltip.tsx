import { memo, useState, useRef, useId, useEffect } from 'react';

type TooltipPlacement = 'top' | 'bottom' | 'left' | 'right';

interface TooltipProps {
  content: string;
  placement?: TooltipPlacement;
  delay?: number;
  children: React.ReactElement;
}

export default memo(function Tooltip({
  content,
  placement = 'top',
  delay = 300,
  children,
}: TooltipProps) {
  const [visible, setVisible] = useState(false);
  const [mounted, setMounted] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const tooltipId = useId();
  const wrapperRef = useRef<HTMLSpanElement>(null);

  const showTooltip = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      setMounted(true);
      setTimeout(() => setVisible(true), 10);
    }, delay);
  };

  const hideTooltip = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setVisible(false);
    timerRef.current = setTimeout(() => {
      setMounted(false);
    }, 150);
  };

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const positionStyles: Record<TooltipPlacement, React.CSSProperties> = {
    top: {
      bottom: '100%',
      left: '50%',
      transform: 'translateX(-50%)',
      marginBottom: 8,
    },
    bottom: {
      top: '100%',
      left: '50%',
      transform: 'translateX(-50%)',
      marginTop: 8,
    },
    left: {
      right: '100%',
      top: '50%',
      transform: 'translateY(-50%)',
      marginRight: 8,
    },
    right: {
      left: '100%',
      top: '50%',
      transform: 'translateY(-50%)',
      marginLeft: 8,
    },
  };

  const arrowStyles: Record<TooltipPlacement, React.CSSProperties> = {
    top: {
      top: '100%',
      left: '50%',
      transform: 'translateX(-50%)',
      borderLeft: '5px solid transparent',
      borderRight: '5px solid transparent',
      borderTop: '5px solid var(--color-surface-deep)',
    },
    bottom: {
      bottom: '100%',
      left: '50%',
      transform: 'translateX(-50%)',
      borderLeft: '5px solid transparent',
      borderRight: '5px solid transparent',
      borderBottom: '5px solid var(--color-surface-deep)',
    },
    left: {
      left: '100%',
      top: '50%',
      transform: 'translateY(-50%)',
      borderTop: '5px solid transparent',
      borderBottom: '5px solid transparent',
      borderLeft: '5px solid var(--color-surface-deep)',
    },
    right: {
      right: '100%',
      top: '50%',
      transform: 'translateY(-50%)',
      borderTop: '5px solid transparent',
      borderBottom: '5px solid transparent',
      borderRight: '5px solid var(--color-surface-deep)',
    },
  };

  const animationClass = visible
    ? placement === 'top' || placement === 'bottom'
      ? 'tooltip-fade-y'
      : 'tooltip-fade-x'
    : '';

  const childWithA11y =
    typeof children.type === 'string'
      ? children
      : {
          ...children,
          props: {
            ...children.props,
            'aria-describedby': tooltipId,
          },
        };

  return (
    <span
      ref={wrapperRef}
      tabIndex={0}
      style={{ display: 'inline-block', position: 'relative' }}
      onMouseEnter={showTooltip}
      onMouseLeave={hideTooltip}
      onFocus={showTooltip}
      onBlur={hideTooltip}
    >
      {childWithA11y}
      {mounted && (
        <div
          id={tooltipId}
          role="tooltip"
          className={`tooltip-panel ${animationClass}`}
          style={{
            position: 'absolute',
            zIndex: 1000,
            pointerEvents: 'none',
            ...positionStyles[placement],
            background: 'var(--color-surface-deep)',
            border: '0.5px solid var(--color-border-default)',
            borderRadius: 6,
            padding: '6px 10px',
            fontSize: 12,
            lineHeight: 1.4,
            color: 'var(--color-text-bright)',
            boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)',
            maxWidth: '280px',
            whiteSpace: 'normal',
            wordBreak: 'break-word',
          }}
        >
          {content}
          <span
            style={{
              position: 'absolute',
              width: 0,
              height: 0,
              ...arrowStyles[placement],
            }}
          />
          <style>{`
            @keyframes tooltip-fade-in-y {
              from {
                opacity: 0;
                transform: translateX(-50%) translateY(${placement === 'top' ? '4px' : '-4px'});
              }
              to {
                opacity: 1;
                transform: translateX(-50%) translateY(0);
              }
            }
            @keyframes tooltip-fade-in-x {
              from {
                opacity: 0;
                transform: translateY(-50%) translateX(${placement === 'left' ? '4px' : '-4px'});
              }
              to {
                opacity: 1;
                transform: translateY(-50%) translateX(0);
              }
            }
            .tooltip-fade-y {
              animation: tooltip-fade-in-y 150ms cubic-bezier(0.16, 1, 0.3, 1) both;
            }
            .tooltip-fade-x {
              animation: tooltip-fade-in-x 150ms cubic-bezier(0.16, 1, 0.3, 1) both;
            }
            @media (prefers-reduced-motion: reduce) {
              .tooltip-fade-y,
              .tooltip-fade-x {
                animation: none;
                opacity: 1;
              }
            }
          `}</style>
        </div>
      )}
    </span>
  );
});
