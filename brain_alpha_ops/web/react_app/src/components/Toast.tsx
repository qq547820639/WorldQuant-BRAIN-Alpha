import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';

export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface ToastItem {
  id: string;
  type: ToastType;
  title: string;
  description?: string;
  duration?: number;
}

export interface ToastOptions {
  title: string;
  description?: string;
  duration?: number;
}

export interface ToastContextValue {
  success: (options: string | ToastOptions) => string;
  error: (options: string | ToastOptions) => string;
  warning: (options: string | ToastOptions) => string;
  info: (options: string | ToastOptions) => string;
  remove: (id: string) => void;
  clear: () => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const DEFAULT_DURATION = 3000;
const MAX_TOASTS = 5;

const ICONS: Record<ToastType, JSX.Element> = {
  success: (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
      <polyline points="22 4 12 14.01 9 11.01" />
    </svg>
  ),
  error: (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="12" cy="12" r="10" />
      <line x1="15" y1="9" x2="9" y2="15" />
      <line x1="9" y1="9" x2="15" y2="15" />
    </svg>
  ),
  warning: (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  ),
  info: (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="16" x2="12" y2="12" />
      <line x1="12" y1="8" x2="12.01" y2="8" />
    </svg>
  ),
};

const COLOR_MAP: Record<ToastType, { icon: string; border: string; bg: string }> = {
  success: {
    icon: 'text-positive',
    border: 'border-l-positive',
    bg: 'bg-positive-subtle/40',
  },
  error: {
    icon: 'text-negative',
    border: 'border-l-negative',
    bg: 'bg-negative-subtle/40',
  },
  warning: {
    icon: 'text-warning',
    border: 'border-l-warning',
    bg: 'bg-warning-subtle/40',
  },
  info: {
    icon: 'text-info',
    border: 'border-l-info',
    bg: 'bg-info-subtle/40',
  },
};

let counter = 0;
const generateId = () => `toast_${++counter}_${Date.now()}`;

interface SingleToastProps {
  toast: ToastItem;
  onClose: (id: string) => void;
}

function SingleToast({ toast, onClose }: SingleToastProps) {
  const [isVisible, setIsVisible] = useState(false);
  const [isExiting, setIsExiting] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [progress, setProgress] = useState(100);
  const duration = toast.duration ?? DEFAULT_DURATION;
  const startTimeRef = useRef<number>(0);
  const remainingRef = useRef<number>(duration);
  const animationFrameRef = useRef<number | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => setIsVisible(true), 10);
    return () => clearTimeout(timer);
  }, []);

  const startTimer = useCallback(
    (remaining: number) => {
      if (duration <= 0) return;
      startTimeRef.current = Date.now();
      remainingRef.current = remaining;

      const updateProgress = () => {
        const elapsed = Date.now() - startTimeRef.current;
        const newProgress = Math.max(0, ((remainingRef.current - elapsed) / duration) * 100);
        setProgress(newProgress);

        if (elapsed >= remainingRef.current) {
          handleClose();
          return;
        }
        animationFrameRef.current = requestAnimationFrame(updateProgress);
      };

      animationFrameRef.current = requestAnimationFrame(updateProgress);
    },
    [duration]
  );

  // eslint-disable-next-line react-hooks/preserve-manual-memoization -- 回调内 mutate animationFrameRef.current，React Compiler 跳过保留；手动 memo 保证 handleClose 引用稳定，避免 startTimer/effect 链路无谓重渲染
  const handleClose = useCallback(() => {
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
    setIsExiting(true);
    setTimeout(() => {
      onClose(toast.id);
    }, 200);
  }, [onClose, toast.id]);

  useEffect(() => {
    if (duration > 0 && !isPaused && isVisible && !isExiting) {
      startTimer(remainingRef.current);
    }
    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [isPaused, isVisible, isExiting, startTimer, duration]);

  const colors = COLOR_MAP[toast.type];
  const isUrgent = toast.type === 'error';

  return (
    <div
      role={isUrgent ? 'alert' : 'status'}
      aria-live={isUrgent ? 'assertive' : 'polite'}
      aria-atomic="true"
      className={`
        relative flex items-start gap-3 px-4 py-3 pr-10
        bg-surface-3 border border-border-strong border-l-4 ${colors.border}
        rounded-md shadow-lg
        min-w-[300px] max-w-[420px]
        transition-all duration-200 ease-out
        ${isVisible && !isExiting ? 'opacity-100 translate-x-0' : 'opacity-0 translate-x-4'}
      `}
      onMouseEnter={() => setIsPaused(true)}
      onMouseLeave={() => setIsPaused(false)}
      style={{ willChange: 'transform, opacity' }}
    >
      <div className={`shrink-0 mt-0.5 ${colors.icon}`} aria-hidden="true">
        {ICONS[toast.type]}
      </div>

      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-text-primary leading-tight">{toast.title}</p>
        {toast.description && (
          <p className="text-xs text-text-secondary mt-1 leading-relaxed break-words">
            {toast.description}
          </p>
        )}
      </div>

      <button
        type="button"
        className="absolute top-2 right-2 p-1 rounded-sm text-text-tertiary hover:text-text-primary hover:bg-surface-hover transition-colors"
        onClick={handleClose}
        aria-label="关闭通知"
      >
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>

      {duration > 0 && (
        <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-surface-hover rounded-b-md overflow-hidden">
          <div
            className={`h-full ${colors.icon.replace('text-', 'bg-')} transition-none`}
            style={{ width: `${progress}%` }}
            aria-hidden="true"
          />
        </div>
      )}
    </div>
  );
}

