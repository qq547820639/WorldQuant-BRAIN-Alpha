/**
 * useErrorNotifications — surfaces globalData load failures as toasts with
 * actionable retry / reconnect / refresh buttons derived from ApiMeta.
 *
 * Side-effect-only hook: returns nothing.
 */

import { useRef, useCallback, useEffect } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import type { CardViewId, PhaseData } from '@/types';
import type { useGlobalData } from '@/hooks/useGlobalData';
import type { useApi } from '@/hooks/useApi';
import type { ApiMeta } from '@/hooks/useApi';
import { nextActionLabel, safeDisplayErrorMessage } from '@/helpers/errorExperience';
import type { NotifyFn } from './useBaseState';

export interface ErrorNotificationsOptions {
  globalData: ReturnType<typeof useGlobalData>;
  notify: NotifyFn;
  phaseApiCall: ReturnType<typeof useApi<PhaseData>>['call'];
  setActiveView: Dispatch<SetStateAction<CardViewId>>;
}

export function useErrorNotifications({
  globalData,
  notify,
  phaseApiCall,
  setActiveView,
}: ErrorNotificationsOptions): void {
  const lastCandidatesErrorRef = useRef<string>('');
  const lastSlotsErrorRef = useRef<string>('');
  const lastCloudErrorRef = useRef<string>('');
  const lastConfigErrorRef = useRef<string>('');

  const buildAction = useCallback(
    (meta: ApiMeta | null, retryFn: () => void) => {
      const nextAction = meta?.user_error?.next_action || meta?.next_action;
      const label = meta?.user_error?.action_label || nextActionLabel(nextAction);
      if (!nextAction || !label) return undefined;
      switch (nextAction) {
        case 'reconnect_session':
          return { label, onClick: () => setActiveView('dashboard') };
        case 'refresh_cache':
          return {
            label,
            onClick: () => {
              globalData.refreshAll();
              void phaseApiCall('/api/phase_state');
            },
          };
        case 'wait_and_retry':
          return {
            label,
            onClick: () => {
              notify('info', '5 秒后将自动重试…');
              setTimeout(() => retryFn(), 5000);
            },
          };
        case 'check_config':
          return { label, onClick: () => setActiveView('config') };
        default:
          return { label, onClick: () => retryFn() };
      }
    },
    [globalData, phaseApiCall, notify, setActiveView]
  );

  useEffect(() => {
    const gd = globalData;
    if (gd.candidates.error && gd.candidates.error !== lastCandidatesErrorRef.current) {
      lastCandidatesErrorRef.current = gd.candidates.error;
      notify(
        'warning',
        `候选数据加载失败: ${safeDisplayErrorMessage(gd.candidates.error)}`,
        buildAction(gd.candidates.lastErrorMeta, () => {
          gd.refreshAll();
        })
      );
    }
    if (gd.slots.error && gd.slots.error !== lastSlotsErrorRef.current) {
      lastSlotsErrorRef.current = gd.slots.error;
      notify(
        'warning',
        `回测槽位加载失败: ${safeDisplayErrorMessage(gd.slots.error)}`,
        buildAction(gd.slots.lastErrorMeta, () => {
          gd.refreshAll();
        })
      );
    }
    if (gd.cloud.error && gd.cloud.error !== lastCloudErrorRef.current) {
      lastCloudErrorRef.current = gd.cloud.error;
      notify(
        'warning',
        `云端快照加载失败: ${safeDisplayErrorMessage(gd.cloud.error)}`,
        buildAction(gd.cloud.lastErrorMeta, () => {
          gd.refreshAll();
        })
      );
    }
    if (gd.config.error && gd.config.error !== lastConfigErrorRef.current) {
      lastConfigErrorRef.current = gd.config.error;
      notify(
        'warning',
        `配置状态加载失败: ${safeDisplayErrorMessage(gd.config.error)}`,
        buildAction(gd.config.lastErrorMeta, () => {
          gd.refreshAll();
        })
      );
    }
  }, [globalData, notify, buildAction]);
}
