// brain_alpha_ops/web/js/state.js
// Centralized application state — single source of truth.
// v3: Enhanced with computed helpers, better cache management, batch updates.

(function () {
  'use strict';
  var CHECK_STALE_MS = 24 * 60 * 60 * 1000;
  var MAX_RENDERED_ROWS = 300;

  var state = {
    currentResult: {
      summary: {},
      candidates: [],
      passed_candidates: [],
      pending_backtest_candidates: [],
      cloud_alphas: [],
      research_memory: {},
      research_knowledge: {},
      research_observability: {},
      prompt_runs: {},
      sqlite_indexes: {},
      sqlite_lookup: {},
      robustness_snapshot: {},
      assistant_context: {},
      assistant_guidance: {},
      lifecycle_records: [],
      backtests: [],
    },
    activeJobId: '',
    isRunning: false,
    activeView: 'candidates',
    selected: { kind: '', id: '' },
    checkResults: {},
    selectedSubmitIds: [],
    submitInFlight: false,
    lastSubmitResults: null,
    lastSubmitPayload: null,
    syncInFlight: false,
    syncJobId: '',
    cloudSyncCountdownUntil: 0,
    liveProgress: {},
    jobStatusCountdownUntil: 0,
    checkCountdownUntil: 0,
    progressEtaState: {},
    config: { autoSubmit: false, runForever: false, budget: {} },
    userProfile: { tier: '--', level: null, points: null, username: '' },
    redlineReport: {},
    checkpointStatus: {},
    batchCheckJobId: '',
    checkStartedAt: 0,
    syncStartedAt: 0,
    backtestSnapshotUpdatedAt: 0,
    rowCache: {},
    viewCounts: {},  // v3: cached per-view counts for tab badges
  };

  var listeners = [];

  function resolvePath(key) {
    if (!key) return [state];
    var keys = key.split('.');
    var obj = state;
    for (var i = 0; i < keys.length; i++) {
      if (obj == null) return [undefined];
      obj = obj[keys[i]];
    }
    return [obj];
  }

  var AppState = {
    get: function (key) {
      if (!key) return state;
      var keys = key.split('.');
      var obj = state;
      for (var i = 0; i < keys.length; i++) {
        if (obj == null) return undefined;
        obj = obj[keys[i]];
      }
      return obj;
    },

    set: function (key, value) {
      var keys = key.split('.');
      var last = keys.pop();
      var target = state;
      for (var i = 0; i < keys.length; i++) {
        var k = keys[i];
        if (!target[k] || typeof target[k] !== 'object') target[k] = {};
        target = target[k];
      }
      target[last] = value;
      AppState.notify(key);
    },

    /**
     * v3: Batch set multiple keys and fire a single notification.
     * Usage: AppState.setBatch({ 'isRunning': true, 'activeJobId': 'x' })
     */
    setBatch: function (batch) {
      if (!batch || typeof batch !== 'object') return;
      var paths = [];
      Object.keys(batch).forEach(function (key) {
        var keys = key.split('.');
        var last = keys.pop();
        var target = state;
        for (var i = 0; i < keys.length; i++) {
          var k = keys[i];
          if (!target[k] || typeof target[k] !== 'object') target[k] = {};
          target = target[k];
        }
        target[last] = batch[key];
        paths.push(key);
      });
      // Notify with first path (or combined)
      AppState.notify(paths.length === 1 ? paths[0] : 'batch');
    },

    merge: function (key, partial) {
      var current = AppState.get(key) || {};
      AppState.set(key, Object.assign({}, current, partial));
    },

    // ── Row Cache ─────────────────────────────────────────────────────
    rowId: function (entry) {
      return (entry.kind || '') + ':' + (entry.id || '');
    },

    setCached: function (entry, raw) {
      state.rowCache[AppState.rowId(entry)] = Object.assign({}, entry, { raw: raw });
    },

    getCached: function (kind, id) {
      return state.rowCache[kind + ':' + id] || null;
    },

    clearCache: function () {
      state.rowCache = {};
    },

    // ── Check freshness ───────────────────────────────────────────────
    isFreshCheck: function (check) {
      if (check && typeof check.is_stale === 'boolean') return !check.is_stale;
      var checkedAt = Date.parse((check && check.checked_at) || '');
      return Number.isFinite(checkedAt) && (Date.now() - checkedAt) <= CHECK_STALE_MS;
    },

    isFreshPassedCheck: function (check) {
      if (!AppState.isFreshCheck(check)) return false;
      return check && check.passed && (check.checks || []).some(function (row) {
        return row.name === 'official_pre_submit_check' && row.passed;
      });
    },

    isFreshBlockedCheck: function (check) {
      return Boolean(check && AppState.isFreshCheck(check) && !AppState.isFreshPassedCheck(check));
    },

    isSubmittable: function (candidate) {
      return Boolean(candidate && candidate.alpha_id && AppState.isFreshPassedCheck(state.checkResults[candidate.alpha_id]));
    },

    // ── Counts ────────────────────────────────────────────────────────
    candidateCount: function () {
      return (state.currentResult.candidates || []).length;
    },

    passedCount: function () {
      return (state.currentResult.candidates || []).filter(function (c) {
        return c.lifecycle_status === 'submission_ready' || ((c.gate || {}).submission_ready);
      }).length;
    },

    submittableCount: function () {
      var checks = state.checkResults || {};
      return (state.currentResult.candidates || []).filter(function (c) {
        return AppState.isFreshPassedCheck(checks[c.alpha_id]);
      }).length;
    },

    /**
     * v3: Get count for a specific view (for tab badges).
     */
    viewCount: function (view) {
      var checks = state.checkResults || {};
      var candidates = state.currentResult.candidates || [];
      var lifecycle = state.currentResult.lifecycle_records || [];
      var cloud = state.currentResult.cloud_alphas || [];
      switch (view) {
        case 'candidates': return candidates.length;
        case 'pending_backtest': return candidates.filter(function (c) { return (c.lifecycle_status || c.status || '') === 'pending_backtest'; }).length;
        case 'running_backtest': return candidates.filter(function (c) { var s = c.lifecycle_status || c.status || ''; return s === 'running_backtest' || s === 'running'; }).length;
        case 'backtest_rework': return candidates.filter(function (c) { var s = c.lifecycle_status || c.status || ''; return s === 'backtest_rework' || s === 'failed_backtest' || s === 'rejected'; }).length;
        case 'passed': return candidates.filter(function (c) { return c.lifecycle_status === 'submission_ready' || ((c.gate || {}).submission_ready); }).length;
        case 'submittable': return candidates.filter(function (c) { return AppState.isFreshPassedCheck(checks[c.alpha_id]); }).length;
        case 'submitted': return lifecycle.filter(function (r) { return r.stage === 'submitted' || r.status === 'submitted'; }).length;
        case 'failed': return candidates.filter(function (c) { var s = c.lifecycle_status || c.status || ''; return s === 'failed' || s === 'rejected' || s === 'blocked'; }).length;
        case 'cloud': return cloud.length;
        case 'lifecycle': return lifecycle.length;
        default: return 0;
      }
    },

    // ── Events ────────────────────────────────────────────────────────
    onUpdate: function (fn) { listeners.push(fn); },

    offUpdate: function (fn) {
      listeners = listeners.filter(function (l) { return l !== fn; });
    },

    notify: function (path) {
      listeners.forEach(function (fn) {
        try { fn(path, state); } catch (e) { /* silent */ }
      });
    },

    CHECK_STALE_MS: CHECK_STALE_MS,
    MAX_RENDERED_ROWS: MAX_RENDERED_ROWS,
  };

  window.AppState = AppState;
})();
