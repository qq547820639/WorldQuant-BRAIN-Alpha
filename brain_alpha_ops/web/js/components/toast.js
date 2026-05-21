// brain_alpha_ops/web/js/components/toast.js
// Toast notification component — success/error/warning/info.
// v3: Enhanced with icons, stacking, duration, and queue management.

(function () {
  'use strict';

  var $ = window.Utils.$;
  var escapeHtml = window.Utils.escapeHtml;

  var ICONS = { success: '✓', error: '✗', warning: '⚠', info: 'ℹ' };
  var activeToasts = [];
  var MAX_VISIBLE = 5;

  function removeToast(el) {
    if (!el) return;
    el.classList.add('removing');
    setTimeout(function () {
      if (el.parentNode) el.parentNode.removeChild(el);
      activeToasts = activeToasts.filter(function (t) { return t !== el; });
    }, 260);
  }

  function toast(msg, type, duration) {
    type = type || 'info';
    duration = duration !== undefined ? duration : 4000;

    var container = $('toastContainer');
    if (!container) return;

    // Limit max toasts visible (FIFO eviction)
    while (activeToasts.length >= MAX_VISIBLE) {
      removeToast(activeToasts[0]);
    }

    var toastEl = document.createElement('div');
    toastEl.className = 'toast is-' + type;
    toastEl.setAttribute('role', type === 'error' ? 'alert' : 'status');
    toastEl.setAttribute('aria-live', 'polite');

    toastEl.innerHTML =
      '<span class="toast-icon">' + (ICONS[type] || 'ℹ') + '</span>' +
      '<span class="toast-msg">' + escapeHtml(String(msg)) + '</span>' +
      '<span class="toast-close" role="button" tabindex="0" aria-label="关闭通知" ' +
      'onclick="event.stopPropagation();window.Toast.removeToast(this.parentElement)" ' +
      'onkeydown="if(event.key===\'Enter\'){event.stopPropagation();window.Toast.removeToast(this.parentElement)}">✕</span>';

    // Click anywhere on toast to dismiss
    toastEl.addEventListener('click', function () { removeToast(toastEl); });

    container.appendChild(toastEl);
    activeToasts.push(toastEl);

    if (duration > 0) {
      setTimeout(function () { removeToast(toastEl); }, duration);
    }

    return toastEl;
  }

  // Convenience methods
  function success(msg, duration) { return toast(msg, 'success', duration); }
  function error(msg, duration) { return toast(msg, 'error', duration || 6000); }
  function warning(msg, duration) { return toast(msg, 'warning', duration); }
  function info(msg, duration) { return toast(msg, 'info', duration); }

  // v3: Clear all toasts
  function clearAll() {
    activeToasts.slice().forEach(function (t) { removeToast(t); });
  }

  window.Toast = {
    toast: toast,
    success: success,
    error: error,
    warning: warning,
    info: info,
    removeToast: removeToast,
    clearAll: clearAll,
  };
})();
