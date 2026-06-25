/**
 * Error handling utility functions
 */

/**
 * Error class for API-related errors
 */
export class ApiError extends Error {
  constructor(
    message: string,
    public statusCode?: number,
    public response?: unknown
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/**
 * Error class for validation errors
 */
export class ValidationError extends Error {
  constructor(
    message: string,
    public field?: string
  ) {
    super(message);
    this.name = 'ValidationError';
  }
}

/**
 * Logs an error to the console with additional context
 */
export function logError(error: unknown, context?: string): void {
  const timestamp = new Date().toISOString();
  const errorMessage = error instanceof Error ? error.message : String(error);
  const errorStack = error instanceof Error ? error.stack : undefined;

  console.error(
    `[${timestamp}]${context ? ` [${context}]` : ''} ${errorMessage}`,
    errorStack || ''
  );
}

/**
 * Formats an error for display to the user
 */
export function formatErrorForUser(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.statusCode === 401) {
      return '登录已过期，请重新登录。';
    }
    if (error.statusCode === 403) {
      return '您没有权限执行此操作。';
    }
    if (error.statusCode === 404) {
      return '请求的资源不存在。';
    }
    if (error.statusCode === 500) {
      return '服务器错误，请稍后再试。';
    }
    return error.message || '发生错误，请稍后再试。';
  }

  if (error instanceof ValidationError) {
    return error.field ? `${error.field}: ${error.message}` : error.message;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return '发生未知错误，请稍后再试。';
}

/**
 * Determines if an error should be reported to an error tracking service
 */
export function shouldReportError(error: unknown): boolean {
  // Don't report user cancellation errors
  if (error instanceof Error && error.name === 'AbortError') {
    return false;
  }

  // Don't report validation errors
  if (error instanceof ValidationError) {
    return false;
  }

  return true;
}

/**
 * Safely executes an async function and handles errors
 */
export async function safeExecute<T>(
  fn: () => Promise<T>,
  onError?: (error: unknown) => void
): Promise<T | null> {
  try {
    return await fn();
  } catch (error) {
    logError(error);
    onError?.(error);
    return null;
  }
}
