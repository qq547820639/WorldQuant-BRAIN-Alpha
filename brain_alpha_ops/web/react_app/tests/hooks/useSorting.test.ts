import { describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useSorting } from "@/hooks/useSorting";

describe("useSorting", () => {
  it("initializes with provided initial values", () => {
    const { result } = renderHook(() =>
      useSorting<"name" | "age">({
        initialSortKey: "name",
        initialSortAsc: true,
      })
    );

    expect(result.current.sortKey).toBe("name");
    expect(result.current.sortAsc).toBe(true);
    expect(result.current.sortDirection).toBe("asc");
  });

  it("initializes with default values when not provided", () => {
    const { result } = renderHook(() => useSorting<"name" | "age">());

    expect(result.current.sortAsc).toBe(false);
    expect(result.current.sortDirection).toBe("desc");
  });

  it("handleSort toggles direction when same key is clicked", () => {
    const { result } = renderHook(() =>
      useSorting<"name" | "age">({
        initialSortKey: "name",
        initialSortAsc: false,
      })
    );

    act(() => {
      result.current.handleSort("name");
    });

    expect(result.current.sortKey).toBe("name");
    expect(result.current.sortAsc).toBe(true);
    expect(result.current.sortDirection).toBe("asc");

    act(() => {
      result.current.handleSort("name");
    });

    expect(result.current.sortAsc).toBe(false);
    expect(result.current.sortDirection).toBe("desc");
  });

  it("handleSort changes key and resets to descending when different key is clicked", () => {
    const { result } = renderHook(() =>
      useSorting<"name" | "age">({
        initialSortKey: "name",
        initialSortAsc: true,
      })
    );

    act(() => {
      result.current.handleSort("age");
    });

    expect(result.current.sortKey).toBe("age");
    expect(result.current.sortAsc).toBe(false);
    expect(result.current.sortDirection).toBe("desc");
  });

  it("setSortKey updates the sort key", () => {
    const { result } = renderHook(() =>
      useSorting<"name" | "age">({ initialSortKey: "name" })
    );

    act(() => {
      result.current.setSortKey("age");
    });

    expect(result.current.sortKey).toBe("age");
  });

  it("setSortAsc updates the sort direction", () => {
    const { result } = renderHook(() =>
      useSorting<"name" | "age">({ initialSortAsc: false })
    );

    act(() => {
      result.current.setSortAsc(true);
    });

    expect(result.current.sortAsc).toBe(true);
    expect(result.current.sortDirection).toBe("asc");
  });

  it("toggleSortDirection toggles the sort direction", () => {
    const { result } = renderHook(() =>
      useSorting<"name" | "age">({ initialSortAsc: false })
    );

    act(() => {
      result.current.toggleSortDirection();
    });

    expect(result.current.sortAsc).toBe(true);

    act(() => {
      result.current.toggleSortDirection();
    });

    expect(result.current.sortAsc).toBe(false);
  });

  it("sortItems sorts numbers correctly in descending order", () => {
    const { result } = renderHook(() =>
      useSorting<"score">({
        initialSortKey: "score",
        initialSortAsc: false,
      })
    );

    const items = [
      { id: "1", score: 10 },
      { id: "2", score: 30 },
      { id: "3", score: 20 },
    ];

    const sorted = result.current.sortItems(items);

    expect(sorted[0].score).toBe(30);
    expect(sorted[1].score).toBe(20);
    expect(sorted[2].score).toBe(10);
  });

  it("sortItems sorts numbers correctly in ascending order", () => {
    const { result } = renderHook(() =>
      useSorting<"score">({
        initialSortKey: "score",
        initialSortAsc: true,
      })
    );

    const items = [
      { id: "1", score: 10 },
      { id: "2", score: 30 },
      { id: "3", score: 20 },
    ];

    const sorted = result.current.sortItems(items);

    expect(sorted[0].score).toBe(10);
    expect(sorted[1].score).toBe(20);
    expect(sorted[2].score).toBe(30);
  });

  it("sortItems sorts strings correctly", () => {
    const { result } = renderHook(() =>
      useSorting<"name">({
        initialSortKey: "name",
        initialSortAsc: true,
      })
    );

    const items = [
      { id: "1", name: "Charlie" },
      { id: "2", name: "Alice" },
      { id: "3", name: "Bob" },
    ];

    const sorted = result.current.sortItems(items);

    expect(sorted[0].name).toBe("Alice");
    expect(sorted[1].name).toBe("Bob");
    expect(sorted[2].name).toBe("Charlie");
  });

  it("sortItems returns same array when empty", () => {
    const { result } = renderHook(() =>
      useSorting<"name">({ initialSortKey: "name" })
    );

    const items: Array<{ id: string; name: string }> = [];
    const sorted = result.current.sortItems(items);

    expect(sorted).toEqual([]);
  });

  it("sortItems does not mutate original array", () => {
    const { result } = renderHook(() =>
      useSorting<"score">({
        initialSortKey: "score",
        initialSortAsc: true,
      })
    );

    const items = [
      { id: "1", score: 30 },
      { id: "2", score: 10 },
    ];
    const original = [...items];

    result.current.sortItems(items);

    expect(items[0].score).toBe(original[0].score);
    expect(items[1].score).toBe(original[1].score);
  });
});
