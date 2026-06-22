/**
 * StatusFlowDiagram — submission readiness flow visualization (UI Design System v3.0)
 * Shows the checklist → review → submit flow with candidate counts at each stage.
 */
import { memo } from "react";

interface FlowStage {
  label: string;
  count: number;
  status: "complete" | "active" | "blocked" | "pending";
}

interface Props {
  stages: FlowStage[];
}

export default memo(function StatusFlowDiagram({ stages }: Props) {
  if (!stages.length) return null;

  return (
    <div className="panel mb-4" role="region" aria-label="提交状态流转">
      <div className="panel-header">
        <span>提交流转</span>
        <span className="badge badge-neutral">达标 ≠ 可提交</span>
      </div>
      <div className="panel-body-padded">
        <div style={{ display: "flex", alignItems: "flex-start", gap: 0, overflowX: "auto", padding: "8px 0" }}>
          {stages.map((stage, idx) => (
            <div key={stage.label} style={{ display: "flex", alignItems: "flex-start", gap: 0, flexShrink: 0 }}>
              <div style={{ textAlign: "center", minWidth: 100 }}>
                <div style={{
                  width: 40, height: 40, borderRadius: "50%",
                  margin: "0 auto 8px",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 16, fontWeight: 500,
                  fontFamily: "var(--font-mono)",
                  background: stage.status === "complete" ? "var(--color-status-complete-bg)"
                    : stage.status === "active" ? "var(--color-status-active-bg)"
                    : stage.status === "blocked" ? "var(--color-status-blocked-bg)"
                    : "var(--color-status-pending-bg)",
                  border: `1.5px solid ${
                    stage.status === "complete" ? "var(--color-status-complete-border)"
                    : stage.status === "active" ? "var(--color-status-active-text)"
                    : stage.status === "blocked" ? "var(--color-status-blocked-border)"
                    : "var(--color-text-dim)"
                  }`,
                  color: stage.status === "complete" ? "var(--color-status-complete-text)"
                    : stage.status === "active" ? "var(--color-status-active-text)"
                    : stage.status === "blocked" ? "var(--color-status-blocked-text)"
                    : "var(--color-text-dim)",
                  transition: "all 200ms",
                }}>
                  {stage.count}
                </div>
                <div style={{ fontSize: 12, fontWeight: 500, color: stage.status === "pending" ? "var(--color-text-dim)" : "var(--color-text-bright)" }}>
                  {stage.label}
                </div>
                <div style={{ fontSize: 11, color: "var(--color-text-muted)", marginTop: 2 }}>
                  {stage.status === "complete" ? "完成" : stage.status === "active" ? "进行中" : stage.status === "blocked" ? "阻断" : "等待"}
                </div>
              </div>
              {idx < stages.length - 1 && (
                <div style={{
                  width: 40, height: 1,
                  marginTop: 20,
                  background: stage.status === "complete" ? "var(--color-status-complete-border)" : "var(--color-border-medium)",
                  flexShrink: 0,
                }} aria-hidden="true" />
              )}
            </div>
          ))}
        </div>
        <p className="text-xs text-text-tertiary mt-3" style={{ borderTop: "0.5px solid var(--color-border-default)", paddingTop: 8 }}>
          本页面不执行真实提交。任何真实提交需另走人工审批。
        </p>
      </div>
    </div>
  );
});
