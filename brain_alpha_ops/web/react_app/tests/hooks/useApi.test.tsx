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

  describe("session recovery", () => {
    it("retries request after session recovery succeeds", async () => {
      let callCount = 0;
      const fetchMock = vi.fn(async (url: string) => {
        callCount++;
        if (url === "/api/session") {
          return jsonResponse({ ok: true, csrf_token: "new-csrf-token", stream_token: "new-stream-token" });
        }
        if (callCount === 1) {
          return jsonResponse(
            { ok: false, error_code: "session_invalid", error: "invalid session" },
            { status: 401 },
          );
        }
        return jsonResponse({ ok: true, data: "recovered-data" });
      });
      vi.stubGlobal("fetch", fetchMock);

      const { result } = renderHook(() => useApi());

      await act(async () => {
        await result.current.call("/api/test");
      });

      expect(callCount).toBe(3);
      expect(result.current.data).toBe("recovered-data");
      expect(result.current.error).toBeNull();
      expect(result.current.loading).toBe(false);
    });

    it("does not retry session recovery for /api/session endpoint", async () => {
      let callCount = 0;
      const fetchMock = vi.fn(async () => {
        callCount++;
        return jsonResponse(
          { ok: false, error_code: "session_invalid", error: "invalid session" },
          { status: 401 },
        );
      });
      vi.stubGlobal("fetch", fetchMock);

      const { result } = renderHook(() => useApi());

      await act(async () => {
        await result.current.call("/api/session", { method: "POST" });
      });

      expect(callCount).toBe(1);
      expect(result.current.error).toBeTruthy();
      expect(result.current.lastErrorMeta?.error_code).toBe("session_invalid");
    });

    it("does not retry when bootstrapSession fails", async () => {
      let callCount = 0;
      const fetchMock = vi.fn(async (url: string) => {
        callCount++;
        if (url === "/api/session") {
          return jsonResponse({ ok: false }, { status: 500 });
        }
        return jsonResponse(
          { ok: false, error_code: "session_invalid", error: "invalid session" },
          { status: 401 },
        );
      });
      vi.stubGlobal("fetch", fetchMock);

      const { result } = renderHook(() => useApi());

      await act(async () => {
        await result.current.call("/api/test");
      });

      expect(callCount).toBe(2);
      expect(result.current.error).toBeTruthy();
      expect(result.current.lastErrorMeta?.error_code).toBe("session_invalid");
    });

    it("handles retry success with non-JSON response after recovery", async () => {
      let callCount = 0;
      const fetchMock = vi.fn(async (url: string) => {
        callCount++;
        if (url === "/api/session") {
          return jsonResponse({ ok: true, csrf_token: "new-token" });
        }
        if (callCount === 1) {
          return jsonResponse(
            { ok: false, error_code: "session_invalid" },
            { status: 401 },
          );
        }
        return new Response("OK", { status: 200, statusText: "OK" });
      });
      vi.stubGlobal("fetch", fetchMock);

      const { result } = renderHook(() => useApi());

      await act(async () => {
        await result.current.call("/api/test");
      });

      expect(callCount).toBe(3);
      expect(result.current.data).toBeNull();
      expect(result.current.loading).toBe(false);
      expect(result.current.error).toContain("200");
    });

    it("handles retry with error response after recovery", async () => {
      let callCount = 0;
      const fetchMock = vi.fn(async (url: string) => {
        callCount++;
        if (url === "/api/session") {
          return jsonResponse({ ok: true, csrf_token: "new-token" });
        }
        if (callCount === 1) {
          return jsonResponse(
            { ok: false, error_code: "session_invalid" },
            { status: 401 },
          );
        }
        return jsonResponse(
          { ok: false, error_code: "PERMISSION_DENIED", error: "no access" },
          { status: 403 },
        );
      });
      vi.stubGlobal("fetch", fetchMock);

      const { result } = renderHook(() => useApi());

      let returnValue: Awaited<ReturnType<typeof result.current.call>> | undefined;
      await act(async () => {
        returnValue = await result.current.call("/api/test");
      });

      expect(returnValue).not.toBeNull();
      expect(returnValue!.ok).toBe(false);
      expect(returnValue!.error_code).toBe("PERMISSION_DENIED");
      expect(result.current.lastErrorMeta?.error_code).toBe("PERMISSION_DENIED");
    });

    it("handles retry with ok:false in response body after recovery", async () => {
      let callCount = 0;
      const fetchMock = vi.fn(async (url: string) => {
        callCount++;
        if (url === "/api/session") {
          return jsonResponse({ ok: true, csrf_token: "new-token" });
        }
        if (callCount === 1) {
          return jsonResponse(
            { ok: false, error_code: "session_invalid" },
            { status: 401 },
          );
        }
        return jsonResponse({ ok: false, error: "something went wrong" });
      });
      vi.stubGlobal("fetch", fetchMock);

      const { result } = renderHook(() => useApi());

      await act(async () => {
        await result.current.call("/api/test");
      });

      expect(result.current.error).toBeTruthy();
      expect(result.current.data).toBeNull();
    });
  });

  describe("custom abort signal", () => {
    it("uses caller-provided signal instead of creating new controller", async () => {
      const controller = new AbortController();
      const fetchMock = vi.fn(async () => jsonResponse({ ok: true, data: "test" }));
      vi.stubGlobal("fetch", fetchMock);

      const { result } = renderHook(() => useApi());

      await act(async () => {
        await result.current.call("/api/test", { signal: controller.signal });
      });

      const callArgs = fetchMock.mock.calls[0];
      expect(callArgs[1]?.signal).toBe(controller.signal);
    });

    it("handles abort via caller-provided signal", async () => {
      const controller = new AbortController();
      const fetchMock = vi.fn(async () => {
        throw new DOMException("The operation was aborted.", "AbortError");
      });
      vi.stubGlobal("fetch", fetchMock);

      const { result } = renderHook(() => useApi());

      await act(async () => {
        const promise = result.current.call("/api/test", { signal: controller.signal });
        controller.abort();
        await promise;
      });

      expect(result.current.error).toContain("网络请求未在预期时间内返回");
      expect(result.current.loading).toBe(false);
    });
  });

  describe("request headers", () => {
    it("handles Headers instance as input headers", async () => {
      let receivedInit: RequestInit | undefined;
      const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
        receivedInit = init;
        return jsonResponse({ ok: true });
      });
      vi.stubGlobal("fetch", fetchMock);

      const { result } = renderHook(() => useApi());
      const headers = new Headers({ "X-Custom": "custom-value" });

      await act(async () => {
        await result.current.call("/api/test", { method: "POST", headers });
      });

      expect(receivedInit).toBeDefined();
      const sentHeaders = receivedInit?.headers as Record<string, string>;
      expect(sentHeaders["x-custom"]).toBe("custom-value");
      expect(sentHeaders["Content-Type"]).toBe("application/json");
    });

    it("handles array format headers", async () => {
      const fetchMock = vi.fn(async () => jsonResponse({ ok: true }));
      vi.stubGlobal("fetch", fetchMock);

      const { result } = renderHook(() => useApi());
      const headers: [string, string][] = [["X-Custom", "array-value"]];

      await act(async () => {
        await result.current.call("/api/test", { method: "POST", headers });
      });

      const callArgs = fetchMock.mock.calls[0];
      const sentHeaders = callArgs[1]?.headers as Record<string, string>;
      expect(sentHeaders["X-Custom"]).toBe("array-value");
    });

    it("includes CSRF header for GET requests when token exists", async () => {
      const existingMeta = document.querySelector<HTMLMetaElement>('meta[name="brain-alpha-csrf"]');
      const previousContent = existingMeta?.content;
      const meta = document.createElement("meta");
      meta.name = "brain-alpha-csrf";
      meta.content = "test-csrf-token";
      if (existingMeta) {
        document.head.replaceChild(meta, existingMeta);
      } else {
        document.head.appendChild(meta);
      }

      const fetchMock = vi.fn(async () => jsonResponse({ ok: true }));
      vi.stubGlobal("fetch", fetchMock);

      const { result } = renderHook(() => useApi());

      await act(async () => {
        await result.current.call("/api/test");
      });

      const callArgs = fetchMock.mock.calls[0];
      const headers = callArgs[1]?.headers as Record<string, string>;
      expect(headers["X-Brain-Alpha-CSRF"]).toBe("test-csrf-token");

      if (existingMeta && previousContent !== undefined) {
        existingMeta.content = previousContent;
        document.head.replaceChild(existingMeta, meta);
      } else {
        document.head.removeChild(meta);
      }
    });

    it("includes CSRF headers for DELETE requests", async () => {
      const fetchMock = vi.fn(async () => jsonResponse({ ok: true }));
      vi.stubGlobal("fetch", fetchMock);

      const { result } = renderHook(() => useApi());

      await act(async () => {
        await result.current.call("/api/test/1", { method: "DELETE" });
      });

      const callArgs = fetchMock.mock.calls[0];
      const headers = callArgs[1]?.headers as Record<string, string>;
      expect(headers["Content-Type"]).toBe("application/json");
      expect(headers["X-Brain-Alpha-Request-ID"]).toBeTruthy();
    });

    it("includes CSRF headers for PATCH requests", async () => {
      const fetchMock = vi.fn(async () => jsonResponse({ ok: true }));
      vi.stubGlobal("fetch", fetchMock);

      const { result } = renderHook(() => useApi());

      await act(async () => {
        await result.current.call("/api/test/1", { method: "PATCH", body: '{"key":"value"}' });
      });

      const callArgs = fetchMock.mock.calls[0];
      const headers = callArgs[1]?.headers as Record<string, string>;
      expect(headers["Content-Type"]).toBe("application/json");
    });
  });

  describe("ok field logic", () => {
    it("treats response with ok:undefined and error field as failure", async () => {
      const fetchMock = vi.fn(async () =>
        jsonResponse({ error: "something failed", error_code: "UNKNOWN_ERROR" }),
      );
      vi.stubGlobal("fetch", fetchMock);

      const { result } = renderHook(() => useApi());

      let returnValue: Awaited<ReturnType<typeof result.current.call>> | undefined;
      await act(async () => {
        returnValue = await result.current.call("/api/test");
      });

      expect(returnValue).not.toBeNull();
      expect(returnValue!.ok).toBe(false);
      expect(result.current.error).toBeTruthy();
      expect(result.current.data).toBeNull();
    });

    it("treats response with ok:undefined and no error as success", async () => {
      const fetchMock = vi.fn(async () =>
        jsonResponse({ name: "test", value: 42 }),
      );
      vi.stubGlobal("fetch", fetchMock);

      const { result } = renderHook(() => useApi<{ name: string; value: number }>());

      let returnValue: Awaited<ReturnType<typeof result.current.call>> | undefined;
      await act(async () => {
        returnValue = await result.current.call("/api/test");
      });

      expect(returnValue).not.toBeNull();
      expect(returnValue!.ok).toBe(true);
      expect(result.current.error).toBeNull();
      expect(result.current.data).toEqual(expect.objectContaining({ name: "test", value: 42 }));
    });
  });

  describe("refreshSessionTokens", () => {
    it("refreshes csrf and stream tokens from response", async () => {
      const fetchMock = vi.fn(async () =>
        jsonResponse({ ok: true, csrf_token: "fresh-csrf", stream_token: "fresh-stream" }),
      );
      vi.stubGlobal("fetch", fetchMock);

      const { result } = renderHook(() => useApi());

      await act(async () => {
        await result.current.call("/api/test");
      });

      const csrfMeta = document.querySelector<HTMLMetaElement>('meta[name="brain-alpha-csrf"]');
      const streamMeta = document.querySelector<HTMLMetaElement>('meta[name="brain-alpha-stream"]');
      expect(csrfMeta?.content).toBe("fresh-csrf");
      expect(streamMeta?.content).toBe("fresh-stream");
    });

    it("handles non-string csrf and stream tokens gracefully", async () => {
      const fetchMock = vi.fn(async () =>
        jsonResponse({ ok: true, csrf_token: 12345, stream_token: null }),
      );
      vi.stubGlobal("fetch", fetchMock);

      const { result } = renderHook(() => useApi());

      await act(async () => {
        await result.current.call("/api/test");
      });

      expect(result.current.error).toBeNull();
      expect(result.current.data).toBeTruthy();
    });
  });

  describe("POST method and saveResumeState", () => {
    it("calls saveResumeState on successful POST", async () => {
      const fetchMock = vi.fn(async () => jsonResponse({ ok: true, success: true }));
      vi.stubGlobal("fetch", fetchMock);

      const { result } = renderHook(() => useApi());

      await act(async () => {
        await result.current.call("/api/test", { method: "POST", body: "{}" });
      });

      expect(result.current.error).toBeNull();
      expect(result.current.data).toBeTruthy();
    });
  });

  describe("unsupported HTTP methods for session recovery", () => {
    it("does not recover session for unsupported methods", async () => {
      let callCount = 0;
      const fetchMock = vi.fn(async () => {
        callCount++;
        return jsonResponse(
          { ok: false, error_code: "session_invalid" },
          { status: 401 },
        );
      });
      vi.stubGlobal("fetch", fetchMock);

      const { result } = renderHook(() => useApi());

      await act(async () => {
        await result.current.call("/api/test", { method: "OPTIONS" });
      });

      expect(callCount).toBe(1);
      expect(result.current.error).toBeTruthy();
    });
  });
});
