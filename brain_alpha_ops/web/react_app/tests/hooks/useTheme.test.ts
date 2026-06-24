import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useTheme } from "@/hooks/useTheme";

const THEME_STORAGE_KEY = "brain-alpha-ops-theme";

describe("useTheme", () => {
  let matchMediaListeners: Map<string, (e: MediaQueryListEvent) => void>;
  let mockMatchMedia: {
    matches: boolean;
    addEventListener: vi.Mock;
    removeEventListener: vi.Mock;
    dispatchEvent: (event: MediaQueryListEvent) => void;
  };

  beforeEach(() => {
    localStorage.clear();
    document.documentElement.classList.remove("dark");

    matchMediaListeners = new Map();

    mockMatchMedia = {
      matches: false,
      addEventListener: vi.fn((type: string, listener: (e: MediaQueryListEvent) => void) => {
        matchMediaListeners.set(type, listener);
      }),
      removeEventListener: vi.fn((type: string) => {
        matchMediaListeners.delete(type);
      }),
      dispatchEvent: (event: MediaQueryListEvent) => {
        const listener = matchMediaListeners.get(event.type);
        if (listener) {
          listener(event);
        }
      },
    };

    vi.stubGlobal("matchMedia", vi.fn(() => mockMatchMedia));
  });

  it("initializes with light theme by default", () => {
    mockMatchMedia.matches = false;

    const { result } = renderHook(() => useTheme());

    expect(result.current.theme).toBe("light");
    expect(result.current.isDark).toBe(false);
  });

  it("initializes with dark theme when system preference is dark", () => {
    mockMatchMedia.matches = true;

    const { result } = renderHook(() => useTheme());

    expect(result.current.theme).toBe("dark");
    expect(result.current.isDark).toBe(true);
  });

  it("reads initial theme from localStorage", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "dark");
    mockMatchMedia.matches = false;

    const { result } = renderHook(() => useTheme());

    expect(result.current.theme).toBe("dark");
    expect(result.current.isDark).toBe(true);
  });

  it("toggleTheme switches between light and dark", () => {
    mockMatchMedia.matches = false;

    const { result } = renderHook(() => useTheme());

    expect(result.current.theme).toBe("light");

    act(() => {
      result.current.toggleTheme();
    });

    expect(result.current.theme).toBe("dark");
    expect(result.current.isDark).toBe(true);

    act(() => {
      result.current.toggleTheme();
    });

    expect(result.current.theme).toBe("light");
    expect(result.current.isDark).toBe(false);
  });

  it("setTheme sets the theme directly", () => {
    mockMatchMedia.matches = false;

    const { result } = renderHook(() => useTheme());

    act(() => {
      result.current.setTheme("dark");
    });

    expect(result.current.theme).toBe("dark");
    expect(result.current.isDark).toBe(true);

    act(() => {
      result.current.setTheme("light");
    });

    expect(result.current.theme).toBe("light");
    expect(result.current.isDark).toBe(false);
  });

  it("persists theme to localStorage when changed", () => {
    mockMatchMedia.matches = false;

    const { result } = renderHook(() => useTheme());

    act(() => {
      result.current.setTheme("dark");
    });

    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");

    act(() => {
      result.current.toggleTheme();
    });

    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
  });

  it("applies dark class to document element", () => {
    mockMatchMedia.matches = false;

    const { result } = renderHook(() => useTheme());

    expect(document.documentElement.classList.contains("dark")).toBe(false);

    act(() => {
      result.current.setTheme("dark");
    });

    expect(document.documentElement.classList.contains("dark")).toBe(true);

    act(() => {
      result.current.setTheme("light");
    });

    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("saves initial theme to localStorage on mount", () => {
    mockMatchMedia.matches = true;

    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();

    renderHook(() => useTheme());

    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
  });

  it("ignores system theme changes after mount because theme is persisted", () => {
    mockMatchMedia.matches = false;

    const { result } = renderHook(() => useTheme());

    expect(result.current.theme).toBe("light");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");

    const changeHandler = mockMatchMedia.addEventListener.mock.calls.find(
      (call: [string, unknown]) => call[0] === "change"
    )[1] as (e: MediaQueryListEvent) => void;

    act(() => {
      mockMatchMedia.matches = true;
      changeHandler({ type: "change", matches: true } as MediaQueryListEvent);
    });

    expect(result.current.theme).toBe("light");
  });

  it("removes event listener on unmount", () => {
    mockMatchMedia.matches = false;

    const { unmount } = renderHook(() => useTheme());

    expect(mockMatchMedia.removeEventListener).not.toHaveBeenCalled();

    unmount();

    expect(mockMatchMedia.removeEventListener).toHaveBeenCalledWith(
      "change",
      expect.any(Function)
    );
  });
});
