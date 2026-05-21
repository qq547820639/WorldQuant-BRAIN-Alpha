// brain_alpha_ops/web/js/views/detail.js
// Detail modal rendering — candidate, cloud, lifecycle, check details.
// v3: Enhanced with better formatting, performance, and accessibility.

(function () {
  'use strict';

  var $ = window.Utils.$;
  var esc = window.Utils.escapeHtml;
  var jsStringAttr = window.Utils.jsStringAttr;
  var formatScore = window.Utils.formatScore;
  var humanCheckName = window.Utils.humanCheckName;
  var renderRiskExplanation = window.Utils.renderRiskExplanation;
  var scoreSpan = window.Utils.scoreSpan;
  var statusBadge = window.Utils.statusBadge;
  var S = window.AppState;
  var previousFocus = null;

  // ── Helpers ────────────────────────────────────────────────────────────

  function fmtVal(val) {
    if (val == null) return '-';
    if (typeof val === 'boolean') return val ? '是' : '否';
    if (typeof val === 'object') return JSON.stringify(val);
    return String(val);
  }

  function formatFieldValue(value, format) {
    if (value == null) return '-';
    switch (format) {
      case 'score': return scoreSpan(value);
      case 'badge': return statusBadge(String(value), value === true || value === '是' ? 'good' : 'muted');
      case 'json': return '<pre class="detail-json">' + esc(JSON.stringify(value, null, 2)) + '</pre>';
      case 'number': { var n = Number(value); return Number.isFinite(n) ? n.toFixed(Number.isInteger(n) ? 0 : 4) : '-'; }
      default: return esc(String(value));
    }
  }

  function hasDataObject(obj) { return Boolean(obj && typeof obj === 'object' && Object.keys(obj).length); }

  function metricValue(candidate, key) {
    var metrics = (candidate || {}).official_metrics || (candidate || {}).metrics || {};
    if (!Object.prototype.hasOwnProperty.call(metrics, key)) return null;
    var n = Number(metrics[key]);
    return Number.isFinite(n) ? n : metrics[key];
  }

  function sectionBlock(title, body) {
    return '<div class="detail-section">' +
      '<div class="detail-section-title">' + esc(title) + '</div>' +
      '<div class="detail-section-body">' + body + '</div></div>';
  }

  function renderFieldTableHTML(title, fields) {
    var rows = fields.map(function (f) {
      var label = f.label || '';
      var value = formatFieldValue(f.value, f.format || 'text');
      var cls = f.className || '';
      return '<tr><td class="field-label ' + cls + '">' + esc(label) + '</td>' +
        '<td class="field-value ' + cls + '">' + value + '</td></tr>';
    }).join('');
    return '<table class="detail-table"><thead><tr><th colspan="2" style="font-weight:var(--fw-bold);font-size:var(--fs-sm)">' + esc(title) + '</th></tr></thead><tbody>' + rows + '</tbody></table>';
  }

  function showEmpty() {
    var bodyEl = $('detail'); if (bodyEl) bodyEl.innerHTML = '<div class="text-center text-muted" style="padding:var(--sp-8)">暂无详情数据。</div>';
  }

  // ── MODAL OPEN/CLOSE ──────────────────────────────────────────────────

  window.closeDetailModal = function () {
    var overlay = $('detailModal');
    if (overlay) { overlay.classList.add('hidden'); overlay.setAttribute('aria-hidden', 'true'); }
    if (previousFocus && typeof previousFocus.focus === 'function') { try { previousFocus.focus(); } catch (e) {} }
  };

  function openDetailModal() {
    var overlay = $('detailModal');
    if (overlay) {
      previousFocus = document.activeElement;
      overlay.classList.remove('hidden');
      overlay.setAttribute('aria-hidden', 'false');
      var closeBtn = $('detailCloseButton');
      if (closeBtn) setTimeout(function () { closeBtn.focus(); }, 80);
    }
  }

  // ── Candidate Detail ──────────────────────────────────────────────────

  window.viewCandidateDetail = function (candidate) {
    if (!candidate) { showEmpty(); openDetailModal(); return; }
    var titleEl = $('modalTitle'); if (titleEl) titleEl.textContent = candidate.alpha_id || '候选详情';
    var bodyEl = $('detail'); if (!bodyEl) return;

    var parts = [];

    // Basic info
    parts.push(renderFieldTableHTML('基本信息', [
      { label: 'Alpha ID', value: candidate.alpha_id },
      { label: '家族', value: candidate.family },
      { label: '假说', value: candidate.hypothesis },
      { label: '表达式', value: candidate.expression },
      { label: '数据字段', value: (candidate.data_fields || []).join(', ') },
      { label: '算子', value: (candidate.operators || []).join(', ') },
      { label: '来源标签', value: (candidate.source_tags || []).join(', ') },
      { label: '模板来源', value: candidate.template_source || '-' },
      { label: '生命周期', value: candidate.lifecycle_status || '-' },
    ]));

    // Scorecard
    var sc = candidate.scorecard || {};
    if (hasDataObject(sc) || hasDataObject(candidate.official_metrics)) {
      parts.push(renderScorecardDetail(candidate));
    }

    // Post-score attribution
    if (candidate.alpha_id) {
      parts.push(renderScoringSection(candidate));
    }

    // Gate
    var gate = candidate.gate || {};
    if (Object.keys(gate).length) {
      parts.push(renderFieldTableHTML('门禁', [
        { label: '通过', value: gate.passed, format: 'badge' },
        { label: '可提交', value: gate.submission_ready, format: 'badge' },
        { label: '详情', value: gate.details || gate.reason || '-' },
      ]));
    }

    // Validation
    var v = candidate.validation || {};
    if (Object.keys(v).length) {
      parts.push(renderFieldTableHTML('校验', [
        { label: 'IS Sharpe', value: v.is_sharpe, format: 'number' },
        { label: 'OOS Sharpe', value: v.oos_sharpe, format: 'number' },
        { label: 'R IC', value: v.r_ic, format: 'number' },
        { label: 'R IC IR', value: v.r_ic_ir, format: 'number' },
        { label: 'Max Drawdown', value: v.max_drawdown, format: 'number' },
        { label: '自相关', value: v.self_correlation, format: 'number' },
        { label: '状态', value: v.passed != null ? (v.passed ? '通过' : '未通过') : (v.status || '-') },
      ]));
    }

    // Local quality
    var lq = candidate.local_quality || {};
    if (Object.keys(lq).length) {
      parts.push(renderFieldTableHTML('本地质量', Object.keys(lq).slice(0, 12).map(function (k) {
        return { label: k, value: lq[k] };
      })));
    }

    // Official metrics
    var om = candidate.official_metrics || {};
    if (hasDataObject(om)) {
      parts.push(renderFieldTableHTML('官方指标', [
        { label: 'Sharpe', value: om.sharpe, format: 'number' },
        { label: 'Fitness', value: om.fitness, format: 'number' },
        { label: 'Turnover', value: om.turnover, format: 'number' },
        { label: 'Returns', value: om.returns, format: 'number' },
        { label: 'Drawdown', value: om.drawdown, format: 'number' },
        { label: 'Margin', value: om.margin, format: 'number' },
        { label: 'Self Correlation', value: om.self_correlation, format: 'number' },
      ]));
    }

    // Risk
    if (candidate.submission_risk || candidate.risk_check) {
      var risk = candidate.submission_risk || candidate.risk_check || {};
      parts.push(renderRiskExplanation(risk.explanation || risk));
    }

    bodyEl.innerHTML = parts.map(function (html) {
      return '<div class="detail-section">' +
        '<div class="detail-section-title" style="font-size:var(--fs-sm);font-weight:var(--fw-extrabold)">' + (html.title || '') + '</div>' +
        '<div class="detail-section-body">' + (html.body || html) + '</div>' +
        '</div>';
    }).join('');

    openDetailModal();
  };

  // ── Scorecard Detail ──────────────────────────────────────────────────

  function renderScorecardDetail(candidate) {
    var sc = candidate.scorecard || {};
    var parts = [];

    // Overall
    if (sc.total_score !== undefined || sc.local_rank_score !== undefined) {
      parts.push('<div style="font-weight:var(--fw-bold);margin-bottom:var(--sp-2)">总分：' +
        scoreSpan(sc.total_score || sc.local_rank_score || 0) + '</div>');
    }

    // Layers
    var layers = sc.layers || sc.scorecard_layers || [];
    if (layers.length) {
      layers.forEach(function (layer) {
        var layerTitle = layer.name || layer.layer || '';
        parts.push('<div class="sc-layer-title">' + esc(layerTitle) + '</div>');
        var dims = layer.dimensions || layer.dims || layer.items || [];
        dims.forEach(function (dim) {
          var name = dim.name || dim.dimension || dim.label || '';
          var score = dim.score !== undefined ? Number(dim.score) : 0;
          var weight = dim.weight !== undefined ? Number(dim.weight) : 0;
          var pctScore = Math.max(0, Math.min(100, (score + 10) / 20 * 100)); // normalize to 0-100
          var barClass = pctScore >= 70 ? 'high' : pctScore >= 40 ? 'mid' : 'low';
          parts.push('<div class="sc-dim-row">' +
            '<span style="font-size:var(--fs-2xs);color:var(--text-muted)">' + esc(name.slice(0, 2)) + '</span>' +
            '<span style="font-size:var(--fs-xs)">' + esc(name) + '</span>' +
            '<div class="sc-dim-bar-wrap"><div class="sc-dim-bar ' + barClass + '" style="width:' + pctScore + '%"></div></div>' +
            '<span class="sc-dim-val">' + scoreSpan(score) + '</span>' +
            '<span style="font-size:var(--fs-2xs);color:var(--text-muted);text-align:right">' + (weight * 100).toFixed(0) + '%</span>' +
            '</div>');
        });
      });
    }

    return sectionBlock('评分卡', parts.join(''));
  }

  // ── Scoring Section ───────────────────────────────────────────────────

  function renderScoringSection(candidate) {
    var scoring = candidate.post_score_attribution || candidate.scoring_attribution || candidate.scoring || {};
    if (!hasDataObject(scoring)) {
      // Try fetch from cache
      var cachedCheck = S.get('checkResults') || {};
      var check = cachedCheck[candidate.alpha_id];
      if (check && hasDataObject(check.scoring)) scoring = check.scoring;
    }
    if (!hasDataObject(scoring)) return '';

    var fields = [];
    if (scoring.shap_values && Array.isArray(scoring.shap_values)) {
      scoring.shap_values.slice(0, 8).forEach(function (item) {
        fields.push({ label: item.name || item.feature || '', value: (item.value || item.shap_value || 0).toFixed(4) });
      });
    }
    if (scoring.top_features && Array.isArray(scoring.top_features)) {
      scoring.top_features.slice(0, 8).forEach(function (item) {
        fields.push({ label: item, value: scoring.feature_values ? scoring.feature_values[item] : '' });
      });
    }
    if (!fields.length) {
      Object.keys(scoring).slice(0, 10).forEach(function (k) {
        var v = scoring[k];
        if (typeof v !== 'object') fields.push({ label: k, value: v });
      });
    }
    if (!fields.length) return '';

    return sectionBlock('评分归因', renderFieldTableHTML('', fields));
  }

  // ── Cloud Detail ──────────────────────────────────────────────────────

  window.viewCloudDetail = function (el) {
    var id = el && el.getAttribute('data-id');
    var cloudRows = S.get('currentResult.cloud_alphas') || [];
    var row = cloudRows.find(function (r) { return (r.alpha_id || r.id) === id; });
    if (!row) { Toast.error('未找到云端记录。'); return; }

    var titleEl = $('modalTitle'); if (titleEl) titleEl.textContent = '云端 Alpha: ' + (row.alpha_id || id);
    var bodyEl = $('detail'); if (!bodyEl) return;

    bodyEl.innerHTML = sectionBlock('云端记录', renderFieldTableHTML('', [
      { label: 'Alpha ID', value: row.alpha_id },
      { label: '状态', value: row.status, format: 'badge' },
      { label: 'Sharpe', value: row.sharpe, format: 'number' },
      { label: 'Fitness', value: row.fitness, format: 'number' },
      { label: 'Turnover', value: row.turnover, format: 'number' },
      { label: 'Self Correlation', value: row.self_correlation, format: 'number' },
      { label: 'Date', value: row.date_created || row.date || '-' },
    ]));

    openDetailModal();
  };

  // ── Lifecycle Detail ──────────────────────────────────────────────────

  window.viewLifecycleDetail = function (el) {
    var id = el && el.getAttribute('data-id');
    var lifecycle = S.get('currentResult.lifecycle_records') || [];
    var record = lifecycle.find(function (r) { return (r.alpha_id || r.id) === id; });
    if (!record) { Toast.error('未找到生命周期记录。'); return; }

    var titleEl = $('modalTitle'); if (titleEl) titleEl.textContent = '生命周期: ' + (record.alpha_id || id);
    var bodyEl = $('detail'); if (!bodyEl) return;

    bodyEl.innerHTML = sectionBlock('生命周期记录', renderFieldTableHTML('', [
      { label: 'Alpha ID', value: record.alpha_id },
      { label: '阶段', value: record.stage },
      { label: '状态', value: record.status, format: 'badge' },
      { label: '时间', value: record.timestamp },
      { label: '消息', value: record.message || '' },
      { label: '详情', value: record.details || record.note || '-' },
    ]));

    openDetailModal();
  };

  // ── Check Detail ──────────────────────────────────────────────────────

  window.viewCheckDetail = function (check) {
    if (!check) { showEmpty(); openDetailModal(); return; }
    var titleEl = $('modalTitle'); if (titleEl) titleEl.textContent = '检查结果: ' + (check.alpha_id || '');
    var bodyEl = $('detail'); if (!bodyEl) return;

    var checks = Array.isArray(check.checks) ? check.checks : [];
    var checkHtml = checks.length > 0 ? renderFieldTableHTML('检查项', checks.map(function (c) {
      return { label: humanCheckName(c.name || c), value: (c.passed !== undefined ? (c.passed ? '✓ 通过' : '✗ 未通过') : fmtVal(c)) + (c.message ? ' — ' + esc(c.message) : ''), format: c.passed ? 'badge' : 'text' };
    })) : '<div class="text-muted" style="padding:var(--sp-2)">暂无检查项详情。</div>';

    bodyEl.innerHTML = sectionBlock('检查结果', renderFieldTableHTML('', [
      { label: 'Alpha ID', value: check.alpha_id },
      { label: '通过', value: check.passed, format: 'badge' },
      { label: '检查时间', value: check.checked_at || '-' },
      { label: '是否过期', value: check.is_stale ? '是' : '否', format: 'badge' },
      { label: '错误', value: check.error || '-' },
    ])) + sectionBlock('检查详情', checkHtml);

    openDetailModal();
  };

  // ── Expose ─────────────────────────────────────────────────────────────

  window.DetailView = {
    viewCandidateDetail: window.viewCandidateDetail,
    viewCloudDetail: window.viewCloudDetail,
    viewLifecycleDetail: window.viewLifecycleDetail,
    viewCheckDetail: window.viewCheckDetail,
  };
})();
