/**
 * Actionable error types & frontend classification (Workstream E3).
 *
 * Mirrors the backend ``brain_alpha_ops.error_catalog`` module so that
 * API error payloads carrying an ``actionable`` field can be rendered
 * uniformly by ``<ActionableError>``.  ``classifyError`` provides a
 * frontend-side fallback when an error has no actionable payload
 * attached (e.g. thrown by client code, network layer, or a backend
 * route that has not yet been migrated).
 *
 * Keep this file stdlib-only relative to the rest of the codebase: it
 * is imported from many places and should not pull heavy dependencies.
 */

// ── Backend payload shapes ────────────────────────────────────────────────

/** The 11 error kinds defined in the spec. */
export type ErrorKind =
  | 'login_expired'
  | 'cache_unavailable'
  | 'official_rate_limited'
  | 'simulation_concurrency_exceeded'
  | 'dataset_missing'
  | 'field_non_compliant'
  | 'expression_invalid'
  | 'network_timeout'
  | 'task_cancelled'
  | 'queue_blocked'
  | 'local_service_unavailable';

/** Severity colors map to ErrorCard's existing severity config. */
export type ErrorSeverity = 'error' | 'warning' | 'info';

/**
 * Structured actionable error payload (matches the dict returned by
 * ``brain_alpha_ops.error_catalog.build_actionable_error``).
 */
export interface ActionableErrorPayload {
  kind: ErrorKind;
  cause: string;
  impact_scope: string;
  suggested_action: string;
  /** Handler id the frontend dispatches on click (see RECOVERY_ACTION_LABELS). */
  recovery_action_id: string;
  /** Frontend route/handler id the user can click (e.g. "/config"). */
  recovery_url: string;
  /** i18n catalog key (e.g. "error.login_expired"). */
  i18n_key: string;
  severity: ErrorSeverity;
  context?: Record<string, unknown>;
}

/** A backend error response that carries an actionable payload. */
export interface ActionableErrorResponse {
  ok?: boolean;
  error?: string;
  error_code?: string;
  actionable?: ActionableErrorPayload;
  [key: string]: unknown;
}

// ── Type guards ───────────────────────────────────────────────────────────

export function isActionableErrorPayload(
  value: unknown
): value is ActionableErrorPayload {
  if (typeof value !== 'object' || value === null) return false;
  const rec = value as Record<string, unknown>;
  return (
    typeof rec.kind === 'string' &&
    typeof rec.cause === 'string' &&
    typeof rec.impact_scope === 'string' &&
    typeof rec.suggested_action === 'string' &&
    typeof rec.recovery_action_id === 'string' &&
    typeof rec.recovery_url === 'string' &&
    typeof rec.i18n_key === 'string' &&
    typeof rec.severity === 'string'
  );
}

export function isActionableErrorResponse(
  value: unknown
): value is ActionableErrorResponse {
  if (typeof value !== 'object' || value === null) return false;
  const rec = value as Record<string, unknown>;
  return isActionableErrorPayload(rec.actionable);
}

// ── Recovery action labels (mirrors backend recovery_action_id values) ────

export const RECOVERY_ACTION_LABELS: Record<string, string> = {
  reconnect_session: '重新连接',
  refresh_cache: '刷新缓存',
  review_official_slots: '查看回测队列',
  check_config: '检查配置',
  fix_expression: '前往候选管理',
  wait_and_retry: '稍后重试',
  resume_or_restart: '恢复或重启',
  restart_flow: '重启服务',
};

/** Human-readable Chinese label for a recovery_action_id. */
export function recoveryActionLabel(actionId: string | undefined): string | null {
  if (!actionId) return null;
  return RECOVERY_ACTION_LABELS[actionId] ?? null;
}

// ── Frontend classification (fallback when no actionable payload) ────────

