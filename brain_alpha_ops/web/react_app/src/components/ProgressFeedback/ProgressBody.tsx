import { memo } from "react";
import { fmtDuration } from "./progressUtils";

interface ProgressBodyProps {
  state: "idle" | "loading" | "progress" | "success" | "error";
  displayMessage: string;
  displayError: string;
  scanCount: string | null;
  elapsed: number;
  eta: string;
  isStalled: boolean;
}

function ProgressBody({
  state,
  displayMessage,
  displayError,
  scanCount,
  elapsed,
  eta,
  isStalled,
}: ProgressBodyProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 12, fontSize: "0.8125rem", lineHeight: 1.6, color: "var(--color-text-body)" }}>
        <span className="min-w-0 break-words">
          {state === "error" ? displayError : displayMessage}
        </span>
        <span style={{ display: "flex", gap: 12 }}>
          {scanCount && <span style={{ color: "var(--color-text-muted)" }}>{scanCount}</span>}
          {elapsed > 0 && <span className="tabular" style={{ color: "var(--color-text-muted)" }}>已耗时 {fmtDuration(elapsed)}</span>}
          {eta && <span className="tabular" style={{ color: "var(--color-text-muted)" }}>预计剩余 {eta}</span>}
        </span>
      </div>
      {isStalled && (
        <div style={{ fontSize: 12, color: "var(--color-stall-text)", padding: "4px 0" }}>
          BRAIN 服务器仍在响应中，请耐心等待。
        </div>
      )}
    </div>
  );
}

export default memo(ProgressBody);
