// brain_alpha_ops/web/js/views/charts.js
// Chart.js charts — score trend, Sharpe distribution, gate pie, turnover.
// IIFE exposes to window namespace.

(function () {
  'use strict';

  var chartInstances = {};
  var MAX_CHART_POINTS = 300;

  // ---------- Helpers -------------------------------------------------------

  function destroyChart(key) {
    if (chartInstances[key]) {
      chartInstances[key].destroy();
      delete chartInstances[key];
    }
  }

  function destroyAll() {
    Object.keys(chartInstances).forEach(destroyChart);
  }

  function canvasCtx(id) {
    var canvas = document.getElementById(id);
    if (!canvas) return null;
    return canvas.getContext('2d');
  }

  function isChartJsAvailable() {
    return typeof Chart !== 'undefined';
  }

  function setChartFallback(message) {
    var el = document.getElementById('chartFallback');
    if (!el) return;
    el.textContent = message || '';
    el.classList.toggle('hidden', !message);
  }

  function displayScore(candidate) {
    if (window.AppScoring && typeof window.AppScoring.candidateDisplayScore === 'function') {
      return window.AppScoring.candidateDisplayScore(candidate);
    }
    return (candidate.scorecard || {}).total_score || 0;
  }

  function officialMetric(candidate, key) {
    var metrics = window.AppScoring && typeof window.AppScoring.extractOfficialMetrics === 'function'
      ? window.AppScoring.extractOfficialMetrics(candidate)
      : Object.assign({}, (candidate || {}).official_metrics || (candidate || {}).metrics || {});
    var value = metrics[key];
    return Number.isFinite(Number(value)) ? Number(value) : 0;
  }

  function safeNumber(value, fallback) {
    var parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : (fallback === undefined ? 0 : fallback);
  }

  function candidateRows(candidates) {
    return Array.isArray(candidates)
      ? candidates.filter(function (candidate) { return candidate && typeof candidate === 'object'; })
      : [];
  }

  function sampleRows(rows, limit) {
    rows = Array.isArray(rows) ? rows : [];
    limit = Math.max(1, Math.floor(safeNumber(limit, MAX_CHART_POINTS)));
    if (rows.length <= limit) return rows.slice();
    var step = Math.ceil(rows.length / limit);
    var sampled = rows.filter(function (_, index) { return index % step === 0; }).slice(0, limit - 1);
    sampled.push(rows[rows.length - 1]);
    return sampled;
  }

  function renderEmptyChart(ctx, key, title, message) {
    destroyChart(key);
    chartInstances[key] = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: [message || 'No data'],
        datasets: [{
          label: message || 'No data',
          data: [0],
          backgroundColor: COLORS.mutedAlpha,
          borderColor: COLORS.muted,
          borderWidth: 1,
        }],
      },
      options: chartOptions(title, false),
    });
  }

  // ---------- Color brewer --------------------------------------------------
  // Uses CSS-variable-style colors matched to the theme

  var COLORS = {
    accent: '#0f766e',
    accentAlpha: 'rgba(15,118,110,0.18)',
    good: '#15803d',
    goodAlpha: 'rgba(21,128,61,0.18)',
    warn: '#a16207',
    warnAlpha: 'rgba(161,98,7,0.18)',
    bad: '#b91c1c',
    badAlpha: 'rgba(185,28,28,0.18)',
    blue: '#2563eb',
    blueAlpha: 'rgba(37,99,235,0.18)',
    muted: '#64748b',
    mutedAlpha: 'rgba(100,116,139,0.18)',
    grid: 'rgba(100,116,139,0.12)',
    panel: '#ffffff',
  };

  // ---------- renderScoreTrendChart -----------------------------------------

  function renderScoreTrendChart(summary, candidates) {
    var ctx = canvasCtx('scoreTrendChart');
    if (!ctx) return;

    destroyChart('scoreTrend');

    // Data: sort candidates by creation time and use the same displayed score as the main table.
    var sorted = sampleRows(candidateRows(candidates).sort(function (a, b) {
      return (a.created_at || '').localeCompare(b.created_at || '');
    }), MAX_CHART_POINTS);
    if (!sorted.length) {
      renderEmptyChart(ctx, 'scoreTrend', '排序分趋势', '暂无候选数据');
      return;
    }

    var labels = sorted.map(function (_, i) { return String(i + 1); });
    var scores = sorted.map(function (c) {
      return safeNumber(displayScore(c), 0);
    });
    var sharpes = sorted.map(function (c) {
      return safeNumber(officialMetric(c, 'sharpe'), 0);
    });

    // Rolling average for score
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
          {
            label: '排序分',
            data: scores,
            borderColor: COLORS.accent,
            backgroundColor: COLORS.accentAlpha,
            fill: false,
            tension: 0.3,
            pointRadius: scores.length > 50 ? 0 : 2,
            pointHoverRadius: 5,
          },
          {
            label: '滚动均值',
            data: rollingAvg,
            borderColor: COLORS.blue,
            backgroundColor: COLORS.blueAlpha,
            borderDash: [5, 3],
            fill: false,
            tension: 0.3,
            pointRadius: 0,
          },
          {
            label: 'Sharpe',
            data: sharpes,
            borderColor: COLORS.warn,
            backgroundColor: COLORS.warnAlpha,
            fill: false,
            tension: 0.3,
            pointRadius: 0,
            yAxisID: 'y1',
          },
        ],
      },
      options: chartOptions('排序分趋势', false),
    });
  }

  // ---------- renderSharpeDistChart -----------------------------------------

  function renderSharpeDistChart(summary, candidates) {
    var ctx = canvasCtx('sharpeDistChart');
    if (!ctx) return;

    destroyChart('sharpeDist');

    var sharpes = candidateRows(candidates).map(function (c) {
      return safeNumber((c.scorecard || {}).sharpe || officialMetric(c, 'sharpe'), NaN);
    }).filter(function (v) { return Number.isFinite(v) && v !== 0; });

    if (!sharpes.length) {
      renderEmptyChart(ctx, 'sharpeDist', 'Sharpe 分布', '暂无 Sharpe 数据');
      return;
    }

    // Build histogram bins
    var min = Math.min.apply(null, sharpes);
    var max = Math.max.apply(null, sharpes);
    var range = max - min || 1;
    var binCount = Math.min(15, Math.max(5, Math.floor(sharpes.length / 5)));
    var binWidth = range / binCount;

    var bins = [];
    var binLabels = [];
    for (var i = 0; i < binCount; i++) {
      bins[i] = 0;
      var low = min + i * binWidth;
      var high = low + binWidth;
      binLabels.push(low.toFixed(2) + '-' + high.toFixed(2));
    }

    sharpes.forEach(function (v) {
      var idx = Math.min(binCount - 1, Math.floor((v - min) / binWidth));
      bins[idx]++;
    });

    chartInstances.sharpeDist = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: binLabels,
        datasets: [{
          label: 'Alpha 数量',
          data: bins,
          backgroundColor: COLORS.accentAlpha,
          borderColor: COLORS.accent,
          borderWidth: 1,
        }],
      },
      options: chartOptions('Sharpe 分布', false),
    });
  }

  // ---------- renderGatePieChart --------------------------------------------

  function renderGatePieChart(summary, candidates) {
    var ctx = canvasCtx('gatePieChart');
    if (!ctx) return;

    destroyChart('gatePie');

    var passed = 0;
    var failed = 0;
    var unchecked = 0;

    var rows = candidateRows(candidates);
    if (!rows.length) {
      renderEmptyChart(ctx, 'gatePie', '门禁状态', '暂无门禁数据');
      return;
    }

    rows.forEach(function (c) {
      var gate = c.gate || {};
      if (gate.passed === true || gate.submission_ready === true) passed++;
      else if (gate.passed === false || gate.status === 'BRAIN_CHECK_FAILED') failed++;
      else unchecked++;
    });

    chartInstances.gatePie = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: ['通过', '未通过', '未检查'],
        datasets: [{
          data: [passed, failed, unchecked],
          backgroundColor: [COLORS.good, COLORS.bad, COLORS.mutedAlpha],
          borderColor: COLORS.panel,
          borderWidth: 2,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          title: { display: true, text: '门禁状态', font: { size: 14, weight: 'bold' }, color: '#172033' },
          legend: { position: 'bottom' },
        },
      },
    });
  }

  // ---------- renderTurnoverChart -------------------------------------------

  function renderTurnoverChart(summary, candidates) {
    var ctx = canvasCtx('turnoverChart');
    if (!ctx) return;

    destroyChart('turnover');

    var values = sampleRows(candidateRows(candidates).map(function (c) {
      var sc = c.scorecard || {};
      var turnover = safeNumber(sc.turnover || officialMetric(c, 'turnover'), NaN);
      var fitness = safeNumber(sc.fitness || officialMetric(c, 'fitness'), NaN);
      var sharpe = safeNumber(sc.sharpe || officialMetric(c, 'sharpe'), NaN);
      return {
        turnover: Number.isFinite(turnover) ? turnover : 0,
        fitness: Number.isFinite(fitness) ? fitness : 0,
        sharpe: Number.isFinite(sharpe) ? sharpe : 0,
      };
    }).filter(function (row) {
      return row.turnover !== 0 || row.fitness !== 0 || row.sharpe !== 0;
    }), MAX_CHART_POINTS);
    if (!values.length) {
      renderEmptyChart(ctx, 'turnover', 'Turnover vs Sharpe', '暂无 Turnover 数据');
      return;
    }

    // Sort by turnover for a meaningful visualization
    values.sort(function (a, b) { return a.turnover - b.turnover; });

    var labels = values.map(function (_, i) { return String(i + 1); });
    var turnovers = values.map(function (v) { return v.turnover; });
    var sharpeVals = values.map(function (v) { return v.sharpe; });

    chartInstances.turnover = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [
          {
            label: 'Turnover',
            data: turnovers,
            backgroundColor: COLORS.accentAlpha,
            borderColor: COLORS.accent,
            borderWidth: 1,
            yAxisID: 'y',
          },
          {
            label: 'Sharpe',
            data: sharpeVals,
            type: 'line',
            borderColor: COLORS.warn,
            backgroundColor: 'transparent',
            fill: false,
            tension: 0.3,
            pointRadius: 0,
            yAxisID: 'y1',
          },
        ],
      },
      options: chartOptions('Turnover vs Sharpe', true),
    });
  }

  // ---------- Shared chart options ------------------------------------------

  function chartOptions(title, hasDualAxis) {
    var opts = {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { intersect: false, mode: 'index' },
      plugins: {
        title: {
          display: true,
          text: title,
          font: { size: 14, weight: 'bold' },
          color: '#172033',
        },
        legend: {
          display: true,
          position: 'top',
          labels: { usePointStyle: true, boxWidth: 8 },
        },
        tooltip: {
          backgroundColor: 'rgba(23,32,51,0.9)',
          titleFont: { size: 12 },
          bodyFont: { size: 11 },
        },
      },
      scales: {
        x: {
          grid: { color: COLORS.grid },
          ticks: {
            maxTicksLimit: 10,
            color: COLORS.muted,
          },
        },
        y: {
          type: 'linear',
          position: 'left',
          grid: { color: COLORS.grid },
          ticks: { color: COLORS.muted },
          title: { display: true, text: '主指标', color: COLORS.muted },
        },
      },
    };

    if (hasDualAxis) {
      opts.scales.y1 = {
        type: 'linear',
        position: 'right',
        grid: { drawOnChartArea: false },
        ticks: { color: COLORS.warn },
        title: { display: true, text: 'Sharpe', color: COLORS.warn },
      };
    }

    return opts;
  }

  // ---------- Native canvas fallback ---------------------------------------

  function nativeCanvas(id) {
    var canvas = document.getElementById(id);
    if (!canvas) return null;
    var rect = canvas.getBoundingClientRect();
    var parentWidth = canvas.parentElement ? canvas.parentElement.clientWidth : 0;
    var width = Math.max(260, Math.round(rect.width || parentWidth || 360));
    var height = Math.max(180, Math.round(rect.height || 200));
    var ratio = window.devicePixelRatio || 1;
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    canvas.style.width = width + 'px';
    canvas.style.height = height + 'px';
    var ctx = canvas.getContext('2d');
    if (!ctx) return null;
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = COLORS.panel;
    ctx.fillRect(0, 0, width, height);
    return { canvas: canvas, ctx: ctx, width: width, height: height };
  }

  function drawTitle(ctx, title) {
    ctx.fillStyle = COLORS.muted;
    ctx.font = '700 13px "Microsoft YaHei", "Segoe UI", sans-serif';
    ctx.fillText(title, 12, 20);
  }

  function drawEmptyNative(id, title, message) {
    var chart = nativeCanvas(id);
    if (!chart) return;
    drawTitle(chart.ctx, title);
    chart.ctx.fillStyle = COLORS.muted;
    chart.ctx.font = '12px "Microsoft YaHei", "Segoe UI", sans-serif';
    chart.ctx.fillText(message || '暂无数据', 12, Math.round(chart.height / 2));
  }

  function valueRange(values) {
    var clean = values.filter(function (value) { return Number.isFinite(value); });
    if (!clean.length) return { min: 0, max: 1 };
    var min = Math.min.apply(null, clean);
    var max = Math.max.apply(null, clean);
    if (min === max) {
      min -= 1;
      max += 1;
    }
    return { min: min, max: max };
  }

  function drawLineNative(id, title, values, color) {
    var chart = nativeCanvas(id);
    if (!chart) return;
    drawTitle(chart.ctx, title);
    values = values.filter(function (value) { return Number.isFinite(value); });
    if (!values.length) {
      drawEmptyNative(id, title, '暂无候选数据');
      return;
    }
    var ctx = chart.ctx;
    var pad = { left: 34, right: 12, top: 32, bottom: 24 };
    var width = chart.width - pad.left - pad.right;
    var height = chart.height - pad.top - pad.bottom;
    var range = valueRange(values);
    ctx.strokeStyle = COLORS.grid;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(pad.left, pad.top);
    ctx.lineTo(pad.left, pad.top + height);
    ctx.lineTo(pad.left + width, pad.top + height);
    ctx.stroke();
    ctx.strokeStyle = color || COLORS.accent;
    ctx.lineWidth = 2;
    ctx.beginPath();
    values.forEach(function (value, index) {
      var x = pad.left + (values.length === 1 ? width / 2 : index / (values.length - 1) * width);
      var y = pad.top + height - ((value - range.min) / (range.max - range.min) * height);
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
    ctx.fillStyle = COLORS.muted;
    ctx.font = '11px "Segoe UI", sans-serif';
    ctx.fillText(range.max.toFixed(1), 4, pad.top + 4);
    ctx.fillText(range.min.toFixed(1), 4, pad.top + height);
  }

  function drawBarsNative(id, title, values, color, emptyText) {
    var chart = nativeCanvas(id);
    if (!chart) return;
    drawTitle(chart.ctx, title);
    values = values.filter(function (value) { return Number.isFinite(value); });
    if (!values.length) {
      drawEmptyNative(id, title, emptyText || '暂无数据');
      return;
    }
    var ctx = chart.ctx;
    var pad = { left: 28, right: 10, top: 32, bottom: 24 };
    var width = chart.width - pad.left - pad.right;
    var height = chart.height - pad.top - pad.bottom;
    var max = Math.max.apply(null, values.concat([1]));
    var barWidth = Math.max(2, width / values.length * 0.72);
    ctx.strokeStyle = COLORS.grid;
    ctx.beginPath();
    ctx.moveTo(pad.left, pad.top + height);
    ctx.lineTo(pad.left + width, pad.top + height);
    ctx.stroke();
    ctx.fillStyle = color || COLORS.accentAlpha;
    values.forEach(function (value, index) {
      var x = pad.left + index / values.length * width;
      var h = Math.max(1, value / max * height);
      ctx.fillRect(x, pad.top + height - h, barWidth, h);
    });
  }

  function drawDoughnutNative(id, title, values) {
    var chart = nativeCanvas(id);
    if (!chart) return;
    drawTitle(chart.ctx, title);
    var total = values.reduce(function (sum, value) { return sum + Math.max(0, value); }, 0);
    if (!total) {
      drawEmptyNative(id, title, '暂无门禁数据');
      return;
    }
    var ctx = chart.ctx;
    var cx = chart.width / 2;
    var cy = chart.height / 2 + 8;
    var radius = Math.min(chart.width, chart.height) * 0.28;
    var start = -Math.PI / 2;
    [COLORS.good, COLORS.bad, COLORS.muted].forEach(function (color, index) {
      var value = Math.max(0, values[index] || 0);
      var end = start + value / total * Math.PI * 2;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.arc(cx, cy, radius, start, end);
      ctx.closePath();
      ctx.fillStyle = color;
      ctx.fill();
      start = end;
    });
    ctx.fillStyle = COLORS.panel;
    ctx.beginPath();
    ctx.arc(cx, cy, radius * 0.58, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = COLORS.muted;
    ctx.font = '11px "Microsoft YaHei", "Segoe UI", sans-serif';
    ctx.fillText('通过 ' + values[0] + ' / 未通过 ' + values[1] + ' / 未查 ' + values[2], 12, chart.height - 10);
  }

  function nativeGateCounts(candidates) {
    var counts = [0, 0, 0];
    candidateRows(candidates).forEach(function (c) {
      var gate = c.gate || {};
      if (gate.passed === true || gate.submission_ready === true) counts[0]++;
      else if (gate.passed === false || gate.status === 'BRAIN_CHECK_FAILED') counts[1]++;
      else counts[2]++;
    });
    return counts;
  }

  function renderNativeCharts(summary, candidates) {
    var rows = candidateRows(candidates);
    if (!rows.length) {
      setChartFallback('当前视图暂无可绘制数据；表格和操作仍可正常使用。');
      drawEmptyNative('scoreTrendChart', '排序分趋势', '暂无候选数据');
      drawEmptyNative('sharpeDistChart', 'Sharpe 分布', '暂无 Sharpe 数据');
      drawEmptyNative('gatePieChart', '门禁状态', '暂无门禁数据');
      drawEmptyNative('turnoverChart', 'Turnover vs Sharpe', '暂无 Turnover 数据');
      return;
    }
    setChartFallback('已使用内置离线图表渲染；无需外部 CDN。');
    var sampled = sampleRows(rows, MAX_CHART_POINTS);
    drawLineNative('scoreTrendChart', '排序分趋势', sampled.map(displayScore), COLORS.accent);
    var sharpes = rows.map(function (c) {
      return safeNumber((c.scorecard || {}).sharpe || officialMetric(c, 'sharpe'), NaN);
    }).filter(function (value) { return Number.isFinite(value) && value !== 0; });
    if (sharpes.length) {
      var range = valueRange(sharpes);
      var bins = new Array(Math.min(15, Math.max(5, Math.floor(sharpes.length / 5)))).fill(0);
      sharpes.forEach(function (value) {
        var index = Math.min(bins.length - 1, Math.max(0, Math.floor((value - range.min) / (range.max - range.min) * bins.length)));
        bins[index] += 1;
      });
      drawBarsNative('sharpeDistChart', 'Sharpe 分布', bins, COLORS.accentAlpha, '暂无 Sharpe 数据');
    } else {
      drawEmptyNative('sharpeDistChart', 'Sharpe 分布', '暂无 Sharpe 数据');
    }
    drawDoughnutNative('gatePieChart', '门禁状态', nativeGateCounts(rows));
    var turnovers = sampleRows(rows.map(function (c) {
      var sc = c.scorecard || {};
      return safeNumber(sc.turnover || officialMetric(c, 'turnover'), NaN);
    }).filter(function (value) { return Number.isFinite(value) && value !== 0; }).sort(function (a, b) { return a - b; }), MAX_CHART_POINTS);
    drawBarsNative('turnoverChart', 'Turnover vs Sharpe', turnovers, COLORS.warnAlpha, '暂无 Turnover 数据');
  }

  // ---------- renderCharts (main entry) -------------------------------------

  function renderCharts(options) {
    options = options || {};
    if (!isChartJsAvailable()) {
      destroyAll();
      renderNativeCharts(AppState.get('currentResult.summary') || {}, Array.isArray(options.candidates) ? options.candidates : (AppState.get('currentResult.candidates') || []));
      return;
    }

    var summary = AppState.get('currentResult.summary') || {};
    var candidates = Array.isArray(options.candidates) ? options.candidates : (AppState.get('currentResult.candidates') || []);

    // Only render if at least one canvas exists
    var hasAnyCanvas = !!(
      document.getElementById('scoreTrendChart') ||
      document.getElementById('sharpeDistChart') ||
      document.getElementById('gatePieChart') ||
      document.getElementById('turnoverChart')
    );
    if (!hasAnyCanvas) return;
    var label = options.title ? String(options.title) : '候选';
    setChartFallback(candidateRows(candidates).length ? '' : '当前' + label + '视图暂无可绘制数据；开始生产或调整筛选后这里会展示评分、Sharpe、门禁和 Turnover 图表。');

    renderScoreTrendChart(summary, candidates);
    renderSharpeDistChart(summary, candidates);
    renderGatePieChart(summary, candidates);
    renderTurnoverChart(summary, candidates);
  }

  // ---------- Public API ----------------------------------------------------

  window.ChartView = {
    renderCharts: renderCharts,
    destroyAll: destroyAll,
  };

  // Backward-compat global alias
  window.renderCharts = renderCharts;
})();
