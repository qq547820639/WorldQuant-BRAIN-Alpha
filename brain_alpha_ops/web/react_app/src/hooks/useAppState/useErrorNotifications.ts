/**
 * useErrorNotifications — surfaces globalData load failures as toasts with
 * actionable retry / reconnect / refresh buttons derived from ApiMeta.
 *
 * Workstream E3: when the backend attaches an ``actionable`` payload
 * (cause / impact_scope / suggested_action / recovery_action_id), the
 * toast uses that structured info instead of the raw error string, and
 * the recovery button is built from recovery_action_id so it routes to
 * the correct CardViewId (config / candidates / dashboard /
 * official_backtests) or triggers a non-navigation side effect
 * (refresh_cache, wait_and_retry, restart_flow).
 *
 * The hook also surfaces the latest actionable payload via the optional
 * ``onActionableError`` callback so the parent can render
 * ``<ActionableError payload={...} />`` at the page level.
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
import {
  isActionableErrorPayload,
  recoveryActionLabel,
  type ActionableErrorPayload,
} from '@/types/errors';
import type { NotifyFn } from './useBaseState';

export interface ErrorNotificationsOptions {
  globalData: ReturnType<typeof useGlobalData>;
  notify: NotifyFn;
  phaseApiCall: ReturnType<typeof useApi<PhaseData>>['call'];
  setActiveView: Dispatch<SetStateAction<CardViewId>>;
  /**
   * Optional: invoked when an error response carries an actionable
   * payload.  Parent can render ``<ActionableError payload={...} />``.
   * Pass ``null`` to clear the page-level error when no actionable
   * error is currently active.
   */
  onActionableError?: (payload: ActionableErrorPayload | null) => void;
}

interface ToastAction {
  label: string;
  onClick: () => void;
}

/**
 * Build a toast action from a recovery_action_id (E3 actionable payload)
 * or fall back to the legacy next_action field.  Returns ``undefined``
 * when no actionable next step is available.
 */
function buildRecoveryAction(
  recoveryActionId: string | undefined,
  nextAction: string | undefined,
  label: string | undefined,
  ctx: {
    setActiveView: Dispatch<SetStateAction<CardViewId>>;
    globalData: ReturnType<typeof useGlobalData>;
    phaseApiCall: ReturnType<typeof useApi<PhaseData>>['call'];
    notify: NotifyFn;
    retryFn: () => void;
  }
): ToastAction | undefined {
  // E3: prefer recovery_action_id from the actionable payload.
  const actionId = recoveryActionId || nextAction;
  const actionLabel =
    label ||
    (recoveryActionId ? recoveryActionLabel(recoveryActionId) : null) ||
    nextActionLabel(nextAction);
  if (!actionId || !actionLabel) return undefined;

  switch (actionId) {
    case 'reconnect_session':
      return { label: actionLabel, onClick: () => ctx.setActiveView('dashboard') };
    case 'refresh_cache':
      return {
        label: actionLabel,
        onClick: () => {
          ctx.globalData.refreshAll();
          void ctx.phaseApiCall('/api/phase_state');
        },
      };
    case 'wait_and_retry':
      return {
        label: actionLabel,
        onClick: () => {
          ctx.notify('info', '5 秒后将自动重试…');
          setTimeout(() => ctx.retryFn(), 5000);
        },
      };
    case 'check_config':
      return { label: actionLabel, onClick: () => ctx.setActiveView('config') };
    case 'review_official_slots':
      return { label: actionLabel, onClick: () => ctx.setActiveView('official_backtests') };
    case 'fix_expression':
      return { label: actionLabel, onClick: () => ctx.setActiveView('candidates') };
    case 'resume_or_restart':
    case 'restart_flow':
      return { label: actionLabel, onClick: () => ctx.setActiveView('dashboard') };
    default:
      return { label: actionLabel, onClick: () => ctx.retryFn() };
  }
}

