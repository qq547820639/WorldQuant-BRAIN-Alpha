// brain_alpha_ops/web/js/view-renderers.js
// Row source, filter, and column helpers for the main result view.

(function () {
  'use strict';

  var Utils = window.Utils;
  var VM = window.ViewModel;

  var esc = Utils.escapeHtml;
  var escapeAttr = Utils.escapeAttr;
  var num = Utils.num;
  var scoreSpan = Utils.scoreSpan;
  var statusBadge = Utils.statusBadge;
  var candidateIdentity = VM.candidateIdentity;
  var cloudMetric = VM.cloudMetric || function (row, key) { return (row || {})[key]; };
  var cloudSelfCorrelationDisplay = VM.cloudSelfCorrelationDisplay || function (row) { return num(cloudMetric(row || {}, 'self_correlation'), 4); };
  var expressionFromRow = VM.expressionFromRow;
  var uniqueBy = VM.uniqueBy;
  var lifecycleStatusLabel = VM.lifecycleStatusLabel || function (row) {
    row = row || {};
    return String(row.lifecycle_status || row.status || '');
  };
  var lifecycleStatusColor = VM.lifecycleStatusColor || function () { return 'muted'; };

  function getRowsForView(view, data) {
    data = data || {};
    var candidates = data.candidates || [];
    var cloud = data.cloud || [];
    var lifecycle = data.lifecycle || [];
    var checks = data.checks || {};

    switch (view) {
      case 'candidates': return buildCandidateRows(candidates, 'candidate');
      case 'pending_backtest': return buildCandidateRows(candidates.filter(function (c) { return (c.lifecycle_status || c.status || '') === 'pending_backtest'; }), 'pending_backtest');
      case 'running_backtest': return buildCandidateRows(candidates.filter(function (c) { var s = c.lifecycle_status || c.status || ''; return s === 'running_backtest' || s === 'running'; }), 'running_backtest');
      case 'backtest_rework': return buildCandidateRows(candidates.filter(function (c) { var s = c.lifecycle_status || c.status || ''; return s === 'backtest_rework' || s === 'failed_backtest' || s === 'rejected'; }), 'backtest_rework');
      case 'passed': return buildCandidateRows(candidates.filter(function (c) { return c.lifecycle_status === 'submission_ready' || ((c.gate || {}).submission_ready); }), 'passed');
      case 'submittable': return buildSubmittableRows(candidates, checks, data);
      case 'submitted': return buildSubmittedRows(candidates, lifecycle);
      case 'failed': return buildCandidateRows(candidates.filter(function (c) { var s = c.lifecycle_status || c.status || ''; return s === 'failed' || s === 'rejected' || s === 'blocked'; }), 'failed');
      case 'cloud': return buildCloudRows(cloud);
      case 'lifecycle': return buildLifecycleRows(lifecycle);
      case 'research_memory': return buildResearchRows(data.researchMemory, 'research_memory');
      case 'research_observability': return buildResearchRows(data.researchObservability, 'research_observability');
      case 'research_knowledge': return buildResearchRows(data.researchKnowledge, 'research_knowledge');
      case 'prompt_runs': return buildPromptRunRows(data.promptRuns);
      case 'sqlite_indexes': return buildSqliteRows(data.sqliteIndexes);
      case 'robustness': return buildRobustnessRows(data.robustnessSnapshot);
      default: return [];
    }
  }

  function buildCandidateRows(list, kind) {
    return (list || []).map(function (c, i) { return { kind: kind, id: c.alpha_id || c.id || ('row' + i), raw: c, _rowIndex: i, _candidate: c }; });
  }

  function buildSubmittableRows(candidates, checks, data) {
    data = data || {};
    var isFreshPassedCheck = data.isFreshPassedCheck || function () { return false; };
    var lastSubmitResults = data.lastSubmitResults || [];
    return (candidates || []).filter(function (c) {
      var aid = c.alpha_id || candidateIdentity(c);
      return isFreshPassedCheck(checks[aid]) && !lastSubmitResults.some(function (r) { return r.alpha_id === aid && r.submitted; });
    }).map(function (c, i) {
      var aid = c.alpha_id || candidateIdentity(c);
      return { kind: 'submittable', id: aid, raw: c, _rowIndex: i, _candidate: c, _check: checks[aid] };
    });
  }

  function buildSubmittedRows(candidates, lifecycle) {
    var submitted = (lifecycle || []).filter(function (r) { return r.stage === 'submitted' || r.status === 'submitted'; });
    var localSubmitted = (candidates || []).filter(function (c) { return c.lifecycle_status === 'submitted'; });
    return uniqueBy(submitted.concat(localSubmitted.map(function (c, i) { return { kind: 'submitted', id: c.alpha_id || c.official_alpha_id || ('sub' + i), raw: c }; })), function (r) { return r.id; });
  }

  function buildCloudRows(cloud) {
    return (cloud || []).map(function (d, i) { return { kind: 'cloud', id: d.alpha_id || d.id || ('cloud' + i), raw: d, _rowIndex: i }; });
  }

  function buildLifecycleRows(lifecycle) {
    return (lifecycle || []).map(function (r, i) { return { kind: 'lifecycle', id: r.alpha_id || r.id || ('life' + i), raw: r, _rowIndex: i }; });
  }

  function buildResearchRows(data, kind) {
    var items = data && Array.isArray(data.items) ? data.items : Array.isArray(data) ? data : [];
    return items.map(function (item, i) { return { kind: kind, id: item.id || ('res' + i), raw: item, _rowIndex: i }; });
  }

  function buildPromptRunRows(data) {
    var items = data && Array.isArray(data.runs) ? data.runs : Array.isArray(data) ? data : [];
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
    var items = snapshot && Array.isArray(snapshot.candidates) ? snapshot.candidates : Array.isArray(snapshot) ? snapshot : [];
    return items.map(function (item, i) { return { kind: 'robustness', id: item.alpha_id || ('rob' + i), raw: item, _rowIndex: i }; });
  }

  function applySearchFilter(rows, query) {
    query = String(query || '');
    if (!query || !rows) return rows;
    var q = query.toLowerCase();
    for (var i = rows.length - 1; i >= 0; i -= 1) {
      var row = rows[i], raw = row.raw || {};
      var text = [row.id, raw.alpha_id, raw.official_alpha_id, raw.family, raw.hypothesis, raw.expression, expressionFromRow(raw), raw.status, raw.simulation_id, (raw.scorecard || {}).decision_band, raw.lifecycle_status || '', raw.stage || ''].join(' ').toLowerCase();
      if (text.indexOf(q) === -1) rows.splice(i, 1);
    }
    return rows;
  }

  function getColumnsForView(view, options) {
    options = options || {};
    var actionButton = options.actionButton;
    var activeView = options.activeView || function () { return view; };
    var submitInFlight = options.submitInFlight || function () { return false; };
    var isSelectedSubmitId = options.isSelectedSubmitId || function () { return false; };

    switch (view) {
      case 'cloud': return [
        { accessor: '_rowIndex', render: function (v, r, i) { return String(i + 1); } },
        { accessor: 'id', render: function (v, r) { return esc(String((r.raw || {}).alpha_id || r.id || '-')); } },
        { accessor: 'status', render: function (v, r) { var s = (r.raw || {}).status || ''; return statusBadge(s, s === 'APPROVED' || s === 'PRODUCTION' ? 'good' : s === 'REJECTED' ? 'bad' : 'info'); }, htmlType: 'badge' },
        { accessor: 'sharpe', render: function (v, r) { return scoreSpan(cloudMetric(r.raw || {}, 'sharpe')); }, htmlType: 'score' },
        { accessor: 'fitness', render: function (v, r) { return scoreSpan(cloudMetric(r.raw || {}, 'fitness')); }, htmlType: 'score' },
        { accessor: 'turnover', render: function (v, r) { return num(cloudMetric(r.raw || {}, 'turnover'), 4); } },
        { accessor: 'self_correlation', render: function (v, r) { return cloudSelfCorrelationDisplay(r.raw || {}); } },
        { accessor: 'actions', render: function (v, r) { return actionButton('open-row', '详情', r, 'btn btn-secondary btn-sm'); }, htmlType: 'buttonGroup' },
      ];
      case 'lifecycle': return [
        { accessor: '_rowIndex', render: function (v, r, i) { return String(i + 1); } },
        { accessor: 'id', render: function (v, r) { return esc(String((r.raw || {}).alpha_id || r.id || '-')); } },
        { accessor: 'stage', render: function (v, r) { return esc(String((r.raw || {}).stage || '-')); } },
        { accessor: 'status', render: function (v, r) { var s = (r.raw || {}).status || ''; return statusBadge(s, s === 'completed' || s === 'passed' ? 'good' : s === 'failed' ? 'bad' : 'info'); }, htmlType: 'badge' },
        { accessor: 'timestamp', render: function (v, r) { return esc(String((r.raw || {}).timestamp || '-')); } },
        { accessor: 'message', render: function (v, r) { return esc(String((r.raw || {}).message || '')); } },
        { accessor: 'actions', render: function (v, r) { return actionButton('open-row', '详情', r, 'btn btn-secondary btn-sm'); }, htmlType: 'buttonGroup' },
      ];
      default: return [
        { accessor: '_rowIndex', render: function (v, r, i) { return String(i + 1); } },
        { accessor: 'id', render: function (v, r) {
          var raw = r.raw || {};
          var id = raw.alpha_id || r.id || '';
          var family = raw.family || '';
          return '<div><div class="candidate-id-main">' + esc(id || '-') + '</div>' + (family ? '<div class="candidate-id-family">' + esc(family) + '</div>' : '') + '</div>';
        }, htmlType: 'candidateId' },
        { accessor: 'family', render: function (v, r) { return esc(String((r.raw || {}).family || '-')); } },
        { accessor: 'score', render: function (v, r) { var sc = (r.raw || {}).scorecard || {}; return scoreSpan(sc.total_score || sc.local_rank_score || 0); }, htmlType: 'score' },
        { accessor: 'status', render: function (v, r) {
          var raw = r.raw || {};
          var status = lifecycleStatusLabel(raw);
          return statusBadge(status || '-', lifecycleStatusColor(raw));
        }, htmlType: 'badge' },
        { accessor: 'official_id', render: function (v, r) { return esc(String((r.raw || {}).official_alpha_id || '-')); } },
        { accessor: 'risk', render: function (v, r) {
          var raw = r.raw || {};
          var risk = raw.submission_risk || raw.risk || '';
          return risk ? '<span class="risk-text">' + esc(String(risk).slice(0, 60)) + '</span>' : '';
        }, htmlType: 'riskText' },
        { accessor: 'actions', render: function (v, r) {
          var raw = r.raw || {}, aid = raw.alpha_id || r.id || '';
          var viewName = activeView();
          var buttons = [actionButton('open-row', '详情', r, 'btn btn-secondary btn-sm')];
          if (viewName === 'candidates') buttons.push(actionButton('score-candidate', '评分', r, 'btn btn-primary btn-sm'));
          if (viewName === 'submittable' && !submitInFlight()) buttons.push(actionButton('submit-single', '提交', r, 'btn btn-primary btn-sm'));
          if (viewName === 'passed') buttons.push(actionButton('toggle-select', isSelectedSubmitId(aid) ? '已选' : '选择', r, 'btn btn-secondary btn-sm', { pressed: isSelectedSubmitId(aid) }));
          return buttons.join(' ');
        }, htmlType: 'buttonGroup' },
      ];
    }
  }

  function getMobileColumns() {
    return [
      { label: '排序分', accessor: 'score', render: function (v, r) { return scoreSpan(((r.raw || {}).scorecard || {}).total_score || 0); }, htmlType: 'score' },
      { label: '状态', accessor: 'status', render: function (v, r) { return statusBadge(lifecycleStatusLabel(r.raw || {}), lifecycleStatusColor(r.raw || {})); }, htmlType: 'badge' },
      { label: '官方 ID', accessor: 'official_id', render: function (v, r) { return esc(String((r.raw || {}).official_alpha_id || '-')); } },
    ];
  }

  function renderMobileActions(row, view, options) {
    options = options || {};
    var actionButton = options.actionButton;
    var submitInFlight = options.submitInFlight || function () { return false; };
    var isSelectedSubmitId = options.isSelectedSubmitId || function () { return false; };
    var raw = row.raw || {}, aid = raw.alpha_id || row.id || '';
    var buttons = [actionButton('open-row', '详情', row, 'btn btn-secondary btn-sm')];
    if (view === 'candidates') buttons.push(actionButton('score-candidate', '评分', row, 'btn btn-primary btn-sm'));
    if (view === 'submittable' && !submitInFlight()) buttons.push(actionButton('submit-single', '提交', row, 'btn btn-primary btn-sm'));
    if (view === 'passed') buttons.push(actionButton('toggle-select', isSelectedSubmitId(aid) ? '已选' : '选择', row, 'btn btn-secondary btn-sm', { pressed: isSelectedSubmitId(aid) }));
    return buttons.join(' ');
  }

  function hasDataObject(obj) {
    return Boolean(obj && typeof obj === 'object' && Object.keys(obj).length);
  }

  window.ViewRenderers = {
    applySearchFilter: applySearchFilter,
    getColumnsForView: getColumnsForView,
    getMobileColumns: getMobileColumns,
    getRowsForView: getRowsForView,
    renderMobileActions: renderMobileActions,
  };
})();
