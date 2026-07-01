/**
 * @deprecated Use useSseEventHandler from './useSseEventHandler' instead.
 */

import { useState, useRef, useCallback } from 'react';
import { SSE_RETRY_DELAYS, SSE_MAX_RETRIES } from './constants';
import type { NotifyFn } from './types';

export interface UseSseRetryStateOptions {
  notify: NotifyFn;
  onResume: () => void;
  onExhausted: (message: string) => void;
}

export interface SseRetryState {
  sseRetryCountdown: number;
  sseRetryExhausted: boolean;
  clearSseRetryTimers: () => void;
  resetSseRetryState: () => void;
  handleStreamExhausted: () => void;
  handleSseExhaustedManualRetry: () => void;
}

export function useSseRetryState({
  notify,
  onResume,
  onExhausted,
}: UseSseRetryStateOptions): SseRetryState {
  const sseRetryCountRef = useRef(0);
  const sseRetryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sseRetryCountdownIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [sseRetryCountdown, setSseRetryCountdown] = useState(0);
  const [sseRetryExhausted, setSseRetryExhausted] = useState(false);

  const clearSseRetryTimers = useCallback(() => {
    if (sseRetryTimerRef.current) {
      clearTimeout(sseRetryTimerRef.current);
      sseRetryTimerRef.current = null;
    }
    if (sseRetryCountdownIntervalRef.current) {
      clearInterval(sseRetryCountdownIntervalRef.current);
      sseRetryCountdownIntervalRef.current = null;
    }
  }, []);

  const resetSseRetryState = useCallback(() => {
    sseRetryCountRef.current = 0;
    setSseRetryCountdown(0);
    setSseRetryExhausted(false);
    clearSseRetryTimers();
  }, [clearSseRetryTimers]);

  const handleStreamExhausted = useCallback(() => {
    const retryCount = sseRetryCountRef.current;
    if (retryCount < SSE_MAX_RETRIES) {
      sseRetryCountRef.current = retryCount + 1;
      const delay = SSE_RETRY_DELAYS[retryCount];
      const delaySeconds = Math.ceil(delay / 1000);
      setSseRetryCountdown(delaySeconds);
      notify(
        'warning',
        `同步进度通道中断，${delaySeconds}秒后自动重试 (${retryCount + 1}/${SSE_MAX_RETRIES})`
      );

      sseRetryCountdownIntervalRef.current = setInterval(() => {
        setSseRetryCountdown((c) => {
          if (c <= 1) {
            if (sseRetryCountdownIntervalRef.current) {
              clearInterval(sseRetryCountdownIntervalRef.current);
              sseRetryCountdownIntervalRef.current = null;
            }
            return 0;
          }
          return c - 1;
        });
      }, 1000);

      sseRetryTimerRef.current = setTimeout(() => {
        sseRetryTimerRef.current = null;
        setSseRetryCountdown(0);
        onResume();
      }, delay);
      return;
    }

    sseRetryCountRef.current = 0;
    setSseRetryCountdown(0);
    setSseRetryExhausted(true);
    const msg = `同步进度通道已中断 ${SSE_MAX_RETRIES} 次自动重试均未恢复，正在请求自动中断。`;
    notify('warning', msg);
    onExhausted(msg);
  }, [notify, onResume, onExhausted]);

  const handleSseExhaustedManualRetry = useCallback(() => {
    sseRetryCountRef.current = 0;
    setSseRetryExhausted(false);
    setSseRetryCountdown(0);
    clearSseRetryTimers();
    onResume();
  }, [clearSseRetryTimers, onResume]);

  return {
    sseRetryCountdown,
    sseRetryExhausted,
    clearSseRetryTimers,
    resetSseRetryState,
    handleStreamExhausted,
    handleSseExhaustedManualRetry,
  };
}
