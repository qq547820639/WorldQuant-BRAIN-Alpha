import { useEffect, useState } from 'react';

interface SubmissionPanelProps {
  notify?: (type: 'info' | 'success' | 'warning' | 'error', message: string) => void;
}

interface BlockingReason {
  reason: string;
  count?: number;
}

/** 阻断原因枚举 → 中文可读文本 */
const REASON_LABELS: Record<string, string> = {
  missing_official_alpha_id: '缺少官方 Alpha ID',
  duplicate_alpha: '存在重复 Alpha',
  no_eligible_candidate: '无合格候选',
  official_api_unavailable: '官方接口不可用',
  session_invalid: '会话无效',
};

function labelFor(reason: string): string {
  return REASON_LABELS[reason] ?? reason;
}

/**
 * 只读的提交就绪状态包装组件。
 * 旧版提交面板已退役，不再提供提交按钮，仅展示当前提交就绪状态与阻断原因。
 */
export default function SubmissionPanel({ notify }: SubmissionPanelProps) {
  const [blockingReasons, setBlockingReasons] = useState<BlockingReason[]>([]);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/submit_readiness')
      .then((response) => response.json())
      .then((data) => {
        if (cancelled) return;
        if (data?.ok && Array.isArray(data.top_blocking_reasons)) {
          setBlockingReasons(data.top_blocking_reasons);
        }
      })
      .catch(() => {
        if (!cancelled && notify) {
          notify('error', '提交就绪状态加载失败');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [notify]);

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">旧提交面板已退役</h2>
        <p className="text-sm text-text-tertiary">
          提交功能已迁移至官方操作面板，此处仅展示当前就绪状态。
        </p>
      </div>
      {blockingReasons.length > 0 && (
        <div>
          <h3 className="text-sm font-medium">提交阻断原因</h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
            {blockingReasons.map((reason, index) => (
              <li key={index}>
                {labelFor(reason.reason)}
                {typeof reason.count === 'number' ? `（${reason.count}条）` : ''}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
