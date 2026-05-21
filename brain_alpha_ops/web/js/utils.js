// brain_alpha_ops/web/js/utils.js
// Pure utility functions — no DOM, no state.
// v3: Enhanced with better formatting, badge helpers, and sidebar management.

(function () {
  'use strict';
  var Utils = {};

  // ── DOM shortcut ──────────────────────────────────────────────────────
  Utils.$ = function (id) { return document.getElementById(id); };

  // ── HTML escape ───────────────────────────────────────────────────────
  Utils.escapeHtml = function (s) {
    return String(s).replace(/[&<>"']/g, function (ch) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch];
    });
  };

  Utils.escapeAttr = function (s) {
    return Utils.escapeHtml(s).replace(/\\/g, '\\\\').replace(/\n/g, '\\n');
  };

  Utils.jsStringAttr = function (s) {
    return Utils.escapeHtml(JSON.stringify(String(s ?? '')));
  };

  Utils.escapeId = function (s) {
    return String(s).replace(/[^a-zA-Z0-9_-]/g, '_');
  };

  // ── Phase name ────────────────────────────────────────────────────────
  Utils.phaseName = function (phaseOrProgress) {
    if (typeof phaseOrProgress === 'object' && phaseOrProgress && phaseOrProgress.phase_label) {
      return phaseOrProgress.phase_label;
    }
    var phase = typeof phaseOrProgress === 'string' ? phaseOrProgress : String(phaseOrProgress || '');
    var map = {
      queued: '排队', auth: '认证', scan: '扫描', merge: '合并',
      startup: '启动', cloud_sync: '云端数据同步', context: '加载上下文',
      production_loop: '循环生产', local_scoring: '本地评分排序',
      candidate_pool: '候选池维护', official_validation: '回测前预检',
      simulation_submit: '提交回测', simulation_wait: '等待回测结果',
      official_deferred: '官方调用延后', official_simulation: '官方回测等待',
      strategy_switch: '自动切换策略', completed: '完成', stopped: '已停止',
      failed: '失败', stopping: '正在停止', checking: '批量检查', submitting: '提交',
    };
    return map[phase] || phase;
  };

  // ── Check name ────────────────────────────────────────────────────────
  Utils.humanCheckName = function (nameOrCheck) {
    if (typeof nameOrCheck === 'object' && nameOrCheck && nameOrCheck.label_cn) {
      return nameOrCheck.label_cn;
    }
    var name = typeof nameOrCheck === 'string' ? nameOrCheck : String(nameOrCheck || '');
    var map = {
      production_gate: '未达提交门禁',
      official_alpha_id: '缺少官方 ID',
      not_failed_locally: '本地状态异常',
      cloud_sync_available: '云端数据未就绪',
      not_submitted_before: '本地已有提交记录',
      cloud_status_not_already_submitted: '云端已提交',
      cloud_self_correlation: '云端相似度过高',
      official_pre_submit_check: '官方预提交检查未过',
      LOW_SHARPE: '低 Sharpe', LOW_FITNESS: '低 Fitness',
      LOW_TURNOVER: '低换手率', HIGH_TURNOVER: '高换手率',
      CONCENTRATED_WEIGHT: '权重集中', SELF_CORRELATION: '自相关过高',
      LOW_SUB_UNIVERSE_SHARPE: '子宇宙低 Sharpe',
    };
    return map[name] || name;
  };

  // ── Value formatting ──────────────────────────────────────────────────
  Utils.formatScore = function (v) { return v != null ? Number(v).toFixed(1) : '-'; };
  Utils.formatPct = function (v) { return v != null ? (Number(v) * 100).toFixed(1) + '%' : '-'; };
  Utils.num = function (value, digits) {
    if (value === undefined || value === null || value === '') return '-';
    var n = Number(value);
    if (!Number.isFinite(n)) return String(value);
    return n.toFixed(digits === undefined ? 1 : digits);
  };

  Utils.payloadTruthy = function (value) {
    if (typeof value === 'boolean') return value;
    if (typeof value === 'string') return value.trim().toLowerCase() === 'true' || value === '1' || value === 'yes' || value === 'on';
    return Boolean(value);
  };

  // ── Badge class helper ────────────────────────────────────────────────
  Utils.badgeClass = function (color) {
    var map = { good: 'badge-success', warn: 'badge-warning', bad: 'badge-danger', info: 'badge-info', accent: 'badge-accent', muted: 'badge-default' };
    return 'badge ' + (map[color] || 'badge-default');
  };

  // ── Score span (color-coded) ──────────────────────────────────────────
  Utils.scoreSpan = function (val) {
    var n = Number(val);
    if (!Number.isFinite(n)) return Utils.escapeHtml(String(val ?? '-'));
    var color = n >= 70 ? 'var(--success)' : n >= 50 ? 'var(--warning)' : 'var(--danger)';
    return '<span style="font-weight:700;color:' + color + '">' + n.toFixed(1) + '</span>';
  };

  // ── Status badge renderer ─────────────────────────────────────────────
  Utils.statusBadge = function (status, color) {
    var map = { good: 'success', warn: 'warning', bad: 'danger', info: 'info', muted: 'default' };
    var cls = map[color] || 'default';
    return '<span class="badge badge-' + cls + '">' + Utils.escapeHtml(String(status || '')) + '</span>';
  };

  // ── Risk explanation renderer ─────────────────────────────────────────
  Utils.renderRiskExplanation = function (explanation) {
    if (!explanation || typeof explanation !== 'object') return '';
    var visual = explanation.visual || {};
    var evidence = explanation.evidence || {};
    var value = Number(visual.value !== undefined ? visual.value : evidence.max_similarity);
    if (!Number.isFinite(value)) value = 0;
    var threshold = Number(visual.threshold || evidence.threshold || 0.9);
    if (!Number.isFinite(threshold) || threshold <= 0) threshold = 0.9;
    var severity = String(explanation.severity || explanation.level || 'info').replace(/[^a-z]/g, '') || 'info';
    var reasons = (Array.isArray(explanation.reasons) ? explanation.reasons : []).slice(0, 5).map(function (item) {
      return '<li>' + Utils.escapeHtml(item) + '</li>';
    }).join('');
    var actions = (Array.isArray(explanation.recommended_actions) ? explanation.recommended_actions : []).slice(0, 5).map(function (item) {
      return '<li>' + Utils.escapeHtml(item) + '</li>';
    }).join('');
    var pctVal = Math.max(0, Math.min(100, Number(value || 0) * 100));
    var pctThreshold = Math.max(0, Math.min(100, Number(threshold) * 100));
    var severityClass = severity === 'blocking' ? 'blocking' : severity === 'warning' ? 'warning' : '';
    return '<div class="risk-card' + (severityClass ? ' ' + severityClass : '') + '">' +
      '<div class="risk-card-head">' +
        '<div><div class="risk-title">' + Utils.escapeHtml(explanation.title || '风险提示') + '</div>' +
        '<div class="risk-summary">' + Utils.escapeHtml(explanation.summary || '') + '</div></div>' +
        '<div class="risk-score">' + pctVal.toFixed(1) + '%</div>' +
      '</div>' +
      '<div class="risk-meter" aria-label="risk meter"><div class="risk-meter-fill" style="width:' + pctVal + '%"></div><span class="risk-threshold" style="left:' + pctThreshold + '%"></span></div>' +
      (reasons ? '<div class="risk-list-title">原因</div><ul class="risk-list">' + reasons + '</ul>' : '') +
      (actions ? '<div class="risk-list-title">处理路径</div><ul class="risk-list">' + actions + '</ul>' : '') +
      Utils.renderStateNavigation(explanation.navigation || explanation.state_navigation) +
      '</div>';
  };

  Utils.renderStateNavigation = function (navigation) {
    if (!navigation || typeof navigation !== 'object') return '';
    var steps = Array.isArray(navigation.steps) ? navigation.steps : [];
    var stepHtml = steps.map(function (step) {
      var cls = String(step.status || 'pending').replace(/[^a-zA-Z0-9_-]/g, '') || 'pending';
      return '<span class="lc-step ' + cls + '">' + Utils.escapeHtml(step.label || step.id || '-') + '</span>';
    }).join('');
    return '<div style="margin-top:var(--sp-2);padding:var(--sp-2);background:var(--bg-muted);border-radius:var(--r-sm)">' +
      '<div style="font-weight:var(--fw-bold);margin-bottom:4px">' + Utils.escapeHtml(navigation.title || '解决路径') + '</div>' +
      (navigation.summary ? '<div style="font-size:var(--fs-xs);color:var(--text-secondary)">' + Utils.escapeHtml(navigation.summary) + '</div>' : '') +
      (stepHtml ? '<div class="lc-timeline" style="margin-top:4px">' + stepHtml + '</div>' : '') +
      (navigation.primary_action ? '<div style="font-size:var(--fs-xs);color:var(--accent);font-weight:var(--fw-bold);margin-top:4px">' + Utils.escapeHtml(navigation.primary_action) + '</div>' : '') +
      '</div>';
  };

  // ── Sidebar section toggle ────────────────────────────────────────────
  Utils.toggleSidebarSection = function (sectionId) {
    var section = document.getElementById(sectionId);
    if (section) section.classList.toggle('is-collapsed');
  };

  Utils.updateSidebarToggleAll = function () {
    var sections = document.querySelectorAll('.sbar-section');
    var allCollapsed = true;
    sections.forEach(function (s) { if (!s.classList.contains('is-collapsed')) allCollapsed = false; });
    var btn = document.getElementById('sidebarToggleAllBtn');
    if (btn) btn.textContent = allCollapsed ? '全部展开' : '全部折叠';
  };

  // ── Set form value ────────────────────────────────────────────────────
  Utils.setVal = function (id, value) {
    var el = Utils.$(id);
    if (el && value !== undefined && value !== null) el.value = value;
  };

  window.toggleSidebarSection = function (sectionId) {
    Utils.toggleSidebarSection(sectionId);
    Utils.updateSidebarToggleAll();
  };

  window.toggleAllSidebarSections = function () {
    var sections = document.querySelectorAll('.sbar-section');
    var allCollapsed = true;
    sections.forEach(function (s) { if (!s.classList.contains('is-collapsed')) allCollapsed = false; });
    sections.forEach(function (s) { s.classList.toggle('is-collapsed', !allCollapsed); });
    Utils.updateSidebarToggleAll();
  };

  window.Utils = Utils;
})();
