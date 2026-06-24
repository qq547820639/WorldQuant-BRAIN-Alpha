import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useToast } from "@/hooks/useToast";
import type { Toast } from "@/types";

describe("useToast", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  it("initializes with empty toasts", () => {
    const { result } = renderHook(() => useToast());

    expect(result.current.toasts).toEqual([]);
  });

  it("addToast adds a toast to the list", () => {
    const { result } = renderHook(() => useToast());

    let toastId: string;
    act(() => {
      toastId = result.current.addToast("success", "Operation successful");
    });

    expect(result.current.toasts).toHaveLength(1);
    expect(result.current.toasts[0].id).toBe(toastId!);
    expect(result.current.toasts[0].type).toBe("success");
    expect(result.current.toasts[0].message).toBe("Operation successful");
  });

  it("dismissToast removes a toast by id", () => {
    const { result } = renderHook(() => useToast());

    let toastId1: string, toastId2: string;
    act(() => {
      toastId1 = result.current.addToast("success", "Toast 1");
      toastId2 = result.current.addToast("error", "Toast 2");
    });

    expect(result.current.toasts).toHaveLength(2);

    act(() => {
      result.current.dismissToast(toastId1);
    });

    expect(result.current.toasts).toHaveLength(1);
    expect(result.current.toasts[0].id).toBe(toastId2);
  });

  it("toast auto-dismisses after duration", () => {
    const { result } = renderHook(() => useToast());

    act(() => {
      result.current.addToast("info", "Auto dismiss", 5000);
    });

    expect(result.current.toasts).toHaveLength(1);

    act(() => {
      vi.advanceTimersByTime(4999);
    });

    expect(result.current.toasts).toHaveLength(1);

    act(() => {
      vi.advanceTimersByTime(1);
    });

    expect(result.current.toasts).toHaveLength(0);
  });

  it("toast with duration 0 does not auto-dismiss", () => {
    const { result } = renderHook(() => useToast());

    act(() => {
      result.current.addToast("info", "Persistent", 0);
    });

    expect(result.current.toasts).toHaveLength(1);

    act(() => {
      vi.advanceTimersByTime(10000);
    });

    expect(result.current.toasts).toHaveLength(1);
  });

  it("uses default duration of 5000ms", () => {
    const { result } = renderHook(() => useToast());

    act(() => {
      result.current.addToast("info", "Default duration");
    });

    expect(result.current.toasts).toHaveLength(1);

    act(() => {
      vi.advanceTimersByTime(4999);
    });
    expect(result.current.toasts).toHaveLength(1);

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(result.current.toasts).toHaveLength(0);
  });

  it("clears timeout when toast is manually dismissed", () => {
    const clearTimeoutSpy = vi.spyOn(global, "clearTimeout");
    const { result } = renderHook(() => useToast());

    let toastId: string;
    act(() => {
      toastId = result.current.addToast("info", "Test", 5000);
    });

    act(() => {
      result.current.dismissToast(toastId);
    });

    expect(clearTimeoutSpy).toHaveBeenCalled();
    clearTimeoutSpy.mockRestore();
  });

  it("respects maxToasts limit", () => {
    const { result } = renderHook(() => useToast(3));

    act(() => {
      result.current.addToast("info", "Toast 1");
      result.current.addToast("info", "Toast 2");
      result.current.addToast("info", "Toast 3");
    });

    expect(result.current.toasts).toHaveLength(3);

    act(() => {
      result.current.addToast("info", "Toast 4");
    });

    expect(result.current.toasts).toHaveLength(3);
  });

  it("keeps at least 2 error toasts when exceeding maxToasts", () => {
    const { result } = renderHook(() => useToast(3));

    act(() => {
      result.current.addToast("error", "Error 1");
      result.current.addToast("info", "Info 1");
      result.current.addToast("info", "Info 2");
    });

    expect(result.current.toasts).toHaveLength(3);

    act(() => {
      result.current.addToast("error", "Error 2");
    });

    expect(result.current.toasts).toHaveLength(3);

    const errorToasts = result.current.toasts.filter((t: Toast) => t.type === "error");
    expect(errorToasts).toHaveLength(2);
  });

  it("passes action and secondaryAction to toast", () => {
    const { result } = renderHook(() => useToast());

    const actionOnClick = vi.fn();
    const secondaryActionOnClick = vi.fn();

    act(() => {
      result.current.addToast(
        "info",
        "With actions",
        5000,
        { label: "Action", onClick: actionOnClick },
        { label: "Secondary", onClick: secondaryActionOnClick }
      );
    });

    expect(result.current.toasts[0].action_label).toBe("Action");
    expect(result.current.toasts[0].on_action).toBe(actionOnClick);
    expect(result.current.toasts[0].secondary_action_label).toBe("Secondary");
    expect(result.current.toasts[0].on_secondary_action).toBe(secondaryActionOnClick);
  });

  it("generates unique ids for each toast", () => {
    const { result } = renderHook(() => useToast());

    let ids: string[] = [];
    act(() => {
      ids.push(result.current.addToast("info", "Toast 1"));
      ids.push(result.current.addToast("info", "Toast 2"));
      ids.push(result.current.addToast("info", "Toast 3"));
    });

    const uniqueIds = new Set(ids);
    expect(uniqueIds.size).toBe(3);
  });
});
