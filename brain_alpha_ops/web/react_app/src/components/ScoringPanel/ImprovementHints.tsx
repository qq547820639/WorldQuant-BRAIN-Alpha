import type { FailureItem } from '@/types';
import { safeScoringText } from './utils';

interface Props {
  failures: FailureItem[];
  hints: string[];
}

export default function ImprovementHints({ failures, hints }: Props) {
  if (failures.length === 0 && hints.length === 0) return null;
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <InsightList title="主要失败原因" items={failures} />
      <HintList title="改进建议" items={hints} />
    </div>
  );
}

function InsightList({ title, items }: { title: string; items: FailureItem[] }) {
  return (
    <div className="panel">
      <div className="panel-header">
        <span>{title}</span>
      </div>
      <div className="panel-body">
        {items.map((item, i) => (
          <div
            key={`${item.item || 'failure'}-${i}`}
            className="text-xs px-3.5 py-2 border-b border-border-subtle last:border-0"
          >
            <p className="text-negative font-medium">
              {safeScoringText(item.item, '评分项待确认')}
            </p>
            <p className="text-text-tertiary">
              {safeScoringText(item.reason || item.severity, '原因待确认')}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

function HintList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="panel">
      <div className="panel-header">
        <span>{title}</span>
      </div>
      <div className="panel-body">
        {items.map((item, i) => (
          <p
            key={`${item}-${i}`}
            className="text-xs text-text-secondary px-3.5 py-2 border-b border-border-subtle last:border-0"
          >
            {safeScoringText(item, '建议待确认')}
          </p>
        ))}
      </div>
    </div>
  );
}
