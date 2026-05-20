// brain_alpha_ops/web/js/views/monitor.js
// Ops monitor tiles — stat tiles, insight card, and backtest slots.
// IIFE exposes to window namespace.

(function () {
  'use strict';

  var $ = window.Utils.$;
  var esc = window.Utils.escapeHtml;
  var formatScore = window.Utils.formatScore;
  var scoreSpan = window.Table.scoreSpan;

  // ---------- Tile helpers --------------------------------------------------

  function tileHTML(label, value, sub, extraClass) {
    var cls = 'monitor-tile' + (extraClass ? ' ' + extraClass : '');
    return '<div class="' + cls + '">' +
      '<div class="tile-label">' + esc(label) + '</div>' +
      '<div class="tile-value">' + esc(String(value ?? '-')) + '</div>' +
      (sub ? '<div class="tile-sub">' + esc(sub) + '</div>' : '') +
      '</div>';
  }

  function scoreTile(label, val) {
    return '<div class="monitor-tile">' +
      '<div class="tile-label">' + esc(label) + '</div>' +
      '<div class="tile-value">' + scoreSpan(val) + '</div>' +
      '</div>';
  }

  // ---------- renderOpsMonitor ----------------------------------------------

  function renderOpsMonitor() {
    var container = $('opsMonitor');
    if (!container) return;

    var live = (AppState.get('liveProgress') || {}).data || {};
    var summary = AppState.get('currentResult.summary') || {};
    var stats = summary.stats || {};

    // Merge: live data may override summary during active run
    var produced = stats.produced_count ?? live.produced_count ?? summary.produced_count ?? 0;
    var passed = stats.passed_count ?? live.passed_count ?? 0;
    var validationTile = stats.validation_tile || live.validation_tile || '0/0';
    var activeBacktests = stats.active_backtests ?? live.active_backtests ?? 0;
    var candidateCount = (AppState.get('currentResult.candidates') || []).length || produced;
    var submittableCount = (AppState.get('currentResult.candidates') || []).filter(function (c) {
      return AppState.isSubmittable(c);
    }).length;

    // Convergence status
    var convergence = summary.convergence || live.convergence || {};
    var convergenceState = convergence.state || '-';
    var convergenceIter = convergence.iteration ?? convergence.iter ?? '-';

    // Strategy performance
    var strategyPerf = summary.strategy_performance || live.strategy_performance || {};
    var topSharpe = strategyPerf.top_sharpe ?? summary.top_sharpe ?? '-';
    var avgSharpe = strategyPerf.avg_sharpe ?? summary.avg_sharpe ?? '-';

    // Dataset info
    var dataset = live.dataset_id || summary.dataset_id || '\u2014';

    // Official capacity
    var officialCap = summary.official_capacity || live.official_capacity || {};
    var capacityUsed = officialCap.used ?? officialCap.submitted ?? '-';
    var capacityTotal = officialCap.total ?? officialCap.limit ?? '-';

    var tiles = [
      tileHTML('本地生产', produced, '累计产量'),
      tileHTML('候选池', candidateCount, passed + ' 达标'),
      tileHTML('回测前预检', validationTile, '通过/尝试'),
      tileHTML('达标', passed, 'submission_ready'),
      tileHTML('可提交', submittableCount, '已通过预检'),
      tileHTML('收敛状态', convergenceState, '迭代 ' + convergenceIter),
      tileHTML('策略表现', '-', topSharpe !== '-' ? 'Top Sharpe: ' + formatScore(topSharpe) : ''),
      tileHTML('数据集', dataset, '当前数据集'),
      tileHTML('官方容量', capacityUsed + '/' + capacityTotal, '已用/总容量'),
    ];

    container.innerHTML = tiles.join('');
  }

  // ---------- renderInsight -------------------------------------------------

  function renderInsight() {
    var container = $('insight');
    if (!container) return;

    var summary = AppState.get('currentResult.summary') || {};
    var live = (AppState.get('liveProgress') || {}).data || {};
    var checks = AppState.get('checkResults') || {};

    var candidates = AppState.get('currentResult.candidates') || [];
    var passedCount = candidates.filter(function (c) {
      return (c.lifecycle_status === 'submission_ready') ||
        ((c.gate || {}).submission_ready);
    }).length;

    var freshPassed = 0;
    var freshBlocked = 0;
    Object.keys(checks).forEach(function (aid) {
      var chk = checks[aid];
      if (AppState.isFreshPassedCheck(chk)) freshPassed++;
      else if (AppState.isFreshBlockedCheck(chk)) freshBlocked++;
    });

    var isRunning = AppState.get('isRunning');
    var phase = (AppState.get('liveProgress') || {}).phase || '';
    var phaseLabel = window.Utils.phaseName(phase);

    var cards = [];

    // Status card
    cards.push(
      '<div class="insight-card">' +
      '<div class="insight-card-head">运行状态</div>' +
      '<div class="insight-card-body">' +
      '<span class="pill" style="background:var(--' + (isRunning ? 'good-soft' : 'soft') + ');color:var(--' + (isRunning ? 'good' : 'muted') + ')">' +
      (isRunning ? '运行中 — ' + esc(phaseLabel) : '已停止') +
      '</span>' +
      '</div></div>'
    );

    // Production count card
    cards.push(
      '<div class="insight-card">' +
      '<div class="insight-card-head">候选统计</div>' +
      '<div class="insight-card-body">' +
      '<div class="insight-stat">总候选 <strong>' + candidates.length + '</strong></div>' +
      '<div class="insight-stat">达标 <strong>' + passedCount + '</strong></div>' +
      '</div></div>'
    );

    // Check status card
    cards.push(
      '<div class="insight-card">' +
      '<div class="insight-card-head">预检状态</div>' +
      '<div class="insight-card-body">' +
      '<div class="insight-stat">新鲜通过 <strong style="color:var(--good)">' + freshPassed + '</strong></div>' +
      '<div class="insight-stat">阻断 <strong style="color:var(--bad)">' + freshBlocked + '</strong></div>' +
      '</div></div>'
    );

    // Score summary card
    var topScore = 0;
    candidates.forEach(function (c) {
      var s = window.AppScoring && typeof window.AppScoring.candidateDisplayScore === 'function'
        ? window.AppScoring.candidateDisplayScore(c)
        : (c.scorecard || {}).total_score;
      if (s != null && Number(s) > topScore) topScore = Number(s);
    });
    if (topScore > 0) {
      cards.push(
        '<div class="insight-card">' +
        '<div class="insight-card-head">质量峰值</div>' +
        '<div class="insight-card-body">' +
        '<div class="insight-stat">最高排序分 <strong>' + scoreSpan(topScore) + '</strong></div>' +
        '</div></div>'
      );
    }

    // Backtest active card
    var backtests = AppState.get('currentResult.backtests') || [];
    var runningBT = backtests.filter(function (b) { return b.status === 'active' || b.status === 'running'; }).length;
    cards.push(
      '<div class="insight-card">' +
      '<div class="insight-card-head">回测槽位</div>' +
      '<div class="insight-card-body">' +
      '<div class="insight-stat">运行中 <strong>' + runningBT  + '</strong> / ' + backtests.length + '</div>' +
      '</div></div>'
    );

    container.innerHTML = cards.join('');
  }

  // ---------- renderBacktests -----------------------------------------------

  function renderBacktests(backtests) {
    var container = $('backtestPanel');
    if (!container) return;

    if (!backtests || !backtests.length) {
      container.innerHTML = '<div class="monitor-empty">暂无回测槽位。</div>';
      return;
    }

    container.innerHTML = backtests.map(function (bt, idx) {
      var status = bt.status || 'idle';
      var statusColor;
      switch (status) {
        case 'active': case 'running': statusColor = 'good'; break;
        case 'completed': case 'done': statusColor = 'muted'; break;
        case 'failed': case 'error': statusColor = 'bad'; break;
        default: statusColor = 'muted';
      }

      var alphaId = bt.alpha_id || bt.id || '-';
      var sharpe = bt.sharpe != null ? formatScore(bt.sharpe) : '-';
      var fitness = bt.fitness != null ? formatScore(bt.fitness) : '-';

      return '<div class="monitor-slot" data-slot="' + idx + '">' +
        '<div class="slot-header">' +
        '<span class="slot-id">#' + (idx + 1) + '</span>' +
        '<span class="pill" style="background:var(--' + statusColor + '-soft);color:var(--' + statusColor + ')">' + esc(status) + '</span>' +
        '</div>' +
        '<div class="slot-body">' +
        '<div class="slot-row">Alpha: ' + esc(alphaId) + '</div>' +
        '<div class="slot-row">Sharpe: ' + scoreSpan(sharpe) + '</div>' +
        '<div class="slot-row">Fitness: ' + scoreSpan(fitness) + '</div>' +
        '</div>' +
        '</div>';
    }).join('');
  }

  // ---------- Public API ----------------------------------------------------

  window.MonitorView = {
    renderOpsMonitor: renderOpsMonitor,
    renderInsight: renderInsight,
    renderBacktests: renderBacktests,
  };

  // Backward-compat global aliases
  window.renderOpsMonitor = renderOpsMonitor;
  window.renderBacktests = renderBacktests;
})();
