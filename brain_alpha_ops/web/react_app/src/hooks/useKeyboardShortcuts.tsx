/**
 * useKeyboardShortcuts — custom hook for keyboard shortcuts.
 * Provides global keyboard navigation and quick actions.
 */
import { useEffect, useCallback } from "react";

interface ShortcutHandlers {
  onNavigateDashboard?: () => void;
  onNavigateCandidates?: () => void;
  onNavigateConfig?: () => void;
  onToggleSidebar?: () => void;
  onRefresh?: () => void;
  onEscape?: () => void;
}

export function useKeyboardShortcuts(handlers: ShortcutHandlers) {
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    // Don't handle shortcuts when typing in inputs
    if (
      e.target instanceof HTMLInputElement ||
      e.target instanceof HTMLTextAreaElement ||
      e.target instanceof HTMLSelectElement
    ) {
      return;
    }

    const key = e.key.toLowerCase();
    const ctrl = e.ctrlKey || e.metaKey;

    // Ctrl/Cmd + key shortcuts
    if (ctrl) {
      switch (key) {
        case "1":
          e.preventDefault();
          handlers.onNavigateDashboard?.();
          break;
        case "2":
          e.preventDefault();
          handlers.onNavigateCandidates?.();
          break;
        case "3":
          e.preventDefault();
          handlers.onNavigateConfig?.();
          break;
        case "r":
          e.preventDefault();
          handlers.onRefresh?.();
          break;
      }
      return;
    }

    // Single key shortcuts
    switch (key) {
      case "escape":
        handlers.onEscape?.();
        break;
      case "b":
        handlers.onToggleSidebar?.();
        break;
    }
  }, [handlers]);

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);
}

/**
 * KeyboardShortcutsHelp — modal showing available keyboard shortcuts.
 */
export function KeyboardShortcutsHelp({ onClose }: { onClose: () => void }) {
  const shortcuts = [
    { keys: ["Ctrl", "1"], action: "Navigate to Dashboard" },
    { keys: ["Ctrl", "2"], action: "Navigate to Candidates" },
    { keys: ["Ctrl", "3"], action: "Navigate to Config" },
    { keys: ["Ctrl", "R"], action: "Refresh data" },
    { keys: ["B"], action: "Toggle sidebar" },
    { keys: ["Esc"], action: "Close modal / Cancel" },
  ];

  return (
    <div
      className="modal-overlay"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Keyboard shortcuts"
    >
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Keyboard Shortcuts</h2>
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Close">
            &times;
          </button>
        </div>
        <div className="modal-body">
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", padding: "8px", borderBottom: "1px solid oklch(0.28 0.008 45)", color: "oklch(0.52 0.006 45)", fontSize: "11px", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em" }}>Keys</th>
                <th style={{ textAlign: "left", padding: "8px", borderBottom: "1px solid oklch(0.28 0.008 45)", color: "oklch(0.52 0.006 45)", fontSize: "11px", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em" }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {shortcuts.map((shortcut, i) => (
                <tr key={i}>
                  <td style={{ padding: "8px", borderBottom: "1px solid oklch(0.18 0.007 45)" }}>
                    {shortcut.keys.map((key, j) => (
                      <kbd key={j} style={{
                        display: "inline-block",
                        padding: "2px 6px",
                        fontSize: "12px",
                        fontFamily: "var(--font-mono, monospace)",
                        background: "oklch(0.22 0.008 45)",
                        color: "oklch(0.92 0.003 45)",
                        borderRadius: "4px",
                        marginRight: "4px",
                        border: "0.5px solid oklch(0.30 0.008 45)",
                      }}>
                        {key}
                      </kbd>
                    ))}
                  </td>
                  <td style={{ padding: "8px", borderBottom: "1px solid oklch(0.18 0.007 45)", color: "oklch(0.82 0.004 45)" }}>
                    {shortcut.action}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
