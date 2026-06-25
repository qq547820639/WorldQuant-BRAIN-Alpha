import { QualitySummaryItem } from "./CandidateTableSubComponents";
import type { QualitySummaryData } from "./CandidateTableToolbar";

export interface QualitySummaryBarProps {
  qualitySummary: QualitySummaryData;
}

export function QualitySummaryBar({ qualitySummary }: QualitySummaryBarProps) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-4">
      <QualitySummaryItem label="主池保留" value={String(qualitySummary.retained)} />
      <QualitySummaryItem label="可推进" value={String(qualitySummary.promotable)} />
      <QualitySummaryItem label="需优化" value={String(qualitySummary.rework)} />
      <QualitySummaryItem label="阻断" value={String(qualitySummary.blocked)} />
      <QualitySummaryItem label="输出模式" value={qualitySummary.outputMode} />
    </div>
  );
}
