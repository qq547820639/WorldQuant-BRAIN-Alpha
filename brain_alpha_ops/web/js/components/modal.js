// brain_alpha_ops/web/js/components/modal.js
// Confirmation dialog modal component.
// v3: Enhanced with focus trap, icon, and better keyboard a11y.

(function () {
  'use strict';

  var $ = window.Utils.$;
  var escapeHtml = window.Utils.escapeHtml;

  function hideConfirm() {
    var overlay = $('confirmOverlay');
    if (overlay) {
      overlay.classList.add('hidden');
      overlay.setAttribute('aria-hidden', 'true');
    }
  }

  /**
   * v3: Enhanced confirm with optional icon, auto-focus, and Escape handling.
   * @param {string} msg - Message text
   * @param {string} yesText - Confirm button text
   * @param {string} noText - Cancel button text
   * @param {object} opts - { icon, variant (danger/warning/default) }
   * @returns {Promise<boolean>}
   */
  function confirmAction(msg, yesText, noText, opts) {
    yesText = yesText || '确认';
    noText = noText || '取消';
    opts = opts || {};

    return new Promise(function (resolve) {
      var overlay = $('confirmOverlay');
      var textEl = $('confirmText');
      var yesBtn = $('confirmYes');
      var noBtn = $('confirmNo');
      var iconEl = overlay ? overlay.querySelector('.confirm-dialog-icon') : null;

      if (!overlay || !textEl || !yesBtn || !noBtn) {
        resolve(false);
        return;
      }

      textEl.textContent = msg;
      yesBtn.textContent = yesText;
      noBtn.textContent = noText;

      // v3: Style the yes button based on variant
      yesBtn.className = 'btn btn-sm ' + (opts.variant === 'danger' ? 'btn-danger' : 'btn-primary');

      // v3: Icon
      if (iconEl) {
        iconEl.style.display = opts.icon === false ? 'none' : '';
        iconEl.textContent = opts.icon || '⚠';
      }

      overlay.classList.remove('hidden');
      overlay.setAttribute('aria-hidden', 'false');

      // Focus management
      var previousFocus = document.activeElement;
      setTimeout(function () { noBtn.focus(); }, 60);

      function onKeyDown(e) {
        if (e.key === 'Escape') { cleanup(); resolve(false); }
        if (e.key === 'Enter' && document.activeElement === yesBtn) { cleanup(); resolve(true); }
      }

      document.addEventListener('keydown', onKeyDown);

      function cleanup() {
        document.removeEventListener('keydown', onKeyDown);
        overlay.classList.add('hidden');
        overlay.setAttribute('aria-hidden', 'true');
        yesBtn.removeEventListener('click', onYes);
        noBtn.removeEventListener('click', onNo);
        if (previousFocus && typeof previousFocus.focus === 'function') {
          try { previousFocus.focus(); } catch (e) { /* ignore */ }
        }
      }

      function onYes() { cleanup(); resolve(true); }
      function onNo() { cleanup(); resolve(false); }

      yesBtn.addEventListener('click', onYes);
      noBtn.addEventListener('click', onNo);
    });
  }

  // v3: Danger confirmation shortcut
  function confirmDanger(msg, yesText) {
    return confirmAction(msg, yesText || '确认删除', '取消', { variant: 'danger', icon: '⚠' });
  }

  window.Modal = {
    confirmAction: confirmAction,
    confirmDanger: confirmDanger,
    hideConfirm: hideConfirm,
  };

  // Backward-compatible handler used by inline overlay markup
  window.hideConfirm = hideConfirm;
})();
