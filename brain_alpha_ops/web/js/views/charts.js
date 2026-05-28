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

  function chartRows(options) {
    options = options || {};
    if (Array.isArray(options.candidates)) return candidateRows(options.candidates);
    var view = S.get('activeView') || 'candidates';
    if (view === 'cloud') return candidateRows(S.get('currentResult.cloud_alphas') || []);
    return candidateRows(S.get('currentResult.candidates') || []);
  }

  function metricsFor(row) {
    row = row || {};
    var raw = row.raw || row;
    return row.scorecard || raw.scorecard || raw.metrics || raw.is || {};
  }

  function metricNumber(row, names, fallback) {
    var metrics = metricsFor(row);
    names = Array.isArray(names) ? names : [names];
    for (var i = 0; i < names.length; i++) {
      var value = metrics[names[i]];
      var parsed = Number(value);
      if (Number.isFinite(parsed)) return parsed;
    }
    return fallback === undefined ? NaN : fallback;
  }

  function rowCreatedAt(row) {
    row = row || {};
    var raw = row.raw || row;
    return raw.created_at || raw.dateCreated || row.created_at || '';
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
      return rowCreatedAt(a).localeCompare(rowCreatedAt(b));
    }), MAX_CHART_POINTS);

    if (!sorted.length) {
      chartInstances.scoreTrend = new Chart(ctx, {
        type: 'bar', data: { labels: ['暂无数据'], datasets: [{ label: '暂无候选数据', data: [0], backgroundColor: COLORS.mutedAlpha, borderColor: COLORS.muted, borderWidth: 1 }] },
        options: chartOptions('排序分趋势', false),
      });
      return;
    }

    var labels = sorted.map(function (_, i) { return String(i + 1); });
    var scores = sorted.map(function (c) {
      var score = metricNumber(c, ['total_score', 'local_rank_score'], NaN);
      return Number.isFinite(score) ? score : metricNumber(c, 'sharpe', 0);
    });

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
      return metricNumber(c, 'sharpe', NaN);
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
      var passFail = String(metricsFor(c).pass_fail || '').toUpperCase();
      if (gate.passed === true || gate.submission_ready === true || passFail === 'PASS') passed++;
      else if (gate.passed === false || gate.status === 'BRAIN_CHECK_FAILED' || passFail === 'FAIL') failed++;
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
      return {
        turnover: metricNumber(c, ['turnover', 'turnover_raw'], 0),
        fitness: metricNumber(c, 'fitness', 0),
        sharpe: metricNumber(c, 'sharpe', 0),
      };
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

  function renderEmptyNativeChart(target, title, message) {
    if (!target) return;
    drawTitle(target.ctx, title);
    target.ctx.fillStyle = COLORS.muted;
    target.ctx.font = '12px "Microsoft YaHei", sans-serif';
    target.ctx.fillText(message || '暂无可绘制数据', 12, 48);
  }

  function drawLineChart(target, title, values, color) {
    if (!target) return;
    values = values.filter(function (v) { return Number.isFinite(v); });
    drawTitle(target.ctx, title);
    if (!values.length) {
      renderEmptyNativeChart(target, title, '暂无评分数据');
      return;
    }
    var ctx = target.ctx, width = target.width, height = target.height;
    var left = 34, right = 14, top = 38, bottom = 28;
    var chartW = Math.max(1, width - left - right);
    var chartH = Math.max(1, height - top - bottom);
    var min = Math.min.apply(null, values), max = Math.max.apply(null, values);
    if (min === max) { min -= 1; max += 1; }
    ctx.strokeStyle = COLORS.grid; ctx.lineWidth = 1;
    for (var g = 0; g <= 3; g++) {
      var yGrid = top + chartH * g / 3;
      ctx.beginPath(); ctx.moveTo(left, yGrid); ctx.lineTo(left + chartW, yGrid); ctx.stroke();
    }
    ctx.strokeStyle = color || COLORS.accent; ctx.lineWidth = 2;
    ctx.beginPath();
    values.forEach(function (value, i) {
      var x = left + (values.length === 1 ? chartW : chartW * i / (values.length - 1));
      var y = top + chartH - ((value - min) / (max - min)) * chartH;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
    ctx.fillStyle = COLORS.muted; ctx.font = '11px "Microsoft YaHei", sans-serif';
    ctx.fillText(max.toFixed(1), 4, top + 4);
    ctx.fillText(min.toFixed(1), 4, top + chartH);
  }

  function drawBarChart(target, title, values, color) {
    if (!target) return;
    values = values.filter(function (v) { return Number.isFinite(v); });
    drawTitle(target.ctx, title);
    if (!values.length) {
      renderEmptyNativeChart(target, title, '暂无分布数据');
      return;
    }
    var ctx = target.ctx, width = target.width, height = target.height;
    var left = 24, right = 12, top = 38, bottom = 24;
    var chartW = Math.max(1, width - left - right);
    var chartH = Math.max(1, height - top - bottom);
    var max = Math.max.apply(null, values.concat([1]));
    var barW = Math.max(2, chartW / values.length - 2);
    ctx.fillStyle = color || COLORS.accent;
    values.forEach(function (value, i) {
      var h = Math.max(2, Math.abs(value) / max * chartH);
      var x = left + i * (chartW / values.length);
      var y = top + chartH - h;
      ctx.fillRect(x, y, barW, h);
    });
  }

  function drawPieChart(target, title, values, colors) {
    if (!target) return;
    drawTitle(target.ctx, title);
    var total = values.reduce(function (sum, value) { return sum + Math.max(0, value); }, 0);
    if (!total) {
      renderEmptyNativeChart(target, title, '暂无门禁数据');
      return;
    }
    var ctx = target.ctx;
    var cx = target.width / 2, cy = target.height / 2 + 8;
    var radius = Math.max(42, Math.min(target.width, target.height) / 3.4);
    var start = -Math.PI / 2;
    values.forEach(function (value, i) {
      var angle = Math.max(0, value) / total * Math.PI * 2;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.arc(cx, cy, radius, start, start + angle);
      ctx.closePath();
      ctx.fillStyle = colors[i] || COLORS.muted;
      ctx.fill();
      start += angle;
    });
  }

  function renderNativeCharts(summary, candidates) {
    var rows = candidateRows(candidates);
    setChartFallback(rows.length
      ? 'Chart.js 未加载，已启用本地简版图表（本地 canvas）；表格视图仍可继续使用。'
      : '当前没有可绘制数据；表格视图仍可继续使用。');
    var sampled = sampleRows(rows, MAX_CHART_POINTS);
    var scores = sampled.map(function (c) {
      var score = metricNumber(c, ['total_score', 'local_rank_score'], NaN);
      return Number.isFinite(score) ? score : metricNumber(c, 'sharpe', NaN);
    });
    var sharpes = rows.map(function (c) { return metricNumber(c, 'sharpe', NaN); }).filter(function (v) { return Number.isFinite(v) && v !== 0; });
    var turnover = sampleRows(rows.map(function (c) { return metricNumber(c, ['turnover', 'turnover_raw'], NaN); }).filter(Number.isFinite), MAX_CHART_POINTS);
    var passed = 0, failed = 0, unchecked = 0;
    rows.forEach(function (c) {
      var gate = c.gate || {};
      var passFail = String(metricsFor(c).pass_fail || '').toUpperCase();
      if (gate.passed === true || gate.submission_ready === true || passFail === 'PASS') passed++;
      else if (gate.passed === false || gate.status === 'BRAIN_CHECK_FAILED' || passFail === 'FAIL') failed++;
      else unchecked++;
    });
    drawLineChart(nativeCanvas('scoreTrendChart'), '评分趋势', scores, COLORS.accent);
    drawBarChart(nativeCanvas('sharpeDistChart'), 'Sharpe 分布', sharpes, COLORS.blue);
    drawPieChart(nativeCanvas('gatePieChart'), '门禁通过率', [passed, failed, unchecked], [COLORS.good, COLORS.bad, COLORS.muted]);
    drawBarChart(nativeCanvas('turnoverChart'), 'Turnover 质量目标', turnover, COLORS.warn);
  }

  // ── Main Entry ─────────────────────────────────────────────────────────

  function renderCharts(options) {
    options = options || {};
    if (!isChartJsAvailable()) {
      destroyAll();
      renderNativeCharts(S.get('currentResult.summary') || {}, chartRows(options));
      return;
    }
    var summary = S.get('currentResult.summary') || {};
    var candidates = chartRows(options);
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
