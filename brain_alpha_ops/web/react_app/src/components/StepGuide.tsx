/**
 * StepGuide — horizontal step progress bar (UI Design System v3.0)
 * Shows 5 workflow steps with complete/active/pending states.
 */
import { memo } from 'react';
import type { StepGuideItem } from '@/types';

interface Props {
  steps: StepGuideItem[];
}

function CheckIcon() {
  return (
    <svg
      aria-hidden="true"
      width="10"
      height="10"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="3"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

export default memo(function StepGuide({ steps }: Props) {
  if (!steps.length) return null;

  return (
    <div className="step-guide" role="list" aria-label="工作流阶段进度">
      {steps.map((step, idx) => (
        <div key={step.id} style={{ display: 'flex', alignItems: 'center', flexShrink: 0 }}>
          <div
            className={`step ${step.status}`}
            role="listitem"
            aria-current={step.status === 'active' ? 'step' : undefined}
          >
            <div
              className="step-indicator"
              aria-label={`${step.label}: ${step.status === 'complete' ? '已完成' : step.status === 'active' ? '进行中' : '待开始'}`}
            >
              {step.status === 'complete' ? <CheckIcon /> : idx + 1}
            </div>
            <span className="step-label">{step.label}</span>
          </div>
          {idx < steps.length - 1 && (
            <div
              className={`step-connector ${step.status === 'complete' ? 'complete' : step.status === 'active' ? 'active' : ''}`}
              aria-hidden="true"
            />
          )}
        </div>
      ))}
    </div>
  );
});
