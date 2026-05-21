// brain_alpha_ops/web/js/app.js
// Application entry point: render dispatch, view state, and page-level actions.
// v3: Redesigned with tab-based navigation, simplified rendering, and enhanced UX.

(function () {
  'use strict';

  var $ = window.Utils.$;
  var esc = window.Utils.escapeHtml;
  var escapeAttr = window.Utils.escapeAttr;
  var jsStringAttr = window.Utils.jsStringAttr;
  var phaseName = window.Utils.phaseName;
  var num = window.Utils.num;
  var badgeClass = window.Utils.badgeClass;
  var scoreSpan = window.Utils.scoreSpan;
  var statusBadge = window.Utils.statusBadge;

  var Api = window.ApiClient;
  var S = window.AppState;
  var Toast = window.Toast;
  var VM = window.ViewModel;
  var candidateIdentity = VM.candidateIdentity;
  var candidateDisplayScore = VM.candidateDisplayScore;
  var chooseRuntimeArray = VM.chooseRuntimeArray;
  var expressionFromRow = VM.expressionFromRow;
  var normalizedExpression = VM.normalizedExpression;
  var uniqueBacktestSlots = VM.uniqueBacktestSlots;
  var uniqueBy = VM.uniqueBy;
  var uniqueCandidates = VM.uniqueCandidates;
  var uniqueLifecycle = VM.uniqueLifecycle;
  var firstFiniteNumber = VM.firstFiniteNumber;
  var firstPositiveFiniteNumber = VM.firstPositiveFiniteNumber;

  window.$ = $;

  var MAX_RENDERED_ROWS = S.MAX_RENDERED_ROWS || 300;
  var CHECK_STALE_MS = S.CHECK_STALE_MS || 24 * 60 * 60 * 1000;

  // ── View Registry ─────────────────────────────────────────────────────
  var VIEW_ORDER = [
    'candidates', 'pending_backtest', 'running_backtest', 'backtest_rework',
    'passed', 'submittable', 'submitted', 'failed',
    'cloud', 'lifecycle',
    'research_memory', 'research_knowledge', 'research_observability',
    'prompt_runs', 'sqlite_indexes', 'robustness',
  ];

  var WORKFLOW_VIEWS = ['candidates', 'pending_backtest', 'running_backtest', 'backtest_rework', 'passed', 'submittable', 'submitted', 'failed'];
  var DATA_VIEWS = ['cloud', 'lifecycle'];
  var RESEARCH_VIEWS = ['research_memory', 'research_knowledge', 'research_observability', 'prompt_runs', 'sqlite_indexes', 'robustness'];

  var VIEW_TITLES = {
    candidates: '候选池', pending_backtest: '等待回测', running_backtest: '回测中',
    backtest_rework: '二次融合', passed: '达标', submittable: '可提交',
    submitted: '已提交', failed: '不达标', cloud: '云端数据', lifecycle: '生命周期',
    research_memory: 'Research Memory', research_observability: 'Observability',
    research_knowledge: 'Knowledge Base', prompt_runs: 'Prompt Ledger',
    sqlite_indexes: 'SQLite Index', robustness: 'Robustness',
  };

  var VIEW_ICONS = {
    candidates: '📋', pending_backtest: '⏳', running_backtest: '🔄',
    backtest_rework: '🔧', passed: '✅', submittable: '📤',
    submitted: '🚀', failed: '❌', cloud: '☁️', lifecycle: '📅',
    research_memory: '🧠', research_observability: '📊',
    research_knowledge: '📚', prompt_runs: '💬', sqlite_indexes: '🗄️', robustness: '🛡️',
  };

  var VIEW_HINTS = {
    candidates: '按排序分降序展示核心候选池。',
    pending_backtest: '等待回测按排队顺序展示。',
    running_backtest: '正在等待官方回测结果返回。',
    backtest_rework: '回测失败或需要二次融合的 Alpha。',
    passed: '达标 Alpha 可批量检查后提交。',
    submittable: '检查通过且在有效期内的 Alpha，可直接提交。',
    submitted: '已提交和云端已提交记录。',
    failed: '不达标、拒绝和阻断记录。',
    cloud: '云端快照和缓存统计。',
    lifecycle: '关键生命周期事件追踪。',
    research_memory: '本地 JSONL research memory。',
    research_knowledge: '结构化规则和发现。',
    research_observability: '可观测性快照。',
    prompt_runs: 'Prompt 运行账本。',
    sqlite_indexes: 'SQLite 缓存状态。',
    robustness: '反过拟合和滚动验证状态。',
  };

  // ── App-level state ───────────────────────────────────────────────────
  var activeFilter = '';
  var resultDisplayMode = 'table';
  var presets = {};
  var syncInFlight = false;
  var batchCheckJobId = '';
  var submitInFlight = false;
  var selectedSubmitIds = new Set();
  var syncStartedAt = 0;
  var checkStartedAt = 0;

  // ── Helpers ────────────────────────────────────────────────────────────

  function toast(msg, type, duration) {
    if (Toast && Toast.toast) Toast.toast(String(msg || ''), type || 'info', duration);
  }

  function setVal(id, value) {
    var el = $(id); if (el && value !== undefined && value !== null) el.value = value;
  }

  function hasDataObject(obj) { return Boolean(obj && typeof obj === 'object' && Object.keys(obj).length); }

  function setControlState(id, disabled, reason) {
    var el = $(id); if (!el) return;
    if (!el.dataset.defaultTitle) el.dataset.defaultTitle = el.getAttribute('title') || '';
    el.disabled = Boolean(disabled);
    if (reason) el.setAttribute('title', reason);
    else if (el.dataset.defaultTitle) el.setAttribute('title', el.dataset.defaultTitle);
    else el.removeAttribute('title');
  }

  // ── Operation Blocking ─────────────────────────────────────────────────

  window.operationBlockReason = function (action) {
    var running = Boolean(S.get('isRunning'));
    switch (action) {
      case 'production': if (syncInFlight) return '云端同步正在进行。'; if (batchCheckJobId) return '达标检查正在进行。'; if (submitInFlight) return '提交正在进行。'; return '';
      case 'sync': if (running) return '生产任务运行中。'; if (batchCheckJobId) return '达标检查正在进行。'; if (submitInFlight) return '提交正在进行。'; if (syncInFlight) return '云端同步正在进行。'; return '';
      case 'check': if (running) return '生产任务运行中。'; if (syncInFlight) return '云端同步正在进行。'; if (submitInFlight) return '提交正在进行。'; if (batchCheckJobId) return '达标检查正在进行。'; return '';
      case 'submit': if (running) return '生产任务运行中。'; if (syncInFlight) return '云端同步正在进行。'; if (batchCheckJobId) return '达标检查正在进行。'; if (submitInFlight) return '提交正在进行。'; return '';
    }
    return '';
  };

  function currentOperationText() {
    if (syncInFlight) return '云端同步正在进行，其他冲突操作已暂时锁定。';
    if (batchCheckJobId) return '达标检查正在进行，其他冲突操作已暂时锁定。';
    if (submitInFlight) return '提交正在进行，其他冲突操作已暂时锁定。';
    if (S.get('isRunning')) return '生产任务正在运行。';
    return '';
  }

  window.renderBusyControls = function () {
    var prodReason = window.operationBlockReason('production');
    var syncReason = window.operationBlockReason('sync');
    var checkReason = window.operationBlockReason('check');
    var submitReason = window.operationBlockReason('submit');

    setControlState('controlButton', Boolean(prodReason), prodReason);
    setControlState('syncButton', Boolean(syncReason), syncReason);
    var syncRange = $('syncRange'); if (syncRange) syncRange.disabled = Boolean(syncReason);
    setControlState('checkButton', Boolean(checkReason) || Boolean(batchCheckJobId), checkReason);

    var submitBtn = $('submitSelectedButton');
    if (submitBtn) { var sReason = submitReason || !selectedSubmitIds.size ? (selectedSubmitIds.size ? submitReason : '请先选择要提交的 Alpha') : ''; submitBtn.disabled = Boolean(sReason); if (sReason) submitBtn.setAttribute('title', sReason); }

    var autoSubmit = $('autoSubmitToggle'); if (autoSubmit) autoSubmit.disabled = Boolean(submitReason || batchCheckJobId || submitInFlight);

    var guard = $('operationGuard');
    if (guard) { var msg = currentOperationText(); guard.textContent = msg; guard.classList.toggle('hidden', !msg); }
  };

  // ── Data Accessors ─────────────────────────────────────────────────────

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

  // ── Theme ──────────────────────────────────────────────────────────────

  window.toggleTheme = function () {
    var html = document.documentElement;
    var isDark = html.getAttribute('data-theme') === 'dark';
    var next = isDark ? '' : 'dark';
    html.setAttribute('data-theme', next);
    var light = document.querySelector('.theme-icon-light');
    var dark = document.querySelector('.theme-icon-dark');
    if (light) light.style.display = isDark ? '' : 'none';
    if (dark) dark.style.display = isDark ? 'none' : '';
    try { localStorage.setItem('brain-alpha-ops-theme', isDark ? 'light' : 'dark'); } catch (e) {}
  };

  (function initTheme() {
    try {
      var saved = localStorage.getItem('brain-alpha-ops-theme');
      if (saved === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
        var li = document.querySelector('.theme-icon-light');
        var di = document.querySelector('.theme-icon-dark');
        if (li) li.style.display = 'none';
        if (di) di.style.display = '';
      }
    } catch (e) {}
  })();

  // ── Environment Toggle ─────────────────────────────────────────────────

  window.toggleEnvironment = function () {
    var env = ($('environment') || {}).value;
    var prodNote = $('productionNote'), mockNote = $('mockNote');
    if (prodNote) prodNote.classList.toggle('hidden', env !== 'production');
    if (mockNote) mockNote.classList.toggle('hidden', env !== 'mock');
    var envBadge = $('envBadge');
    if (envBadge) envBadge.textContent = env === 'mock' ? 'Mock' : 'Production';
    window.renderBusyControls();
  };

  // ── View Tabs ──────────────────────────────────────────────────────────

  function renderViewTabs() {
    var container = $('viewTabs');
    if (!container) return;
    var currentView = activeView();

    var workflowTabs = WORKFLOW_VIEWS.map(function (v) {
      return renderTab(v, currentView);
    });

    var dataTabs = DATA_VIEWS.map(function (v) {
      return renderTab(v, currentView);
    });

    var researchTabs = RESEARCH_VIEWS.map(function (v) {
      return renderTab(v, currentView);
    });

    container.innerHTML =
      workflowTabs.join('') +
      '<span class="view-tab-separator" aria-hidden="true"></span>' +
      dataTabs.join('') +
      '<span class="view-tab-separator" aria-hidden="true"></span>' +
      researchTabs.join('');
  }

  function renderTab(view, currentView) {
    var title = VIEW_TITLES[view] || view;
    var icon = VIEW_ICONS[view] || '📌';
    var isActive = view === currentView;
    var count = S.viewCount(view);
    var badgeHtml = count > 0 ? '<span class="tab-badge">' + (count > 99 ? '99+' : count) + '</span>' : '';

    return '<button class="view-tab' + (isActive ? ' is-active' : '') + '"' +
      ' onclick="switchView(\'' + view + '\')"' +
      ' aria-pressed="' + isActive + '"' +
      ' title="' + esc(title) + (count > 0 ? ' (' + count + ')' : '') + '"' +
      '>' + icon + ' ' + esc(title) + badgeHtml + '</button>';
  }

  // ── View Switching ─────────────────────────────────────────────────────

  window.switchView = function (view) {
    if (VIEW_ORDER.indexOf(view) === -1) view = 'candidates';
    activeFilter = '';
    S.set('activeView', view);
    renderViewTabs();
    _renderCurrentView();
    if (typeof window.renderInsight === 'function') window.renderInsight();
    updatePanelHeader();
    // Show/hide action bar based on view
    updateActionBarVisibility(view);
  };

  function activeView() { return S.get('activeView') || 'candidates'; }

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
      hintEl.textContent = view === 'submittable' ? '选择 Alpha 进行提交。' : view === 'passed' ? '批量核验全部达标 Alpha 当前是否仍可提交。' : '管理候选池中的 Alpha。';
    }
    // Show/hide specific buttons
    var checkBtn = $('checkButton');
    var submitBtn = $('submitSelectedButton');
    if (checkBtn) checkBtn.classList.toggle('hidden', view !== 'passed');
    if (submitBtn) submitBtn.classList.toggle('hidden', view !== 'submittable' && view !== 'passed');
  }

  // ── Display Mode ───────────────────────────────────────────────────────

  window.setResultDisplayMode = function (mode) {
    resultDisplayMode = mode || 'table';
    var tableBtn = $('tableModeBtn'), chartBtn = $('chartModeBtn');
    var chartsPanel = $('chartsPanel');
    if (tableBtn) { tableBtn.classList.toggle('is-active', mode === 'table'); tableBtn.setAttribute('aria-pressed', mode === 'table'); }
    if (chartBtn) { chartBtn.classList.toggle('is-active', mode === 'charts'); chartBtn.setAttribute('aria-pressed', mode === 'charts'); }
    if (chartsPanel) chartsPanel.classList.toggle('visible', mode === 'charts');
    if (mode === 'charts' && typeof window.renderCharts === 'function') window.renderCharts();
    var toggle = $('displayModeToggle'); if (toggle) toggle.classList.toggle('hidden', false);
  };

  // ── Panel Header ───────────────────────────────────────────────────────

  function updatePanelHeader() {
    var view = activeView();
    var titleEl = $('tableTitle'), hintEl = $('panelHint');
    if (titleEl) titleEl.textContent = VIEW_TITLES[view] || view;
    if (hintEl) hintEl.textContent = VIEW_HINTS[view] || '';
    updateCountPill();
  }

  function updateCountPill() {
    var pill = $('countPill');
    if (!pill) return;
    var rows = getRowsForView(activeView());
    var count = rows.length;
    pill.textContent = count + ' 条';
    pill.className = 'badge ' + (count > 0 ? 'badge-accent' : 'badge-default');
  }

  // ── Cloud Sync / Check Helpers ─────────────────────────────────────────

  function cloudSyncStatus(cloud) {
    cloud = cloud || {};
    return String(cloud.phase || cloud.status || cloud.status_code || '').trim().toLowerCase();
  }

  function isActiveCloudSync(cloud) {
    cloud = cloud || {};
    var status = cloudSyncStatus(cloud);
    if (['completed', 'synced', 'failed', 'skipped'].indexOf(status) !== -1) return false;
    if (['auth', 'scan', 'merge', 'running', 'cloud_sync'].indexOf(status) !== -1) return true;
    return firstPositiveFiniteNumber(cloud.scanned, cloud.current, cloud.total) !== null;
  }

  function liveCloudSyncProgress() {
    var live = S.get('liveProgress') || {};
    var progress = live.data || {};
    return ((progress.data || {}).cloud_sync || progress.cloud_sync || {});
  }

  function isEmptyCloudSyncSnapshot(cloud, rows) {
    cloud = cloud || {};
    var status = cloudSyncStatus(cloud);
    if (status === 'empty') return true;
    if (['completed', 'synced', 'failed', 'skipped'].indexOf(status) !== -1) return false;
    if (Array.isArray(rows) && rows.length > 0) return false;
    return !firstPositiveFiniteNumber(cloud.scanned, cloud.current, cloud.total) && !firstPositiveFiniteNumber(cloud.count, cloud.loaded);
  }

  function mergeCloudSyncSummary(previous, incoming, rows) {
    previous = previous || {};
    incoming = incoming || {};
    var liveCloud = liveCloudSyncProgress();
    var active = isActiveCloudSync(liveCloud) ? Object.assign({}, previous, liveCloud) : previous;
    if (isActiveCloudSync(active) && isEmptyCloudSyncSnapshot(incoming, rows)) return Object.assign({}, incoming, active);
    if (!Object.keys(incoming).length && Object.keys(active).length) return Object.assign({}, active);
    return Object.assign({}, previous, incoming);
  }

  // ── Strategy Policy Rendering ──────────────────────────────────────────

  window.renderStrategyPolicy = function (config) {
    var target = $('strategyText');
    if (!target) return;
    var ops = (config || {}).ops || {};
    var budget = ops.budget || {};
    var slotLimits = [
      Number(budget.official_backtest_batch_size) || 3,
      Number(budget.max_official_simulations_per_cycle) || 3,
      Number(budget.max_official_concurrent_simulations) || 3,
    ].filter(function (v) { return Number.isFinite(v) && v > 0; });
    var slotLimit = Math.max(1, Math.round(Math.min.apply(Math, slotLimits)));
    if ($('slotPolicyText')) $('slotPolicyText').textContent = slotLimit + ' 槽';

    var runForever = Boolean(budget.run_forever);
    var pluginSpecs = Array.isArray(budget.strategy_plugin_specs) ? budget.strategy_plugin_specs : [];

    var items = [
      { label: '候选上限', value: (budget.max_candidates_per_cycle || 20) + ' / 轮', note: '每轮最多生成并评分的候选数' },
      { label: '池容量', value: (budget.retained_alpha_pool_size || 10), note: '本地候选池保留上限' },
      { label: '回测槽位', value: slotLimit + ' 并发槽', note: '批量 ' + (budget.official_backtest_batch_size || 3) },
      { label: '连续生产', value: runForever ? '开启' : '单轮', note: runForever ? '持续生产' : '单轮后停止' },
      { label: 'Strategy Plugins', value: budget.strategy_plugins_enabled ? ('On | ' + pluginSpecs.length + ' specs') : 'Off', note: pluginSpecs.length ? pluginSpecs.join(', ') : '-' },
    ];

    target.innerHTML = '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:var(--sp-2)">' +
      items.map(function (item) {
        return '<div style="padding:var(--sp-2);border:1px solid var(--border-default);border-radius:var(--r-md);background:var(--bg-surface-raised)">' +
          '<div style="font-size:var(--fs-2xs);color:var(--text-secondary);font-weight:var(--fw-bold)">' + esc(item.label) + '</div>' +
          '<div style="font-size:var(--fs-sm);font-weight:var(--fw-bold);margin-top:2px">' + esc(String(item.value)) + '</div>' +
          '<div style="font-size:var(--fs-2xs);color:var(--text-muted);margin-top:1px">' + esc(item.note) + '</div>' +
          '</div>';
      }).join('') + '</div>';
  };

  // ── Main Result Rendering ──────────────────────────────────────────────

  function renderResult(result) {
    result = result || {};
    var previousSummary = currentSummary();
    var summary = Object.assign({}, result.summary || {});
    var candidates = uniqueCandidates(chooseRuntimeArray(summary.candidates, result.candidates, currentCandidates()));
    var pending = uniqueCandidates(chooseRuntimeArray(summary.pending_backtest_candidates, null, S.get('currentResult.pending_backtest_candidates')));
    var passed = uniqueCandidates(chooseRuntimeArray(summary.passed_candidates, null, []));
    var incomingCloudRows = Array.isArray(summary.cloud_alphas) ? summary.cloud_alphas : null;
    var existingCloudRows = currentCloudAlphas();
    var incomingCloudSync = summary.cloud_sync || {};
    summary.cloud_sync = mergeCloudSyncSummary(previousSummary.cloud_sync, incomingCloudSync, incomingCloudRows);
    var cloud = uniqueCandidates(Array.isArray(incomingCloudRows) ? incomingCloudRows : existingCloudRows);
    var lifecycle = uniqueLifecycle(summary.lifecycle_records || currentLifecycle());
    var backtests = uniqueBacktestSlots(summary.backtest_slots || summary.backtests || result.backtests || currentBacktests());

    S.setBatch({
      'currentResult.summary': summary,
      'currentResult.candidates': candidates || [],
      'currentResult.pending_backtest_candidates': pending || [],
      'currentResult.passed_candidates': passed || [],
      'currentResult.cloud_alphas': cloud || [],
      'currentResult.lifecycle_records': lifecycle || [],
      'currentResult.backtests': backtests || [],
    });

    renderAll();
  }

  function renderJobSnapshot(job) {
    job = job || {};
    var progress = job.progress || {};
    var data = progress.data || {};
    var result = job.result || {};
    var summary = Object.assign({}, data, result.summary || {});
    renderResult({ summary: summary, candidates: firstArrayWithItems(summary.candidates, data.candidates, result.candidates) || [], backtests: summary.backtests || [] });
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
  }

  function firstArrayWithItems() {
    for (var i = 0; i < arguments.length; i++) { if (Array.isArray(arguments[i]) && arguments[i].length) return arguments[i]; }
    for (var j = 0; j < arguments.length; j++) { if (Array.isArray(arguments[j])) return arguments[j]; }
    return null;
  }

  // ── Main View Renderer ─────────────────────────────────────────────────

  var _renderCurrentView = function () {
    var view = activeView();
    var rows = getRowsForView(view);
    applySearchFilter(rows);
    var columns = getColumnsForView(view);

    var tableBody = $('candidateRows');
    var emptyEl = document.getElementById('tableEmptyState');
    var tableEl = document.getElementById('candidateTable');
    var mobileEl = document.getElementById('mobileCardList');

    if (!rows.length) {
      if (tableBody) tableBody.innerHTML = '';
      if (tableEl) tableEl.classList.add('hidden');
      if (mobileEl) mobileEl.classList.add('hidden');
      if (emptyEl) {
        emptyEl.classList.remove('hidden');
        var descEl = document.getElementById('tableEmptyDescription');
        var desc = getEmptyDescription(view);
        if (descEl) descEl.textContent = desc;
        var iconEl = document.getElementById('tableEmptyIcon');
        if (iconEl) iconEl.textContent = VIEW_ICONS[view] || '📊';
      }
      updateCountPill();
      return;
    }

    if (emptyEl) emptyEl.classList.add('hidden');
    if (tableEl) tableEl.classList.remove('hidden');

    var displayRows = rows.slice(0, MAX_RENDERED_ROWS);

    // Desktop table
    if (tableBody) {
      tableBody.innerHTML = displayRows.map(function (row, idx) {
        var isSelected = selectedSubmitIds.has(row.id || candidateIdentity(row.raw || {}));
        var rowHtml = '<tr data-kind="' + escapeAttr(row.kind || '') + '" data-id="' + escapeAttr(row.id || '') + '"' +
          (isSelected ? ' class="is-selected"' : '') + ' tabindex="0" role="button" aria-label="查看详情" ' +
          'onclick="handleRowClick(this)" onkeydown="if(event.key===\'Enter\')handleRowClick(this)">';

        rowHtml += columns.map(function (col) {
          var value = typeof col.accessor === 'function' ? col.accessor(row, idx) : (row.raw || row)[col.accessor];
          var rendered = col.render ? col.render(value, row, idx) : esc(String(value ?? ''));
          return '<td>' + (col.trustedHtml ? rendered : esc(String(rendered ?? ''))) + '</td>';
        }).join('');

        return rowHtml + '</tr>';
      }).join('');
    }

    // Mobile cards
    if (mobileEl && window.innerWidth <= 640) {
      mobileEl.classList.remove('hidden');
      var mobileCols = getMobileColumns(view);
      mobileEl.innerHTML = displayRows.map(function (row, idx) {
        var isSelected = selectedSubmitIds.has(row.id || candidateIdentity(row.raw || {}));
        var title = row.id || candidateIdentity(row.raw || {}) || ('条目 ' + (idx + 1));
        var metaHtml = mobileCols.map(function (col) {
          var value = typeof col.accessor === 'function' ? col.accessor(row, idx) : (row.raw || row)[col.accessor];
          var rendered = col.render ? col.render(value, row, idx) : esc(String(value ?? ''));
          return '<div class="mobile-card-meta-item">' + (col.trustedHtml ? rendered : esc(String(rendered ?? '-'))) + '</div>';
        }).join('');
        var actionsHtml = renderMobileActions(row, view);
        return '<div class="mobile-card' + (isSelected ? ' is-selected' : '') + '"' +
          ' data-kind="' + escapeAttr(row.kind || '') + '" data-id="' + escapeAttr(row.id || '') + '"' +
          ' tabindex="0" role="button" onclick="handleRowClick(this)" onkeydown="if(event.key===\'Enter\')handleRowClick(this)">' +
          '<div class="mobile-card-header"><div class="mobile-card-title">' + esc(String(title)) + '</div></div>' +
          '<div class="mobile-card-meta">' + metaHtml + '</div>' +
          (actionsHtml ? '<div class="mobile-card-actions">' + actionsHtml + '</div>' : '') +
          '</div>';
      }).join('');
    } else if (mobileEl) {
      mobileEl.classList.add('hidden');
    }

    updateCountPill();
    updateSortHint(view);
  };
  window.renderCurrentView = _renderCurrentView;

  function getEmptyDescription(view) {
    var defaults = {
      candidates: '点击「开始生产搜索」启动无人值守流程，或同步云端数据查看现有 Alpha。',
      pending_backtest: '暂无等待回测的 Alpha。生产任务会自动将候选提交到回测队列。',
      running_backtest: '暂无正在回测中的 Alpha。等待官方回测结果返回后自动填充。',
      backtest_rework: '暂无回测失败的 Alpha。',
      passed: '暂无达标的 Alpha。等待生产任务产生达标候选。',
      submittable: '暂无可提交的 Alpha，请先在达标视图中执行批量检查。',
      submitted: '暂无已提交的 Alpha。',
      failed: '暂无不达标的 Alpha。',
      cloud: '暂无云端数据。请先同步云端数据以查看现有 Alpha 记录。',
      lifecycle: '暂无生命周期记录。',
    };
    return defaults[view] || '当前视图暂无数据，请调整筛选条件或开始生产。';
  }

  function updateSortHint(view) {
    var el = $('sortHint'); if (!el) return;
    var hints = { candidates: '按排序分降序', passed: '按排序分降序', submittable: '按可提交状态排序' };
    el.textContent = hints[view] || '';
  }

  // ── Row click handler ──────────────────────────────────────────────────

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

  // ── View Data Sources ──────────────────────────────────────────────────

  function getRowsForView(view) {
    var summary = currentSummary();
    var candidates = currentCandidates();
    var cloud = currentCloudAlphas();
    var lifecycle = currentLifecycle();
    var checks = checkResults();

    switch (view) {
      case 'candidates': return buildCandidateRows(candidates, 'candidate');
      case 'pending_backtest': return buildCandidateRows(candidates.filter(function (c) { return (c.lifecycle_status || c.status || '') === 'pending_backtest'; }), 'pending_backtest');
      case 'running_backtest': return buildCandidateRows(candidates.filter(function (c) { var s = c.lifecycle_status || c.status || ''; return s === 'running_backtest' || s === 'running'; }), 'running_backtest');
      case 'backtest_rework': return buildCandidateRows(candidates.filter(function (c) { var s = c.lifecycle_status || c.status || ''; return s === 'backtest_rework' || s === 'failed_backtest' || s === 'rejected'; }), 'backtest_rework');
      case 'passed': return buildCandidateRows(candidates.filter(function (c) { return c.lifecycle_status === 'submission_ready' || ((c.gate || {}).submission_ready); }), 'passed');
      case 'submittable': return buildSubmittableRows(candidates, checks);
      case 'submitted': return buildSubmittedRows(candidates, lifecycle);
      case 'failed': return buildCandidateRows(candidates.filter(function (c) { var s = c.lifecycle_status || c.status || ''; return s === 'failed' || s === 'rejected' || s === 'blocked'; }), 'failed');
      case 'cloud': return buildCloudRows(cloud);
      case 'lifecycle': return buildLifecycleRows(lifecycle);
      case 'research_memory': return buildResearchRows(currentResearchMemory(), 'research_memory');
      case 'research_observability': return buildResearchRows(currentResearchObservability(), 'research_observability');
      case 'research_knowledge': return buildResearchRows(currentResearchKnowledge(), 'research_knowledge');
      case 'prompt_runs': return buildPromptRunRows(currentPromptRuns());
      case 'sqlite_indexes': return buildSqliteRows(currentSqliteIndexes());
      case 'robustness': return buildRobustnessRows(currentRobustnessSnapshot());
      default: return [];
    }
  }

  function buildCandidateRows(list, kind) {
    return (list || []).map(function (c, i) { return { kind: kind, id: c.alpha_id || c.id || ('row' + i), raw: c, _rowIndex: i, _candidate: c }; });
  }

  function buildSubmittableRows(candidates, checks) {
    return candidates.filter(function (c) {
      var aid = c.alpha_id || candidateIdentity(c);
      return S.isFreshPassedCheck(checks[aid]) && !(S.get('lastSubmitResults') || []).some(function (r) { return r.alpha_id === aid && r.submitted; });
    }).map(function (c, i) {
      return { kind: 'submittable', id: c.alpha_id || candidateIdentity(c), raw: c, _rowIndex: i, _candidate: c, _check: checks[c.alpha_id] };
    });
  }

  function buildSubmittedRows(candidates, lifecycle) {
    var submitted = lifecycle.filter(function (r) { return r.stage === 'submitted' || r.status === 'submitted'; });
    var localSubmitted = candidates.filter(function (c) { return c.lifecycle_status === 'submitted'; });
    return uniqueBy(submitted.concat(localSubmitted.map(function (c, i) { return { kind: 'submitted', id: c.alpha_id || c.official_alpha_id || ('sub' + i), raw: c }; })), function (r) { return r.id; });
  }

  function buildCloudRows(cloud) {
    return cloud.map(function (d, i) { return { kind: 'cloud', id: d.alpha_id || d.id || ('cloud' + i), raw: d, _rowIndex: i }; });
  }

  function buildLifecycleRows(lifecycle) {
    return lifecycle.map(function (r, i) { return { kind: 'lifecycle', id: r.alpha_id || r.id || ('life' + i), raw: r, _rowIndex: i }; });
  }

  function buildResearchRows(data, kind) {
    var items = Array.isArray(data.items) ? data.items : Array.isArray(data) ? data : [];
    return items.map(function (item, i) { return { kind: kind, id: item.id || ('res' + i), raw: item, _rowIndex: i }; });
  }

  function buildPromptRunRows(data) {
    var items = Array.isArray(data.runs) ? data.runs : Array.isArray(data) ? data : [];
    return items.map(function (item, i) { return { kind: 'prompt_run', id: item.run_id || ('pr' + i), raw: item, _rowIndex: i }; });
  }

  function buildSqliteRows(indexes) {
    var items = [];
    if (hasDataObject(indexes)) {
      Object.keys(indexes).forEach(function (key, i) { items.push({ kind: 'sqlite_index', id: key, raw: { key: key, value: indexes[key] }, _rowIndex: i }); });
    }
    return items;
  }

  function buildRobustnessRows(snapshot) {
    var items = Array.isArray(snapshot.candidates) ? snapshot.candidates : Array.isArray(snapshot) ? snapshot : [];
    return items.map(function (item, i) { return { kind: 'robustness', id: item.alpha_id || ('rob' + i), raw: item, _rowIndex: i }; });
  }

  // ── Search Filter ──────────────────────────────────────────────────────

  function applySearchFilter(rows) {
    var query = ($('tableSearch') || {}).value || '';
    if (!query || !rows) return;
    var q = query.toLowerCase();
    for (var i = rows.length - 1; i >= 0; i--) {
      var row = rows[i], raw = row.raw || {};
      var text = [row.id, raw.alpha_id, raw.official_alpha_id, raw.family, raw.hypothesis, raw.expression, expressionFromRow(raw), raw.status, raw.simulation_id, (raw.scorecard || {}).decision_band, raw.lifecycle_status || '', raw.stage || ''].join(' ').toLowerCase();
      if (text.indexOf(q) === -1) rows.splice(i, 1);
    }
  }

  // ── Column Definitions ─────────────────────────────────────────────────

  function getColumnsForView(view) {
    switch (view) {
      case 'cloud': return [
        { accessor: '_rowIndex', render: function (v, r, i) { return String(i + 1); } },
        { accessor: 'id', render: function (v, r) { return esc(String((r.raw || {}).alpha_id || r.id || '-')); } },
        { accessor: 'status', render: function (v, r) { var s = (r.raw || {}).status || ''; return statusBadge(s, s === 'APPROVED' || s === 'PRODUCTION' ? 'good' : s === 'REJECTED' ? 'bad' : 'info'); }, trustedHtml: true },
        { accessor: 'sharpe', render: function (v, r) { return scoreSpan((r.raw || {}).sharpe); }, trustedHtml: true },
        { accessor: 'fitness', render: function (v, r) { return scoreSpan((r.raw || {}).fitness); }, trustedHtml: true },
        { accessor: 'turnover', render: function (v, r) { return num((r.raw || {}).turnover, 4); } },
        { accessor: 'self_correlation', render: function (v, r) { return num((r.raw || {}).self_correlation, 4); } },
        { accessor: 'actions', render: function (v, r) { return '<button class="btn btn-secondary btn-sm" onclick="event.stopPropagation();window.viewCloudDetail(document.querySelector(\'[data-id=&quot;' + escapeAttr(r.id) + '&quot;]\'))">详情</button>'; }, trustedHtml: true },
      ];
      case 'lifecycle': return [
        { accessor: '_rowIndex', render: function (v, r, i) { return String(i + 1); } },
        { accessor: 'id', render: function (v, r) { return esc(String((r.raw || {}).alpha_id || r.id || '-')); } },
        { accessor: 'stage', render: function (v, r) { return esc(String((r.raw || {}).stage || '-')); } },
        { accessor: 'status', render: function (v, r) { var s = (r.raw || {}).status || ''; return statusBadge(s, s === 'completed' || s === 'passed' ? 'good' : s === 'failed' ? 'bad' : 'info'); }, trustedHtml: true },
        { accessor: 'timestamp', render: function (v, r) { return esc(String((r.raw || {}).timestamp || '-')); } },
        { accessor: 'message', render: function (v, r) { return esc(String((r.raw || {}).message || '')); } },
        { accessor: 'actions', render: function (v, r) { return '<button class="btn btn-secondary btn-sm" onclick="event.stopPropagation();window.viewLifecycleDetail(document.querySelector(\'[data-id=&quot;' + escapeAttr(r.id) + '&quot;]\'))">详情</button>'; }, trustedHtml: true },
      ];
      default: return [
        { accessor: '_rowIndex', render: function (v, r, i) { return String(i + 1); } },
        { accessor: 'id', render: function (v, r) {
          var raw = r.raw || {};
          var id = raw.alpha_id || r.id || '';
          var family = raw.family || '';
          return '<div><div style="font-weight:700">' + esc(id || '-') + '</div>' + (family ? '<div style="font-size:var(--fs-2xs);color:var(--text-muted)">' + esc(family) + '</div>' : '') + '</div>';
        }, trustedHtml: true },
        { accessor: 'family', render: function (v, r) { return esc(String((r.raw || {}).family || '-')); } },
        { accessor: 'score', render: function (v, r) { var sc = (r.raw || {}).scorecard || {}; return scoreSpan(sc.total_score || sc.local_rank_score || 0); }, trustedHtml: true },
        { accessor: 'status', render: function (v, r) {
          var raw = r.raw || {};
          var status = raw.lifecycle_status || raw.status || '';
          var gate = raw.gate || {};
          var color = status === 'submission_ready' || gate.submission_ready ? 'good' : status === 'failed' || status === 'rejected' ? 'bad' : status === 'running' || status === 'pending_backtest' ? 'info' : 'muted';
          return statusBadge(status || '-', color);
        }, trustedHtml: true },
        { accessor: 'official_id', render: function (v, r) { return esc(String((r.raw || {}).official_alpha_id || '-')); } },
        { accessor: 'risk', render: function (v, r) {
          var raw = r.raw || {};
          var risk = raw.submission_risk || raw.risk || '';
          return risk ? '<span style="color:var(--danger);font-size:var(--fs-2xs)">' + esc(String(risk).slice(0, 60)) + '</span>' : '';
        }, trustedHtml: true },
        { accessor: 'actions', render: function (v, r) {
          var raw = r.raw || {}, aid = raw.alpha_id || r.id || '';
          var viewName = activeView();
          var buttons = ['<button class="btn btn-secondary btn-sm" onclick="event.stopPropagation();window.viewCandidateDetail(' + jsStringAttr(JSON.stringify(raw)) + ')">详情</button>'];
          if (viewName === 'submittable' && !S.get('submitInFlight')) { buttons.push('<button class="btn btn-primary btn-sm" onclick="event.stopPropagation();submitSingleCandidate(\'' + escapeAttr(aid) + '\')">提交</button>'); }
          if (viewName === 'passed') { buttons.push('<button class="btn btn-secondary btn-sm" onclick="event.stopPropagation();toggleSelectCandidate(\'' + escapeAttr(aid) + '\', this)">选择</button>'); }
          return buttons.join(' ');
        }, trustedHtml: true },
      ];
    }
  }

  function getMobileColumns(view) {
    return [
      { label: '排序分', accessor: 'score', render: function (v, r) { return scoreSpan(((r.raw || {}).scorecard || {}).total_score || 0); }, trustedHtml: true },
      { label: '状态', accessor: 'status', render: function (v, r) { var s = (r.raw || {}).lifecycle_status || '-'; return statusBadge(s, s === 'submission_ready' ? 'good' : 'muted'); }, trustedHtml: true },
      { label: '官方 ID', accessor: 'official_id', render: function (v, r) { return esc(String((r.raw || {}).official_alpha_id || '-')); } },
    ];
  }

  function renderMobileActions(row, view) {
    var raw = row.raw || {}, aid = raw.alpha_id || row.id || '';
    var buttons = ['<button class="btn btn-secondary btn-sm" onclick="event.stopPropagation();window.viewCandidateDetail(' + jsStringAttr(JSON.stringify(raw)) + ')">详情</button>'];
    if (view === 'submittable') buttons.push('<button class="btn btn-primary btn-sm" onclick="event.stopPropagation();submitSingleCandidate(\'' + escapeAttr(aid) + '\')">提交</button>');
    return buttons.join(' ');
  }

  // ── Selection Helpers ──────────────────────────────────────────────────

  window.toggleSelectCandidate = function (id, el) {
    if (selectedSubmitIds.has(id)) { selectedSubmitIds.delete(id); if (el) el.textContent = '选择'; }
    else { selectedSubmitIds.add(id); if (el) el.textContent = '已选'; }
    _renderCurrentView();
  };

  window.submitSelectedCandidates = async function () {
    if (selectedSubmitIds.size === 0) { Toast.warning('请先选择要提交的 Alpha。'); return; }
    var confirmed = await window.Modal.confirmAction('确认提交 ' + selectedSubmitIds.size + ' 个 Alpha？', '确认提交', '取消');
    if (!confirmed) return;
    try {
      submitInFlight = true;
      var ids = Array.from(selectedSubmitIds);
      var resp = await Api.post('/api/submit_batch', { alpha_ids: ids });
      if (resp.ok) {
        Toast.success('提交成功：' + (resp.submitted || ids.length) + ' 个 Alpha');
        selectedSubmitIds.clear();
        if (typeof window.loadCheckResults === 'function') window.loadCheckResults();
      }
    } catch (e) { Toast.error('提交失败：' + e.message); }
    finally { submitInFlight = false; _renderCurrentView(); window.renderBusyControls(); }
  };

  window.submitSingleCandidate = async function (alphaId) {
    var confirmed = await window.Modal.confirmAction('确认提交 Alpha ' + alphaId + '？', '提交', '取消');
    if (!confirmed) return;
    try {
      submitInFlight = true;
      var resp = await Api.post('/api/submit', { alpha_id: alphaId });
      if (resp.ok) Toast.success('提交成功：' + alphaId);
    } catch (e) { Toast.error('提交失败：' + e.message); }
    finally { submitInFlight = false; _renderCurrentView(); window.renderBusyControls(); }
  };

  // ── Cloud Sync ─────────────────────────────────────────────────────────

  window.syncCloud = async function () {
    if (syncInFlight) return;
    var reason = window.operationBlockReason('sync');
    if (reason) { Toast.warning(reason); return; }
    syncInFlight = true; syncStartedAt = Date.now();
    renderBusyControls();
    Toast.info('开始同步云端数据...');
    var range = ($('syncRange') || {}).value || '3d';
    try {
      var resp = await Api.post('/api/sync_alphas', { range: range });
      if (resp.ok) {
        S.set('currentResult.cloud_alphas', resp.cloud_alphas || []);
        S.set('currentResult.summary.cloud_sync', resp.cloud_sync || { status: 'completed' });
        Toast.success('云端同步完成');
        renderAll();
      }
    } catch (e) { Toast.error('云端同步失败：' + e.message); }
    finally { syncInFlight = false; renderBusyControls(); }
  };

  // ── Check Batch ────────────────────────────────────────────────────────

  window.checkBatch = async function (mode) {
    if (batchCheckJobId) return;
    var reason = window.operationBlockReason('check');
    if (reason) { Toast.warning(reason); return; }
    var passed = currentCandidates().filter(function (c) { return c.lifecycle_status === 'submission_ready' || ((c.gate || {}).submission_ready); });
    if (!passed.length) { Toast.warning('暂无达标 Alpha 可检查。'); return; }
    batchCheckJobId = 'check_' + Date.now(); checkStartedAt = Date.now();
    renderBusyControls();
    try {
      var alphaIds = (mode === 'all' ? passed : passed.slice(0, 10)).map(function (c) { return c.alpha_id || candidateIdentity(c); });
      var resp = await Api.post('/api/check_batch', { alpha_ids: alphaIds });
      if (resp.ok && resp.check_results) {
        var checks = S.get('checkResults') || {};
        Object.assign(checks, resp.check_results);
        S.set('checkResults', checks);
        var passedCount = Object.values(resp.check_results).filter(function (c) { return c.passed; }).length;
        Toast.success('检查完成：' + passedCount + ' 通过 / ' + alphaIds.length + ' 总数');
        if (($('autoSubmitToggle') || {}).checked && passedCount > 0) {
          var passedIds = Object.entries(resp.check_results).filter(function (e) { return e[1].passed; }).map(function (e) { return e[0]; });
          try { await Api.post('/api/submit_batch', { alpha_ids: passedIds }); Toast.success('自动提交完成'); } catch (e) {}
        }
      }
    } catch (e) { Toast.error('检查失败：' + e.message); }
    finally { batchCheckJobId = ''; renderBusyControls(); renderAll(); }
  };

  window.handleAutoSubmitToggle = function () {
    S.set('config.autoSubmit', Boolean(($('autoSubmitToggle') || {}).checked));
  };

  // ── Shutdown ───────────────────────────────────────────────────────────

  window.shutdownApp = async function () {
    var confirmed = await window.Modal.confirmAction('确认关闭本地服务并终止所有后台任务？', '关闭服务', '取消', { variant: 'danger' });
    if (!confirmed) return;
    try { await Api.post('/api/shutdown', {}); } catch (e) {}
    document.body.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100vh;flex-direction:column;gap:16px"><div style="font-size:18px;font-weight:700">服务已关闭</div><div style="color:var(--text-muted)">可以安全关闭此窗口。</div></div>';
  };

  // ── Profile Loading ────────────────────────────────────────────────────

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
      el.innerHTML = '<span style="color:var(--accent);font-weight:var(--fw-bold)">' + esc(profile.tier || '') + '</span> <span style="color:var(--text-secondary)">' + esc(String(profile.points ?? '--')) + '</span>';
    } else {
      el.innerHTML = '<span class="text-muted">未连接</span>';
    }
  }

  // ── Load Config ────────────────────────────────────────────────────────

  window.loadConfig = async function () {
    try {
      var data = await Api.get('/api/config');
      if (data && data.config) {
        S.set('config', data.config);
        if (typeof window.renderStrategyPolicy === 'function') window.renderStrategyPolicy(data.config);
        var ops = (data.config || {}).ops || {}, budget = ops.budget || {};
        setVal('useAssistantGuidance', budget.assistant_guidance_enabled !== false);
        setVal('assistantGuidanceScoreAdjustment', budget.assistant_guidance_score_adjustment !== false);
        setVal('strategyPluginsEnabled', Boolean(budget.strategy_plugins_enabled));
      }
    } catch (e) {}
  };

  // ── Presets ────────────────────────────────────────────────────────────

  window.applyPreset = function () {
    var presetId = ($('preset') || {}).value, p = (presets || {})[presetId];
    if (!p || !p.settings) return;
    var s = p.settings;
    setVal('region', s.region); setVal('universe', s.universe); setVal('delay', s.delay);
    setVal('neutralization', s.neutralization); setVal('instrumentType', s.instrumentType);
    setVal('alphaType', s.alphaType); setVal('decay', s.decay); setVal('truncation', s.truncation);
    setVal('pasteurization', s.pasteurization); setVal('nanHandling', s.nanHandling);
    setVal('unitHandling', s.unitHandling); setVal('language', s.language);
  };

  async function loadPresets() {
    try { var data = await Api.get('/api/presets'); if (data && data.presets) presets = data.presets; } catch (e) {}
  }

  // ── Connection Test ────────────────────────────────────────────────────

  window.testConnection = async function () {
    var resultEl = $('connTestResult');
    if (!resultEl) return;
    resultEl.classList.remove('hidden');
    resultEl.textContent = '测试中...';
    resultEl.style.background = 'var(--bg-warning-soft)'; resultEl.style.color = 'var(--warning)';
    try {
      var resp = await Api.post('/api/test_connection', { username: ($('username') || {}).value, password: ($('password') || {}).value, token: ($('token') || {}).value, base_url: ($('baseUrl') || {}).value });
      if (resp.ok) { resultEl.textContent = '✓ 连接成功'; resultEl.style.background = 'var(--bg-success-soft)'; resultEl.style.color = 'var(--success)'; }
      else { resultEl.textContent = '✗ 连接失败：' + (resp.error || '未知错误'); resultEl.style.background = 'var(--bg-danger-soft)'; resultEl.style.color = 'var(--danger)'; }
    } catch (e) { resultEl.textContent = '✗ 连接失败：' + e.message; resultEl.style.background = 'var(--bg-danger-soft)'; resultEl.style.color = 'var(--danger)'; }
  };

  // ── Collect Payload ────────────────────────────────────────────────────

  window.collectPayload = function () {
    return {
      environment: ($('environment') || {}).value || 'production',
      username: ($('username') || {}).value, password: ($('password') || {}).value,
      token: ($('token') || {}).value, base_url: ($('baseUrl') || {}).value,
      preset: ($('preset') || {}).value,
      settings: {
        region: ($('region') || {}).value, universe: ($('universe') || {}).value,
        delay: Number(($('delay') || {}).value) || 1, neutralization: ($('neutralization') || {}).value,
        instrumentType: ($('instrumentType') || {}).value, alphaType: ($('alphaType') || {}).value,
        decay: Number(($('decay') || {}).value) || 0, truncation: Number(($('truncation') || {}).value) || 0,
        pasteurization: ($('pasteurization') || {}).value, nanHandling: ($('nanHandling') || {}).value,
        unitHandling: ($('unitHandling') || {}).value, language: ($('language') || {}).value,
      },
      use_assistant_guidance: ($('useAssistantGuidance') || {}).checked,
      assistant_guidance_min_confidence: Number(($('assistantGuidanceMinConfidence') || {}).value) || 0.6,
      assistant_guidance_score_adjustment: ($('assistantGuidanceScoreAdjustment') || {}).checked,
      assistant_guidance_score_min_confidence: Number(($('assistantGuidanceScoreMinConfidence') || {}).value) || 0.6,
      strategy_plugins_enabled: ($('strategyPluginsEnabled') || {}).checked,
    };
  };

  // ── Init ───────────────────────────────────────────────────────────────

  async function init() {
    renderViewTabs();
    updatePanelHeader();

    try {
      var results = await Promise.all([
        Api.get('/api/latest_result').catch(function () { return {}; }),
        Api.get('/api/config').catch(function () { return {}; }),
      ]);
      if (results[0] && results[0].result) renderResult(results[0].result);
      if (results[1] && results[1].config) {
        S.set('config', results[1].config);
        if (typeof window.renderStrategyPolicy === 'function') window.renderStrategyPolicy(results[1].config);
      }
    } catch (e) { /* ignore */ }

    loadProfile();
    loadPresets();
    if (typeof window.loadRedlineReport === 'function') window.loadRedlineReport();
    if (typeof window.loadCheckpointStatus === 'function') window.loadCheckpointStatus();
    if (typeof window.loadCheckResults === 'function') window.loadCheckResults();

    var toggle = $('displayModeToggle'); if (toggle) toggle.classList.remove('hidden');
    window.renderBusyControls();
  }

  // ── State listener ─────────────────────────────────────────────────────

  S.onUpdate(function (path) {
    if (path === 'isRunning' || path === 'activeJobId') {
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

  // ── Expose ─────────────────────────────────────────────────────────────

  window._app = {
    renderResult: renderResult,
    renderJobSnapshot: renderJobSnapshot,
    renderAll: renderAll,
    loadConfig: window.loadConfig,
    loadProfile: loadProfile,
    loadCheckResults: function () {
      Api.get('/api/check_results').then(function (data) { if (data && data.check_results) S.set('checkResults', data.check_results); }).catch(function () {});
    },
    loadCloudSnapshot: function () {
      Api.get('/api/cloud_alphas').then(function (data) { if (data && data.cloud_alphas) S.set('currentResult.cloud_alphas', data.cloud_alphas); }).catch(function () {});
    },
    loadResearchMemory: function () {
      Api.get('/api/research_memory').then(function (data) { if (data) S.set('currentResult.research_memory', data); }).catch(function () {});
    },
  };

  window.renderCurrentView = _renderCurrentView;
  window.renderAll = renderAll;

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else setTimeout(init, 10);
})();
