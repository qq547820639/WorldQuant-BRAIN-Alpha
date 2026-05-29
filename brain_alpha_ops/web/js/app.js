// brain_alpha_ops/web/js/app.js
// Application entry point: render dispatch, view state, and page-level actions.
// v4: Keyboard shortcuts, skeleton screens, workflow wizard, view transitions.
(function () {
  'use strict';
  var $ = window.Utils.$;
  var esc = window.Utils.escapeHtml;
  var escapeAttr = window.Utils.escapeAttr;
  var setSafeHtml = window.Utils.setSafeHtml;
  var phaseName = window.Utils.phaseName;
  var Api = window.ApiClient;
  var S = window.AppState;
  var Toast = window.Toast;
  var Spinner = window.Spinner || {};
  var VM = window.ViewModel;
  var Registry = window.ViewRegistry;
  var ViewRenderers = window.ViewRenderers;
  var ResultState = window.ResultState;
  var FormControls = window.FormControls;
  var StrategyPanel = window.StrategyPanel || {};
  var LoadingFeedback = window.LoadingFeedback || {};
  var candidateIdentity = VM.candidateIdentity;
  window.$ = $;
  var VIEW_ORDER = Registry.VIEW_ORDER;
  var VIEW_GROUPS = Registry.VIEW_GROUPS;
  var VIEW_TITLES = Registry.VIEW_TITLES;
  var VIEW_ICONS = Registry.VIEW_ICONS;
  var presets = {};
  function syncInFlight() { return Boolean(S.get('syncInFlight')); }
  function batchCheckJobId() { return S.get('batchCheckJobId') || ''; }
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
  function isSelectedSubmitId(id) { return selectedSubmitList().indexOf(id) !== -1; }
  function selectedSubmitIdSet() { return new Set(selectedSubmitList()); }
  function setSelectedSubmitIds(ids) { S.set('selectedSubmitIds', Array.from(ids || [])); }
  function setControlState(id, disabled, reason) {
    var el = $(id); if (!el) return;
    if (!el.dataset.defaultTitle) el.dataset.defaultTitle = el.getAttribute('title') || '';
    el.disabled = Boolean(disabled);
    el.setAttribute('aria-disabled', Boolean(disabled));
    if (reason) el.setAttribute('title', reason);
    else if (el.dataset.defaultTitle) el.setAttribute('title', el.dataset.defaultTitle);
    else el.removeAttribute('title');
  }
  function syncStrategyPluginControls() { if (StrategyPanel.syncPluginControls) StrategyPanel.syncPluginControls(); }
  window.syncStrategyPluginControls = syncStrategyPluginControls;
  function syncStartupState(snapshot) {
    snapshot = snapshot || {};
    if (snapshot.latest && snapshot.latest.result) renderResult(snapshot.latest.result);
    if (snapshot.config && snapshot.config.config) {
      S.set('config', snapshot.config.config);
      if (typeof window.renderStrategyPolicy === 'function') window.renderStrategyPolicy(snapshot.config.config);
      FormControls.applyConfig(snapshot.config.config);
      syncStrategyPluginControls();
    }
    if (snapshot.profile && snapshot.profile.profile) S.set('userProfile', snapshot.profile.profile);
    if (snapshot.presets && snapshot.presets.presets) presets = snapshot.presets.presets;
    if (snapshot.cloud && window.CloudSync && window.CloudSync.applyCloudSnapshotPayload) window.CloudSync.applyCloudSnapshotPayload(snapshot.cloud);
    if (snapshot.redline && S.set) S.set('redlineReport', snapshot.redline);
    if (snapshot.checkResults && snapshot.checkResults.check_results) S.set('checkResults', snapshot.checkResults.check_results);
    if (snapshot.research && snapshot.research.research_memory) S.set('currentResult.research_memory', snapshot.research.research_memory);
  }
  window.operationBlockReason = function (action) {
    var running = Boolean(S.get('isRunning'));
    if (S.get('connectionTestInFlight')) return '连接测试正在进行。';
    if (S.get('pageLoadInFlight')) return '页面数据正在加载。';
    switch (action) {
      case 'production': if (syncInFlight()) return '云端同步正在进行。'; if (batchCheckJobId()) return '达标检查正在进行。'; if (submitInFlight()) return '提交正在进行。'; return '';
      case 'sync': if (running) return '生产任务运行中。'; if (batchCheckJobId()) return '达标检查正在进行。'; if (submitInFlight()) return '提交正在进行。'; if (syncInFlight()) return '云端同步正在进行。'; return '';
      case 'check': if (running) return '生产任务运行中。'; if (syncInFlight()) return '云端同步正在进行。'; if (submitInFlight()) return '提交正在进行。'; if (batchCheckJobId()) return '达标检查正在进行。'; return '';
      case 'submit': if (running) return '生产任务运行中。'; if (syncInFlight()) return '云端同步正在进行。'; if (batchCheckJobId()) return '达标检查正在进行。'; if (submitInFlight()) return '提交正在进行。'; return '';
    }
    return '';
  };
  function currentOperationText() {
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
    var percent = Number(progress.percent);
    if (Number.isFinite(percent)) return Math.min(100, Math.max(0, percent));
    var scanned = Number(progress.scanned || progress.current || progress.done || 0);
    var total = Number(progress.total || 0);
    if (total > 0) return Math.min(100, Math.max(0, scanned / total * 100));
    return null;
  }
  function runtimeCountText(progress) {
    progress = progress || {};
    var scanned = numberText(progress.scanned || progress.current || progress.done);
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
    if (typeof window.renderRuntimeStatus === 'function') window.renderRuntimeStatus();
  }
  function clearRuntimeStatus() {
    S.setBatch({ runtimeStatusStartedAt: 0, runtimeStatusUpdatedAt: 0, liveProgress: {} });
    if (typeof window.renderRuntimeStatus === 'function') window.renderRuntimeStatus();
  }
  window.renderRuntimeStatus = function () {
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
  };
  window.renderBusyControls = function () {
    var prodReason = window.operationBlockReason('production');
    var syncReason = window.operationBlockReason('sync');
    var checkReason = window.operationBlockReason('check');
    var submitReason = window.operationBlockReason('submit');
    setControlState('controlButton', Boolean(prodReason), prodReason);
    setControlState('workflowRunButton', Boolean(prodReason), prodReason);
    setControlState('syncButton', Boolean(syncReason), syncReason);
    setControlState('workflowSyncButton', Boolean(syncReason), syncReason);
    setControlState('sideSyncButton', Boolean(syncReason), syncReason);
    setControlState('connTestBtn', Boolean(S.get('connectionTestInFlight')), S.get('connectionTestInFlight') ? '连接测试正在进行。' : '');
    var syncRange = $('syncRange'); if (syncRange) syncRange.disabled = Boolean(syncReason);
    setControlState('checkButton', Boolean(checkReason) || Boolean(batchCheckJobId()), checkReason);
    setControlState('workflowCheckButton', Boolean(checkReason) || Boolean(batchCheckJobId()), checkReason || (batchCheckJobId() ? '达标检查正在进行。' : ''));
    setControlState('sideCheckButton', Boolean(checkReason) || Boolean(batchCheckJobId()), checkReason || (batchCheckJobId() ? '达标检查正在进行。' : ''));
    var submitBtn = $('submitSelectedButton');
    if (submitBtn) { var selectedCount = selectedSubmitCount(); var sReason = submitReason || !selectedCount ? (selectedCount ? submitReason : '请先选择要提交的 Alpha') : ''; submitBtn.disabled = Boolean(sReason); if (sReason) submitBtn.setAttribute('title', sReason); }
    var railSubmitBtn = $('workflowSubmitButton');
    if (railSubmitBtn) { var railSelectedCount = selectedSubmitCount(); var railReason = submitReason || !railSelectedCount ? (railSelectedCount ? submitReason : '请先在达标或可提交视图选择 Alpha') : ''; railSubmitBtn.disabled = Boolean(railReason); railSubmitBtn.setAttribute('aria-disabled', Boolean(railReason)); if (railReason) railSubmitBtn.setAttribute('title', railReason); else railSubmitBtn.removeAttribute('title'); }
    var sideSubmitBtn = $('sideSubmitButton');
    if (sideSubmitBtn) { var sideSelectedCount = selectedSubmitCount(); var sideSubmitReason = submitReason || !sideSelectedCount ? (sideSelectedCount ? submitReason : '请先在达标或可提交视图选择 Alpha') : ''; sideSubmitBtn.disabled = Boolean(sideSubmitReason); sideSubmitBtn.setAttribute('aria-disabled', Boolean(sideSubmitReason)); if (sideSubmitReason) sideSubmitBtn.setAttribute('title', sideSubmitReason); else sideSubmitBtn.removeAttribute('title'); }
    var autoSubmit = $('autoSubmitToggle'); if (autoSubmit) autoSubmit.disabled = Boolean(submitReason || batchCheckJobId() || submitInFlight());
    var guard = $('operationGuard');
    if (guard) { var msg = currentOperationText(); guard.textContent = msg; guard.classList.toggle('hidden', !msg); }
    var sideReason = $('sideTaskReason');
    if (sideReason) {
      var reasonText = currentOperationText() || (selectedSubmitCount() ? '已选择 ' + selectedSubmitCount() + ' 个 Alpha，可提交。' : '当前无冲突操作。');
      sideReason.textContent = reasonText;
      sideReason.classList.toggle('is-blocked', Boolean(currentOperationText()));
    }
    syncStrategyPluginControls();
    renderTaskRail();
    window.renderRuntimeStatus();
  };
  function currentSummary() { return S.get('currentResult.summary') || {}; }
  function currentCandidates() { return S.get('currentResult.candidates') || []; }
  function currentBacktests() { return S.get('currentResult.backtests') || []; }
  function currentCloudAlphas() { return S.get('currentResult.cloud_alphas') || []; }
  function currentLifecycle() { return S.get('currentResult.lifecycle_records') || []; }
  function currentResearchMemory() { return S.get('currentResult.research_memory') || {}; }
  function currentResearchKnowledge() { return S.get('currentResult.research_knowledge') || {}; }
  function currentResearchObservability() { return S.get('currentResult.research_observability') || {}; }
  function currentPromptRuns() { return S.get('currentResult.prompt_runs') || {}; }
  function currentSqliteIndexes() { return S.get('currentResult.sqlite_indexes') || {}; }
  function currentRobustnessSnapshot() { return S.get('currentResult.robustness_snapshot') || {}; }
  function checkResults() { return S.get('checkResults') || {}; }
  window.toggleTheme = function () {
    var html = document.documentElement;
    var isDark = html.getAttribute('data-theme') === 'dark';
    var next = isDark ? '' : 'dark';
    html.setAttribute('data-theme', next);
    var light = document.querySelector('.theme-icon-light');
    var dark = document.querySelector('.theme-icon-dark');
    if (light) light.classList.toggle('hidden', !isDark);
    if (dark) dark.classList.toggle('hidden', isDark);
    try { localStorage.setItem('brain-alpha-ops-theme', isDark ? 'light' : 'dark'); } catch (e) {}
  };
  (function initTheme() {
    try {
      var saved = localStorage.getItem('brain-alpha-ops-theme');
      if (saved === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
        var li = document.querySelector('.theme-icon-light');
        var di = document.querySelector('.theme-icon-dark');
        if (li) li.classList.add('hidden');
        if (di) di.classList.remove('hidden');
      }
    } catch (e) {}
  })();
  function renderViewTabs() {
    var container = $('viewTabs');
    if (!container) return;
    var currentView = activeView();
    setSafeHtml(container, VIEW_GROUPS.map(function (group) {
      return '<div class="view-tab-group" aria-label="' + esc(group.label) + '">' +
        '<div class="view-tab-group-label"><span>' + esc(group.label) + '</span><small>' + esc(group.hint) + '</small></div>' +
        '<div class="view-tab-row">' + group.views.map(function (view) { return renderTab(view, currentView); }).join('') + '</div>' +
        '</div>';
    }).join(''));
  }
  function renderTab(view, currentView) {
    var title = VIEW_TITLES[view] || view;
    var icon = VIEW_ICONS[view] || '--';
    var isActive = view === currentView;
    var count = S.viewCount(view);
    var badgeHtml = count > 0 ? '<span class="tab-badge">' + (count > 99 ? '99+' : count) + '</span>' : '';
    return '<button type="button" class="view-tab' + (isActive ? ' is-active' : '') + '"' +
      ' data-action="switch-view" data-view="' + escapeAttr(view) + '"' +
      ' aria-pressed="' + isActive + '"' +
      ' title="' + esc(title) + (count > 0 ? ' (' + count + ')' : '') + '"' +
      '><span class="tab-marker" aria-hidden="true">' + esc(icon) + '</span>' +
      '<span class="view-tab-label">' + esc(title) + '</span>' + badgeHtml + '</button>';
  }
  function installViewTabDelegates() {
    var container = $('viewTabs');
    if (!container || container.dataset.delegatedActions === '1') return;
    container.dataset.delegatedActions = '1';
    container.addEventListener('click', function (event) {
      var button = findActionElement(event.target, container);
      if (!button || button.getAttribute('data-action') !== 'switch-view') return;
      if (event.preventDefault) event.preventDefault();
      if (event.stopPropagation) event.stopPropagation();
      window.switchView(button.getAttribute('data-view') || 'candidates');
    });
  }
  window.switchView = function (view) {
    if (VIEW_ORDER.indexOf(view) === -1) view = 'candidates';
    S.set('activeView', view);
    renderViewTabs();
    _renderCurrentView();
    if (typeof window.renderInsight === 'function') window.renderInsight();
    updatePanelHeader();
    // Show/hide action bar based on view
    updateActionBarVisibility(view);
    renderTaskRail();
  };
  function activeView() { return S.get('activeView') || 'candidates'; }
  function setWorkflowText(id, value) {
    var el = $(id);
    if (el) el.textContent = String(value);
  }
  function workflowStepViews(stepId) {
    if (stepId === 'workflowStepProduce') return ['candidates', 'pending_backtest', 'running_backtest', 'backtest_rework'];
    if (stepId === 'workflowStepCheck') return ['passed'];
    if (stepId === 'workflowStepSubmit') return ['submittable', 'submitted', 'failed'];
    if (stepId === 'workflowStepCloud') return ['cloud', 'lifecycle'];
    return [];
  }
  function updateWorkflowStep(stepId, currentView) {
    var el = $(stepId);
    if (!el) return;
    var active = workflowStepViews(stepId).indexOf(currentView) !== -1;
    el.classList.toggle('is-active', active);
    if (active) el.setAttribute('aria-current', 'step');
    else el.removeAttribute('aria-current');
  }
  function workflowStatusText() {
    var candidateCount = S.viewCount('candidates');
    var passedCount = S.viewCount('passed');
    var submittableCount = S.viewCount('submittable');
    var selectedCount = selectedSubmitCount();
    if (syncInFlight()) return '云端同步进行中，正在刷新官方 Alpha 快照。';
    if (batchCheckJobId()) return '达标检查进行中，通过后会进入可提交队列。';
    if (submitInFlight()) return '提交处理中，请等待官方结果返回。';
    if (S.get('isRunning')) return '生产搜索运行中，候选、回测和评分会自动更新。';
    if (selectedCount) return '已选择 ' + selectedCount + ' 个 Alpha，可从这里批量提交。';
    if (submittableCount) return '已有 ' + submittableCount + ' 个 Alpha 可提交，先复核再提交。';
    if (passedCount) return '已有 ' + passedCount + ' 个达标 Alpha，下一步执行官方检查。';
    if (candidateCount) return '候选池已有 ' + candidateCount + ' 条记录，可查看详情或继续生产。';
    return '先连接账号，再启动生产搜索或同步云端数据。';
  }
  function renderTaskRail() {
    setWorkflowText('workflowCandidateCount', S.viewCount('candidates'));
    setWorkflowText('workflowPassedCount', S.viewCount('passed'));
    setWorkflowText('workflowSubmittableCount', S.viewCount('submittable'));
    setWorkflowText('workflowCloudCount', S.viewCount('cloud'));
    var currentView = activeView();
    ['workflowStepProduce', 'workflowStepCheck', 'workflowStepSubmit', 'workflowStepCloud'].forEach(function (id) {
      updateWorkflowStep(id, currentView);
    });
    var statusEl = $('workflowStatus');
    if (statusEl) {
      statusEl.textContent = workflowStatusText();
      statusEl.classList.toggle('is-busy', Boolean(syncInFlight() || batchCheckJobId() || submitInFlight() || S.get('isRunning')));
    }
    var runBtn = $('workflowRunButton');
    if (runBtn) {
      var running = Boolean(S.get('isRunning'));
      runBtn.textContent = running ? '停止生产' : '开始生产搜索';
      runBtn.classList.toggle('btn-danger', running);
      runBtn.classList.toggle('btn-primary', !running);
      runBtn.classList.toggle('is-stopping', running);
    }
    var runtimeStopBtn = $('runtimeStopButton');
    if (runtimeStopBtn) {
      var kind = activeRuntimeKind();
      var canStopProduction = kind === 'production' && Boolean(S.get('isRunning'));
      var canStopSync = kind === 'sync' && Boolean(S.get('syncJobId') || S.get('syncRecoverable'));
      runtimeStopBtn.disabled = !(canStopProduction || canStopSync);
      runtimeStopBtn.setAttribute('aria-disabled', !(canStopProduction || canStopSync));
      runtimeStopBtn.setAttribute('data-action', canStopSync ? 'cancel-sync-cloud' : 'toggle-run');
      runtimeStopBtn.textContent = canStopSync ? '停止同步' : (canStopProduction ? '停止生产' : '等待完成');
      if (canStopSync) runtimeStopBtn.setAttribute('title', '停止当前云端同步，随后可调整范围并重试。');
      else if (!canStopProduction) runtimeStopBtn.setAttribute('title', '当前任务会自动结束，暂不支持手动停止。');
      else runtimeStopBtn.removeAttribute('title');
    }
    var retryBtn = $('runtimeRetryButton');
    if (retryBtn) {
      var showRetry = activeRuntimeKind() === 'sync' && Boolean(S.get('syncRecoverable'));
      retryBtn.classList.toggle('hidden', !showRetry);
      retryBtn.disabled = !showRetry;
      retryBtn.setAttribute('aria-disabled', !showRetry);
    }
    var logBtn = $('runtimeLogButton');
    if (logBtn) {
      var showLog = activeRuntimeKind() === 'sync';
      logBtn.classList.toggle('hidden', !showLog);
      logBtn.disabled = !showLog;
      logBtn.setAttribute('aria-disabled', !showLog);
    }
  }
  function updateActionBarVisibility(view) {
    var bar = $('moduleActions');
    if (!bar) return;
    var showFor = ['passed', 'submittable', 'candidates'];
    bar.classList.toggle('hidden', showFor.indexOf(view) === -1);
    // Update title
    var titleEl = $('moduleActionTitle');
    if (titleEl) {
      titleEl.textContent = view === 'submittable' ? '提交操作' : view === 'passed' ? '达标检查' : '批量操作';
    }
    var hintEl = $('moduleActionHint');
    if (hintEl) {
      hintEl.textContent = view === 'submittable' ? '勾选已通过检查的 Alpha 后提交。' : view === 'passed' ? '先跑官方预提交检查，再进入可提交列表。' : '查看候选详情，必要时切换到达标视图执行检查。';
    }
    // Show/hide specific buttons
    var checkBtn = $('checkButton');
    var submitBtn = $('submitSelectedButton');
    var checkMode = $('checkMode');
    var autoSubmit = $('autoSubmitToggle');
    var autoSubmitWrap = autoSubmit && autoSubmit.closest ? autoSubmit.closest('.toggle') : null;
    if (checkBtn) checkBtn.classList.toggle('hidden', view !== 'passed');
    if (checkMode) checkMode.classList.toggle('hidden', view !== 'passed');
    if (autoSubmitWrap) autoSubmitWrap.classList.toggle('hidden', view !== 'passed');
    if (submitBtn) submitBtn.classList.toggle('hidden', view !== 'submittable' && view !== 'passed');
  }
  window.setResultDisplayMode = function (mode) {
    var tableBtn = $('tableModeBtn'), chartBtn = $('chartModeBtn');
    var chartsPanel = $('chartsPanel');
    if (tableBtn) { tableBtn.classList.toggle('is-active', mode === 'table'); tableBtn.setAttribute('aria-pressed', mode === 'table'); }
    if (chartBtn) { chartBtn.classList.toggle('is-active', mode === 'charts'); chartBtn.setAttribute('aria-pressed', mode === 'charts'); }
    if (chartsPanel) chartsPanel.classList.toggle('visible', mode === 'charts');
    if (mode === 'charts' && typeof window.renderCharts === 'function') window.renderCharts();
    var toggle = $('displayModeToggle'); if (toggle) toggle.classList.toggle('hidden', false);
  };
  function viewRendererOptions() {
    return {
      actionButton: actionButton,
      activeView: activeView,
      isFreshPassedCheck: S.isFreshPassedCheck,
      isSelectedSubmitId: isSelectedSubmitId,
      lastSubmitResults: S.get('lastSubmitResults') || [],
      submitInFlight: submitInFlight,
    };
  }
  function viewDataSources() {
    return {
      candidates: currentCandidates(),
      checks: checkResults(),
      cloud: currentCloudAlphas(),
      isFreshPassedCheck: S.isFreshPassedCheck,
      lastSubmitResults: S.get('lastSubmitResults') || [],
      lifecycle: currentLifecycle(),
      promptRuns: currentPromptRuns(),
      researchKnowledge: currentResearchKnowledge(),
      researchMemory: currentResearchMemory(),
      researchObservability: currentResearchObservability(),
      robustnessSnapshot: currentRobustnessSnapshot(),
      sqliteIndexes: currentSqliteIndexes(),
    };
  }
  function liveCloudSyncProgress() {
    var live = S.get('liveProgress') || {};
    var progress = live.data || {};
    return ((progress.data || {}).cloud_sync || progress.cloud_sync || {});
  }
  var resultTable = window.ResultTableView.create({
    activeView: activeView,
    applySearchFilter: applySearchFilter,
    getColumnsForView: getColumnsForView,
    getMobileColumns: getMobileColumns,
    getRowsForView: getRowsForView,
    isSelectedSubmitId: isSelectedSubmitId,
    renderMobileActions: renderMobileActions,
    state: S,
  });
  window.ResultTable = resultTable;
  function updatePanelHeader() { resultTable.updatePanelHeader(); }
  window.renderStrategyPolicy = function (config) { if (StrategyPanel.renderPolicy) StrategyPanel.renderPolicy(config); };
  function renderResult(result) {
    S.setBatch(ResultState.buildResultBatch(result, {
      currentBacktests: currentBacktests(),
      currentCandidates: currentCandidates(),
      currentCloudAlphas: currentCloudAlphas(),
      currentLifecycle: currentLifecycle(),
      currentPendingBacktestCandidates: S.get('currentResult.pending_backtest_candidates') || [],
      currentSummary: currentSummary(),
      liveCloudSyncProgress: liveCloudSyncProgress,
    }));
    renderAll();
  }
  function renderJobSnapshot(job) {
    renderResult(ResultState.jobToResult(job));
  }
  function renderAll() {
    renderViewTabs();
    if (typeof window.renderInsight === 'function') window.renderInsight();
    if (typeof window.renderOpsMonitor === 'function') window.renderOpsMonitor();
    if (typeof window.renderBacktests === 'function') window.renderBacktests(currentBacktests());
    if (typeof window.renderCharts === 'function') window.renderCharts();
    _renderCurrentView();
    window.renderBusyControls();
    updatePanelHeader();
    renderTaskRail();
  }
  var _renderCurrentView = function () { resultTable.renderCurrentView(); };
  window.renderCurrentView = _renderCurrentView;
  function actionButton(action, label, row, className, options) {
    return resultTable.actionButton(action, label, row, className, options);
  }
  function findActionElement(target, boundary) {
    while (target && target !== boundary && target.getAttribute) {
      if (target.getAttribute('data-action')) return target;
      target = target.parentElement;
    }
    return boundary && boundary.getAttribute && boundary.getAttribute('data-action') ? boundary : null;
  }
  function handleDelegatedAction(event) {
    var container = event.currentTarget || event.delegateTarget || this || null;
    var el = findActionElement(event.target, container);
    if (!el) return;
    var action = el.getAttribute('data-action') || '';
    if (!action) return;
    if (event.preventDefault) event.preventDefault();
    if (event.stopPropagation) event.stopPropagation();
    var id = el.getAttribute('data-id') || '';
    if (action === 'open-row') {
      window.handleRowClick(el);
    } else if (action === 'submit-single') {
      window.submitSingleCandidate(id);
    } else if (action === 'toggle-select') {
      window.toggleSelectCandidate(id, el);
    }
  }
  function installResultDelegates() {
    ['candidateRows', 'mobileCardList'].forEach(function (id) {
      var el = $(id);
      if (!el || el.dataset.delegatedActions === '1') return;
      el.dataset.delegatedActions = '1';
      el.addEventListener('click', handleDelegatedAction);
      el.addEventListener('keydown', function (event) {
        if (event.key === 'Enter' || event.key === ' ') handleDelegatedAction(event);
      });
    });
  }
  function isNativeInteractive(el) {
    var tag = String((el && el.tagName) || '').toUpperCase();
    return tag === 'BUTTON' || tag === 'A' || tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA';
  }
  function hasAncestorClass(target, className, boundary) {
    while (target && target !== boundary && target.getAttribute) {
      if (target.classList && target.classList.contains(className)) return true;
      target = target.parentElement;
    }
    return false;
  }
  function validatePageAction(action, el) {
    if (!action || !el) return false;
    if (el.disabled || el.getAttribute('aria-disabled') === 'true') {
      if (Toast && Toast.warning) Toast.warning(el.getAttribute('title') || '当前操作不可用，请等待正在执行的任务完成。');
      return false;
    }
    var blockMap = {
      'toggle-run': 'production',
      'sync-cloud': 'sync',
      'check-batch': 'check',
      'submit-selected': 'submit',
      'assistant-generate-candidates': 'production',
    };
    var blockAction = blockMap[action] || '';
    if (blockAction && typeof window.operationBlockReason === 'function') {
      var reason = window.operationBlockReason(blockAction);
      if (reason) { if (Toast && Toast.warning) Toast.warning(reason); return false; }
    }
    if (action === 'switch-view' && VIEW_ORDER.indexOf(el.getAttribute('data-view') || '') === -1) {
      if (Toast && Toast.warning) Toast.warning('视图参数无效。');
      return false;
    }
    if (action === 'set-result-display-mode' && ['table', 'charts'].indexOf(el.getAttribute('data-mode') || '') === -1) {
      if (Toast && Toast.warning) Toast.warning('展示模式参数无效。');
      return false;
    }
    if ((action === 'toggle-sidebar-section' || action === 'toggle-collapsible') && !$(el.getAttribute('data-target') || '')) {
      if (Toast && Toast.warning) Toast.warning('目标区域不存在，请刷新页面后重试。');
      return false;
    }
    if (action === 'submit-selected' && selectedSubmitCount() === 0) {
      if (Toast && Toast.warning) Toast.warning('请先选择要提交的 Alpha。');
      return false;
    }
    return true;
  }
  function invokeWindowAction(name, args) {
    var fn = window[name];
    if (typeof fn !== 'function') {
      if (Toast && Toast.warning) Toast.warning('Action is not available in this build.');
      return;
    }
    try {
      var result = fn.apply(window, args || []);
      if (result && typeof result.catch === 'function') {
        result.catch(function (err) { if (Toast && Toast.error) Toast.error((err && err.message) || String(err)); });
      }
    } catch (err) {
      if (Toast && Toast.error) Toast.error((err && err.message) || String(err));
    }
  }
  function handlePageAction(event) {
    var body = document.body;
    if (!body) return;
    var el = findActionElement(event.target, body);
    if (!el) return;
    var action = el.getAttribute('data-action') || '';
    if (!action) return;
    if (el.id === 'detailModal' && hasAncestorClass(event.target, 'modal-panel', el)) return;
    if (el.id === 'confirmOverlay' && hasAncestorClass(event.target, 'confirm-dialog', el)) return;
    if (!validatePageAction(action, el)) {
      if (event.preventDefault) event.preventDefault();
      return;
    }
    switch (action) {
      case 'toggle-theme':
        invokeWindowAction('toggleTheme');
        break;
      case 'shutdown-app':
        invokeWindowAction('shutdownApp');
        break;
      case 'toggle-run':
        invokeWindowAction('toggleRun');
        break;
      case 'scroll-main': {
        var main = $('mainContent');
        if (main && typeof main.scrollIntoView === 'function') main.scrollIntoView({ behavior: 'smooth', block: 'start' });
        break;
      }
      case 'switch-view':
        invokeWindowAction('switchView', [el.getAttribute('data-view') || 'candidates']);
        break;
      case 'toggle-sidebar-section':
        invokeWindowAction('toggleSidebarSection', [el.getAttribute('data-target') || '']);
        break;
      case 'toggle-collapsible': {
        var target = $(el.getAttribute('data-target') || '');
        if (target) target.classList.toggle('is-closed');
        break;
      }
      case 'test-connection':
        invokeWindowAction('testConnection');
        break;
      case 'sync-cloud':
        invokeWindowAction('syncCloud');
        break;
      case 'cancel-sync-cloud':
        invokeWindowAction('cancelSyncCloud');
        break;
      case 'retry-sync-cloud':
        invokeWindowAction('retrySyncCloud');
        break;
      case 'set-result-display-mode':
        invokeWindowAction('setResultDisplayMode', [el.getAttribute('data-mode') || 'table']);
        break;
      case 'clear-search': {
        var search = $('tableSearch');
        if (search) search.value = '';
        _renderCurrentView();
        break;
      }
      case 'sort-table':
        if (window.ResultTable && typeof window.ResultTable.toggleSort === 'function') {
          window.ResultTable.toggleSort(el.getAttribute('data-sort-key') || '');
        }
        break;
      case 'check-batch':
        invokeWindowAction('checkBatch', [(($('checkMode') || {}).value) || 'quick']);
        break;
      case 'submit-selected':
        invokeWindowAction('submitSelectedCandidates');
        break;
      case 'assistant-use-draft':
        invokeWindowAction('useOfflineAssistantDraft');
        break;
      case 'assistant-save-draft':
        invokeWindowAction('saveOfflineAssistantDraftGuidance');
        break;
      case 'assistant-use-latest':
        invokeWindowAction('useLatestAssistantGuidance');
        break;
      case 'assistant-preview-guidance':
        invokeWindowAction('previewAssistantGuidance');
        break;
      case 'assistant-save-guidance':
        invokeWindowAction('saveAssistantGuidance');
        break;
      case 'assistant-generate-candidates':
        invokeWindowAction('generateAssistantCandidates');
        break;
      case 'retry-all-failed-submit':
        invokeWindowAction('retryAllFailedSubmit');
        break;
      case 'clear-submit-failure-panel':
        invokeWindowAction('clearSubmitFailurePanel');
        break;
      case 'close-detail-modal':
        invokeWindowAction('closeDetailModal');
        break;
      case 'hide-confirm':
        invokeWindowAction('hideConfirm');
        break;
      default:
        return;
    }
    if (event.preventDefault) event.preventDefault();
  }
  function handlePageKeydown(event) {
    if (event.key !== 'Enter' && event.key !== ' ' && event.key !== 'Spacebar') return;
    var el = findActionElement(event.target, document.body);
    if (!el || isNativeInteractive(el)) return;
    handlePageAction(event);
  }
  function handlePageChange(event) {
    var target = event.target;
    if (!target || !target.getAttribute) return;
    switch (target.getAttribute('data-change-action') || '') {
      case 'apply-preset':
        invokeWindowAction('applyPreset');
        break;
      case 'handle-auto-submit-toggle':
        invokeWindowAction('handleAutoSubmitToggle');
        break;
      case 'toggle-strategy-plugins':
        syncStrategyPluginControls();
        break;
    }
  }
  function handlePageInput(event) {
    var target = event.target;
    if (!target || !target.getAttribute) return;
    if (target.getAttribute('data-input-action') === 'render-current-view') _renderCurrentView();
  }
  function installStaticActionHandlers() {
    if (!document.body || document.body.dataset.staticActions === '1') return;
    document.body.dataset.staticActions = '1';
    document.addEventListener('click', handlePageAction);
    document.addEventListener('keydown', handlePageKeydown);
    document.addEventListener('change', handlePageChange);
    document.addEventListener('input', handlePageInput);
  }
  window.handleRowClick = function (el) {
    var kind = el.getAttribute('data-kind') || '';
    var id = el.getAttribute('data-id') || '';
    var view = activeView();
    if (view === 'cloud') { if (typeof window.viewCloudDetail === 'function') window.viewCloudDetail(el); return; }
    if (view === 'lifecycle') { if (typeof window.viewLifecycleDetail === 'function') window.viewLifecycleDetail(el); return; }
    if (kind === 'check' || view === 'submittable') { if (typeof window.viewCheckDetail === 'function') window.viewCheckDetail({ alpha_id: id }); return; }
    if (typeof window.viewCandidateDetail === 'function') {
      var cached = S.getCached(kind, id);
      window.viewCandidateDetail(cached ? cached.raw || cached : { alpha_id: id });
    }
  };
  function getRowsForView(view) {
    return ViewRenderers.getRowsForView(view, viewDataSources());
  }
  function applySearchFilter(rows) {
    var query = ($('tableSearch') || {}).value || '';
    ViewRenderers.applySearchFilter(rows, query);
  }
  function getColumnsForView(view) {
    return ViewRenderers.getColumnsForView(view, viewRendererOptions());
  }
  function getMobileColumns(view) {
    return ViewRenderers.getMobileColumns(view, viewRendererOptions());
  }
  function renderMobileActions(row, view) {
    return ViewRenderers.renderMobileActions(row, view, viewRendererOptions());
  }
  window.toggleSelectCandidate = function (id, el) {
    var selected = selectedSubmitIdSet();
    if (selected.has(id)) { selected.delete(id); if (el) el.textContent = '选择'; }
    else { selected.add(id); if (el) el.textContent = '已选'; }
    setSelectedSubmitIds(selected);
    _renderCurrentView();
  };
  window.submitSelectedCandidates = async function () {
    if (selectedSubmitCount() === 0) { Toast.warning('请先选择要提交的 Alpha。'); return; }
    var confirmed = await window.Modal.confirmAction('确认提交 ' + selectedSubmitCount() + ' 个 Alpha？', '确认提交', '取消');
    if (!confirmed) return;
    try {
      var ids = selectedSubmitList();
      var submitStarted = Date.now();
      var submitEta = requestEtaSeconds(ids.length, 3, 8, 45);
      S.setBatch({
        submitInFlight: true,
        runtimeStatusStartedAt: submitStarted,
        runtimeStatusUpdatedAt: submitStarted,
        liveProgress: {
          phase: 'submit',
          data: {
            phase: 'submit',
            phase_label: '提交处理',
            message: '正在提交 ' + ids.length + ' 个 Alpha，请等待官方返回结果。',
            scanned: 0,
            total: ids.length,
            percent: 15,
            eta_seconds: submitEta,
            eta_deadline_at_ms: etaDeadline(submitStarted, submitEta),
            updated_at_ms: submitStarted,
          },
        },
      });
      var payload = Object.assign(window.collectPayload ? window.collectPayload() : {}, { alpha_ids: ids });
      var resp = await Api.post('/api/submit_batch', payload);
      if (resp.ok) {
        touchRuntimeStatus(submitStarted, {
          phase: 'submit',
          data: {
            phase: 'submit',
            phase_label: '提交处理',
            message: '提交已返回，正在刷新检查结果。',
            scanned: ids.length,
            total: ids.length,
            percent: 95,
            eta_seconds: 3,
            eta_deadline_at_ms: etaDeadline(Date.now(), 3),
            updated_at_ms: Date.now(),
          },
        });
        Toast.success('提交成功：' + (resp.submitted || ids.length) + ' 个 Alpha');
        setSelectedSubmitIds([]);
        if (typeof window.loadCheckResults === 'function') await window.loadCheckResults();
      }
    } catch (e) { Toast.error('提交失败：' + e.message); }
    finally { S.set('submitInFlight', false); clearRuntimeStatus(); _renderCurrentView(); window.renderBusyControls(); }
  };
  window.submitSingleCandidate = async function (alphaId) {
    var confirmed = await window.Modal.confirmAction('确认提交 Alpha ' + alphaId + '？', '提交', '取消');
    if (!confirmed) return;
    try {
      var submitStarted = Date.now();
      var submitEta = requestEtaSeconds(1, 3, 8, 30);
      S.setBatch({
        submitInFlight: true,
        runtimeStatusStartedAt: submitStarted,
        runtimeStatusUpdatedAt: submitStarted,
        liveProgress: {
          phase: 'submit',
          data: {
            phase: 'submit',
            phase_label: '提交处理',
            message: '正在提交 Alpha ' + alphaId + '，请等待官方返回结果。',
            scanned: 0,
            total: 1,
            percent: 20,
            eta_seconds: submitEta,
            eta_deadline_at_ms: etaDeadline(submitStarted, submitEta),
            updated_at_ms: submitStarted,
          },
        },
      });
      var payload = Object.assign(window.collectPayload ? window.collectPayload() : {}, { alpha_id: alphaId });
      var resp = await Api.post('/api/submit', payload);
      if (resp.ok) Toast.success('提交成功：' + alphaId);
    } catch (e) { Toast.error('提交失败：' + e.message); }
    finally { S.set('submitInFlight', false); clearRuntimeStatus(); _renderCurrentView(); window.renderBusyControls(); }
  };
  if (typeof window.syncCloud !== 'function') {
    window.syncCloud = function () {
      if (window.CloudSync && typeof window.CloudSync.syncCloud === 'function') return window.CloudSync.syncCloud();
      if (Toast && Toast.warning) Toast.warning('云端同步模块尚未加载，请刷新页面后重试。');
    };
  }
  window.checkBatch = async function (mode) {
    if (batchCheckJobId()) return;
    var reason = window.operationBlockReason('check');
    if (reason) { Toast.warning(reason); return; }
    var passed = currentCandidates().filter(function (c) { return c.lifecycle_status === 'submission_ready' || ((c.gate || {}).submission_ready); });
    if (!passed.length) { Toast.warning('暂无达标 Alpha 可检查。'); return; }
    var checkStarted = Date.now();
    S.setBatch({ batchCheckJobId: 'check_' + checkStarted, checkStartedAt: checkStarted, runtimeStatusStartedAt: checkStarted, runtimeStatusUpdatedAt: checkStarted });
    renderBusyControls();
    try {
      var alphaIds = (mode === 'all' ? passed : passed.slice(0, 10)).map(function (c) { return c.alpha_id || candidateIdentity(c); });
      var checkEta = requestEtaSeconds(alphaIds.length, 4, 10, 60);
      touchRuntimeStatus(checkStarted, {
        phase: 'official_pre_submit_check',
        data: {
          phase: 'official_pre_submit_check',
          phase_label: '官方预提交检查',
          message: '正在检查 ' + alphaIds.length + ' 个 Alpha。',
          scanned: 0,
          total: alphaIds.length,
          percent: 0,
          eta_seconds: checkEta,
          eta_deadline_at_ms: etaDeadline(checkStarted, checkEta),
          updated_at_ms: checkStarted,
        },
      });
      var payload = Object.assign(window.collectPayload ? window.collectPayload() : {}, { alpha_ids: alphaIds });
      var resp = await Api.post('/api/check_batch', payload);
      if (resp.ok && resp.check_results) {
        var checks = S.get('checkResults') || {};
        Object.assign(checks, resp.check_results);
        S.set('checkResults', checks);
        var passedCount = Object.values(resp.check_results).filter(function (c) { return c.passed; }).length;
        touchRuntimeStatus(checkStarted, {
          phase: 'official_pre_submit_check',
          data: {
            phase: 'official_pre_submit_check',
            phase_label: '官方预提交检查',
            message: '检查完成：' + passedCount + ' 通过 / ' + alphaIds.length + ' 总数。',
            scanned: alphaIds.length,
            total: alphaIds.length,
            percent: 100,
          },
        });
        Toast.success('检查完成：' + passedCount + ' 通过 / ' + alphaIds.length + ' 总数');
        if (($('autoSubmitToggle') || {}).checked && passedCount > 0) {
          var passedIds = Object.entries(resp.check_results).filter(function (e) { return e[1].passed; }).map(function (e) { return e[0]; });
          try {
            var autoSubmitEta = requestEtaSeconds(passedIds.length, 3, 8, 45);
            touchRuntimeStatus(checkStarted, {
              phase: 'auto_submit',
              data: {
                phase: 'auto_submit',
                phase_label: '自动提交',
                message: '检查通过后正在自动提交 ' + passedIds.length + ' 个 Alpha。',
                scanned: 0,
                total: passedIds.length,
                percent: 80,
                eta_seconds: autoSubmitEta,
                eta_deadline_at_ms: etaDeadline(Date.now(), autoSubmitEta),
                updated_at_ms: Date.now(),
              },
            });
            var submitPayload = Object.assign(window.collectPayload ? window.collectPayload() : {}, { alpha_ids: passedIds });
            await Api.post('/api/submit_batch', submitPayload);
            touchRuntimeStatus(checkStarted, {
              phase: 'auto_submit',
              data: {
                phase: 'auto_submit',
                phase_label: '自动提交',
                message: '自动提交完成。',
                scanned: passedIds.length,
                total: passedIds.length,
                percent: 100,
                eta_seconds: 0,
                updated_at_ms: Date.now(),
              },
            });
            Toast.success('自动提交完成');
          } catch (e) {}
        }
      }
    } catch (e) { Toast.error('检查失败：' + e.message); }
    finally { S.set('batchCheckJobId', ''); clearRuntimeStatus(); renderBusyControls(); renderAll(); }
  };
  window.handleAutoSubmitToggle = function () {
    S.set('config.autoSubmit', Boolean(($('autoSubmitToggle') || {}).checked));
  };
  window.shutdownApp = async function () {
    var confirmed = await window.Modal.confirmAction('确认关闭本地服务并终止所有后台任务？', '关闭服务', '取消', { variant: 'danger' });
    if (!confirmed) return;
    try { await Api.post('/api/shutdown', {}); } catch (e) {}
    setSafeHtml(document.body, '<div class="shutdown-screen"><div class="shutdown-title">服务已关闭</div><div class="shutdown-note">可以安全关闭此窗口。</div></div>');
  };
  async function loadProfile() {
    if (LoadingFeedback.loadProfile) return LoadingFeedback.loadProfile();
    try {
      var data = await Api.get('/api/profile');
      if (data && data.profile) S.set('userProfile', data.profile);
      renderUserProfile();
    } catch (e) { /* silent */ }
  }
	  function renderUserProfile() {
	    var profile = S.get('userProfile') || {}, el = $('userProfile');
	    if (!el) return;
	    var tier = String(profile.tier || '');
	    if (tier && tier !== '--' && tier !== 'offline' && tier !== 'loading') {
	      el.textContent = String(profile.tier || '') + ' ' + String(profile.points ?? '--');
	    } else if (S.get('connectionStatus') === 'connected') {
	      el.textContent = connectionStatusLabel();
	    } else {
	      el.textContent = '未连接';
	    }
	  }
  function submitConnectionForm(event) {
    if (event && typeof event.preventDefault === 'function') event.preventDefault();
    window.testConnection();
  }
  window.loadConfig = async function () {
    if (LoadingFeedback.loadConfig) return LoadingFeedback.loadConfig();
    try {
      var data = await Api.get('/api/config');
      if (data && data.config) {
        S.set('config', data.config);
        if (typeof window.renderStrategyPolicy === 'function') window.renderStrategyPolicy(data.config);
        FormControls.applyConfig(data.config);
        syncStrategyPluginControls();
      }
    } catch (e) {}
  };
  window.applyPreset = function () {
    FormControls.applyPreset(presets);
    syncStrategyPluginControls();
  };
  async function loadPresets() {
    if (LoadingFeedback.loadPresets) return LoadingFeedback.loadPresets(function (items) { presets = items || {}; });
    try { var data = await Api.get('/api/presets'); if (data && data.presets) presets = data.presets; } catch (e) {}
  }
  window.loadRedlineReport = LoadingFeedback.loadRedlineReport || window.loadRedlineReport;
  window.loadCheckResults = LoadingFeedback.loadCheckResults || window.loadCheckResults;
  window.loadResearchMemory = LoadingFeedback.loadResearchMemory || window.loadResearchMemory;
  window.loadCheckpointStatus = LoadingFeedback.loadCheckpointStatus || window.loadCheckpointStatus;
  window.testConnection = async function () {
    // v4: Validate connection fields first
    if (FormControls.validateConnection && !FormControls.validateConnection()) {
      return;
    }
    var resultEl = $('connTestResult');
    if (!resultEl) return;
    resultEl.classList.remove('hidden');
    resultEl.textContent = '\u6D4B\u8BD5\u4E2D...';
    resultEl.className = 'connection-result is-pending';
    resultEl.setAttribute('role', 'status');
    resultEl.setAttribute('aria-live', 'polite');
    var startedAt = Date.now();
    var connectionEta = 8;
    S.setBatch({
      connectionTestInFlight: true,
      runtimeStatusStartedAt: startedAt,
      runtimeStatusUpdatedAt: startedAt,
      liveProgress: { phase: 'connection', data: { phase: 'connection', phase_label: '连接测试', message: '正在验证 BRAIN 生产环境凭证，请等待官方返回。', percent: 15, eta_seconds: connectionEta, eta_deadline_at_ms: etaDeadline(startedAt, connectionEta), updated_at_ms: startedAt } },
    });
    renderBusyControls();
    try {
      var resp = await Api.post('/api/test_connection', FormControls.connectionPayload());
      if (resp.ok) {
        resultEl.textContent = '\u8FDE\u63A5\u6210\u529F';
        resultEl.className = 'connection-result is-success';
        S.setBatch({
          connectionStatus: 'connected',
          connectionEnvironment: resp.environment || '',
          connectionAuth: resp.auth || '',
          lastConnectionError: '',
        });
        loadProfile();
        renderHeaderStatus();
      } else {
        resultEl.textContent = '\u8FDE\u63A5\u5931\u8D25\uFF1A' + (resp.error || '\u672A\u77E5\u9519\u8BEF');
        resultEl.className = 'connection-result is-error';
        S.setBatch({ connectionStatus: 'failed', lastConnectionError: resp.error || '未知错误' });
        renderHeaderStatus();
      }
    } catch (e) {
      resultEl.textContent = '\u8FDE\u63A5\u5931\u8D25\uFF1A' + e.message;
      resultEl.className = 'connection-result is-error';
      S.setBatch({ connectionStatus: 'failed', lastConnectionError: e.message || String(e) });
      renderHeaderStatus();
    } finally {
      S.setBatch({ connectionTestInFlight: false, runtimeStatusStartedAt: 0, runtimeStatusUpdatedAt: 0, liveProgress: {} });
      renderBusyControls();
    }
  };
  window._appPreRenderResult = renderResult;
  window.collectPayload = function () {
    return FormControls.collectPayload();
  };
  var Enhancements = window.AppEnhancements && window.AppEnhancements.create ? window.AppEnhancements.create({
    $: $,
    activeView: activeView,
    esc: esc,
    findActionElement: findActionElement,
    invokeWindowAction: invokeWindowAction,
    registry: Registry,
    renderCurrentView: function () { _renderCurrentView(); },
    renderTaskRail: renderTaskRail,
    renderViewTabs: renderViewTabs,
    spinner: Spinner,
    state: S,
    updateActionBarVisibility: updateActionBarVisibility,
    updatePanelHeader: updatePanelHeader,
    viewOrder: VIEW_ORDER,
  }) : {};
  var SHORTCUTS = Enhancements.SHORTCUTS || [];
  var handleKeyboardShortcut = Enhancements.handleKeyboardShortcut || function () {};
  var toggleShortcutsPanel = Enhancements.toggleShortcutsPanel || function () {};
  var showWorkflowWizard = Enhancements.showWorkflowWizard || function () {};
  var _prevSwitchView = window.switchView;
  if (Enhancements.wrapSwitchView) window.switchView = Enhancements.wrapSwitchView(_prevSwitchView);

  // ── v4: INIT ───────────────────────────────────────────────────────────

  async function init() {
    // Show skeleton screens immediately
    if (Spinner.showTableSkeleton) Spinner.showTableSkeleton(6);

    renderViewTabs();
    updatePanelHeader();
    renderTaskRail();
    installStaticActionHandlers();
    installViewTabDelegates();
    installResultDelegates();
    var connectionForm = $('connectionForm');
    if (connectionForm && !connectionForm.dataset.boundSubmit) {
      connectionForm.dataset.boundSubmit = '1';
      connectionForm.addEventListener('submit', submitConnectionForm);
    }

    // v4: Install keyboard shortcuts
    document.addEventListener('keydown', handleKeyboardShortcut);

    window._appPreRenderResult = renderResult;
    if (LoadingFeedback.runStartup) {
      await LoadingFeedback.runStartup({ apply: syncStartupState, setPresets: function (items) { presets = items || {}; } });
    } else {
      try {
        var results = await Promise.all([
          Api.get('/api/latest_result').catch(function () { return {}; }),
          Api.get('/api/config').catch(function () { return {}; }),
        ]);
        if (results[0] && results[0].result) renderResult(results[0].result);
        if (results[1] && results[1].config) {
          S.set('config', results[1].config);
          if (typeof window.renderStrategyPolicy === 'function') window.renderStrategyPolicy(results[1].config);
          FormControls.applyConfig(results[1].config);
          syncStrategyPluginControls();
        }
      } catch (e) { /* ignore */ }
      loadProfile();
      loadPresets();
      if (LoadingFeedback.loadCloudSnapshot) LoadingFeedback.loadCloudSnapshot();
      else if (window.CloudSync && window.CloudSync.loadSnapshot) window.CloudSync.loadSnapshot().catch(function () {});
      if (typeof window.loadRedlineReport === 'function') window.loadRedlineReport();
      if (typeof window.loadCheckpointStatus === 'function') window.loadCheckpointStatus();
      if (typeof window.loadCheckResults === 'function') window.loadCheckResults();
    }
    var toggle = $('displayModeToggle'); if (toggle) toggle.classList.remove('hidden');
    window.renderBusyControls();
    var runtimeTimer = setInterval(function () {
      if (activeRuntimeKind() && typeof window.renderRuntimeStatus === 'function') window.renderRuntimeStatus();
    }, 1000);
    if (runtimeTimer && typeof runtimeTimer.unref === 'function') runtimeTimer.unref();
  }
  S.onUpdate(function (path) {
    var pathName = String(path || '');
    var busyPaths = ['isRunning', 'activeJobId', 'syncInFlight', 'syncJobId', 'syncRecoverable', 'batchCheckJobId', 'submitInFlight', 'selectedSubmitIds', 'batch', 'liveProgress', 'runtimeStatusStartedAt', 'runtimeStatusUpdatedAt', 'syncStartedAt', 'checkStartedAt', 'pageLoadInFlight', 'connectionTestInFlight'];
    if (busyPaths.indexOf(pathName) !== -1) window.renderBusyControls();
    if (busyPaths.indexOf(pathName) !== -1 || pathName === 'activeView' || pathName === 'checkResults' || pathName.indexOf('currentResult') === 0) renderTaskRail();
    if (busyPaths.indexOf(pathName) !== -1 || pathName === 'connectionStatus' || pathName === 'connectionEnvironment' || pathName === 'connectionAuth') {
      renderHeaderStatus();
    }
  });
  window.addEventListener('resize', function () { _renderCurrentView(); });
  window._app = {
    renderResult: renderResult,
    renderJobSnapshot: renderJobSnapshot,
    renderAll: renderAll,
    renderTaskRail: renderTaskRail,
    renderHeaderStatus: renderHeaderStatus,
    syncStartupState: syncStartupState,
    loadConfig: window.loadConfig,
    loadProfile: loadProfile,
    loadCheckResults: function () { return LoadingFeedback.loadCheckResults ? LoadingFeedback.loadCheckResults() : Promise.resolve(); },
    loadCheckpointStatus: function () { return LoadingFeedback.loadCheckpointStatus ? LoadingFeedback.loadCheckpointStatus() : Promise.resolve(); },
    loadCloudSnapshot: function () { return LoadingFeedback.loadCloudSnapshot ? LoadingFeedback.loadCloudSnapshot() : Promise.resolve(); },
    loadResearchMemory: function () { return LoadingFeedback.loadResearchMemory ? LoadingFeedback.loadResearchMemory() : Promise.resolve(); },
  };
  window.renderCurrentView = _renderCurrentView;
  window.renderTaskRail = renderTaskRail;
  window.renderAll = renderAll;
  window.toggleShortcutsPanel = toggleShortcutsPanel;
  window.showWorkflowWizard = showWorkflowWizard;
  window.SHORTCUTS = SHORTCUTS;

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else setTimeout(init, 10);
})();
