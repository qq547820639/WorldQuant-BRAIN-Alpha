/** Read-only pre-submit confirmation surface.
 *
 * P0-1: When submission is blocked, renders a structured "Next Steps Guidance"
 * panel with actionable exit paths instead of a dead-end error message.
 * Each blocking reason maps to a specific action (navigate, external link, etc.).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiErrorMessage } from '@/helpers/errorExperience';
import { useApi } from '@/hooks/useApi';
import { useGlobalData } from '@/hooks/useGlobalData';
import type { Candidate, SubmitReadinessResponse } from '@/types';
import { isRecord } from '@/types';
import ProgressFeedback from '@/components/ProgressFeedback';
import StatusFlowDiagram from '@/components/StatusFlowDiagram';
import {
  ConfirmationTable,
  buildRows,
  formatCount,
  type CheckResult,
} from '@/components/SubmissionChecklist';
import { ReadinessSummary } from '@/components/SubmissionGates';
import { DrillModal } from '@/components/SubmissionGuidance';

interface Props {
  notify: (type: 'success' | 'error' | 'warning' | 'info', msg: string) => void;
  onNavigate?: (view: string) => void;
}

export default function SubmissionConfirmPanel({ notify, onNavigate }: Props) {
  const { candidates: globalCandidates, refreshAll } = useGlobalData();
  const checksApi = useApi<{ items?: CheckResult[] }>();
  const readinessApi = useApi<SubmitReadinessResponse>();
  const callChecks = checksApi.call;
  const callReadiness = readinessApi.call;

  const load = useCallback(async () => {
    refreshAll();
    const [checksResult, readinessResult] = await Promise.all([
      callChecks<{ items?: CheckResult[] }>('/api/check_results'),
      callReadiness<SubmitReadinessResponse>('/api/submit_readiness'),
    ]);
    if (checksResult?.error) notify('error', apiErrorMessage(checksResult, '检查结果加载失败'));
    if (readinessResult?.error)
      notify('error', apiErrorMessage(readinessResult, '提交阻断复核加载失败'));
  }, [callChecks, callReadiness, notify, refreshAll]);

  useEffect(() => {
    void load();
  }, [load]);

  const prevRealSubmitRef = useRef<boolean | undefined>(undefined);
  const readiness = readinessApi.data;
  const readyToSubmit = readiness?.ready_to_submit;

  useEffect(() => {
    if (!readyToSubmit) return;
    if (prevRealSubmitRef.current === undefined) {
      prevRealSubmitRef.current = readiness?.real_submit_performed ?? false;
    }
    const POLL_INTERVAL_MS = 30_000;
    let timer: ReturnType<typeof setInterval> | null = null;

    const poll = async () => {
      try {
        const res = await fetch('/api/submit_readiness');
        if (!res.ok) return;
        const json: unknown = await res.json();
        if (!json || typeof json !== 'object') return;
        const data = isRecord(json) ? json : {};
        const currentPerformed = Boolean(data.real_submit_performed);
        if (currentPerformed && prevRealSubmitRef.current === false) {
          prevRealSubmitRef.current = true;
          notify('success', '检测到真实提交已完成！正在自动刷新数据。');
          await load();
        } else {
          prevRealSubmitRef.current = currentPerformed;
        }
      } catch {
        console.warn('SubmissionConfirm: polling failed, will retry');
      }
    };

    timer = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      if (timer !== null) clearInterval(timer);
    };
  }, [readyToSubmit, readiness?.real_submit_performed, load, notify]);

  const candidates = globalCandidates.data?.candidates || globalCandidates.data?.items || [];
  const checks = checksApi.data?.items || [];
  const rows = useMemo(() => buildRows(candidates, checks), [candidates, checks]);

  const [drillOpen, setDrillOpen] = useState(false);
  const drillSteps = useMemo(
    () => [
      {
        id: 1,
        label: '确认候选 ID',
        description: '确认要提交的 Alpha ID 无误，并与 BRAIN 平台一致',
      },
      {
        id: 2,
        label: '打开 BRAIN 平台',
        description: '在浏览器中打开 platform.worldquantbrain.com/alphas',
      },
      {
        id: 3,
        label: '粘贴表达式',
        description: '将候选表达式复制粘贴到 BRAIN 平台的 Alpha 编辑器中',
      },
      { id: 4, label: '设置参数', description: '配置区域、股票池、延迟、中性化等参数与本地一致' },
      {
        id: 5,
        label: '确认提交',
        description: '在 BRAIN 平台上点击提交按钮完成真实 Alpha 提交流程',
      },
    ],
    []
  );
  const [drillChecks, setDrillChecks] = useState<Set<number>>(new Set());
  const drilledAllChecked = drillChecks.size === drillSteps.length;
  const readyRows = rows.filter((row) => row.status === 'READY');
  const blockedRows = rows.filter((row) => row.status !== 'READY');
  const readyCount = readiness?.eligible_count ?? readyRows.length;
  const readinessCandidateCount =
    readiness?.job_family_candidate_count ?? readiness?.candidate_count ?? rows.length;
  const blockedCount = readiness
    ? Math.max(0, readinessCandidateCount - readyCount)
    : blockedRows.length;
  const loading =
    (globalCandidates.loading || checksApi.loading || readinessApi.loading) &&
    !globalCandidates.data &&
    !checksApi.data &&
    !readinessApi.data;
  const error = globalCandidates.error || checksApi.error || readinessApi.error;

  const flowStages = useMemo(() => {
    const checked = new Set(
      checks
        .filter((c) => c.passed || c.submittable)
        .map((c) => c.alpha_id || c.official_alpha_id || c.simulation_id || JSON.stringify(c))
    ).size;
    const ready = readyCount;
    return [
      {
        label: '批量检查',
        count: checked,
        status: checked > 0 ? ('complete' as const) : ('active' as const),
      },
      {
        label: '阻断复核',
        count: ready,
        status:
          ready > 0
            ? ('complete' as const)
            : checked > 0
              ? ('active' as const)
              : ('pending' as const),
      },
      {
        label: '可提交',
        count: readiness?.ready_to_submit ? ready : 0,
        status: readiness?.ready_to_submit
          ? ('complete' as const)
          : blockedCount > 0
            ? ('blocked' as const)
            : ('pending' as const),
      },
    ];
  }, [checks, readyCount, blockedCount, readiness?.ready_to_submit]);

  if (loading) {
    return (
      <ProgressFeedback
        state="loading"
        title="提交前阻断复核"
        progress={{ phase: 'submission_confirm_load', status_message: '正在加载提交前检查记录。' }}
      />
    );
  }

  return (
    <div className="min-w-0 space-y-5 animate-fade-in">
      <div className="flex flex-col gap-1">
        <h2 className="text-base font-semibold text-text-primary">提交前阻断复核</h2>
        <p className="text-xs text-text-tertiary" role="status" aria-live="polite">
          复核候选 {readyCount} · 阻断 {blockedCount}
        </p>
      </div>

      {error && (
        <div
          className="rounded-md border border-[var(--color-error-border)] bg-[var(--color-error-bg)] p-4"
          role="alert"
          aria-live="assertive"
        >
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm text-negative">提交前阻断复核数据加载失败: {error}</p>
            <button type="button" onClick={load} className="btn btn-secondary text-sm">
              重试
            </button>
          </div>
        </div>
      )}

      <StatusFlowDiagram stages={flowStages} />

      <ReadinessSummary
        readiness={readiness}
        onNavigate={onNavigate}
        onDrillOpen={() => {
          setDrillOpen(true);
          setDrillChecks(new Set());
        }}
      />

      <ConfirmationTable title="预检查通过" empty="暂无通过预提交检查的 Alpha" rows={readyRows} />

      <ConfirmationTable title="阻断与待处理" empty="暂无阻断记录" rows={blockedRows} />

      {drillOpen && (
        <DrillModal
          steps={drillSteps}
          checks={drillChecks}
          onToggle={(id) => {
            setDrillChecks((prev) => {
              const next = new Set(prev);
              if (next.has(id)) {
                next.delete(id);
              } else {
                next.add(id);
              }
              return next;
            });
          }}
          allChecked={drilledAllChecked}
          onClose={() => setDrillOpen(false)}
        />
      )}
    </div>
  );
}
