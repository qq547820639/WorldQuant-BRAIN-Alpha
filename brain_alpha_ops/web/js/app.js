// brain_alpha_ops/web/js/app.js
// Application entry point: render dispatch, view state, and page-level actions.
// v3: Redesigned with tab-based navigation, simplified rendering, and enhanced UX.
(function () {
  'use strict';
  var $ = window.Utils.$;
  var esc = window.Utils.escapeHtml;
  var escapeAttr = window.Utils.escapeAttr;
  var phaseName = window.Utils.phaseName;
  var Api = window.ApiClient;
  var S = window.AppState;
  var Toast = window.Toast;
  var VM = window.ViewModel;
  var Registry = window.ViewRegistry;
  var ViewRenderers = window.ViewRenderers;
  var ResultState = window.ResultState;
  var FormControls = window.FormControls;
  var StrategyPanel = window.StrategyPanel || {};
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
  window.operationBlockReason = function (action) {
    var running = Boolean(S.get('isRunning'));
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
    return '';
  }
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
  window.toggleEnvironment = function () {
    var envEl = $('environment');
    if (envEl) envEl.value = 'production';
    var prodNote = $('productionNote');
    if (prodNote) prodNote.classList.remove('hidden');
    var envBadge = $('envBadge');
    if (envBadge) envBadge.textContent = '生产环境';
    window.renderBusyControls();
  };
  function renderViewTabs() {
    var container = $('viewTabs');
    if (!container) return;
    var currentView = activeView();
    container.innerHTML = VIEW_GROUPS.map(function (group) {
      return '<div class="view-tab-group" aria-label="' + esc(group.label) + '">' +
        '<div class="view-tab-group-label"><span>' + esc(group.label) + '</span><small>' + esc(group.hint) + '</small></div>' +
        '<div class="view-tab-row">' + group.views.map(function (view) { return renderTab(view, currentView); }).join('') + '</div>' +
        '</div>';
    }).join('');
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
      case 'set-result-display-mode':
        invokeWindowAction('setResultDisplayMode', [el.getAttribute('data-mode') || 'table']);
        break;
      case 'clear-search': {
        var search = $('tableSearch');
        if (search) search.value = '';
        _renderCurrentView();
        break;
      }
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
      case 'toggle-environment':
        invokeWindowAction('toggleEnvironment');
        break;
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
      S.set('submitInFlight', true);
      var ids = selectedSubmitList();
      var payload = Object.assign(window.collectPayload ? window.collectPayload() : {}, { alpha_ids: ids });
      var resp = await Api.post('/api/submit_batch', payload);
      if (resp.ok) {
        Toast.success('提交成功：' + (resp.submitted || ids.length) + ' 个 Alpha');
        setSelectedSubmitIds([]);
        if (typeof window.loadCheckResults === 'function') window.loadCheckResults();
      }
    } catch (e) { Toast.error('提交失败：' + e.message); }
    finally { S.set('submitInFlight', false); _renderCurrentView(); window.renderBusyControls(); }
  };
  window.submitSingleCandidate = async function (alphaId) {
    var confirmed = await window.Modal.confirmAction('确认提交 Alpha ' + alphaId + '？', '提交', '取消');
    if (!confirmed) return;
    try {
      S.set('submitInFlight', true);
      var payload = Object.assign(window.collectPayload ? window.collectPayload() : {}, { alpha_id: alphaId });
      var resp = await Api.post('/api/submit', payload);
      if (resp.ok) Toast.success('提交成功：' + alphaId);
    } catch (e) { Toast.error('提交失败：' + e.message); }
    finally { S.set('submitInFlight', false); _renderCurrentView(); window.renderBusyControls(); }
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
    S.setBatch({ batchCheckJobId: 'check_' + Date.now(), checkStartedAt: Date.now() });
    renderBusyControls();
    try {
      var alphaIds = (mode === 'all' ? passed : passed.slice(0, 10)).map(function (c) { return c.alpha_id || candidateIdentity(c); });
      var payload = Object.assign(window.collectPayload ? window.collectPayload() : {}, { alpha_ids: alphaIds });
      var resp = await Api.post('/api/check_batch', payload);
      if (resp.ok && resp.check_results) {
        var checks = S.get('checkResults') || {};
        Object.assign(checks, resp.check_results);
        S.set('checkResults', checks);
        var passedCount = Object.values(resp.check_results).filter(function (c) { return c.passed; }).length;
        Toast.success('检查完成：' + passedCount + ' 通过 / ' + alphaIds.length + ' 总数');
        if (($('autoSubmitToggle') || {}).checked && passedCount > 0) {
          var passedIds = Object.entries(resp.check_results).filter(function (e) { return e[1].passed; }).map(function (e) { return e[0]; });
          try {
            var submitPayload = Object.assign(window.collectPayload ? window.collectPayload() : {}, { alpha_ids: passedIds });
            await Api.post('/api/submit_batch', submitPayload);
            Toast.success('自动提交完成');
          } catch (e) {}
        }
      }
    } catch (e) { Toast.error('检查失败：' + e.message); }
    finally { S.set('batchCheckJobId', ''); renderBusyControls(); renderAll(); }
  };
  window.handleAutoSubmitToggle = function () {
    S.set('config.autoSubmit', Boolean(($('autoSubmitToggle') || {}).checked));
  };
  window.shutdownApp = async function () {
    var confirmed = await window.Modal.confirmAction('确认关闭本地服务并终止所有后台任务？', '关闭服务', '取消', { variant: 'danger' });
    if (!confirmed) return;
    try { await Api.post('/api/shutdown', {}); } catch (e) {}
    document.body.innerHTML = '<div class="shutdown-screen"><div class="shutdown-title">服务已关闭</div><div class="shutdown-note">可以安全关闭此窗口。</div></div>';
  };
  async function loadProfile() {
    try {
      var data = await Api.get('/api/profile');
      if (data && data.profile) S.set('userProfile', data.profile);
      renderUserProfile();
    } catch (e) { /* silent */ }
  }
  function renderUserProfile() {
    var profile = S.get('userProfile') || {}, el = $('userProfile');
    if (!el) return;
    if (profile.tier && profile.tier !== '--') {
      el.innerHTML = '<span class="profile-tier">' + esc(profile.tier || '') + '</span> <span class="profile-points">' + esc(String(profile.points ?? '--')) + '</span>';
    } else {
      el.innerHTML = '<span class="text-muted">未连接</span>';
    }
  }
  window.loadConfig = async function () {
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
    try { var data = await Api.get('/api/presets'); if (data && data.presets) presets = data.presets; } catch (e) {}
  }
  window.testConnection = async function () {
    var resultEl = $('connTestResult');
    if (!resultEl) return;
    resultEl.classList.remove('hidden');
    resultEl.textContent = '测试中...';
    resultEl.className = 'connection-result is-pending';
    try {
      var resp = await Api.post('/api/test_connection', FormControls.connectionPayload());
      if (resp.ok) { resultEl.textContent = '连接成功'; resultEl.className = 'connection-result is-success'; }
      else { resultEl.textContent = '连接失败：' + (resp.error || '未知错误'); resultEl.className = 'connection-result is-error'; }
    } catch (e) { resultEl.textContent = '连接失败：' + e.message; resultEl.className = 'connection-result is-error'; }
  };
  window.collectPayload = function () {
    return FormControls.collectPayload();
  };
  async function init() {
    renderViewTabs();
    updatePanelHeader();
    renderTaskRail();
    installStaticActionHandlers();
    installViewTabDelegates();
    installResultDelegates();
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
    if (window.CloudSync && window.CloudSync.loadSnapshot) window.CloudSync.loadSnapshot().catch(function () {});
    if (typeof window.loadRedlineReport === 'function') window.loadRedlineReport();
    if (typeof window.loadCheckpointStatus === 'function') window.loadCheckpointStatus();
    if (typeof window.loadCheckResults === 'function') window.loadCheckResults();
    var toggle = $('displayModeToggle'); if (toggle) toggle.classList.remove('hidden');
    window.renderBusyControls();
  }
  S.onUpdate(function (path) {
    var pathName = String(path || '');
    var busyPaths = ['isRunning', 'activeJobId', 'syncInFlight', 'batchCheckJobId', 'submitInFlight', 'selectedSubmitIds', 'batch'];
    if (busyPaths.indexOf(pathName) !== -1) window.renderBusyControls();
    if (busyPaths.indexOf(pathName) !== -1 || pathName === 'activeView' || pathName === 'checkResults' || pathName.indexOf('currentResult') === 0) renderTaskRail();
    if (pathName === 'isRunning' || pathName === 'activeJobId') {
      var statusEl = $('globalStatus');
      var dotEl = $('headerStatusDot');
      if (statusEl) {
        var isRunning = S.get('isRunning');
        if (isRunning) {
          var live = S.get('liveProgress') || {}, phase = live.phase || '';
          statusEl.textContent = '运行中 — ' + phaseName(phase);
          statusEl.className = 'text-sm text-success fw-bold';
        } else {
          statusEl.textContent = '系统空闲';
          statusEl.className = 'text-sm text-muted';
        }
      }
      if (dotEl) {
        dotEl.className = 'header-status-dot' + (S.get('isRunning') ? ' is-running' : '');
      }
    }
  });
  window.addEventListener('resize', function () { _renderCurrentView(); });
  window._app = {
    renderResult: renderResult,
    renderJobSnapshot: renderJobSnapshot,
    renderAll: renderAll,
    renderTaskRail: renderTaskRail,
    loadConfig: window.loadConfig,
    loadProfile: loadProfile,
    loadCheckResults: function () {
      Api.get('/api/check_results').then(function (data) { if (data && data.check_results) S.set('checkResults', data.check_results); }).catch(function () {});
    },
    loadCloudSnapshot: function () {
      return window.CloudSync && window.CloudSync.loadSnapshot ? window.CloudSync.loadSnapshot().catch(function () {}) : Promise.resolve();
    },
    loadResearchMemory: function () {
      Api.get('/api/research_memory').then(function (data) { if (data) S.set('currentResult.research_memory', data); }).catch(function () {});
    },
  };
  window.renderCurrentView = _renderCurrentView;
  window.renderTaskRail = renderTaskRail;
  window.renderAll = renderAll;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else setTimeout(init, 10);
})();
