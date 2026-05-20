// brain_alpha_ops/web/js/components/toast.js
// Toast notification component — success/error/warning/info.

(function () {
  'use strict';

  var $ = window.Utils.$;
  var escapeHtml = window.Utils.escapeHtml;

  var ICONS = {
    success: '\u2713',
    error: '\u2717',
    warning: '\u26A0',
    info: '\u2139'
  };

  function removeToast(el) {
    if (!el) return;
    el.classList.add('removing');
    setTimeout(function () {
      if (el.parentNode) {
        el.parentNode.removeChild(el);
      }
    }, 300);
  }

  function toast(msg, type, duration) {
    type = type || 'info';
    duration = duration || 4000;

    var container = $('toastContainer');
    if (!container) return;

    var toastEl = document.createElement('div');
    toastEl.className = 'toast ' + type;
    toastEl.innerHTML =
      '<span class="toast-icon">' + ICONS[type] + '</span>' +
      '<span class="toast-msg">' + escapeHtml(msg) + '</span>';

    container.appendChild(toastEl);

    if (duration > 0) {
      setTimeout(function () {
        removeToast(toastEl);
      }, duration);
    }

    return toastEl;
  }

  window.Toast = {
    toast: toast,
    removeToast: removeToast
  };
})();
