// brain_alpha_ops/web/js/result-state.js
// Pure result snapshot merging for the app entry point.
(function () {
  'use strict';

  var VM = window.ViewModel;
  var chooseRuntimeArray = VM.chooseRuntimeArray;
  var firstArrayWithItems = VM.firstArrayWithItems;
  var firstPositiveFiniteNumber = VM.firstPositiveFiniteNumber;
  var uniqueBacktestSlots = VM.uniqueBacktestSlots;
  var uniqueCandidates = VM.uniqueCandidates;
  var uniqueLifecycle = VM.uniqueLifecycle;

  function cloudSyncStatus(cloud) {
    cloud = cloud || {};
    return String(cloud.phase || cloud.status || cloud.status_code || '').trim().toLowerCase();
  }

  function isActiveCloudSync(cloud) {
    cloud = cloud || {};
    var status = cloudSyncStatus(cloud);
    if (['completed', 'synced', 'failed', 'skipped'].indexOf(status) !== -1) return false;
    if (['auth', 'scan', 'merge', 'running', 'cloud_sync'].indexOf(status) !== -1) return true;
    return firstPositiveFiniteNumber(cloud.scanned, cloud.current, cloud.total) !== null;
  }

  function isEmptyCloudSyncSnapshot(cloud, rows) {
    cloud = cloud || {};
    var status = cloudSyncStatus(cloud);
    if (status === 'empty') return true;
    if (['completed', 'synced', 'failed', 'skipped'].indexOf(status) !== -1) return false;
    if (Array.isArray(rows) && rows.length > 0) return false;
    return !firstPositiveFiniteNumber(cloud.scanned, cloud.current, cloud.total) &&
      !firstPositiveFiniteNumber(cloud.count, cloud.loaded);
  }

  function mergeCloudSyncSummary(previous, incoming, rows, liveCloud) {
    previous = previous || {};
    incoming = incoming || {};
    liveCloud = liveCloud || {};
    var active = isActiveCloudSync(liveCloud) ? Object.assign({}, previous, liveCloud) : previous;
    if (isActiveCloudSync(active) && isEmptyCloudSyncSnapshot(incoming, rows)) return Object.assign({}, incoming, active);
    if (!Object.keys(incoming).length && Object.keys(active).length) return Object.assign({}, active);
    return Object.assign({}, previous, incoming);
  }

  function buildResultBatch(result, context) {
    result = result || {};
    context = context || {};
    var previousSummary = context.currentSummary || {};
    var summary = Object.assign({}, result.summary || {});
    var currentCandidates = context.currentCandidates || [];
    var currentCloudAlphas = context.currentCloudAlphas || [];
    var currentLifecycle = context.currentLifecycle || [];
    var currentBacktests = context.currentBacktests || [];
    var liveCloud = typeof context.liveCloudSyncProgress === 'function' ? context.liveCloudSyncProgress() : {};

    var incomingCloudRows = Array.isArray(summary.cloud_alphas) ? summary.cloud_alphas : null;
    summary.cloud_sync = mergeCloudSyncSummary(previousSummary.cloud_sync, summary.cloud_sync || {}, incomingCloudRows, liveCloud);

    return {
      'currentResult.summary': summary,
      'currentResult.candidates': uniqueCandidates(chooseRuntimeArray(summary.candidates, result.candidates, currentCandidates)) || [],
      'currentResult.pending_backtest_candidates': uniqueCandidates(chooseRuntimeArray(summary.pending_backtest_candidates, null, context.currentPendingBacktestCandidates || [])) || [],
      'currentResult.passed_candidates': uniqueCandidates(chooseRuntimeArray(summary.passed_candidates, null, [])) || [],
      'currentResult.cloud_alphas': uniqueCandidates(Array.isArray(incomingCloudRows) ? incomingCloudRows : currentCloudAlphas) || [],
      'currentResult.lifecycle_records': uniqueLifecycle(summary.lifecycle_records || currentLifecycle) || [],
      'currentResult.backtests': uniqueBacktestSlots(summary.backtest_slots || summary.backtests || result.backtests || currentBacktests) || [],
    };
  }

  function jobToResult(job) {
    job = job || {};
    var progress = job.progress || {};
    var data = progress.data || {};
    var result = job.result || {};
    var summary = Object.assign({}, data, result.summary || {});
    return {
      summary: summary,
      candidates: firstArrayWithItems(summary.candidates, data.candidates, result.candidates) || [],
      backtests: summary.backtests || [],
    };
  }

  window.ResultState = {
    buildResultBatch: buildResultBatch,
    cloudSyncStatus: cloudSyncStatus,
    isActiveCloudSync: isActiveCloudSync,
    isEmptyCloudSyncSnapshot: isEmptyCloudSyncSnapshot,
    jobToResult: jobToResult,
    mergeCloudSyncSummary: mergeCloudSyncSummary,
  };
})();
