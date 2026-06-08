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
                  background: stage.status === "complete" ? "oklch(0.52 0.06 155 / 0.15)"
                    : stage.status === "active" ? "oklch(0.65 0.07 80 / 0.15)"
                    : stage.status === "blocked" ? "oklch(0.48 0.12 22 / 0.15)"
                    : "oklch(0.38 0.005 45 / 0.08)",
                  border: `1.5px solid ${
                    stage.status === "complete" ? "oklch(0.52 0.10 155)"
                    : stage.status === "active" ? "oklch(0.65 0.14 80)"
                    : stage.status === "blocked" ? "oklch(0.48 0.12 22)"
                    : "oklch(0.38 0.006 45)"
                  }`,
                  color: stage.status === "complete" ? "oklch(0.62 0.10 160)"
                    : stage.status === "active" ? "oklch(0.65 0.14 80)"
                    : stage.status === "blocked" ? "oklch(0.58 0.12 25)"
                    : "oklch(0.38 0.006 45)",
                  transition: "all 200ms",
                }}>
                  {stage.count}
                </div>
                <div style={{ fontSize: 12, fontWeight: 500, color: stage.status === "pending" ? "oklch(0.38 0.006 45)" : "oklch(0.92 0.003 45)" }}>
                  {stage.label}
                </div>
                <div style={{ fontSize: 11, color: "oklch(0.52 0.006 45)", marginTop: 2 }}>
                  {stage.status === "complete" ? "完成" : stage.status === "active" ? "进行中" : stage.status === "blocked" ? "阻断" : "等待"}
                </div>
              </div>
              {idx < stages.length - 1 && (
                <div style={{
                  width: 40, height: 1,
                  marginTop: 20,
                  background: stage.status === "complete" ? "oklch(0.52 0.10 155)" : "oklch(0.28 0.008 45)",
                  flexShrink: 0,
                }} aria-hidden="true" />
              )}
            </div>
          ))}
        </div>
        <p className="text-xs text-text-tertiary mt-3" style={{ borderTop: "0.5px solid oklch(0.22 0.007 45)", paddingTop: 8 }}>
          本页面不执行真实提交。任何真实提交需另走人工审批。
        </p>
      </div>
    </div>
  );
});
