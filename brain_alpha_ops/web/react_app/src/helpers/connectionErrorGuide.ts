/**
 * P1-2 / U-003: Connection error recovery guide.
 * Maps backend error_code values to user-facing messages and suggested
 * recovery actions. Every error_code emitted by the backend's
 * `_BRAIN_ERROR_CODE_MAP` (see helpers/errorExperience.ts) has a matching
 * entry here so users always get an actionable recovery entry.
 *
 * U-002: `rate_limit` / `rate_limited` entries keep a default `waitSeconds`
 * but callers should prefer the `retry_after` value from the response body
 * (or `Retry-After` header) when present.
 */

export interface ConnectionErrorGuideEntry {
  /** User-facing error message. */
  message: string;
  /** Label for the suggested action button. */
  actionLabel: string;
  /** Optional wait time in seconds before retry is advisable. */
  waitSeconds?: number;
}

export const CONNECTION_ERROR_GUIDE: Record<string, ConnectionErrorGuideEntry> = {
  // --- Rate limiting (U-002: callers should override waitSeconds with retry_after) ---
  rate_limit: {
    message: 'BRAIN 平台限流，请稍后重试',
    actionLabel: '稍后重试',
    waitSeconds: 30,
  },
  rate_limited: {
    message: 'BRAIN 平台限流，请稍后重试',
    actionLabel: '稍后重试',
    waitSeconds: 30,
  },
  official_rate_limited: {
    message: 'BRAIN 官方接口请求过于频繁，请稍后重试',
    actionLabel: '稍后重试',
    waitSeconds: 30,
  },
  web_rate_limited: {
    message: '本地页面请求过于频繁，请稍后重试',
    actionLabel: '稍后重试',
    waitSeconds: 10,
  },
  too_many_requests: {
    message: '请求过于频繁，请等待片刻后再试',
    actionLabel: '稍后重试',
    waitSeconds: 15,
  },
  concurrent_simulation_limit_exceeded: {
    message: 'BRAIN 回测并发槽位已满，系统将等待释放后自动重试',
    actionLabel: '查看槽位',
  },

  // --- Authentication / credentials ---
  invalid_credentials: {
    message: '用户名或密码不正确，请重新输入',
    actionLabel: '重新输入',
  },
  missing_credentials: {
    message: '缺少连接凭据，请填写账户邮箱和密码或 API Token',
    actionLabel: '填写凭据',
  },
  auth_invalid: {
    message: '认证失败，用户名或密码不正确',
    actionLabel: '重新输入',
  },
  auth_bearer_invalid: {
    message: 'Bearer Token 无效，请重新连接',
    actionLabel: '重新连接',
  },
  auth_token_expired: {
    message: '登录已过期，请重新输入凭据',
    actionLabel: '重新登录',
  },
  auth_required: {
    message: '需要重新登录，请刷新页面或重新输入凭据',
    actionLabel: '重新登录',
  },
  session_expired: {
    message: '本地会话已失效，请重新连接后继续',
    actionLabel: '重新连接',
  },
  session_invalid: {
    message: '本地会话已失效，请重新连接后继续',
    actionLabel: '重新连接',
  },
  admin_auth_required: {
    message: '远程 Web 访问需要管理员认证',
    actionLabel: '重新认证',
  },

  // --- Network / connectivity ---
  network_timeout: {
    message: '连接超时，请检查网络',
    actionLabel: '重试',
  },
  connection_refused: {
    message: '无法连接到 BRAIN 平台，请确认网络正常',
    actionLabel: '重试',
  },
  connection_error: {
    message: '连接 BRAIN 失败，请检查凭据和网络后重试',
    actionLabel: '重试',
  },
  request_timeout: {
    message: '请求处理超时，BRAIN 平台仍在处理中，请稍后重试',
    actionLabel: '稍后重试',
    waitSeconds: 15,
  },
  sse_connection_failed: {
    message: '实时进度连接失败，系统将自动重试',
    actionLabel: '重试',
  },
  sse_timeout: {
    message: '实时进度连接超时，请检查网络后刷新页面',
    actionLabel: '刷新页面',
  },

  // --- BRAIN platform ---
  brain_error: {
    message: 'BRAIN 平台异常，请稍后重试',
    actionLabel: '60秒后重试',
    waitSeconds: 60,
  },
  brain_server_error: {
    message: 'BRAIN 平台服务异常，请稍后重试',
    actionLabel: '60秒后重试',
    waitSeconds: 60,
  },
  internal_server_error: {
    message: '服务器内部错误，请稍后重试或联系管理员',
    actionLabel: '稍后重试',
    waitSeconds: 30,
  },
  bad_gateway: {
    message: '上游 BRAIN 服务暂时不可用，请稍后重试',
    actionLabel: '稍后重试',
    waitSeconds: 30,
  },
  service_unavailable: {
    message: '服务暂时不可用，正在恢复中，请稍后重试',
    actionLabel: '稍后重试',
    waitSeconds: 30,
  },

  // --- Validation / config ---
  validation_error: {
    message: '请求参数不合规，请检查输入后重试',
    actionLabel: '检查配置',
  },
  config_invalid: {
    message: '配置无效，请检查生产参数后重新保存',
    actionLabel: '检查配置',
  },

  // --- Job lifecycle ---
  job_already_running: {
    message: '已有验证任务在运行，请等待当前任务完成或手动停止后再启动',
    actionLabel: '查看任务',
  },
  job_start_failed: {
    message: '验证任务启动失败，请检查配置和连接后重试',
    actionLabel: '重试',
  },
  backtest_failed: {
    message: '回测请求失败，BRAIN 平台可能暂时繁忙，请稍后重试',
    actionLabel: '稍后重试',
    waitSeconds: 30,
  },
  backtest_timeout: {
    message: '回测请求超时，BRAIN 平台处理时间较长，系统将继续等待',
    actionLabel: '刷新状态',
  },

  // --- Sync / cache ---
  sync_failed: {
    message: '云端同步失败，请检查网络后手动重试',
    actionLabel: '重试',
  },
  sync_timeout: {
    message: '云端同步超时，建议缩小同步范围后重试',
    actionLabel: '重试',
  },
  cache_unavailable: {
    message: '本地缓存不可用，请先完成首次同步或检查本地数据目录',
    actionLabel: '刷新缓存',
  },
};

const _NORMALIZED_GUIDE: Record<string, ConnectionErrorGuideEntry> = (() => {
  const out: Record<string, ConnectionErrorGuideEntry> = {};
  for (const [key, value] of Object.entries(CONNECTION_ERROR_GUIDE)) {
    out[key.toLowerCase()] = value;
  }
  return out;
})();

/**
 * Look up the connection error guide entry for a given error_code.
 * Lookup is case-insensitive so backend codes like `RATE_LIMITED` match
 * guide keys like `rate_limited`. Returns undefined if no matching guide.
 */
export function getConnectionErrorGuide(
  errorCode: string | undefined | null
): ConnectionErrorGuideEntry | undefined {
  if (!errorCode) return undefined;
  return _NORMALIZED_GUIDE[errorCode.toLowerCase()];
}
