import { describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { usePagination } from "@/hooks/usePagination";

describe("usePagination", () => {
  it("initializes with correct default values", () => {
    const { result } = renderHook(() =>
      usePagination({ totalItems: 100, pageSize: 20 })
    );

    expect(result.current.currentPage).toBe(1);
    expect(result.current.pageSize).toBe(20);
    expect(result.current.totalItems).toBe(100);
    expect(result.current.totalPages).toBe(5);
    expect(result.current.startIndex).toBe(1);
    expect(result.current.endIndex).toBe(20);
  });

  it("calculates totalPages correctly for partial last page", () => {
    const { result } = renderHook(() =>
      usePagination({ totalItems: 25, pageSize: 10 })
    );

    expect(result.current.totalPages).toBe(3);
  });

  it("returns totalPages as 1 when totalItems is 0", () => {
    const { result } = renderHook(() =>
      usePagination({ totalItems: 0, pageSize: 10 })
    );

    expect(result.current.totalPages).toBe(1);
    expect(result.current.startIndex).toBe(0);
    expect(result.current.endIndex).toBe(0);
  });

  it("uses initialPage when provided", () => {
    const { result } = renderHook(() =>
      usePagination({ totalItems: 100, pageSize: 20, initialPage: 3 })
    );

    expect(result.current.currentPage).toBe(3);
    expect(result.current.startIndex).toBe(41);
    expect(result.current.endIndex).toBe(60);
  });

  it("goToPage navigates to specified page", () => {
    const { result } = renderHook(() =>
      usePagination({ totalItems: 100, pageSize: 20 })
    );

    act(() => {
      result.current.goToPage(3);
    });

    expect(result.current.currentPage).toBe(3);
    expect(result.current.startIndex).toBe(41);
    expect(result.current.endIndex).toBe(60);
  });

  it("goToPage clamps to valid range", () => {
    const { result } = renderHook(() =>
      usePagination({ totalItems: 100, pageSize: 20 })
    );

    act(() => {
      result.current.goToPage(10);
    });
    expect(result.current.currentPage).toBe(5);

    act(() => {
      result.current.goToPage(0);
    });
    expect(result.current.currentPage).toBe(1);
  });

  it("nextPage increments page", () => {
    const { result } = renderHook(() =>
      usePagination({ totalItems: 100, pageSize: 20 })
    );

    act(() => {
      result.current.nextPage();
    });

    expect(result.current.currentPage).toBe(2);
  });

  it("nextPage does not exceed totalPages", () => {
    const { result } = renderHook(() =>
      usePagination({ totalItems: 60, pageSize: 20 })
    );

    act(() => {
      result.current.goToPage(3);
    });
    expect(result.current.currentPage).toBe(3);

    act(() => {
      result.current.nextPage();
    });
    expect(result.current.currentPage).toBe(3);
  });

  it("prevPage decrements page", () => {
    const { result } = renderHook(() =>
      usePagination({ totalItems: 100, pageSize: 20, initialPage: 3 })
    );

    act(() => {
      result.current.prevPage();
    });

    expect(result.current.currentPage).toBe(2);
  });

  it("prevPage does not go below 1", () => {
    const { result } = renderHook(() =>
      usePagination({ totalItems: 100, pageSize: 20 })
    );

    act(() => {
      result.current.prevPage();
    });

    expect(result.current.currentPage).toBe(1);
  });

  it("resetPage resets to page 1", () => {
    const { result } = renderHook(() =>
      usePagination({ totalItems: 100, pageSize: 20, initialPage: 4 })
    );

    act(() => {
      result.current.resetPage();
    });

    expect(result.current.currentPage).toBe(1);
  });

  it("adjusts currentPage when totalPages decreases", () => {
    const { result, rerender } = renderHook(
      ({ totalItems }) => usePagination({ totalItems, pageSize: 20 }),
      { initialProps: { totalItems: 100 } }
    );

    act(() => {
      result.current.goToPage(5);
    });
    expect(result.current.currentPage).toBe(5);

    rerender({ totalItems: 40 });
    expect(result.current.totalPages).toBe(2);
    expect(result.current.currentPage).toBeLessThanOrEqual(2);
  });

  it("setCurrentPage works with function updater", () => {
    const { result } = renderHook(() =>
      usePagination({ totalItems: 100, pageSize: 20 })
    );

    act(() => {
      result.current.setCurrentPage((prev) => prev + 2);
    });

    expect(result.current.currentPage).toBe(3);
  });
});
