// brain_alpha_ops/web/js/view-model.js
// Pure view-model helpers shared by app rendering flows.

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

  window.ViewModel = {
    candidateIdentity: candidateIdentity,
    chooseRuntimeArray: chooseRuntimeArray,
    expressionFromRow: expressionFromRow,
    firstArrayWithItems: firstArrayWithItems,
    lifecycleIdentity: lifecycleIdentity,
    normalizedExpression: normalizedExpression,
    uniqueBacktestSlots: uniqueBacktestSlots,
    uniqueBy: uniqueBy,
    uniqueCandidates: uniqueCandidates,
    uniqueLifecycle: uniqueLifecycle,
  };
})();
