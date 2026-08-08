import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiErrorMessage } from '@/helpers/errorExperience';
import type { AlphaLifecycleHistoryResponse, Candidate } from '@/types';
import {
  candidateIdentity,
  candidateStatus,
  candidateCreatedAt,
  candidateText,
  candidateQualitySearchText,
  candidateNeedsOptimization,
  candidateRetainedPoolEligible,
  indexCheckResults,
  lifecycleTracesForCandidates,
  rankPoolCandidates,
  candidatePoolSnapshot,
  workflowCandidatesForQueue,
  candidateMatchesQueueView,
  summarizeCandidateQuality,
  CandidateCheckResult,
  CandidateQueueView,
  CandidatePoolSnapshot,
  CandidateWorkflowPlan,
  CandidateListMeta,
} from '@/components/CandidateTableUtils';
import { getStarred } from '@/utils';
import type { SortKey } from './useCandidateTableState';
import { PAGE_SIZE } from './useCandidateTableState';

type LoadedCandidateState = {
  rows: Candidate[];
  mainPoolCandidates: Candidate[] | null;
  snapshot: CandidatePoolSnapshot;
  workflowPlan?: CandidateWorkflowPlan | null;
};

interface UseCandidateTableDataOptions {
  globalCandidatesData: {
    candidates?: Candidate[];
    items?: Candidate[];
    main_pool_candidates?: Candidate[];
    workflow_plan?: Record<string, unknown> | null;
    candidate_workflow?: Record<string, unknown> | null;
    total?: number;
    returned_count?: number;
    total_count?: number;
  } | null;
  refreshAll: () => void;
  callCheckResultsApi: <T = { items?: CandidateCheckResult[] }>(
    url: string,
    options?: RequestInit
  ) => Promise<(T & { ok?: boolean; error?: string }) | null>;
  callLifecycleApi: <T = AlphaLifecycleHistoryResponse>(
    url: string,
    options?: RequestInit
  ) => Promise<(T & { ok?: boolean; error?: string }) | null>;
  notify: (type: 'success' | 'error' | 'warning' | 'info', msg: string) => void;
  viewMode: CandidateQueueView;
  targetPoolSize: number;
  filter: string;
  showStarredOnly: boolean;
  sortKey: SortKey;
  sortAsc: boolean;
  currentPage: number;
  lifecycleLoading: boolean;
}

