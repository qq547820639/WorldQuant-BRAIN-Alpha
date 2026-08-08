import { useRef } from 'react';

/**
 * 基于自定义比较函数的记忆化 hook。
 * 仅当 `compare(上一次依赖, 本次依赖)` 返回 false 时才重新执行 `factory`。
 */

export function useMemoCompare<T, D>(
  factory: () => T,
  deps: readonly [D, ...unknown[]],
  compare: (prev: D | undefined, next: D) => boolean
): T {
  const valueRef = useRef<T | undefined>(undefined);
  const depsRef = useRef<D | undefined>(undefined);

  // compare 针对首个依赖元素进行判断（与测试中 compare 的签名一致）
  const current = deps[0];

  if (depsRef.current === undefined || !compare(depsRef.current, current)) {
    valueRef.current = factory();
    depsRef.current = current;
  }

  return valueRef.current as T;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** 深度相等比较（支持嵌套对象与数组）。 */
export function deepEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  const aIsArray = Array.isArray(a);
  const bIsArray = Array.isArray(b);
  if (aIsArray && bIsArray) {
    const aArr = a as unknown[];
    const bArr = b as unknown[];
    if (aArr.length !== bArr.length) return false;
    return aArr.every((item, index) => deepEqual(item, bArr[index]));
  }
  if (isPlainObject(a) && isPlainObject(b)) {
    const aKeys = Object.keys(a);
    const bKeys = Object.keys(b);
    if (aKeys.length !== bKeys.length) return false;
    return aKeys.every((key) => deepEqual(a[key], b[key]));
  }
  return false;
}

/**
 * 基于深度相等比较的记忆化 hook。
 * 仅当依赖数组发生深度变化时重新执行 `factory`。
 */
export function useDeepMemo<T>(factory: () => T, deps: readonly unknown[]): T {
  const valueRef = useRef<T | undefined>(undefined);
  const depsRef = useRef<readonly unknown[] | undefined>(undefined);

  if (depsRef.current === undefined || !deepEqual(depsRef.current, deps)) {
    valueRef.current = factory();
    depsRef.current = deps;
  }

  return valueRef.current as T;
}

export default useMemoCompare;
