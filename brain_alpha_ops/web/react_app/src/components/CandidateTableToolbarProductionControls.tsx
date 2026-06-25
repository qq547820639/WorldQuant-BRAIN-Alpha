import {
  MIN_TARGET_POOL_SIZE,
  MAX_TARGET_POOL_SIZE,
} from "./CandidateTableUtils";

export interface ProductionControlsProps {
  targetPoolSize: number;
  candidateWorkflowBusy: boolean;
  taskState: "idle" | "loading" | "progress" | "success" | "error";
  simState: "idle" | "loading" | "progress" | "success" | "error";
  optimizationState: "idle" | "loading" | "progress" | "success" | "error";
  onTargetPoolSizeChange: (value: string) => void;
  onGenerateCandidates: () => void;
  onStartValidationQueue: () => void;
  onStartOptimization: () => void;
}

export function ProductionControls({
  targetPoolSize,
  candidateWorkflowBusy,
  taskState,
  simState,
  optimizationState,
  onTargetPoolSizeChange,
  onGenerateCandidates,
  onStartValidationQueue,
  onStartOptimization,
}: ProductionControlsProps) {
  return (
    <div className="flex flex-wrap items-center gap-3 mb-4">
      <label className="flex items-center gap-2 text-sm font-medium text-text-secondary">
        目标池容量
        <input
          type="number"
          min={MIN_TARGET_POOL_SIZE}
          max={MAX_TARGET_POOL_SIZE}
          value={targetPoolSize}
          disabled={candidateWorkflowBusy}
          onChange={(event) => onTargetPoolSizeChange(event.target.value)}
          className="form-input w-20"
        />
      </label>
      <button
        type="button"
        onClick={onGenerateCandidates}
        disabled={candidateWorkflowBusy}
        aria-busy={taskState === "loading" || taskState === "progress"}
        className="btn btn-primary btn-sm"
        title="自动维护目标池容量，并在非提交边界内继续官方模拟与质量检查"
      >
        {taskState === "loading" || taskState === "progress" ? "推进中..." : "自动推进候选池"}
      </button>
      <button
        type="button"
        onClick={onStartValidationQueue}
        disabled={candidateWorkflowBusy}
        aria-busy={simState === "loading" || simState === "progress"}
        className="btn btn-secondary btn-sm"
        title="自动推进中断或单批证据缺失时使用；按 Top3 进入官方模拟后自动接质量门槛检查，不执行真实 Alpha submit"
      >
        {simState === "loading" || simState === "progress" ? "模拟中..." : "运行官方验证队列"}
      </button>
      <button
        type="button"
        onClick={onStartOptimization}
        disabled={candidateWorkflowBusy}
        aria-busy={optimizationState === "loading" || optimizationState === "progress"}
        className="btn btn-secondary btn-sm"
        title="根据服务端返工队列进行本地优化；不会携带凭据，也不会提交 Alpha"
      >
        {optimizationState === "loading" || optimizationState === "progress" ? "优化中..." : "优化返工队列"}
      </button>
    </div>
  );
}
