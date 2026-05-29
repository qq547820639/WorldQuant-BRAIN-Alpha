// brain_alpha_ops/web/js/loading-feedback.js
// Page-level waiting feedback for startup, refreshes, and short blocking calls.
(function () {
  'use strict';

  var $ = window.Utils.$;
  var Api = window.ApiClient;
  var S = window.AppState;
  var Toast = window.Toast;

  function refreshBusyControls() {
    if (typeof window.renderBusyControls === 'function') window.renderBusyControls();
  }

  function taskTotal(total) {
    total = Number(total || S.get('pageLoadTotal') || 1);
    return Math.max(1, total);
  }

  function setTaskProgress(message, done, total, opts) {
    opts = opts || {};
    var now = Date.now();
    total = taskTotal(total);
    done = Math.min(total, Math.max(0, Number(done || 0)));
    var percent = Math.round(done / total * 100);
    var batch = {
      pageLoadInFlight: done < total,
      pageLoadStartedAt: S.get('pageLoadStartedAt') || now,
      pageLoadTotal: total,
      pageLoadDone: done,
      pageLoadMessage: message || '正在刷新页面数据。',
      pageLoadEtaSeconds: opts.eta_seconds || (done < total ? Math.max(3, (total - done) * 2) : 0),
      runtimeStatusStartedAt: S.get('runtimeStatusStartedAt') || S.get('pageLoadStartedAt') || now,
      runtimeStatusUpdatedAt: now,
      liveProgress: {
        phase: 'page_load',
        data: {
          phase: 'page_load',
          phase_label: opts.phase_label || '页面加载',
          message: message || '正在刷新页面数据。',
          scanned: done,
          total: total,
          percent: percent,
          eta_seconds: opts.eta_seconds || (done < total ? Math.max(3, (total - done) * 2) : 0),
          updated_at_ms: now,
        },
      },
    };
    S.setBatch(batch);
    if (typeof window.renderRuntimeStatus === 'function') window.renderRuntimeStatus();
    refreshBusyControls();
    return done;
  }

  function begin(total, message, opts) {
    S.setBatch({ pageLoadStartedAt: Date.now(), pageLoadDone: 0, pageLoadTotal: taskTotal(total) });
    return setTaskProgress(message || '正在加载生产工作台数据。', 0, total, opts);
  }

  function finish(message) {
    var total = taskTotal();
    setTaskProgress(message || '页面数据已刷新。', total, total, { eta_seconds: 0 });
    setTimeout(function () {
      if (!S.get('pageLoadInFlight')) {
        S.setBatch({ pageLoadStartedAt: 0, pageLoadTotal: 0, pageLoadDone: 0, pageLoadMessage: '', pageLoadEtaSeconds: 0 });
        if (typeof window.renderRuntimeStatus === 'function') window.renderRuntimeStatus();
        refreshBusyControls();
      }
    }, 400);
  }

  function standaloneProgress() {
    return !S.get('pageLoadInFlight') && !S.get('connectionTestInFlight') &&
      !S.get('syncInFlight') && !S.get('batchCheckJobId') &&
      !S.get('submitInFlight') && !S.get('isRunning');
  }

  function withTimeout(work, label, timeoutMs) {
    timeoutMs = Math.max(1000, Number(timeoutMs || 15000));
    var timerId = null;
    return Promise.race([
      Promise.resolve().then(work),
      new Promise(function (resolve) {
        timerId = setTimeout(function () {
          resolve({ ok: false, error: label + '超时，已跳过并继续加载。' });
        }, timeoutMs);
      }),
    ]).finally(function () {
      if (timerId) clearTimeout(timerId);
    });
  }

  async function track(label, action, timeoutMs) {
    var total = taskTotal();
    var done = Number(S.get('pageLoadDone') || 0);
    setTaskProgress(label + '...', done, total);
    try {
      return await withTimeout(action, label, timeoutMs);
    } catch (e) {
      if (Toast && Toast.warning) Toast.warning(label + '失败：' + (e.message || String(e)));
      return { ok: false, error: e.message || String(e) };
    } finally {
      setTaskProgress(label + '完成', Math.min(total, done + 1), total);
    }
  }

  function renderRedlineReport(data) {
    var el = $('redlineSummary');
    if (!el) return;
    var ok = Boolean(data && (data.ok || data.overall === 'PASS'));
    var passed = Number((data && data.passed) || 0);
    var total = Number((data && data.total_checks) || (data && data.total) || 0);
    var failed = Number((data && data.failed) || 0);
    el.textContent = ok ? '红线通过' + (total ? '：' + passed + '/' + total : '') : '红线需处理' + (failed ? '：' + failed + ' 项' : '');
    el.title = ok ? '技术红线验证已通过' : '技术红线验证存在阻断项，请查看诊断信息';
    el.className = 'status-pill ' + (ok ? 'badge-success' : 'badge-danger');
  }

  function markStatus(id, text, title, className) {
    var el = $(id);
    if (!el) return;
    el.textContent = text;
    if (title) el.title = title;
    if (className) el.className = 'status-pill ' + className;
  }

  async function loadProfile() {
    var standalone = standaloneProgress();
    if (standalone) begin(1, '正在刷新账户状态。');
    try {
      var data = await Api.get('/api/profile');
      if (data && data.profile) S.set('userProfile', data.profile);
      if (typeof window.renderUserProfile === 'function') window.renderUserProfile();
      return data;
    } catch (e) { return null; }
    finally { if (standalone) finish('账户状态已刷新。'); }
  }

  async function loadConfig(presetsRef) {
    var standalone = standaloneProgress();
    if (standalone) begin(1, '正在刷新运行配置。');
    try {
      var data = await Api.get('/api/config');
      if (data && data.config) {
        S.set('config', data.config);
        if (typeof window.renderStrategyPolicy === 'function') window.renderStrategyPolicy(data.config);
        if (window.FormControls && window.FormControls.applyConfig) window.FormControls.applyConfig(data.config);
        if (window.syncStrategyPluginControls) window.syncStrategyPluginControls();
      }
      return data;
    } catch (e) { return null; }
    finally { if (standalone) finish('运行配置已刷新。'); }
  }

  async function loadPresets(setter) {
    var standalone = standaloneProgress();
    if (standalone) begin(1, '正在加载市场预设。');
    try {
      var data = await Api.get('/api/presets');
      if (data && data.presets && typeof setter === 'function') setter(data.presets);
      return data;
    } catch (e) { return null; }
    finally { if (standalone) finish('市场预设已刷新。'); }
  }

  async function loadCloudSnapshot() {
    var standalone = standaloneProgress();
    if (standalone) begin(1, '正在加载云端快照。');
    try {
      if (!window.CloudSync || !window.CloudSync.loadSnapshot) return null;
      return await window.CloudSync.loadSnapshot().catch(function () { return null; });
    } finally {
      if (standalone) finish('云端快照已刷新。');
    }
  }

  async function loadCheckResults() {
    var standalone = standaloneProgress();
    if (standalone) begin(1, '正在刷新检查结果。');
    try {
      var data = await Api.get('/api/check_results');
      if (data && data.check_results) S.set('checkResults', data.check_results);
      return data;
    } catch (e) { return null; }
    finally { if (standalone) finish('检查结果已刷新。'); }
  }

  async function loadResearchMemory() {
    var standalone = standaloneProgress();
    if (standalone) begin(1, '正在加载研究记忆。');
    try {
      var data = await Api.get('/api/research_memory');
      if (data) S.set('currentResult.research_memory', data);
      return data;
    } catch (e) { return null; }
    finally { if (standalone) finish('研究记忆已刷新。'); }
  }

  async function loadRedlineReport() {
    var standalone = standaloneProgress();
    if (standalone) begin(1, '正在验证技术红线。');
    markStatus('redlineSummary', '红线验证中...', '', 'badge-warning');
    try {
      var data = await Api.get('/api/redline/report', { timeout: 120000 });
      S.set('redlineReport', data || {});
      renderRedlineReport(data || {});
      return data;
    } catch (e) {
      markStatus('redlineSummary', '红线验证不可用', e.message || String(e), 'badge-danger');
      return null;
    } finally {
      if (standalone) finish('技术红线已刷新。');
    }
  }

  async function loadCheckpointStatus() {
    var loader = window.ProductionView && window.ProductionView.loadCheckpointStatus;
    if (typeof loader !== 'function') return null;
    var standalone = standaloneProgress();
    if (standalone) begin(1, '正在刷新断点状态。');
    markStatus('checkpointSummary', '断点刷新中...', '', 'badge-info');
    try {
      var data = await loader();
      var ok = Boolean(data && data.ok);
      markStatus('checkpointSummary', ok
        ? ((data.resume_available ? '断点可续跑' : '暂无断点') + ' · 断点 ' + Number(data.checkpoint_count || 0) + ' · 历史 ' + Number(data.history_count || 0))
        : '断点状态不可用',
        ok ? '' : (data && data.error) || '',
        ok ? (data.resume_available ? 'badge-success' : 'badge-warning') : 'badge-danger');
      return data;
    } finally {
      if (standalone) finish('断点状态已刷新。');
    }
  }

  async function runStartup(options) {
    options = options || {};
    begin(9, '正在加载生产工作台数据。');
    var result = {};
    result.latest = await track('读取最近生产结果', function () {
      return Api.get('/api/latest_result', { timeout: 30000 }).catch(function () { return {}; });
    }, 30000);
    result.config = await track('读取运行配置', function () { return Api.get('/api/config', { timeout: 15000 }).catch(function () { return {}; }); }, 15000);
    result.profile = await track('刷新账户状态', function () { return Api.get('/api/profile', { timeout: 15000 }).catch(function () { return {}; }); }, 15000);
    result.presets = await track('加载市场预设', function () { return Api.get('/api/presets', { timeout: 15000 }).catch(function () { return {}; }); }, 15000);
    result.cloud = await track('加载云端快照', loadCloudSnapshot, 120000);
    result.redline = await track('验证技术红线', loadRedlineReport, 120000);
    result.checkpoint = await track('刷新断点状态', loadCheckpointStatus, 15000);
    result.checks = await track('刷新检查结果', loadCheckResults, 30000);
    result.research = await track('加载研究记忆', loadResearchMemory, 30000);
    if (typeof options.apply === 'function') options.apply(result);
    finish('生产工作台数据已加载。');
    return result;
  }

  window.LoadingFeedback = {
    begin: begin,
    finish: finish,
    loadCheckResults: loadCheckResults,
    loadCheckpointStatus: loadCheckpointStatus,
    loadCloudSnapshot: loadCloudSnapshot,
    loadConfig: loadConfig,
    loadPresets: loadPresets,
    loadProfile: loadProfile,
    loadRedlineReport: loadRedlineReport,
    loadResearchMemory: loadResearchMemory,
    runStartup: runStartup,
    setTaskProgress: setTaskProgress,
    track: track,
  };
})();
