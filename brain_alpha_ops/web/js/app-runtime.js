// brain_alpha_ops/web/js/app-runtime.js
// Runtime progress, operation locks, and async job feedback helpers.
(function () {
  'use strict';

  var Utils = window.Utils || {};
  var $ = Utils.$ || function (id) { return document.getElementById(id); };
  var phaseName = Utils.phaseName || function (phase) { return String(phase || ''); };
  var Api = window.ApiClient;
  var S = window.AppState;
  var Toast = window.Toast;
  var callbacks = {
    renderTaskRail: function () { if (typeof window.renderTaskRail === 'function') window.renderTaskRail(); },
    syncStrategyPluginControls: function () { if (typeof window.syncStrategyPluginControls === 'function') window.syncStrategyPluginControls(); },
  };

  function configure(options) {
    options = options || {};
    if (typeof options.renderTaskRail === 'function') callbacks.renderTaskRail = options.renderTaskRail;
    if (typeof options.syncStrategyPluginControls === 'function') callbacks.syncStrategyPluginControls = options.syncStrategyPluginControls;
  }

  function syncInFlight() { return Boolean(S.get('syncInFlight')); }
  function batchCheckJobId() { return S.get('batchCheckJobId') || ''; }
  function asyncOperationJobId() { return S.get('asyncOperationJobId') || ''; }
  function submitInFlight() { return Boolean(S.get('submitInFlight')); }
  function selectedSubmitList() { return S.get('selectedSubmitIds') || []; }
  function selectedSubmitCount() { return selectedSubmitList().length; }
  function requestEtaSeconds(count, perItem, minSeconds, maxSeconds) {
    count = Math.max(1, Number(count || 1));
    var estimate = Math.ceil(count * Number(perItem || 2));
    return Math.min(Number(maxSeconds || 60), Math.max(Number(minSeconds || 6), estimate));
  }
  function etaDeadline(startedAt, seconds) {
    return Number(startedAt || Date.now()) + Math.max(1, Number(seconds || 1)) * 1000;
  }
  function setControlState(id, disabled, reason) {
    var el = $(id); if (!el) return;
    if (!Object.prototype.hasOwnProperty.call(el.dataset, 'defaultTitle')) {
      var currentTitle = el.getAttribute('title') || '';
      el.dataset.defaultTitle = reason && isTransientControlTitle(currentTitle) ? '' : currentTitle;
    }
    el.disabled = Boolean(disabled);
    el.setAttribute('aria-disabled', Boolean(disabled));
    if (reason) {
      el.setAttribute('title', reason);
    } else if (el.dataset.defaultTitle) {
      el.setAttribute('title', el.dataset.defaultTitle);
    } else {
      el.removeAttribute('title');
    }
  }
  function isTransientControlTitle(title) {
    title = String(title || '');
    if (!title) return false;
    if (title.indexOf('正在') !== -1) return true;
    if (title.indexOf('请先') === 0) return true;
    return ['页面数据正在加载。', '云端同步正在进行。', '达标检查正在进行。', '提交正在进行。'].indexOf(title) !== -1;
  }

  function operationBlockReason(action) {
    var running = Boolean(S.get('isRunning'));
    var asyncJobId = asyncOperationJobId();
    if (asyncJobId) return (S.get('asyncOperationLabel') || '后台任务') + '正在进行。';
    if (S.get('connectionTestInFlight')) return '连接测试正在进行。';
    if (S.get('pageLoadInFlight')) return '页面数据正在加载。';
    switch (action) {
      case 'production': if (syncInFlight()) return '云端同步正在进行。'; if (batchCheckJobId()) return '达标检查正在进行。'; if (submitInFlight()) return '提交正在进行。'; return '';
      case 'sync': if (running) return '生产任务运行中。'; if (batchCheckJobId()) return '达标检查正在进行。'; if (submitInFlight()) return '提交正在进行。'; if (syncInFlight()) return '云端同步正在进行。'; return '';
      case 'check': if (running) return '生产任务运行中。'; if (syncInFlight()) return '云端同步正在进行。'; if (submitInFlight()) return '提交正在进行。'; if (batchCheckJobId()) return '达标检查正在进行。'; return '';
      case 'submit': if (running) return '生产任务运行中。'; if (syncInFlight()) return '云端同步正在进行。'; if (batchCheckJobId()) return '达标检查正在进行。'; if (submitInFlight()) return '提交正在进行。'; return '';
    }
    return '';
  }

  function currentOperationText() {
    if (asyncOperationJobId()) return (S.get('asyncOperationLabel') || '后台任务') + '正在进行，其他冲突操作已暂时锁定。';
    if (syncInFlight()) return '云端同步正在进行，其他冲突操作已暂时锁定。';
    if (batchCheckJobId()) return '达标检查正在进行，其他冲突操作已暂时锁定。';
    if (submitInFlight()) return '提交正在进行，其他冲突操作已暂时锁定。';
    if (S.get('isRunning')) return '生产任务正在运行。';
    if (S.get('connectionTestInFlight')) return '连接测试正在进行，核心操作已暂时锁定。';
    if (S.get('pageLoadInFlight')) return '页面数据正在加载，核心操作已暂时锁定。';
    return '';
  }

  function activeRuntimeKind() {
    if (S.get('isRunning')) return 'production';
    if (syncInFlight()) return 'sync';
    if (batchCheckJobId()) return 'check';
    if (submitInFlight()) return 'submit';
    if (asyncOperationJobId()) return 'async';
    if (S.get('connectionTestInFlight')) return 'connection';
    if (S.get('pageLoadInFlight')) return 'page_load';
    return '';
  }
  function runtimeKindLabel(kind) {
    if (kind === 'production') return '生产搜索';
    if (kind === 'sync') return '云端同步';
    if (kind === 'check') return '达标检查';
    if (kind === 'submit') return '提交处理';
    if (kind === 'connection') return '连接测试';
    if (kind === 'page_load') return '页面加载';
    if (kind === 'async') return S.get('asyncOperationLabel') || '后台任务';
    return '后台任务';
  }
  function connectionStatusLabel() {
    var connectionStatus = String(S.get('connectionStatus') || 'disconnected');
    var env = S.get('connectionEnvironment') || '';
    var auth = S.get('connectionAuth') || '';
    if (connectionStatus === 'connected') {
      return '已连接' + (env ? ' — ' + env : '') + (auth ? ' · ' + auth : '');
    }
    if (connectionStatus === 'failed') return '连接失败';
    return '未连接';
  }
  function renderHeaderStatus() {
    if (window.HeaderStatus && window.HeaderStatus.render) {
      window.HeaderStatus.render(activeRuntimeKind(), runtimeKindLabel);
    }
  }

  function runtimeDefaultMessage(kind) {
    if (kind === 'production') return '正在生成、回测并筛选 Alpha，结果会陆续刷新。';
    if (kind === 'sync') return '正在读取官方云端数据，列表会在完成后更新。';
    if (kind === 'check') return '正在向官方发送预提交检查，请等待结果返回。';
    if (kind === 'submit') return '正在提交已选择的 Alpha，请不要重复点击。';
    if (kind === 'connection') return '正在验证账号与官方生产环境连接。';
    if (kind === 'page_load') return '正在加载页面数据，完成后会自动刷新界面。';
    if (kind === 'async') return '后台任务正在处理，完成后会自动刷新界面。';
    return '后台正在处理，请稍候。';
  }
  function formatDuration(ms) {
    var seconds = Math.max(0, Math.floor(Number(ms || 0) / 1000));
    if (seconds < 60) return seconds + ' 秒';
    var minutes = Math.floor(seconds / 60);
    var remain = seconds % 60;
    if (minutes < 60) return minutes + ' 分 ' + remain + ' 秒';
    var hours = Math.floor(minutes / 60);
    return hours + ' 小时 ' + (minutes % 60) + ' 分';
  }
  function formatClock(ts, now) {
    ts = Number(ts || 0);
    if (!ts) return '等待首次进度';
    var diff = Math.max(0, Number(now || Date.now()) - ts);
    if (diff < 5000) return '刚刚';
    return formatDuration(diff) + '前';
  }
  function formatEtaClock(ts) {
    try {
      return new Date(Number(ts || 0)).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch (e) {
      return '';
    }
  }
  function runtimeRemainingSeconds(progress, now, updatedAt) {
    progress = progress || {};
    var deadline = Number(progress.eta_deadline_at_ms || 0);
    if (deadline > 0) return Math.max(0, Math.ceil((deadline - now) / 1000));
    var eta = Number(progress.eta_seconds || 0);
    if (eta > 0) {
      var calculatedAt = Number(progress.updated_at_ms || updatedAt || now);
      return Math.max(0, Math.ceil(eta - ((now - calculatedAt) / 1000)));
    }
    return null;
  }
  function runtimeDynamicHint(kind, progress, now, updatedAt, stale) {
    var remaining = runtimeRemainingSeconds(progress, now, updatedAt);
    if (remaining !== null) {
      if (remaining > 0) {
        var deadline = Number((progress || {}).eta_deadline_at_ms || 0) || (now + remaining * 1000);
        var clock = formatEtaClock(deadline);
        return '预计剩余 ' + formatDuration(remaining * 1000) + (clock ? '，预计 ' + clock + ' 完成。' : '。');
      }
      return '已到预计完成时间，正在等待官方接口返回最新结果。';
    }
    var nextPollAt = Number((progress || {}).next_poll_at_ms || 0);
    if (nextPollAt > now) {
      return '下一次状态刷新倒计时 ' + formatDuration(nextPollAt - now) + '，系统会自动继续检查。';
    }
    if (stale) return '已经超过 2 分钟没有收到新进度，后台可能仍在等待官方接口返回；如果长时间不动，可点击停止后重试。';
    if (kind === 'sync') return '正在等待官方接口返回；页面会按倒计时自动刷新状态。';
    return '页面没有卡死；系统会在收到新进度后自动刷新。';
  }
  function numberText(value) {
    var num = Number(value);
    return Number.isFinite(num) ? String(num) : '';
  }
  function runtimeProgressData(kind) {
    var live = S.get('liveProgress') || {};
    var data = live.data || {};
    if (kind === 'submit') return data || {};
    if (kind === 'sync') {
      if (data.cloud_sync) return data.cloud_sync || {};
      if (data.progress) return data.progress || {};
      return data || {};
    }
    if (kind === 'check') return data || {};
    if (kind === 'async') {
      if (data.progress) return data.progress || {};
      return data || {};
    }
    if (kind === 'production') {
      if (data.progress) return data.progress || {};
      if (data.phase || data.message || data.percent !== undefined) return data || {};
      return data || {};
    }
    if (data.cloud_sync) return data.cloud_sync || {};
    if (data.progress) return data.progress || {};
    return data || {};
  }
  function runtimeProgressPercent(progress) {
    if (!progress) return null;
    var percent = Number(progress.percent_complete !== undefined && progress.percent_complete !== null ? progress.percent_complete : progress.percent);
    if (Number.isFinite(percent)) return Math.min(100, Math.max(0, percent));
    var scanned = Number(progress.scanned || progress.current || progress.done || 0);
    var total = Number(progress.total || 0);
    if (total > 0) return Math.min(100, Math.max(0, scanned / total * 100));
    return null;
  }
  function runtimeCountText(progress) {
    progress = progress || {};
    var scanned = numberText(progress.scanned || progress.checked || progress.submitted || progress.current || progress.done);
    var total = numberText(progress.total);
    if (scanned && total) return scanned + ' / ' + total;
    if (scanned) return scanned;
    if (progress.added !== undefined || progress.updated !== undefined || progress.skipped !== undefined) {
      var parts = [];
      if (progress.added !== undefined) parts.push('新增 ' + Number(progress.added || 0));
      if (progress.updated !== undefined) parts.push('更新 ' + Number(progress.updated || 0));
      if (progress.skipped !== undefined) parts.push('跳过 ' + Number(progress.skipped || 0));
      return parts.join('，');
    }
    return '-';
  }
  function runtimeTitle(kind, progress) {
    var phase = progress && (progress.phase_label || phaseName(progress.phase || ''));
    if (phase) return runtimeKindLabel(kind) + '：' + phase;
    return runtimeKindLabel(kind) + '正在进行';
  }
  function touchRuntimeStatus(startedAt, progress) {
    var now = Date.now();
    var batch = {
      runtimeStatusStartedAt: startedAt || S.get('runtimeStatusStartedAt') || now,
      runtimeStatusUpdatedAt: now,
    };
    if (progress) batch.liveProgress = progress;
    S.setBatch(batch);
    renderRuntimeStatus();
  }
  function clearRuntimeStatus() {
    S.setBatch({ runtimeStatusStartedAt: 0, runtimeStatusUpdatedAt: 0, liveProgress: {} });
    renderRuntimeStatus();
  }
  function isTerminalJobStatus(status) {
    return ['completed', 'completed_with_warnings', 'stopped', 'failed', 'cancelled', 'canceled'].indexOf(String(status || '').toLowerCase()) !== -1;
  }
  function normalizeAsyncProgress(data, options) {
    data = data || {};
    options = options || {};
    var progress = Object.assign({}, data.progress || {});
    var status = data.status || progress.status || 'running';
    progress.task_id = progress.task_id || data.task_id || data.job_id || options.jobId || '';
    progress.job_id = progress.job_id || data.job_id || data.task_id || options.jobId || '';
    progress.status = status;
    progress.phase = progress.phase || data.phase || options.phase || options.operation || 'working';
    progress.phase_label = progress.phase_label || options.phaseLabel || phaseName(progress.phase || '');
    progress.percent = progress.percent_complete !== undefined ? progress.percent_complete : progress.percent;
    progress.status_message = progress.status_message || progress.message || data.status_message || options.message || progress.phase_label;
    progress.message = progress.message || progress.status_message;
    progress.eta_seconds = Number(progress.eta_seconds || data.eta_seconds || 0);
    return { status: status, progress: progress };
  }
  function waitForAsyncJob(startResponse, options) {
    options = options || {};
    var jobId = startResponse.job_id || startResponse.task_id || options.jobId || '';
    var startedAt = options.startedAt || Date.now();
    var sseUrl = startResponse.sse_url || ('/sse?job_id=' + encodeURIComponent(jobId));
    var statusUrl = startResponse.status_url || ('/api/status?job_id=' + encodeURIComponent(jobId));
    var eventSource = null;
    var pollTimer = null;
    var settled = false;
    var polling = false;

    function cleanup() {
      settled = true;
      if (eventSource) { try { eventSource.close(); } catch (e) {} eventSource = null; }
      if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    }
    function publish(data) {
      var normalized = normalizeAsyncProgress(data, Object.assign({}, options, { jobId: jobId }));
      touchRuntimeStatus(startedAt, { phase: normalized.progress.phase, data: normalized.progress });
      if (typeof options.onProgress === 'function') options.onProgress(data, normalized.progress);
      if (isTerminalJobStatus(normalized.status)) {
        cleanup();
        if (normalized.status === 'failed') {
          var message = data.error || normalized.progress.error || normalized.progress.status_message || '任务失败';
          return { error: new Error(message), data: data };
        }
        return data;
      }
      return null;
    }
    function startPolling(message) {
      if (settled || polling) return;
      polling = true;
      if (message && Toast && Toast.warning) Toast.warning(message);
      pollTimer = setInterval(pollOnce, 1500);
      pollOnce();
    }
    async function pollOnce() {
      if (settled) return;
      try {
        var data = await Api.get(statusUrl, { timeout: 30000 });
        var terminal = publish(data);
        if (terminal && terminal.error && typeof options.reject === 'function') options.reject(terminal.error);
        else if (terminal && typeof options.resolve === 'function') options.resolve(terminal);
      } catch (e) {
        if (settled) return;
        cleanup();
        if (typeof options.reject === 'function') options.reject(e);
      }
    }

    return new Promise(function (resolve, reject) {
      options.resolve = resolve;
      options.reject = reject;
      if (!jobId) {
        reject(new Error('后台任务没有返回 job_id。'));
        return;
      }
      try {
        eventSource = new EventSource(sseUrl);
        eventSource.onmessage = function (event) {
          if (settled) return;
          try {
            var data = JSON.parse(event.data);
            var terminal = publish(data);
            if (terminal && terminal.error) reject(terminal.error);
            else if (terminal) resolve(terminal);
          } catch (e) {
            cleanup();
            reject(e);
          }
        };
        eventSource.onerror = function () {
          if (settled) return;
          if (eventSource) { try { eventSource.close(); } catch (e) {} eventSource = null; }
          startPolling('实时进度流暂不可用，已切换为状态轮询。');
        };
      } catch (e) {
        startPolling('实时进度流暂不可用，已切换为状态轮询。');
      }
    });
  }

  function renderRuntimeStatus() {
    var panel = $('runtimeStatusPanel');
    if (!panel) return;
    var kind = activeRuntimeKind();
    var active = Boolean(kind);
    panel.classList.toggle('hidden', !active);
    if (!active) return;

    var now = Date.now();
    var startedAt = Number(S.get('runtimeStatusStartedAt') || S.get('syncStartedAt') || S.get('checkStartedAt') || now);
    var updatedAt = Number(S.get('runtimeStatusUpdatedAt') || startedAt || now);
    var progress = runtimeProgressData(kind);
    var percent = runtimeProgressPercent(progress);
    var stale = now - updatedAt > 120000;
    var phase = (progress && (progress.phase_label || phaseName(progress.phase || ''))) || runtimeKindLabel(kind);
    var message = (progress && progress.message) || runtimeDefaultMessage(kind);
    var title = runtimeTitle(kind, progress);
    var hint = runtimeDynamicHint(kind, progress, now, updatedAt, stale);
    var progressTrack = panel.querySelector('.runtime-progress');
    var fill = $('runtimeProgressFill');

    panel.classList.toggle('is-warning', stale);
    if ($('runtimeStatusBadge')) $('runtimeStatusBadge').textContent = stale ? '等待中' : '运行中';
    if ($('runtimeStatusTitle')) $('runtimeStatusTitle').textContent = title;
    if ($('runtimeStatusMessage')) $('runtimeStatusMessage').textContent = message;
    if ($('runtimeStatusHint')) $('runtimeStatusHint').textContent = hint;
    if ($('runtimePhaseText')) $('runtimePhaseText').textContent = phase || '准备中';
    if ($('runtimePercentText')) $('runtimePercentText').textContent = percent === null ? '计算中' : Math.round(percent) + '%';
    if ($('runtimeCountText')) $('runtimeCountText').textContent = runtimeCountText(progress);
    if ($('runtimeUpdatedText')) $('runtimeUpdatedText').textContent = formatClock(updatedAt, now);
    if ($('runtimeElapsedText')) $('runtimeElapsedText').textContent = formatDuration(now - startedAt);
    if (progressTrack) {
      progressTrack.classList.toggle('is-indeterminate', percent === null);
      progressTrack.setAttribute('aria-valuenow', percent === null ? '0' : String(Math.round(percent)));
      progressTrack.setAttribute('aria-label', title);
    }
    if (fill) fill.style.width = percent === null ? '' : Math.round(percent) + '%';
  }

  function renderBusyControls() {
    var prodReason = operationBlockReason('production');
    var syncReason = operationBlockReason('sync');
    var checkReason = operationBlockReason('check');
    var submitReason = operationBlockReason('submit');
    setControlState('controlButton', Boolean(prodReason), prodReason);
    setControlState('workflowRunButton', Boolean(prodReason), prodReason);
    setControlState('syncButton', Boolean(syncReason), syncReason);
    setControlState('workflowSyncButton', Boolean(syncReason), syncReason);
    setControlState('sideSyncButton', Boolean(syncReason), syncReason);
    setControlState('connTestBtn', Boolean(S.get('connectionTestInFlight')), S.get('connectionTestInFlight') ? '连接测试正在进行。' : '');
    var syncRange = $('syncRange'); if (syncRange) syncRange.disabled = Boolean(syncReason);
    setControlState('checkButton', Boolean(checkReason) || Boolean(batchCheckJobId()), checkReason);
    setControlState('assistantGenerateButton', Boolean(prodReason), prodReason);
    setControlState('workflowCheckButton', Boolean(checkReason) || Boolean(batchCheckJobId()), checkReason || (batchCheckJobId() ? '达标检查正在进行。' : ''));
    setControlState('sideCheckButton', Boolean(checkReason) || Boolean(batchCheckJobId()), checkReason || (batchCheckJobId() ? '达标检查正在进行。' : ''));
    var submitBtn = $('submitSelectedButton');
    if (submitBtn) {
      var selectedCount = selectedSubmitCount();
      var sReason = submitReason || !selectedCount ? (selectedCount ? submitReason : '请先选择要提交的 Alpha') : '';
      submitBtn.disabled = Boolean(sReason);
      submitBtn.setAttribute('aria-disabled', Boolean(sReason));
      if (sReason) submitBtn.setAttribute('title', sReason); else submitBtn.removeAttribute('title');
    }
    var railSubmitBtn = $('workflowSubmitButton');
    if (railSubmitBtn) {
      var railSelectedCount = selectedSubmitCount();
      var railReason = submitReason || !railSelectedCount ? (railSelectedCount ? submitReason : '请先在达标或可提交视图选择 Alpha') : '';
      railSubmitBtn.disabled = Boolean(railReason);
      railSubmitBtn.setAttribute('aria-disabled', Boolean(railReason));
      if (railReason) railSubmitBtn.setAttribute('title', railReason); else railSubmitBtn.removeAttribute('title');
    }
    var sideSubmitBtn = $('sideSubmitButton');
    if (sideSubmitBtn) {
      var sideSelectedCount = selectedSubmitCount();
      var sideSubmitReason = submitReason || !sideSelectedCount ? (sideSelectedCount ? submitReason : '请先在达标或可提交视图选择 Alpha') : '';
      sideSubmitBtn.disabled = Boolean(sideSubmitReason);
      sideSubmitBtn.setAttribute('aria-disabled', Boolean(sideSubmitReason));
      if (sideSubmitReason) sideSubmitBtn.setAttribute('title', sideSubmitReason); else sideSubmitBtn.removeAttribute('title');
    }
    var autoSubmit = $('autoSubmitToggle'); if (autoSubmit) autoSubmit.disabled = Boolean(submitReason || batchCheckJobId() || submitInFlight());
    var guard = $('operationGuard');
    if (guard) { var msg = currentOperationText(); guard.textContent = msg; guard.classList.toggle('hidden', !msg); }
    var sideReason = $('sideTaskReason');
    if (sideReason) {
      var reasonText = currentOperationText() || (selectedSubmitCount() ? '已选择 ' + selectedSubmitCount() + ' 个 Alpha，可提交。' : '当前无冲突操作。');
      sideReason.textContent = reasonText;
      sideReason.classList.toggle('is-blocked', Boolean(currentOperationText()));
    }
    callbacks.syncStrategyPluginControls();
    callbacks.renderTaskRail();
    renderRuntimeStatus();
  }

  window.AppRuntime = {
    activeRuntimeKind: activeRuntimeKind,
    asyncOperationJobId: asyncOperationJobId,
    batchCheckJobId: batchCheckJobId,
    clearRuntimeStatus: clearRuntimeStatus,
    configure: configure,
    connectionStatusLabel: connectionStatusLabel,
    currentOperationText: currentOperationText,
    etaDeadline: etaDeadline,
    operationBlockReason: operationBlockReason,
    renderBusyControls: renderBusyControls,
    renderHeaderStatus: renderHeaderStatus,
    renderRuntimeStatus: renderRuntimeStatus,
    requestEtaSeconds: requestEtaSeconds,
    selectedSubmitCount: selectedSubmitCount,
    setControlState: setControlState,
    submitInFlight: submitInFlight,
    syncInFlight: syncInFlight,
    touchRuntimeStatus: touchRuntimeStatus,
    waitForAsyncJob: waitForAsyncJob,
    runtimeKindLabel: runtimeKindLabel,
  };
  window.operationBlockReason = operationBlockReason;
  window.renderRuntimeStatus = renderRuntimeStatus;
  window.renderBusyControls = renderBusyControls;
})();
