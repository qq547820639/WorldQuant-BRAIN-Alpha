import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useThrottle, useThrottledCallback } from "@/hooks/useThrottle";

describe("useThrottle", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  it("returns the initial value immediately", () => {
    const { result } = renderHook(() => useThrottle("hello", 300));
    expect(result.current).toBe("hello");
  });

  it("updates value after delay when value changes", () => {
    const { result, rerender } = renderHook(
      ({ value, delay }) => useThrottle(value, delay),
      { initialProps: { value: "initial", delay: 300 } }
    );

    expect(result.current).toBe("initial");

    rerender({ value: "updated", delay: 300 });

    expect(result.current).toBe("initial");

    act(() => {
      vi.advanceTimersByTime(300);
    });

    expect(result.current).toBe("updated");
  });

  it("throttles multiple rapid changes", () => {
    const { result, rerender } = renderHook(
      ({ value, delay }) => useThrottle(value, delay),
      { initialProps: { value: "v1", delay: 300 } }
    );

    rerender({ value: "v2", delay: 300 });
    rerender({ value: "v3", delay: 300 });
    rerender({ value: "v4", delay: 300 });

    act(() => {
      vi.advanceTimersByTime(150);
    });
    expect(result.current).toBe("v1");

    act(() => {
      vi.advanceTimersByTime(150);
    });
    expect(result.current).toBe("v4");
  });

  it("uses default delay of 300ms when not specified", () => {
    const { result, rerender } = renderHook(({ value }) => useThrottle(value), {
      initialProps: { value: "initial" },
    });

    rerender({ value: "updated" });

    act(() => {
      vi.advanceTimersByTime(299);
    });
    expect(result.current).toBe("initial");

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(result.current).toBe("updated");
  });

  it("respects custom delay", () => {
    const { result, rerender } = renderHook(
      ({ value, delay }) => useThrottle(value, delay),
      { initialProps: { value: "initial", delay: 500 } }
    );

    rerender({ value: "updated", delay: 500 });

    act(() => {
      vi.advanceTimersByTime(499);
    });
    expect(result.current).toBe("initial");

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(result.current).toBe("updated");
  });

  it("cleans up timer on unmount", () => {
    const clearTimeoutSpy = vi.spyOn(global, "clearTimeout");
    const { unmount, rerender } = renderHook(
      ({ value }) => useThrottle(value, 300),
      { initialProps: { value: "initial" } }
    );

    rerender({ value: "updated" });
    unmount();

    expect(clearTimeoutSpy).toHaveBeenCalled();
    clearTimeoutSpy.mockRestore();
  });
});

describe("useThrottledCallback", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  it("invokes callback immediately on first call", () => {
    const callback = vi.fn();
    const { result } = renderHook(() => useThrottledCallback(callback, 300));

    result.current("arg1", "arg2");

    expect(callback).toHaveBeenCalledTimes(1);
    expect(callback).toHaveBeenCalledWith("arg1", "arg2");
  });

  it("throttles subsequent calls", () => {
    const callback = vi.fn();
    const { result } = renderHook(() => useThrottledCallback(callback, 300));

    result.current(1);
    expect(callback).toHaveBeenCalledTimes(1);

    result.current(2);
    result.current(3);
    expect(callback).toHaveBeenCalledTimes(1);

    act(() => {
      vi.advanceTimersByTime(300);
    });

    expect(callback).toHaveBeenCalledTimes(2);
    expect(callback).toHaveBeenLastCalledWith(3);
  });

  it("uses default delay of 300ms when not specified", () => {
    const callback = vi.fn();
    const { result } = renderHook(() => useThrottledCallback(callback));

    result.current(1);
    result.current(2);

    act(() => {
      vi.advanceTimersByTime(299);
    });
    expect(callback).toHaveBeenCalledTimes(1);

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(callback).toHaveBeenCalledTimes(2);
  });

  it("cleans up timer on unmount", () => {
    const clearTimeoutSpy = vi.spyOn(global, "clearTimeout");
    const callback = vi.fn();
    const { result, unmount } = renderHook(() =>
      useThrottledCallback(callback, 300)
    );

    result.current(1);
    result.current(2);
    unmount();

    expect(clearTimeoutSpy).toHaveBeenCalled();
    clearTimeoutSpy.mockRestore();
  });
});
