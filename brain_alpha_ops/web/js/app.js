// brain_alpha_ops/web/js/app.js
// Application entry point: render dispatch, view state, and page-level actions.

(function () {
  'use strict';

  var $ = window.Utils.$;
  var esc = window.Utils.escapeHtml;
  var escapeAttr = window.Utils.escapeAttr;
  var jsStringAttr = window.Utils.jsStringAttr;
  var phaseName = window.Utils.phaseName;
  var Api = window.ApiClient;
  var S = window.AppState;
  var Toast = window.Toast;
  var VM = window.ViewModel;
  var candidateIdentity = VM.candidateIdentity;
  var chooseRuntimeArray = VM.chooseRuntimeArray;
  var expressionFromRow = VM.expressionFromRow;
  var normalizedExpression = VM.normalizedExpression;
  var uniqueBacktestSlots = VM.uniqueBacktestSlots;
  var uniqueBy = VM.uniqueBy;
  var uniqueCandidates = VM.uniqueCandidates;
  var uniqueLifecycle = VM.uniqueLifecycle;

  // Legacy inline handlers in the template call $("id").
  window.$ = $;

  var MAX_RENDERED_ROWS = S.MAX_RENDERED_ROWS || 300;
  var CHECK_STALE_MS = S.CHECK_STALE_MS || 24 * 60 * 60 * 1000;
  var VIEW_ORDER = [
    'candidates',
    'pending_backtest',
    'running_backtest',
    'backtest_rework',
    'passed',
    'submittable',
    'submitted',
    'failed',
    'cloud',
    'research_observability',
    'research_memory',
    'research_knowledge',
    'prompt_runs',
    'sqlite_indexes',
    'robustness',
    'lifecycle',
  ];
  var VIEW_TITLES = {
    candidates: '候选池',
    pending_backtest: '等待回测',
    running_backtest: '回测中',
    backtest_rework: '回测失败/二次融合',
    passed: '达标',
    submittable: '可提交',
    submitted: '已提交',
    failed: '官方不达标',
    cloud: '数据统计',
    lifecycle: '生命周期',
    research_memory: 'Research Memory',
  };
  VIEW_TITLES.research_observability = 'Observability';
  VIEW_TITLES.research_knowledge = 'Knowledge Base';
  VIEW_TITLES.prompt_runs = 'Prompt Ledger';
  VIEW_TITLES.sqlite_indexes = 'SQLite Index';
  VIEW_TITLES.robustness = 'Robustness';

  var activeFilter = '';
  var rowCache = new Map();
  var presets = {};
  var syncInFlight = false;
  var batchCheckJobId = '';
  var submitInFlight = false;
  var selectedSubmitIds = new Set();
  var lastSubmitPayload = null;
  var lastSubmitResults = [];
  var syncStartedAt = 0;
  var checkStartedAt = 0;
  var syncCountdownTimer = null;
  var checkCountdownTimer = null;
  var lastSyncProgressSnapshot = null;
  var lastCheckProgressSnapshot = null;
  var progressEtaState = {};
  var syncCountdownState = { key: '', deadline: 0, lastPoint: null, lastCurrent: null, lastPercent: null };
  var checkCountdownState = { key: '', deadline: 0, lastPoint: null, lastCurrent: null, lastPercent: null };
  var backtestCountdownTimer = null;
  var lastRenderedBacktestSlots = [];
  var assistantGenerateInFlight = false;
  var assistantGuidanceSaveInFlight = false;
  var assistantGuidancePreviewInFlight = false;
  var assistantDraftInFlight = false;
  var assistantDraftSaveInFlight = false;
  var assistantGuidanceOverride = null;
  var assistantGuidanceOverrideText = '';

  function toast(message, type, duration) {
    if (Toast && Toast.toast) Toast.toast(String(message || ''), type || 'info', duration);
  }

  function setVal(id, value) {
    var el = $(id);
    if (el && value !== undefined && value !== null) el.value = value;
  }

  function num(value, digits) {
    if (value === undefined || value === null || value === '') return '-';
    var n = Number(value);
    if (!Number.isFinite(n)) return String(value);
    return n.toFixed(digits === undefined ? 1 : digits);
  }

  function rowId(item) {
    return String((item.kind || '') + ':' + (item.id || '')).replace(/[^a-zA-Z0-9_-]/g, '_');
  }

  function safeClassTokens(value) {
    return String(value || '')
      .split(/\s+/)
      .filter(function (token) { return /^[a-zA-Z0-9_-]+$/.test(token); })
      .join(' ');
  }

  function safeStatActionHandler(handler) {
    var allowed = {
      'refreshAssistantContext()': true,
      'openAssistantContext()': true,
      'copyAssistantPrompt()': true,
      'copyAssistantRequest()': true,
      'refreshAssistantGuidance()': true,
      'openAssistantGuidance()': true,
      'openSqliteLookupDetail()': true,
      'openRobustnessDetail()': true,
    };
    return allowed[String(handler || '')] ? String(handler) : '';
  }

  function currentSummary() {
    return S.get('currentResult.summary') || {};
  }

  function currentCandidates() {
    return S.get('currentResult.candidates') || [];
  }

  function currentBacktests() {
    return S.get('currentResult.backtests') || [];
  }

  function currentCloudAlphas() {
    return S.get('currentResult.cloud_alphas') || [];
  }

  function currentResearchMemory() {
    return S.get('currentResult.research_memory') || {};
  }

  function currentResearchKnowledge() {
    return S.get('currentResult.research_knowledge') || {};
  }

  function currentResearchObservability() {
    return S.get('currentResult.research_observability') || {};
  }

  function currentPromptRuns() {
    return S.get('currentResult.prompt_runs') || {};
  }

  function currentSqliteIndexes() {
    return S.get('currentResult.sqlite_indexes') || {};
  }

  function currentSqliteLookup() {
    return S.get('currentResult.sqlite_lookup') || {};
  }

  function currentRobustnessSnapshot() {
    return S.get('currentResult.robustness_snapshot') || {};
  }

  function currentObservabilityGenerationGuidance() {
    var summary = currentSummary();
    var throttle = summary.observability_throttle || {};
    return summary.observability_generation_guidance || throttle.generation_guidance || {};
  }

  function currentObservabilityOfficialCallGuard(snapshot) {
    snapshot = snapshot || {};
    if (snapshot.official_call_guard && snapshot.official_call_guard.schema_version) return snapshot.official_call_guard;
    var summary = currentSummary();
    var throttle = summary.observability_throttle || {};
    return summary.observability_official_call_guard || throttle.official_call_guard || {};
  }

  function currentAssistantContext() {
    return S.get('currentResult.assistant_context') || {};
  }

  function currentAssistantGuidance() {
    return S.get('currentResult.assistant_guidance') || {};
  }

  function currentLifecycle() {
    return S.get('currentResult.lifecycle_records') || [];
  }

  function checkResults() {
    return S.get('checkResults') || {};
  }

  function configuredBudget() {
    return S.get('config.budget') || {};
  }

  function configuredBacktestSlotLimit() {
    var summary = currentSummary();
    var budget = configuredBudget();
    var policy = summary.official_call_policy || {};
    var explicit = firstFiniteNumber(
      summary.backtest_slot_limit,
      policy.active_backtest_slot_limit,
      policy.effective_backtest_slot_limit
    );
    if (explicit !== null) return Math.max(1, Math.round(explicit));

    var limits = [
      firstFiniteNumber(policy.official_backtest_batch_size, budget.official_backtest_batch_size),
      firstFiniteNumber(policy.max_official_simulations_per_cycle, budget.max_official_simulations_per_cycle),
      firstFiniteNumber(policy.max_official_concurrent_simulations, budget.max_official_concurrent_simulations),
    ].filter(function (value) { return value !== null; });
    if (limits.length) return Math.max(1, Math.round(Math.min.apply(Math, limits)));
    return 3;
  }

  function hasOwn(obj, key) {
    return Boolean(obj && Object.prototype.hasOwnProperty.call(obj, key));
  }

  function hasDataObject(obj) {
    return Boolean(obj && typeof obj === 'object' && Object.keys(obj).length);
  }

  function uniqueRowsByAlpha(rows) {
    return uniqueBy(rows, function (item) { return candidateIdentity(item.raw || {}) || item.id || ''; });
  }

  function uniqueRowsById(rows) {
    return uniqueBy(rows, function (item) { return (item.kind || '') + ':' + (item.id || candidateIdentity(item.raw || {})); });
  }

  function finiteNumber(value) {
    if (value === undefined || value === null || value === '') return null;
    var n = Number(value);
    return Number.isFinite(n) ? n : null;
  }

  function firstFiniteNumber() {
    for (var i = 0; i < arguments.length; i += 1) {
      var n = finiteNumber(arguments[i]);
      if (n !== null) return n;
    }
    return null;
  }

  function firstPositiveFiniteNumber() {
    for (var i = 0; i < arguments.length; i += 1) {
      var n = finiteNumber(arguments[i]);
      if (n !== null && n > 0) return n;
    }
    return null;
  }

  function isSkippedCloudSync(cloud) {
    var status = String((cloud || {}).status || (cloud || {}).phase || '').toLowerCase();
    return status === 'skipped' || status === 'not_started';
  }

  function cloudSyncStatus(cloud) {
    cloud = cloud || {};
    return String(cloud.phase || cloud.status || cloud.status_code || '').trim().toLowerCase();
  }

  function liveCloudSyncProgress() {
    var live = S.get('liveProgress') || {};
    var progress = live.data || {};
    return ((progress.data || {}).cloud_sync || progress.cloud_sync || {});
  }

  function isActiveCloudSync(cloud) {
    cloud = cloud || {};
    var status = cloudSyncStatus(cloud);
    var terminal = ['completed', 'synced', 'failed', 'skipped'].indexOf(status) !== -1;
    if (terminal) return false;
    if (['auth', 'scan', 'merge', 'running', 'cloud_sync'].indexOf(status) !== -1) return true;
    return firstPositiveFiniteNumber(cloud.scanned, cloud.current, cloud.total, cloud.expected_total) !== null;
  }

  function isEmptyCloudSyncSnapshot(cloud, rows) {
    cloud = cloud || {};
    var status = cloudSyncStatus(cloud);
    if (status === 'empty') return true;
    if (['completed', 'synced', 'failed', 'skipped'].indexOf(status) !== -1) return false;
    if (Array.isArray(rows) && rows.length > 0) return false;
    var hasProgress = firstPositiveFiniteNumber(cloud.scanned, cloud.current, cloud.total, cloud.expected_total) !== null;
    var hasCount = firstPositiveFiniteNumber(cloud.count, cloud.loaded) !== null;
    return !hasProgress && !hasCount && (!Object.keys(cloud).length || ['loaded', 'not_started', ''].indexOf(status) !== -1);
  }

  function mergeCloudSyncSummary(previous, incoming, rows) {
    previous = previous || {};
    incoming = incoming || {};
    var liveCloud = liveCloudSyncProgress();
    var active = isActiveCloudSync(liveCloud) ? Object.assign({}, previous, liveCloud) : previous;
    if (isActiveCloudSync(active) && isEmptyCloudSyncSnapshot(incoming, rows)) {
      return Object.assign({}, incoming, active);
    }
    if (!Object.keys(incoming).length && Object.keys(active).length) return Object.assign({}, active);
    return Object.assign({}, previous, incoming);
  }

  function cloudCachedCount(cloud, fallback) {
    var count = firstPositiveFiniteNumber(
      (cloud || {}).count,
      (cloud || {}).loaded,
      (cloud || {}).scanned,
      (cloud || {}).total,
      fallback
    );
    return count === null ? 0 : Math.round(count);
  }

  function valueOrDefault(value, fallback) {
    var n = finiteNumber(value);
    return n !== null ? n : fallback;
  }

  function formatStrategyNumber(value, fallback, suffix) {
    var n = valueOrDefault(value, fallback);
    var text = Number.isInteger(n) ? String(n) : num(n, 2);
    return text + (suffix || '');
  }

  function renderStrategyPolicy(config) {
    var target = $('strategyText');
    if (!target) return;
    var ops = (config || {}).ops || {};
    var budget = ops.budget || {};
    var scoring = ops.scoring || {};
    var thresholds = ops.thresholds || {};
    var api = ops.official_api || {};
    var pluginSpecs = Array.isArray(budget.strategy_plugin_specs) ? budget.strategy_plugin_specs : [];
    var slotLimits = [
      valueOrDefault(budget.official_backtest_batch_size, 3),
      valueOrDefault(budget.max_official_simulations_per_cycle, 3),
      valueOrDefault(budget.max_official_concurrent_simulations, 3),
    ].filter(function (value) { return Number.isFinite(value) && value > 0; });
    var slotLimit = Math.max(1, Math.round(slotLimits.length ? Math.min.apply(Math, slotLimits) : 3));
    if ($('slotPolicyText')) {
      $('slotPolicyText').textContent = slotLimit + ' 槽并发提交 / 间隔轮询';
    }
    var runForever = Boolean(budget.run_forever);
    var items = [
      {
        label: '候选上限',
        value: formatStrategyNumber(budget.max_candidates_per_cycle, 20, ' / 轮'),
        note: '每轮最多生成并评分的候选数',
      },
      {
        label: '池容量',
        value: formatStrategyNumber(budget.retained_alpha_pool_size, 10),
        note: '本地候选池保留上限',
      },
      {
        label: '预检数',
        value: formatStrategyNumber(budget.max_official_validations_per_cycle, 10, ' / 轮'),
        note: '官方表达式预检调用上限',
      },
      {
        label: '回测槽位',
        value: slotLimit + ' 并发槽',
        note: '批量 ' + formatStrategyNumber(budget.official_backtest_batch_size, 3) +
          ' / 周期 ' + formatStrategyNumber(budget.max_official_simulations_per_cycle, 3) +
          ' / 官方并发 ' + formatStrategyNumber(budget.max_official_concurrent_simulations, 3),
      },
      {
        label: '候选阈值',
        value: '预检 ≥ ' + formatStrategyNumber(budget.min_prior_score_for_official_validation, 60) +
          '，回测 ≥ ' + formatStrategyNumber(budget.min_prior_score_for_official_simulation, 70),
        note: '基于本地评分进入官方流程',
        wide: true,
      },
      {
        label: '官方硬阈值',
        value: 'Sharpe ≥ ' + formatStrategyNumber(thresholds.min_sharpe, 1.25) +
          '，Fitness ≥ ' + formatStrategyNumber(thresholds.min_fitness, 1.0) +
          '，Turnover ' + formatStrategyNumber(thresholds.min_turnover, 0.01) +
          '-' + formatStrategyNumber(thresholds.platform_max_turnover, 0.70),
        note: '用于回测后质量门禁展示',
        wide: true,
      },
      {
        label: '连续生产',
        value: runForever ? '开启' : '单轮',
        note: runForever ? '按暂停间隔持续生产' : '达到配置轮次后停止',
      },
      {
        label: '轮询/暂停',
        value: formatStrategyNumber(api.poll_interval_seconds, 6, ' 秒') +
          ' / ' + formatStrategyNumber(budget.cycle_pause_seconds, 2, ' 秒'),
        note: '回测轮询间隔 / 生产循环间隔',
      },
      {
        label: 'Guidance 排序',
        value: scoring.assistant_guidance_score_adjustment_enabled === false
          ? 'Off'
          : ('+' + formatStrategyNumber(scoring.assistant_guidance_score_bonus_cap, 4) +
            ' / -' + formatStrategyNumber(scoring.assistant_guidance_score_penalty_cap, 5) +
            ' | c>=' + formatStrategyNumber(scoring.assistant_guidance_score_min_confidence, 0.6) +
            ' | n>=' + formatStrategyNumber(scoring.assistant_guidance_score_min_outcome_count, 1)),
        note: '仅影响本地排序；官方指标到位后不改实证评分',
        wide: true,
      },
    ];
    items.push({
      label: 'Strategy Plugins',
      value: budget.strategy_plugins_enabled ? ('On | ' + pluginSpecs.length + ' specs') : 'Off',
      note: pluginSpecs.length ? pluginSpecs.join(', ') : 'No plugin specs configured',
      wide: true,
    });
    target.innerHTML = items.map(function (item) {
      return '<div class="strategy-item' + (item.wide ? ' wide' : '') + '">' +
        '<div class="strategy-label">' + esc(item.label) + '</div>' +
        '<div class="strategy-value">' + esc(item.value) + '</div>' +
        '<div class="strategy-note">' + esc(item.note) + '</div>' +
      '</div>';
    }).join('');
  }

  function metricNumber(metrics, key) {
    if (!hasOwn(metrics, key)) return null;
    return finiteNumber(metrics[key]);
  }

  function hasOfficialMetrics(candidate) {
    return hasDataObject((candidate || {}).official_metrics) || hasDataObject((candidate || {}).metrics);
  }

  function extractOfficialMetrics(row) {
    row = row || {};
    var metrics = Object.assign({}, row.official_metrics || row.metrics || {});
    var raw = row.raw || {};
    var rawIs = raw.is || row.is || {};
    [
      'sharpe',
      'fitness',
      'turnover',
      'returns',
      'drawdown',
      'margin',
      'correlation',
      'weight_concentration',
      'sub_universe_sharpe',
      'pass_fail',
    ].forEach(function (key) {
      if (!hasOwn(metrics, key) && hasOwn(rawIs, key)) metrics[key] = rawIs[key];
    });
    if (!hasOwn(metrics, 'sub_universe_sharpe') && Array.isArray(rawIs.checks)) {
      var subCheck = rawIs.checks.find(function (item) { return item && item.name === 'LOW_SUB_UNIVERSE_SHARPE'; });
      if (subCheck && hasOwn(subCheck, 'value')) metrics.sub_universe_sharpe = subCheck.value;
    }
    if (Array.isArray(rawIs.checks)) {
      metrics._alpha_checks = rawIs.checks;
      var subUniverseCheck = rawIs.checks.find(function (item) { return item && item.name === 'LOW_SUB_UNIVERSE_SHARPE'; });
      if (subUniverseCheck && hasOwn(subUniverseCheck, 'value')) {
        var currentSub = finiteNumber(metrics.sub_universe_sharpe);
        if (currentSub === null || currentSub === 0) metrics.sub_universe_sharpe = subUniverseCheck.value;
      }
    }
    return metrics;
  }

  function scorecardFromMetrics(metrics, fallbackScore) {
    metrics = metrics || {};
    var total = firstFiniteNumber(cloudMetricScore(metrics), fallbackScore, 0);
    var checkGate = officialCheckGate(metrics);
    var empiricalItems = [
      ['sharpe', metricNumber(metrics, 'sharpe'), 1.25, 25, '>='],
      ['fitness', metricNumber(metrics, 'fitness'), 1.0, 20, '>='],
      ['turnover', metricNumber(metrics, 'turnover'), [0.01, 0.7], 15, 'between'],
      ['returns', metricNumber(metrics, 'returns'), 0, 10, '>'],
      ['drawdown', metricNumber(metrics, 'drawdown'), 0.3, 10, '<='],
      ['correlation', metricNumber(metrics, 'correlation'), 0.7, 15, '<='],
    ].map(function (row) {
      var actual = row[1];
      var passed = false;
      if (actual !== null) {
        if (row[4] === 'between') passed = actual >= row[2][0] && actual <= row[2][1];
        else if (row[4] === '>=') passed = actual >= row[2];
        else if (row[4] === '<=') passed = actual <= row[2];
        else if (row[4] === '>') passed = actual > row[2];
      }
      return {
        name: row[0],
        actual: actual,
        target: row[2],
        passed: passed,
        points: row[3],
        score: passed ? row[3] : 0,
      };
    });
    var passFailPassed = String(metrics.pass_fail || '').toUpperCase() === 'PASS';
    empiricalItems.push({
      name: 'pass_fail',
      actual: metrics.pass_fail || '',
      target: 'PASS',
      passed: passFailPassed,
      points: 5,
      score: passFailPassed ? 5 : 0,
    });
    var checklistScore = passFailPassed ? 100 : 0;
    if (checkGate.status === 'failed') checklistScore = 0;
    else if (checkGate.status === 'pending') checklistScore = 50;
    var checklistItems = [{
      name: 'official_pass',
      actual: metrics.pass_fail || '',
      target: 'PASS',
      passed: passFailPassed,
      points: 50,
      score: passFailPassed ? 50 : 0,
      meaning: 'BRAIN Pass/Fail result.',
    }];
    if (checkGate.rows.length) {
      checkGate.rows.forEach(function (row) {
        checklistItems.push({
          name: row.name,
          actual: row.result || '-',
          target: 'PASS',
          passed: row.result === 'PASS',
          points: 50 / checkGate.rows.length,
          score: row.result === 'PASS' ? 50 / checkGate.rows.length : 0,
          meaning: 'Official Alpha check.',
        });
      });
    }
    return {
      schema_version: 'ui-metric-scorecard-v1',
      total_score: total,
      decision_band: metricDecisionBand(total, checkGate),
      score_basis: hasDataObject(metrics) ? 'ui_metric_estimate' : 'missing_metrics',
      local_rank_score: total,
      prior: { score: 0, dimensions: {}, weights: {}, source: 'not_used_for_metric_score' },
      empirical: { score: total, items: empiricalItems, status: hasDataObject(metrics) ? 'metric_snapshot' : 'missing_official_metrics' },
      submission_checklist: { score: Math.round(checklistScore * 100) / 100, items: checklistItems },
      official_check_gate: checkGate,
      calibration: { sample_weight: hasDataObject(metrics) ? 1.0 : 0.0, purpose: '基于可用官方指标的本地展示分，不是 BRAIN 官方总评分；待定或失败的官方硬检查会降低/封顶。' },
    };
  }

  function metricDecisionBand(total, checkGate) {
    if (checkGate && checkGate.status === 'failed') return 'official_check_failed';
    if (checkGate && checkGate.status === 'pending') return 'official_check_pending';
    if (total >= 85) return 'submit_candidate';
    if (total >= 70) return 'optimize_before_submit';
    if (total >= 50) return 'research_only';
    return 'abandon_or_rebuild';
  }

  function renderResult(result) {
    result = result || {};
    var previousSummary = currentSummary();
    var summary = Object.assign({}, result.summary || {});
    var candidates = uniqueCandidates(chooseRuntimeArray(summary.candidates, result.candidates, currentCandidates()));
    var pending = uniqueCandidates(chooseRuntimeArray(summary.pending_backtest_candidates, null, S.get('currentResult.pending_backtest_candidates')));
    var passed = uniqueCandidates(chooseRuntimeArray(summary.passed_candidates, null, derivePassedCandidates(candidates)));
    var incomingCloudRows = Array.isArray(summary.cloud_alphas) ? summary.cloud_alphas : null;
    var existingCloudRows = currentCloudAlphas();
    var incomingCloudSync = summary.cloud_sync || {};
    summary.cloud_sync = mergeCloudSyncSummary(previousSummary.cloud_sync, incomingCloudSync, incomingCloudRows);
    incomingCloudSync = summary.cloud_sync;
    var preserveCloudCache = Boolean(
      incomingCloudRows &&
      incomingCloudRows.length === 0 &&
      existingCloudRows.length > 0 &&
      isSkippedCloudSync(incomingCloudSync)
    );
    var cloud = uniqueCandidates(preserveCloudCache ? existingCloudRows : (incomingCloudRows || existingCloudRows));
    if (preserveCloudCache) {
      var cachedSync = Object.assign({}, previousSummary.cloud_sync || {});
      var cachedCount = cloudCachedCount(cachedSync, cloud.length);
      summary.cloud_sync = Object.assign({}, cachedSync, {
        status: cachedSync.status || 'loaded',
        count: cachedCount || cloud.length,
        run_status: incomingCloudSync.status || 'skipped',
        run_range: incomingCloudSync.range || '',
        run_warning: incomingCloudSync.warning || '',
      });
      summary.cloud_alphas = cloud;
    }
    var lifecycle = uniqueLifecycle(summary.lifecycle_records || currentLifecycle());
    var backtests = uniqueBacktestSlots(summary.backtest_slots || summary.backtests || summary.backtests_slots || result.backtests || currentBacktests());

    S.set('currentResult.summary', summary);
    S.set('currentResult.candidates', candidates || []);
    S.set('currentResult.pending_backtest_candidates', pending || []);
    S.set('currentResult.passed_candidates', passed || []);
    S.set('currentResult.cloud_alphas', cloud || []);
    S.set('currentResult.lifecycle_records', lifecycle || []);
    S.set('currentResult.backtests', backtests || []);
    renderAll();
  }

  function renderJobSnapshot(job) {
    job = job || {};
    var progress = job.progress || {};
    var data = progress.data || {};
    var result = job.result || {};
    var summary = Object.assign({}, data, result.summary || {});
    var progressCloudSync = Object.assign(
      {},
      summary.cloud_sync || {},
      ((result.summary || {}).cloud_sync || {}),
      data.cloud_sync || {}
    );
    if (Object.keys(progressCloudSync).length) {
      summary.cloud_sync = mergeCloudSyncSummary(currentSummary().cloud_sync, progressCloudSync, summary.cloud_alphas);
    }
    renderResult({
      summary: summary,
      candidates: firstArrayWithItems(summary.candidates, data.candidates, result.candidates) || [],
      backtests: summary.backtests || summary.backtest_slots || [],
    });
    if (summary.cloud_sync) {
      updateSyncProgress(Object.assign(
        {},
        summary.cloud_sync,
        {
          phase: progress.phase === 'cloud_sync' ? 'cloud_sync' : (summary.cloud_sync.phase || summary.cloud_sync.status || progress.phase),
          percent: progress.phase === 'cloud_sync' ? progress.percent : summary.cloud_sync.percent,
          message: progress.phase === 'cloud_sync' ? progress.message : summary.cloud_sync.message,
        }
      ));
    }
  }

  function renderAll() {
    renderInsight();
    renderOpsMonitor();
    renderBacktests(currentBacktests());
    if (typeof window.renderCharts === 'function') window.renderCharts();
    renderCurrentView();
  }

  window.switchView = function (view) {
    if (VIEW_ORDER.indexOf(view) === -1) view = 'candidates';
    activeFilter = '';
    S.set('activeView', view);
    renderCurrentView();
    renderInsight();
  };

  function activeView() {
    return S.get('activeView') || 'candidates';
  }

  function viewTitle(view) {
    return VIEW_TITLES[view] || view || '-';
  }

  function viewHint(view) {
    var hints = {
      candidates: '候选池按排序分降序排序。',
      pending_backtest: '等待回测按本地排序分排队。',
      running_backtest: '仅显示正在等待官方回测结果的槽位。',
      backtest_rework: '回测失败、官方拒绝或需要二次融合的记录。',
      passed: '达标 Alpha 可批量检查后进入可提交队列。',
      submittable: '检查通过且仍在有效期内的 Alpha 可提交。',
      submitted: '展示本地生命周期和云端已提交记录。',
      failed: '展示不达标、拒绝和阻断记录。',
      cloud: '展示云端快照、字段和算子缓存统计。',
      lifecycle: '展示关键生命周期事件。',
    };
    if (view === 'research_memory') return 'Local JSONL research memory: fields, operators, failures, and lineage.';
    if (view === 'research_knowledge') return 'Structured rules, findings, and failures promoted from research evidence.';
    if (view === 'research_observability') return 'Operational snapshot for expression reuse, backtests, structured errors, and JSONL health.';
    if (view === 'prompt_runs') return 'Prompt run ledger with digests and parse status only; raw prompts and responses stay out of the UI.';
    if (view === 'sqlite_indexes') return 'SQLite cache status for expression history, cloud alphas, and backtest records.';
    if (view === 'robustness') return 'Anti-overfit and rolling validation status for candidates that already carry robustness reports.';
    return hints[view] || '';
  }

  function panelBusinessHint(view) {
    var hints = {
      candidates: '候选池按排序分降序展示，仅包含仍可进入后续流程的本地候选。',
      pending_backtest: '等待回测只展示已通过预检、尚未拿到 simulation_id 的 Alpha；官方并发满时显示为容量等待。',
      running_backtest: '回测中只展示已提交并正在等待官方 simulation 结果的槽位。',
      backtest_rework: '展示请求失败、限流/并发延后、重试排队和需要二次融合的回测流程问题。',
      passed: '达标 Alpha 可批量检查后进入可提交队列。',
      submittable: '检查通过且仍在有效期内的 Alpha 可提交。',
      submitted: '展示本地与云端已经提交或运行中的 Alpha。',
      failed: '不达标只展示官方回测后返回 FAIL/硬检查失败的 Alpha，不包含本地淘汰或请求失败。',
      cloud: '展示云端快照、字段和算子缓存统计。',
      lifecycle: '生命周期是关键状态流转审计：同一 Alpha 可有多个阶段事件，但完全相同事件只显示一次。',
    };
    if (view === 'research_memory') return 'Summarizes reusable evidence from candidates, lifecycle, checks, and extracted alpha features.';
    if (view === 'research_knowledge') return 'Shows append-only structured knowledge records filtered by confidence and kind.';
    if (view === 'research_observability') return 'Shows recent expression-index duplication, official backtest health, retryable errors, and local history file status.';
    if (view === 'prompt_runs') return 'Shows LLM prompt run metadata: prompt/context/response digests, model, temperature, and parse outcome.';
    if (view === 'sqlite_indexes') return 'Shows SQLite cache freshness, duplicate expression pressure, and indexed cloud/backtest records.';
    if (view === 'robustness') return 'Summarizes anti-overfit recommendations, rolling validation outcomes, and candidate-level robustness gaps.';
    return hints[view] || viewHint(view);
  }

  function renderCurrentView() {
    var view = activeView();
    renderModuleActions();
    var allRows = filteredRows();
    var rows = allRows.slice(0, MAX_RENDERED_ROWS);
    var tableTitle = $('tableTitle');
    var countPill = $('countPill');
    var sortHint = $('sortHint');
    if (tableTitle) tableTitle.textContent = viewTitle(view);
    if (countPill) countPill.textContent = countText(view, allRows.length);
    if (sortHint) {
      var businessHint = panelBusinessHint(view);
      sortHint.textContent = allRows.length > rows.length
        ? businessHint + ' 当前显示前 ' + rows.length + '/' + allRows.length + ' 条，可用搜索缩小范围。'
        : businessHint;
    }

    renderFilterBar();
    renderCloudStatsPanel(rows);
    renderResearchMemoryPanel(rows);
    renderResearchObservabilityPanel(rows);
    renderResearchKnowledgePanel(rows);
    renderPromptRunLedgerPanel(rows);
    renderSqliteIndexPanel(rows);
    renderRobustnessPanel(rows);
    var tableWrap = $('tableWrap');
    var cloudStatsPanel = $('cloudStatsPanel');
    var candidateTable = $('candidateTable');
    var filterBar = $('filterBar');
    var statsMode = ['cloud', 'research_memory', 'research_observability', 'research_knowledge', 'prompt_runs', 'sqlite_indexes', 'robustness'].indexOf(view) !== -1;
    if (tableWrap) tableWrap.classList.toggle('stats-mode', statsMode);
    if (cloudStatsPanel) cloudStatsPanel.classList.toggle('hidden', !statsMode);
    if (candidateTable) candidateTable.classList.toggle('hidden', statsMode);
    if (filterBar) filterBar.classList.toggle('hidden', statsMode);
    if (statsMode) return;

    cacheRenderedRows(rows);
    var body = $('candidateRows');
    if (!body) return;
    body.innerHTML = rows.length
      ? rows.map(rowHtml).join('')
      : '<tr><td colspan="8" style="text-align:center;color:var(--muted);padding:22px">' + esc(emptyText(view)) + '</td></tr>';
  }

  window.renderCurrentView = renderCurrentView;

  function countText(view, count) {
    var summary = currentSummary();
    var budget = configuredBudget();
    if (view === 'candidates') return '候选池 ' + count + '/' + (summary.retained_pool_limit || budget.retained_alpha_pool_size || 10);
    if (view === 'running_backtest') return '回测中 ' + activeBacktestCount(currentBacktests()) + '/' + configuredBacktestSlotLimit();
    return viewTitle(view) + ' ' + count;
  }

  function cacheRenderedRows(rows) {
    rowCache = new Map();
    rows.forEach(function (item) {
      rowCache.set((item.kind || '') + ':' + (item.id || ''), item);
    });
  }

  function renderCloudStatsPanel(rows) {
    var panel = $('cloudStatsPanel');
    if (!panel || activeView() !== 'cloud') return;
    var items = rows.map(function (item) { return item.raw || {}; });
    if (!items.length) {
      panel.innerHTML = '<div class="stats-card"><div class="stat-label">数据统计</div><div class="stat-value">暂无</div><div class="stat-note">' + esc(emptyText('cloud')) + '</div></div>';
      return;
    }
    panel.innerHTML = items.map(function (row, index) {
      var value = row.value === undefined || row.value === null ? '-' : String(row.value);
      var cls = index <= 2 ? 'primary' : (/失败|不达标|过期/.test(row.name || '') ? 'warning' : '');
      var action = index === 0 ? '<button class="small secondary" onclick="event.stopPropagation(); openCloudRawDetail()">查看明细</button>' : '';
      return '<div class="stats-card ' + cls + '">' +
        '<div class="stat-label">' + esc(row.name || '') + '</div>' +
        '<div class="stat-value">' + esc(value) + '</div>' +
        '<div class="stat-note">' + esc(row.note || row.name || '') + '</div>' +
        action +
      '</div>';
    }).join('');
  }

  function percentText(value) {
    var n = Number(value);
    if (!Number.isFinite(n)) return '-';
    return Math.round(n * 100) + '%';
  }

  function bucketPreview(rows) {
    rows = Array.isArray(rows) ? rows : [];
    return rows.slice(0, 3).map(function (row) {
      return String(row.name || '-') + ' ' + String(row.count || 0) + ' (' + percentText(row.success_rate) + ')';
    }).join(' | ') || '-';
  }

  function observabilityFeaturePreview(rows, labelKey) {
    rows = Array.isArray(rows) ? rows : [];
    return rows.slice(0, 3).map(function (row) {
      var label = row[labelKey] || row.name || row.reason || row.error_code || row.family || row.window || '-';
      var value = row.unique_expression_count !== undefined ? row.unique_expression_count : row.count;
      return String(label) + ' x' + String(value || 0);
    }).join(' | ') || '-';
  }

  function observabilityDictPreview(data) {
    data = data || {};
    return Object.keys(data).slice(0, 4).map(function (key) {
      return key + ':' + data[key];
    }).join(' | ') || '-';
  }

  function dictPreview(data) {
    return observabilityDictPreview(data);
  }

  function sqliteManifestPreview(manifest) {
    var sources = (manifest || {}).sources || {};
    return Object.keys(sources).slice(0, 4).map(function (name) {
      var row = sources[name] || {};
      return name.replace('.jsonl', '') + ':' + String(row.indexed_count || 0) + '/' + String(row.record_count || 0);
    }).join(' | ') || '-';
  }

  function researchObservabilityCards(snapshot) {
    snapshot = snapshot || {};
    var generationGuidance = currentObservabilityGenerationGuidance();
    var officialCallGuard = currentObservabilityOfficialCallGuard(snapshot);
    if (snapshot.ok !== true && !snapshot.expression_index && !generationGuidance.schema_version && !officialCallGuard.schema_version) return [];
    var expression = snapshot.expression_index || {};
    var backtests = snapshot.backtests || {};
    var errors = snapshot.errors || {};
    var sqlite = snapshot.sqlite_cache || {};
    var jsonl = snapshot.jsonl || {};
    var health = snapshot.health || {};
    var partialErrors = Array.isArray(snapshot.partial_errors) ? snapshot.partial_errors : [];
    var jsonlNames = Object.keys(jsonl);
    var cards = [
      {
        name: 'Health Risk',
        value: health.risk_level || 'unknown',
        note: observabilityFeaturePreview((health.health_flags || []).map(function (flag) { return { name: flag, count: 1 }; }), 'name'),
        cls: health.risk_level === 'blocked' || health.risk_level === 'high' ? 'warning' : 'primary',
      },
      {
        name: 'Blocking Flags',
        value: (health.blocking_flags || []).length,
        note: (health.blocking_flags || []).slice(0, 3).join(' | ') || 'None',
        cls: (health.blocking_flags || []).length ? 'warning' : 'primary',
      },
      {
        name: 'Partial Errors',
        value: partialErrors.length,
        note: partialErrors.slice(0, 2).map(function (row) {
          return String(row.component || '-') + ': ' + String(row.error || '-');
        }).join(' | ') || 'None',
        cls: partialErrors.length ? 'warning' : 'primary',
      },
      {
        name: 'Generation Guidance',
        value: generationGuidance.active ? 'Active' : 'Idle',
        note: 'status ' + String(generationGuidance.status || '-') +
          ' | avoid ' + String(generationGuidance.avoid_expression_count || 0) +
          ' | ratio ' + percentText(generationGuidance.duplicate_ratio || 0) +
          ' | ' + String(generationGuidance.generator_type || '-'),
        cls: generationGuidance.active ? 'warning' : 'primary',
      },
      {
        name: 'Official Guard',
        value: officialCallGuard.blocked_count || 0,
        note: 'validation ' + String(officialCallGuard.validation_blocked_count || 0) +
          ' | simulation ' + String(officialCallGuard.simulation_blocked_count || 0) +
          ' | latest ' + String(officialCallGuard.last_blocked_alpha_id || '-'),
        cls: Number(officialCallGuard.blocked_count || 0) ? 'warning' : 'primary',
      },
      {
        name: 'Expression Records',
        value: expression.total_expression_records || 0,
        note: 'unique ' + String(expression.unique_expression_count || 0) + ' | sources ' + observabilityDictPreview(expression.source_counts),
        cls: 'primary',
      },
      {
        name: 'Duplicate Fingerprints',
        value: expression.duplicate_expression_count || 0,
        note: 'ratio ' + percentText(expression.duplicate_ratio || 0) + ' | ' + observabilityFeaturePreview(expression.top_duplicates, 'expression_canonical'),
        cls: expression.duplicate_expression_count ? 'warning' : 'primary',
      },
      {
        name: 'Backtest Failure Rate',
        value: percentText(backtests.failure_rate || 0),
        note: 'failed ' + String(backtests.failed_count || 0) + '/' + String(backtests.total || 0) + ' | completed ' + percentText(backtests.completion_rate || 0),
        cls: Number(backtests.failure_rate || 0) > 0.2 ? 'warning' : 'primary',
      },
      {
        name: 'Retryable Errors',
        value: errors.retryable_count || 0,
        note: 'total ' + String(errors.total || 0) + ' | ' + observabilityDictPreview(errors.category_counts),
        cls: errors.retryable_count ? 'warning' : '',
      },
      {
        name: 'Top Fields',
        value: (expression.top_fields || []).length,
        note: observabilityFeaturePreview(expression.top_fields, 'name'),
      },
      {
        name: 'Top Operators',
        value: (expression.top_operators || []).length,
        note: observabilityFeaturePreview(expression.top_operators, 'name'),
      },
      {
        name: 'Backtest Actions',
        value: Object.keys(backtests.action_counts || {}).length,
        note: observabilityDictPreview(backtests.action_counts),
      },
      {
        name: 'Failure Patterns',
        value: (backtests.failure_patterns || []).length,
        note: observabilityFeaturePreview(backtests.failure_patterns, 'reason'),
        cls: (backtests.failure_patterns || []).length ? 'warning' : '',
      },
      {
        name: 'Error Codes',
        value: Object.keys(errors.code_counts || {}).length,
        note: observabilityDictPreview(errors.code_counts),
        cls: errors.total ? 'warning' : '',
      },
      {
        name: 'SQLite Cache',
        value: sqlite.exists ? (sqlite.row_count || 0) : 'Off',
        note: sqlite.exists ? ('age ' + formatDuration(sqlite.age_seconds || 0) + (sqlite.error ? ' | ' + sqlite.error : '')) : 'Optional cache not built; JSONL remains source of truth.',
      },
      {
        name: 'JSONL Files',
        value: jsonlNames.length,
        note: jsonlNames.map(function (name) {
          var item = jsonl[name] || {};
          return name.replace('.jsonl', '') + ':' + (item.parsed_count || 0);
        }).join(' | ') || '-',
      },
      {
        name: 'Latest Backtests',
        value: (backtests.latest || []).length,
        note: (backtests.latest || []).slice(0, 3).map(function (row) {
          return String(row.alpha_id || row.simulation_id || row.action || '-') + ' ' + String(row.status || '');
        }).join(' | ') || '-',
      },
    ];
    ((health.actions || snapshot.recommendations || [])).slice(0, 3).forEach(function (recommendation, index) {
      cards.push({ name: 'Recommendation ' + (index + 1), value: 'Action', note: String(recommendation || ''), cls: 'primary' });
    });
    return cards;
  }

  function researchMemoryCards(memory) {
    memory = memory || {};
    if (memory.ok !== true && !hasOwn(memory, 'total_candidates')) return [];
    var assistantContext = currentAssistantContext();
    var assistantGuidance = currentAssistantGuidance();
    var latestGuidance = assistantGuidance.guidance || {};
    var guidanceOperators = Array.isArray(latestGuidance.top_operators) ? latestGuidance.top_operators : [];
    var guidanceWindows = Array.isArray(latestGuidance.preferred_windows) ? latestGuidance.preferred_windows : [];
    var guidanceFields = Array.isArray(latestGuidance.top_fields) ? latestGuidance.top_fields : [];
    var guidanceReady = Boolean(latestGuidance.usable);
    var guidanceBlocked = latestGuidance.reason === 'weak_historical_guidance_outcome' || latestGuidance.historical_outcome_status === 'weak';
    var guidanceState = assistantGuidance.enabled === false ? 'Disabled' : (guidanceReady ? 'Ready' : (guidanceBlocked ? 'Blocked' : 'Empty'));
    var guidanceNote = guidanceReady
      ? ('conf ' + num(latestGuidance.confidence, 2) + ' | fields ' + guidanceFields.slice(0, 3).join(', ') + ' | ops ' + guidanceOperators.slice(0, 3).join(', '))
      : ('history ' + String(assistantGuidance.history_count || 0) + ' | min conf ' + num(assistantGuidance.min_confidence || assistantGuidance.configured_min_confidence || 0, 2) + (latestGuidance.reason ? ' | ' + latestGuidance.reason : ''));
    if (guidanceReady && latestGuidance.historical_outcome_status && latestGuidance.historical_outcome_status !== 'unknown') {
      guidanceNote += ' | outcome ' + latestGuidance.historical_outcome_status;
    }
    var assistantGuidedStats = memory.assistant_guided || {};
    var statusCounts = memory.status_counts || {};
    var statusKeys = Object.keys(statusCounts);
    var failures = Array.isArray(memory.failure_patterns) ? memory.failure_patterns : [];
    var lineage = Array.isArray(memory.lineage) ? memory.lineage : [];
    var cards = [
      {
        name: 'Context Pack',
        value: assistantContext.ok ? 'Ready' : 'Load',
        note: assistantContext.generated_at ? ('Generated ' + assistantContext.generated_at) : 'Prompt-ready LLM context from config, latest result, cloud cache, and memory.',
        cls: 'primary',
        actions: [
          { label: '刷新', handler: 'refreshAssistantContext()' },
          { label: '预览', handler: 'openAssistantContext()' },
          { label: '复制 Prompt', handler: 'copyAssistantPrompt()' },
          { label: 'Copy Request', handler: 'copyAssistantRequest()' },
        ],
      },
      {
        name: 'Assistant Guidance',
        value: guidanceState,
        note: guidanceReady && guidanceWindows.length ? (guidanceNote + ' | windows ' + guidanceWindows.slice(0, 4).join(', ')) : guidanceNote,
        cls: guidanceReady ? 'primary' : '',
        actions: [
          { label: 'Refresh', handler: 'refreshAssistantGuidance()' },
          { label: 'View', handler: 'openAssistantGuidance()' },
        ],
      },
      {
        name: 'Guided Outcomes',
        value: assistantGuidedStats.count || 0,
        note: assistantGuidedStats.count
          ? ('success ' + percentText(assistantGuidedStats.success_rate || 0) + ' | avg score ' + num(assistantGuidedStats.avg_score, 2))
          : 'No persisted assistant-guided candidates yet.',
        cls: assistantGuidedStats.count ? 'primary' : '',
      },
      { name: 'Candidates', value: memory.total_candidates || 0, note: 'Local candidate records', cls: 'primary' },
      { name: 'Lifecycle', value: memory.total_lifecycle_records || 0, note: 'Recorded alpha state transitions', cls: 'primary' },
      { name: 'Checks', value: memory.total_check_records || 0, note: 'Official check records', cls: 'primary' },
      { name: 'Feature Rows', value: memory.total_feature_records || 0, note: 'Extracted feature snapshots' },
      { name: 'Top Fields', value: (memory.fields || []).length, note: bucketPreview(memory.fields) },
      { name: 'Top Operators', value: (memory.operators || []).length, note: bucketPreview(memory.operators) },
      { name: 'Families', value: (memory.families || []).length, note: bucketPreview(memory.families) },
      { name: 'Hypotheses', value: (memory.hypotheses || []).length, note: bucketPreview(memory.hypotheses) },
      {
        name: 'Failure Patterns',
        value: failures.length,
        note: failures.slice(0, 3).map(function (row) { return String(row.reason || '-') + ' x' + String(row.count || 0); }).join(' | ') || '-',
        cls: failures.length ? 'warning' : '',
      },
      {
        name: 'Lineage',
        value: lineage.length,
        note: lineage.slice(0, 3).map(function (row) { return String(row.parent_id || '-') + ' -> ' + String(row.child_count || 0); }).join(' | ') || '-',
      },
      {
        name: 'Statuses',
        value: statusKeys.length,
        note: statusKeys.slice(0, 4).map(function (key) { return key + ':' + statusCounts[key]; }).join(' | ') || '-',
      },
      { name: 'Source', value: memory.source || '-', note: memory.storage_dir || '-' },
    ];
    (memory.recommendations || []).slice(0, 3).forEach(function (recommendation, index) {
      cards.push({ name: 'Recommendation ' + (index + 1), value: 'Action', note: String(recommendation || ''), cls: 'primary' });
    });
    return cards;
  }

  function researchKnowledgeCards(snapshot) {
    snapshot = snapshot || {};
    if (snapshot.ok !== true && !hasOwn(snapshot, 'items')) return [];
    var counts = snapshot.counts || {};
    var items = Array.isArray(snapshot.items) ? snapshot.items : [];
    var cards = [
      { name: 'Knowledge Records', value: snapshot.count || items.length || 0, note: 'Append-only structured research knowledge', cls: (snapshot.count || items.length) ? 'primary' : '' },
      { name: 'Rules', value: counts.rules || 0, note: 'Reusable constraints and generation rules' },
      { name: 'Findings', value: counts.findings || 0, note: 'Empirical research findings' },
      { name: 'Failures', value: counts.failures || 0, note: 'Known failure modes and blocked patterns', cls: counts.failures ? 'warning' : '' },
      { name: 'Source', value: snapshot.source || '-', note: snapshot.root || '-' },
    ];
    items.slice(0, 5).forEach(function (item, index) {
      cards.push({
        name: 'Knowledge ' + (index + 1),
        value: item.kind || '-',
        note: String(item.title || item.body || item.knowledge_id || '-') + ' | conf ' + num(item.confidence || 0, 2),
        cls: Number(item.confidence || 0) >= 0.7 ? 'primary' : '',
      });
    });
    return cards;
  }

  function promptRunLedgerCards(snapshot) {
    snapshot = snapshot || {};
    if (snapshot.ok !== true && !hasOwn(snapshot, 'items')) return [];
    var items = Array.isArray(snapshot.items) ? snapshot.items : [];
    var parseCounts = {};
    var modelCounts = {};
    items.forEach(function (item) {
      var status = String(item.parse_status || 'unknown');
      var model = String(item.model || 'unknown');
      parseCounts[status] = (parseCounts[status] || 0) + 1;
      modelCounts[model] = (modelCounts[model] || 0) + 1;
    });
    var latest = items[0] || {};
    var cards = [
      { name: 'Prompt Runs', value: snapshot.count || items.length || 0, note: 'Ledger stores digests only; no raw prompt/response text.', cls: items.length ? 'primary' : '' },
      { name: 'Latest Model', value: latest.model || '-', note: latest.timestamp || '-' },
      { name: 'Latest Parse', value: latest.parse_status || '-', note: latest.response_digest ? ('response ' + latest.response_digest) : '-' },
      { name: 'Parse Statuses', value: Object.keys(parseCounts).length, note: dictPreview(parseCounts) },
      { name: 'Models', value: Object.keys(modelCounts).length, note: dictPreview(modelCounts) },
      { name: 'Source', value: snapshot.source || '-', note: snapshot.path || '-' },
    ];
    items.slice(0, 4).forEach(function (item, index) {
      cards.push({
        name: 'Run ' + (index + 1),
        value: item.parse_status || 'unknown',
        note: String(item.model || '-') + ' | prompt ' + String(item.prompt_digest || '-') + ' | context ' + String(item.context_digest || '-'),
        cls: String(item.parse_status || '').toLowerCase() === 'ok' ? 'primary' : 'warning',
      });
    });
    return cards;
  }

  function sqliteIndexCards(snapshot) {
    snapshot = snapshot || {};
    if (snapshot.ok !== true && !hasOwn(snapshot, 'expression_index') && !hasOwn(snapshot, 'record_index')) return [];
    var expressionIndex = snapshot.expression_index || {};
    var recordIndex = snapshot.record_index || {};
    var exprManifest = expressionIndex.manifest || {};
    var recordManifest = recordIndex.manifest || {};
    var expressionReady = expressionIndex.ok !== false;
    var recordReady = recordIndex.ok !== false;
    var cards = [
      {
        name: 'Expression Index',
        value: expressionReady ? (expressionIndex.total_expression_records || 0) : 'Missing',
        note: expressionReady
          ? ('unique ' + String(expressionIndex.unique_expression_count || 0) + ' | dupes ' + String(expressionIndex.duplicate_expression_count || 0))
          : (expressionIndex.error || 'SQLite expression cache not built'),
        cls: expressionIndex.is_stale ? 'warning' : (expressionReady ? 'primary' : 'warning'),
      },
      {
        name: 'Record Index',
        value: recordReady ? (recordIndex.row_count || 0) : 'Missing',
        note: recordReady ? dictPreview(recordIndex.counts || {}) : (recordIndex.error || 'SQLite record cache not built'),
        cls: recordIndex.is_stale ? 'warning' : (recordReady ? 'primary' : 'warning'),
      },
      {
        name: 'Cache Freshness',
        value: snapshot.has_stale_index ? 'Stale' : (snapshot.has_missing_index ? 'Partial' : 'Fresh'),
        note: 'Expression stale: ' + String(Boolean(expressionIndex.is_stale)) + ' | record stale: ' + String(Boolean(recordIndex.is_stale)),
        cls: snapshot.has_stale_index || snapshot.has_missing_index ? 'warning' : 'primary',
      },
      {
        name: 'Expression Sources',
        value: Object.keys((exprManifest.sources || {})).length,
        note: sqliteManifestPreview(exprManifest),
      },
      {
        name: 'Record Sources',
        value: Object.keys((recordManifest.sources || {})).length,
        note: sqliteManifestPreview(recordManifest),
      },
      { name: 'Source', value: snapshot.source || '-', note: snapshot.storage_dir || '-' },
    ];
    (expressionIndex.duplicates || []).slice(0, 3).forEach(function (item, index) {
      cards.push({
        name: 'Duplicate ' + (index + 1),
        value: item.count || 0,
        note: String(item.expression_canonical || item.expression_fingerprint || '-') + ' | sources ' + dictPreview(item.sources || {}),
        cls: 'warning',
      });
    });
    var lookup = currentSqliteLookup();
    var expressionLookup = lookup.expression || {};
    var recordLookup = lookup.record || {};
    if (expressionLookup.ok) {
      cards.push({
        name: 'Expression Lookup',
        value: expressionLookup.exact_match ? 'Exact' : 'Similar',
        note: 'exact ' + String(expressionLookup.exact_count || 0) + ' | similar ' + String(expressionLookup.similar_count || 0),
        cls: expressionLookup.exact_match ? 'primary' : '',
        actions: [{ label: 'Details', handler: 'openSqliteLookupDetail()' }],
      });
    }
    if (recordLookup.ok) {
      cards.push({
        name: 'Record Lookup',
        value: recordLookup.count || 0,
        note: String(recordLookup.alpha_id || '-') + ' | ' + (recordLookup.records || []).slice(0, 3).map(function (row) { return String(row.kind || '-') + ':' + String(row.status || row.action || '-'); }).join(' | '),
        cls: recordLookup.count ? 'primary' : '',
        actions: [{ label: 'Details', handler: 'openSqliteLookupDetail()' }],
      });
    }
    return cards;
  }

  function robustnessCards(snapshot) {
    snapshot = snapshot || buildRobustnessSnapshot();
    if (snapshot.ok !== true && !hasOwn(snapshot, 'candidate_count')) return [];
    var cards = [
      { name: 'Candidates', value: snapshot.candidate_count || 0, note: 'Current retained candidates scanned', cls: 'primary' },
      { name: 'Anti-overfit Reports', value: snapshot.anti_report_count || 0, note: dictPreview(snapshot.anti_recommendations || {}) },
      { name: 'Rolling Reports', value: snapshot.rolling_report_count || 0, note: dictPreview(snapshot.rolling_statuses || {}) },
      { name: 'Missing Reports', value: snapshot.missing_report_count || 0, note: 'Candidates without one or both robustness reports', cls: snapshot.missing_report_count ? 'warning' : '' },
      { name: 'Blocked', value: snapshot.blocked_count || 0, note: 'Anti-overfit review or rolling validation failed', cls: snapshot.blocked_count ? 'warning' : '' },
      { name: 'On-demand Review', value: 'API', note: 'Use the candidate id input above or batch the visible examples.', actions: [{ label: 'Details', handler: 'openRobustnessDetail()' }] },
    ];
    (snapshot.examples || []).slice(0, 5).forEach(function (item, index) {
      cards.push({
        name: 'Candidate ' + (index + 1),
        value: item.alpha_id || '-',
        note: 'anti ' + String(item.anti || '-') + ' | rolling ' + String(item.rolling || '-') + ' | score ' + String(item.score || '-'),
        cls: item.blocked ? 'warning' : '',
      });
    });
    return cards;
  }

  function buildRobustnessSnapshot() {
    var candidates = uniqueCandidates(currentCandidates().concat(S.get('currentResult.passed_candidates') || []));
    var antiCounts = {};
    var rollingCounts = {};
    var examples = [];
    var antiReportCount = 0;
    var rollingReportCount = 0;
    var blockedCount = 0;
    var missingCount = 0;
    candidates.forEach(function (candidate) {
      var sub = (candidate || {}).submission || {};
      var anti = sub.anti_overfit_report || candidate.anti_overfit_report || {};
      var rolling = sub.rolling_validation_report || candidate.rolling_validation_report || {};
      var antiKey = anti.recommendation || anti.status || (anti.schema_version ? 'unknown' : 'missing');
      var rollingKey = rolling.status || (rolling.schema_version ? 'unknown' : 'missing');
      if (anti.schema_version) antiReportCount += 1;
      if (rolling.schema_version) rollingReportCount += 1;
      antiCounts[antiKey] = (antiCounts[antiKey] || 0) + 1;
      rollingCounts[rollingKey] = (rollingCounts[rollingKey] || 0) + 1;
      var blocked = String(antiKey).toLowerCase().indexOf('review') !== -1 || rolling.passed === false && rolling.status !== 'insufficient_data';
      if (blocked) blockedCount += 1;
      if (!anti.schema_version || !rolling.schema_version) missingCount += 1;
      if (examples.length < 8) {
        examples.push({
          alpha_id: candidateIdentity(candidate),
          anti: antiKey,
          rolling: rollingKey,
          score: submissionRankScore(candidate),
          blocked: blocked,
        });
      }
    });
    return {
      ok: true,
      schema_version: 'robustness_frontend_snapshot.v1',
      candidate_count: candidates.length,
      anti_report_count: antiReportCount,
      rolling_report_count: rollingReportCount,
      missing_report_count: missingCount,
      blocked_count: blockedCount,
      anti_recommendations: antiCounts,
      rolling_statuses: rollingCounts,
      examples: examples,
    };
  }

  function sqliteLookupControlsHtml() {
    var lookup = currentSqliteLookup();
    var expression = lookup.expression || {};
    var record = lookup.record || {};
    var expressionNote = expression.ok
      ? ('exact ' + String(expression.exact_count || 0) + ' / similar ' + String(expression.similar_count || 0))
      : (expression.error || 'Enter an expression to query the expression cache.');
    var recordNote = record.ok
      ? ('records ' + String(record.count || 0))
      : (record.error || 'Enter alpha, official alpha, or simulation id.');
    return '<div class="stats-card primary">' +
      '<div class="stat-label">Interactive Lookup</div>' +
      '<div class="stat-value">SQLite</div>' +
      '<div class="stat-note">' + esc(expressionNote + ' | ' + recordNote) + '</div>' +
      '<div class="action-row" style="margin-top:8px;gap:8px;flex-wrap:wrap">' +
      '<input id="sqliteExpressionLookupInput" placeholder="Expression lookup" style="min-width:220px;max-width:360px">' +
      '<button class="secondary small" onclick="runSqliteExpressionLookup()">Expression</button>' +
      '<input id="sqliteRecordLookupInput" placeholder="Alpha / official / simulation id" style="min-width:220px;max-width:320px">' +
      '<button class="secondary small" onclick="runSqliteRecordLookup()">Record</button>' +
      '<button class="secondary small" onclick="openSqliteLookupDetail()">Details</button>' +
      '</div>' +
      '</div>';
  }

  function robustnessControlsHtml() {
    var snapshot = currentRobustnessSnapshot();
    var latestAnti = snapshot.latest_anti_overfit || {};
    var latestRolling = snapshot.latest_rolling_validation || {};
    var note = 'Run checks against candidates in the latest result snapshot.';
    if (latestAnti.ok) note = 'Latest anti-overfit: ' + String(latestAnti.candidate_id || '-');
    if (latestRolling.ok) note += ' | Latest rolling: ' + String(latestRolling.candidate_id || '-');
    return '<div class="stats-card primary">' +
      '<div class="stat-label">Candidate Robustness Review</div>' +
      '<div class="stat-value">Tools</div>' +
      '<div class="stat-note">' + esc(note) + '</div>' +
      '<div class="action-row" style="margin-top:8px;gap:8px;flex-wrap:wrap">' +
      '<input id="robustnessCandidateInput" placeholder="Candidate id" style="min-width:220px;max-width:320px">' +
      '<button class="secondary small" onclick="runAntiOverfitForInput()">Anti-overfit</button>' +
      '<button class="secondary small" onclick="runRollingValidationForInput()">Rolling</button>' +
      '<button class="secondary small" onclick="runRobustnessBatchForVisible()">Batch visible</button>' +
      '<button class="secondary small" onclick="openRobustnessDetail()">Details</button>' +
      '</div>' +
      '</div>';
  }

  function renderResearchMemoryPanel(rows) {
    var panel = $('cloudStatsPanel');
    if (!panel || activeView() !== 'research_memory') return;
    var items = rows.map(function (item) { return item.raw || {}; });
    if (!items.length) {
      panel.innerHTML = '<div class="stats-card"><div class="stat-label">Research Memory</div><div class="stat-value">Empty</div><div class="stat-note">' + esc(emptyText('research_memory')) + '</div></div>';
      return;
    }
    panel.innerHTML = items.map(function (row, index) {
      var value = row.value === undefined || row.value === null ? '-' : String(row.value);
      var cls = safeClassTokens(row.cls || (index <= 2 ? 'primary' : ''));
      var actions = Array.isArray(row.actions) && row.actions.length
        ? '<div class="action-row" style="margin-top:8px">' + row.actions.map(function (action) {
          var handler = safeStatActionHandler(action.handler);
          return handler ? '<button class="secondary small" onclick="' + handler + '">' + esc(action.label || '') + '</button>' : '';
        }).join('') + '</div>'
        : '';
      return '<div class="stats-card ' + cls + '">' +
        '<div class="stat-label">' + esc(row.name || '') + '</div>' +
        '<div class="stat-value">' + esc(value) + '</div>' +
        '<div class="stat-note">' + esc(row.note || '') + '</div>' +
        actions +
        '</div>';
    }).join('');
  }

  function renderResearchObservabilityPanel(rows) {
    var panel = $('cloudStatsPanel');
    if (!panel || activeView() !== 'research_observability') return;
    var items = rows.map(function (item) { return item.raw || {}; });
    if (!items.length) {
      panel.innerHTML = '<div class="stats-card"><div class="stat-label">Observability</div><div class="stat-value">Empty</div><div class="stat-note">' + esc(emptyText('research_observability')) + '</div></div>';
      return;
    }
    panel.innerHTML = items.map(function (row, index) {
      var value = row.value === undefined || row.value === null ? '-' : String(row.value);
      var cls = safeClassTokens(row.cls || (index <= 2 ? 'primary' : ''));
      return '<div class="stats-card ' + cls + '">' +
        '<div class="stat-label">' + esc(row.name || '') + '</div>' +
        '<div class="stat-value">' + esc(value) + '</div>' +
        '<div class="stat-note">' + esc(row.note || '') + '</div>' +
        '</div>';
    }).join('');
  }

  function renderResearchKnowledgePanel(rows) {
    renderStatsPanelForView(rows, 'research_knowledge', 'Knowledge Base');
  }

  function renderPromptRunLedgerPanel(rows) {
    renderStatsPanelForView(rows, 'prompt_runs', 'Prompt Ledger');
  }

  function renderSqliteIndexPanel(rows) {
    renderStatsPanelForView(rows, 'sqlite_indexes', 'SQLite Index', sqliteLookupControlsHtml());
  }

  function renderRobustnessPanel(rows) {
    renderStatsPanelForView(rows, 'robustness', 'Robustness', robustnessControlsHtml());
  }

  function renderStatsPanelForView(rows, view, title, prefixHtml) {
    var panel = $('cloudStatsPanel');
    if (!panel || activeView() !== view) return;
    var items = rows.map(function (item) { return item.raw || {}; });
    var prefix = prefixHtml || '';
    if (!items.length) {
      panel.innerHTML = prefix + '<div class="stats-card"><div class="stat-label">' + esc(title) + '</div><div class="stat-value">Empty</div><div class="stat-note">' + esc(emptyText(view)) + '</div></div>';
      return;
    }
    panel.innerHTML = prefix + items.map(function (row, index) {
      var value = row.value === undefined || row.value === null ? '-' : String(row.value);
      var cls = safeClassTokens(row.cls || (index <= 2 ? 'primary' : ''));
      var actions = Array.isArray(row.actions) && row.actions.length
        ? '<div class="action-row" style="margin-top:8px">' + row.actions.map(function (action) {
          var handler = safeStatActionHandler(action.handler);
          return handler ? '<button class="secondary small" onclick="' + handler + '">' + esc(action.label || '') + '</button>' : '';
        }).join('') + '</div>'
        : '';
      return '<div class="stats-card ' + cls + '">' +
        '<div class="stat-label">' + esc(row.name || '') + '</div>' +
        '<div class="stat-value">' + esc(value) + '</div>' +
        '<div class="stat-note">' + esc(row.note || '') + '</div>' +
        actions +
        '</div>';
    }).join('');
  }

  function renderModuleActions() {
    var view = activeView();
    var visible = view === 'passed' || view === 'submittable' || view === 'research_memory';
    var panel = $('moduleActions');
    if (!panel) return;
    panel.classList.toggle('hidden', !visible);
    if (!visible) return;

    var autoSwitch = $('autoSubmitSwitch');
    var title = $('moduleActionTitle');
    var hint = $('moduleActionHint');
    var checkMode = $('checkMode');
    var checkButton = $('checkButton');
    var submitButton = $('submitSelectedButton');
    var assistantInputs = $('assistantGenerateInputs');
    var assistantButton = $('assistantGenerateButton');
    var assistantSaveButton = $('assistantSaveGuidanceButton');
    var assistantPreviewButton = $('assistantPreviewGuidanceButton');
    var assistantDraftButton = $('assistantUseDraftButton');
    var assistantLatestButton = $('assistantUseLatestButton');
    var assistantDraftSaveButton = $('assistantSaveDraftButton');
    if (assistantInputs) assistantInputs.classList.toggle('hidden', view !== 'research_memory');
    if (assistantButton) assistantButton.classList.toggle('hidden', view !== 'research_memory');
    if (assistantSaveButton) assistantSaveButton.classList.toggle('hidden', view !== 'research_memory');
    if (assistantPreviewButton) assistantPreviewButton.classList.toggle('hidden', view !== 'research_memory');
    if (assistantDraftButton) assistantDraftButton.classList.toggle('hidden', view !== 'research_memory');
    if (assistantLatestButton) assistantLatestButton.classList.toggle('hidden', view !== 'research_memory');
    if (assistantDraftSaveButton) assistantDraftSaveButton.classList.toggle('hidden', view !== 'research_memory');
    if (autoSwitch) autoSwitch.classList.toggle('hidden', view !== 'submittable');

    if (view === 'research_memory') {
      var guidance = (currentSummary().assistant_generation || {}).assistant_guidance || {};
      var hintParts = ['Local-only generation uses Research Memory and optional assistant JSON; no official API call is made.'];
      if (guidance.applied !== undefined) {
        hintParts.push('Last guidance: ' + (guidance.applied ? 'applied' : (guidance.reason || 'skipped')) + '.');
      }
      if (title) title.textContent = 'Assistant-guided generation';
      if (hint) hint.textContent = hintParts.join(' ');
      if (checkMode) checkMode.classList.add('hidden');
      if (checkButton) checkButton.classList.add('hidden');
      if (submitButton) submitButton.classList.add('hidden');
      if (assistantButton) {
        assistantButton.disabled = assistantGenerateInFlight;
        assistantButton.textContent = assistantGenerateInFlight ? 'Generating...' : 'Generate';
      }
      if (assistantSaveButton) {
        assistantSaveButton.disabled = assistantGuidanceSaveInFlight;
        assistantSaveButton.textContent = assistantGuidanceSaveInFlight ? 'Saving...' : 'Save Guidance';
      }
      if (assistantPreviewButton) {
        assistantPreviewButton.disabled = assistantGuidancePreviewInFlight;
        assistantPreviewButton.textContent = assistantGuidancePreviewInFlight ? 'Parsing...' : 'Preview Guidance';
      }
      if (assistantDraftButton) {
        assistantDraftButton.disabled = assistantDraftInFlight;
        assistantDraftButton.textContent = assistantDraftInFlight ? 'Loading...' : 'Use Offline Draft';
      }
      if (assistantLatestButton) {
        assistantLatestButton.disabled = assistantDraftInFlight;
        assistantLatestButton.textContent = assistantDraftInFlight ? 'Loading...' : 'Use Saved';
      }
      if (assistantDraftSaveButton) {
        assistantDraftSaveButton.disabled = assistantDraftSaveInFlight;
        assistantDraftSaveButton.textContent = assistantDraftSaveInFlight ? 'Saving...' : 'Save Draft';
      }
      if ($('checkStats')) {
        var generated = (currentSummary().assistant_generation || {}).generated_count;
        $('checkStats').textContent = generated !== undefined ? ('Last generated ' + generated + ' local candidates.') : 'Copy Request, paste model JSON, save guidance, or generate a local candidate batch.';
      }
      return;
    }

    if (view === 'passed') {
      if (title) title.textContent = '达标检查';
      if (hint) hint.textContent = '批量核验全部达标 Alpha 当前是否仍可提交；' + needsCheckCount() + ' 个需要检查或复检。';
      if (checkMode) checkMode.classList.remove('hidden');
      if (checkButton) {
        checkButton.classList.remove('hidden');
        checkButton.disabled = Boolean(batchCheckJobId);
      }
      if (submitButton) submitButton.classList.add('hidden');
    } else {
      if (title) title.textContent = '可提交队列';
      if (hint) hint.textContent = '按检查分、排序分和云端相关风险排序；检查超过 24 小时会回到达标列表等待复检。云端缓存：' + cloudFreshnessText() + '。';
      if (checkMode) checkMode.classList.add('hidden');
      if (checkButton) checkButton.classList.add('hidden');
      if (submitButton) {
        submitButton.classList.toggle('hidden', Boolean(($('autoSubmitToggle') || {}).checked));
        submitButton.disabled = submitInFlight || selectedSubmitIds.size === 0;
      }
    }
    if ($('checkStats')) $('checkStats').textContent = latestCheckSummary();
  }

  function renderFilterBar() {
    var bar = $('filterBar');
    if (!bar) return;
    var viewsWithFilters = ['candidates', 'passed', 'submittable', 'failed', 'backtest_rework'];
    if (viewsWithFilters.indexOf(activeView()) === -1) {
      bar.classList.add('hidden');
      bar.innerHTML = '';
      return;
    }
    bar.classList.remove('hidden');
    var rows = rowsForView(activeView());
    var families = [];
    var seen = {};
    rows.forEach(function (row) {
      var family = (row.raw || {}).family || '';
      if (family && !seen[family]) {
        seen[family] = true;
        families.push(family);
      }
    });
    var chips = [
      ['all', '全部'],
      ['score_gte_85', '分≥85'],
      ['score_gte_70', '分≥70'],
      ['has_official', '有官方指标'],
    ];
    var html = chips.map(function (chip) {
      var key = chip[0];
      var active = activeFilter === key || (!activeFilter && key === 'all');
      return '<span class="filter-chip ' + (active ? 'active' : '') + '" onclick="setFilter(' + jsStringAttr(key) + ')">' + esc(chip[1]) + '</span>';
    }).join('');
    families.slice(0, 6).forEach(function (family) {
      var key = 'family:' + family;
      html += '<span class="filter-chip ' + (activeFilter === key ? 'active' : '') + '" onclick="setFilter(' + jsStringAttr(key) + ')">' + esc(family) + '</span>';
    });
    bar.innerHTML = html;
  }

  window.setFilter = function (key) {
    activeFilter = key === 'all' || activeFilter === key ? '' : key;
    renderCurrentView();
  };

  function filteredRows() {
    var query = (($('tableSearch') || {}).value || '').trim().toLowerCase();
    var rows = rowsForView(activeView());
    if (activeFilter) {
      rows = rows.filter(function (row) {
        var raw = row.raw || {};
        if (activeFilter === 'score_gte_85') return submissionRankScore(raw) >= 85;
        if (activeFilter === 'score_gte_70') return submissionRankScore(raw) >= 70;
        if (activeFilter === 'has_official') return Boolean(raw.official_alpha_id || hasDataObject(raw.official_metrics) || raw.simulation_id);
        if (activeFilter.indexOf('family:') === 0) return raw.family === activeFilter.slice(7);
        return true;
      });
    }
    if (!query) return rows;
    return rows.filter(function (item) {
      return JSON.stringify(item.raw || item).toLowerCase().indexOf(query) !== -1;
    });
  }

  function rowsForView(view) {
    if (view === 'candidates') return candidateRows(currentCandidates(), 'candidate');
    if (view === 'pending_backtest') return candidateRows(pendingBacktestCandidates(), 'pending_backtest');
    if (view === 'running_backtest') return runningBacktestRows();
    if (view === 'backtest_rework') return backtestReworkRows();
    if (view === 'passed') return candidateRows(passedCandidates(), 'passed');
    if (view === 'submittable') return candidateRows(submittableCandidates(), 'submittable');
    if (view === 'submitted') return submittedRows();
    if (view === 'failed') return failedRows();
    if (view === 'cloud') return cloudRows();
    if (view === 'research_observability') return researchObservabilityRows();
    if (view === 'research_memory') return researchMemoryRows();
    if (view === 'research_knowledge') return researchKnowledgeRows();
    if (view === 'prompt_runs') return promptRunLedgerRows();
    if (view === 'sqlite_indexes') return sqliteIndexRows();
    if (view === 'robustness') return robustnessRows();
    return lifecycleRows();
  }

  function candidateRows(list, kind) {
    return uniqueCandidates(list)
      .slice()
      .sort(function (a, b) { return submissionRankScore(b) - submissionRankScore(a); })
      .map(function (candidate, index) {
        return {
          kind: kind,
          id: candidateIdentity(candidate) || String(index),
          raw: candidate,
        };
      });
  }

  function derivePassedCandidates(candidates) {
    return (Array.isArray(candidates) ? candidates : []).filter(function (candidate) {
      return candidate.lifecycle_status === 'submission_ready' || (candidate.gate || {}).submission_ready;
    });
  }

  function pendingBacktestCandidates() {
    var explicit = S.get('currentResult.pending_backtest_candidates') || [];
    if (explicit.length) return uniqueCandidates(explicit.filter(isWaitingForOfficialBacktest));
    var threshold = Number((currentSummary().official_call_policy || {}).min_prior_score_for_official_simulation || configuredBudget().min_prior_score_for_official_simulation || 0);
    return uniqueCandidates(currentCandidates().filter(function (candidate) {
      return isWaitingForOfficialBacktest(candidate, threshold);
    }));
  }

  function isWaitingForOfficialBacktest(candidate, threshold) {
    candidate = candidate || {};
    threshold = threshold === undefined ? Number((currentSummary().official_call_policy || {}).min_prior_score_for_official_simulation || configuredBudget().min_prior_score_for_official_simulation || 0) : threshold;
    var status = String(candidate.lifecycle_status || '') + ' ' + String((candidate.gate || {}).status || '');
    var lower = status.toLowerCase();
    var hasMetrics = hasDataObject(extractOfficialMetrics(candidate));
    var capacityDeferred = /simulation_deferred_(concurrency|rate)_limit|official_validation_deferred_rate_limit/.test(lower);
    var hasPrecheck = candidate.validation && candidate.validation.status === 'PASS'
      || /official_validation_passed|backtest_batch_selected|backtest_slot_selected/.test(lower)
      || capacityDeferred;
    var hardBlocked = /official_validation_failed|local_standard_rejected|official_standard_rejected|simulation_request_failed|simulation_poll_failed|simulation_result_failed|simulation_failed|simulation_timeout|rejected/i.test(status);
    return hasPrecheck && !candidate.simulation_id && !hasMetrics && submissionRankScore(candidate) >= threshold && (!hardBlocked || capacityDeferred);
  }

  function runningBacktestRows() {
    return currentBacktests()
      .filter(function (slot) { return isActiveSlotStatus(slot.status); })
      .sort(function (a, b) { return Number(a.slot || 0) - Number(b.slot || 0); })
      .map(function (slot) { return { kind: 'backtest', id: String(slot.slot || slot.alpha_id || ''), raw: slot }; });
  }

  function backtestReworkRows() {
    var pattern = /simulation_.*failed|backtest_failed|official_standard_rejected|request_failed|poll_failed|result_failed|simulation_retry_pending|simulation_deferred|official_deferred|rate_limit|concurrency_limit|rejected/i;
    var slots = currentBacktests()
      .filter(function (slot) { return pattern.test(String(slot.status || '') + ' ' + String(slot.message || '')); })
      .map(function (slot) { return { kind: 'backtest', id: String(slot.slot || slot.alpha_id || ''), raw: slot }; });
    var candidates = candidateRows(currentCandidates().filter(function (candidate) {
      return pattern.test(String(candidate.lifecycle_status || '') + ' ' + String((candidate.gate || {}).status || ''));
    }), 'backtest_rework');
    return uniqueRowsById(slots.concat(candidates));
  }

  function passedCandidates() {
    var map = {};
    (S.get('currentResult.passed_candidates') || []).concat(currentCandidates()).forEach(function (candidate) {
      if (!candidate || !candidate.alpha_id) return;
      if (candidate.lifecycle_status === 'submission_ready' || (candidate.gate || {}).submission_ready) {
        map[candidate.alpha_id] = candidate;
      }
    });
    currentCloudAlphas().filter(isCloudPassedUnsubmitted).map(cloudAlphaToCandidate).forEach(function (candidate) {
      if (candidate.alpha_id && !map[candidate.alpha_id]) map[candidate.alpha_id] = candidate;
    });
    return uniqueCandidates(Object.keys(map).map(function (key) { return map[key]; })).sort(function (a, b) { return submissionRankScore(b) - submissionRankScore(a); });
  }

  function submittableCandidates() {
    return passedCandidates().filter(isSubmittable).sort(function (a, b) { return submissionRankScore(b) - submissionRankScore(a); });
  }

  function needsCheckCount() {
    return passedCandidates().filter(function (candidate) { return !isSubmittable(candidate); }).length;
  }

  function staleCheckCount() {
    return passedCandidates().filter(function (candidate) {
      var check = checkResults()[candidate.alpha_id];
      return Boolean(isOfficialPassedCheck(check) && !isFreshPassedCheck(check));
    }).length;
  }

  function isFreshCheck(check) {
    if (!check) return false;
    if (typeof check.is_stale === 'boolean') return !check.is_stale;
    var checkedAt = Date.parse(check.checked_at || '');
    return Number.isFinite(checkedAt) && Date.now() - checkedAt <= CHECK_STALE_MS;
  }

  function isOfficialPassedCheck(check) {
    if (!check || !check.passed) return false;
    return (check.checks || []).some(function (row) { return row.name === 'official_pre_submit_check' && row.passed; });
  }

  function isFreshPassedCheck(check) {
    return Boolean(isOfficialPassedCheck(check) && isFreshCheck(check));
  }

  function isSubmittable(candidate) {
    return Boolean(candidate && candidate.alpha_id && isFreshPassedCheck(checkResults()[candidate.alpha_id]));
  }

  function submissionRankScore(candidate) {
    candidate = candidate || {};
    var metrics = extractOfficialMetrics(candidate);
    var metricScore = hasDataObject(metrics) ? cloudMetricScore(metrics) : null;
    var base = hasDataObject(metrics)
      ? firstFiniteNumber(metricScore, (candidate.scorecard || {}).total_score, candidate.smart_rank_score, candidate.score, 0)
      : firstFiniteNumber(candidate.smart_rank_score, (candidate.scorecard || {}).total_score, candidate.score, 0);
    var check = checkResults()[candidate.alpha_id || ''];
    var risk = candidate.cloud_correlation_risk || {};
    var riskPenalty = risk.level === 'high' ? 40 : risk.level === 'medium' ? 12 : 0;
    var metricBonus = hasDataObject(metrics)
      ? Number(metrics.sharpe || 0) * 2 + Number(metrics.fitness || 0)
      : 0;
    var checkScore = check ? firstFiniteNumber(check.score, base) : base;
    return Math.max(0, Math.min(100, Number(checkScore || 0) + (check && check.passed ? 8 : 0) + metricBonus - riskPenalty));
  }

  function scoreBasisLabel(candidate) {
    candidate = candidate || {};
    var basis = String((candidate.scorecard || {}).score_basis || '');
    if (basis === 'ui_metric_estimate') return '本地指标展示分';
    if (hasDataObject(extractOfficialMetrics(candidate))) return '官方指标折算';
    if (basis === 'official_verified') return '官方指标折算';
    if (basis === 'local_prior') return '本地估算';
    if (basis === 'missing_metrics') return '缺少指标';
    if (candidate.smart_rank_score !== undefined) return '智能排序';
    return '本地排序';
  }

  function submittedRows() {
    var lifecycle = currentLifecycle()
      .filter(function (row) { return !isBadStatus(row) && (row.stage === 'submitted' || isSubmittedCloudStatus(row.status)); })
      .map(function (row) { return { kind: 'lifecycle', id: lifecycleIdentity(row), raw: row }; });
    var cloud = currentCloudAlphas()
      .filter(function (row) { return !isBadStatus(row) && isSubmittedCloudStatus(row.status); })
      .map(function (row) { return { kind: 'cloud', id: row.id || row.alpha_id || '', raw: row }; });
    return uniqueRowsByAlpha(lifecycle.concat(cloud));
  }

  function failedRows() {
    var candidates = candidateRows(currentCandidates().filter(isOfficialBacktestFailed), 'candidate');
    var lifecycle = currentLifecycle()
      .filter(isOfficialBacktestFailed)
      .map(function (row) { return { kind: 'lifecycle', id: lifecycleIdentity(row), raw: row }; });
    var cloud = currentCloudAlphas().filter(isCloudFailedAlpha).map(function (row) {
      return { kind: 'cloud', id: row.id || row.alpha_id || '', raw: row };
    });
    return uniqueRowsByAlpha(candidates.concat(lifecycle, cloud));
  }

  function lifecycleRows() {
    return uniqueLifecycle(currentLifecycle())
      .filter(isImportantLifecycle)
      .slice()
      .reverse()
      .map(function (row) {
        return { kind: 'lifecycle', id: lifecycleIdentity(row), raw: row };
      });
  }

  function cloudRows() {
    var cloud = currentSummary().cloud_sync || {};
    var alphas = currentCloudAlphas();
    var rows = [
      ['同步范围', cloud.range || (($('syncRange') || {}).value) || '-'],
      ['已扫描', formatLoadedCount(cloud.scanned !== undefined ? cloud.scanned : alphas.length, cloud.total || cloud.count || cloud.scanned)],
      ['云端已提交', cloud.submitted_count !== undefined ? cloud.submitted_count : submittedRows().filter(function (row) { return row.kind === 'cloud'; }).length],
      ['云端达标未提交', cloud.passed_unsubmitted_count !== undefined ? cloud.passed_unsubmitted_count : alphas.filter(isCloudPassedUnsubmitted).length],
      ['云端不达标', cloud.failed_unsubmitted_count !== undefined ? cloud.failed_unsubmitted_count : alphas.filter(isCloudFailedAlpha).length],
      ['新增', cloud.added || 0],
      ['跳过', cloud.skipped || 0],
      ['失败', cloud.failed || 0],
      ['字段数', formatLoadedCount(cloud.fields_count, cloud.fields_total)],
      ['算子数', formatLoadedCount(cloud.operators_count, cloud.operators_total)],
      ['数据集数', formatLoadedCount(cloud.datasets_count, cloud.datasets_total)],
      ['最近同步', cloudFreshnessText(cloud)],
      ['快照来源', cloud.source || '-'],
      ['同步状态', statusLabelFromCode(cloud.status || '未同步')],
    ];
    return rows.map(function (pair, index) {
      return { kind: 'cloud_stat', id: 'cloud_stat_' + index, raw: { name: pair[0], value: pair[1] } };
    });
  }

  function researchMemoryRows() {
    return researchMemoryCards(currentResearchMemory()).map(function (card, index) {
      return { kind: 'research_memory_stat', id: 'research_memory_stat_' + index, raw: card };
    });
  }

  function researchObservabilityRows() {
    return researchObservabilityCards(currentResearchObservability()).map(function (card, index) {
      return { kind: 'research_observability_stat', id: 'research_observability_stat_' + index, raw: card };
    });
  }

  function researchKnowledgeRows() {
    return researchKnowledgeCards(currentResearchKnowledge()).map(function (card, index) {
      return { kind: 'research_knowledge_stat', id: 'research_knowledge_stat_' + index, raw: card };
    });
  }

  function promptRunLedgerRows() {
    return promptRunLedgerCards(currentPromptRuns()).map(function (card, index) {
      return { kind: 'prompt_run_stat', id: 'prompt_run_stat_' + index, raw: card };
    });
  }

  function sqliteIndexRows() {
    return sqliteIndexCards(currentSqliteIndexes()).map(function (card, index) {
      return { kind: 'sqlite_index_stat', id: 'sqlite_index_stat_' + index, raw: card };
    });
  }

  function robustnessRows() {
    var snapshot = buildRobustnessSnapshot();
    S.set('currentResult.robustness_snapshot', snapshot);
    return robustnessCards(snapshot).map(function (card, index) {
      return { kind: 'robustness_stat', id: 'robustness_stat_' + index, raw: card };
    });
  }

  function isSubmittedCloudStatus(status) {
    return ['ACTIVE', 'SUBMITTED', 'PRODUCTION', 'CONDUCTED'].indexOf(String(status || '').trim().toUpperCase()) !== -1;
  }

  function isCloudPassedUnsubmitted(row) {
    var status = String((row || {}).status || '').trim().toUpperCase();
    var metrics = (row || {}).metrics || {};
    return status === 'UNSUBMITTED' && String(metrics.pass_fail || '').toUpperCase() === 'PASS';
  }

  function isCloudFailedAlpha(row) {
    var status = String((row || {}).status || '').trim().toUpperCase();
    return status === 'UNSUBMITTED' && isOfficialBacktestFailed(row);
  }

  function isOfficialBacktestFailed(row) {
    row = row || {};
    var metrics = extractOfficialMetrics(row);
    var passFail = String(metrics.pass_fail || '').trim().toUpperCase();
    if (passFail === 'FAIL') return true;
    var checks = Array.isArray(metrics._alpha_checks) ? metrics._alpha_checks : [];
    if (checks.some(function (check) { return check && (String(check.result || '').toUpperCase() === 'FAIL' || String(check.result || '').toUpperCase() === 'ERROR'); })) return true;
    var text = (String(row.stage || '') + ' ' + String(row.status || '') + ' ' + String(row.lifecycle_status || '') + ' ' + String((row.gate || {}).status || '')).toLowerCase();
    return hasDataObject(metrics) && /official_standard_rejected|backtest_failed/.test(text);
  }

  function isBadStatus(row) {
    return /failed|rejected|fail|blocked|不达标/i.test(String((row || {}).stage || '') + ' ' + String((row || {}).status || '') + ' ' + String((row || {}).note || '') + ' ' + String((row || {}).failure_reason || ''));
  }

  function isImportantLifecycle(row) {
    var text = (String(row.stage || '') + ' ' + String(row.status || '') + ' ' + String(row.note || '')).toLowerCase();
    if (text.indexOf('generated') !== -1 || text.indexOf('local_scored') !== -1) return false;
    return /validation|simulation|backtest|submission|submitted|failed|rejected|ready|deferred|limit|strategy|不达标|达标|提交/.test(text);
  }

  function isActiveSlotStatus(status) {
    return ['active', 'running', 'submitted', 'polling', 'simulation_submitted', 'simulation_running'].indexOf(String(status || '').toLowerCase()) !== -1;
  }

  function activeBacktestCount(backtests) {
    return (backtests || []).filter(function (slot) { return isActiveSlotStatus(slot.status); }).length;
  }

  function cloudAlphaToCandidate(row) {
    row = row || {};
    var metrics = extractOfficialMetrics(row);
    var score = cloudMetricScore(metrics);
    var checkGate = officialCheckGate(metrics);
    var cloudPass = String(metrics.pass_fail || '').toUpperCase() === 'PASS';
    var submissionReady = cloudPass && checkGate.status !== 'failed' && checkGate.status !== 'pending';
    var lifecycleStatus = submissionReady ? 'submission_ready' : checkGate.status === 'failed' ? 'official_check_failed' : checkGate.status === 'pending' ? 'official_check_pending' : 'submission_ready';
    return {
      alpha_id: row.id || row.alpha_id || '',
      official_alpha_id: row.id || row.alpha_id || '',
      source: 'cloud',
      cloud_status: row.status || '',
      expression: expressionFromRow(row),
      family: '云端',
      hypothesis: '云端同步的已回测 Alpha。',
      lifecycle_status: lifecycleStatus,
      official_metrics: metrics,
      gate: { submission_ready: submissionReady, status: lifecycleStatus },
      scorecard: scorecardFromMetrics(metrics, score),
      cloud_correlation_risk: { level: 'unknown', max_similarity: 0 },
    };
  }

  function cloudMetricScore(metrics) {
    metrics = metrics || {};
    if (!hasDataObject(metrics)) return 0;
    var score = 0;
    var sharpe = metricNumber(metrics, 'sharpe');
    var fitness = metricNumber(metrics, 'fitness');
    var turnover = metricNumber(metrics, 'turnover');
    var returns = metricNumber(metrics, 'returns');
    var drawdown = metricNumber(metrics, 'drawdown');
    var correlation = metricNumber(metrics, 'correlation');
    if (sharpe !== null && sharpe >= 1.25) score += 25;
    if (fitness !== null && fitness >= 1.0) score += 20;
    if (turnover !== null && turnover >= 0.01 && turnover <= 0.7) score += 15;
    if (returns !== null && returns > 0) score += 10;
    if (drawdown !== null && drawdown <= 0.3) score += 10;
    if (correlation !== null && correlation <= 0.7) score += 15;
    if (String(metrics.pass_fail || '').toUpperCase() === 'PASS') score += 5;
    score = applyOfficialCheckCap(score, metrics);
    return Math.max(0, Math.min(100, score));
  }

  function applyOfficialCheckCap(score, metrics) {
    var checkGate = officialCheckGate(metrics);
    if (checkGate.status === 'failed') return Math.min(score, 49);
    if (checkGate.status === 'pending') return Math.min(score, 84);
    return score;
  }

  function officialCheckGate(metrics) {
    metrics = metrics || {};
    var checks = Array.isArray(metrics._alpha_checks) ? metrics._alpha_checks : [];
    var hardChecks = [
      'LOW_SHARPE',
      'LOW_FITNESS',
      'LOW_TURNOVER',
      'HIGH_TURNOVER',
      'CONCENTRATED_WEIGHT',
      'LOW_SUB_UNIVERSE_SHARPE',
      'SELF_CORRELATION',
    ];
    var rows = checks
      .filter(function (check) { return check && hardChecks.indexOf(check.name) !== -1; })
      .map(function (check) {
        return {
          name: check.name,
          result: String(check.result || '').toUpperCase(),
          value: check.value,
        };
      });
    var failedRows = rows.filter(function (row) { return row.result === 'FAIL' || row.result === 'ERROR'; });
    var pendingRows = rows.filter(function (row) { return !row.result || row.result === 'PENDING' || row.result === 'WARNING'; });
    return {
      status: failedRows.length ? 'failed' : pendingRows.length ? 'pending' : rows.length ? 'passed' : 'unknown',
      rows: rows,
      failed_rows: failedRows,
      pending_rows: pendingRows,
    };
  }

  function candidateDisplayScore(candidate) {
    candidate = candidate || {};
    var metrics = extractOfficialMetrics(candidate);
    var metricScore = hasDataObject(metrics) ? cloudMetricScore(metrics) : null;
    return hasDataObject(metrics)
      ? firstFiniteNumber((candidate.scorecard || {}).total_score, metricScore, candidate.smart_rank_score, candidate.score, 0)
      : firstFiniteNumber(candidate.smart_rank_score, (candidate.scorecard || {}).total_score, candidate.score, 0);
  }

  function rowHtml(item, index) {
    if (item.kind === 'cloud') return cloudRowHtml(item, index);
    if (item.kind === 'lifecycle') return lifecycleRowHtml(item, index);
    if (item.kind === 'backtest') return backtestRowHtml(item, index);
    return candidateRowHtml(item, index);
  }

  function candidateRowHtml(item, index) {
    var c = item.raw || {};
    var score = item.kind === 'submittable' ? submissionRankScore(c) : candidateDisplayScore(c);
    var officialId = c.official_alpha_id || ((c.official_metrics || {}).official_alpha_id) || c.simulation_id || '';
    var risk = c.cloud_correlation_risk || {};
    var checked = isSubmittable(c);
    var stale = Boolean(isOfficialPassedCheck(checkResults()[c.alpha_id]) && !checked);
    var kindArg = jsStringAttr(item.kind);
    var idArg = jsStringAttr(item.id);
    var selectBox = item.kind === 'submittable' && checked && !(($('autoSubmitToggle') || {}).checked)
      ? '<input type="checkbox" ' + (selectedSubmitIds.has(c.alpha_id) ? 'checked' : '') + ' onclick="event.stopPropagation(); toggleSubmitSelection(' + jsStringAttr(c.alpha_id) + ', this.checked)">'
      : '';
    return '<tr id="' + rowId(item) + '" data-kind="' + escapeAttr(item.kind) + '" data-id="' + escapeAttr(item.id) + '" onclick="viewRow(' + kindArg + ', ' + idArg + ', event)">' +
      '<td>' + (selectBox || String(index + 1)) + '</td>' +
      '<td><b>' + esc(c.alpha_id || '') + '</b><div class="mini">' + esc(c.hypothesis || '无假说') + '</div><div class="mini">' + esc(c.expression || '') + '</div></td>' +
      '<td>' + esc(c.family || '') + '</td>' +
      '<td><span class="score-badge ' + scoreClass(score) + '" title="' + escapeAttr(scoreBasisLabel(c)) + '">' + esc(num(score)) + '</span><div class="mini">' + esc(scoreBasisLabel(c)) + '</div></td>' +
      '<td>' + esc(candidateStatusLabel(c, checked, stale)) + '</td>' +
      '<td>' + esc(officialId || '未获得') + '</td>' +
      '<td>' + esc(attention(c)) + (risk.level ? '<br>云端相关：' + esc(risk.level) + ' ' + esc(num(risk.max_similarity, 3)) : '') + '</td>' +
      '<td>' + candidateActions(c, item.kind) + '</td>' +
      '</tr>';
  }

  function backtestRowHtml(item, index) {
    var slot = item.raw || {};
    var idArg = jsStringAttr(item.id);
    var score = candidateDisplayScore(slot);
    return '<tr id="' + rowId(item) + '" data-kind="backtest" data-id="' + escapeAttr(item.id) + '" onclick="viewRow(&quot;backtest&quot;, ' + idArg + ', event)">' +
      '<td>' + (index + 1) + '</td>' +
      '<td><b>' + esc(slot.alpha_id || '-') + '</b><div class="mini">槽 ' + esc(slot.slot || '-') + ' | Simulation ' + esc(slot.simulation_id || '-') + '</div></td>' +
      '<td>官方回测</td>' +
      '<td><span class="score-badge ' + scoreClass(score) + '">' + esc(num(score)) + '</span></td>' +
      '<td>' + esc(statusText(slot.status)) + '</td>' +
      '<td>' + esc(slot.official_alpha_id || '-') + '</td>' +
      '<td>' + esc(slot.message || '') + '</td>' +
      '<td><button class="small secondary" data-action="view-row" data-kind="backtest" data-id="' + escapeAttr(item.id) + '" onclick="viewRow(&quot;backtest&quot;, ' + idArg + ', event)">查看</button></td>' +
      '</tr>';
  }

  function cloudRowHtml(item, index) {
    var row = item.raw || {};
    var idArg = jsStringAttr(item.id);
    var metrics = extractOfficialMetrics(row);
    var score = cloudMetricScore(metrics);
    return '<tr id="' + rowId(item) + '" data-kind="cloud" data-id="' + escapeAttr(item.id) + '" onclick="viewRow(&quot;cloud&quot;, ' + idArg + ', event)">' +
      '<td>' + (index + 1) + '</td>' +
      '<td><b>' + esc(row.id || row.alpha_id || '') + '</b><div class="mini">' + esc(expressionFromRow(row)) + '</div></td>' +
      '<td>云端</td>' +
      '<td><span class="score-badge ' + scoreClass(score) + '">' + esc(num(score)) + '</span></td>' +
      '<td>' + esc(statusLabelFromCode(row.status || '-')) + '</td>' +
      '<td>' + esc(row.id || row.alpha_id || '-') + '</td>' +
      '<td>' + esc((row.metrics || {}).failure_reason || row.created_at || '') + '</td>' +
      '<td><button class="small secondary" data-action="view-row" data-kind="cloud" data-id="' + escapeAttr(item.id) + '" onclick="viewRow(&quot;cloud&quot;, ' + idArg + ', event)">查看</button></td>' +
      '</tr>';
  }

  function lifecycleRowHtml(item, index) {
    var row = item.raw || {};
    var idArg = jsStringAttr(item.id);
    var score = candidateDisplayScore(row);
    return '<tr id="' + rowId(item) + '" data-kind="lifecycle" data-id="' + escapeAttr(item.id) + '" onclick="viewRow(&quot;lifecycle&quot;, ' + idArg + ', event)">' +
      '<td>' + (index + 1) + '</td>' +
      '<td><b>' + esc(row.alpha_id || row.official_alpha_id || '-') + '</b><div class="mini">' + esc(row.timestamp || '') + '</div></td>' +
      '<td>' + esc(row.family || '-') + '</td>' +
      '<td><span class="score-badge ' + scoreClass(score) + '">' + esc(num(score)) + '</span></td>' +
      '<td>' + esc(statusLabelFromCode(row.status || row.stage || '-')) + '</td>' +
      '<td>' + esc(row.official_alpha_id || '-') + '</td>' +
      '<td>' + esc(row.note || row.message || row.status || '') + '</td>' +
      '<td><button class="small secondary" data-action="view-row" data-kind="lifecycle" data-id="' + escapeAttr(item.id) + '" onclick="viewRow(&quot;lifecycle&quot;, ' + idArg + ', event)">查看</button></td>' +
      '</tr>';
  }

  function candidateActions(candidate, kind) {
    var kindArg = jsStringAttr(kind || 'candidate');
    var idArg = jsStringAttr(candidate.alpha_id || candidate.id || '');
    var submit = isSubmittable(candidate) && !(($('autoSubmitToggle') || {}).checked)
      ? '<button class="small" ' + (submitInFlight ? 'disabled' : '') + ' onclick="event.stopPropagation(); submitCandidate(' + jsStringAttr(candidate.alpha_id) + ')">提交</button>'
      : '';
    return '<button class="small secondary" data-action="view-row" data-kind="' + escapeAttr(kind || 'candidate') + '" data-id="' + escapeAttr(candidate.alpha_id || '') + '" onclick="viewRow(' + kindArg + ', ' + idArg + ', event)">查看</button>' + submit;
  }

  window.toggleSubmitSelection = function (alphaId, checked) {
    if (checked) selectedSubmitIds.add(alphaId);
    else selectedSubmitIds.delete(alphaId);
    renderModuleActions();
  };

  function candidateLikeFromRecord(kind, raw) {
    raw = raw || {};
    if (kind === 'cloud') return cloudAlphaToCandidate(raw);
    var metrics = extractOfficialMetrics(raw);
    var score = candidateDisplayScore(raw);
    if (kind !== 'lifecycle' && kind !== 'backtest') {
      if (!hasDataObject(metrics)) return raw;
      return Object.assign({}, raw, {
        official_metrics: metrics,
        scorecard: scorecardFromMetrics(metrics, score),
      });
    }
    var scorecard = hasDataObject(metrics)
      ? scorecardFromMetrics(metrics, score)
      : hasDataObject(raw.scorecard)
        ? raw.scorecard
        : scorecardFromMetrics(metrics, score);
    return Object.assign({}, raw, {
      alpha_id: raw.alpha_id || raw.id || raw.official_alpha_id || '',
      official_alpha_id: raw.official_alpha_id || raw.id || '',
      expression: expressionFromRow(raw),
      family: raw.family || (kind === 'backtest' ? 'Official Backtest' : 'Lifecycle'),
      hypothesis: raw.hypothesis || raw.message || raw.note || '',
      lifecycle_status: raw.lifecycle_status || raw.status || raw.stage || '',
      official_metrics: metrics,
      scorecard: scorecard,
      _detail_source_kind: kind,
      _detail_raw: raw,
    });
  }

  function hasAlphaDetail(raw) {
    raw = raw || {};
    return Boolean(raw.alpha_id || raw.id || raw.official_alpha_id || raw.expression || raw.scorecard || raw.official_metrics || raw.metrics);
  }

  window.viewRow = function (kind, id, event) {
    if (event) {
      event.preventDefault();
      event.stopPropagation();
    }
    var item = rowCache.get(kind + ':' + id) || findAnyRow(kind, id);
    if (!item) return;
    document.querySelectorAll('tbody tr').forEach(function (row) { row.classList.remove('selected'); });
    var rowEl = $(rowId(item));
    if (rowEl) rowEl.classList.add('selected');

    if (window.DetailView && hasAlphaDetail(item.raw || {})) {
      window.DetailView.renderCandidateDetail(candidateLikeFromRecord(kind, item.raw || {}));
    } else if (kind === 'cloud' && window.DetailView) window.DetailView.renderCloudDetail(item.raw || {});
    else if (kind === 'lifecycle' && window.DetailView) window.DetailView.renderLifecycleDetail(item.raw || {});
    else if (kind === 'backtest') renderBacktestDetail(item.raw || {});
    else if (window.DetailView) window.DetailView.renderCandidateDetail(item.raw || {});
  };

  function findAnyRow(kind, id) {
    if (kind === 'backtest') {
      var slots = normalizedBacktestSlots(currentBacktests());
      for (var s = 0; s < slots.length; s += 1) {
        if (String(slots[s].slot || slots[s].alpha_id || s) === String(id)) {
          return { kind: 'backtest', id: String(id), raw: slots[s] };
        }
      }
    }
    for (var i = 0; i < VIEW_ORDER.length; i += 1) {
      var rows = rowsForView(VIEW_ORDER[i]);
      for (var j = 0; j < rows.length; j += 1) {
        if (rows[j].kind === kind && String(rows[j].id) === String(id)) return rows[j];
      }
    }
    return null;
  }

  function renderBacktestDetail(slot) {
    var modal = $('detailModal');
    var title = $('modalTitle');
    var body = $('detail');
    if (!modal || !title || !body) return;
    title.textContent = '回测槽 ' + (slot.slot || '-') + '：' + (slot.alpha_id || '-');
    body.innerHTML = '<div class="kv">' +
      '<div><b>槽位</b><br>' + esc(slot.slot || '-') + '</div>' +
      '<div><b>状态</b><br>' + esc(statusText(slot.status)) + '</div>' +
      '<div><b>轮询</b><br>' + esc(String(slot.poll_count || 0)) + ' 次</div>' +
      '</div><h3>状态说明</h3><div class="copy-box">' + esc(slot.message || '-') + '</div>' +
      '<h3>原始记录</h3><div class="copy-box">' + esc(JSON.stringify(slot, null, 2)) + '</div>';
    modal.classList.remove('hidden');
  }

  window.openCloudRawDetail = function () {
    var rows = currentCloudAlphas();
    var modal = $('detailModal');
    var title = $('modalTitle');
    var body = $('detail');
    if (!modal || !title || !body) return;
    title.textContent = '云端 Alpha 明细';
    body.innerHTML = '<div class="kv"><div><b>云端总量</b><br>' + rows.length + '</div><div><b>展示范围</b><br>前 ' + Math.min(rows.length, 50) + ' 条</div></div>' +
      '<div class="copy-box">' + esc(JSON.stringify(rows.slice(0, 50), null, 2)) + '</div>';
    modal.classList.remove('hidden');
  };

  window.openSqliteLookupDetail = function () {
    var lookup = currentSqliteLookup();
    var expression = lookup.expression || {};
    var record = lookup.record || {};
    var filterInput = $('sqliteLookupDetailFilter');
    var sortInput = $('sqliteLookupDetailSort');
    var filterText = filterInput ? String(filterInput.value || '').trim().toLowerCase() : String(lookup.detail_filter || '').trim().toLowerCase();
    var sortKey = sortInput ? String(sortInput.value || 'timestamp') : String(lookup.detail_sort || 'timestamp');
    var modal = $('detailModal');
    var title = $('modalTitle');
    var body = $('detail');
    if (!modal || !title || !body) return;
    title.textContent = 'SQLite Lookup Detail';
    var expressionRows = []
      .concat((expression.exact_records || []).map(function (row) { return Object.assign({ match_type: 'exact' }, row); }))
      .concat((expression.similar_records || []).map(function (row) { return Object.assign({ match_type: 'similar', similarity: row.similarity }, row); }));
    var recordRows = Array.isArray(record.records) ? record.records : [];
    expressionRows = sortedLookupRows(filteredLookupRows(expressionRows, filterText), sortKey);
    recordRows = sortedLookupRows(filteredLookupRows(recordRows, filterText), sortKey);
    body.innerHTML =
      '<div class="stats-card primary"><div class="stat-label">Lookup Tools</div><div class="stat-value">Details</div>' +
      '<div class="stat-note">Filter and sort are applied in-browser to current lookup results.</div>' +
      '<div class="action-row" style="margin-top:8px;gap:8px;flex-wrap:wrap">' +
      '<input id="sqliteLookupDetailFilter" placeholder="Filter results" value="' + escapeAttr(filterText) + '" style="min-width:180px">' +
      '<select id="sqliteLookupDetailSort"><option value="timestamp">Timestamp</option><option value="score">Score</option><option value="similarity">Similarity</option><option value="alpha_id">Alpha ID</option><option value="kind">Kind</option></select>' +
      '<button class="secondary small" onclick="updateSqliteLookupDetailControls()">Apply</button>' +
      '<button class="secondary small" onclick="copySqliteLookupJson()">Copy JSON</button>' +
      '</div></div>' +
      '<h3>Expression Lookup</h3>' +
      '<div class="kv">' +
      '<div><b>Exact</b><br>' + esc(String(expression.exact_count || 0)) + '</div>' +
      '<div><b>Similar</b><br>' + esc(String(expression.similar_count || 0)) + '</div>' +
      '<div><b>Fingerprint</b><br>' + esc(expression.expression_fingerprint || '-') + '</div>' +
      '</div>' +
      renderSimpleDetailTable(expressionRows.slice(0, 20), ['match_type', 'alpha_id', 'source', 'status', 'score', 'similarity', 'expression_canonical']) +
      '<h3>Record Lookup</h3>' +
      '<div class="kv"><div><b>Query</b><br>' + esc(record.alpha_id || '-') + '</div><div><b>Records</b><br>' + esc(String(record.count || 0)) + '</div></div>' +
      renderSimpleDetailTable(recordRows.slice(0, 30), ['kind', 'alpha_id', 'official_alpha_id', 'simulation_id', 'status', 'action', 'timestamp']) +
      '<h3>Raw JSON</h3><div class="copy-box">' + esc(JSON.stringify(lookup, null, 2)) + '</div>';
    var sortEl = $('sqliteLookupDetailSort');
    if (sortEl) sortEl.value = sortKey;
    modal.classList.remove('hidden');
  };

  window.updateSqliteLookupDetailControls = function () {
    var filterInput = $('sqliteLookupDetailFilter');
    var sortInput = $('sqliteLookupDetailSort');
    S.merge('currentResult.sqlite_lookup', {
      detail_filter: filterInput ? filterInput.value : '',
      detail_sort: sortInput ? sortInput.value : 'timestamp',
    });
    window.openSqliteLookupDetail();
  };

  window.copySqliteLookupJson = function () {
    return window.copyText(JSON.stringify(currentSqliteLookup(), null, 2));
  };

  function filteredLookupRows(rows, filterText) {
    if (!filterText) return rows;
    return rows.filter(function (row) {
      return JSON.stringify(row || {}).toLowerCase().indexOf(filterText) !== -1;
    });
  }

  function sortedLookupRows(rows, sortKey) {
    rows = rows.slice();
    rows.sort(function (a, b) {
      var av = a && a[sortKey];
      var bv = b && b[sortKey];
      var an = Number(av);
      var bn = Number(bv);
      if (Number.isFinite(an) || Number.isFinite(bn)) return (Number.isFinite(bn) ? bn : -Infinity) - (Number.isFinite(an) ? an : -Infinity);
      return String(bv || '').localeCompare(String(av || ''));
    });
    return rows;
  }

  window.openRobustnessDetail = function () {
    var snapshot = currentRobustnessSnapshot();
    if (!snapshot || !snapshot.schema_version) snapshot = buildRobustnessSnapshot();
    var modal = $('detailModal');
    var title = $('modalTitle');
    var body = $('detail');
    if (!modal || !title || !body) return;
    title.textContent = 'Robustness Detail';
    body.innerHTML =
      '<div class="kv">' +
      '<div><b>Candidates</b><br>' + esc(String(snapshot.candidate_count || 0)) + '</div>' +
      '<div><b>Anti Reports</b><br>' + esc(String(snapshot.anti_report_count || 0)) + '</div>' +
      '<div><b>Rolling Reports</b><br>' + esc(String(snapshot.rolling_report_count || 0)) + '</div>' +
      '<div><b>Blocked</b><br>' + esc(String(snapshot.blocked_count || 0)) + '</div>' +
      '</div>' +
      '<h3>Candidate Examples</h3>' +
      renderSimpleDetailTable((snapshot.examples || []).slice(0, 30), ['alpha_id', 'anti', 'rolling', 'score', 'blocked']) +
      '<h3>Latest API Results</h3><div class="copy-box">' + esc(JSON.stringify({
        anti_overfit: snapshot.latest_anti_overfit || {},
        rolling_validation: snapshot.latest_rolling_validation || {},
        batch: snapshot.latest_batch || {},
      }, null, 2)) + '</div>' +
      '<h3>Raw Snapshot</h3><div class="copy-box">' + esc(JSON.stringify(snapshot, null, 2)) + '</div>';
    modal.classList.remove('hidden');
  };

  function renderSimpleDetailTable(rows, columns) {
    rows = Array.isArray(rows) ? rows : [];
    columns = Array.isArray(columns) ? columns : [];
    if (!rows.length) return '<div class="copy-box">No rows.</div>';
    return '<table class="detail-table"><thead><tr>' +
      columns.map(function (col) { return '<th>' + esc(col) + '</th>'; }).join('') +
      '</tr></thead><tbody>' +
      rows.map(function (row) {
        return '<tr>' + columns.map(function (col) {
          var value = row && row[col];
          if (value && typeof value === 'object') value = JSON.stringify(value);
          return '<td>' + esc(value === undefined || value === null ? '-' : String(value)) + '</td>';
        }).join('') + '</tr>';
      }).join('') +
      '</tbody></table>';
  }

  function scoreClass(value) {
    var n = Number(value || 0);
    return n >= 85 ? 'badge-good' : n >= 70 ? 'badge-warn' : n >= 50 ? 'badge-info' : 'badge-bad';
  }

  function candidateStatusLabel(candidate, checked, stale) {
    if (checked) return '检查通过';
    if (stale) return '检查已过期';
    if ((candidate.gate || {}).submission_ready) return '达标待查';
    return statusLabelFromCode(candidate.lifecycle_status || (candidate.gate || {}).status || (candidate.validation || {}).status || '-');
  }

  function assistantGuidanceBrief(candidate) {
    var sub = (candidate || {}).submission || {};
    if (!sub.assistant_guidance_digest) return '';
    var status = sub.assistant_guidance_outcome_status && sub.assistant_guidance_outcome_status !== 'unknown'
      ? ' ' + sub.assistant_guidance_outcome_status
      : '';
    return 'guidance ' + sub.assistant_guidance_digest + status;
  }

  function attention(candidate) {
    var gate = candidate.gate || {};
    var base = '-';
    if (gate.failed_reasons && gate.failed_reasons.length) base = gate.failed_reasons.slice(0, 2).join('；');
    else if (gate.warnings && gate.warnings.length) base = gate.warnings.slice(0, 2).join('；');
    else if ((candidate.local_quality || {}).reasons) base = (candidate.local_quality.reasons || []).slice(0, 2).join('；');
    var guidance = assistantGuidanceBrief(candidate);
    if (!guidance) return base;
    return base === '-' ? guidance : base + ' | ' + guidance;
  }

  function statusText(status) {
    return statusLabelFromCode(status || '-');
  }

  function statusLabelFromCode(status) {
    var raw = String(status || '-');
    var key = raw.toLowerCase();
    var map = {
      queued: '排队',
      running: '运行中',
      active: '运行中',
      submitted: '已提交',
      completed: '完成',
      stopped: '已停止',
      failed: '失败',
      pass: '通过',
      passed: '通过',
      fail: '未通过',
      empty: '空闲',
      capacity_wait: '官方容量等待',
      loaded: '已加载',
      synced: '已同步',
      unsubmittable: '不可提交',
      submission_ready: '达标',
      official_check_pending: '官方检查待定未提交',
      official_check_failed: '官方检查未通过',
      official_validation_passed: '预检通过',
      official_validation_failed: '预检失败',
      official_standard_rejected: '官方拒绝',
      official_deferred: '官方容量等待',
      simulation_deferred_concurrency_limit: '官方并发等待',
      simulation_deferred_rate_limit: '官方限流等待',
      official_validation_deferred_rate_limit: '预检限流等待',
      simulation_retry_pending: '等待重试回测',
      backtest_slot_selected: '准备提交回测',
      backtest_batch_selected: '等待提交回测',
    };
    return map[key] || raw;
  }

  function emptyText(view) {
    var phase = (S.get('liveProgress') || {}).phase || '';
    if (view === 'candidates' && ['auth', 'cloud_sync', 'context', 'startup'].indexOf(phase) !== -1) {
      return phaseName(phase) + '中，完成后开始本地生产、评分和排序。';
    }
    if (view === 'research_memory') return 'No research memory yet; run production or import local JSONL records first.';
    if (view === 'research_observability') return 'No local observability snapshot yet.';
    if (view === 'research_knowledge') return 'No structured research knowledge records yet.';
    if (view === 'prompt_runs') return 'No prompt run ledger records yet.';
    if (view === 'sqlite_indexes') return 'SQLite index cache is not built yet; JSONL remains available.';
    if (view === 'robustness') return 'No robustness reports are attached to current candidates yet.';
    var messages = {
      candidates: '暂无候选；点击开始生产后，这里会显示本地评分排序后的候选。',
      pending_backtest: '暂无等待回测 Alpha。',
      running_backtest: '暂无正在回测的槽位。',
      backtest_rework: '暂无回测失败或二次融合记录。',
      passed: '暂无达标 Alpha。',
      submittable: '暂无可提交 Alpha；请先在达标列表执行检查。',
      submitted: '暂无已提交记录。',
      failed: '暂无不达标回溯记录。',
      cloud: '暂无云端统计；登录后同步云端数据。',
      lifecycle: '暂无生命周期记录。',
    };
    return messages[view] || '暂无记录';
  }

  function renderInsightLegacyUnused() {
    var summary = currentSummary();
    var cloud = summary.cloud_sync || {};
    var processCards = [
      ['candidates', '候选池', currentCandidates().length + '/' + (summary.retained_pool_limit || configuredBudget().retained_alpha_pool_size || 10), '动态排序'],
      ['pending_backtest', '等待回测', pendingBacktestCandidates().length, '排序分优先'],
      ['running_backtest', '回测中', activeBacktestCount(currentBacktests()) + '/' + configuredBacktestSlotLimit(), '活动槽位'],
      ['backtest_rework', '失败/二次融合', backtestReworkRows().length, '硬失败沉淀'],
      ['passed', '达标', passedCandidates().length, needsCheckCount() ? needsCheckCount() + ' 个待检查' : '已检查'],
      ['submittable', '可提交', submittableCandidates().length, staleCheckCount() ? staleCheckCount() + ' 个已过期' : '检查通过'],
      ['submitted', '已提交', submittedRows().length, '生命周期/云端'],
      ['failed', '官方不达标', failedRows().length, '官方 FAIL'],
    ];
    var trackingCards = [
      ['cloud', '数据统计', cloud.scanned !== undefined ? cloud.scanned : currentCloudAlphas().length, statusLabelFromCode(cloud.status || '未同步')],
      ['lifecycle', '生命周期', lifecycleRows().length, '关键状态'],
    ];
    var container = $('insight');
    if (!container) return;
    container.innerHTML = insightGroupHtml('生产流程', processCards) + insightGroupHtml('辅助追踪', trackingCards);
  }

  function startupInsightState(summary) {
    var live = S.get('liveProgress') || {};
    var phase = String(live.phase || '').toLowerCase();
    var startupPhases = ['auth', 'cloud_sync', 'context', 'startup'];
    var noRuntimeRows = !Number((summary || {}).produced_count || 0)
      && !currentCandidates().length
      && !currentBacktests().some(function (slot) { return slot && slot.alpha_id; })
      && !currentLifecycle().length;
    var active = Boolean(S.get('isRunning')) && (startupPhases.indexOf(phase) !== -1 || noRuntimeRows);
    return {
      active: active,
      label: startupPhases.indexOf(phase) !== -1 ? phaseName(phase) + '中' : '准备中',
      note: active ? '启动后生成数据' : '关键状态',
    };
  }

  function renderInsight() {
    var summary = currentSummary();
    var cloud = summary.cloud_sync || {};
    var startup = startupInsightState(summary);
    var candidateCount = currentCandidates().length;
    var lifecycleCount = lifecycleRows().length;
    var cloudHasStatus = hasOwn(cloud, 'status') || hasOwn(cloud, 'phase') || hasOwn(cloud, 'scanned') || hasOwn(cloud, 'count');
    var cloudCount = cloudCachedCount(cloud, currentCloudAlphas().length);
    var cloudStatus = String(cloud.status || cloud.phase || '').toLowerCase();
    var cloudIsActivelySyncing = ['auth', 'scan', 'merge', 'running', 'cloud_sync'].indexOf(cloudStatus) !== -1 && hasOwn(cloud, 'scanned');
    var cloudValue = cloudIsActivelySyncing ? formatLoadedCount(cloud.scanned, cloud.total) : cloudCount;
    var cloudNote = cloud.run_status === 'skipped' || (isSkippedCloudSync(cloud) && cloudCount)
      ? '缓存已加载 / 本轮未强制同步'
      : (cloudHasStatus ? statusLabelFromCode(cloud.status || '未同步') : startup.note);
    var awaitingData = startup.active && !candidateCount;
    var memory = currentResearchMemory();
    var memoryCandidates = Number(memory.total_candidates || 0);
    var memoryFields = Array.isArray(memory.fields) ? memory.fields.length : 0;
    var memoryOperators = Array.isArray(memory.operators) ? memory.operators.length : 0;
    var memoryNote = memoryCandidates ? ('fields ' + memoryFields + ' / ops ' + memoryOperators) : 'local JSONL';
    var memoryCard = ['research_memory', 'Research Memory', startup.active && !memoryCandidates ? startup.label : memoryCandidates, memoryNote];
    var observability = currentResearchObservability();
    var observabilityExpr = observability.expression_index || {};
    var observabilityErrors = observability.errors || {};
    var observabilityValue = observabilityExpr.total_expression_records || 0;
    var observabilityNote = 'dupes ' + String(observabilityExpr.duplicate_expression_count || 0) + ' / errors ' + String(observabilityErrors.total || 0);
    if (summary.observability_throttle && summary.observability_throttle.risk_level) {
      observabilityNote += ' / risk ' + String(summary.observability_throttle.risk_level || 'unknown');
    }
    var observabilityGuidance = currentObservabilityGenerationGuidance();
    if (observabilityGuidance.active) {
      observabilityNote += ' / guide ' + String(observabilityGuidance.status || 'active') +
        ' avoid ' + String(observabilityGuidance.avoid_expression_count || 0);
    }
    var observabilityGuard = currentObservabilityOfficialCallGuard();
    if (Number(observabilityGuard.blocked_count || 0)) {
      observabilityNote += ' / guard blocked ' + String(observabilityGuard.blocked_count || 0);
    }
    var observabilityCard = ['research_observability', 'Observability', startup.active && !observabilityValue ? startup.label : observabilityValue, observabilityNote];
    var knowledge = currentResearchKnowledge();
    var knowledgeCount = Number(knowledge.count || 0);
    var knowledgeCounts = knowledge.counts || {};
    var knowledgeCard = ['research_knowledge', 'Knowledge Base', startup.active && !knowledgeCount ? startup.label : knowledgeCount, 'rules ' + String(knowledgeCounts.rules || 0) + ' / findings ' + String(knowledgeCounts.findings || 0) + ' / failures ' + String(knowledgeCounts.failures || 0)];
    var promptRuns = currentPromptRuns();
    var promptItems = Array.isArray(promptRuns.items) ? promptRuns.items : [];
    var promptLatest = promptItems[0] || {};
    var promptCard = ['prompt_runs', 'Prompt Ledger', startup.active && !promptItems.length ? startup.label : (promptRuns.count || promptItems.length || 0), promptLatest.model ? (String(promptLatest.model) + ' / ' + String(promptLatest.parse_status || 'unknown')) : 'digests only'];
    var sqlite = currentSqliteIndexes();
    var sqliteExpr = sqlite.expression_index || {};
    var sqliteRecord = sqlite.record_index || {};
    var sqliteCount = Number(sqliteExpr.total_expression_records || 0) + Number(sqliteRecord.row_count || 0);
    var sqliteNote = sqlite.has_stale_index ? 'stale cache' : (sqlite.has_missing_index ? 'partial cache' : ('dupes ' + String(sqliteExpr.duplicate_expression_count || 0)));
    var sqliteCard = ['sqlite_indexes', 'SQLite Index', startup.active && !sqliteCount ? startup.label : sqliteCount, sqliteNote];
    var robustness = currentRobustnessSnapshot();
    var robustnessCount = Number(robustness.anti_report_count || 0) + Number(robustness.rolling_report_count || 0);
    var robustnessCard = ['robustness', 'Robustness', startup.active && !robustnessCount ? startup.label : robustnessCount, 'blocked ' + String(robustness.blocked_count || 0) + ' / missing ' + String(robustness.missing_report_count || 0)];
    var processCards = [
      ['candidates', '候选池', awaitingData ? startup.label : candidateCount + '/' + (summary.retained_pool_limit || configuredBudget().retained_alpha_pool_size || 10), awaitingData ? startup.note : '动态排序'],
      ['pending_backtest', '等待回测', awaitingData ? '待生成' : pendingBacktestCandidates().length, '排序分优先'],
      ['running_backtest', '回测中', awaitingData ? '待生成' : activeBacktestCount(currentBacktests()) + '/' + configuredBacktestSlotLimit(), '活动槽位'],
      ['backtest_rework', '失败/二次融合', awaitingData ? '待生成' : backtestReworkRows().length, '硬失败沉淀'],
      ['passed', '达标', awaitingData ? '待回测' : passedCandidates().length, needsCheckCount() ? needsCheckCount() + ' 个待检查' : '已检查'],
      ['submittable', '可提交', awaitingData ? '待检查' : submittableCandidates().length, staleCheckCount() ? staleCheckCount() + ' 个已过期' : '检查通过'],
      ['submitted', '已提交', awaitingData ? '待提交' : submittedRows().length, '生命周期/云端'],
      ['failed', '官方不达标', awaitingData ? '待回测' : failedRows().length, '官方 FAIL'],
    ];
    var trackingCards = [
      observabilityCard,
      memoryCard,
      knowledgeCard,
      promptCard,
      sqliteCard,
      robustnessCard,
      ['cloud', '云端 Alpha', startup.active && !cloudHasStatus && !cloudCount ? startup.label : cloudValue, cloudNote],
      ['lifecycle', '生命周期', startup.active && !lifecycleCount ? startup.label : lifecycleCount, startup.active && !lifecycleCount ? startup.note : '关键状态'],
    ];
    var container = $('insight');
    if (!container) return;
    container.innerHTML = insightGroupHtml('生产流程', processCards) + insightGroupHtml('辅助追踪', trackingCards);
  }

  function insightGroupHtml(title, cards) {
    return '<div class="insight-group"><div class="insight-group-title">' + esc(title) + '</div><div class="insight-grid">' +
      cards.map(function (card) { return insightCardHtml(card[0], card[1], card[2], card[3]); }).join('') +
      '</div></div>';
  }

  function insightCardHtml(view, label, value, note) {
    var active = view === activeView();
    return '<button type="button" class="insight-item ' + (active ? 'active' : '') + '" data-view="' + escapeAttr(view) + '" onclick="switchView(' + jsStringAttr(view) + ')" aria-current="' + (active ? 'page' : 'false') + '">' +
      '<div class="insight-label">' + esc(label) + '</div>' +
      '<div class="insight-value">' + esc(value) + '</div>' +
      '<div class="insight-note">' + esc(note) + '</div>' +
      '</button>';
  }

  function renderOpsMonitor() {
    var container = $('opsMonitor');
    if (!container) return;
    container.innerHTML = '';
    container.classList.add('hidden');
  }

  window.renderInsight = renderInsight;
  window.renderOpsMonitor = renderOpsMonitor;

  function normalizedBacktestSlots(backtests) {
    var input = Array.isArray(backtests) ? backtests : [];
    var summary = currentSummary();
    var officialHalted = Boolean(summary.official_calls_halted);
    var haltReason = summary.official_halt_reason || 'official capacity unavailable';
    var capacityWaitSeconds = firstPositiveFiniteNumber(
      summary.official_retry_remaining_seconds,
      summary.retry_remaining_seconds,
      summary.official_retry_seconds,
      summary.retry_seconds
    ) || 0;
    var maxSlot = input.reduce(function (max, slot) {
      return Math.max(max, Number(slot.slot || 0));
    }, 0);
    var limit = Math.max(1, configuredBacktestSlotLimit(), maxSlot || 0);
    var bySlot = {};
    input.forEach(function (slot, index) {
      var key = Number(slot.slot || index + 1);
      var row = Object.assign({}, slot, { slot: key });
      if (!Number(row.next_poll_seconds || 0) && /capacity|wait|defer/i.test(String(row.status || ''))) {
        row.next_poll_seconds = capacityWaitSeconds;
      }
      bySlot[key] = row;
    });
    var slots = [];
    for (var slotNo = 1; slotNo <= limit; slotNo += 1) {
      slots.push(bySlot[slotNo] || {
        slot: slotNo,
        alpha_id: '',
        simulation_id: '',
        official_alpha_id: '',
        status: officialHalted ? 'CAPACITY_WAIT' : 'EMPTY',
        score: 0,
        progress_percent: 0,
        next_poll_seconds: officialHalted ? capacityWaitSeconds : 0,
        message: officialHalted ? ('官方调用暂停：' + haltReason) : '等待候选补位',
      });
    }
    return slots;
  }

  function renderBacktests(backtests) {
    var container = $('backtestPanel');
    if (!container) return;
    var slots = normalizedBacktestSlots(backtests);
    if (!slots.length) {
      container.innerHTML = '<div class="slot-card"><div class="slot-head"><span>暂无回测槽位</span><span>空闲</span></div><div class="track"><div class="fill" style="width:0%"></div></div><div class="message">等待高分达标候选。</div></div>';
      return;
    }
    lastRenderedBacktestSlots = slots.map(function (slot) { return Object.assign({}, slot); });
    container.innerHTML = slots.map(function (slot, index) {
      var status = String(slot.status || 'idle').toLowerCase();
      var cls = status === 'empty' ? '' : isActiveSlotStatus(status) ? 'active' : /fail|reject|error/.test(status) ? 'bad' : /defer|wait|queued|capacity/.test(status) ? 'warn' : 'done';
      var progress = Math.max(0, Math.min(100, Number(slot.progress_percent || slot.percent || (cls === 'done' ? 100 : cls === 'active' ? 50 : 0))));
      var countdown = slotCountdownText(slot);
      var detail = esc(slot.alpha_id || '等待 Alpha') + '<br>' + esc(slot.message || slot.simulation_id || '');
      if (countdown) detail += '<br>' + esc(countdown);
      return '<div class="slot-card ' + cls + '" onclick="viewRow(&quot;backtest&quot;, ' + jsStringAttr(String(slot.slot || slot.alpha_id || index)) + ', event)">' +
        '<div class="slot-head"><span>槽 ' + esc(slot.slot || index + 1) + '</span><span>' + esc(statusText(slot.status || 'idle')) + '</span></div>' +
        '<div class="track"><div class="fill" style="width:' + progress + '%"></div></div>' +
        '<div class="message">' + detail + '</div>' +
        '</div>';
    }).join('');
    scheduleBacktestCountdownRefresh(slots);
  }

  function scheduleBacktestCountdownRefresh(slots) {
    if (backtestCountdownTimer) {
      clearInterval(backtestCountdownTimer);
      backtestCountdownTimer = null;
    }
    var hasCountdown = (slots || []).some(function (slot) {
      return Number((slot || {}).next_poll_seconds || 0) > 0;
    });
    if (!hasCountdown) return;
    backtestCountdownTimer = setInterval(function () {
      var nextSlots = (lastRenderedBacktestSlots || []).map(function (slot) {
        var row = Object.assign({}, slot);
        var seconds = Number(row.next_poll_seconds || 0);
        if (seconds > 0) row.next_poll_seconds = Math.max(0, seconds - 1);
        return row;
      });
      renderBacktests(nextSlots);
    }, 1000);
  }

  window.renderBacktests = renderBacktests;

  function formatLoadedCount(count, total) {
    if (count === undefined || count === null || count === '') return '-';
    var c = Number(count);
    var t = Number(total || 0);
    if (!Number.isFinite(c)) return String(count);
    return t > 0 ? c + '/' + t : String(c);
  }

  function cloudFreshnessText(source) {
    var cloud = source || currentSummary().cloud_sync || {};
    var loadedAt = cloud.loaded_at || cloud.latest_sync_at || '';
    if (!loadedAt) return Number(cloud.count || currentCloudAlphas().length || 0) ? '最近同步时间未确认' : '未同步';
    var date = new Date(loadedAt);
    if (Number.isNaN(date.getTime())) return String(loadedAt);
    var age = cloud.age_seconds !== undefined ? Number(cloud.age_seconds) : Math.max(0, Math.round((Date.now() - date.getTime()) / 1000));
    var ageText = age < 60 ? '刚刚' : age < 3600 ? Math.floor(age / 60) + ' 分钟前' : age < 86400 ? Math.floor(age / 3600) + ' 小时前' : Math.floor(age / 86400) + ' 天前';
    return date.toLocaleString('zh-CN', { hour12: false }) + '（' + ageText + '）' + (cloud.is_stale ? '，建议刷新' : '');
  }

  function latestCheckSummary() {
    var items = Object.keys(checkResults()).map(function (key) { return checkResults()[key]; });
    if (!items.length) return '尚未检查。';
    var passed = items.filter(isFreshPassedCheck).length;
    var blocked = items.filter(function (item) { return isFreshCheck(item) && !isFreshPassedCheck(item); }).length;
    var stale = items.filter(function (item) { return isOfficialPassedCheck(item) && !isFreshPassedCheck(item); }).length;
    return '有效通过 ' + passed + ' | 阻断 ' + blocked + (stale ? ' | 过期 ' + stale : '');
  }

  function remainingText(progress, percent, startedAt) {
    progress = progress || {};
    return progressEtaText(progress, 'sync');
  }

  function stableRemainingText(progress, percent, startedAt, state) {
    return progressEtaText(progress, 'progress');
  }

  function progressEtaText(progress, keyPrefix) {
    progress = progress || {};
    var total = firstFiniteNumber(progress.progressTotal, progress.total, progress.expected_total);
    var current = firstFiniteNumber(progress.progressCurrent, progressCurrentValue(progress));
    if (isTerminalProgress(progress)) return '-';
    if (total === null || total <= 0 || current === null || current <= 0) return '计算中';
    if (current >= total) return '-';
    var remaining = estimateRemainingSeconds(progressEtaKey(progress, keyPrefix || 'progress', total), current, total);
    if (remaining === Infinity) return '等待接口返回';
    if (!Number.isFinite(remaining) || remaining < 0) return '计算中';
    return formatDuration(remaining);
  }

  function estimateRemainingSeconds(key, current, total) {
    var now = Date.now();
    var state = progressEtaState[key];
    if (!state || current < state.current || total !== state.total) {
      progressEtaState[key] = { current: current, total: total, time: now, lastEta: null };
      return NaN;
    }
    if (current === state.current) {
      if (now - state.time > 15000) return Infinity;
      return state.lastEta === null ? Infinity : state.lastEta;
    }
    var elapsed = Math.max(0.001, (now - state.time) / 1000);
    var rate = (current - state.current) / elapsed;
    if (rate <= 0) return Infinity;
    var eta = Math.max(0, Math.round((total - current) / rate));
    progressEtaState[key] = { current: current, total: total, time: now, lastEta: eta };
    return eta;
  }

  function progressCurrentValue(progress) {
    return firstFiniteNumber(
      (progress || {}).scanned,
      (progress || {}).current,
      (progress || {}).checked,
      (progress || {}).count,
      (progress || {}).loaded
    );
  }

  function progressCountdownKey(progress, total, startedAt) {
    progress = progress || {};
    return [
      progress.job_id || progress.run_id || '',
      progress.range || progress.mode || '',
      progress.phase || progress.status || '',
      total || '',
      startedAt || '',
    ].join('|');
  }

  function progressEtaKey(progress, keyPrefix, total) {
    progress = progress || {};
    return [
      keyPrefix || 'progress',
      progress.range || progress.mode || '',
      progress.phase || progress.status || '',
      progress.status_code || progress.statusCode || '',
      total || '',
    ].join(':');
  }

  function resetCountdownState(state) {
    if (!state) return;
    state.key = '';
    state.deadline = 0;
    state.lastPoint = null;
    state.lastCurrent = null;
    state.lastPercent = null;
  }

  function isTerminalProgress(progress) {
    var status = String((progress || {}).phase || (progress || {}).status || (progress || {}).status_code || '').toLowerCase();
    return ['completed', 'synced', 'failed', 'skipped', 'stopped', 'done'].indexOf(status) !== -1;
  }

  function formatDuration(seconds) {
    seconds = Math.max(0, Math.ceil(Number(seconds) || 0));
    if (seconds < 60) return seconds + ' 秒';
    var hours = Math.floor(seconds / 3600);
    var minutes = Math.floor((seconds % 3600) / 60);
    var restSeconds = seconds % 60;
    if (hours > 0) return hours + '小时 ' + String(minutes).padStart(2, '0') + '分 ' + String(restSeconds).padStart(2, '0') + '秒';
    return minutes + '分 ' + String(restSeconds).padStart(2, '0') + '秒';
  }

  function remainingTextLegacyUnused(progress, percent, startedAt) {
    progress = progress || {};
    var seconds = firstFiniteNumber(progress.remaining_seconds, progress.eta_seconds, progress.estimated_remaining_seconds);
    if (seconds === null && startedAt && percent > 0 && percent < 100) {
      var elapsed = Math.max(0, (Date.now() - startedAt) / 1000);
      seconds = elapsed * (100 - percent) / percent;
    }
    if (seconds === null || !Number.isFinite(seconds) || seconds < 1) return '计算中';
    if (seconds < 60) return Math.ceil(seconds) + ' 秒';
    if (seconds < 3600) return Math.ceil(seconds / 60) + ' 分钟';
    return Math.ceil(seconds / 3600) + ' 小时';
  }

  function updateSyncProgress(progress) {
    progress = progress || {};
    lastSyncProgressSnapshot = Object.assign({}, progress);
    var total = Number(progress.total || progress.expected_total || progress.count || 0);
    var scanned = Number(progress.scanned !== undefined ? progress.scanned : (progress.current !== undefined ? progress.current : (progress.count || 0)));
    var terminal = isTerminalProgress(progress);
    if (!terminal && !syncStartedAt) syncStartedAt = Date.now();
    if (terminal) {
      resetCountdownState(syncCountdownState);
      if (syncCountdownTimer) {
        clearInterval(syncCountdownTimer);
        syncCountdownTimer = null;
      }
    }
    var percent = Number(progress.percent);
    if (!Number.isFinite(percent)) percent = total > 0 ? Math.round(scanned / total * 100) : (terminal ? 100 : 5);
    percent = Math.max(0, Math.min(100, percent));
    var status = progress.phase_label || phaseName(progress.phase || progress.status || 'cloud_sync');
    var totalLabel = total > 0 ? scanned + '/' + total : scanned + '/待确认';
    var remaining = terminal || percent >= 100 ? '-' : stableRemainingText(progress, percent, syncStartedAt, syncCountdownState);
    if ($('cloudSyncFill')) $('cloudSyncFill').style.width = percent + '%';
    if ($('monitorCloudFill')) $('monitorCloudFill').style.width = percent + '%';
    if ($('cloudSyncMeta')) $('cloudSyncMeta').textContent = '进度：' + percent + '% | 已扫描：' + totalLabel + ' | 预计剩余：' + remaining;
    if ($('monitorCloudMeta')) $('monitorCloudMeta').textContent = '进度：' + percent + '% | 已扫描：' + totalLabel + ' | 预计剩余：' + remaining;
    if ($('monitorCloudStatus')) $('monitorCloudStatus').textContent = status;
    if ($('monitorCloudText')) $('monitorCloudText').textContent = progress.message || compactCloudText();
  }

  function scheduleSyncCountdownRefresh() {
    if (syncCountdownTimer) return;
    syncCountdownTimer = setInterval(function () {
      if (!lastSyncProgressSnapshot) return;
      updateSyncProgress(lastSyncProgressSnapshot);
    }, 1000);
  }

  function compactCloudText() {
    var cloud = currentSummary().cloud_sync || {};
    var count = cloudCachedCount(cloud, currentCloudAlphas().length);
    var suffix = cloud.run_status === 'skipped' || (isSkippedCloudSync(cloud) && count)
      ? '，本轮未强制同步'
      : '';
    return '已加载云端 Alpha ' + count + ' 条' + suffix;
  }

  window.syncCloud = async function () {
    if (syncInFlight) return;
    syncInFlight = true;
    syncStartedAt = Date.now();
    resetCountdownState(syncCountdownState);
    lastSyncProgressSnapshot = null;
    progressEtaState = {};
    if ($('syncButton')) {
      $('syncButton').disabled = true;
      $('syncButton').textContent = '同步中...';
    }
    try {
      var payload = window.collectPayload();
      payload.syncRange = (($('syncRange') || {}).value) || '3d';
      updateSyncProgress({ phase: 'queued', scanned: 0, total: 0, message: '正在创建同步任务。' });
      var data = await Api.post('/api/sync_alphas', payload);
      await waitForSync(data.job_id);
    } catch (e) {
      toast('同步失败：' + e.message, 'error');
      updateSyncProgress({ phase: 'failed', scanned: 0, total: 0, message: e.message });
    } finally {
      syncInFlight = false;
      if ($('syncButton')) {
        $('syncButton').disabled = false;
        $('syncButton').textContent = '同步云端数据';
      }
    }
  };

  async function waitForSync(jobId) {
    while (jobId) {
      await sleep(700);
      var data = await Api.get('/api/sync_status?job_id=' + encodeURIComponent(jobId));
      updateSyncProgress(data.progress || {});
      if (data.status === 'completed') {
        var result = data.result || {};
        S.set('currentResult.cloud_alphas', result.alphas || currentCloudAlphas());
        S.merge('currentResult.summary', { cloud_sync: Object.assign({}, result, { status: 'synced' }) });
        await loadCloudSnapshot();
        window.switchView('cloud');
        toast('云端同步完成。', 'success');
        return;
      }
      if (data.status === 'failed') throw new Error(data.error || (data.progress || {}).message || '同步失败');
    }
  }

  window.checkBatch = async function (mode, options) {
    options = options || {};
    if (batchCheckJobId) return;
    var candidates = mode === 'all' ? passedCandidates() : derivePassedCandidates(currentCandidates()).concat(S.get('currentResult.passed_candidates') || []);
    var byId = {};
    candidates.forEach(function (candidate) { if (candidate.alpha_id) byId[candidate.alpha_id] = candidate; });
    candidates = Object.keys(byId).map(function (key) { return byId[key]; });
    if (!candidates.length) {
      if (!options.silentEmpty) toast('当前没有达标 Alpha 可检查。', 'info');
      return;
    }
    var payload = window.collectPayload();
    payload.job_id = S.get('activeJobId') || '';
    payload.mode = mode || 'quick';
    payload.check_candidates = candidates;
    batchCheckJobId = 'starting';
    checkStartedAt = Date.now();
    resetCountdownState(checkCountdownState);
    lastCheckProgressSnapshot = null;
    progressEtaState = {};
    updateCheckControls(true);
    if ($('checkStats')) $('checkStats').textContent = '正在检查 ' + candidates.length + ' 个达标 Alpha...';
    try {
      var data = await Api.post('/api/check_batch', payload);
      batchCheckJobId = data.job_id;
      await waitForCheckBatch(data.job_id, options);
    } catch (e) {
      toast('检查失败：' + e.message, 'error');
      if ($('checkStats')) $('checkStats').textContent = e.message;
    } finally {
      batchCheckJobId = '';
      if (checkCountdownTimer) {
        clearInterval(checkCountdownTimer);
        checkCountdownTimer = null;
      }
      updateCheckControls(false);
    }
  };

  async function waitForCheckBatch(jobId, options) {
    while (jobId) {
      await sleep(700);
      var data = await Api.get('/api/check_status?job_id=' + encodeURIComponent(jobId));
      updateBatchCheckProgress(data.progress || {});
      if (data.status === 'completed') {
        applyBatchCheckResults(((data.result || {}).items) || []);
        window.switchView(submittableCandidates().length ? 'submittable' : 'passed');
        if (options.autoSubmitAfterCheck !== false && (($('autoSubmitToggle') || {}).checked) && submittableCandidates().length) {
          selectedSubmitIds = new Set(submittableCandidates().map(function (candidate) { return candidate.alpha_id; }));
          await window.submitSelectedCandidates({ auto: true });
        }
        return;
      }
      if (data.status === 'failed') throw new Error(data.error || (data.progress || {}).message || '批量检查失败');
    }
  }

  function updateBatchCheckProgress(progress) {
    progress = progress || {};
    lastCheckProgressSnapshot = Object.assign({}, progress);
    if (Array.isArray(progress.items)) applyBatchCheckResults(progress.items, false);
    var total = Math.max(0, Number(progress.total || 0));
    var checked = Math.max(0, Number(progress.checked || 0));
    var percent = progress.phase === 'completed' ? 100 : (total > 0 ? Math.round(checked / total * 100) : 0);
    if ($('checkProgressFill')) $('checkProgressFill').style.width = percent + '%';
    var terminal = isTerminalProgress(progress) || percent >= 100;
    if (terminal) {
      resetCountdownState(checkCountdownState);
      if (checkCountdownTimer) {
        clearInterval(checkCountdownTimer);
        checkCountdownTimer = null;
      }
    }
    var remaining = terminal ? '-' : progressEtaText(
      Object.assign({}, progress, {
        progressCurrent: progress.phase === 'cloud_sync' ? firstFiniteNumber(progress.cloud_scanned, progress.scanned, 0) : checked,
        progressTotal: progress.phase === 'cloud_sync' ? firstFiniteNumber(progress.cloud_total, progress.total, 0) : total,
      }),
      progress.phase === 'cloud_sync' ? 'check:cloud' : 'check:batch'
    );
    if ($('checkProgressMeta')) $('checkProgressMeta').textContent = '进度：' + percent + '% | 已检查：' + checked + '/' + total + ' | 预计剩余：' + remaining;
    if ($('checkStats')) {
      $('checkStats').textContent = [
        '模式：' + (progress.mode === 'all' ? '全部检查' : '快速检查'),
        '总数：' + (progress.total || 0),
        '已检查：' + (progress.checked || 0),
        '可提交：' + (progress.submittable || 0),
        '不可提交：' + (progress.blocked || 0),
        '失败：' + (progress.failed || 0),
      ].join(' | ');
    }
    renderOpsMonitor();
  }

  function scheduleCheckCountdownRefresh() {
    if (checkCountdownTimer) return;
    checkCountdownTimer = setInterval(function () {
      if (!lastCheckProgressSnapshot) return;
      updateBatchCheckProgress(lastCheckProgressSnapshot);
    }, 1000);
  }

  function applyBatchCheckResults(items, rerender) {
    var results = Object.assign({}, checkResults());
    (Array.isArray(items) ? items : []).forEach(function (item) {
      if (item.alpha_id) results[item.alpha_id] = item;
    });
    S.set('checkResults', results);
    if (rerender !== false) renderAll();
  }

  function updateCheckControls(disabled) {
    if ($('checkButton')) $('checkButton').disabled = disabled;
    if ($('checkMode')) $('checkMode').disabled = disabled;
    renderModuleActions();
  }

  function observabilityConfirmationMessage(advisory, actionLabel) {
    advisory = advisory || {};
    var flags = (advisory.blocking_flags || []).slice(0, 3).join(', ') || advisory.risk_level || 'unknown';
    var guard = advisory.official_call_guard || {};
    var guardNote = Number(guard.blocked_count || 0) ? ' Guard blocked ' + String(guard.blocked_count || 0) + ' recent official calls.' : '';
    var errorNote = advisory.ok === false && advisory.error ? ' Preflight unavailable: ' + String(advisory.error) + '.' : '';
    var actions = Array.isArray(advisory.actions) ? advisory.actions.slice(0, 2).join(' ') : '';
    var actionNote = actions ? ' Suggested action: ' + actions : '';
    return 'Observability blocking flags: ' + flags + '.' + guardNote + errorNote + actionNote + ' ' + actionLabel;
  }

  window.submitCandidate = async function (alphaId, options) {
    options = options || {};
    var candidate = findCandidate(alphaId);
    if (!candidate) {
      toast('找不到待提交 Alpha。', 'error');
      return;
    }
    var payload = window.collectPayload();
    payload.job_id = S.get('activeJobId') || '';
    payload.alpha_id = alphaId;
    payload.candidate = candidate;
    payload.submit_mode = options.auto ? 'auto' : 'manual';
    if (options.confirmObservabilityRisk) payload.confirm_observability_risk = true;
    submitInFlight = true;
    renderModuleActions();
    try {
      var data = await Api.post('/api/submit', payload);
      toast('提交成功：' + alphaId, 'success');
      selectedSubmitIds.delete(alphaId);
      await loadCloudSnapshot();
      return data;
    } catch (e) {
      toast('提交失败：' + e.message, 'error');
      if (e.code === 'SUBMIT_OBSERVABILITY_CONFIRMATION_REQUIRED' && !options.confirmObservabilityRisk) {
        var advisory = e.data && e.data.observability_preflight || {};
        var ok = window.Modal
          ? await window.Modal.confirmAction(observabilityConfirmationMessage(advisory, 'Continue submission?'), 'Continue', 'Cancel')
          : false;
        if (ok) {
          return window.submitCandidate(alphaId, Object.assign({}, options, { confirmObservabilityRisk: true }));
        }
      }
      return { ok: false, alpha_id: alphaId, error: e.message };
    } finally {
      submitInFlight = false;
      renderAll();
    }
  };

  window.submitSelectedCandidates = async function (options) {
    options = options || {};
    var ids = Array.from(selectedSubmitIds);
    if (!ids.length) {
      toast('请先勾选可提交 Alpha。', 'info');
      return;
    }
    var candidates = ids.map(findCandidate).filter(Boolean);
    var payload = window.collectPayload();
    payload.job_id = S.get('activeJobId') || '';
    payload.alpha_ids = ids;
    payload.submit_candidates = candidates;
    payload.submit_mode = options.auto ? 'auto' : 'manual';
    if (options.confirmObservabilityRisk) payload.confirm_observability_risk = true;
    lastSubmitPayload = payload;
    submitInFlight = true;
    renderModuleActions();
    try {
      var data = await Api.post('/api/submit_batch', payload);
      lastSubmitResults = data.results || [];
      if (data.failed) renderSubmitFailurePanel(lastSubmitResults);
      else window.clearSubmitFailurePanel();
      toast('批量提交完成：成功 ' + (data.submitted || 0) + '，失败 ' + (data.failed || 0), data.failed ? 'warning' : 'success');
      selectedSubmitIds.clear();
      await loadCloudSnapshot();
    } catch (e) {
      if (e.code === 'SUBMIT_OBSERVABILITY_CONFIRMATION_REQUIRED' && !options.confirmObservabilityRisk) {
        var advisory = e.data && e.data.observability_preflight || {};
        var ok = window.Modal
          ? await window.Modal.confirmAction(observabilityConfirmationMessage(advisory, 'Continue batch submission?'), 'Continue', 'Cancel')
          : false;
        if (ok) {
          return window.submitSelectedCandidates(Object.assign({}, options, { confirmObservabilityRisk: true }));
        }
      }
      toast('批量提交失败：' + e.message, 'error');
    } finally {
      submitInFlight = false;
      renderAll();
    }
  };

  function findCandidate(alphaId) {
    var lists = [submittableCandidates(), passedCandidates(), currentCandidates()];
    for (var i = 0; i < lists.length; i += 1) {
      for (var j = 0; j < lists[i].length; j += 1) {
        if (String(lists[i][j].alpha_id || lists[i][j].id || '') === String(alphaId)) return lists[i][j];
      }
    }
    return null;
  }

  function renderSubmitFailurePanel(results) {
    var panel = $('submitFailurePanel');
    if (!panel) return;
    var failed = (results || []).filter(function (item) { return !item.ok; });
    panel.classList.toggle('hidden', !failed.length);
    if ($('submitFailureCount')) $('submitFailureCount').textContent = failed.length + ' 个 Alpha 提交失败。';
    if ($('submitFailureList')) {
      $('submitFailureList').innerHTML = failed.map(function (item) {
        return '<div class="submit-fail-row"><b>' + esc(item.alpha_id || '-') + '</b><div class="mini">' + esc(item.error || item.error_code || '提交失败') + '</div></div>';
      }).join('');
    }
  }

  window.clearSubmitFailurePanel = function () {
    var panel = $('submitFailurePanel');
    if (panel) panel.classList.add('hidden');
    if ($('submitFailureList')) $('submitFailureList').innerHTML = '';
  };

  window.retryAllFailedSubmit = async function () {
    var failedIds = (lastSubmitResults || []).filter(function (item) { return !item.ok && item.alpha_id; }).map(function (item) { return item.alpha_id; });
    if (!failedIds.length || !lastSubmitPayload) return;
    selectedSubmitIds = new Set(failedIds);
    await window.submitSelectedCandidates({ auto: lastSubmitPayload.submit_mode === 'auto' });
  };

  window.handleAutoSubmitToggle = function () {
    selectedSubmitIds.clear();
    renderCurrentView();
  };

  window.selectAllSubmittable = function () {
    submittableCandidates().forEach(function (candidate) { if (candidate.alpha_id) selectedSubmitIds.add(candidate.alpha_id); });
    renderCurrentView();
    toast('已勾选 ' + selectedSubmitIds.size + ' 个 Alpha', 'success', 1500);
  };

  window.deselectAllSubmittable = function () {
    selectedSubmitIds.clear();
    renderCurrentView();
    toast('已取消全部勾选', 'info', 1500);
  };

  window.testConnection = async function () {
    var btn = $('connTestBtn');
    var result = $('connTestResult');
    if (btn) btn.disabled = true;
    if (result) {
      result.className = 'conn-test testing';
      result.textContent = '测试中...';
    }
    try {
      var data = await Api.post('/api/test_connection', window.collectPayload());
      if (result) {
        result.className = 'conn-test ' + (data.ok ? 'ok' : 'fail');
        result.textContent = data.ok ? '连接成功：' + (data.environment || '') : (data.error || '连接失败');
      }
    } catch (e) {
      if (result) {
        result.className = 'conn-test fail';
        result.textContent = e.message;
      }
    } finally {
      if (btn) btn.disabled = false;
    }
  };

  window.applyPreset = async function () {
    if (!Object.keys(presets).length) await loadPresets();
    var key = (($('preset') || {}).value) || '';
    var preset = presets[key] || {};
    var settings = preset.settings || {};
    Object.keys(settings).forEach(function (name) {
      var id = name === 'type' ? 'alphaType' : name;
      setVal(id, settings[name]);
    });
    toast('已应用预设：' + (preset.label || key), 'success', 1500);
  };

  async function loadPresets() {
    try {
      var data = await Api.get('/api/presets');
      presets = data.presets || {};
    } catch (e) {
      presets = {};
    }
  }

  window.copyText = async function (text) {
    try {
      await navigator.clipboard.writeText(String(text || ''));
      toast('已复制。', 'success', 1500);
    } catch (e) {
      toast('复制失败。', 'error');
    }
  };

  window.collectPayload = function () {
    var config = S.get('config') || {};
    var budget = config.budget || {};
    var scoring = config.scoring || {};
    var assistantMinConfidence = Number((($('assistantGuidanceMinConfidence') || {}).value) || budget.assistant_guidance_min_confidence || 0.6);
    var guidanceScoreMinConfidence = Number((($('assistantGuidanceScoreMinConfidence') || {}).value) || scoring.assistant_guidance_score_min_confidence || 0.6);
    var guidanceScoreMinOutcomeCount = Number((($('assistantGuidanceScoreMinOutcomeCount') || {}).value) || scoring.assistant_guidance_score_min_outcome_count || 1);
    var guidanceBonusCap = Number((($('assistantGuidanceScoreBonusCap') || {}).value) || scoring.assistant_guidance_score_bonus_cap || 4);
    var guidancePenaltyCap = Number((($('assistantGuidanceScorePenaltyCap') || {}).value) || scoring.assistant_guidance_score_penalty_cap || 5);
    var currentPluginSpecs = Array.isArray(budget.strategy_plugin_specs) ? budget.strategy_plugin_specs.join('\n') : '';
    return {
      environment: (($('environment') || {}).value) || 'production',
      username: (($('username') || {}).value) || '',
      password: (($('password') || {}).value) || '',
      token: (($('token') || {}).value) || '',
      baseUrl: (($('baseUrl') || {}).value) || '',
      syncRange: (($('syncRange') || {}).value) || '3d',
      settings: {
        instrumentType: (($('instrumentType') || {}).value) || 'EQUITY',
        region: (($('region') || {}).value) || 'USA',
        universe: (($('universe') || {}).value) || 'TOP3000',
        delay: Number((($('delay') || {}).value) || 1),
        decay: Number((($('decay') || {}).value) || 10),
        neutralization: (($('neutralization') || {}).value) || 'SUBINDUSTRY',
        truncation: Number((($('truncation') || {}).value) || 0.05),
        pasteurization: (($('pasteurization') || {}).value) || 'ON',
        unitHandling: (($('unitHandling') || {}).value) || 'VERIFY',
        nanHandling: (($('nanHandling') || {}).value) || 'ON',
        language: (($('language') || {}).value) || 'FASTEXPR',
        visualization: false,
        type: (($('alphaType') || {}).value) || 'REGULAR',
      },
      continuousMode: Boolean(config.runForever),
      strategyPluginsEnabled: $('strategyPluginsEnabled') ? Boolean($('strategyPluginsEnabled').checked) : Boolean(budget.strategy_plugins_enabled),
      strategyPluginSpecs: (($('strategyPluginSpecs') || {}).value) || currentPluginSpecs,
      useAssistantGuidance: $('useAssistantGuidance') ? Boolean($('useAssistantGuidance').checked) : budget.use_assistant_guidance !== false,
      assistantGuidanceMinConfidence: Number.isFinite(assistantMinConfidence) ? Math.max(0, Math.min(1, assistantMinConfidence)) : 0.6,
      assistantGuidanceScoreAdjustment: $('assistantGuidanceScoreAdjustment') ? Boolean($('assistantGuidanceScoreAdjustment').checked) : scoring.assistant_guidance_score_adjustment_enabled !== false,
      assistantGuidanceScoreMinConfidence: Number.isFinite(guidanceScoreMinConfidence) ? Math.max(0, Math.min(1, guidanceScoreMinConfidence)) : 0.6,
      assistantGuidanceScoreMinOutcomeCount: Number.isFinite(guidanceScoreMinOutcomeCount) ? Math.max(0, Math.min(100, Math.round(guidanceScoreMinOutcomeCount))) : 1,
      assistantGuidanceScoreBonusCap: Number.isFinite(guidanceBonusCap) ? Math.max(0, Math.min(10, guidanceBonusCap)) : 4,
      assistantGuidanceScorePenaltyCap: Number.isFinite(guidancePenaltyCap) ? Math.max(0, Math.min(10, guidancePenaltyCap)) : 5,
      autoSubmit: Boolean(($('autoSubmitToggle') || {}).checked),
    };
  };

  async function loadConfig() {
    try {
      var data = await Api.get('/api/config');
      if (data.ok) applyConfig(data.config || {});
    } catch (e) {
      toast('读取配置失败：' + e.message, 'warning');
    }
  }

  function applyConfig(config) {
    var ops = config.ops || {};
    var settings = ops.settings || {};
    var budget = ops.budget || {};
    var scoring = ops.scoring || {};
    S.set('config', { autoSubmit: Boolean(config.auto_submit), runForever: Boolean(budget.run_forever), budget: budget, scoring: scoring });
    setVal('environment', config.environment || 'production');
    setVal('baseUrl', (ops.official_api || {}).base_url || 'https://api.worldquantbrain.com');
    setVal('region', settings.region || 'USA');
    setVal('universe', settings.universe || 'TOP3000');
    setVal('delay', settings.delay !== undefined ? settings.delay : 1);
    setVal('instrumentType', settings.instrumentType || 'EQUITY');
    setVal('alphaType', settings.type || 'REGULAR');
    setVal('decay', settings.decay !== undefined ? settings.decay : 10);
    setVal('neutralization', settings.neutralization || 'SUBINDUSTRY');
    setVal('truncation', settings.truncation !== undefined ? settings.truncation : 0.05);
    setVal('pasteurization', settings.pasteurization || 'ON');
    setVal('unitHandling', settings.unitHandling || 'VERIFY');
    setVal('nanHandling', settings.nanHandling || 'ON');
    setVal('language', settings.language || 'FASTEXPR');
    if ($('strategyPluginsEnabled')) $('strategyPluginsEnabled').checked = Boolean(budget.strategy_plugins_enabled);
    setVal('strategyPluginSpecs', Array.isArray(budget.strategy_plugin_specs) ? budget.strategy_plugin_specs.join('\n') : '');
    if ($('useAssistantGuidance')) $('useAssistantGuidance').checked = budget.use_assistant_guidance !== false;
    setVal('assistantGuidanceMinConfidence', budget.assistant_guidance_min_confidence !== undefined ? budget.assistant_guidance_min_confidence : 0.6);
    if ($('assistantGuidanceScoreAdjustment')) $('assistantGuidanceScoreAdjustment').checked = scoring.assistant_guidance_score_adjustment_enabled !== false;
    setVal('assistantGuidanceScoreMinConfidence', scoring.assistant_guidance_score_min_confidence !== undefined ? scoring.assistant_guidance_score_min_confidence : 0.6);
    setVal('assistantGuidanceScoreMinOutcomeCount', scoring.assistant_guidance_score_min_outcome_count !== undefined ? scoring.assistant_guidance_score_min_outcome_count : 1);
    setVal('assistantGuidanceScoreBonusCap', scoring.assistant_guidance_score_bonus_cap !== undefined ? scoring.assistant_guidance_score_bonus_cap : 4);
    setVal('assistantGuidanceScorePenaltyCap', scoring.assistant_guidance_score_penalty_cap !== undefined ? scoring.assistant_guidance_score_penalty_cap : 5);
    renderStrategyPolicy(config);
    window.toggleEnvironment();
    renderAll();
  }

  async function loadCloudSnapshot() {
    try {
      var data = await Api.get('/api/cloud_alphas');
      if (data.ok) {
        var incomingSummary = data.summary || data.cloud_sync || {};
        window.applyCloudSnapshot(data);
        var appliedSummary = currentSummary().cloud_sync || {};
        if (isActiveCloudSync(appliedSummary) && isEmptyCloudSyncSnapshot(incomingSummary, data.alphas || [])) {
          updateSyncProgress(appliedSummary);
        } else if (!isEmptyCloudSyncSnapshot(incomingSummary, data.alphas || [])) {
          updateSyncProgress(Object.assign({ phase: incomingSummary.status || 'loaded' }, appliedSummary, incomingSummary));
        }
        renderAll();
      }
    } catch (e) {
      // The console remains usable without a cloud cache.
    }
  }

  async function loadResearchMemory() {
    try {
      var data = await Api.get('/api/research_memory?limit=5000&top_n=10');
      if (data) {
        S.set('currentResult.research_memory', data);
        renderAll();
      }
    } catch (e) {
      // Optional local cache; no toast needed.
    }
  }

  async function loadResearchKnowledge() {
    try {
      var data = await Api.get('/api/research_knowledge?limit=100&min_confidence=0');
      if (data) {
        S.set('currentResult.research_knowledge', data);
        renderAll();
      }
    } catch (e) {
      // Optional local cache; no toast needed.
    }
  }

  async function loadResearchObservability() {
    try {
      var data = await Api.get('/api/research_observability?limit=5000&top_n=10');
      if (data) {
        S.set('currentResult.research_observability', data);
        renderAll();
      }
    } catch (e) {
      // Optional local cache; no toast needed.
    }
  }

  async function loadPromptRuns() {
    try {
      var data = await Api.get('/api/prompt_runs?limit=100');
      if (data) {
        S.set('currentResult.prompt_runs', data);
        renderAll();
      }
    } catch (e) {
      // Optional local cache; no toast needed.
    }
  }

  async function loadSqliteIndexes() {
    try {
      var data = await Api.get('/api/sqlite_indexes?top_n=10');
      if (data) {
        S.set('currentResult.sqlite_indexes', data);
        renderAll();
      }
    } catch (e) {
      // Optional local cache; no toast needed.
    }
  }

  window.runSqliteExpressionLookup = async function () {
    var input = $('sqliteExpressionLookupInput');
    var expression = input ? String(input.value || '').trim() : '';
    if (!expression) {
      toast('Expression is required for SQLite lookup.', 'warning');
      return;
    }
    try {
      var data = await Api.get('/api/sqlite_expression_lookup?top_n=10&min_similarity=0.75&expression=' + encodeURIComponent(expression));
      S.merge('currentResult.sqlite_lookup', { expression: data });
      renderAll();
    } catch (e) {
      toast('SQLite expression lookup failed: ' + e.message, 'error');
    }
  };

  window.runSqliteRecordLookup = async function () {
    var input = $('sqliteRecordLookupInput');
    var alphaId = input ? String(input.value || '').trim() : '';
    if (!alphaId) {
      toast('Alpha, official alpha, or simulation id is required.', 'warning');
      return;
    }
    try {
      var data = await Api.get('/api/sqlite_record_lookup?limit=50&alpha_id=' + encodeURIComponent(alphaId));
      S.merge('currentResult.sqlite_lookup', { record: data });
      renderAll();
    } catch (e) {
      toast('SQLite record lookup failed: ' + e.message, 'error');
    }
  };

  window.runAntiOverfitForCandidate = async function (candidateId) {
    var wanted = String(candidateId || '').trim();
    if (!wanted) {
      toast('Candidate id is required for anti-overfit review.', 'warning');
      return;
    }
    try {
      var data = await Api.get('/api/anti_overfit?candidate_id=' + encodeURIComponent(wanted));
      S.merge('currentResult.robustness_snapshot', { latest_anti_overfit: data });
      applyRobustnessResultToCandidate(wanted, { anti_overfit: data });
      renderAll();
      if (data.ok) toast('Anti-overfit review completed for ' + wanted, 'success');
    } catch (e) {
      toast('Anti-overfit review failed: ' + e.message, 'error');
    }
  };

  window.runAntiOverfitForInput = function () {
    var input = $('robustnessCandidateInput');
    return window.runAntiOverfitForCandidate(input ? input.value : '');
  };

  window.runRollingValidationForCandidate = async function (candidateId, windows) {
    var wanted = String(candidateId || '').trim();
    if (!wanted) {
      toast('Candidate id is required for rolling validation.', 'warning');
      return;
    }
    var safeWindows = Math.max(2, Math.min(50, Number(windows || 4) || 4));
    try {
      var data = await Api.get('/api/rolling_validation?candidate_id=' + encodeURIComponent(wanted) + '&windows=' + encodeURIComponent(String(safeWindows)));
      S.merge('currentResult.robustness_snapshot', { latest_rolling_validation: data });
      applyRobustnessResultToCandidate(wanted, { rolling_validation: data });
      renderAll();
      if (data.ok) toast('Rolling validation completed for ' + wanted, 'success');
    } catch (e) {
      toast('Rolling validation failed: ' + e.message, 'error');
    }
  };

  window.runRollingValidationForInput = function () {
    var input = $('robustnessCandidateInput');
    return window.runRollingValidationForCandidate(input ? input.value : '', 4);
  };

  window.runRobustnessBatchForVisible = async function () {
    var snapshot = buildRobustnessSnapshot();
    var ids = (snapshot.examples || [])
      .map(function (item) { return String(item.alpha_id || '').trim(); })
      .filter(Boolean)
      .slice(0, 5);
    if (!ids.length) {
      toast('No visible candidates available for robustness batch.', 'warning');
      return;
    }
    var results = [];
    for (var i = 0; i < ids.length; i += 1) {
      var id = ids[i];
      try {
        var anti = await Api.get('/api/anti_overfit?candidate_id=' + encodeURIComponent(id));
        var rolling = await Api.get('/api/rolling_validation?candidate_id=' + encodeURIComponent(id) + '&windows=4');
        applyRobustnessResultToCandidate(id, { anti_overfit: anti, rolling_validation: rolling });
        results.push({ candidate_id: id, anti_overfit: anti, rolling_validation: rolling });
      } catch (e) {
        results.push({ candidate_id: id, error: e.message });
      }
    }
    S.merge('currentResult.robustness_snapshot', { latest_batch: { ok: true, count: results.length, items: results } });
    renderAll();
    toast('Robustness batch completed for ' + String(results.length) + ' candidates.', 'success');
  };

  function applyRobustnessResultToCandidate(candidateId, result) {
    var updateList = function (rows) {
      var changed = false;
      var next = (Array.isArray(rows) ? rows : []).map(function (candidate) {
        if (!candidateMatchesId(candidate, candidateId)) return candidate;
        changed = true;
        var copy = Object.assign({}, candidate);
        var submission = Object.assign({}, copy.submission || {});
        if (result.anti_overfit && result.anti_overfit.ok && result.anti_overfit.anti_overfit_report) {
          submission.anti_overfit_report = result.anti_overfit.anti_overfit_report;
        }
        if (result.rolling_validation && result.rolling_validation.ok && result.rolling_validation.rolling_validation_report) {
          submission.rolling_validation_report = result.rolling_validation.rolling_validation_report;
        }
        copy.submission = submission;
        return copy;
      });
      return { changed: changed, rows: next };
    };
    var candidateUpdate = updateList(currentCandidates());
    if (candidateUpdate.changed) S.set('currentResult.candidates', candidateUpdate.rows);
    var passedUpdate = updateList(S.get('currentResult.passed_candidates') || []);
    if (passedUpdate.changed) S.set('currentResult.passed_candidates', passedUpdate.rows);
  }

  function candidateMatchesId(candidate, candidateId) {
    var wanted = String(candidateId || '').trim();
    var metrics = (candidate || {}).official_metrics || (candidate || {}).metrics || {};
    var submission = (candidate || {}).submission || {};
    var ids = [
      (candidate || {}).alpha_id,
      (candidate || {}).id,
      (candidate || {}).official_alpha_id,
      (candidate || {}).simulation_id,
      metrics.official_alpha_id,
      metrics.alpha_id,
      submission.official_alpha_id,
      submission.simulation_id,
      candidateIdentity(candidate || {}),
    ];
    return ids.some(function (value) { return String(value || '').trim() === wanted; });
  }

  async function loadAssistantContext() {
    try {
      var data = await Api.get('/api/assistant_context?limit=5000&top_n=10&include_prompt=true');
      if (data) {
        S.set('currentResult.assistant_context', data);
        renderAll();
      }
    } catch (e) {
      // Optional local cache; no toast needed.
    }
  }

  async function loadAssistantGuidance() {
    try {
      var data = await Api.get('/api/assistant_guidance?limit=100');
      if (data) {
        S.set('currentResult.assistant_guidance', data);
        renderAll();
      }
    } catch (e) {
      // Optional local cache; no toast needed.
    }
  }

  async function loadProductionSnapshot() {
    try {
      var data = await Api.get('/api/latest_result');
      if (!data || data.ok === false || (!data.result && !((data.progress || {}).data))) return;
      S.set('activeJobId', data.job_id || '');
      S.set('isRunning', ['queued', 'running', 'stopping'].indexOf(String(data.status || '').toLowerCase()) !== -1);
      renderJobSnapshot(data);
    } catch (e) {
      // A fresh install may not have historical production data yet.
    }
  }

  window.WAITING_CAPACITY = 'WAITING_CAPACITY';
  window.WAITING_SUBMIT = 'WAITING_SUBMIT';
  window.CONTEXT_READY = 'CONTEXT_READY';

  window.setSyncBusy = function (busy) {
    syncInFlight = Boolean(busy);
    if ($('syncButton')) {
      $('syncButton').disabled = syncInFlight;
      $('syncButton').textContent = syncInFlight ? '同步中...' : '同步云端数据';
    }
    if ($('syncRange')) $('syncRange').disabled = syncInFlight;
  };

  window.setSubmitBusy = function (busy) {
    submitInFlight = Boolean(busy);
    renderModuleActions();
  };

  window.refreshAssistantContext = async function () {
    try {
      var data = await Api.get('/api/assistant_context?limit=5000&top_n=10&include_prompt=true');
      if (data) {
        S.set('currentResult.assistant_context', data);
        renderAll();
      }
    } catch (e) {
      toast('加载上下文包失败：' + e.message, 'warning');
    }
  };

  window.openAssistantContext = async function () {
    var data = currentAssistantContext();
    if (!data || !data.prompt) {
      await window.refreshAssistantContext();
      data = currentAssistantContext();
    }
    if (window.DetailView && data) {
      window.DetailView.renderAssistantContextDetail(data);
    }
  };

  window.refreshAssistantGuidance = async function () {
    try {
      var minConfidence = Number((($('assistantGuidanceMinConfidence') || {}).value) || 0.6);
      var query = Number.isFinite(minConfidence) ? ('?limit=100&min_confidence=' + encodeURIComponent(Math.max(0, Math.min(1, minConfidence)))) : '?limit=100';
      var data = await Api.get('/api/assistant_guidance' + query);
      if (data) {
        S.set('currentResult.assistant_guidance', data);
        renderAll();
      }
    } catch (e) {
      toast('Failed to load assistant guidance: ' + e.message, 'warning');
    }
  };

  window.openAssistantGuidance = async function () {
    var data = currentAssistantGuidance();
    if (!data || !data.guidance) {
      await window.refreshAssistantGuidance();
      data = currentAssistantGuidance();
    }
    if (window.DetailView && data) {
      window.DetailView.renderAssistantGuidanceDetail(data);
    }
  };

  window.copyAssistantPrompt = async function () {
    var data = currentAssistantContext();
    if (!data || !data.prompt) {
      await window.refreshAssistantContext();
      data = currentAssistantContext();
    }
    if (!data || !data.prompt) {
      toast('上下文包尚未生成', 'warning');
      return;
    }
    await window.copyText(data.prompt);
  };

  window.copyAssistantRequest = async function () {
    try {
      var data = await Api.get('/api/assistant_request?limit=5000&top_n=10&include_prompt=true&include_draft=true');
      if (!data || data.ok === false) {
        toast('Assistant request is not ready', 'warning');
        return;
      }
      await window.copyText(JSON.stringify(data, null, 2));
    } catch (e) {
      toast('Failed to build assistant request: ' + e.message, 'warning');
    }
  };

  function assistantInputThreshold() {
    var minConfidence = Number((($('assistantMinConfidence') || {}).value) || 0.6);
    return Number.isFinite(minConfidence) ? Math.max(0, Math.min(1, minConfidence)) : 0.6;
  }

  function guidanceHasGeneratorBias(guidance) {
    guidance = guidance || {};
    return Boolean(
      (Array.isArray(guidance.top_fields) && guidance.top_fields.length) ||
      (Array.isArray(guidance.top_operators) && guidance.top_operators.length) ||
      (Array.isArray(guidance.preferred_windows) && guidance.preferred_windows.length) ||
      (Array.isArray(guidance.field_combinations) && guidance.field_combinations.length)
    );
  }

  function guidanceHasHealthyOutcome(guidance) {
    guidance = guidance || {};
    return guidance.historical_outcome_status !== 'weak' && guidance.reason !== 'weak_historical_guidance_outcome';
  }

  function activeAssistantGuidanceOverride() {
    var raw = (($('assistantResponseInput') || {}).value) || '';
    if (assistantGuidanceOverride && raw === assistantGuidanceOverrideText) return assistantGuidanceOverride;
    return null;
  }

  function setAssistantGuidanceOverride(guidance) {
    assistantGuidanceOverride = guidance && typeof guidance === 'object' ? guidance : null;
    assistantGuidanceOverrideText = assistantGuidanceOverride ? JSON.stringify(assistantGuidanceOverride, null, 2) : '';
    if ($('assistantResponseInput')) $('assistantResponseInput').value = assistantGuidanceOverrideText;
  }

  async function fetchOfflineAssistantDraft() {
    var data = await Api.get('/api/assistant_request?limit=5000&top_n=10&include_prompt=false&include_draft=true');
    if (!data || data.ok === false || !data.offline_draft) return null;
    return data.offline_draft;
  }

  function assistantGuidancePreviewSnapshot(guidance, threshold, reason) {
    var current = currentAssistantGuidance() || {};
    var previewGuidance = Object.assign({}, guidance || {});
    var confidence = Number(previewGuidance.confidence);
    if (!Number.isFinite(confidence)) confidence = 1;
    var usable = previewGuidance.ok !== false && previewGuidance.usable !== false && confidence >= threshold && guidanceHasGeneratorBias(previewGuidance);
    previewGuidance.confidence = confidence;
    previewGuidance.min_confidence = threshold;
    previewGuidance.usable = usable;
    previewGuidance.reason = usable ? (reason || previewGuidance.reason || 'preview_only') : (confidence < threshold ? 'confidence_below_threshold' : (previewGuidance.reason || 'no_generator_bias'));
    return {
      ok: true,
      schema_version: 'assistant_guidance_preview.v1',
      enabled: $('useAssistantGuidance') ? Boolean($('useAssistantGuidance').checked) : true,
      configured_min_confidence: threshold,
      min_confidence: threshold,
      history_count: current.history_count || 0,
      history_limit: current.history_limit || 100,
      history: current.history || [],
      guidance: previewGuidance,
      outcomes: current.outcomes || {},
      preview_only: true,
    };
  }

  function guidanceHistoryItem(historyIndex) {
    var snapshot = currentAssistantGuidance() || {};
    var history = Array.isArray(snapshot.history) ? snapshot.history : [];
    var target = String(historyIndex);
    for (var i = 0; i < history.length; i += 1) {
      if (String(history[i].history_index) === target) return history[i];
    }
    return history[Number(historyIndex)] || null;
  }

  window.useSavedAssistantGuidance = async function (historyIndex) {
    if (assistantDraftInFlight) return;
    assistantDraftInFlight = true;
    renderModuleActions();
    try {
      var snapshot = currentAssistantGuidance();
      if (!snapshot || !Array.isArray(snapshot.history)) {
        await window.refreshAssistantGuidance();
      }
      var item = guidanceHistoryItem(historyIndex);
      var guidance = item && item.assistant_guidance;
      if (!guidance) {
        toast('Saved guidance is not available.', 'warning');
        return;
      }
      if (item && item.has_healthy_outcome === false) {
        toast('Saved guidance has weak historical outcomes; loaded for review.', 'warning', 2400);
      }
      if (activeView() !== 'research_memory') window.switchView('research_memory');
      setAssistantGuidanceOverride(guidance);
      toast('Saved guidance loaded for local generation.', 'success', 1600);
      await window.previewAssistantGuidance();
    } catch (e) {
      toast('Failed to load saved guidance: ' + e.message, 'warning');
    } finally {
      assistantDraftInFlight = false;
      renderModuleActions();
    }
  };

  window.useLatestAssistantGuidance = async function () {
    if (assistantDraftInFlight) return;
    var snapshot = currentAssistantGuidance();
    if (!snapshot || !Array.isArray(snapshot.history)) {
      await window.refreshAssistantGuidance();
      snapshot = currentAssistantGuidance();
    }
    var latestGuidance = (snapshot || {}).guidance || {};
    if (
      latestGuidance &&
      latestGuidance.usable !== false &&
      guidanceHasGeneratorBias(latestGuidance) &&
      guidanceHasHealthyOutcome(latestGuidance)
    ) {
      assistantDraftInFlight = true;
      renderModuleActions();
      try {
        if (activeView() !== 'research_memory') window.switchView('research_memory');
        setAssistantGuidanceOverride(latestGuidance);
        toast('Latest outcome-filtered guidance loaded.', 'success', 1600);
        await window.previewAssistantGuidance();
      } finally {
        assistantDraftInFlight = false;
        renderModuleActions();
      }
      return;
    }
    var history = Array.isArray((snapshot || {}).history) ? snapshot.history : [];
    var item = history.find(function (row) {
      return row && row.assistant_guidance && row.usable !== false && row.meets_min_confidence !== false && row.has_generator_bias !== false && row.has_healthy_outcome !== false;
    });
    if (!item) {
      toast(history.length ? 'No outcome-healthy saved guidance is ready.' : 'No saved assistant guidance yet.', 'warning');
      return;
    }
    await window.useSavedAssistantGuidance(item.history_index);
  };

  window.useOfflineAssistantDraft = async function () {
    if (assistantDraftInFlight) return;
    assistantDraftInFlight = true;
    renderModuleActions();
    try {
      var draft = await fetchOfflineAssistantDraft();
      if (!draft) {
        toast('Offline draft is not ready', 'warning');
        return;
      }
      var text = JSON.stringify(draft, null, 2);
      assistantGuidanceOverride = null;
      assistantGuidanceOverrideText = '';
      if ($('assistantResponseInput')) $('assistantResponseInput').value = text;
      toast('Offline draft loaded into Assistant JSON.', 'success', 1600);
      await window.previewAssistantGuidance();
    } catch (e) {
      toast('Failed to load offline draft: ' + e.message, 'warning');
    } finally {
      assistantDraftInFlight = false;
      renderModuleActions();
    }
  };

  window.saveOfflineAssistantDraftGuidance = async function () {
    if (assistantDraftSaveInFlight) return;
    assistantDraftSaveInFlight = true;
    renderModuleActions();
    try {
      var draft = await fetchOfflineAssistantDraft();
      if (!draft) {
        toast('Offline draft is not ready', 'warning');
        return;
      }
      var text = JSON.stringify(draft, null, 2);
      assistantGuidanceOverride = null;
      assistantGuidanceOverrideText = '';
      if ($('assistantResponseInput')) $('assistantResponseInput').value = text;
      var payload = window.collectPayload();
      payload.assistant_response = text;
      payload.min_confidence = assistantInputThreshold();
      payload.source = 'web_save_offline_draft_guidance';
      var data = await Api.post('/api/assistant_guidance', payload);
      if (!data || data.ok === false) {
        toast('Offline draft guidance save failed', 'warning');
        return;
      }
      if (data.snapshot) S.set('currentResult.assistant_guidance', data.snapshot);
      else await loadAssistantGuidance();
      renderAll();
      if (data.saved) toast('Offline draft guidance saved.', 'success', 1800);
      else toast('Offline draft not saved: ' + (data.reason || 'not usable'), 'warning', 2200);
    } catch (e) {
      toast('Offline draft guidance save failed: ' + e.message, 'warning');
    } finally {
      assistantDraftSaveInFlight = false;
      renderModuleActions();
    }
  };

  window.previewAssistantGuidance = async function () {
    if (assistantGuidancePreviewInFlight) return;
    var raw = (($('assistantResponseInput') || {}).value) || '';
    if (!raw.trim()) {
      toast('Paste assistant JSON before previewing guidance.', 'warning');
      return;
    }
    var threshold = assistantInputThreshold();
    var savedGuidance = activeAssistantGuidanceOverride();
    if (savedGuidance) {
      if (window.DetailView) window.DetailView.renderAssistantGuidanceDetail(assistantGuidancePreviewSnapshot(savedGuidance, threshold, 'saved_guidance_reuse'));
      return;
    }
    assistantGuidancePreviewInFlight = true;
    renderModuleActions();
    try {
      var data = await Api.post('/api/assistant_response/guidance', {
        text: raw,
        min_confidence: threshold,
      });
      if (!data || data.ok === false) {
        toast('Assistant guidance preview failed', 'warning');
        return;
      }
      var snapshot = {
        ok: true,
        schema_version: 'assistant_guidance_preview.v1',
        enabled: $('useAssistantGuidance') ? Boolean($('useAssistantGuidance').checked) : true,
        configured_min_confidence: threshold,
        min_confidence: threshold,
        history_count: (currentAssistantGuidance() || {}).history_count || 0,
        history_limit: (currentAssistantGuidance() || {}).history_limit || 100,
        history: (currentAssistantGuidance() || {}).history || [],
        guidance: Object.assign({ reason: data.usable === false ? 'confidence_below_threshold' : 'preview_only' }, data),
        outcomes: (currentAssistantGuidance() || {}).outcomes || {},
        preview_only: true,
      };
      if (window.DetailView) window.DetailView.renderAssistantGuidanceDetail(snapshot);
    } catch (e) {
      toast('Assistant guidance preview failed: ' + e.message, 'warning');
    } finally {
      assistantGuidancePreviewInFlight = false;
      renderModuleActions();
    }
  };

  window.saveAssistantGuidance = async function () {
    if (assistantGuidanceSaveInFlight) return;
    var raw = (($('assistantResponseInput') || {}).value) || '';
    if (!raw.trim()) {
      toast('Paste assistant JSON before saving guidance.', 'warning');
      return;
    }
    assistantGuidanceSaveInFlight = true;
    renderModuleActions();
    try {
      var minConfidence = assistantInputThreshold();
      var savedGuidance = activeAssistantGuidanceOverride();
      var payload = window.collectPayload();
      if (savedGuidance) payload.assistant_guidance = savedGuidance;
      else payload.assistant_response = raw;
      payload.min_confidence = minConfidence;
      payload.source = savedGuidance ? 'web_reuse_assistant_guidance' : 'web_save_assistant_guidance';
      var data = await Api.post('/api/assistant_guidance', payload);
      if (!data || data.ok === false) {
        toast('Assistant guidance save failed', 'warning');
        return;
      }
      if (data.snapshot) S.set('currentResult.assistant_guidance', data.snapshot);
      else await loadAssistantGuidance();
      renderAll();
      if (data.saved) toast('Assistant guidance saved for future cycles.', 'success', 1800);
      else toast('Guidance not saved: ' + (data.reason || 'not usable'), 'warning', 2200);
    } catch (e) {
      toast('Assistant guidance save failed: ' + e.message, 'warning');
    } finally {
      assistantGuidanceSaveInFlight = false;
      renderModuleActions();
    }
  };

  window.generateAssistantCandidates = async function () {
    if (assistantGenerateInFlight) return;
    assistantGenerateInFlight = true;
    renderModuleActions();
    try {
      var raw = (($('assistantResponseInput') || {}).value) || '';
      var count = Number((($('assistantCandidateCount') || {}).value) || 10);
      var minConfidence = Number((($('assistantMinConfidence') || {}).value) || 0);
      var savedGuidance = activeAssistantGuidanceOverride();
      var payload = window.collectPayload();
      payload.count = Number.isFinite(count) ? Math.max(1, Math.min(100, Math.round(count))) : 10;
      payload.use_research_memory = true;
      payload.assistant_min_confidence = Number.isFinite(minConfidence) ? Math.max(0, Math.min(1, minConfidence)) : 0;
      if (savedGuidance) payload.assistant_guidance = savedGuidance;
      else if (raw.trim()) payload.assistant_response = raw;
      var data = await Api.post('/api/generate_candidates', payload);
      if (!data || data.ok === false) {
        toast('Candidate generation failed', 'warning');
        return;
      }
      var generated = uniqueCandidates(data.candidates || []);
      S.set('currentResult.candidates', uniqueCandidates(generated.concat(currentCandidates())));
      S.merge('currentResult.summary', {
        assistant_generation: data.summary || {
          generated_count: generated.length,
          assistant_guidance: data.assistant_guidance || {},
        },
      });
      await loadAssistantGuidance();
      window.switchView('candidates');
      toast('Generated ' + generated.length + ' local candidates.', generated.length ? 'success' : 'warning', 1800);
    } catch (e) {
      toast('Assistant-guided generation failed: ' + e.message, 'warning');
    } finally {
      assistantGenerateInFlight = false;
      renderModuleActions();
    }
  };

  window.applyCloudSnapshot = function (data) {
    data = data || {};
    var rows = uniqueCandidates(Array.isArray(data.alphas) ? data.alphas : []);
    var incomingSummary = data.summary || data.cloud_sync || {};
    var mergedSummary = mergeCloudSyncSummary(currentSummary().cloud_sync, incomingSummary, rows);
    if (!(isActiveCloudSync(mergedSummary) && isEmptyCloudSyncSnapshot(incomingSummary, rows))) {
      S.set('currentResult.cloud_alphas', rows);
    }
    S.merge('currentResult.summary', { cloud_sync: mergedSummary });
  };

  window.cloudPassedCandidates = function () {
    return uniqueCandidates(currentCloudAlphas().filter(isCloudPassedUnsubmitted).map(cloudAlphaToCandidate));
  };

  window.detailedSyncStatusCode = function (source) {
    source = source || currentSummary().cloud_sync || {};
    return statusLabelFromCode(source.status_code || source.status || source.phase || '未同步');
  };

  window.contextScopeText = function () {
    var summary = currentSummary();
    var policy = summary.official_call_policy || {};
    return [
      '槽位 ' + configuredBacktestSlotLimit(),
      '预检 ' + (policy.max_official_validations_per_cycle || '-'),
      '同步 ' + (((summary.cloud_sync || {}).range) || (($('syncRange') || {}).value) || '3d'),
    ].join(' | ');
  };

  window.checkFailureSummary = function (result) {
    var checks = (result || {}).checks || [];
    var failed = checks.filter(function (row) { return row && !row.passed; });
    return failed.length ? failed.map(function (row) { return row.name || row.message || 'check_failed'; }).join('；') : '无失败项';
  };

  window.priorBreakdown = function (scorecard) {
    var dims = ((scorecard || {}).prior || {}).dimensions || {};
    var keys = Object.keys(dims);
    return keys.length ? keys.map(function (key) { return key + ':' + num(dims[key]); }).join(' | ') : '-';
  };

  window.slotTarget = function () {
    return configuredBacktestSlotLimit();
  };

  function slotCountdownText(slot) {
    var status = String((slot || {}).status || '').toLowerCase();
    var seconds = Number((slot || {}).next_poll_seconds || 0);
    if (seconds > 0) return '倒计时 ' + formatDuration(seconds) + ' 后轮询';
    if (status === 'empty') return '';
    if (/capacity|wait|defer|running|submitted|polling/.test(status)) return '倒计时等待状态更新';
    return '';
  }

  window.slotCountdownText = slotCountdownText;

  window.slotCountdownTextLegacyUnused = function (slot) {
    return slotCountdownText(slot);
  };

  window.openBacktestSlot = function (slot) {
    window.viewRow('backtest', String(slot || 1));
  };

  window.waitForJob = async function (jobId) {
    if (!jobId) return null;
    var data = await Api.get('/api/status?job_id=' + encodeURIComponent(jobId));
    if (data && data.ok !== false) renderJobSnapshot(data);
    return data;
  };

  async function loadCheckResults() {
    try {
      var data = await Api.get('/api/check_results');
      if (data.ok && Array.isArray(data.items)) {
        var results = {};
        data.items.forEach(function (item) {
          if (item.alpha_id && item.checked_at) results[item.alpha_id] = item;
        });
        S.set('checkResults', results);
        renderAll();
      }
    } catch (e) {
      // Optional recovery path.
    }
  }

  async function refreshUserProfile() {
    try {
      var data = await Api.get('/api/profile');
      if (data.ok && data.profile) renderUserProfile(data.profile);
    } catch (e) {
      renderUserProfile({ tier: 'offline', points: null });
    }
  }

  function renderUserProfile(profile) {
    var el = $('user-profile');
    if (!el) return;
    var parts = [];
    if (profile.username) parts.push('<span class="user-name" style="font-weight:800">' + esc(profile.username) + '</span>');
    parts.push('<span class="user-tier">' + esc(profile.tier || '--') + '</span>');
    if (profile.level !== undefined && profile.level !== null) parts.push('<span class="user-level">Lv.' + esc(profile.level) + '</span>');
    if (profile.points !== undefined && profile.points !== null) parts.push('<span class="user-points">' + Number(profile.points).toLocaleString() + ' pts</span>');
    el.innerHTML = parts.join(' ');
    el.className = 'user-profile' + (profile.error ? ' error' : '');
  }

  window.toggleTheme = function () {
    var current = document.documentElement.getAttribute('data-theme');
    var next = current === 'dark' ? '' : 'dark';
    document.documentElement.setAttribute('data-theme', next || '');
    localStorage.setItem('brain-ui-theme', next || 'light');
    var light = document.querySelector('.theme-icon-light');
    var dark = document.querySelector('.theme-icon-dark');
    if (next === 'dark') {
      if (light) light.style.display = 'none';
      if (dark) dark.style.display = '';
    } else {
      if (light) light.style.display = '';
      if (dark) dark.style.display = 'none';
    }
  };

  window.toggleEnvironment = function () {
    var prod = (($('environment') || {}).value) === 'production';
    if ($('credentials')) $('credentials').classList.toggle('hidden', !prod);
    if ($('productionNote')) $('productionNote').classList.toggle('hidden', !prod);
    if ($('mockNote')) $('mockNote').classList.toggle('hidden', prod);
    if ($('env-badge')) $('env-badge').textContent = prod ? 'Production' : 'Mock';
  };

  window.shutdownApp = async function () {
    var ok = window.Modal ? await window.Modal.confirmAction('关闭本地服务后，当前连续生产任务会停止。确定关闭？', '确定关闭', '取消') : false;
    if (!ok) return;
    try {
      await Api.post('/api/shutdown', {});
      document.body.innerHTML = '<div style="min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px;box-sizing:border-box;background:#f5f7fa;font-family:\'Microsoft YaHei\',\'Segoe UI\',Arial,sans-serif;color:#172033;"><div style="max-width:560px;width:100%;border:1px solid #d7dee8;border-radius:8px;background:#fff;padding:28px;box-sizing:border-box;box-shadow:0 12px 40px rgba(15,23,42,0.08);"><h1 style="margin:0 0 10px;font-size:22px;">本地服务已关闭</h1><p style="margin:0;color:#64748b;line-height:1.7;">当前页面将不再响应。请关闭浏览器标签页。</p></div></div>';
    } catch (e) {
      toast('关闭服务失败：' + e.message, 'error');
    }
  };

  function sleep(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
  }

  window.AppScoring = {
    candidateDisplayScore: candidateDisplayScore,
    cloudMetricScore: cloudMetricScore,
    extractOfficialMetrics: extractOfficialMetrics,
    scorecardFromMetrics: scorecardFromMetrics,
  };

  function init() {
    var saved = localStorage.getItem('brain-ui-theme');
    var prefersDark = window.matchMedia('(prefers-color-scheme:dark)').matches;
    if (saved === 'dark' || (!saved && prefersDark)) document.documentElement.setAttribute('data-theme', 'dark');

    var body = $('candidateRows');
    if (body) {
      body.addEventListener('click', function (event) {
        var viewBtn = event.target.closest('[data-action="view-row"]');
        if (viewBtn) {
          window.viewRow(viewBtn.dataset.kind || '', viewBtn.dataset.id || '', event);
          return;
        }
        if (event.target.closest('input, button, select, textarea, label')) return;
        var row = event.target.closest('tr[data-kind]');
        if (row) window.viewRow(row.dataset.kind || '', row.dataset.id || '', event);
      });
    }

    document.addEventListener('keydown', function (event) {
      var tag = (event.target && event.target.tagName) || '';
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      if (event.key === 'Escape') {
        var modal = $('detailModal');
        var confirm = $('confirmOverlay');
        if (modal && !modal.classList.contains('hidden')) window.closeDetailModal && window.closeDetailModal();
        else if (confirm && !confirm.classList.contains('hidden')) window.hideConfirm && window.hideConfirm();
      }
      if (event.ctrlKey && event.key === 'Enter' && typeof window.toggleRun === 'function') {
        window.toggleRun();
      }
    });

    renderAll();
    loadPresets();
    loadConfig();
    loadProductionSnapshot();
    loadCloudSnapshot();
    loadResearchObservability();
    loadResearchMemory();
    loadResearchKnowledge();
    loadPromptRuns();
    loadSqliteIndexes();
    loadAssistantContext();
    loadAssistantGuidance();
    loadCheckResults();
    refreshUserProfile();
    setInterval(refreshUserProfile, 30000);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  window._app = {
    loadConfig: loadConfig,
    loadProductionSnapshot: loadProductionSnapshot,
    loadCloudSnapshot: loadCloudSnapshot,
    loadResearchObservability: loadResearchObservability,
    loadResearchMemory: loadResearchMemory,
    loadResearchKnowledge: loadResearchKnowledge,
    loadPromptRuns: loadPromptRuns,
    loadSqliteIndexes: loadSqliteIndexes,
    loadAssistantContext: loadAssistantContext,
    loadAssistantGuidance: loadAssistantGuidance,
    loadCheckResults: loadCheckResults,
    refreshUserProfile: refreshUserProfile,
    renderCurrentView: renderCurrentView,
    renderResult: renderResult,
    renderJobSnapshot: renderJobSnapshot,
  };
})();
