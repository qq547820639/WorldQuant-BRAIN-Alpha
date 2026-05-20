// brain_alpha_ops/web/js/state.js
// Centralized application state — single source of truth.
// Phase 4: Extracted from scattered global variables.

(function () {
  var CHECK_STALE_MS = 24 * 60 * 60 * 1000;
  var MAX_RENDERED_ROWS = 300;

  var state = {
    // Core data
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

    // Job
    activeJobId: "",
    isRunning: false,

    // View
    activeView: "candidates",
    selected: { kind: "", id: "" },

    // Check
    checkResults: {},
    selectedSubmitIds: [],

    // Submit
    submitInFlight: false,
    lastSubmitResults: null,
    lastSubmitPayload: null,

    // Sync
    syncInFlight: false,
    syncJobId: "",
    cloudSyncCountdownUntil: 0,

    // Progress
    liveProgress: {},
    jobStatusCountdownUntil: 0,
    checkCountdownUntil: 0,
    progressEtaState: {},

    // Config (from /api/config)
    config: { autoSubmit: false, runForever: false, budget: {} },

    // User
    userProfile: { tier: "--", level: null, points: null, username: "" },

    // Batch check
    batchCheckJobId: "",
    checkStartedAt: 0,
    syncStartedAt: 0,
    backtestSnapshotUpdatedAt: 0,

    // Cache
    rowCache: {},
  };

  var listeners = [];

  var AppState = {
    get: function (key) {
      if (!key) return state;
      var keys = key.split(".");
      var obj = state;
      for (var i = 0; i < keys.length; i++) {
        if (obj == null) return undefined;
        obj = obj[keys[i]];
      }
      return obj;
    },

    set: function (key, value) {
      var keys = key.split(".");
      var last = keys.pop();
      var target = state;
      for (var i = 0; i < keys.length; i++) {
        var k = keys[i];
        if (!target[k] || typeof target[k] !== "object") target[k] = {};
        target = target[k];
      }
      target[last] = value;
      AppState.notify(key);
    },

    merge: function (key, partial) {
      var current = AppState.get(key) || {};
      AppState.set(key, Object.assign({}, current, partial));
    },

    // Row cache helpers
    rowId: function (entry) {
      var kind = entry.kind || "";
      var id = entry.id || "";
      return kind + ":" + id;
    },

    setCached: function (entry, raw) {
      state.rowCache[AppState.rowId(entry)] = Object.assign({}, entry, { raw: raw });
    },

    getCached: function (kind, id) {
      return state.rowCache[kind + ":" + id];
    },

    clearCache: function () {
      state.rowCache = {};
    },

    // View helpers
    isFreshCheck: function (check) {
      if (check && typeof check.is_stale === "boolean") return !check.is_stale;
      var checkedAt = Date.parse(check && check.checked_at || "");
      return Number.isFinite(checkedAt) && Date.now() - checkedAt <= CHECK_STALE_MS;
    },

    isFreshPassedCheck: function (check) {
      if (!AppState.isFreshCheck(check)) return false;
      return check && check.passed && (check.checks || []).some(function (row) {
        return row.name === "official_pre_submit_check" && row.passed;
      });
    },

    isFreshBlockedCheck: function (check) {
      return Boolean(check && AppState.isFreshCheck(check) && !AppState.isFreshPassedCheck(check));
    },

    isSubmittable: function (candidate) {
      return Boolean(candidate && candidate.alpha_id && AppState.isFreshPassedCheck(state.checkResults[candidate.alpha_id]));
    },

    // Notification
    onUpdate: function (fn) { listeners.push(fn); },

    notify: function (path) {
      for (var i = 0; i < listeners.length; i++) {
        try { listeners[i](path, state); } catch (e) { /* best-effort */ }
      }
    },

    CHECK_STALE_MS: CHECK_STALE_MS,
    MAX_RENDERED_ROWS: MAX_RENDERED_ROWS,
  };

  window.AppState = AppState;
})();
