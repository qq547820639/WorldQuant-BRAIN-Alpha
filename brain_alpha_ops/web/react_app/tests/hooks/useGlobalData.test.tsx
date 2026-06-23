import { renderHook, act, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import React from "react";
import { GlobalDataProvider, useGlobalData } from "@/hooks/useGlobalData";

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    ...init,
    headers: { "Content-Type": "application/json" },
  });
}

function createWrapper() {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <GlobalDataProvider>{children}</GlobalDataProvider>;
  };
}

function defaultFetchMock() {
  return vi.fn(async (url: RequestInfo | URL) => {
    const path = String(url);
    if (path.startsWith("/api/candidates")) return jsonResponse({ ok: true, candidates: [], total: 0 });
    if (path === "/api/backtest_slots") return jsonResponse({ ok: true, slot_limit: 3, active_count: 0, slots: [] });
    if (path.startsWith("/api/snapshot/cloud")) return jsonResponse({ ok: true, count: 0, total: 0, summary: {} });
    if (path === "/api/config") return jsonResponse({ ok: true, config: { environment: "production" } });
    throw new Error(`Unexpected fetch: ${path}`);
  });
}

describe("useGlobalData", () => {
  beforeEach(() => {
    vi.useRealTimers();
  });

  it("throws when used outside GlobalDataProvider", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => {
      renderHook(() => useGlobalData());
    }).toThrow("useGlobalData must be used within a GlobalDataProvider");
    spy.mockRestore();
  });

  it("fetches all endpoints on mount", async () => {
    const fetchMock = defaultFetchMock();
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useGlobalData(), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(result.current.candidates.loading).toBe(false);
      expect(result.current.slots.loading).toBe(false);
      expect(result.current.cloud.loading).toBe(false);
      expect(result.current.config.loading).toBe(false);
    });

    expect(fetchMock).toHaveBeenCalledWith("/api/candidates", expect.any(Object));
    expect(fetchMock).toHaveBeenCalledWith("/api/backtest_slots", expect.any(Object));
    expect(fetchMock).toHaveBeenCalledWith("/api/snapshot/cloud", expect.any(Object));
    expect(fetchMock).toHaveBeenCalledWith("/api/config", expect.any(Object));
  });

  it("returns candidate data after fetch completes", async () => {
    const candidates = [
      { alpha_id: "alpha_1", expression: "rank(close)", score: 88 },
      { alpha_id: "alpha_2", expression: "rank(volume)", score: 75 },
    ];
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path.startsWith("/api/candidates")) return jsonResponse({ ok: true, candidates, total: 2 });
      if (path === "/api/backtest_slots") return jsonResponse({ ok: true, slot_limit: 3, active_count: 0, slots: [] });
      if (path.startsWith("/api/snapshot/cloud")) return jsonResponse({ ok: true, count: 0, total: 0 });
      if (path === "/api/config") return jsonResponse({ ok: true, config: {} });
      throw new Error(`Unexpected fetch: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useGlobalData(), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(result.current.candidates.data).not.toBeNull();
    });

    expect(result.current.candidates.data?.candidates).toEqual(candidates);
    expect(result.current.candidates.error).toBeNull();
  });

  it("propagates fetch errors to the corresponding endpoint", async () => {
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path.startsWith("/api/candidates")) return jsonResponse({ ok: false, error: "server error" }, { status: 500 });
      if (path === "/api/backtest_slots") return jsonResponse({ ok: true, slot_limit: 3, active_count: 0, slots: [] });
      if (path.startsWith("/api/snapshot/cloud")) return jsonResponse({ ok: true, count: 0, total: 0 });
      if (path === "/api/config") return jsonResponse({ ok: true, config: {} });
      throw new Error(`Unexpected fetch: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useGlobalData(), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(result.current.candidates.error).not.toBeNull();
    });

    expect(result.current.candidates.data).toBeNull();
    expect(result.current.candidates.error).toBeTruthy();
    expect(result.current.slots.error).toBeNull();
  });

  it("provides a refreshAll function that re-fetches all endpoints", async () => {
    let fetchCount = 0;
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      fetchCount += 1;
      const path = String(url);
      if (path.startsWith("/api/candidates")) return jsonResponse({ ok: true, candidates: [], total: fetchCount });
      if (path === "/api/backtest_slots") return jsonResponse({ ok: true, slot_limit: 3, active_count: 0, slots: [] });
      if (path.startsWith("/api/snapshot/cloud")) return jsonResponse({ ok: true, count: 0, total: 0 });
      if (path === "/api/config") return jsonResponse({ ok: true, config: {} });
      throw new Error(`Unexpected fetch: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useGlobalData(), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(result.current.candidates.loading).toBe(false);
    });

    const callsAfterMount = fetchMock.mock.calls.length;

    await act(async () => {
      result.current.refreshAll();
    });

    await waitFor(() => {
      expect(fetchMock.mock.calls.length).toBeGreaterThan(callsAfterMount);
    });

    expect(fetchMock).toHaveBeenCalledWith("/api/candidates", expect.any(Object));
    expect(fetchMock).toHaveBeenCalledWith("/api/backtest_slots", expect.any(Object));
    expect(fetchMock).toHaveBeenCalledWith("/api/snapshot/cloud", expect.any(Object));
    expect(fetchMock).toHaveBeenCalledWith("/api/config", expect.any(Object));
  });

  it("sets up a 30-second auto-refresh interval", async () => {
    const fetchMock = defaultFetchMock();
    vi.stubGlobal("fetch", fetchMock);

    renderHook(() => useGlobalData(), { wrapper: createWrapper() });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4));

    const initialCalls = fetchMock.mock.calls.length;

    await waitFor(() => {
      expect(fetchMock.mock.calls.length).toBeGreaterThan(initialCalls);
    }, { timeout: 35000 });
  }, 40000);

  it("memoizes the context value across re-renders", async () => {
    const fetchMock = defaultFetchMock();
    vi.stubGlobal("fetch", fetchMock);

    const { result, rerender } = renderHook(() => useGlobalData(), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(result.current.candidates.loading).toBe(false);
    });

    const firstValue = result.current;
    rerender();
    const secondValue = result.current;

    expect(firstValue.candidates).toBe(secondValue.candidates);
    expect(firstValue.slots).toBe(secondValue.slots);
    expect(firstValue.cloud).toBe(secondValue.cloud);
    expect(firstValue.config).toBe(secondValue.config);
    expect(firstValue.refreshAll).toBe(secondValue.refreshAll);
  });
});
