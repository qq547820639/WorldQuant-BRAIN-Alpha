import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useIntersectionObserver, useInView } from "@/hooks/useIntersectionObserver";

describe("useIntersectionObserver", () => {
  let mockObserve: ReturnType<typeof vi.fn>;
  let mockUnobserve: ReturnType<typeof vi.fn>;
  let mockDisconnect: ReturnType<typeof vi.fn>;
  let mockCallback: IntersectionObserverCallback;

  beforeEach(() => {
    mockObserve = vi.fn();
    mockUnobserve = vi.fn();
    mockDisconnect = vi.fn();

    vi.stubGlobal(
      "IntersectionObserver",
      class MockIntersectionObserver {
        constructor(callback: IntersectionObserverCallback) {
          mockCallback = callback;
        }
        observe = mockObserve;
        unobserve = mockUnobserve;
        disconnect = mockDisconnect;
        root = null;
        rootMargin = "";
        thresholds = [];
        takeRecords() {
          return [];
        }
      }
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("has initial state with isIntersecting false", () => {
    const { result } = renderHook(() => useIntersectionObserver());
    expect(result.current.isIntersecting).toBe(false);
    expect(result.current.entry).toBeNull();
    expect(typeof result.current.ref).toBe("function");
  });

  it("observes element when ref is set", () => {
    const { result } = renderHook(() => useIntersectionObserver());
    const element = document.createElement("div");

    act(() => {
      result.current.ref(element);
    });

    expect(mockObserve).toHaveBeenCalledWith(element);
  });

  it("updates state when element intersects", () => {
    const { result } = renderHook(() => useIntersectionObserver());
    const element = document.createElement("div");

    act(() => {
      result.current.ref(element);
    });

    const entry = {
      isIntersecting: true,
      target: element,
      intersectionRatio: 1,
      boundingClientRect: {} as DOMRectReadOnly,
      intersectionRect: {} as DOMRectReadOnly,
      rootBounds: null,
      time: 0,
    } as IntersectionObserverEntry;

    act(() => {
      mockCallback([entry], {} as IntersectionObserver);
    });

    expect(result.current.isIntersecting).toBe(true);
    expect(result.current.entry).toBe(entry);
  });

  it("updates state when element leaves viewport", () => {
    const { result } = renderHook(() => useIntersectionObserver());
    const element = document.createElement("div");

    act(() => {
      result.current.ref(element);
    });

    const entry = {
      isIntersecting: true,
      target: element,
      intersectionRatio: 1,
      boundingClientRect: {} as DOMRectReadOnly,
      intersectionRect: {} as DOMRectReadOnly,
      rootBounds: null,
      time: 0,
    } as IntersectionObserverEntry;

    act(() => {
      mockCallback([entry], {} as IntersectionObserver);
    });
    expect(result.current.isIntersecting).toBe(true);

    const exitEntry = {
      ...entry,
      isIntersecting: false,
      intersectionRatio: 0,
    };

    act(() => {
      mockCallback([exitEntry], {} as IntersectionObserver);
    });
    expect(result.current.isIntersecting).toBe(false);
  });

  it("triggerOnce: disconnects after first intersection", () => {
    const { result } = renderHook(() => useIntersectionObserver({ triggerOnce: true }));
    const element = document.createElement("div");

    act(() => {
      result.current.ref(element);
    });

    const entry = {
      isIntersecting: true,
      target: element,
      intersectionRatio: 1,
      boundingClientRect: {} as DOMRectReadOnly,
      intersectionRect: {} as DOMRectReadOnly,
      rootBounds: null,
      time: 0,
    } as IntersectionObserverEntry;

    act(() => {
      mockCallback([entry], {} as IntersectionObserver);
    });

    expect(mockDisconnect).toHaveBeenCalled();
    expect(result.current.isIntersecting).toBe(true);
  });

  it("disconnects on unmount", () => {
    const { result, unmount } = renderHook(() => useIntersectionObserver());
    const element = document.createElement("div");

    act(() => {
      result.current.ref(element);
    });

    unmount();

    expect(mockDisconnect).toHaveBeenCalled();
  });

  it("passes options to IntersectionObserver", () => {
    const options = {
      rootMargin: "100px",
      threshold: 0.5,
    };

    let observerOptions: IntersectionObserverInit | undefined;
    vi.stubGlobal(
      "IntersectionObserver",
      class MockIntersectionObserver {
        constructor(callback: IntersectionObserverCallback, opts: IntersectionObserverInit) {
          observerOptions = opts;
          mockCallback = callback;
        }
        observe = mockObserve;
        unobserve = mockUnobserve;
        disconnect = mockDisconnect;
        root = null;
        rootMargin = "";
        thresholds = [];
        takeRecords() {
          return [];
        }
      }
    );

    const { result } = renderHook(() => useIntersectionObserver(options));
    const element = document.createElement("div");

    act(() => {
      result.current.ref(element);
    });

    expect(observerOptions?.rootMargin).toBe("100px");
    expect(observerOptions?.threshold).toBe(0.5);
  });
});

describe("useInView", () => {
  let mockCallback: IntersectionObserverCallback;

  beforeEach(() => {
    vi.stubGlobal(
      "IntersectionObserver",
      class MockIntersectionObserver {
        constructor(callback: IntersectionObserverCallback) {
          mockCallback = callback;
        }
        observe = vi.fn();
        unobserve = vi.fn();
        disconnect = vi.fn();
        root = null;
        rootMargin = "";
        thresholds = [];
        takeRecords() {
          return [];
        }
      }
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns isInView and ref", () => {
    const { result } = renderHook(() => useInView());
    expect(result.current.isInView).toBe(false);
    expect(typeof result.current.ref).toBe("function");
    expect(result.current.entry).toBeNull();
  });

  it("uses initialInView option", () => {
    const { result } = renderHook(() => useInView({ initialInView: true }));
    expect(result.current.isInView).toBe(true);
  });

  it("updates isInView when intersecting", () => {
    const { result } = renderHook(() => useInView());
    const element = document.createElement("div");

    act(() => {
      result.current.ref(element);
    });

    const entry = {
      isIntersecting: true,
      target: element,
      intersectionRatio: 1,
      boundingClientRect: {} as DOMRectReadOnly,
      intersectionRect: {} as DOMRectReadOnly,
      rootBounds: null,
      time: 0,
    } as IntersectionObserverEntry;

    act(() => {
      mockCallback([entry], {} as IntersectionObserver);
    });

    expect(result.current.isInView).toBe(true);
  });

  it("supports triggerOnce option", () => {
    const disconnectMock = vi.fn();
    vi.stubGlobal(
      "IntersectionObserver",
      class MockIntersectionObserver {
        constructor(callback: IntersectionObserverCallback) {
          mockCallback = callback;
        }
        observe = vi.fn();
        unobserve = vi.fn();
        disconnect = disconnectMock;
        root = null;
        rootMargin = "";
        thresholds = [];
        takeRecords() {
          return [];
        }
      }
    );

    const { result } = renderHook(() => useInView({ triggerOnce: true }));
    const element = document.createElement("div");

    act(() => {
      result.current.ref(element);
    });

    const entry = {
      isIntersecting: true,
      target: element,
      intersectionRatio: 1,
      boundingClientRect: {} as DOMRectReadOnly,
      intersectionRect: {} as DOMRectReadOnly,
      rootBounds: null,
      time: 0,
    } as IntersectionObserverEntry;

    act(() => {
      mockCallback([entry], {} as IntersectionObserver);
    });

    expect(disconnectMock).toHaveBeenCalled();
    expect(result.current.isInView).toBe(true);
  });
});
