import { memo, useEffect, useRef } from 'react';

interface DrillStep {
  id: number;
  label: string;
  description: string;
}

export const DrillModal = memo(function DrillModal({
  steps,
  checks,
  onToggle,
  allChecked,
  onClose,
}: {
  steps: DrillStep[];
  checks: Set<number>;
  onToggle: (id: number) => void;
  allChecked: boolean;
  onClose: () => void;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
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
  }, [onClose]);

  return (
    <div
      className="drill-modal-overlay"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'var(--color-overlay-strong)',
        backdropFilter: 'blur(3px)',
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="drill-modal-title"
    >
      <div
        ref={dialogRef}
        className="drill-modal-content"
        style={{
          background: 'var(--color-surface-elevated)',
          borderRadius: 8,
          border: '0.5px solid var(--color-border-default)',
          maxWidth: 480,
          width: 'calc(100% - 32px)',
          maxHeight: '90vh',
          overflow: 'auto',
          padding: '24px 20px 20px',
        }}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'flex-start',
            marginBottom: 16,
          }}
        >
          <div>
            <h3 id="drill-modal-title" className="text-base font-semibold text-text-primary">
              模拟提交演练
            </h3>
            <p className="text-xs text-text-tertiary mt-1">
              逐项确认提交步骤，帮助你在 BRAIN 平台上顺利完成真实提交。
            </p>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            className="btn btn-ghost btn-sm"
            aria-label="关闭"
            style={{ padding: '2px 6px', fontSize: 18, lineHeight: 1 }}
          >
            ✕
          </button>
        </div>

        <div
          className="progress-bar"
          style={{ marginBottom: 16 }}
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={steps.length}
          aria-valuenow={checks.size}
        >
          <div
            className="progress-bar-fill positive"
            style={{ width: `${(checks.size / steps.length) * 100}%` }}
          />
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {steps.map((step) => {
            const checked = checks.has(step.id);
            return (
              <label
                key={step.id}
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 12,
                  padding: '10px 12px',
                  borderRadius: 6,
                  cursor: 'pointer',
                  background: checked
                    ? 'var(--color-step-checked-bg)'
                    : 'var(--color-layer-header-bg)',
                  border: `0.5px solid ${checked ? 'var(--color-step-checked-border)' : 'var(--color-border-default)'}`,
                  transition: 'all 0.15s',
                }}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => onToggle(step.id)}
                  style={{
                    marginTop: 2,
                    flexShrink: 0,
                    accentColor: 'var(--color-status-active-text)',
                  }}
                />
                <div>
                  <span
                    className="text-sm font-medium"
                    style={{
                      color: checked ? 'var(--color-stall-text)' : 'var(--color-step-checked-text)',
                      textDecoration: checked ? 'line-through' : 'none',
                    }}
                  >
                    {step.id}. {step.label}
                  </span>
                  <p className="text-xs text-text-tertiary mt-0.5">{step.description}</p>
                </div>
              </label>
            );
          })}
        </div>

        <div style={{ marginTop: 20, display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button type="button" onClick={onClose} className="btn btn-secondary btn-sm">
            {allChecked ? '完成演练' : '关闭'}
          </button>
          {!allChecked && (
            <span className="text-xs text-text-tertiary self-center">
              已完成 {checks.size}/{steps.length} 步
            </span>
          )}
          {allChecked && (
            <span className="text-xs text-positive self-center" role="status">
              ✅ 全部步骤已确认
            </span>
          )}
        </div>
      </div>
    </div>
  );
});
