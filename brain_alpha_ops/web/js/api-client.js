// brain_alpha_ops/web/js/api-client.js
// Unified API fetch layer — single entry point for all backend calls.
// v3: Added retry logic, better timeout handling, typed errors.

(function () {
  'use strict';
  var CSRF_TOKEN = '__BRAIN_ALPHA_OPS_CSRF_TOKEN__';

  function apiUrl(path) {
    var url = new URL(path, window.location.origin);
    return url.pathname + url.search + url.hash;
  }

  var ERROR_MESSAGES = {
    SESSION_INVALID: '会话已过期，请刷新页面。',
    ORIGIN_FORBIDDEN: '仅允许本地访问。',
    JOB_NOT_FOUND: '任务不存在或已过期。',
    CONFLICT_RUNNING: '已有任务在运行，请先停止。',
    CONFLICT_AUX_OP: '请等待当前操作完成后再试。',
    VALIDATION_ERROR: '参数错误，请检查输入。',
    AUTH_FAILED: 'BRAIN API 认证失败，请检查凭据。',
    SUBMIT_BLOCKED: '提交被安全门禁阻断。',
    SUBMIT_NON_PRODUCTION_CANDIDATE: '提交被阻止：候选 Alpha 含非生产或模拟来源标记。',
    SUBMIT_NOT_READY: '提交被阻止：候选 Alpha 尚未通过本地与官方检查。',
    SUBMIT_FAILED_CANDIDATE: '提交被阻止：候选 Alpha 当前处于失败或拒绝状态。',
    SUBMIT_DUPLICATE_OFFICIAL_ID: '提交被阻止：该官方 Alpha ID 已记录在提交账本中。',
    SUBMIT_DUPLICATE_EXPRESSION: '提交被阻止：本地历史中已有相同或高相似表达式。',
    SUBMIT_CLOUD_SYNC_REQUIRED: '提交被阻止：请先同步云端 Alpha 缓存。',
    SUBMIT_CLOUD_SYNC_STALE: '提交被阻止：云端 Alpha 缓存已过期，请重新同步。',
    SUBMIT_CLOUD_ALREADY_SUBMITTED: '提交被阻止：云端记录显示该 Alpha 已提交或已进入生产状态。',
    SUBMIT_CLOUD_SELF_CORRELATION_BLOCKED: '提交被阻止：官方 cloud_self_correlation 风险过高。',
    SUBMIT_OBSERVABILITY_CONFIRMATION_REQUIRED: '提交前需要确认观测风险，请查看阻断项后再次确认。',
    SUBMIT_ERROR: '提交失败，请查看候选详情和服务日志。',
    SUBMIT_BATCH_ERROR: '批量提交失败，请查看失败项明细。',
    MISSING_OFFICIAL_ID: '缺少官方 Alpha ID，请先运行官方模拟。',
    INTERNAL_ERROR: '服务内部错误，请查看日志。',
    NETWORK_ERROR: '网络连接失败，请检查服务是否运行。',
    TIMEOUT_ERROR: '请求超时，请稍后重试。',
    NOT_FOUND: '请求的资源不存在。',
  };

  function userMessage(errorCode, fallback) {
    return ERROR_MESSAGES[errorCode] || fallback || '操作失败';
  }

  /**
   * v3: Core fetch with timeout support and retry logic.
   */
  async function apiFetch(path, options) {
    options = options || {};
    var timeoutMs = options.timeout || 30000; // default 30s
    var retries = options.retries || 0;
    var lastError = null;

    for (var attempt = 0; attempt <= retries; attempt++) {
      if (attempt > 0) {
        // Exponential backoff: 500ms, 1s, 2s...
        await new Promise(function (resolve) {
          setTimeout(resolve, Math.min(500 * Math.pow(2, attempt - 1), 5000));
        });
      }

      try {
        var controller = new AbortController();
        var timeoutId = setTimeout(function () { controller.abort(); }, timeoutMs);

        var response = await fetch(apiUrl(path), {
          method: options.method || 'GET',
          headers: Object.assign(
            { 'X-Brain-Alpha-CSRF': CSRF_TOKEN },
            options.headers || {}
          ),
          body: options.body || undefined,
          signal: controller.signal,
        });

        clearTimeout(timeoutId);

        var data;
        try {
          data = await response.json();
        } catch (parseErr) {
          throw createError('NETWORK_ERROR', '响应格式无效');
        }

        if (!data.ok) {
          var code = data.error_code || 'UNKNOWN';
          var msg = userMessage(code, data.error);
          var err = new Error(msg);
          err.code = code;
          err.data = data;
          // Don't retry on auth or validation errors
          if (code === 'AUTH_FAILED' || code === 'VALIDATION_ERROR' || code === 'SESSION_INVALID') {
            throw err;
          }
          throw err;
        }
        return data;
      } catch (e) {
        if (e.code) {
          lastError = e;
          if (e.code === 'AUTH_FAILED' || e.code === 'VALIDATION_ERROR' || e.code === 'SESSION_INVALID') {
            throw e;
          }
        } else if (e.name === 'AbortError') {
          lastError = createError('TIMEOUT_ERROR', '请求超时');
        } else {
          lastError = createError('NETWORK_ERROR', '网络连接失败');
        }
      }
    }

    throw lastError || createError('NETWORK_ERROR', '网络连接失败');
  }

  function createError(code, msg) {
    var err = new Error(msg);
    err.code = code;
    return err;
  }

  // ── Public API ────────────────────────────────────────────────────────
  window.ApiClient = {
    get: function (path, opts) {
      opts = opts || {};
      return apiFetch(path, { method: 'GET', timeout: opts.timeout, retries: opts.retries });
    },
    post: function (path, body, opts) {
      opts = opts || {};
      return apiFetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        timeout: opts.timeout,
        retries: opts.retries,
      });
    },
    ERROR_MESSAGES: ERROR_MESSAGES,
  };
})();
