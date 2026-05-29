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

  function etaDeadline(seconds) {
    return Date.now() + Math.max(1, Number(seconds || 1)) * 1000;
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
    var percent = Number(progress.percent_complete !== undefined && progress.percent_complete !== null ? progress.percent_complete : progress.percent);
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
        eta_deadline_at_ms: Number(progress.eta_deadline_at_ms || 0),
      });
    }
    S.setBatch({
      runtimeStatusStartedAt: S.get('runtimeStatusStartedAt') || S.get('syncStartedAt') || Date.now(),
      runtimeStatusUpdatedAt: Date.now(),
      liveProgress: {
        phase: progress.phase || 'cloud_sync',
        data: { cloud_sync: Object.assign({}, progress, { percent: percent, scanned: scanned, total: total, message: progress.message || fallbackMessage || '云端同步进行中' }) },
      },
    });
  }

  function failedSyncPayload(range, message) {
    var jobId = S.get('syncJobId') || '';
    return {
      ok: false,
      status: 'failed',
      range: range,
      job_id: jobId,
      scanned: 0,
      total: 0,
      failed: 1,
      cloud_sync: {
        status: 'failed',
        status_code: 'FAILED',
        phase: 'failed',
        range: range,
        job_id: jobId,
        scanned: 0,
        total: 0,
        failed: 1,
        message: '云端同步失败：' + message,
        error: message,
      },
    };
  }

  function stoppedSyncPayload(range, message) {
    var jobId = S.get('syncJobId') || '';
    return {
      ok: false,
      status: 'stopped',
      range: range,
      job_id: jobId,
      scanned: 0,
      total: 0,
      cloud_sync: {
        status: 'stopped',
        status_code: 'STOPPED',
        phase: 'stopped',
        range: range,
        job_id: jobId,
        scanned: 0,
        total: 0,
        message: message || '云端同步已停止，可调整范围后重试。',
      },
    };
  }

  function markSyncRecoverable(range, message) {
    var lastProgress = S.get('liveProgress') || {};
    var lastCloudSync = lastProgress.cloud_sync || {};
    var lastScanned = Number(lastCloudSync.scanned || S.get('syncScanned') || 0);
    var lastTotal = Number(lastCloudSync.total || S.get('syncTotal') || 0);
    var lastPercent = Number(lastCloudSync.percent || S.get('syncPercent') || 0);
    var progress = {
      phase: 'waiting',
      phase_label: '等待官方接口',
      status_code: 'RECOVERABLE_TIMEOUT',
      range: range,
      job_id: S.get('syncJobId') || '',
      percent: lastPercent > 0 ? lastPercent : undefined,
      scanned: lastScanned,
      total: lastTotal,
      message: message,
      eta_seconds: 0,
      eta_deadline_at_ms: 0,
      recoverable: true,
    };
    S.setBatch({
      syncInFlight: true,
      syncRecoverable: true,
      syncLastError: message,
      runtimeStatusUpdatedAt: Date.now(),
      liveProgress: { phase: 'cloud_sync', data: { cloud_sync: progress } },
    });
    renderSyncProgress(progress, message);
  }

  async function pollSyncJob(jobId) {
    var terminal = { completed: true, completed_with_warnings: true, failed: true, stopped: true, cancelled: true };
    S.set('syncJobId', jobId || '');
    for (var attempt = 0; attempt < 90; attempt++) {
      var waitMs = attempt < 3 ? 1200 : 2500;
      var live = (((S.get('liveProgress') || {}).data || {}).cloud_sync) || {};
      if (S.get('syncInFlight')) {
        renderSyncProgress(Object.assign({}, live, {
          phase: live.phase || 'waiting',
          phase_label: live.phase_label || '等待官方接口',
          status_code: live.status_code || 'WAITING',
          job_id: jobId,
          next_poll_at_ms: Date.now() + waitMs,
          eta_seconds: Math.max(1, Math.ceil(waitMs / 1000)),
          eta_deadline_at_ms: Date.now() + waitMs,
          message: live.message || '等待官方接口返回进度，系统会自动刷新。',
        }));
      }
      await sleep(waitMs);
      var snapshot = await Api.get('/api/sync_status?compact=1&job_id=' + encodeURIComponent(jobId), { timeout: 120000 });
      if (!snapshot || !snapshot.ok) throw new Error((snapshot && snapshot.error) || '同步状态不可用');
      S.set('syncJobId', snapshot.job_id || jobId || '');
      var progress = snapshot.progress || {};
      S.setBatch({ runtimeStatusUpdatedAt: Date.now(), liveProgress: { phase: progress.phase || 'cloud_sync', data: { cloud_sync: progress } } });
      renderSyncProgress(progress, progress.message || '云端同步进行中');
      if (window._app && window._app.renderJobSnapshot) window._app.renderJobSnapshot(snapshot);
      var status = String(snapshot.status || '').toLowerCase();
      if (terminal[status]) {
        if (snapshot.status === 'failed') {
          renderSyncProgress(progress, snapshot.error || '云端同步失败');
          throw new Error(snapshot.error || '云端同步失败');
        }
        if (status === 'stopped' || status === 'cancelled') {
          applySyncResultPayload(stoppedSyncPayload(($('syncRange') || {}).value || '', progress.message || '云端同步已停止。'));
          return snapshot;
        }
        if (snapshot.result) applySyncResultPayload(snapshot.result);
        if (status === 'completed_with_warnings') Toast.warning(progress.message || '云端同步完成，但官方上下文刷新有警告。');
        return snapshot;
      }
    }
    var timeout = new Error('云端同步超时，后台任务仍未完成');
    timeout.recoverable = true;
    timeout.job_id = jobId;
    throw timeout;
  }

  window.cancelSyncCloud = async function () {
    var jobId = S.get('syncJobId') || '';
    if (!jobId) {
      Toast.warning('当前没有可停止的云端同步任务。');
      return;
    }
    try {
      renderSyncProgress({
        phase: 'stopping',
        phase_label: '正在停止',
        status_code: 'STOPPING',
        message: '正在停止云端同步，请稍候。',
        job_id: jobId,
        percent: 100,
      });
      var resp = await Api.post('/api/sync_cancel', { job_id: jobId });
      if (!resp || resp.ok === false) throw new Error((resp && resp.error) || '停止同步失败');
      applySyncResultPayload(stoppedSyncPayload(($('syncRange') || {}).value || '', resp.message || '云端同步停止请求已发送。'));
      S.setBatch({
        syncInFlight: false,
        syncRecoverable: false,
        syncJobId: '',
        syncLastError: '',
        runtimeStatusStartedAt: 0,
        runtimeStatusUpdatedAt: 0,
      });
      Toast.info(resp.message || '云端同步已停止');
    } catch (e) {
      Toast.error('停止同步失败：' + ((e && e.message) || e));
    } finally {
      if (typeof window.renderBusyControls === 'function') window.renderBusyControls();
    }
  };

  window.retrySyncCloud = async function () {
    var jobId = S.get('syncJobId') || '';
    if (jobId) {
      await window.cancelSyncCloud();
      await sleep(1200);
    }
    S.setBatch({ syncInFlight: false, syncRecoverable: false, syncJobId: '', syncLastError: '' });
    return window.syncCloud();
  };

  window.syncCloud = async function () {
    if (S.get('syncInFlight')) return;
    var reason = window.operationBlockReason ? window.operationBlockReason('sync') : '';
    if (reason) { Toast.warning(reason); return; }
    var startedAt = Date.now();
    S.setBatch({
      syncInFlight: true,
      syncRecoverable: false,
      syncJobId: '',
      syncLastError: '',
      syncStartedAt: startedAt,
      runtimeStatusStartedAt: startedAt,
      runtimeStatusUpdatedAt: startedAt,
      liveProgress: {
        phase: 'cloud_sync',
        data: { cloud_sync: { phase: 'cloud_sync', phase_label: '云端同步', message: '正在启动云端同步，请稍候。', percent: 0, scanned: 0, total: 0, eta_seconds: 10, eta_deadline_at_ms: startedAt + 10000, updated_at_ms: startedAt } },
      },
    });
    if (typeof window.renderBusyControls === 'function') window.renderBusyControls();
    Toast.info('开始同步云端数据...');
    var range = ($('syncRange') || {}).value || '3d';
    try {
      var basePayload = window.collectPayload ? window.collectPayload() : {};
      var payload = Object.assign(basePayload, { range: range, syncRange: range });
      var resp = await Api.post('/api/sync_alphas', payload);
      if (resp.ok) {
        if (resp.job_id) {
          S.set('syncJobId', resp.job_id);
          Toast.info('云端同步任务已启动：' + resp.job_id.slice(0, 8));
          await pollSyncJob(resp.job_id);
        } else {
          applySyncResultPayload(resp);
        }
        renderSyncProgress({
          phase: 'snapshot_refresh',
          phase_label: '刷新云端快照',
          status_code: 'SNAPSHOT_REFRESH',
          message: '同步已完成，正在刷新云端 Alpha 列表。',
          percent: 96,
          scanned: 1,
          total: 1,
          eta_seconds: 5,
          eta_deadline_at_ms: etaDeadline(5),
        });
        await loadSnapshot().catch(function () {});
        renderSyncProgress({
          phase: 'completed',
          phase_label: '同步完成',
          status_code: 'COMPLETED',
          message: '云端 Alpha 列表已刷新。',
          percent: 100,
          scanned: 1,
          total: 1,
          eta_seconds: 0,
        });
        Toast.success('云端同步完成');
      }
    } catch (e) {
      var errorMessage = (e && e.message) ? e.message : '云端同步失败';
      var failedPayload = failedSyncPayload(range, errorMessage);
      var recoverable = Boolean((e && e.recoverable) || (S.get('syncJobId') && /超时|仍未完成|timeout/i.test(errorMessage)));
      S.setBatch({ runtimeStatusUpdatedAt: Date.now(), liveProgress: { phase: 'failed', data: { cloud_sync: failedPayload.cloud_sync } } });
      applySyncResultPayload(failedPayload);
      renderSyncProgress(failedPayload.cloud_sync);
      if (recoverable) {
        markSyncRecoverable(range, '官方接口仍在处理本次同步；可点击“停止同步”后重试。');
        Toast.warning('云端同步等待超时，可停止后重试。');
      } else {
        Toast.error('云端同步失败：' + errorMessage);
      }
    } finally {
      if (!S.get('syncRecoverable')) {
        S.setBatch({ syncInFlight: false, syncJobId: '', runtimeStatusStartedAt: 0, runtimeStatusUpdatedAt: 0 });
      }
      if (typeof window.renderBusyControls === 'function') window.renderBusyControls();
    }
  };

  window.CloudSync = {
    applyCloudSnapshotPayload: applyCloudSnapshotPayload,
    applySyncResultPayload: applySyncResultPayload,
    loadSnapshot: loadSnapshot,
    pollSyncJob: pollSyncJob,
    cancelSyncCloud: window.cancelSyncCloud,
    retrySyncCloud: window.retrySyncCloud,
    syncCloud: window.syncCloud,
  };
})();
