/**
 * 状态卡着陆页 - 核心导航入口
 *
 * 设计原则：
 * 1. 简洁直观的卡片设计
 * 2. 核心指标突出显示
 * 3. 操作引导清晰
 * 4. 统一中文界面
 */

import { useCallback, useEffect, useMemo, memo } from 'react';
import { useApi } from '@/hooks/useApi';
import { useGlobalData } from '@/hooks/useGlobalData';
import type { CardViewId } from '@/types';
import ProgressFeedback from '@/components/ProgressFeedback';
import { CARD_CONFIGS } from './cardConfigs';
import StateCardItem from './StateCardItem';
import {
  buildStateCardsMetrics,
  type CheckpointStatusSummary,
  type StateCardsMetrics,
} from './metrics';
import { labeledError } from './helpers';

interface Props {
  onNavigate: (view: CardViewId) => void;
  notify: (type: 'success' | 'error' | 'warning' | 'info', msg: string) => void;
}

function StateCards({ onNavigate, notify }: Props) {
  const {
    candidates: candidatesGlobal,
    slots: slotsGlobal,
    config: configGlobal,
    cloud: cloudGlobal,
    refreshAll,
  } = useGlobalData();
  const checkpointApi = useApi<CheckpointStatusSummary>();

  const loadStateSnapshots = useCallback(() => {
    refreshAll();
    void checkpointApi.call('/api/checkpoint_status');
  }, [refreshAll, checkpointApi.call]);

  // 加载数据
  useEffect(() => {
    loadStateSnapshots();
  }, [loadStateSnapshots]);

  // 错误处理
  const stateErrors = useMemo(
    () =>
      [
        labeledError('候选', candidatesGlobal.error),
        labeledError('回测', slotsGlobal.error),
        labeledError('配置', configGlobal.error),
        labeledError('历史', checkpointApi.error),
        labeledError('云端', cloudGlobal.error),
      ].filter(Boolean),
    [
      candidatesGlobal.error,
      slotsGlobal.error,
      configGlobal.error,
      checkpointApi.error,
      cloudGlobal.error,
    ]
  );

  useEffect(() => {
    if (stateErrors.length) notify('warning', `状态快照加载不完整: ${stateErrors.join('；')}`);
  }, [notify, stateErrors]);

  // 计算核心指标
  const candidates = candidatesGlobal.data?.candidates || candidatesGlobal.data?.items || [];
  const metrics: StateCardsMetrics = useMemo(
    () =>
      buildStateCardsMetrics({
        candidatesData: candidatesGlobal.data,
        slotsData: slotsGlobal.data,
        configData: configGlobal.data,
        cloudData: cloudGlobal.data,
        checkpointData: checkpointApi.data,
      }),
    [
      candidates,
      candidatesGlobal.data?.ready_count,
      candidatesGlobal.data?.total,
      configGlobal.data,
      checkpointApi.data,
      cloudGlobal.data,
      slotsGlobal.data,
    ]
  );

  // 加载状态
  const loading = [candidatesGlobal, slotsGlobal, configGlobal, checkpointApi, cloudGlobal].some(
    (api) => api.loading && !api.data
  );
  const loadError = stateErrors.length ? stateErrors.join('；') : '';

  return (
    <div className="w-full min-w-0 max-w-full animate-fade-in">
      {/* 加载状态 */}
      {loading && (
        <div className="mb-8 w-full max-w-full overflow-hidden">
          <ProgressFeedback
            state="loading"
            title="状态卡"
            progress={{ phase: 'state_cards_load', status_message: '正在加载本地状态快照。' }}
          />
        </div>
      )}

      {/* 错误提示 */}
      {loadError && !loading && (
        <div
          className="mb-8 p-4 rounded-xl border border-danger/30 bg-danger/5"
          role="alert"
          aria-live="assertive"
        >
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex min-w-0 items-start gap-3">
              <span className="text-danger" aria-hidden="true">
                ⚠
              </span>
              <div className="min-w-0">
                <p className="text-sm font-medium text-danger">状态快照加载不完整</p>
                <p className="mt-1 break-words text-sm text-danger/90">{loadError}</p>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={loadStateSnapshots}
                className="btn-secondary min-h-11 text-sm"
              >
                重试全部
              </button>
              <button
                type="button"
                onClick={() => onNavigate('config')}
                className="btn-ghost min-h-11 text-sm"
              >
                检查配置
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 状态卡网格 */}
      <div className="grid w-full max-w-full grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5">
        {CARD_CONFIGS.map((config) => (
          <StateCardItem
            key={config.id}
            config={config}
            metrics={metrics}
            onNavigate={onNavigate}
          />
        ))}
      </div>

      {/* 流程说明 */}
      <div className="mt-8 max-w-full rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex items-center gap-3">
          <span className="h-2 w-2 rounded-full bg-brand-600" aria-hidden="true" />
          <p className="text-sm text-slate-600">
            点击状态卡进入对应功能模块，完成从候选生成到提交前阻断复核的可视化管理；真实提交保持关闭
          </p>
        </div>
      </div>
    </div>
  );
}

export default memo(StateCards);
