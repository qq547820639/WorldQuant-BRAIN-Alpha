// brain_alpha_ops/web/js/views/charts.js
// Chart.js charts — score trend, Sharpe distribution, gate pie, turnover.
// v3: Enhanced with theme-aware colors and better fallback.

(function () {
  'use strict';

  var chartInstances = {};
  var MAX_CHART_POINTS = 300;
  var S = window.AppState;

  // ── Helpers ────────────────────────────────────────────────────────────

  function destroyChart(key) {
    if (chartInstances[key]) { chartInstances[key].destroy(); delete chartInstances[key]; }
  }

  function destroyAll() {
    Object.keys(chartInstances).forEach(destroyChart);
  }

  function canvasCtx(id) {
    var canvas = document.getElementById(id);
    if (!canvas) return null;
    return canvas.getContext('2d');
  }

  function isChartJsAvailable() { return typeof Chart !== 'undefined'; }

  function setChartFallback(message) {
    var el = document.getElementById('chartFallback');
    if (!el) return;
    el.textContent = message || '';
    el.classList.toggle('hidden', !message);
  }

  function safeNumber(value, fallback) {
    var parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : (fallback === undefined ? 0 : fallback);
  }

  function candidateRows(candidates) {
    return Array.isArray(candidates) ? candidates.filter(function (c) { return c && typeof c === 'object'; }) : [];
  }

  function sampleRows(rows, limit) {
    rows = Array.isArray(rows) ? rows : [];
    limit = Math.max(1, Math.floor(safeNumber(limit, MAX_CHART_POINTS)));
    if (rows.length <= limit) return rows.slice();
    var step = Math.ceil(rows.length / limit);
    var sampled = rows.filter(function (_, i) { return i % step === 0; }).slice(0, limit - 1);
    sampled.push(rows[rows.length - 1]);
    return sampled;
  }

  // ── Colors ─────────────────────────────────────────────────────────────

  var COLORS = {
    accent: '#0f766e', accentAlpha: 'rgba(15,118,110,0.18)',
    good: '#15803d', goodAlpha: 'rgba(21,128,61,0.18)',
    warn: '#a16207', warnAlpha: 'rgba(161,98,7,0.18)',
    bad: '#b91c1c', badAlpha: 'rgba(185,28,28,0.18)',
    blue: '#2563eb', blueAlpha: 'rgba(37,99,235,0.18)',
    muted: '#64748b', mutedAlpha: 'rgba(100,116,139,0.18)',
    grid: 'rgba(100,116,139,0.12)', panel: '#ffffff',
  };

  // ── Score Trend ────────────────────────────────────────────────────────

  function renderScoreTrendChart(summary, candidates) {
    var ctx = canvasCtx('scoreTrendChart');
    if (!ctx) return;
    destroyChart('scoreTrend');

    var sorted = sampleRows(candidateRows(candidates).sort(function (a, b) {
      return (a.created_at || '').localeCompare(b.created_at || '');
    }), MAX_CHART_POINTS);

    if (!sorted.length) {
      chartInstances.scoreTrend = new Chart(ctx, {
        type: 'bar', data: { labels: ['暂无数据'], datasets: [{ label: '暂无候选数据', data: [0], backgroundColor: COLORS.mutedAlpha, borderColor: COLORS.muted, borderWidth: 1 }] },
        options: chartOptions('排序分趋势', false),
      });
      return;
    }

    var labels = sorted.map(function (_, i) { return String(i + 1); });
    var scores = sorted.map(function (c) { return safeNumber((c.scorecard || {}).total_score || 0, 0); });

    var windowSize = Math.max(3, Math.floor(scores.length / 10));
    var rollingAvg = scores.map(function (_, i) {
      var start = Math.max(0, i - windowSize + 1);
      var slice = scores.slice(start, i + 1);
      return slice.reduce(function (a, b) { return a + b; }, 0) / slice.length;
    });

    chartInstances.scoreTrend = new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          { label: '排序分', data: scores, borderColor: COLORS.accent, backgroundColor: COLORS.accentAlpha, fill: false, tension: 0.3, pointRadius: scores.length > 50 ? 0 : 2, pointHoverRadius: 5 },
          { label: '滚动均值', data: rollingAvg, borderColor: COLORS.blue, backgroundColor: COLORS.blueAlpha, borderDash: [5, 3], fill: false, tension: 0.3, pointRadius: 0 },
        ],
      },
      options: chartOptions('排序分趋势', false),
    });
  }

  // ── Sharpe Distribution ────────────────────────────────────────────────

  function renderSharpeDistChart(summary, candidates) {
    var ctx = canvasCtx('sharpeDistChart');
    if (!ctx) return;
    destroyChart('sharpeDist');

    var sharpes = candidateRows(candidates).map(function (c) {
      return safeNumber((c.scorecard || {}).sharpe || 0, NaN);
    }).filter(function (v) { return Number.isFinite(v) && v !== 0; });

    if (!sharpes.length) {
      chartInstances.sharpeDist = new Chart(ctx, {
        type: 'bar', data: { labels: ['暂无数据'], datasets: [{ label: '暂无 Sharpe 数据', data: [0], backgroundColor: COLORS.mutedAlpha, borderColor: COLORS.muted, borderWidth: 1 }] },
        options: chartOptions('Sharpe 分布', false),
      });
      return;
    }

    var min = Math.min.apply(null, sharpes), max = Math.max.apply(null, sharpes);
    var range = max - min || 1, binCount = Math.min(15, Math.max(5, Math.floor(sharpes.length / 5)));
    var binWidth = range / binCount;
    var bins = new Array(binCount).fill(0);
    var binLabels = [];
    for (var i = 0; i < binCount; i++) {
      binLabels.push((min + i * binWidth).toFixed(2) + '-' + (min + (i + 1) * binWidth).toFixed(2));
    }
    sharpes.forEach(function (v) { var idx = Math.min(binCount - 1, Math.floor((v - min) / binWidth)); bins[idx]++; });

    chartInstances.sharpeDist = new Chart(ctx, {
      type: 'bar', data: { labels: binLabels, datasets: [{ label: 'Alpha 数量', data: bins, backgroundColor: COLORS.accentAlpha, borderColor: COLORS.accent, borderWidth: 1 }] },
      options: chartOptions('Sharpe 分布', false),
    });
  }

  // ── Gate Pie ───────────────────────────────────────────────────────────

  function renderGatePieChart(summary, candidates) {
    var ctx = canvasCtx('gatePieChart');
    if (!ctx) return;
    destroyChart('gatePie');

    var rows = candidateRows(candidates);
    if (!rows.length) {
      chartInstances.gatePie = new Chart(ctx, {
        type: 'doughnut', data: { labels: ['暂无数据'], datasets: [{ data: [1], backgroundColor: [COLORS.muted] }] },
        options: { responsive: true, maintainAspectRatio: false },
      });
      return;
    }

    var passed = 0, failed = 0, unchecked = 0;
    rows.forEach(function (c) {
      var gate = c.gate || {};
      if (gate.passed === true || gate.submission_ready === true) passed++;
      else if (gate.passed === false || gate.status === 'BRAIN_CHECK_FAILED') failed++;
      else unchecked++;
    });

    chartInstances.gatePie = new Chart(ctx, {
      type: 'doughnut',
      data: { labels: ['通过', '未通过', '未检查'], datasets: [{ data: [passed, failed, unchecked], backgroundColor: [COLORS.good, COLORS.bad, COLORS.mutedAlpha], borderColor: COLORS.panel, borderWidth: 2 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { title: { display: true, text: '门禁状态', font: { size: 14, weight: 'bold' } }, legend: { position: 'bottom' } } },
    });
  }

  // ── Turnover Chart ────────────────────────────────────────────────────

  function renderTurnoverChart(summary, candidates) {
    var ctx = canvasCtx('turnoverChart');
    if (!ctx) return;
    destroyChart('turnover');

    var values = sampleRows(candidateRows(candidates).map(function (c) {
      var sc = c.scorecard || {};
      return { turnover: safeNumber(sc.turnover || 0, 0), fitness: safeNumber(sc.fitness || 0, 0), sharpe: safeNumber(sc.sharpe || 0, 0) };
    }).filter(function (row) { return row.turnover !== 0 || row.fitness !== 0 || row.sharpe !== 0; }), MAX_CHART_POINTS);

    if (!values.length) {
      chartInstances.turnover = new Chart(ctx, {
        type: 'bar', data: { labels: ['暂无数据'], datasets: [{ label: '暂无数据', data: [0], backgroundColor: COLORS.mutedAlpha }] },
        options: chartOptions('Turnover vs Sharpe', true),
      });
      return;
    }

    values.sort(function (a, b) { return a.turnover - b.turnover; });
    var labels = values.map(function (_, i) { return String(i + 1); });

    chartInstances.turnover = new Chart(ctx, {
      type: 'bar',
      data: { labels: labels, datasets: [
        { label: 'Turnover', data: values.map(function (v) { return v.turnover; }), backgroundColor: COLORS.accentAlpha, borderColor: COLORS.accent, borderWidth: 1, yAxisID: 'y' },
        { label: 'Sharpe', data: values.map(function (v) { return v.sharpe; }), type: 'line', borderColor: COLORS.warn, backgroundColor: 'transparent', fill: false, tension: 0.3, pointRadius: 0, yAxisID: 'y1' },
      ]},
      options: chartOptions('Turnover vs Sharpe', true),
    });
  }

  // ── Chart Options ──────────────────────────────────────────────────────

  function chartOptions(title, hasDualAxis) {
    var opts = {
      responsive: true, maintainAspectRatio: false,
      interaction: { intersect: false, mode: 'index' },
      plugins: {
        title: { display: true, text: title, font: { size: 14, weight: 'bold' }, color: '#172033' },
        legend: { display: true, position: 'top', labels: { usePointStyle: true, boxWidth: 8 } },
        tooltip: { backgroundColor: 'rgba(23,32,51,0.9)', titleFont: { size: 12 }, bodyFont: { size: 11 } },
      },
      scales: {
        x: { grid: { color: COLORS.grid }, ticks: { maxTicksLimit: 10, color: COLORS.muted } },
        y: { type: 'linear', position: 'left', grid: { color: COLORS.grid }, ticks: { color: COLORS.muted }, title: { display: true, text: '主指标', color: COLORS.muted } },
      },
    };
    if (hasDualAxis) {
      opts.scales.y1 = { type: 'linear', position: 'right', grid: { drawOnChartArea: false }, ticks: { color: COLORS.warn }, title: { display: true, text: 'Sharpe', color: COLORS.warn } };
    }
    return opts;
  }

  // ── Native canvas fallback ─────────────────────────────────────────────

  function nativeCanvas(id) {
    var canvas = document.getElementById(id);
    if (!canvas) return null;
    var rect = canvas.getBoundingClientRect();
    var parentWidth = canvas.parentElement ? canvas.parentElement.clientWidth : 0;
    var width = Math.max(260, Math.round(rect.width || parentWidth || 360));
    var height = Math.max(180, Math.round(rect.height || 200));
    var ratio = window.devicePixelRatio || 1;
    canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
    canvas.style.width = width + 'px'; canvas.style.height = height + 'px';
    var ctx = canvas.getContext('2d');
    if (!ctx) return null;
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = COLORS.panel; ctx.fillRect(0, 0, width, height);
    return { canvas: canvas, ctx: ctx, width: width, height: height };
  }

  function drawTitle(ctx, title) {
    ctx.fillStyle = COLORS.muted; ctx.font = '700 13px "Microsoft YaHei", sans-serif';
    ctx.fillText(title, 12, 20);
  }

  function renderNativeCharts(summary, candidates) {
    // Minimal native fallback when Chart.js is unavailable
    setChartFallback('Chart.js 未加载，图表功能不可用。表格和操作仍可正常使用。');
  }

  // ── Main Entry ─────────────────────────────────────────────────────────

  function renderCharts(options) {
    options = options || {};
    if (!isChartJsAvailable()) {
      destroyAll();
      renderNativeCharts(S.get('currentResult.summary') || {}, Array.isArray(options.candidates) ? options.candidates : (S.get('currentResult.candidates') || []));
      return;
    }
    var summary = S.get('currentResult.summary') || {};
    var candidates = Array.isArray(options.candidates) ? options.candidates : (S.get('currentResult.candidates') || []);
    var hasAnyCanvas = !!(document.getElementById('scoreTrendChart') || document.getElementById('sharpeDistChart') || document.getElementById('gatePieChart') || document.getElementById('turnoverChart'));
    if (!hasAnyCanvas) return;
    setChartFallback(candidateRows(candidates).length ? '' : '当前视图暂无可绘制数据。');

    renderScoreTrendChart(summary, candidates);
    renderSharpeDistChart(summary, candidates);
    renderGatePieChart(summary, candidates);
    renderTurnoverChart(summary, candidates);
  }

  window.ChartView = { renderCharts: renderCharts, destroyAll: destroyAll };
  window.renderCharts = renderCharts;
})();
