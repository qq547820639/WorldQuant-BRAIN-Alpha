import { useState, useEffect, useCallback } from "react";
import { useDebouncedCallback } from "@/hooks/useDebounce";

export interface Breakpoints {
  sm: number;
  md: number;
  lg: number;
  xl: number;
  "2xl": number;
}

export const DEFAULT_BREAKPOINTS: Breakpoints = {
  sm: 640,
  md: 768,
  lg: 1024,
  xl: 1280,
  "2xl": 1536,
};

export interface UseMediaQueryOptions {
  breakpoints?: Partial<Breakpoints>;
  debounceMs?: number;
}

export interface UseMediaQueryResult {
  width: number;
  height: number;
  isMobile: boolean;
  isTablet: boolean;
  isDesktop: boolean;
  isSm: boolean;
  isMd: boolean;
  isLg: boolean;
  isXl: boolean;
  is2Xl: boolean;
  breakpoints: Breakpoints;
}

function getWindowDimensions(): { width: number; height: number } {
  if (typeof window === "undefined") {
    return { width: 0, height: 0 };
  }
  return {
    width: window.innerWidth,
    height: window.innerHeight,
  };
}

export function useMediaQuery(options: UseMediaQueryOptions = {}): UseMediaQueryResult {
  const { breakpoints: customBreakpoints, debounceMs = 100 } = options;

  const breakpoints: Breakpoints = {
    ...DEFAULT_BREAKPOINTS,
    ...customBreakpoints,
  };

  const [dimensions, setDimensions] = useState<{ width: number; height: number }>(() =>
    getWindowDimensions()
  );

  const handleResize = useCallback(() => {
    setDimensions(getWindowDimensions());
  }, []);

  const debouncedHandleResize = useDebouncedCallback(handleResize, debounceMs);

  useEffect(() => {
    if (typeof window === "undefined") return;

    window.addEventListener("resize", debouncedHandleResize);
    return () => {
      window.removeEventListener("resize", debouncedHandleResize);
    };
  }, [debouncedHandleResize]);

  const isSm = dimensions.width >= breakpoints.sm;
  const isMd = dimensions.width >= breakpoints.md;
  const isLg = dimensions.width >= breakpoints.lg;
  const isXl = dimensions.width >= breakpoints.xl;
  const is2Xl = dimensions.width >= breakpoints["2xl"];

  const isMobile = !isMd;
  const isTablet = isMd && !isLg;
  const isDesktop = isLg;

  return {
    width: dimensions.width,
    height: dimensions.height,
    isMobile,
    isTablet,
    isDesktop,
    isSm,
    isMd,
    isLg,
    isXl,
    is2Xl,
    breakpoints,
  };
}
