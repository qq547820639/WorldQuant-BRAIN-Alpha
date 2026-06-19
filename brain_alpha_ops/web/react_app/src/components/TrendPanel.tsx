import React from "react";

export interface TrendData {
  date: string;
  value: number;
}

interface TrendPanelProps {
  title: string;
  data: TrendData[];
  unit: string;
  color?: string;
  currentValue: number;
  change?: number; // 变化百分比
}

const TrendPanel: React.FC<TrendPanelProps> = ({ title, data, unit, color, currentValue, change }) => {
  if (!data || data.length === 0) {
    return (
      <div className="bg-surface-1 rounded-lg p-4 border border-border-subtle">
        <div className="text-sm text-text-secondary mb-2">{title}</div>
        <div className="text-2xl font-bold text-text-primary">
          {currentValue?.toFixed(1)}{" "}
          <span className="text-sm font-normal text-text-tertiary">{unit}</span>
        </div>
        <div className="text-xs text-text-tertiary mt-2">趋势数据将在运行 3 个周期后显示</div>
      </div>
    );
  }

  const maxVal = Math.max(...data.map((d) => d.value), currentValue);
  const minVal = Math.min(...data.map((d) => d.value), currentValue);
  const range = maxVal - minVal || 1;

  return (
    <div className="bg-surface-1 rounded-lg p-4 border border-border-subtle">
      <div className="flex items-center justify-between mb-2">
        <div className="text-sm text-text-secondary">{title}</div>
        {change !== undefined && (
          <span
            className={`text-xs font-medium ${
              change >= 0 ? "text-positive" : "text-negative"
            }`}
          >
            {change >= 0 ? "↑" : "↓"} {Math.abs(change).toFixed(0)}%
          </span>
        )}
      </div>
      <div className="text-2xl font-bold text-text-primary mb-3">
        {currentValue?.toFixed(1)}{" "}
        <span className="text-sm font-normal text-text-tertiary">{unit}</span>
      </div>
      {/* Simple sparkline bar chart */}
      <div className="flex items-end gap-1 h-12">
        {data.slice(-7).map((d, i) => (
          <div key={i} className="flex-1 flex flex-col items-center">
            <div
              className="w-full rounded-t"
              style={{
                height: `${Math.max(8, ((d.value - minVal) / range) * 40)}px`,
                backgroundColor: color || "oklch(0.65 0.14 80)",
                opacity: 0.7,
              }}
              title={`${d.date}: ${d.value?.toFixed(1)} ${unit}`}
            />
          </div>
        ))}
      </div>
      <div className="flex justify-between text-[10px] text-text-tertiary mt-1">
        <span>{data[0]?.date}</span>
        <span>{data[data.length - 1]?.date}</span>
      </div>
    </div>
  );
};

export default TrendPanel;