const ERROR_KIND_KEYWORDS: Array<{ kind: ErrorKind; needles: string[] }> = [
  {
    kind: 'simulation_concurrency_exceeded',
    needles: ['concurrent_simulation_limit_exceeded', 'concurrent simulation limit'],
  },
  {
    kind: 'official_rate_limited',
    needles: ['rate_limited', 'rate limit', 'too many requests', '429'],
  },
  {
    kind: 'login_expired',
    needles: [
      'auth_token_expired',
      'session_expired',
      'session_invalid',
      'unauthorized',
      'forbidden',
      'invalid_credentials',
      'auth_invalid',
      '401',
      '403',
    ],
  },
  {
    kind: 'cache_unavailable',
    needles: [
      'cache_unavailable',
      'official_fields_empty',
      'official_operators_empty',
      'context_refresh_failed',
      'jsondecodeerror',
      'json decode',
    ],
  },
  {
    kind: 'dataset_missing',
    needles: ['dataset_not_found', 'dataset_not_in_official_context', 'unknown dataset'],
  },
  {
    kind: 'field_non_compliant',
    needles: ['field_not_supported', 'field_non_compliant', 'validation_failed'],
  },
  {
    kind: 'expression_invalid',
    needles: [
      'expression_empty',
      'expression_unbalanced_parens',
      'expression_unknown_operator',
      'expression_null_bytes',
      'expression_invalid',
      'syntax error',
      'unknown operator',
    ],
  },
  {
    kind: 'network_timeout',
    needles: [
      'timed out',
      'timeout',
      'incompleteread',
      'incomplete read',
      'remote end closed',
      'connection reset',
      'connection aborted',
      '408',
      '504',
    ],
  },
  {
    kind: 'task_cancelled',
    needles: ['task_cancelled', 'raw backend cancellation', 'job cancelled', 'aborted', 'aborterror'],
  },
  {
    kind: 'queue_blocked',
    needles: ['queue_blocked', 'jobs_full', 'queue full', 'max concurrent active jobs'],
  },
  {
    kind: 'local_service_unavailable',
    needles: [
      'connection refused',
      'service unavailable',
      'local service',
      'web server not running',
      'health check failed',
      '503',
    ],
  },
];

/**
 * Classify a frontend error (Error / response object / string) into an
 * ErrorKind.  Used as a fallback when the backend did not attach an
 * ``actionable`` payload.  Mirrors the backend classify_exception()
 * resolution: substring match against message + known status codes.
 *
 * Returns ``'network_timeout'`` as the least-misleading fallback when
 * nothing matches (avoids implying user fault or system-down).
 */
export function classifyError(err: unknown): ErrorKind {
  if (err == null) return 'network_timeout';

  // Status code shortcut (number or numeric string).
  const status =
    typeof err === 'number'
      ? err
      : typeof err === 'object' &&
        err !== null &&
        typeof (err as { status_code?: unknown }).status_code === 'number'
      ? (err as { status_code: number }).status_code
      : null;
  if (status !== null) {
    if (status === 401 || status === 403) return 'login_expired';
    if (status === 429) return 'official_rate_limited';
    if (status === 408 || status === 504) return 'network_timeout';
    if (status === 503) return 'local_service_unavailable';
  }

  const text = stringifyError(err).toLowerCase();
  if (!text) return 'network_timeout';

  // DOMException/AbortError → task_cancelled (user-initiated cancel).
  if (
    typeof DOMException !== 'undefined' &&
    err instanceof DOMException &&
    err.name === 'AbortError'
  ) {
    return 'task_cancelled';
  }

  for (const rule of ERROR_KIND_KEYWORDS) {
    for (const needle of rule.needles) {
      if (text.includes(needle)) return rule.kind;
    }
  }
  return 'network_timeout';
}

function stringifyError(err: unknown): string {
  if (typeof err === 'string') return err;
  if (err instanceof Error) {
    const code = (err as { code?: string }).code;
    return [code || '', err.message || '', err.name || ''].join(' ');
  }
  if (typeof err === 'object' && err !== null) {
    const rec = err as Record<string, unknown>;
    const parts: string[] = [];
    for (const key of [
      'error_code',
      'error',
      'message',
      'status',
      'status_code',
      'user_error_kind',
    ]) {
      const value = rec[key];
      if (typeof value === 'string' && value) parts.push(value);
    }
    return parts.join(' ');
  }
  return String(err || '');
}

// ── Builder (frontend-side fallback payload) ─────────────────────────────

