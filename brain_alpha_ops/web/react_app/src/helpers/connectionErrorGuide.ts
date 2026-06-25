/**
 * P1-2: Connection error recovery guide.
 * Maps backend error_code values to user-facing messages and suggested actions.
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
  rate_limit: {
    message: 'BRAIN 平台限流，请稍后重试',
    actionLabel: '30秒后重试',
    waitSeconds: 30,
  },
  invalid_credentials: {
    message: '用户名或密码不正确',
    actionLabel: '重新输入',
    waitSeconds: 0,
  },
  network_timeout: {
    message: '连接超时，请检查网络',
    actionLabel: '重试',
    waitSeconds: 0,
  },
  brain_error: {
    message: 'BRAIN 平台异常，请稍后重试',
    actionLabel: '60秒后重试',
    waitSeconds: 60,
  },
};

/**
 * Look up the connection error guide entry for a given error_code.
 * Returns undefined if no matching guide is found.
 */
export function getConnectionErrorGuide(
  errorCode: string | undefined | null
): ConnectionErrorGuideEntry | undefined {
  if (!errorCode) return undefined;
  return CONNECTION_ERROR_GUIDE[errorCode];
}
