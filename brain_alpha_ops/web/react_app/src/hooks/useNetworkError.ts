import { useCallback, useEffect, useRef, useState } from 'react';

export interface UseNetworkErrorOptions {
  /** 断线时是否自动进入重连状态，默认 true */
  enableAutoRetry?: boolean;
  /** 自动重试延迟（毫秒），默认 3000ms */
  retryDelay?: number;
}

export interface UseNetworkErrorResult {
  isOnline: boolean;
  isReconnecting: boolean;
  retryCount: number;
  lastError: Error | null;
  retry: () => void;
  reset: () => void;
}

function isNavigatorOnline(): boolean {
  return typeof navigator !== 'undefined' ? navigator.onLine : true;
}

/**
 * 网络在线/离线状态管理 hook。
 * 监听 window 的 `online`/`offline` 事件，并提供手动重试与重置能力。
 */
export function useNetworkError(options: UseNetworkErrorOptions = {}): UseNetworkErrorResult {
  const { enableAutoRetry = true, retryDelay = 3000 } = options;

  const [isOnline, setIsOnline] = useState<boolean>(isNavigatorOnline());
  const [isReconnecting, setIsReconnecting] = useState(false);
  const [retryCount, setRetryCount] = useState(0);
  const [lastError, setLastError] = useState<Error | null>(null);

  const onLineRef = useRef<boolean>(isOnline);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const handleOnline = useCallback(() => {
    clearTimer();
    onLineRef.current = true;
    setIsOnline(true);
    setIsReconnecting(false);
    setRetryCount(0);
    setLastError(null);
  }, [clearTimer]);

  const retry = useCallback(() => {
    if (isNavigatorOnline()) {
      handleOnline();
      return;
    }
    if (isReconnecting) {
      return;
    }
    clearTimer();
    setIsReconnecting(true);
    setRetryCount((count) => count + 1);
    setLastError(new Error('网络连接已断开，正在重试…'));
    timerRef.current = setTimeout(() => {
      setIsReconnecting(false);
      if (isNavigatorOnline()) {
        handleOnline();
      }
    }, retryDelay);
  }, [isReconnecting, retryDelay, clearTimer, handleOnline]);

  const handleOffline = useCallback(() => {
    onLineRef.current = false;
    setIsOnline(false);
    setLastError(new Error('网络连接已断开'));
    if (enableAutoRetry) {
      retry();
    }
  }, [enableAutoRetry, retry]);

  const reset = useCallback(() => {
    clearTimer();
    const online = isNavigatorOnline();
    onLineRef.current = online;
    setIsOnline(online);
    setIsReconnecting(false);
    setRetryCount(0);
    setLastError(null);
  }, [clearTimer]);

  useEffect(() => {
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
      clearTimer();
    };
  }, [handleOnline, handleOffline, clearTimer]);

  return {
    isOnline,
    isReconnecting,
    retryCount,
    lastError,
    retry,
    reset,
  };
}

export default useNetworkError;
