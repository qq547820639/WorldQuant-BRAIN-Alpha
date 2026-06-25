export function ReadinessMetric({ label, value, tone = "text-text-primary", mono = false }: { label: string; value: string; tone?: string; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-text-tertiary">{label}</dt>
      <dd className={`mt-0.5 truncate font-medium ${tone} ${mono ? "font-mono-value" : ""}`} title={value}>{value}</dd>
    </div>
  );
}