/**
 * Minimal recovery_url mapping for kinds.  Mirrors the backend
 * ``RECOVERY_URLS`` dict so the frontend can render a recovery entry
 * even when only a kind is known (no full payload from backend).
 */
export const ERROR_KIND_RECOVERY_URL: Record<ErrorKind, string> = {
  login_expired: '/config',
  cache_unavailable: '/operations/refresh',
  official_rate_limited: '/backtests',
  simulation_concurrency_exceeded: '/backtests',
  dataset_missing: '/config',
  field_non_compliant: '/config',
  expression_invalid: '/candidates',
  network_timeout: '/backtests',
  task_cancelled: '/dashboard',
  queue_blocked: '/backtests',
  local_service_unavailable: '/dashboard',
};

/** Default Chinese cause/suggested_action text per kind (compact mirror of catalog). */
const FALLBACK_TEXT: Record<ErrorKind, { cause: string; action: string; severity: ErrorSeverity }> = {
  login_expired: {
    cause: '登录会话已失效或凭据过期。',
    action: '请前往系统配置重新测试连接。',
    severity: 'error',
  },
  cache_unavailable: {
    cause: '本地能力集缓存不可用。',
    action: '请在官方操作入口刷新官方能力集。',
    severity: 'warning',
  },
  official_rate_limited: {
    cause: 'BRAIN 官方接口限流（429）。',
    action: '请稍后重试或查看回测队列。',
    severity: 'warning',
  },
  simulation_concurrency_exceeded: {
    cause: 'BRAIN 回测并发槽位已满。',
    action: '请等待已有回测完成后再提交。',
    severity: 'warning',
  },
  dataset_missing: {
    cause: '指定的 Dataset 不在能力集中。',
    action: '请在系统配置中选择可用 Dataset。',
    severity: 'error',
  },
  field_non_compliant: {
    cause: '字段/参数不符合 BRAIN 平台规则。',
    action: '请检查字段名与取值范围。',
    severity: 'error',
  },
  expression_invalid: {
    cause: '表达式语法非法或包含未知算子。',
    action: '请在候选管理修正表达式后重试。',
    severity: 'error',
  },
  network_timeout: {
    cause: '网络请求超时。',
    action: '请稍后重试或检查网络状态。',
    severity: 'warning',
  },
  task_cancelled: {
    cause: '任务已取消。',
    action: '可在运行总览查看任务状态。',
    severity: 'info',
  },
  queue_blocked: {
    cause: '官方模拟队列阻塞。',
    action: '请在回测监控查看队列状态。',
    severity: 'warning',
  },
  local_service_unavailable: {
    cause: '本地 Web 服务未启动。',
    action: '请让维护者启动本地 Web 服务。',
    severity: 'error',
  },
};

/** Recovery action id per kind (mirrors backend recovery_action_id). */
const RECOVERY_ACTION_ID: Record<ErrorKind, string> = {
  login_expired: 'reconnect_session',
  cache_unavailable: 'refresh_cache',
  official_rate_limited: 'review_official_slots',
  simulation_concurrency_exceeded: 'review_official_slots',
  dataset_missing: 'check_config',
  field_non_compliant: 'check_config',
  expression_invalid: 'fix_expression',
  network_timeout: 'wait_and_retry',
  task_cancelled: 'resume_or_restart',
  queue_blocked: 'review_official_slots',
  local_service_unavailable: 'restart_flow',
};

/**
 * Build an ActionableErrorPayload on the frontend side when the backend
 * did not provide one.  The text comes from FALLBACK_TEXT; the
 * ``context`` field is filled with whatever was supplied.
 */
export function buildActionableError(
  kind: ErrorKind,
  context?: Record<string, unknown>
): ActionableErrorPayload {
  const fallback = FALLBACK_TEXT[kind];
  return {
    kind,
    cause: fallback.cause,
    impact_scope: '',
    suggested_action: fallback.action,
    recovery_action_id: RECOVERY_ACTION_ID[kind],
    recovery_url: ERROR_KIND_RECOVERY_URL[kind],
    i18n_key: `error.${kind}`,
    severity: fallback.severity,
    context: context ?? {},
  };
}
