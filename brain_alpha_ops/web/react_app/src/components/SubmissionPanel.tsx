/** Retired submit surface kept as a compatibility alias for read-only review. */

import { memo } from 'react';
import SubmissionConfirmPanel from '@/components/SubmissionConfirmPanel';

interface Props {
  notify: (
    type: 'success' | 'error' | 'warning' | 'info',
    msg: string,
    action?: { label: string; onClick: () => void }
  ) => void;
  onNavigate?: (view: string) => void;
}

export default memo(function SubmissionPanel({ notify, onNavigate }: Props) {
  return (
    <div className="w-full max-w-3xl min-w-0 space-y-6 animate-fade-in">
      <div
        className="min-w-0 outline-none focus:ring-2 focus:ring-brand-500/50 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"
        role="status"
        aria-live="polite"
      >
        旧提交面板已退役。Web 页面不执行真实提交；任何真实提交需另走人工审批。
      </div>
      <SubmissionConfirmPanel notify={notify} onNavigate={onNavigate} />
    </div>
  );
});
