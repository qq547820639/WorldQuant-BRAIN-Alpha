import { memo } from 'react';

interface StepProgressBarProps {
  currentStep: number;
}

export const StepProgressBar = memo(function StepProgressBar({
  currentStep,
}: StepProgressBarProps) {
  const steps = [
    { num: 1, label: '账户/缓存', desc: '测试连接或使用已有本地缓存' },
    { num: 2, label: '本地缓存', desc: '首次同步后默认使用本地缓存' },
    { num: 3, label: '开始验证', desc: '运行非提交生产验证流水线' },
  ];

  return (
    <div className="panel panel-step-bar mb-4">
      <div className="flex items-center w-full px-3.5 py-2.5">
        {steps.map((step, i) => {
          const isComplete = currentStep > step.num;
          const isActive = currentStep === step.num;
          const isPending = currentStep < step.num;
          return (
            <div
              key={step.num}
              className="flex items-center min-w-0"
              style={{ flex: i < steps.length - 1 ? 1 : '0 0 auto' }}
            >
              <div
                className="flex items-center justify-center w-7 h-7 rounded-full flex-shrink-0 text-xs font-semibold text-white transition-colors duration-300"
                style={{
                  backgroundColor: isComplete
                    ? 'var(--color-step-complete)'
                    : isActive
                      ? 'var(--color-step-active)'
                      : 'var(--color-step-pending)',
                  color: isPending ? 'var(--color-step-pending-text)' : 'var(--color-on-saturated)',
                }}
              >
                {isComplete ? '✓' : step.num}
              </div>
              <div className="ml-1.5 min-w-0 overflow-hidden">
                <p
                  className={`text-xs font-medium truncate hidden sm:block ${isPending ? 'text-text-tertiary' : 'text-text-primary'}`}
                >
                  {step.label}
                </p>
                <p className="text-xs text-text-tertiary hidden md:block truncate">{step.desc}</p>
                <p
                  className={`sm:hidden text-[10px] font-medium truncate ${isPending ? 'text-text-tertiary' : 'text-text-primary'}`}
                  aria-hidden="true"
                >
                  {step.label.replace(' ', '')}
                </p>
              </div>
              {i < steps.length - 1 && (
                <div
                  className="flex-1 h-0.5 min-w-[8px] max-w-[60px] mx-1.5 transition-colors duration-300"
                  style={{
                    backgroundColor: isComplete
                      ? 'var(--color-step-complete)'
                      : 'var(--color-step-pending)',
                  }}
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
});
