import { renderHook, act, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { useApi } from "@/hooks/useApi";

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    ...init,
    headers: { "Content-Type": "application/json" },
  });
}

describe("useApi", () => {
  beforeEach(() => {
    vi.useRealTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("starts with idle state", () => {
    const { result } = renderHook(() => useApi());

    expect(result.current.data).toBeNull();
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.lastErrorMeta).toBeNull();
  });

  it("sets loading true during a call", async () => {
    let resolveRequest: ((value: Response) => void) | null = null;
    const fetchMock = vi.fn(() => new Promise<Response>((resolve) => { resolveRequest = resolve; }));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useApi());

    act(() => {
      result.current.call("/api/test");
    });

    await waitFor(() => expect(result.current.loading).toBe(true));

    resolveRequest?.(jsonResponse({ ok: true, data: "test" }));

    await waitFor(() => expect(result.current.loading).toBe(false));
  });

  it("extracts .data from nested responses", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ ok: true, data: { nested: true } }));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useApi<{ nested: boolean }>());

    await act(async () => {
      await result.current.call("/api/test");
    });

    expect(result.current.data).toEqual({ nested: true });
    expect(result.current.error).toBeNull();
  });

  it("uses whole payload as data when no .data field is present", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ ok: true, name: "test-value" }));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useApi<{ name: string }>());

    await act(async () => {
      await result.current.call("/api/test");
    });

    expect(result.current.data).toEqual({ ok: true, name: "test-value" });
    expect(result.current.error).toBeNull();
    expect(result.current.loading).toBe(false);
  });

  it("sets error on API failure response", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({ ok: false, error: "Something went wrong" }, { status: 400 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useApi());

    await act(async () => {
      await result.current.call("/api/test");
    });

    expect(result.current.data).toBeNull();
    expect(result.current.error).toBeTruthy();
    expect(result.current.loading).toBe(false);
  });

  it("returns normalized error payload with ok:false", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({ ok: false, error: "not found", error_code: "NOT_FOUND" }, { status: 404 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useApi());

    let returnValue: Awaited<ReturnType<typeof result.current.call>> | undefined;
    await act(async () => {
      returnValue = await result.current.call("/api/test");
    });

    expect(returnValue).not.toBeNull();
    expect(returnValue!.ok).toBe(false);
    expect(returnValue!.error_code).toBe("NOT_FOUND");
  });

  it("sets error on network failure", async () => {
    const fetchMock = vi.fn(async () => { throw new Error("network down"); });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useApi());

    await act(async () => {
      await result.current.call("/api/test");
    });

    expect(result.current.data).toBeNull();
    expect(result.current.error).toBeTruthy();
    expect(result.current.loading).toBe(false);
  });

  it("handles AbortError with an actionable message", async () => {
    const fetchMock = vi.fn(async () => {
      throw new DOMException("The operation was aborted.", "AbortError");
    });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useApi());

    await act(async () => {
      await result.current.call("/api/test");
    });

    expect(result.current.error).toContain("网络请求未在预期时间内返回");
  });

  it("includes Content-Type header for POST requests", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useApi());

    await act(async () => {
      await result.current.call("/api/test", { method: "POST", body: "{}" });
    });

    const callArgs = fetchMock.mock.calls[0];
    const headers = callArgs[1]?.headers as Record<string, string>;
    expect(headers["Content-Type"]).toBe("application/json");
  });

  it("sets error state before making a new call", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ ok: false, error: "fail" }, { status: 500 }));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useApi());

    await act(async () => {
      await result.current.call("/api/test");
    });

    expect(result.current.error).toBeTruthy();

    fetchMock.mockResolvedValueOnce(jsonResponse({ ok: true, success: true }));

    await act(async () => {
      await result.current.call("/api/test2");
    });

    expect(result.current.error).toBeNull();
    expect(result.current.data).toEqual({ ok: true, success: true });
  });

  it("reset clears all state", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ ok: true, value: 42 }));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useApi());

    await act(async () => {
      await result.current.call("/api/test");
    });

    expect(result.current.data).toEqual({ ok: true, value: 42 });

    act(() => {
      result.current.reset();
    });

    expect(result.current.data).toBeNull();
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.lastErrorMeta).toBeNull();
  });

  it("sets lastErrorMeta for API errors with structured metadata", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({
        ok: false,
        error_code: "SESSION_INVALID",
        error: "invalid session",
        user_error: { kind: "session_expired", message: "会话已过期" },
      }, { status: 401 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useApi());

    await act(async () => {
      await result.current.call("/api/test");
    });

    expect(result.current.lastErrorMeta).not.toBeNull();
    expect(result.current.lastErrorMeta?.error_code).toBe("SESSION_INVALID");
  });

  it("passes through caller-supplied options", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useApi());

    await act(async () => {
      await result.current.call("/api/custom", {
        method: "PUT",
        body: JSON.stringify({ key: "value" }),
      });
    });

    const callArgs = fetchMock.mock.calls[0];
    expect(String(callArgs[0])).toBe("/api/custom");
    expect(callArgs[1]?.method).toBe("PUT");
    expect(callArgs[1]?.body).toBe(JSON.stringify({ key: "value" }));
  });

  it("handles ok:true payloads with error field as success", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({ ok: true, status: "failed", error: "some context" }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useApi<{ status: string; error: string }>());

    await act(async () => {
      await result.current.call("/api/test");
    });

    expect(result.current.data?.status).toBe("failed");
    expect(result.current.error).toBeNull();
  });

  it("handles 404 non-JSON response", async () => {
    const fetchMock = vi.fn(async () =>
      new Response("Not Found", { status: 404, statusText: "Not Found" }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useApi());

    await act(async () => {
      await result.current.call("/api/test");
    });

    expect(result.current.data).toBeNull();
    expect(result.current.error).toContain("404");
    expect(result.current.loading).toBe(false);
  });
});
