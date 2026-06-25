import { describe, it, expect } from "vitest";
import { renderHook } from "@testing-library/react";
import { useMemoCompare, useDeepMemo } from "@/hooks/useMemoCompare";

describe("useMemoCompare", () => {
  it("returns initial value", () => {
    const { result } = renderHook(() =>
      useMemoCompare(
        () => ({ a: 1, b: 2 }),
        [{ a: 1, b: 2 }],
        (prev, next) => prev?.a === next?.a && prev?.b === next?.b
      )
    );
    expect(result.current).toEqual({ a: 1, b: 2 });
  });

  it("returns same reference when compare returns true", () => {
    const { result, rerender } = renderHook(
      ({ deps }) =>
        useMemoCompare(
          () => ({ value: deps[0].value }),
          deps,
          (prev, next) => prev?.value === next?.value
        ),
      { initialProps: { deps: [{ value: 1 }] } }
    );

    const firstResult = result.current;

    rerender({ deps: [{ value: 1 }] });

    expect(result.current).toBe(firstResult);
  });

  it("returns new reference when compare returns false", () => {
    const { result, rerender } = renderHook(
      ({ deps }) =>
        useMemoCompare(
          () => ({ value: deps[0].value }),
          deps,
          (prev, next) => prev?.value === next?.value
        ),
      { initialProps: { deps: [{ value: 1 }] } }
    );

    const firstResult = result.current;

    rerender({ deps: [{ value: 2 }] });

    expect(result.current).not.toBe(firstResult);
    expect(result.current).toEqual({ value: 2 });
  });

  it("uses custom compare function", () => {
    const compare = (prev: { id: number } | undefined, next: { id: number }) =>
      prev?.id === next.id;

    const { result, rerender } = renderHook(
      ({ obj }) => useMemoCompare(() => obj, [obj], compare),
      { initialProps: { obj: { id: 1, name: "a" } } }
    );

    const firstResult = result.current;

    rerender({ obj: { id: 1, name: "b" } });

    expect(result.current).toBe(firstResult);
    expect(result.current.name).toBe("a");
  });
});

describe("useDeepMemo", () => {
  it("returns initial value", () => {
    const { result } = renderHook(() =>
      useDeepMemo(() => ({ a: 1, b: [2, 3] }), [1])
    );
    expect(result.current).toEqual({ a: 1, b: [2, 3] });
  });

  it("returns same reference with deeply equal deps", () => {
    const { result, rerender } = renderHook(
      ({ deps }) => useDeepMemo(() => ({ value: deps[0] }), deps),
      { initialProps: { deps: [{ a: 1, b: { c: 2 } }] } }
    );

    const firstResult = result.current;

    rerender({ deps: [{ a: 1, b: { c: 2 } }] });

    expect(result.current).toBe(firstResult);
  });

  it("returns new reference when deps change", () => {
    const { result, rerender } = renderHook(
      ({ deps }) => useDeepMemo(() => ({ value: deps[0] }), deps),
      { initialProps: { deps: [{ a: 1 }] } }
    );

    const firstResult = result.current;

    rerender({ deps: [{ a: 2 }] });

    expect(result.current).not.toBe(firstResult);
  });

  it("handles array deps", () => {
    const { result, rerender } = renderHook(
      ({ deps }) => useDeepMemo(() => deps, deps),
      { initialProps: { deps: [1, 2, [3, 4]] } }
    );

    const firstResult = result.current;

    rerender({ deps: [1, 2, [3, 4]] });

    expect(result.current).toBe(firstResult);
  });

  it("handles primitive deps", () => {
    const { result, rerender } = renderHook(
      ({ deps }) => useDeepMemo(() => deps[0], deps),
      { initialProps: { deps: [42] } }
    );

    const firstResult = result.current;

    rerender({ deps: [42] });

    expect(result.current).toBe(firstResult);
  });

  it("detects nested object changes", () => {
    const { result, rerender } = renderHook(
      ({ deps }) => useDeepMemo(() => deps[0], deps),
      { initialProps: { deps: [{ a: { b: { c: 1 } } }] } }
    );

    const firstResult = result.current;

    rerender({ deps: [{ a: { b: { c: 2 } } }] });

    expect(result.current).not.toBe(firstResult);
  });
});
