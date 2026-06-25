import { memo } from 'react';

export const QualitySummaryItem = memo(function QualitySummaryItem({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="kpi-card">
      <p className="kpi-card-label">{label}</p>
      <p className="font-mono-value text-base font-medium text-text-primary">{value}</p>
    </div>
  );
});
