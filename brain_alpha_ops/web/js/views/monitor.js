// brain_alpha_ops/web/js/views/monitor.js
// Ops monitor tiles — insight cards, stat tiles, backtest slot cards.
// v3: Redesigned with cleaner cards, better iconography, and progressive disclosure.

(function () {
  'use strict';

  var $ = window.Utils.$;
  var esc = window.Utils.escapeHtml;
  var formatScore = window.Utils.formatScore;
  var scoreSpan = window.Utils.scoreSpan;
  var S = window.AppState;

  // ── renderInsight (top insight strip) ──────────────────────────────────

  function renderInsight() {
    var container = $('insightPanel');
    if (!container) return;

    var summary = S.get('currentResult.summary') || {};
    var live = (S.get('liveProgress') || {}).data || {};
    var checks = S.get('checkResults') || {};
    var candidates = S.get('currentResult.candidates') || [];

    var passedCount = candidates.filter(function (c) {
      return c.lifecycle_status === 'submission_ready' || ((c.gate || {}).submission_ready);
    }).length;

    var freshPassed = 0, freshBlocked = 0;
    Object.keys(checks).forEach(function (aid) {
      var chk = checks[aid];
      if (S.isFreshPassedCheck(chk)) freshPassed++;
      else if (S.isFreshBlockedCheck(chk)) freshBlocked++;
    });

    var isRunning = S.get('isRunning');
    var phase = (S.get('liveProgress') || {}).phase || '';
    var phaseLabel = window.Utils.phaseName(phase);

    // Top score
    var topScore = 0;
    candidates.forEach(function (c) {
      var s = typeof window.AppScoring === 'object' && typeof window.AppScoring.candidateDisplayScore === 'function'
        ? window.AppScoring.candidateDisplayScore(c)
        : (c.scorecard || {}).total_score;
      if (s != null && Number(s) > topScore) topScore = Number(s);
    });

    var backtests = S.get('currentResult.backtests') || [];
    var runningBT = backtests.filter(function (b) { return b.status === 'active' || b.status === 'running'; }).length;

    var cards = [
      { icon: isRunning ? '⚡' : '⏸', label: '运行状态', value: isRunning ? '运行中' : '已停止',
        note: isRunning ? phaseLabel : '等待启动', accent: isRunning },
      { icon: '📋', label: '候选池', value: candidates.length,
        note: passedCount + ' 达标', accent: candidates.length > 0 },
      { icon: '📤', label: '可提交', value: freshPassed,
        note: freshBlocked + ' 阻断',
        style: freshPassed > 0 ? 'is-success' : (freshBlocked > 0 ? 'is-warning' : '') },
      { icon: '⭐', label: '最高分', value: topScore > 0 ? topScore.toFixed(1) : '-',
        note: topScore >= 70 ? '优秀' : topScore >= 50 ? '中等' : '',
        accent: topScore >= 70 },
      { icon: '🔄', label: '回测中', value: runningBT + '/' + backtests.length,
        note: backtests.length > 0 ? '活跃槽位' : '暂无',
        accent: runningBT > 0 },
    ];

    container.innerHTML = cards.map(function (card) {
      var cls = 'insight-tile';
      if (card.accent) cls += ' is-accent';
      if (card.style) cls += ' ' + card.style;
      return '<div class="' + cls + '">' +
        '<span class="insight-tile-icon">' + esc(card.icon) + '</span>' +
        '<div class="insight-tile-body">' +
        '<div class="insight-tile-label">' + esc(card.label) + '</div>' +
        '<div class="insight-tile-value">' + esc(String(card.value)) + '</div>' +
        (card.note ? '<div class="insight-tile-note">' + esc(card.note) + '</div>' : '') +
        '</div></div>';
    }).join('');
  }

  // ── renderOpsMonitor (stat grid below insight strip) ──────────────────

  function renderOpsMonitor() {
    var container = $('opsMonitor');
    if (!container) return;

    var live = (S.get('liveProgress') || {}).data || {};
    var summary = S.get('currentResult.summary') || {};
    var stats = summary.stats || {};

    var produced = stats.produced_count ?? live.produced_count ?? summary.produced_count ?? 0;
    var passed = stats.passed_count ?? live.passed_count ?? 0;
    var validationTile = stats.validation_tile || live.validation_tile || '0/0';
    var candidateCount = (S.get('currentResult.candidates') || []).length || produced;
    var submittableCount = S.submittableCount();

    var convergence = summary.convergence || live.convergence || {};
    var convergenceState = convergence.state || '-';
    var convergenceIter = convergence.iteration ?? convergence.iter ?? '-';

    var strategyPerf = summary.strategy_performance || live.strategy_performance || {};
    var topSharpe = strategyPerf.top_sharpe ?? summary.top_sharpe ?? '-';
    var dataset = live.dataset_id || summary.dataset_id || '—';

    var officialCap = summary.official_capacity || live.official_capacity || {};
    var capacityUsed = officialCap.used ?? officialCap.submitted ?? '-';
    var capacityTotal = officialCap.total ?? officialCap.limit ?? '-';

    var tiles = [
      { label: '本地生产', value: produced, note: '累计' },
      { label: '候选池', value: candidateCount, note: passed + ' 达标' },
      { label: '预检', value: validationTile, note: '通过/尝试' },
      { label: '可提交', value: submittableCount, note: '通过预检' },
      { label: '收敛', value: convergenceState, note: '迭代 ' + convergenceIter },
      { label: 'Top Sharpe', value: topSharpe !== '-' ? formatScore(topSharpe) : '-', note: '策略最优' },
      { label: '数据集', value: dataset, note: '当前' },
      { label: '官方容量', value: capacityUsed + '/' + capacityTotal, note: '已用/总计' },
    ];

    container.innerHTML = tiles.map(function (tile) {
      return '<div class="stat-tile">' +
        '<div class="stat-label">' + esc(tile.label) + '</div>' +
        '<div class="stat-value">' + esc(String(tile.value)) + '</div>' +
        (tile.note ? '<div class="stat-note">' + esc(tile.note) + '</div>' : '') +
        '</div>';
    }).join('');
    container.classList.remove('hidden');
  }

  // ── renderBacktests (slot cards) ──────────────────────────────────────

  function renderBacktests(backtests) {
    var container = $('backtestPanel');
    if (!container) return;

    if (!backtests || !backtests.length) {
      container.innerHTML = '<div style="padding:var(--sp-5);text-align:center;color:var(--text-muted);font-size:var(--fs-sm)">暂无回测槽位。启动生产后将自动填充。</div>';
      return;
    }

    container.innerHTML = backtests.map(function (bt, idx) {
      var status = bt.status || 'idle';
      var statusClass, badgeClass;
      switch (status) {
        case 'active': case 'running': statusClass = 'is-active'; badgeClass = 'badge-info'; break;
        case 'completed': case 'done': statusClass = 'is-done'; badgeClass = 'badge-success'; break;
        case 'failed': case 'error': statusClass = 'is-error'; badgeClass = 'badge-danger'; break;
        case 'waiting': case 'queued': statusClass = 'is-warn'; badgeClass = 'badge-warning'; break;
        default: statusClass = ''; badgeClass = 'badge-default';
      }

      var alphaId = bt.alpha_id || bt.id || '-';
      var sharpe = bt.sharpe != null ? formatScore(bt.sharpe) : '-';
      var fitness = bt.fitness != null ? formatScore(bt.fitness) : '-';

      return '<div class="slot-card ' + statusClass + '" data-slot="' + idx + '">' +
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">' +
        '<span style="font-weight:700;font-size:var(--fs-sm)">槽 #' + (idx + 1) + '</span>' +
        '<span class="badge ' + badgeClass + '">' + esc(status) + '</span>' +
        '</div>' +
        '<div style="font-size:var(--fs-xs);color:var(--text-secondary);display:grid;gap:2px">' +
        '<div>Alpha: ' + esc(alphaId) + '</div>' +
        '<div>Sharpe: ' + scoreSpan(Number(sharpe) || 0) + ' | Fitness: ' + scoreSpan(Number(fitness) || 0) + '</div>' +
        '</div></div>';
    }).join('');
  }

  // ── Public API ────────────────────────────────────────────────────────
  window.MonitorView = {
    renderOpsMonitor: renderOpsMonitor,
    renderInsight: renderInsight,
    renderBacktests: renderBacktests,
  };

  // Backward-compat global aliases
  window.renderOpsMonitor = renderOpsMonitor;
  window.renderBacktests = renderBacktests;
  window.renderInsight = renderInsight;
})();
