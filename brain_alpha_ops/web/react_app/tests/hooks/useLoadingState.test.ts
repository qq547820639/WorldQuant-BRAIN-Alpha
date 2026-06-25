import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useLoadingState } from "@/hooks/useLoadingState";

describe("useLoadingState", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  it("has initial state with isLoading false", () => {
    const { result } = renderHook(() => useLoadingState());
    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.hasError).toBe(false);
  });

  it("supports initialLoading option", () => {
    const { result } = renderHook(() => useLoadingState({ initialLoading: true }));
    expect(result.current.isLoading).toBe(true);
  });

  it("can start and stop loading", () => {
    const { result } = renderHook(() => useLoadingState({ minDuration: 0 }));

    act(() => {
      result.current.setLoading(true);
    });
    expect(result.current.isLoading).toBe(true);

    act(() => {
      result.current.setLoading(false);
    });
    expect(result.current.isLoading).toBe(false);
  });

  it("runWithLoading: sets loading and resolves on success", async () => {
    const { result } = renderHook(() => useLoadingState({ minDuration: 0 }));
    const mockFn = vi.fn().mockResolvedValue("success");

    let promise: Promise<string>;
    act(() => {
      promise = result.current.runWithLoading(mockFn);
    });

    expect(result.current.isLoading).toBe(true);

    await act(async () => {
      const resultValue = await promise!;
      expect(resultValue).toBe("success");
    });

    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toBeNull();
    expect(mockFn).toHaveBeenCalledTimes(1);
  });

  it("runWithLoading: sets error on failure", async () => {
    const { result } = renderHook(() => useLoadingState({ minDuration: 0 }));
    const testError = new Error("Test error");
    const mockFn = vi.fn().mockRejectedValue(testError);

    let promise: Promise<never>;
    act(() => {
      promise = result.current.runWithLoading(mockFn);
    });

    expect(result.current.isLoading).toBe(true);

    await act(async () => {
      await expect(promise!).rejects.toThrow("Test error");
    });

    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toBe(testError);
    expect(result.current.hasError).toBe(true);
  });

  it("respects minDuration option", () => {
    const { result } = renderHook(() => useLoadingState({ minDuration: 500 }));

    act(() => {
      result.current.setLoading(true);
    });
    expect(result.current.isLoading).toBe(true);

    act(() => {
      result.current.setLoading(false);
    });
    expect(result.current.isLoading).toBe(true);

    act(() => {
      vi.advanceTimersByTime(499);
    });
    expect(result.current.isLoading).toBe(true);

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(result.current.isLoading).toBe(false);
  });

  it("reset: clears loading and error", () => {
    const { result } = renderHook(() => useLoadingState({ minDuration: 0 }));
    const testError = new Error("Test error");

    act(() => {
      result.current.setError(testError);
      result.current.setLoading(true);
    });
    expect(result.current.isLoading).toBe(true);
    expect(result.current.hasError).toBe(true);

    act(() => {
      result.current.reset();
    });
    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.hasError).toBe(false);
  });

  it("setError: sets error state", () => {
    const { result } = renderHook(() => useLoadingState());
    const testError = new Error("Custom error");

    act(() => {
      result.current.setError(testError);
    });

    expect(result.current.error).toBe(testError);
    expect(result.current.hasError).toBe(true);
  });

  it("default minDuration is 300ms", () => {
    const { result } = renderHook(() => useLoadingState());

    act(() => {
      result.current.setLoading(true);
    });

    act(() => {
      result.current.setLoading(false);
    });
    expect(result.current.isLoading).toBe(true);

    act(() => {
      vi.advanceTimersByTime(299);
    });
    expect(result.current.isLoading).toBe(true);

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(result.current.isLoading).toBe(false);
  });
});
