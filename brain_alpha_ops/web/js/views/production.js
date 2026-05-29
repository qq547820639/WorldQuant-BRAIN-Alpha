// brain_alpha_ops/web/js/views/production.js
// SSE-based production control — real-time progress without polling.
// v3: Enhanced with reconnection logic, better status updates, and UX flow.

(function () {
  'use strict';

  var STREAM_TOKEN = '__BRAIN_ALPHA_OPS_STREAM_TOKEN__';
  var $ = window.Utils.$;
  var esc = window.Utils.escapeHtml;
  var Api = window.ApiClient;
  var S = window.AppState;
  var Toast = window.Toast;

  // ── State ──────────────────────────────────────────────────────────────
  var _running = false;
  var _jobId = '';
  var _pollTimer = null;
  var _eventSource = null;
  var _reconnectAttempts = 0;
  var _sseFallbackAnnounced = false;
  var MAX_RECONNECT = 5;
  var POLL_INTERVAL_MS = 5000;

  // ── SSE connection ─────────────────────────────────────────────────────
  function connectSSE(jobId) {
    disconnectSSE();
    _reconnectAttempts = 0;
    _sseFallbackAnnounced = false;
    openSSE(jobId);
  }

  function openSSE(jobId) {
    var url = '/api/stream?job_id=' + encodeURIComponent(jobId) +
              '&stream_token=' + encodeURIComponent(STREAM_TOKEN);

    try {
      _eventSource = new EventSource(url);

      _eventSource.onmessage = function (event) {
        _reconnectAttempts = 0;
        try {
          var data = JSON.parse(event.data);
          handleSSEMessage(data);
        } catch (e) { /* ignore */ }
      };

      _eventSource.onerror = function () {
        if (!_running || !_jobId) {
          disconnectSSE();
          return;
        }
        disconnectSSE();
        _reconnectAttempts++;
        if (_reconnectAttempts <= MAX_RECONNECT) {
          setTimeout(function () {
            if (_running && _jobId) openSSE(_jobId);
          }, Math.min(2000 * _reconnectAttempts, 10000));
        } else {
          startPollingFallback('实时进度流连接失败，已切换为状态轮询。');
        }
      };
    } catch (e) {
      _eventSource = null;
      if (_running && _jobId) startPollingFallback('实时进度流不可用，已切换为状态轮询。');
    }
  }

  function disconnectSSE() {
    if (_eventSource) {
      try { _eventSource.close(); } catch (e) { /* ignore */ }
      _eventSource = null;
    }
  }

  function startPollingFallback(message) {
    if (!_running || !_jobId) return;
    disconnectSSE();
    if (!_pollTimer) _pollTimer = setInterval(pollJobProgress, POLL_INTERVAL_MS);
    if (!_sseFallbackAnnounced) {
      _sseFallbackAnnounced = true;
      Toast.warning(message);
    }
    S.setBatch({
      'liveProgress': {
        phase: 'production',
        data: {
          phase: 'production',
          phase_label: '生产搜索',
          message: message,
          percent: 0,
        },
      },
      'runtimeStatusUpdatedAt': Date.now(),
    });
    if (typeof window.renderRuntimeStatus === 'function') window.renderRuntimeStatus();
    pollJobProgress();
  }

  // ── SSE message handler ────────────────────────────────────────────────
  function handleSSEMessage(data) {
    if (!data.ok) return;

    var now = Date.now();
    S.setBatch({
      'activeJobId': data.job_id || _jobId,
      'isRunning': true,
      'liveProgress': { phase: (data.progress || {}).phase || '', data: data.progress || {} },
      'runtimeStatusStartedAt': S.get('runtimeStatusStartedAt') || now,
      'runtimeStatusUpdatedAt': now,
    });

    // Update header status dot
    var statusDot = $('headerStatusDot');
    if (statusDot) {
      statusDot.className = 'header-status-dot is-running';
    }

    var progress = data.progress || {};

    // Update progress bar if present on the action card
    if (typeof window.Progress === 'object' && window.Progress.renderProgress) {
      window.Progress.renderProgress('cloudSync', {
        percent: progress.percent,
        message: (progress.phase_label || window.Utils.phaseName(progress.phase)) + (progress.message ? ': ' + progress.message : ''),
        scanned: progress.scanned, total: progress.total,
      });
    }

    // Render snapshot
    if (window._app && window._app.renderJobSnapshot) {
      window._app.renderJobSnapshot({
        job_id: data.job_id || _jobId,
        status: data.status || 'running',
        progress: progress,
        result: {},
      });
    } else {
      if (typeof window.renderOpsMonitor === 'function') window.renderOpsMonitor();
      if (typeof window.renderInsight === 'function') window.renderInsight();
    }

    // Terminal states
    var status = data.status || '';
    if (status === 'completed' || status === 'failed' || status === 'stopped') {
      onJobComplete(status);
    }
  }

  // ── Polling fallback ───────────────────────────────────────────────────
  async function pollJobProgress() {
    try {
      var path = _jobId ? '/api/status?job_id=' + encodeURIComponent(_jobId) : '/api/active_job';
      var job = await Api.get(path);
      if (!job || !job.ok) return;
      handleSSEMessage({
        ok: true,
        job_id: job.job_id || _jobId,
        status: job.status || 'running',
        progress: job.progress || {},
        error: job.error || '',
      });
    } catch (e) {
      if (e && e.code === 'SESSION_INVALID') {
        Toast.error('本地会话已过期，请刷新页面后重试。');
        disconnectSSE();
        if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
      }
    }
  }

  // ── Job completion ─────────────────────────────────────────────────────
  function onJobComplete(status) {
    disconnectSSE();
    if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
    _running = false;
    S.setBatch({ 'isRunning': false, 'activeJobId': '', 'runtimeStatusStartedAt': 0, 'runtimeStatusUpdatedAt': 0, 'liveProgress': {} });

    var statusDot = $('headerStatusDot');
    if (statusDot) statusDot.className = 'header-status-dot';

    updateRunButton();

    var isSuccess = status === 'completed';
    Toast.toast(
      '生产任务' + (isSuccess ? '已完成' : '结束') + (status === 'failed' ? ' (失败)' : ''),
      isSuccess ? 'success' : 'error'
    );

    // Refresh data
    if (window._app) {
      if (window._app.renderJobSnapshot && _jobId) {
        Api.get('/api/status?job_id=' + encodeURIComponent(_jobId))
          .then(function (snapshot) { window._app.renderJobSnapshot(snapshot); })
          .catch(function () {});
      }
      if (window._app.loadConfig) window._app.loadConfig();
      if (window._app.loadCheckResults) window._app.loadCheckResults();
      if (window._app.loadCloudSnapshot) window._app.loadCloudSnapshot();
      if (window._app.loadResearchMemory) window._app.loadResearchMemory();
    }
    if (typeof window.loadCheckpointStatus === 'function') window.loadCheckpointStatus();

    _jobId = '';
  }

  // ── UI ─────────────────────────────────────────────────────────────────
  function updateRunButton() {
    var btn = $('controlButton');
    if (!btn) return;
    var running = _running || Boolean(S.get('isRunning'));
    btn.textContent = running ? '⏹ 停止生产' : '▶ 开始生产搜索';
    if (running) {
      btn.classList.add('is-stopping');
    } else {
      btn.classList.remove('is-stopping');
    }
    btn.disabled = false;
    if (typeof window.renderBusyControls === 'function') window.renderBusyControls();
  }

  // ── Production control ─────────────────────────────────────────────────
  window.toggleRun = async function () {
    if (_running || S.get('isRunning')) {
      await stopProduction();
      return;
    }
    await startProduction();
  };

  async function startProduction(options) {
    options = options || {};
    var blockReason = typeof window.operationBlockReason === 'function'
      ? window.operationBlockReason('production') : '';
    if (blockReason) {
      Toast.warning(blockReason);
      if (typeof window.renderBusyControls === 'function') window.renderBusyControls();
      return;
    }

    _running = true;
    var startedAt = Date.now();
    S.setBatch({
      'isRunning': true,
      'runtimeStatusStartedAt': startedAt,
      'runtimeStatusUpdatedAt': startedAt,
      'liveProgress': {
        phase: 'production',
        data: {
          phase: 'production',
          phase_label: '生产搜索',
          message: '正在启动生产搜索，请稍候。',
          percent: 0,
        },
      },
    });
    updateRunButton();
    Toast.info(options.resume ? '正在从断点恢复...' : '正在创建引导式生产任务...');
    if (typeof window.renderRuntimeStatus === 'function') window.renderRuntimeStatus();

    try {
      var payload = window.collectPayload ? window.collectPayload() : {};
      payload.continuousMode = true;
      payload.guided = true;
      if (options.resume) payload.resume = true;

      var resp = await Api.post('/api/run', payload);
      if (!resp.ok) throw new Error(resp.error || '启动失败');

      _jobId = resp.job_id;
      S.setBatch({
        'activeJobId': _jobId,
        'runtimeStatusUpdatedAt': Date.now(),
        'liveProgress': {
          phase: 'production',
          data: {
            phase: 'production',
            phase_label: '生产搜索',
            message: '任务已启动，等待第一条进度。',
            percent: 0,
          },
        },
      });
      Toast.success((options.resume ? '断点续跑已启动' : '引导式生产已启动') + ' (job: ' + _jobId.slice(0, 8) + ')');

      connectSSE(_jobId);
    } catch (e) {
      _running = false;
      S.setBatch({ 'isRunning': false, 'activeJobId': '', 'runtimeStatusStartedAt': 0, 'runtimeStatusUpdatedAt': 0, 'liveProgress': {} });
      updateRunButton();
      disconnectSSE();
      if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
      Toast.error('启动失败: ' + e.message);
    }
  }

  async function stopProduction() {
    disconnectSSE();
    if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }

    try {
      var jobId = _jobId || S.get('activeJobId') || '';
      var resp = await Api.post('/api/stop', { job_id: jobId });
      if (resp.ok) Toast.info('生产已停止');
    } catch (e) { /* force stop */ }

    _running = false;
    _jobId = '';
    S.setBatch({ 'isRunning': false, 'activeJobId': '', 'runtimeStatusStartedAt': 0, 'runtimeStatusUpdatedAt': 0, 'liveProgress': {} });
    updateRunButton();
  }

  async function loadCheckpointStatus() {
    var el = $('checkpointSummary');
    try {
      var data = await Api.get('/api/checkpoint/status', { timeout: 15000 });
      if (!data || !data.ok) throw new Error((data && data.error) || '断点状态不可用');
      S.set('checkpointStatus', data);
      var checkpointCount = Number(data.checkpoint_count || 0);
      var historyCount = Number(data.history_count || 0);
      var latest = data.latest || {};
      var latestHistory = data.latest_history || {};
      var comparison = data.latest_comparison || {};
      var deltas = comparison.deltas || {};
      var phase = latest.phase_completed || latest.phase || '';
      var status = latestHistory.status || '';
      var parts = [];
      parts.push(data.resume_available ? '断点可续跑' : '暂无断点');
      parts.push('断点 ' + checkpointCount);
      parts.push('历史 ' + historyCount);
      if (phase) parts.push(window.Utils.phaseName(phase));
      if (status) parts.push(status);
      if (typeof deltas.best_score === 'number') parts.push('分数Δ ' + deltas.best_score);
      if (typeof deltas.submission_ready === 'number') parts.push('达标Δ ' + deltas.submission_ready);
      if (el) {
        el.textContent = parts.join(' · ');
        el.title = latest.run_id || latestHistory.run_id || '';
      }
      return data;
    } catch (e) {
      if (el) {
        el.textContent = '断点状态不可用';
        el.title = e.message || '';
      }
      return { ok: false, error: e.message || String(e) };
    }
  }

  // ── Init listener ──────────────────────────────────────────────────────
  S.onUpdate(function (path) {
    if (path === 'isRunning' || (path === 'activeJobId' && !S.get('isRunning'))) {
      updateRunButton();
    }
  });

  // Expose
  window.startProduction = startProduction;
  window.ProductionView = window.ProductionView || {};
  window.ProductionView.loadCheckpointStatus = loadCheckpointStatus;
  window.resumeProductionFromCheckpoint = function () {
    return startProduction({ resume: true });
  };
  window.stopProduction = stopProduction;
  window.loadCheckpointStatus = loadCheckpointStatus;
  window.connectSSE = connectSSE;
  window.disconnectSSE = disconnectSSE;
})();
