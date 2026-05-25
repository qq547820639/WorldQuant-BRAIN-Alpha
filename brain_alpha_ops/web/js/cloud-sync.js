// brain_alpha_ops/web/js/cloud-sync.js
// Production cloud snapshot loading and online sync job follow-up.

(function () {
  'use strict';

  var $ = window.Utils.$;
  var Api = window.ApiClient;
  var S = window.AppState;
  var Toast = window.Toast;

  function sleep(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
  }

  function currentSummary() {
    return S.get('currentResult.summary') || {};
  }

  function syncRowsFromPayload(payload) {
    payload = payload || {};
    return payload.cloud_alphas || payload.alphas || [];
  }

  function mergeCloudSyncSummary(previous, incoming, rows) {
    previous = previous || {};
    incoming = incoming || {};
    rows = Array.isArray(rows) ? rows : [];
    var merged = Object.assign({}, previous, incoming);
    if (rows.length) {
      merged.status = merged.status || 'loaded';
      merged.count = Number(merged.count || rows.length);
      merged.scanned = Number(merged.scanned || merged.count || rows.length);
    }
    return merged;
  }

  function applyCloudSnapshotPayload(data) {
    data = data || {};
    var rows = syncRowsFromPayload(data);
    var summary = Object.assign({}, data.summary || data.cloud_sync || {});
    if (!summary.status && rows.length) summary.status = 'completed';
    if (typeof summary.count !== 'number') summary.count = Number(data.count || rows.length || 0);
    S.setBatch({
      'currentResult.cloud_alphas': rows,
      'currentResult.summary.cloud_sync': mergeCloudSyncSummary(currentSummary().cloud_sync, summary, rows),
    });
    if (typeof window.renderAll === 'function') window.renderAll();
  }

  function loadSnapshot() {
    return Api.get('/api/cloud_alphas?limit=500', { timeout: 120000 }).then(function (data) {
      if (data && (data.alphas || data.cloud_alphas)) applyCloudSnapshotPayload(data);
      return data;
    });
  }

  function applySyncResultPayload(payload) {
    payload = payload || {};
    var rows = syncRowsFromPayload(payload);
    var cloudSync = Object.assign({}, payload.cloud_sync || {}, {
      status: payload.status || (payload.ok === false ? 'failed' : 'completed'),
      count: Number(payload.count || payload.scanned || rows.length || 0),
      scanned: Number(payload.scanned || payload.count || rows.length || 0),
      added: Number(payload.added || 0),
      updated: Number(payload.updated || 0),
      skipped: Number(payload.skipped || 0),
      failed: Number(payload.failed || 0),
      datasets_count: Number(payload.datasets_count || 0),
      fields_count: Number(payload.fields_count || 0),
      operators_count: Number(payload.operators_count || 0),
      range: payload.range || ($('syncRange') || {}).value || '',
    });
    var nextState = {
      'currentResult.summary.cloud_sync': mergeCloudSyncSummary(currentSummary().cloud_sync, cloudSync, rows),
    };
    if (rows.length) nextState['currentResult.cloud_alphas'] = rows;
    S.setBatch(nextState);
    if (typeof window.renderAll === 'function') window.renderAll();
  }

  function renderSyncProgress(progress, fallbackMessage) {
    progress = progress || {};
    var scanned = Number(progress.scanned || progress.current || 0);
    var total = Number(progress.total || 0);
    var percent = Number(progress.percent);
    if (!Number.isFinite(percent)) percent = total > 0 ? scanned / total * 100 : 0;
    if (typeof window.Progress === 'object' && window.Progress.renderProgress) {
      window.Progress.renderProgress('cloudSync', {
        percent: percent,
        message: progress.message || fallbackMessage || '',
        scanned: scanned,
        total: total,
        added: Number(progress.added || 0),
        skipped: Number(progress.skipped || 0),
        eta_seconds: Number(progress.eta_seconds || 0),
      });
    }
  }

  function failedSyncPayload(range, message) {
    return {
      ok: false,
      status: 'failed',
      range: range,
      scanned: 0,
      total: 0,
      failed: 1,
      cloud_sync: {
        status: 'failed',
        status_code: 'FAILED',
        phase: 'failed',
        range: range,
        scanned: 0,
        total: 0,
        failed: 1,
        message: '云端同步失败：' + message,
        error: message,
      },
    };
  }

  async function pollSyncJob(jobId) {
    var terminal = { completed: true, failed: true, stopped: true };
    for (var attempt = 0; attempt < 90; attempt++) {
      await sleep(attempt < 3 ? 1200 : 2500);
      var snapshot = await Api.get('/api/sync_status?compact=1&job_id=' + encodeURIComponent(jobId), { timeout: 120000 });
      if (!snapshot || !snapshot.ok) throw new Error((snapshot && snapshot.error) || '同步状态不可用');
      var progress = snapshot.progress || {};
      S.set('liveProgress', { phase: progress.phase || 'cloud_sync', data: { cloud_sync: progress } });
      renderSyncProgress(progress, progress.message || '云端同步进行中');
      if (window._app && window._app.renderJobSnapshot) window._app.renderJobSnapshot(snapshot);
      if (terminal[String(snapshot.status || '').toLowerCase()]) {
        if (snapshot.status === 'failed') {
          renderSyncProgress(progress, snapshot.error || '云端同步失败');
          throw new Error(snapshot.error || '云端同步失败');
        }
        if (snapshot.result) applySyncResultPayload(snapshot.result);
        return snapshot;
      }
    }
    throw new Error('云端同步超时，后台任务仍未完成');
  }

  window.syncCloud = async function () {
    if (S.get('syncInFlight')) return;
    var reason = window.operationBlockReason ? window.operationBlockReason('sync') : '';
    if (reason) { Toast.warning(reason); return; }
    S.setBatch({ syncInFlight: true, syncStartedAt: Date.now() });
    if (typeof window.renderBusyControls === 'function') window.renderBusyControls();
    Toast.info('开始同步云端数据...');
    var range = ($('syncRange') || {}).value || '3d';
    try {
      var basePayload = window.collectPayload ? window.collectPayload() : {};
      var payload = Object.assign(basePayload, { range: range, syncRange: range });
      var resp = await Api.post('/api/sync_alphas', payload);
      if (resp.ok) {
        if (resp.job_id) {
          Toast.info('云端同步任务已启动：' + resp.job_id.slice(0, 8));
          await pollSyncJob(resp.job_id);
        } else {
          applySyncResultPayload(resp);
        }
        await loadSnapshot().catch(function () {});
        Toast.success('云端同步完成');
      }
    } catch (e) {
      var errorMessage = (e && e.message) ? e.message : '云端同步失败';
      var failedPayload = failedSyncPayload(range, errorMessage);
      S.set('liveProgress', { phase: 'failed', data: { cloud_sync: failedPayload.cloud_sync } });
      applySyncResultPayload(failedPayload);
      renderSyncProgress(failedPayload.cloud_sync);
      Toast.error('云端同步失败：' + errorMessage);
    } finally {
      S.set('syncInFlight', false);
      if (typeof window.renderBusyControls === 'function') window.renderBusyControls();
    }
  };

  window.CloudSync = {
    applyCloudSnapshotPayload: applyCloudSnapshotPayload,
    applySyncResultPayload: applySyncResultPayload,
    loadSnapshot: loadSnapshot,
    pollSyncJob: pollSyncJob,
    syncCloud: window.syncCloud,
  };
})();
