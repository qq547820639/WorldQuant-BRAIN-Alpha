import React from 'react';

interface Step {
  phase: string;
  title: string;
  description: string;
  action: string;
}

const FLOW_STEPS: Step[] = [
  {
    phase: 'connect',
    title: '连接与就绪',
    description: '验证 BRAIN 平台连接，同步云端 Alpha 数据，确保系统处于可工作状态',
    action: '点击「官方操作」面板中的「同步云端 Alpha」按钮开始'
  },
  {
    phase: 'discover',
    title: '候选发现',
    description: '基于 BRAIN 平台数据生成候选 Alpha 因子，支持假设驱动、经验反馈和随机探索三种模式',
    action: '在「候选管理」页面点击「生成候选」开始探索'
  },
  {
    phase: 'evaluate',
    title: '评估与验证',
    description: '对候选 Alpha 进行本地预筛选和多维度质量评分，通过 8 项硬性门禁检查',
    action: '点击候选行的「检查」按钮，系统将自动完成评分和门禁验证'
  },
  {
    phase: 'ready',
    title: '提交就绪',
    description: '通过所有门禁检查的 Alpha 可进入提交审批流程。注意：Web 控制台不允许直接提交，需走人工审批路径',
    action: '在「提交确认」面板中复核通过项，确认后发起审批'
  }
];

interface FlowGuideProps {
  currentPhase: string;
  onDismiss?: () => void;
}

export const FlowGuide: React.FC<FlowGuideProps> = ({ currentPhase, onDismiss }) => {
  const [dismissed, setDismissed] = React.useState(false);

  if (dismissed) return null;

  const currentStep = FLOW_STEPS.find(s => s.phase === currentPhase);

  return (
    <div className="rounded-lg p-4 mb-4" style={{ background: "oklch(0.58 0.06 245 / 0.10)", border: "1px solid oklch(0.58 0.10 245 / 0.25)" }}>
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <h3 className="text-sm font-semibold mb-2" style={{ color: "oklch(0.68 0.10 248)" }}>
            📋 流程指引 — {currentStep?.title || currentPhase}
          </h3>
          <p className="text-sm mb-2" style={{ color: "oklch(0.58 0.12 245)" }}>
            {currentStep?.description}
          </p>
          <p className="text-xs rounded px-2 py-1 inline-block" style={{ background: "oklch(0.58 0.06 245 / 0.15)", color: "oklch(0.58 0.12 245)" }}>
            💡 {currentStep?.action}
          </p>
          <div className="mt-3 flex gap-1">
            {FLOW_STEPS.map((step, idx) => {
              const currentIdx = FLOW_STEPS.findIndex(s => s.phase === currentPhase);
              return (
                <div
                  key={step.phase}
                  className="h-1.5 flex-1 rounded-full"
                  style={{
                    background:
                      step.phase === currentPhase
                        ? "oklch(0.58 0.12 245)"
                        : currentIdx > idx
                        ? "oklch(0.58 0.06 245 / 0.40)"
                        : "oklch(0.22 0.007 45)",
                  }}
                  title={step.title}
                />
              );
            })}
          </div>
        </div>
        {onDismiss && (
          <button
            onClick={() => { setDismissed(true); onDismiss?.(); }}
            className="text-xs ml-2 hover:opacity-80"
            style={{ color: "oklch(0.58 0.10 245)" }}
          >
            ✕
          </button>
        )}
      </div>
    </div>
  );
};
