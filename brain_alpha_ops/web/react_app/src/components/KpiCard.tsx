/** Reusable KPI card for dashboard metrics. */

interface Props {
  label: string;
  value: string | number;
  subtitle?: string;
  trend?: "up" | "down" | "neutral";
  className?: string;
}

export default function KpiCard({ label, value, subtitle, trend, className = "" }: Props) {
  const trendColor = trend === "up" ? "text-success" : trend === "down" ? "text-danger" : "text-muted";
  const accessibleLabel = `${label}: ${String(value)}${subtitle ? `, ${subtitle}` : ""}`;

  return (
    <div className={`card ${className}`} role="status" aria-label={accessibleLabel}>
      <p className="text-xs text-muted uppercase tracking-wider mb-1">{label}</p>
      <p className="text-2xl font-bold text-white">{value}</p>
      {subtitle && <p className={`text-xs mt-1 ${trendColor}`}>{subtitle}</p>}
    </div>
  );
}
