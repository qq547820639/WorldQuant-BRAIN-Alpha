// brain_alpha_ops/web/js/components/spinner.js
// Loading spinner overlay component.
// v3: Enhanced with progress message and keyboard trap prevention.

(function () {
  'use strict';

  var $ = window.Utils.$;
  var visible = false;

  function showSpinner(text) {
    text = text || '处理中...';
    var overlay = $('spinnerOverlay');
    var spinnerText = $('spinnerText');
    if (overlay) {
      overlay.classList.remove('hidden');
      overlay.setAttribute('aria-hidden', 'false');
    }
    if (spinnerText) {
      spinnerText.textContent = text;
    }
    visible = true;

    // Trap focus inside spinner to prevent interaction with background
    if (overlay) {
      overlay.addEventListener('keydown', trapFocus);
    }
  }

  function hideSpinner() {
    var overlay = $('spinnerOverlay');
    if (overlay) {
      overlay.classList.add('hidden');
      overlay.setAttribute('aria-hidden', 'true');
      overlay.removeEventListener('keydown', trapFocus);
    }
    visible = false;
  }

  function isSpinnerVisible() {
    return visible;
  }

  function trapFocus(e) {
    if (e.key === 'Tab') {
      e.preventDefault();
    }
  }

  // v3: Async wrapper — show spinner, run action, hide spinner. Handles errors.
  async function withSpinner(text, action) {
    showSpinner(text);
    try {
      return await action();
    } finally {
      hideSpinner();
    }
  }

  window.Spinner = {
    showSpinner: showSpinner,
    hideSpinner: hideSpinner,
    isSpinnerVisible: isSpinnerVisible,
    withSpinner: withSpinner,
  };
})();
