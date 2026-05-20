// brain_alpha_ops/web/js/components/progress.js
// Progress bar rendering component.

(function () {
  'use strict';

  var $ = window.Utils.$;
  var escapeHtml = window.Utils.escapeHtml;

  function renderProgress(prefix, progress) {
    if (!progress) return;

    var fillEl = $(prefix + 'Fill');
    var metaEl = $(prefix + 'Meta');

    if (!fillEl && !metaEl) return;

    var pct = progress.percent;
    if (typeof pct === 'number' && fillEl) {
      fillEl.style.width = Math.min(100, Math.max(0, pct)) + '%';
    }

    if (metaEl) {
      var msg = progress.message || '';

      if (progress.percent !== undefined && progress.percent !== null && msg.indexOf('%') === -1) {
        msg = msg + ' ' + Math.round(progress.percent) + '%';
      }

      if (progress.scanned !== undefined && progress.total !== undefined) {
        msg = msg + ' (' + progress.scanned + '/' + progress.total + ')';
      }

      if (progress.added !== undefined) {
        msg = msg + ' 已新增 ' + progress.added;
      }

      if (progress.skipped !== undefined) {
        msg = msg + ' 已跳过 ' + progress.skipped;
      }

      metaEl.textContent = msg;
    }
  }

  window.Progress = {
    renderProgress: renderProgress
  };
})();
