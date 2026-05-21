// brain_alpha_ops/web/js/components/modal.js
// Confirmation dialog modal component.

(function () {
  'use strict';

  var $ = window.Utils.$;
  var escapeHtml = window.Utils.escapeHtml;

  function hideConfirm() {
    var overlay = $('confirmOverlay');
    if (overlay) {
      overlay.classList.remove('active');
      overlay.classList.add('hidden');
      overlay.setAttribute('aria-hidden', 'true');
    }
  }

  function confirmAction(msg, yesText, noText) {
    yesText = yesText || '确认';
    noText = noText || '取消';

    return new Promise(function (resolve) {
      var overlay = $('confirmOverlay');
      var textEl = $('confirmText');
      var yesBtn = $('confirmYes');
      var noBtn = $('confirmNo');

      if (!overlay || !textEl || !yesBtn || !noBtn) {
        resolve(false);
        return;
      }

      textEl.textContent = msg;
      yesBtn.textContent = yesText;
      noBtn.textContent = noText;

      overlay.classList.remove('hidden');
      overlay.classList.add('active');
      overlay.setAttribute('aria-hidden', 'false');
      noBtn.focus();

      function cleanup() {
        overlay.classList.remove('active');
        overlay.classList.add('hidden');
        overlay.setAttribute('aria-hidden', 'true');
        yesBtn.removeEventListener('click', onYes);
        noBtn.removeEventListener('click', onNo);
      }

      function onYes() {
        cleanup();
        resolve(true);
      }

      function onNo() {
        cleanup();
        resolve(false);
      }

      yesBtn.addEventListener('click', onYes);
      noBtn.addEventListener('click', onNo);
    });
  }

  window.Modal = {
    confirmAction: confirmAction,
    hideConfirm: hideConfirm
  };

  // Backward-compatible handler used by inline overlay markup.
  window.hideConfirm = hideConfirm;
})();
