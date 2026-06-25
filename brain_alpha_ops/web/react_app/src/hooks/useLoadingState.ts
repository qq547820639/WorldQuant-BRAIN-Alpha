/**
 * useLoadingState - 管理 loading/error 状态
 * 支持最小显示时长，避免加载状态闪烁
 * 提供 runWithLoading 自动包装异步函数
 */
import { useState, useCallback, useRef } from 'react';

interface UseLoadingStateOptions {
  initialLoading?: boolean;
  minDuration?: number;
}

interface UseLoadingStateResult<TError = Error> {
  isLoading: boolean;
  error: TError | null;
  hasError: boolean;
  runWithLoading: <TResult>(fn: () => Promise<TResult>) => Promise<TResult>;
  setLoading: (loading: boolean) => void;
  setError: (error: TError | null) => void;
  reset: () => void;
}

export function useLoadingState<TError = Error>(
  options: UseLoadingStateOptions = {}
): UseLoadingStateResult<TError> {
  const { initialLoading = false, minDuration = 300 } = options;
  const [isLoading, setIsLoading] = useState(initialLoading);
  const [error, setError] = useState<TError | null>(null);
  const loadingStartTimeRef = useRef<number>(0);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const startLoading = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    loadingStartTimeRef.current = Date.now();
    setIsLoading(true);
    setError(null);
  }, []);

  const stopLoading = useCallback(() => {
    const elapsed = Date.now() - loadingStartTimeRef.current;
    const remaining = Math.max(0, minDuration - elapsed);

    if (remaining > 0) {
      timeoutRef.current = setTimeout(() => {
        setIsLoading(false);
        timeoutRef.current = null;
      }, remaining);
    } else {
      setIsLoading(false);
    }
  }, [minDuration]);

  const runWithLoading = useCallback(
    async <TResult>(fn: () => Promise<TResult>): Promise<TResult> => {
      startLoading();
      try {
        const result = await fn();
        stopLoading();
        return result;
      } catch (err) {
        setError(err as TError);
        stopLoading();
        throw err;
      }
    },
    [startLoading, stopLoading]
  );

  const reset = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    setIsLoading(false);
    setError(null);
  }, []);

  const setLoading = useCallback((loading: boolean) => {
    if (loading) {
      startLoading();
    } else {
      stopLoading();
    }
  }, [startLoading, stopLoading]);

  return {
    isLoading,
    error,
    hasError: error !== null,
    runWithLoading,
    setLoading,
    setError,
    reset,
  };
}
