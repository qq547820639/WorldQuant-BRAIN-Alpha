import { memo } from "react";

/** Operation metric display. */

interface Props {
  label: string;
  value: string;
  tone?: "success" | "warning" | "neutral";
}

function OperationMetric({ label, value, tone = "neutral" }: Props) {
  const toneClass = tone === "success" ? "text-positive" : tone === "warning" ? "text-warning" : "text-text-secondary";
  return (
    <div className="rounded-md border border-border-subtle bg-surface-1 p-2">
      <p className="text-xs text-text-tertiary">{label}</p>
      <p className={`font-mono-value text-sm font-medium ${toneClass}`}>{value}</p>
    </div>
  );
}

export default memo(OperationMetric);
