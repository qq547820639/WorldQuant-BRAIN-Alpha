import { memo } from "react";

/** Reusable KPI card — Terminal Precision design */
interface KpiCardProps {
  label: string;
  value: string | number;
  subtitle?: string;
  trend?: "up" | "down" | "neutral";
  className?: string;
}

const KpiCard = memo(function KpiCard({ label, value, subtitle, trend, className = "" }: KpiCardProps) {
  const trendClass = trend === "up" ? "text-positive" : trend === "down" ? "text-negative" : "text-text-tertiary";
  const accessibleLabel = `${label}: ${String(value)}${subtitle ? `, ${subtitle}` : ""}`;

  return (
    <div className={`kpi-card ${className}`} role="status" aria-label={accessibleLabel}>
      <p className="kpi-card-label">{label}</p>
      <p className="kpi-card-value">{value}</p>
      {subtitle && <p className={`kpi-card-sub ${trendClass}`}>{subtitle}</p>}
    </div>
  );
});

export default KpiCard;
