// brain_alpha_ops/web/js/view-model.js
// Pure view-model helpers shared by app rendering flows.
// v3: Enhanced with additional identity helpers and batch operations.

(function () {
  'use strict';

  function expressionFromRow(row) {
    row = row || {};
    var raw = row.raw || {};
    var regular = raw.regular || row.regular || {};
    if (regular && regular.code) return regular.code;
    if (row.expression && typeof row.expression === 'object') return row.expression.code || JSON.stringify(row.expression);
    return row.expression || '';
  }

  function normalizedExpression(value) {
    return String(value || '').replace(/\s+/g, ' ').trim().toLowerCase();
  }

  function candidateIdentity(row) {
    row = row || {};
    var metrics = row.official_metrics || row.metrics || {};
    var id = row.official_alpha_id || metrics.official_alpha_id || row.alpha_id || row.id || row.simulation_id || '';
    if (id) return String(id);
    var expr = normalizedExpression(expressionFromRow(row));
    return expr ? 'expr:' + expr : '';
  }

  function lifecycleStatusLabel(row) {
    row = row || {};
    var status = String(row.lifecycle_status || row.status || '');
    var gate = row.gate || {};
    if (status === 'official_validation_passed') return '官方表达式验证通过';
    if (status === 'official_simulated') return '官方回测完成';
    if (status === 'submission_ready' || gate.submission_ready) return '可提交';
    if (status === 'official_standard_rejected') return '官方门禁未通过';
    if (status === 'pending_backtest') return '待回测';
    if (status === 'running_backtest' || status === 'running') return '回测中';
    if (status === 'failed' || status === 'rejected' || status === 'blocked') return '未通过';
    if (status === 'candidate') return '候选';
    return status;
  }

  function lifecycleStatusColor(row) {
    row = row || {};
    var status = String(row.lifecycle_status || row.status || '');
    var gate = row.gate || {};
    if (status === 'official_validation_passed') return 'info';
    if (status === 'official_simulated' || status === 'submission_ready' || gate.submission_ready) return 'good';
    if (status === 'official_standard_rejected' || status === 'failed' || status === 'rejected' || status === 'blocked') return 'bad';
    if (status === 'pending_backtest' || status === 'running_backtest' || status === 'running') return 'info';
    return 'muted';
  }

  function lifecycleIdentity(row) {
    row = row || {};
    return [
      row.run_id || '',
      candidateIdentity(row) || row.alpha_id || row.official_alpha_id || '',
      row.stage || '',
      row.status || '',
      row.simulation_id || '',
      row.note || '',
    ].join('|');
  }

  function uniqueBy(list, keyFn) {
    var seen = {};
    var out = [];
    (Array.isArray(list) ? list : []).forEach(function (item) {
      var key = keyFn(item);
      if (!key) key = 'row:' + out.length;
      if (seen[key]) return;
      seen[key] = true;
      out.push(item);
    });
    return out;
  }

  function uniqueCandidates(list) {
    return uniqueBy(list, candidateIdentity);
  }

  function uniqueLifecycle(list) {
    return uniqueBy(list, lifecycleIdentity);
  }

  function uniqueBacktestSlots(list) {
    var bySlot = {};
    (Array.isArray(list) ? list : []).forEach(function (slot, index) {
      var key = String(slot && slot.slot !== undefined ? slot.slot : index + 1);
      bySlot[key] = slot;
    });
    return Object.keys(bySlot)
      .sort(function (a, b) { return Number(a) - Number(b); })
      .map(function (key) { return bySlot[key]; });
  }

  function firstArrayWithItems() {
    for (var i = 0; i < arguments.length; i += 1) {
      if (Array.isArray(arguments[i]) && arguments[i].length) return arguments[i];
    }
    for (var j = 0; j < arguments.length; j += 1) {
      if (Array.isArray(arguments[j])) return arguments[j];
    }
    return null;
  }

  function chooseRuntimeArray(primary, secondary, fallback) {
    var nonEmpty = firstArrayWithItems(primary, secondary);
    if (nonEmpty) return nonEmpty;
    if (Array.isArray(primary) || Array.isArray(secondary)) return [];
    return Array.isArray(fallback) ? fallback : [];
  }

  /**
   * v3: Scorecard helpers - extract display score from a candidate.
   */
  function candidateDisplayScore(candidate) {
    if (!candidate) return 0;
    var sc = candidate.scorecard || {};
    return sc.total_score || sc.local_rank_score || 0;
  }

  function officialMetric(candidate, key) {
    var metrics = candidate.official_metrics || candidate.metrics || {};
    var value = metrics[key];
    return Number.isFinite(Number(value)) ? Number(value) : 0;
  }

  function firstDefinedValue() {
    for (var i = 0; i < arguments.length; i += 1) {
      var value = arguments[i];
      if (value !== undefined && value !== null && value !== '') return value;
    }
    return null;
  }

  function cloudMetric(row, key) {
    row = row || {};
    var metrics = row.metrics || row.official_metrics || {};
    var raw = row.raw || {};
    var rawMetrics = raw.metrics || {};
    var rawIs = raw.is || {};
    var rawRegular = raw.regular || {};
    var aliases = {
      self_correlation: ['self_correlation', 'correlation', 'selfCorrelation', 'prodCorrelation'],
      correlation: ['correlation', 'self_correlation', 'selfCorrelation', 'prodCorrelation'],
    };
    var lookupKeys = aliases[key] || [key];
    var value = firstDefinedValue(
      row[lookupKeys[0]],
      metrics[lookupKeys[0]],
      rawMetrics[lookupKeys[0]],
      rawIs[lookupKeys[0]],
      rawRegular[lookupKeys[0]],
      row[lookupKeys[1]],
      metrics[lookupKeys[1]],
      rawMetrics[lookupKeys[1]],
      rawIs[lookupKeys[1]],
      rawRegular[lookupKeys[1]],
      row[lookupKeys[2]],
      metrics[lookupKeys[2]],
      rawMetrics[lookupKeys[2]],
      rawIs[lookupKeys[2]],
      rawRegular[lookupKeys[2]]
    );
    if (value == null) return null;
    var n = Number(value);
    return Number.isFinite(n) ? n : value;
  }

  function cloudCheck(row, name) {
    row = row || {};
    var metrics = row.metrics || row.official_metrics || {};
    var raw = row.raw || {};
    var candidates = [
      metrics.brain_checks,
      row.brain_checks,
      raw.brain_checks,
      raw.checks,
      raw.is && raw.is.checks,
    ];
    var target = String(name || '').toUpperCase();
    for (var i = 0; i < candidates.length; i += 1) {
      var checks = candidates[i];
      if (!checks) continue;
      if (Array.isArray(checks)) {
        for (var j = 0; j < checks.length; j += 1) {
          var item = checks[j] || {};
          var itemName = String(item.name || item.check || '').toUpperCase();
          if (itemName === target) return item;
        }
      } else if (typeof checks === 'object') {
        var direct = checks[name] || checks[target];
        if (direct) return direct;
      }
    }
    return null;
  }

  function cloudSelfCorrelationValue(row) {
    row = row || {};
    var metrics = row.metrics || row.official_metrics || {};
    var raw = row.raw || {};
    var rawMetrics = raw.metrics || {};
    var rawIs = raw.is || {};
    var explicit = firstDefinedValue(
      row.self_correlation,
      row.selfCorrelation,
      metrics.self_correlation,
      metrics.selfCorrelation,
      rawMetrics.self_correlation,
      rawMetrics.selfCorrelation,
      rawIs.self_correlation,
      rawIs.selfCorrelation
    );
    if (explicit !== null) {
      var explicitNumber = Number(explicit);
      return Number.isFinite(explicitNumber) ? explicitNumber : explicit;
    }
    var selfCheck = cloudCheck(row, 'SELF_CORRELATION');
    if (selfCheck && selfCheck.value !== undefined && selfCheck.value !== null && selfCheck.value !== '') {
      var checkNumber = Number(selfCheck.value);
      return Number.isFinite(checkNumber) ? checkNumber : selfCheck.value;
    }
    if (selfCheck && selfCheck.result) return String(selfCheck.result);
    return cloudMetric(row, 'self_correlation');
  }

  function cloudSelfCorrelationDisplay(row) {
    var value = cloudSelfCorrelationValue(row);
    if (value == null || value === '') return '-';
    var n = Number(value);
    return Number.isFinite(n) ? n.toFixed(4) : String(value);
  }

  function firstFiniteNumber() {
    for (var i = 0; i < arguments.length; i += 1) {
      var n = Number(arguments[i]);
      if (Number.isFinite(n)) return n;
    }
    return null;
  }

  function firstPositiveFiniteNumber() {
    for (var i = 0; i < arguments.length; i += 1) {
      var n = Number(arguments[i]);
      if (Number.isFinite(n) && n > 0) return n;
    }
    return null;
  }

  window.ViewModel = {
    candidateIdentity: candidateIdentity,
    candidateDisplayScore: candidateDisplayScore,
    cloudCheck: cloudCheck,
    cloudMetric: cloudMetric,
    cloudSelfCorrelationDisplay: cloudSelfCorrelationDisplay,
    cloudSelfCorrelationValue: cloudSelfCorrelationValue,
    chooseRuntimeArray: chooseRuntimeArray,
    firstDefinedValue: firstDefinedValue,
    expressionFromRow: expressionFromRow,
    firstArrayWithItems: firstArrayWithItems,
    firstFiniteNumber: firstFiniteNumber,
    firstPositiveFiniteNumber: firstPositiveFiniteNumber,
    lifecycleIdentity: lifecycleIdentity,
    lifecycleStatusColor: lifecycleStatusColor,
    lifecycleStatusLabel: lifecycleStatusLabel,
    normalizedExpression: normalizedExpression,
    officialMetric: officialMetric,
    uniqueBacktestSlots: uniqueBacktestSlots,
    uniqueBy: uniqueBy,
    uniqueCandidates: uniqueCandidates,
    uniqueLifecycle: uniqueLifecycle,
  };
})();
