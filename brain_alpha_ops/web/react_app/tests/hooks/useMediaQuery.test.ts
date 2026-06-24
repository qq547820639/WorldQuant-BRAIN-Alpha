import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useMediaQuery, DEFAULT_BREAKPOINTS } from "@/hooks/useMediaQuery";

describe("useMediaQuery", () => {
  const originalInnerWidth = window.innerWidth;
  const originalInnerHeight = window.innerHeight;

  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    Object.defineProperty(window, "innerWidth", {
      writable: true,
      value: originalInnerWidth,
    });
    Object.defineProperty(window, "innerHeight", {
      writable: true,
      value: originalInnerHeight,
    });
  });

  const setWindowSize = (width: number, height: number = 800) => {
    Object.defineProperty(window, "innerWidth", {
      writable: true,
      value: width,
    });
    Object.defineProperty(window, "innerHeight", {
      writable: true,
      value: height,
    });
    act(() => {
      window.dispatchEvent(new Event("resize"));
    });
  };

  it("returns initial window dimensions", () => {
    const { result } = renderHook(() => useMediaQuery());

    expect(result.current.width).toBe(window.innerWidth);
    expect(result.current.height).toBe(window.innerHeight);
  });

  it("correctly identifies mobile viewport (below md breakpoint)", () => {
    setWindowSize(500);
    vi.runAllTimers();

    const { result } = renderHook(() => useMediaQuery());

    expect(result.current.isMobile).toBe(true);
    expect(result.current.isTablet).toBe(false);
    expect(result.current.isDesktop).toBe(false);
  });

  it("correctly identifies tablet viewport (md to lg)", () => {
    setWindowSize(900);
    vi.runAllTimers();

    const { result } = renderHook(() => useMediaQuery());

    expect(result.current.isMobile).toBe(false);
    expect(result.current.isTablet).toBe(true);
    expect(result.current.isDesktop).toBe(false);
  });

  it("correctly identifies desktop viewport (lg and above)", () => {
    setWindowSize(1200);
    vi.runAllTimers();

    const { result } = renderHook(() => useMediaQuery());

    expect(result.current.isMobile).toBe(false);
    expect(result.current.isTablet).toBe(false);
    expect(result.current.isDesktop).toBe(true);
  });

  it("correctly reports individual breakpoint flags", () => {
    setWindowSize(1400);
    vi.runAllTimers();

    const { result } = renderHook(() => useMediaQuery());

    expect(result.current.isSm).toBe(true);
    expect(result.current.isMd).toBe(true);
    expect(result.current.isLg).toBe(true);
    expect(result.current.isXl).toBe(true);
    expect(result.current.is2Xl).toBe(false);
  });

  it("updates on window resize", () => {
    setWindowSize(500);
    const { result } = renderHook(() => useMediaQuery());

    expect(result.current.isMobile).toBe(true);

    act(() => {
      setWindowSize(1100);
      vi.runAllTimers();
    });

    expect(result.current.isDesktop).toBe(true);
    expect(result.current.isMobile).toBe(false);
  });

  it("uses custom breakpoints when provided", () => {
    const customBreakpoints = {
      sm: 500,
      md: 700,
      lg: 900,
    };

    setWindowSize(800);
    const { result } = renderHook(() =>
      useMediaQuery({ breakpoints: customBreakpoints })
    );

    expect(result.current.breakpoints.sm).toBe(500);
    expect(result.current.breakpoints.md).toBe(700);
    expect(result.current.breakpoints.lg).toBe(900);
    expect(result.current.isTablet).toBe(true);
  });

  it("includes default breakpoints", () => {
    const { result } = renderHook(() => useMediaQuery());

    expect(result.current.breakpoints).toEqual(DEFAULT_BREAKPOINTS);
  });
});
