interface GuidePanelProps {
  show: boolean;
  currentStep: number;
  phasePending: boolean;
  phaseFailed: boolean;
  contextFresh: boolean;
  connected: boolean;
  onDismiss: () => void;
  onReshow: () => void;
}

export function GuidePanel({
  show,
  currentStep,
  phasePending,
  phaseFailed,
  contextFresh,
  connected,
  onDismiss,
  onReshow,
}: GuidePanelProps) {
  if (show) {
    return (
      <div className="panel mb-4 guide-panel">
        <div className="panel-body-padded flex justify-between items-start gap-3">
          <div>
            <p className="text-sm font-medium text-info mb-2">首次使用？按顺序完成以下步骤</p>
            <div className="grid gap-1 text-xs text-text-secondary guide-steps">
              <StepLabel step={1} currentStep={currentStep} />
              <span>
                {phasePending
                  ? "正在读取本地缓存和账户状态"
                  : phaseFailed
                    ? "状态读取失败，请刷新页面或重新打开本地控制台"
                    : contextFresh && !connected
                      ? "检测到本地缓存，可先以缓存模式继续"
                      : (
                          <>
                            填写账户邮箱和密码，点击 <strong>测试连接</strong>
                            {connected ? " ✓" : ""}
                          </>
                        )}
              </span>
              <StepLabel step={2} currentStep={currentStep} />
              <span>
                本地无缓存时点击 <strong>开始首次同步</strong>
                ；已有缓存会直接使用，可稍后手动刷新
                {currentStep > 2 ? " ✓" : ""}
              </span>
              <StepLabel step={3} currentStep={currentStep} />
              <span>同步完成后，在下方点击 <strong>运行非提交验证</strong> 开始生产搜索</span>
              <StepLabel step={4} currentStep={currentStep} />
              <span>在侧边栏「候选发现」「评估与验证」「提交就绪」中继续后续流程</span>
            </div>
          </div>
          <button
            onClick={onDismiss}
            className="btn btn-ghost btn-sm flex-shrink-0"
            aria-label="关闭引导"
          >
            ✕
          </button>
        </div>
      </div>
    );
  }
  return (
    <div className="mb-4 text-right">
      <button
        type="button"
        className="text-xs text-text-tertiary hover:text-text-secondary underline cursor-pointer bg-transparent border-none p-0"
        onClick={onReshow}
        aria-label="重新显示首次使用引导"
      >
        ? 重新显示首次引导
      </button>
    </div>
  );
}

function StepLabel({ step, currentStep }: { step: number; currentStep: number }) {
  const className =
    currentStep === step
      ? "text-info-text font-medium text-right"
      : currentStep > step
        ? "text-positive-text font-medium text-right"
        : "text-text-disabled font-medium text-right";
  return <span className={className}>{step}.</span>;
}
