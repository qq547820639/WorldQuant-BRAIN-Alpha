import type { TaskSuccessBanner } from '@/hooks/useCandidatePipeline';

interface Props {
  banner: TaskSuccessBanner;
  retainedCount: number;
  targetPoolSize: number;
  onClose: () => void;
}

export default function CandidateTableSuccessBanner({
  banner,
  retainedCount,
  targetPoolSize,
  onClose,
}: Props) {
  return (
    <div
      className="panel-body-padded"
      style={{
        borderBottom: '0.5px solid var(--color-border-default)',
        background: 'var(--color-task-success-bg)',
        borderLeft: '3px solid var(--color-sparkline-dot)',
        margin: 0,
      }}
      role="status"
      aria-live="polite"
    >
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '4px 16px' }}>
        <span style={{ fontSize: 14, marginRight: 4 }}>✅</span>
        <span className="text-sm font-medium text-text-primary">候选池自动推进完成</span>
        <span className="text-xs text-text-secondary">
          新增 <span className="font-mono-value text-positive">{banner.newCount}</span> 个候选
        </span>
        {banner.optimizedCount > 0 && (
          <span className="text-xs text-text-secondary">
            优化 <span className="font-mono-value text-accent">{banner.optimizedCount}</span> 个
          </span>
        )}
        <span className="text-xs text-text-tertiary">
          当前池状态：
          <span className="font-mono-value text-text-primary">
            {retainedCount}/{targetPoolSize}
          </span>
        </span>
      </div>
      <button
        type="button"
        className="btn btn-ghost btn-sm"
        style={{ marginTop: 6 }}
        onClick={onClose}
        aria-label="关闭成功提示"
      >
        关闭提示
      </button>
    </div>
  );
}
