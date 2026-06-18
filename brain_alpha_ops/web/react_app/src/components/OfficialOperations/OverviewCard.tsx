/** Overview card for displaying metrics. */

interface Props {
  label: string;
  value: string;
  detail?: string;
  tone?: "success" | "warning" | "neutral";
}

export default function OverviewCard({ label, value, detail, tone = "neutral" }: Props) {
  const toneClass = tone === "success" ? "text-positive" : tone === "warning" ? "text-warning" : "text-text-primary";
  return (
    <div className="panel min-w-0 p-3">
      <p className="text-xs text-text-tertiary">{label}</p>
      <p className={`font-mono-value text-lg font-semibold ${toneClass}`}>{value}</p>
      {detail && <p className="mt-1 text-xs text-text-secondary">{detail}</p>}
    </div>
  );
}
