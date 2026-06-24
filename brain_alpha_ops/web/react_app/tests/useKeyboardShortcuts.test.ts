/** Unit tests for useKeyboardShortcuts hook */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useKeyboardShortcuts } from "../src/hooks/useKeyboardShortcuts";

// ── useKeyboardShortcuts Tests ────────────────────────────────

describe("useKeyboardShortcuts", () => {
  const mockOnRefresh = vi.fn();
  const mockOnNavigateToDashboard = vi.fn();
  const mockOnNavigateToConfig = vi.fn();
  const mockOnShowHelp = vi.fn();
  const mockOnEscape = vi.fn();

  beforeEach(() => {
    mockOnRefresh.mockClear();
    mockOnNavigateToDashboard.mockClear();
    mockOnNavigateToConfig.mockClear();
    mockOnShowHelp.mockClear();
    mockOnEscape.mockClear();
  });

  it("calls onShowHelp when ? is pressed", () => {
    renderHook(() =>
      useKeyboardShortcuts({
        onShowHelp: mockOnShowHelp,
      })
    );

    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "?" }));
    });

    expect(mockOnShowHelp).toHaveBeenCalledTimes(1);
  });

  it("calls onRefresh when r is pressed", () => {
    renderHook(() =>
      useKeyboardShortcuts({
        onRefresh: mockOnRefresh,
      })
    );

    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "r" }));
    });

    expect(mockOnRefresh).toHaveBeenCalledTimes(1);
  });

  it("does not call onRefresh when ctrl key is pressed", () => {
    renderHook(() =>
      useKeyboardShortcuts({
        onRefresh: mockOnRefresh,
      })
    );

    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "r", ctrlKey: true }));
    });

    expect(mockOnRefresh).not.toHaveBeenCalled();
  });

  it("calls onNavigateToDashboard when g then d is pressed", () => {
    renderHook(() =>
      useKeyboardShortcuts({
        onNavigateToDashboard: mockOnNavigateToDashboard,
      })
    );

    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "g" }));
    });

    // Should not trigger immediately
    expect(mockOnNavigateToDashboard).not.toHaveBeenCalled();

    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "d" }));
    });

    expect(mockOnNavigateToDashboard).toHaveBeenCalledTimes(1);
  });

  it("calls onNavigateToConfig when g then c is pressed", () => {
    renderHook(() =>
      useKeyboardShortcuts({
        onNavigateToConfig: mockOnNavigateToConfig,
      })
    );

    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "g" }));
    });

    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "c" }));
    });

    expect(mockOnNavigateToConfig).toHaveBeenCalledTimes(1);
  });

  it("calls onEscape when Escape is pressed", () => {
    renderHook(() =>
      useKeyboardShortcuts({
        onEscape: mockOnEscape,
      })
    );

    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    });

    expect(mockOnEscape).toHaveBeenCalledTimes(1);
  });

  it("focuses search input when / is pressed", () => {
    renderHook(() =>
      useKeyboardShortcuts({})
    );

    // Create a search input
    const searchInput = document.createElement("input");
    searchInput.type = "search";
    searchInput.placeholder = "Search...";
    document.body.appendChild(searchInput);

    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "/" }));
    });

    // Search input should be focused
    expect(document.activeElement).toBe(searchInput);

    document.body.removeChild(searchInput);
  });
});

// ── SHORTCUTS_LIST Tests ──────────────────────────────────────

describe("SHORTCUTS_LIST", () => {
  it("exports a list of shortcuts", () => {
    const { SHORTCUTS_LIST } = require("../src/hooks/useKeyboardShortcuts");

    expect(SHORTCUTS_LIST).toBeDefined();
    expect(Array.isArray(SHORTCUTS_LIST)).toBe(true);
    expect(SHORTCUTS_LIST.length).toBeGreaterThan(0);
  });

  it("each shortcut has required properties", () => {
    const { SHORTCUTS_LIST } = require("../src/hooks/useKeyboardShortcuts");

    SHORTCUTS_LIST.forEach((shortcut: { keys: unknown[]; description: string; category: string }) => {
      expect(shortcut).toHaveProperty("keys");
      expect(shortcut).toHaveProperty("description");
      expect(shortcut).toHaveProperty("category");
      expect(Array.isArray(shortcut.keys)).toBe(true);
      expect(shortcut.keys.length).toBeGreaterThan(0);
    });
  });

  it("contains navigation shortcuts", () => {
    const { SHORTCUTS_LIST } = require("../src/hooks/useKeyboardShortcuts");

    const navShortcuts = SHORTCUTS_LIST.filter((s: { category: string }) => s.category === "导航");
    expect(navShortcuts.length).toBeGreaterThan(0);
  });

  it("contains help shortcuts", () => {
    const { SHORTCUTS_LIST } = require("../src/hooks/useKeyboardShortcuts");

    const helpShortcuts = SHORTCUTS_LIST.filter((s: { category: string }) => s.category === "帮助");
    expect(helpShortcuts.length).toBeGreaterThan(0);
  });
});