export function useErrorNotifications({
  globalData,
  notify,
  phaseApiCall,
  setActiveView,
  onActionableError,
}: ErrorNotificationsOptions): void {
  const lastCandidatesErrorRef = useRef<string>('');
  const lastSlotsErrorRef = useRef<string>('');
  const lastCloudErrorRef = useRef<string>('');
  const lastConfigErrorRef = useRef<string>('');

  const buildAction = useCallback(
    (meta: ApiMeta | null, retryFn: () => void): ToastAction | undefined => {
      const actionable = meta?.actionable;
      const recoveryActionId = actionable?.recovery_action_id;
      const nextAction = meta?.user_error?.next_action || meta?.next_action;
      const label = meta?.user_error?.action_label;
      return buildRecoveryAction(recoveryActionId, nextAction, label, {
        setActiveView,
        globalData,
        phaseApiCall,
        notify,
        retryFn,
      });
    },
    [globalData, phaseApiCall, notify, setActiveView]
  );

  /**
   * Build the toast message for an error.  When the backend attached
   * an actionable payload, prefer its cause (more user-friendly than
   * the raw error string); otherwise fall back to safeDisplayErrorMessage.
   */
  const buildToastMessage = useCallback(
    (prefix: string, rawError: string, meta: ApiMeta | null): string => {
      const actionable = meta?.actionable;
      if (actionable && isActionableErrorPayload(actionable) && actionable.cause) {
        return `${prefix}: ${actionable.cause}`;
      }
      return `${prefix}: ${safeDisplayErrorMessage(rawError)}`;
    },
    []
  );

  // Surface the actionable payload to the parent for page-level rendering.
  const surfaceActionable = useCallback(
    (meta: ApiMeta | null) => {
      if (!onActionableError) return;
      const actionable = meta?.actionable;
      if (actionable && isActionableErrorPayload(actionable)) {
        onActionableError(actionable);
      }
    },
    [onActionableError]
  );

  useEffect(() => {
    const gd = globalData;
    if (gd.candidates.error && gd.candidates.error !== lastCandidatesErrorRef.current) {
      lastCandidatesErrorRef.current = gd.candidates.error;
      surfaceActionable(gd.candidates.lastErrorMeta);
      notify(
        'warning',
        buildToastMessage('候选数据加载失败', gd.candidates.error, gd.candidates.lastErrorMeta),
        buildAction(gd.candidates.lastErrorMeta, () => {
          gd.refreshAll();
        })
      );
    }
    if (gd.slots.error && gd.slots.error !== lastSlotsErrorRef.current) {
      lastSlotsErrorRef.current = gd.slots.error;
      surfaceActionable(gd.slots.lastErrorMeta);
      notify(
        'warning',
        buildToastMessage('回测槽位加载失败', gd.slots.error, gd.slots.lastErrorMeta),
        buildAction(gd.slots.lastErrorMeta, () => {
          gd.refreshAll();
        })
      );
    }
    if (gd.cloud.error && gd.cloud.error !== lastCloudErrorRef.current) {
      lastCloudErrorRef.current = gd.cloud.error;
      surfaceActionable(gd.cloud.lastErrorMeta);
      notify(
        'warning',
        buildToastMessage('云端快照加载失败', gd.cloud.error, gd.cloud.lastErrorMeta),
        buildAction(gd.cloud.lastErrorMeta, () => {
          gd.refreshAll();
        })
      );
    }
    if (gd.config.error && gd.config.error !== lastConfigErrorRef.current) {
      lastConfigErrorRef.current = gd.config.error;
      surfaceActionable(gd.config.lastErrorMeta);
      notify(
        'warning',
        buildToastMessage('配置状态加载失败', gd.config.error, gd.config.lastErrorMeta),
        buildAction(gd.config.lastErrorMeta, () => {
          gd.refreshAll();
        })
      );
    }
  }, [globalData, notify, buildAction, buildToastMessage, surfaceActionable]);
}
