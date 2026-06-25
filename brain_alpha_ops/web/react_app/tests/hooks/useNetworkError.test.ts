import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useNetworkError } from "@/hooks/useNetworkError";

describe("useNetworkError", () => {
  let originalNavigatorOnLine: boolean;

  beforeEach(() => {
    vi.useFakeTimers();
    originalNavigatorOnLine = navigator.onLine;
    Object.defineProperty(navigator, "onLine", {
      value: true,
      writable: true,
      configurable: true,
    });
  });

  afterEach(() => {
    Object.defineProperty(navigator, "onLine", {
      value: originalNavigatorOnLine,
      writable: true,
      configurable: true,
    });
    vi.useRealTimers();
  });

  it("initial state: online when navigator is online", () => {
    const { result } = renderHook(() => useNetworkError());
    expect(result.current.isOnline).toBe(true);
    expect(result.current.isReconnecting).toBe(false);
    expect(result.current.retryCount).toBe(0);
    expect(result.current.lastError).toBeNull();
  });

  it("initial state: offline when navigator is offline", () => {
    Object.defineProperty(navigator, "onLine", {
      value: false,
      writable: true,
      configurable: true,
    });

    const { result } = renderHook(() => useNetworkError({ enableAutoRetry: false }));
    expect(result.current.isOnline).toBe(false);
  });

  it("handles offline event", () => {
    const { result } = renderHook(() => useNetworkError({ enableAutoRetry: false }));

    expect(result.current.isOnline).toBe(true);

    act(() => {
      window.dispatchEvent(new Event("offline"));
    });

    expect(result.current.isOnline).toBe(false);
    expect(result.current.lastError).not.toBeNull();
  });

  it("handles online event", () => {
    const { result } = renderHook(() => useNetworkError({ enableAutoRetry: false }));

    act(() => {
      window.dispatchEvent(new Event("offline"));
    });
    expect(result.current.isOnline).toBe(false);

    act(() => {
      window.dispatchEvent(new Event("online"));
    });

    expect(result.current.isOnline).toBe(true);
    expect(result.current.isReconnecting).toBe(false);
    expect(result.current.lastError).toBeNull();
    expect(result.current.retryCount).toBe(0);
  });

  it("retry: sets reconnecting state when offline", () => {
    Object.defineProperty(navigator, "onLine", {
      value: false,
      writable: true,
      configurable: true,
    });

    const { result } = renderHook(() => useNetworkError({ enableAutoRetry: false }));

    act(() => {
      result.current.retry();
    });

    expect(result.current.isReconnecting).toBe(true);
    expect(result.current.retryCount).toBe(1);
    expect(result.current.lastError).not.toBeNull();
  });

  it("retry: does nothing if already reconnecting", () => {
    Object.defineProperty(navigator, "onLine", {
      value: false,
      writable: true,
      configurable: true,
    });

    const { result } = renderHook(() => useNetworkError({ enableAutoRetry: false }));

    act(() => {
      result.current.retry();
    });
    expect(result.current.retryCount).toBe(1);

    act(() => {
      result.current.retry();
    });
    expect(result.current.retryCount).toBe(1);
  });

  it("retry: immediately sets online if navigator is online", () => {
    const { result } = renderHook(() => useNetworkError({ enableAutoRetry: false }));

    act(() => {
      window.dispatchEvent(new Event("offline"));
    });
    expect(result.current.isOnline).toBe(false);

    Object.defineProperty(navigator, "onLine", {
      value: true,
      writable: true,
      configurable: true,
    });

    act(() => {
      result.current.retry();
    });

    expect(result.current.isOnline).toBe(true);
    expect(result.current.isReconnecting).toBe(false);
  });

  it("reset: clears all state", () => {
    Object.defineProperty(navigator, "onLine", {
      value: false,
      writable: true,
      configurable: true,
    });

    const { result } = renderHook(() => useNetworkError({ enableAutoRetry: false }));

    act(() => {
      result.current.retry();
    });
    expect(result.current.isReconnecting).toBe(true);

    Object.defineProperty(navigator, "onLine", {
      value: true,
      writable: true,
      configurable: true,
    });

    act(() => {
      result.current.reset();
    });

    expect(result.current.isOnline).toBe(true);
    expect(result.current.isReconnecting).toBe(false);
    expect(result.current.retryCount).toBe(0);
    expect(result.current.lastError).toBeNull();
  });

  it("auto retry: triggers retry on offline when enabled", () => {
    Object.defineProperty(navigator, "onLine", {
      value: false,
      writable: true,
      configurable: true,
    });

    const { result } = renderHook(() => useNetworkError({ enableAutoRetry: true }));

    act(() => {
      window.dispatchEvent(new Event("offline"));
    });

    expect(result.current.isReconnecting).toBe(true);
    expect(result.current.retryCount).toBe(1);
  });

  it("adds and removes event listeners on mount/unmount", () => {
    const addEventListenerSpy = vi.spyOn(window, "addEventListener");
    const removeEventListenerSpy = vi.spyOn(window, "removeEventListener");

    const { unmount } = renderHook(() => useNetworkError());

    expect(addEventListenerSpy).toHaveBeenCalledWith("online", expect.any(Function));
    expect(addEventListenerSpy).toHaveBeenCalledWith("offline", expect.any(Function));

    unmount();

    expect(removeEventListenerSpy).toHaveBeenCalledWith("online", expect.any(Function));
    expect(removeEventListenerSpy).toHaveBeenCalledWith("offline", expect.any(Function));

    addEventListenerSpy.mockRestore();
    removeEventListenerSpy.mockRestore();
  });
});