interface ToastContainerProps {
  toasts: ToastItem[];
  onRemove: (id: string) => void;
}

export function ToastContainer({ toasts, onRemove }: ToastContainerProps) {
  if (toasts.length === 0) return null;

  return (
    <div className="fixed top-4 right-4 z-[1000] flex flex-col gap-2" aria-label="通知区域">
      {toasts.map((toast) => (
        <SingleToast key={toast.id} toast={toast} onClose={onRemove} />
      ))}
    </div>
  );
}

interface ToastProviderProps {
  children: ReactNode;
  maxToasts?: number;
}

export function ToastProvider({ children, maxToasts = MAX_TOASTS }: ToastProviderProps) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const timersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const remove = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
    const timer = timersRef.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timersRef.current.delete(id);
    }
  }, []);

  const addToast = useCallback(
    (type: ToastType, options: string | ToastOptions): string => {
      const id = generateId();
      const toast: ToastItem = {
        id,
        type,
        title: typeof options === 'string' ? options : options.title,
        description: typeof options === 'string' ? undefined : options.description,
        duration: typeof options === 'string' ? undefined : options.duration,
      };

      setToasts((prev) => {
        const next = [toast, ...prev];
        if (next.length > maxToasts) {
          const toRemove = next.slice(maxToasts);
          toRemove.forEach((t) => {
            const timer = timersRef.current.get(t.id);
            if (timer) {
              clearTimeout(timer);
              timersRef.current.delete(t.id);
            }
          });
          return next.slice(0, maxToasts);
        }
        return next;
      });

      return id;
    },
    [maxToasts]
  );

  const clear = useCallback(() => {
    setToasts([]);
    timersRef.current.forEach((timer) => clearTimeout(timer));
    timersRef.current.clear();
  }, []);

  const success = useCallback(
    (options: string | ToastOptions) => addToast('success', options),
    [addToast]
  );
  const error = useCallback(
    (options: string | ToastOptions) => addToast('error', options),
    [addToast]
  );
  const warning = useCallback(
    (options: string | ToastOptions) => addToast('warning', options),
    [addToast]
  );
  const info = useCallback(
    (options: string | ToastOptions) => addToast('info', options),
    [addToast]
  );

  const value = useMemo<ToastContextValue>(
    () => ({ success, error, warning, info, remove, clear }),
    [success, error, warning, info, remove, clear]
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <ToastContainer toasts={toasts} onRemove={remove} />
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
}
