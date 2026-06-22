interface DrillStep {
  id: number;
  label: string;
  description: string;
}

export function DrillModal({
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
  return (
    <div
      className="drill-modal-overlay"
      style={{
        position: "fixed", inset: 0, zIndex: 9999,
        display: "flex", alignItems: "center", justifyContent: "center",
        background: "oklch(0 0 0 / 0.55)", backdropFilter: "blur(3px)",
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      role="dialog"
      aria-modal="true"
      aria-label="模拟提交演练"
    >
      <div
        className="drill-modal-content"
        style={{
          background: "oklch(0.115 0.007 45)", borderRadius: 8,
          border: "0.5px solid oklch(0.22 0.007 45)",
          maxWidth: 480, width: "calc(100% - 32px)", maxHeight: "90vh",
          overflow: "auto", padding: "24px 20px 20px",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
          <div>
            <h3 className="text-base font-semibold text-text-primary">模拟提交演练</h3>
            <p className="text-xs text-text-tertiary mt-1">
              逐项确认提交步骤，帮助你在 BRAIN 平台上顺利完成真实提交。
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="btn btn-ghost btn-sm"
            aria-label="关闭"
            style={{ padding: "2px 6px", fontSize: 18, lineHeight: 1 }}
          >
            ✕
          </button>
        </div>

        <div className="progress-bar" style={{ marginBottom: 16 }} role="progressbar" aria-valuemin={0} aria-valuemax={steps.length} aria-valuenow={checks.size}>
          <div className="progress-bar-fill positive" style={{ width: `${(checks.size / steps.length) * 100}%` }} />
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {steps.map((step) => {
            const checked = checks.has(step.id);
            return (
              <label
                key={step.id}
                style={{
                  display: "flex", alignItems: "flex-start", gap: 12,
                  padding: "10px 12px", borderRadius: 6,
                  cursor: "pointer",
                  background: checked ? "oklch(0.55 0.08 85 / 0.08)" : "oklch(0.10 0.005 45 / 0.50)",
                  border: `0.5px solid ${checked ? "oklch(0.55 0.10 85 / 0.30)" : "oklch(0.22 0.007 45)"}`,
                  transition: "all 0.15s",
                }}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => onToggle(step.id)}
                  style={{ marginTop: 2, flexShrink: 0, accentColor: "oklch(0.65 0.14 80)" }}
                />
                <div>
                  <span
                    className="text-sm font-medium"
                    style={{
                      color: checked ? "oklch(0.75 0.10 85)" : "oklch(0.62 0.01 45)",
                      textDecoration: checked ? "line-through" : "none",
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

        <div style={{ marginTop: 20, display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button type="button" onClick={onClose} className="btn btn-secondary btn-sm">
            {allChecked ? "完成演练" : "关闭"}
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
}
