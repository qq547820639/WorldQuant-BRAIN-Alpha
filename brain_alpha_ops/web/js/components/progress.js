// brain_alpha_ops/web/js/components/progress.js
// Progress bar rendering component.
// v3: Enhanced with indeterminate state, ETA calculation, and better formatting.

(function () {
  'use strict';

  var $ = window.Utils.$;
  var escapeHtml = window.Utils.escapeHtml;

  /**
   * v3: Render a progress bar with optional indeterminate state.
   * @param {string} prefix - Element ID prefix (e.g., "cloudSync" -> "cloudSyncFill", "cloudSyncMeta")
   * @param {object} progress - { percent, message, scanned, total, added, skipped, eta_seconds }
   * @param {object} opts - { indeterminate }
   */
  function renderProgress(prefix, progress, opts) {
    if (!progress) return;
    opts = opts || {};

    var fillEl = $(prefix + 'Fill');
    var metaEl = $(prefix + 'Meta');

    if (!fillEl && !metaEl) return;

    // Indeterminate state
    if (opts.indeterminate) {
      if (fillEl) {
        fillEl.style.width = '';
        if (fillEl.parentElement) {
          fillEl.parentElement.classList.add('is-indeterminate');
          if (fillEl.parentElement.getAttribute('role') === 'progressbar') {
            fillEl.parentElement.setAttribute('aria-valuetext', progress.message || '处理中');
          }
        }
      }
      if (metaEl) metaEl.textContent = progress.message || '处理中...';
      return;
    }

    // Remove indeterminate
    if (fillEl && fillEl.parentElement) {
      fillEl.parentElement.classList.remove('is-indeterminate');
      if (fillEl.parentElement.getAttribute('role') === 'progressbar') {
        fillEl.parentElement.removeAttribute('aria-valuetext');
      }
    }

    var pct = progress.percent_complete !== undefined && progress.percent_complete !== null
      ? progress.percent_complete
      : progress.percent;
    if (typeof pct === 'number' && fillEl) {
      fillEl.style.width = Math.min(100, Math.max(0, pct)) + '%';
      var track = fillEl.parentElement;
      if (track && track.getAttribute('role') === 'progressbar') {
        track.setAttribute('aria-valuenow', String(Math.round(pct)));
      }
    }

    if (metaEl) {
      var parts = [];

      if (progress.message) {
        parts.push(progress.message);
      }

      var displayPercent = progress.percent_complete !== undefined && progress.percent_complete !== null
        ? progress.percent_complete
        : progress.percent;
      if (displayPercent !== undefined && displayPercent !== null) {
        if (!progress.message || progress.message.indexOf('%') === -1) {
          parts.push(Math.round(displayPercent) + '%');
        }
      }

      if (progress.scanned !== undefined && progress.total !== undefined) {
        parts.push(progress.scanned + '/' + progress.total);
      }

      if (progress.added !== undefined) {
        parts.push('新增 ' + progress.added);
      }

      if (progress.skipped !== undefined && progress.skipped > 0) {
        parts.push('跳过 ' + progress.skipped);
      }

      // ETA
      var etaSeconds = Number(progress.eta_seconds || 0);
      if ((!etaSeconds || etaSeconds < 0) && progress.eta_deadline_at_ms) {
        etaSeconds = Math.max(0, Math.ceil((Number(progress.eta_deadline_at_ms) - Date.now()) / 1000));
      }
      if (etaSeconds > 0) {
        var eta = Math.round(etaSeconds);
        var etaStr;
        if (eta < 60) etaStr = eta + ' 秒';
        else if (eta < 3600) etaStr = Math.floor(eta / 60) + ' 分';
        else etaStr = Math.floor(eta / 3600) + ' 时';
        parts.push('预计 ' + etaStr + '（预计剩余 ' + etaStr + '）');
      }

      metaEl.textContent = parts.join(' | ');
    }
  }

  /**
   * v3: Render cloud sync progress specifically (backward compat).
   */
  function renderCloudSyncProgress(progress) {
    renderProgress('cloudSync', progress);
  }

  /**
   * v3: Render check progress specifically.
   */
  function renderCheckProgress(progress) {
    renderProgress('checkProgress', progress);
  }

  window.Progress = {
    renderProgress: renderProgress,
    renderCloudSyncProgress: renderCloudSyncProgress,
    renderCheckProgress: renderCheckProgress,
  };
})();
