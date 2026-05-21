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
  var MAX_RECONNECT = 5;

  // ── SSE connection ─────────────────────────────────────────────────────
  function connectSSE(jobId) {
    disconnectSSE();
    _reconnectAttempts = 0;

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
        if (_eventSource && _eventSource.readyState === EventSource.CLOSED) {
          disconnectSSE();
          if (_running && _jobId && _reconnectAttempts < MAX_RECONNECT) {
            _reconnectAttempts++;
            setTimeout(function () {
              if (_running && _jobId) connectSSE(_jobId);
            }, Math.min(2000 * _reconnectAttempts, 10000));
          } else if (_running && _jobId) {
            // Fallback to polling
            if (!_pollTimer) _pollTimer = setInterval(pollJobProgress, 5000);
          }
        }
      };
    } catch (e) {
      _eventSource = null;
      if (_running && _jobId && !_pollTimer) {
        _pollTimer = setInterval(pollJobProgress, 5000);
      }
    }
  }

  function disconnectSSE() {
    if (_eventSource) {
      try { _eventSource.close(); } catch (e) { /* ignore */ }
      _eventSource = null;
    }
  }

  // ── SSE message handler ────────────────────────────────────────────────
  function handleSSEMessage(data) {
    if (!data.ok) return;

    S.setBatch({
      'activeJobId': data.job_id || _jobId,
      'isRunning': true,
      'liveProgress': { phase: (data.progress || {}).phase || '', data: data.progress || {} },
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
      var d = await Api.get('/api/active_job');
      if (!d.ok || !d.job) return;
      var job = d.job;
      handleSSEMessage({
        ok: true,
        job_id: _jobId,
        status: job.status || 'running',
        progress: job.progress || {},
      });
    } catch (e) { /* silent */ }
  }

  // ── Job completion ─────────────────────────────────────────────────────
  function onJobComplete(status) {
    disconnectSSE();
    if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
    _running = false;
    S.setBatch({ 'isRunning': false, 'activeJobId': '' });

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
    S.set('isRunning', true);
    updateRunButton();
    Toast.info(options.resume ? '正在从断点恢复...' : '正在创建引导式生产任务...');

    try {
      var payload = window.collectPayload ? window.collectPayload() : {};
      payload.continuousMode = true;
      payload.guided = true;
      if (options.resume) payload.resume = true;

      var resp = await Api.post('/api/run', payload);
      if (!resp.ok) throw new Error(resp.error || '启动失败');

      _jobId = resp.job_id;
      S.set('activeJobId', _jobId);
      Toast.success((options.resume ? '断点续跑已启动' : '引导式生产已启动') + ' (job: ' + _jobId.slice(0, 8) + ')');

      connectSSE(_jobId);
    } catch (e) {
      _running = false;
      S.setBatch({ 'isRunning': false, 'activeJobId': '' });
      updateRunButton();
      disconnectSSE();
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
    S.setBatch({ 'isRunning': false, 'activeJobId': '' });
    updateRunButton();
  }

  // ── Init listener ──────────────────────────────────────────────────────
  S.onUpdate(function (path) {
    if (path === 'isRunning' || (path === 'activeJobId' && !S.get('isRunning'))) {
      updateRunButton();
    }
  });

  // Expose
  window.startProduction = startProduction;
  window.resumeProductionFromCheckpoint = function () {
    return startProduction({ resume: true });
  };
  window.stopProduction = stopProduction;
  window.connectSSE = connectSSE;
  window.disconnectSSE = disconnectSSE;
})();
