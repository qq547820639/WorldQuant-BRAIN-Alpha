import { useEffect, useRef } from 'react';
import { SHORTCUTS_LIST } from '@/hooks/useKeyboardShortcuts';

interface KeyboardShortcutsHelpProps {
  open: boolean;
  onClose: () => void;
}

export default function KeyboardShortcutsHelp({ open, onClose }: KeyboardShortcutsHelpProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;

    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const timer = setTimeout(() => {
      closeButtonRef.current?.focus();
    }, 50);

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    document.addEventListener('keydown', handleKeyDown);

    return () => {
      document.body.style.overflow = originalOverflow;
      document.removeEventListener('keydown', handleKeyDown);
      clearTimeout(timer);
    };
  }, [open, onClose]);

  const handleBackdropClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  if (!open) return null;

  const groupedShortcuts = SHORTCUTS_LIST.reduce<Record<string, typeof SHORTCUTS_LIST>>(
    (acc, shortcut) => {
      if (!acc[shortcut.category]) {
        acc[shortcut.category] = [];
      }
      acc[shortcut.category].push(shortcut);
      return acc;
    },
    {}
  );

  return (
    <div
      className="fixed inset-0 z-[999] flex items-center justify-center"
      style={{
        background: 'var(--color-overlay-strong)',
        backdropFilter: 'blur(3px)',
        animation: 'fade-in-overlay 0.2s ease-out',
      }}
      onClick={handleBackdropClick}
      role="dialog"
      aria-modal="true"
      aria-labelledby="keyboard-shortcuts-title"
    >
      <div
        ref={dialogRef}
        className="relative w-full max-w-[520px] mx-4"
        style={{
          background: 'var(--color-surface-deep)',
          border: '0.5px solid var(--color-border-default)',
          borderRadius: 8,
          boxShadow: '0 12px 40px rgba(0, 0, 0, 0.5)',
          animation: 'dialog-in 0.25s cubic-bezier(0.16, 1, 0.3, 1)',
        }}
      >
        <div className="px-5 pt-5 pb-4">
          <div className="flex items-center justify-between">
            <h2
              id="keyboard-shortcuts-title"
              className="text-sm font-semibold text-text-primary leading-tight"
            >
              键盘快捷键
            </h2>
            <button
              ref={closeButtonRef}
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={onClose}
              aria-label="关闭"
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                aria-hidden="true"
                focusable="false"
              >
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
          <p className="mt-1 text-xs text-text-secondary">
            按 <Kbd>?</Kbd> 随时打开此帮助
          </p>
        </div>

        <div className="px-5 pb-5" style={{ maxHeight: '60vh', overflowY: 'auto' }}>
          {Object.entries(groupedShortcuts).map(([category, shortcuts]) => (
            <div key={category} className="mb-4 last:mb-0">
              <div
                className="text-[10px] font-semibold uppercase tracking-wider text-text-tertiary mb-2"
                style={{ letterSpacing: '0.04em' }}
              >
                {category}
              </div>
              <div className="space-y-1">
                {shortcuts.map((shortcut, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between py-1.5 px-2 rounded-md hover:bg-surface-hover"
                  >
                    <span className="text-xs text-text-secondary">{shortcut.description}</span>
                    <div className="flex items-center gap-1">
                      {shortcut.keys.map((key, keyIdx) => (
                        <span key={keyIdx} className="flex items-center gap-1">
                          {keyIdx > 0 && (
                            <span className="text-text-tertiary text-xs mx-0.5">然后</span>
                          )}
                          <Kbd>{key}</Kbd>
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        <div
          className="flex items-center justify-end gap-2 px-5 py-3"
          style={{
            borderTop: '0.5px solid var(--color-border-default)',
            background: 'var(--color-surface-1)',
            borderRadius: '0 0 8px 8px',
          }}
        >
          <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>
            关闭
          </button>
        </div>
      </div>

      <style>{`
        @keyframes fade-in-overlay {
          from { opacity: 0; }
          to   { opacity: 1; }
        }
        @keyframes dialog-in {
          from {
            opacity: 0;
            transform: translateY(8px) scale(0.98);
          }
          to {
            opacity: 1;
            transform: translateY(0) scale(1);
          }
        }
        @media (prefers-reduced-motion: reduce) {
          @keyframes fade-in-overlay {
            from { opacity: 1; }
            to   { opacity: 1; }
          }
          @keyframes dialog-in {
            from { opacity: 1; transform: none; }
            to   { opacity: 1; transform: none; }
          }
        }
      `}</style>
    </div>
  );
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd
      className="inline-flex items-center justify-center min-w-[24px] h-[22px] px-1.5 text-[11px] font-medium rounded"
      style={{
        fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
        background: 'var(--color-kbd-bg)',
        color: 'var(--color-text-bright)',
        border: '0.5px solid var(--color-kbd-border)',
        lineHeight: 1,
      }}
    >
      {children}
    </kbd>
  );
}
