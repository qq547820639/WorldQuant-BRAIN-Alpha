/**
 * useNetworkError - 监听网络在线/离线状态
 * 提供自动重试机制（指数退避）
 */
import { useState, useEffect, useCallback, useRef } from 'react';

interface UseNetworkErrorOptions {
  maxRetries?: number;
  baseDelay?: number;
  maxDelay?: number;
  enableAutoRetry?: boolean;
}

interface UseNetworkErrorResult {
  isOnline: boolean;
  isReconnecting: boolean;
  retryCount: number;
  lastError: Error | null;
  retry: () => void;
  reset: () => void;
}

export function useNetworkError(
  options: UseNetworkErrorOptions = {}
): UseNetworkErrorResult {
  const {
    maxRetries = 5,
    baseDelay = 1000,
    maxDelay = 30000,
    enableAutoRetry = true,
  } = options;

  const [isOnline, setIsOnline] = useState<boolean>(
    typeof navigator !== 'undefined' ? navigator.onLine : true
  );
  const [isReconnecting, setIsReconnecting] = useState(false);
  const [retryCount, setRetryCount] = useState(0);
  const [lastError, setLastError] = useState<Error | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retryCountRef = useRef(0);

  const calculateDelay = useCallback(
    (attempt: number): number => {
      const delay = baseDelay * Math.pow(2, attempt);
      return Math.min(delay, maxDelay);
    },
    [baseDelay, maxDelay]
  );

  const checkOnlineStatus = useCallback((): boolean => {
    return typeof navigator !== 'undefined' ? navigator.onLine : true;
  }, []);

  const retry = useCallback(() => {
    if (isReconnecting) return;

    const currentlyOnline = checkOnlineStatus();
    if (currentlyOnline) {
      setIsOnline(true);
      setIsReconnecting(false);
      setLastError(null);
      setRetryCount(0);
      retryCountRef.current = 0;
      return;
    }

    setIsReconnecting(true);
    setLastError(new Error('网络连接已断开'));

    const attemptRetry = (attempt: number) => {
      if (attempt > maxRetries) {
        setIsReconnecting(false);
        return;
      }

      const delay = calculateDelay(attempt);
      retryCountRef.current = attempt;
      setRetryCount(attempt);

      timeoutRef.current = setTimeout(() => {
        const online = checkOnlineStatus();
        if (online) {
          setIsOnline(true);
          setIsReconnecting(false);
          setLastError(null);
          setRetryCount(0);
          retryCountRef.current = 0;
        } else {
          attemptRetry(attempt + 1);
        }
      }, delay);
    };

    attemptRetry(retryCountRef.current + 1);
  }, [isReconnecting, checkOnlineStatus, maxRetries, calculateDelay]);

  const reset = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    setIsOnline(checkOnlineStatus());
    setIsReconnecting(false);
    setRetryCount(0);
    setLastError(null);
    retryCountRef.current = 0;
  }, [checkOnlineStatus]);

  useEffect(() => {
    const handleOnline = () => {
      setIsOnline(true);
      setIsReconnecting(false);
      setLastError(null);
      setRetryCount(0);
      retryCountRef.current = 0;
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
    };

    const handleOffline = () => {
      setIsOnline(false);
      setLastError(new Error('网络连接已断开'));
      if (enableAutoRetry) {
        retry();
      }
    };

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
    };
  }, [enableAutoRetry, retry]);

  return {
    isOnline,
    isReconnecting,
    retryCount,
    lastError,
    retry,
    reset,
  };
}