export function useCandidateTableData(options: UseCandidateTableDataOptions) {
  const {
    globalCandidatesData,
    refreshAll,
    callCheckResultsApi,
    callLifecycleApi,
    notify,
    viewMode,
    targetPoolSize,
    filter,
    showStarredOnly,
    sortKey,
    sortAsc,
    currentPage,
  } = options;

  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [serverMainPoolCandidates, setServerMainPoolCandidates] = useState<Candidate[] | null>(
    null
  );
  const [serverWorkflowPlan, setServerWorkflowPlan] = useState<CandidateWorkflowPlan | null>(null);
  const [candidateMeta, setCandidateMeta] = useState<CandidateListMeta>({ returned: 0, total: 0 });
  const [checkResults, setCheckResults] = useState<Map<string, CandidateCheckResult>>(new Map());
  const [lifecycleHistory, setLifecycleHistory] = useState<AlphaLifecycleHistoryResponse | null>(
    null
  );
  const [lifecycleError, setLifecycleError] = useState<string | null>(null);

  const lastPoolDeficitWarningRef = useRef<number>(0);
  const POOL_DEFICIT_WARNING_COOLDOWN_MS = 30 * 60 * 1000;

  // Keep the latest snapshot of global candidates in a ref so loadCandidates
  // does NOT depend on globalCandidatesData identity. globalCandidatesData is a
  // fresh object reference after every refreshAll() fetch, which previously
  // re-created loadCandidates → re-ran the load effect → refreshAll() → loop.
  const globalCandidatesDataRef = useRef(globalCandidatesData);
  useEffect(() => {
    globalCandidatesDataRef.current = globalCandidatesData;
  }, [globalCandidatesData]);

  const processCandidatesData = useCallback(
    (result: typeof globalCandidatesData): LoadedCandidateState | null => {
      if (!result) return null;
      const nextRows = result.candidates || result.items || [];
      const nextMainPool = Array.isArray(result.main_pool_candidates)
        ? result.main_pool_candidates
        : null;
      const nextWorkflowPlan = (result.workflow_plan ||
        result.candidate_workflow ||
        null) as CandidateWorkflowPlan | null;
      setCandidates(nextRows);
      setServerMainPoolCandidates(nextMainPool);
      setServerWorkflowPlan(nextWorkflowPlan);
      setCandidateMeta({
        returned: Number(result.returned_count ?? nextRows.length),
        total: Number(result.total ?? result.total_count ?? nextRows.length),
      });
      const snapshot = candidatePoolSnapshot(
        nextRows,
        nextMainPool,
        targetPoolSize,
        nextWorkflowPlan
      );
      const eligibleCount = snapshot.eligibleCount;
      if (eligibleCount < targetPoolSize) {
        const now = Date.now();
        if (now - lastPoolDeficitWarningRef.current >= POOL_DEFICIT_WARNING_COOLDOWN_MS) {
          lastPoolDeficitWarningRef.current = now;
          notify(
            'warning',
            `候选池不足: 当前合格候选 ${eligibleCount}，目标池容量 ${targetPoolSize}，建议启动候选池自动推进补充候选。`
          );
        }
      }
      return {
        rows: nextRows,
        mainPoolCandidates: nextMainPool,
        workflowPlan: nextWorkflowPlan,
        snapshot,
      };
    },
    [notify, targetPoolSize]
  );

  useEffect(() => {
    if (globalCandidatesData) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- 外部候选数据变化后同步处理并落库本地行/池状态
      processCandidatesData(globalCandidatesData);
    }
  }, [globalCandidatesData, processCandidatesData]);

  const loadCandidates = useCallback(async (): Promise<LoadedCandidateState | null> => {
    refreshAll();
    const loaded = processCandidatesData(globalCandidatesDataRef.current);
    const [checkResultsResult, lifecycleResult] = await Promise.all([
      callCheckResultsApi<{ items?: CandidateCheckResult[] }>('/api/check_results'),
      callLifecycleApi<AlphaLifecycleHistoryResponse>('/api/alpha_lifecycle?limit=250'),
    ]);
    if (checkResultsResult?.ok) {
      setCheckResults(indexCheckResults(checkResultsResult.items || []));
    } else if (checkResultsResult?.error) {
      notify('error', apiErrorMessage(checkResultsResult, '检查结果加载失败'));
    }
    if (lifecycleResult?.ok) {
      setLifecycleHistory(lifecycleResult);
      setLifecycleError(null);
    } else if (lifecycleResult) {
      setLifecycleError(apiErrorMessage(lifecycleResult, '生命周期历史加载失败'));
    } else {
      setLifecycleError('生命周期历史加载失败');
    }
    return loaded;
  }, [refreshAll, processCandidatesData, callCheckResultsApi, callLifecycleApi, notify]);

  const refreshCheckResults = useCallback(async () => {
    if (viewMode !== 'submittable') return;
    const result = await callCheckResultsApi<{ items?: CandidateCheckResult[] }>(
      '/api/check_results'
    );
    if (result?.ok) {
      setCheckResults(indexCheckResults(result.items || []));
    } else if (result?.error) {
      notify('error', apiErrorMessage(result, '检查结果加载失败'));
    }
  }, [callCheckResultsApi, notify, viewMode]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 依赖变化后加载候选数据（数据获取副作用，setState 在异步回调内）
    void loadCandidates();
  }, [loadCandidates]);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 视图模式变化后刷新检查结果（数据获取副作用，setState 在异步回调内）
    void refreshCheckResults();
  }, [refreshCheckResults]);

  const poolEligibleCandidates = useMemo(
    () =>
      serverMainPoolCandidates
        ? rankPoolCandidates(serverMainPoolCandidates)
        : rankPoolCandidates(candidates.filter(candidateRetainedPoolEligible)),
    [candidates, serverMainPoolCandidates]
  );

  const retainedPoolCandidates = useMemo(
    () => poolEligibleCandidates.slice(0, targetPoolSize),
    [poolEligibleCandidates, targetPoolSize]
  );

  const rawQueueCandidates = useMemo(
    () => candidates.filter((c) => candidateMatchesQueueView(c, viewMode, checkResults)),
    [candidates, checkResults, viewMode]
  );

  const displayQueueCandidates = useMemo(
    () =>
      viewMode === 'candidates'
        ? candidateManagementDisplayCandidates(
            candidates,
            retainedPoolCandidates,
            serverWorkflowPlan
          )
        : rawQueueCandidates,
    [candidates, rawQueueCandidates, retainedPoolCandidates, serverWorkflowPlan, viewMode]
  );

  const visibleLifecycleTraces = useMemo(
    () =>
      lifecycleTracesForCandidates(
        lifecycleHistory?.alpha_traces || [],
        displayQueueCandidates,
        filter
      ),
    [displayQueueCandidates, filter, lifecycleHistory]
  );

  const sortedCandidates = useMemo(() => {
    const normalizedFilter = filter.trim().toLowerCase();
    const filtered = normalizedFilter
      ? displayQueueCandidates.filter(
          (c) =>
            candidateText(c.expression).toLowerCase().includes(normalizedFilter) ||
            candidateText(c.family).toLowerCase().includes(normalizedFilter) ||
            candidateIdentity(c).toLowerCase().includes(normalizedFilter) ||
            candidateQualitySearchText(c).toLowerCase().includes(normalizedFilter)
        )
      : displayQueueCandidates;
    const starFiltered = showStarredOnly
      ? filtered.filter((c) => getStarred().has(candidateIdentity(c)))
      : filtered;
    return [...starFiltered].sort((a, b) => {
      let va: number;
      let vb: number;
      switch (sortKey) {
        case 'score':
          va = a.scorecard?.total_score ?? 0;
          vb = b.scorecard?.total_score ?? 0;
          break;
        case 'status':
          return candidateStatus(a).localeCompare(candidateStatus(b)) * (sortAsc ? 1 : -1);
        case 'created':
          va = candidateCreatedAt(a);
          vb = candidateCreatedAt(b);
          break;
        default:
          return 0;
      }
      return sortAsc ? va - vb : vb - va;
    });
  }, [displayQueueCandidates, filter, sortAsc, sortKey, showStarredOnly]);

  const summaryCandidates = displayQueueCandidates;
  const qualitySummary = useMemo(
    () =>
      summarizeCandidateQuality(summaryCandidates, retainedPoolCandidates.length, targetPoolSize),
    [summaryCandidates, retainedPoolCandidates.length, targetPoolSize]
  );

  const totalPages = Math.max(1, Math.ceil(sortedCandidates.length / PAGE_SIZE));

  const paginatedCandidates = useMemo(() => {
    const startIndex = (currentPage - 1) * PAGE_SIZE;
    return sortedCandidates.slice(startIndex, startIndex + PAGE_SIZE);
  }, [currentPage, sortedCandidates]);

  const currentPageIds = useMemo(
    () => paginatedCandidates.map((c) => candidateIdentity(c)),
    [paginatedCandidates]
  );

  const remoteTruncated = candidateMeta.total > candidateMeta.returned;

  return {
    candidates,
    setCandidates,
    serverMainPoolCandidates,
    serverWorkflowPlan,
    candidateMeta,
    checkResults,
    lifecycleHistory,
    lifecycleError,
    poolEligibleCandidates,
    retainedPoolCandidates,
    rawQueueCandidates,
    displayQueueCandidates,
    visibleLifecycleTraces,
    sortedCandidates,
    qualitySummary,
    totalPages,
    paginatedCandidates,
    currentPageIds,
    remoteTruncated,
    loadCandidates,
    refreshCheckResults,
  };
}

function candidateManagementDisplayCandidates(
  rows: Candidate[],
  retainedCandidates: Candidate[],
  workflowPlan?: CandidateWorkflowPlan | null
) {
  const queued = [
    ...workflowCandidatesForQueue(
      rows,
      [],
      workflowPlan?.validator?.next_candidate_ids || workflowPlan?.validator?.candidate_ids
    ),
    ...workflowCandidatesForQueue(rows, [], workflowPlan?.rework?.candidate_ids),
    ...workflowCandidatesForQueue(rows, [], workflowPlan?.review?.candidate_ids),
    ...rows.filter(candidateNeedsOptimization),
  ];
  return rankPoolCandidates(uniqueCandidatesByIdentity([...retainedCandidates, ...queued]));
}

function uniqueCandidatesByIdentity(candidates: Candidate[]) {
  const seen = new Set<string>();
  const selected: Candidate[] = [];
  for (const candidate of candidates) {
    const id = candidateIdentity(candidate) || candidate.expression || '';
    if (!id || seen.has(id)) continue;
    seen.add(id);
    selected.push(candidate);
  }
  return selected;
}
