import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * 节流 / 防抖工具 hooks。
 */

/**
 * 返回一个延迟更新的值：输入 `value` 变化后，仅当经过 `delay` 毫秒才输出最新值。
 * 若在 delay 内再次变化，则重置计时并最终输出最后一次的值。
 */
export function useThrottle<T>(value: T, delay = 300): T {
  const [throttled, setThrottled] = useState<T>(value);
  const latestRef = useRef<T>(value);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    latestRef.current = value;
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
    }
    timerRef.current = setTimeout(() => {
      setThrottled(latestRef.current);
      timerRef.current = null;
    }, delay);

    return () => {
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [value, delay]);

  return throttled;
}

type AnyArgs = unknown[];

/**
 * 返回一个节流执行的回调：
 * - 首次调用立即执行；
 * - 在 `delay` 窗口内的后续调用被合并，窗口结束后以最后一次调用的参数执行一次。
 */
export function useThrottledCallback<A extends AnyArgs>(
  callback: (...args: A) => void,
  delay = 300
): (...args: A) => void {
  const callbackRef = useRef(callback);
  callbackRef.current = callback;

  const lastArgsRef = useRef<A | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inThrottleRef = useRef(false);

  const throttled = useCallback(
    (...args: A) => {
      lastArgsRef.current = args;
      if (inThrottleRef.current) {
        return;
      }
      inThrottleRef.current = true;
      callbackRef.current(...args);
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
      }
      timerRef.current = setTimeout(() => {
        inThrottleRef.current = false;
        timerRef.current = null;
        if (lastArgsRef.current) {
          const trailing = lastArgsRef.current;
          lastArgsRef.current = null;
          callbackRef.current(...trailing);
        }
      }, delay);
    },
    [delay]
  );

  useEffect(() => {
    return () => {
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, []);

  return throttled;
}

export default useThrottle;
