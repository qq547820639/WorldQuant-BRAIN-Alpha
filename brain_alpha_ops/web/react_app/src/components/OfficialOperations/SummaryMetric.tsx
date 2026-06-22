/** Summary metric display for label/value pairs. */

interface Props {
  label: string;
  value: string;
  title?: string;
  mono?: boolean;
}

export default function SummaryMetric({ label, value, title, mono = false }: Props) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-text-tertiary">{label}</dt>
      <dd className={`mt-1 truncate text-sm font-semibold text-text-primary ${mono ? "font-mono-value" : ""}`} title={title || value}>{value}</dd>
    </div>
  );
}
