import { useCallback, useEffect, useRef, useState } from 'react';

export interface UseLoadingStateOptions {
  /** 初始 loading 状态，默认 false */
  initialLoading?: boolean;
  /** loading 最短展示时长（毫秒），默认 300ms */
  minDuration?: number;
}

export interface UseLoadingStateResult {
  isLoading: boolean;
  error: Error | null;
  hasError: boolean;
  setLoading: (loading: boolean) => void;
  setError: (error: Error | null) => void;
  reset: () => void;
  /** 以 loading 状态包裹一个异步函数，出错时记录 error 并重新抛出 */
  runWithLoading: <T>(fn: () => Promise<T>) => Promise<T>;
}

/**
 * 统一的 loading / error 状态管理 hook。
 * 支持最短展示时长（避免闪屏），runWithLoading 便捷地包裹异步任务。
 */
export function useLoadingState(options: UseLoadingStateOptions = {}): UseLoadingStateResult {
  const { initialLoading = false, minDuration = 300 } = options;

  const [isLoading, setIsLoading] = useState(initialLoading);
  const [error, setErrorState] = useState<Error | null>(null);

  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const loadStartedAtRef = useRef<number>(0);

  const clearHideTimer = useCallback(() => {
    if (hideTimerRef.current !== null) {
      clearTimeout(hideTimerRef.current);
      hideTimerRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => clearHideTimer();
  }, [clearHideTimer]);

  const setLoading = useCallback(
    (loading: boolean) => {
      if (loading) {
        loadStartedAtRef.current = Date.now();
        clearHideTimer();
        setIsLoading(true);
        return;
      }
      const elapsed = Date.now() - loadStartedAtRef.current;
      const remaining = minDuration - elapsed;
      if (remaining > 0) {
        clearHideTimer();
        hideTimerRef.current = setTimeout(() => {
          setIsLoading(false);
          hideTimerRef.current = null;
        }, remaining);
      } else {
        clearHideTimer();
        setIsLoading(false);
      }
    },
    [minDuration, clearHideTimer]
  );

  const setError = useCallback((nextError: Error | null) => {
    setErrorState(nextError);
  }, []);

  const reset = useCallback(() => {
    clearHideTimer();
    setIsLoading(false);
    setErrorState(null);
  }, [clearHideTimer]);

  const runWithLoading = useCallback(
    async <T>(fn: () => Promise<T>): Promise<T> => {
      setErrorState(null);
      setLoading(true);
      try {
        const result = await fn();
        setLoading(false);
        return result;
      } catch (err) {
        setLoading(false);
        setErrorState(err instanceof Error ? err : new Error(String(err)));
        throw err;
      }
    },
    [setLoading]
  );

  return {
    isLoading,
    error,
    hasError: error !== null,
    setLoading,
    setError,
    reset,
    runWithLoading,
  };
}

export default useLoadingState;
