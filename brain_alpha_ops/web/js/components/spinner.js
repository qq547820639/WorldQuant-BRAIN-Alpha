// brain_alpha_ops/web/js/components/spinner.js
// Loading spinner overlay component.

(function () {
  'use strict';

  var $ = window.Utils.$;

  function showSpinner(text) {
    text = text || '处理中...';

    var overlay = $('spinnerOverlay');
    var spinnerText = $('spinnerText');

    if (overlay) {
      overlay.classList.remove('hidden');
      overlay.classList.add('active');
    }
    if (spinnerText) {
      spinnerText.textContent = text;
    }
  }

  function hideSpinner() {
    var overlay = $('spinnerOverlay');
    if (overlay) {
      overlay.classList.remove('active');
      overlay.classList.add('hidden');
    }
  }

  window.Spinner = {
    showSpinner: showSpinner,
    hideSpinner: hideSpinner
  };
})();
