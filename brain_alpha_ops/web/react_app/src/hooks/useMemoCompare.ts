/**
 * useMemoCompare - 深度比较 memo 值
 * 使用自定义比较函数来决定是否重新计算值
 */
import { useRef, useMemo, useEffect } from 'react';

export function useMemoCompare<T>(
  factory: () => T,
  deps: unknown[],
  compare: (prev: T | undefined, next: T) => boolean
): T {
  const previousRef = useRef<T | undefined>(undefined);
  const result = useMemo(factory, deps);

  if (previousRef.current === undefined || !compare(previousRef.current, result)) {
    previousRef.current = result;
  }

  return previousRef.current;
}

/**
 * useDeepMemo - 深度比较依赖的 useMemo
 * 对依赖进行深度比较，而不是引用比较
 */
function deepEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (a === null || b === null) return false;
  if (typeof a !== typeof b) return false;

  if (typeof a === 'object' && typeof b === 'object') {
    if (Array.isArray(a) && Array.isArray(b)) {
      if (a.length !== b.length) return false;
      for (let i = 0; i < a.length; i++) {
        if (!deepEqual(a[i], b[i])) return false;
      }
      return true;
    }

    if (!Array.isArray(a) && !Array.isArray(b)) {
      const keysA = Object.keys(a as Record<string, unknown>);
      const keysB = Object.keys(b as Record<string, unknown>);
      if (keysA.length !== keysB.length) return false;
      for (const key of keysA) {
        if (!deepEqual(
          (a as Record<string, unknown>)[key],
          (b as Record<string, unknown>)[key]
        )) {
          return false;
        }
      }
      return true;
    }

    return false;
  }

  return false;
}

export function useDeepMemo<T>(factory: () => T, deps: unknown[]): T {
  const previousDepsRef = useRef<unknown[] | null>(null);
  const previousResultRef = useRef<T | null>(null);
  const hasChangedRef = useRef(true);

  const result = factory();

  if (previousDepsRef.current === null || !deepEqual(previousDepsRef.current, deps)) {
    hasChangedRef.current = true;
  }

  if (hasChangedRef.current) {
    previousDepsRef.current = deps;
    previousResultRef.current = result;
    hasChangedRef.current = false;
  }

  useEffect(() => {
    return () => {
      previousDepsRef.current = null;
      previousResultRef.current = null;
    };
  }, []);

  return previousResultRef.current as T;
}
