// brain_alpha_ops/web/js/components/toast.js
// Toast notification component — success/error/warning/info.
// v4: Enhanced with progress bar, actionable toasts, rich icons, undo support.

(function () {
  'use strict';

  var $ = window.Utils.$;
  var escapeHtml = window.Utils.escapeHtml;
  var setSafeHtml = window.Utils.setSafeHtml;

  var ICONS = {
    success: '\u2713',
    error: '\u2717',
    warning: '\u26A0',
    info: '\u24D8',
  };

  var ICON_EMOJI = {
    success: '\u2705',
    error: '\u274C',
    warning: '\u26A0\uFE0F',
    info: '\u2139\uFE0F',
  };

  var activeToasts = [];
  var MAX_VISIBLE = 5;

  function removeToast(el) {
    if (!el) return;
    if (el._removeTimer) { clearTimeout(el._removeTimer); el._removeTimer = null; }
    if (el._progressTimer) { clearInterval(el._progressTimer); el._progressTimer = null; }
    el.classList.add('removing');
    setTimeout(function () {
      if (el.parentNode) el.parentNode.removeChild(el);
      activeToasts = activeToasts.filter(function (t) { return t !== el; });
    }, 260);
  }

  /**
   * v4: Enhanced toast with optional progress bar and action button.
   * @param {string} msg - Message text
   * @param {string} type - success | error | warning | info
   * @param {number|object} options - Duration in ms, or options object
   *   { duration, showProgress, action, actionLabel, icon }
   * @returns {HTMLElement}
   */
  function toast(msg, type, options) {
    type = type || 'info';
    var duration;
    var showProgress = false;
    var actionCallback = null;
    var actionLabel = '';
    var customIcon = null;

    if (typeof options === 'number') {
      duration = options;
    } else if (options && typeof options === 'object') {
      duration = options.duration;
      showProgress = Boolean(options.showProgress);
      actionCallback = options.action || null;
      actionLabel = options.actionLabel || '';
      customIcon = options.icon || null;
    }
    if (duration === undefined) duration = 4000;

    var container = $('toastContainer');
    if (!container) return;

    // Limit max toasts visible (FIFO eviction)
    while (activeToasts.length >= MAX_VISIBLE) {
      removeToast(activeToasts[0]);
    }

    var toastEl = document.createElement('div');
    toastEl.className = 'toast is-' + type + (showProgress && duration > 0 ? ' has-progress' : '');
    toastEl.setAttribute('role', type === 'error' ? 'alert' : 'status');
    toastEl.setAttribute('aria-live', 'polite');
    toastEl.setAttribute('aria-atomic', 'true');

    // Build toast HTML
    var iconChar = customIcon || ICONS[type] || 'i';
    var html = '<span class="toast-icon" aria-hidden="true">' + iconChar + '</span>' +
      '<span class="toast-msg">' + escapeHtml(String(msg)) + '</span>';

    if (actionCallback && typeof actionCallback === 'function') {
      html += '<button class="toast-action-btn" data-action="toast-action">' +
        escapeHtml(actionLabel || '\u21A9') + '</button>';
    }

    html += '<span class="toast-close" role="button" tabindex="0" aria-label="\u5173\u95ED\u901A\u77E5">&times;</span>';

    if (showProgress && duration > 0) {
      html += '<div class="toast-progress"></div>';
    }

    setSafeHtml(toastEl, html);

    // Keyboard support for close button
    toastEl.addEventListener('keydown', function (event) {
      var target = event.target || {};
      var isCloseBtn = target.classList && target.classList.contains('toast-close');
      if ((event.key !== 'Enter' && event.key !== ' ') || !isCloseBtn) return;
      if (event.preventDefault) event.preventDefault();
      if (event.stopPropagation) event.stopPropagation();
      removeToast(toastEl);
    });

    // Click handler: close button dismisses, action button triggers callback
    toastEl.addEventListener('click', function (event) {
      var target = event.target || {};
      if (target.classList && target.classList.contains('toast-close')) {
        if (event.stopPropagation) event.stopPropagation();
        removeToast(toastEl);
        return;
      }
      if (target.classList && target.classList.contains('toast-action-btn')) {
        if (event.stopPropagation) event.stopPropagation();
        try { actionCallback(); } catch (e) { /* ignore */ }
        removeToast(toastEl);
        return;
      }
      // Click anywhere else dismisses
      removeToast(toastEl);
    });

    container.appendChild(toastEl);
    activeToasts.push(toastEl);

    // Auto-dismiss with optional progress bar
    if (duration > 0) {
      var progressEl = toastEl.querySelector('.toast-progress');

      if (showProgress && progressEl) {
        var startTime = Date.now();
        var totalMs = duration;

        toastEl._progressTimer = setInterval(function () {
          var elapsed = Date.now() - startTime;
          var remaining = Math.max(0, totalMs - elapsed);
          var pct = (remaining / totalMs) * 100;
          progressEl.style.width = pct + '%';
          if (remaining <= 0) {
            clearInterval(toastEl._progressTimer);
            toastEl._progressTimer = null;
          }
        }, 50);
      }

      toastEl._removeTimer = setTimeout(function () {
        removeToast(toastEl);
      }, duration);
    }

    return toastEl;
  }

  // ── Convenience methods ───────────────────────────────────────────────

  function success(msg, duration) {
    return toast(msg, 'success', duration);
  }

  function error(msg, duration) {
    return toast(msg, 'error', duration || 8000);
  }

  function warning(msg, duration) {
    return toast(msg, 'warning', duration);
  }

  function info(msg, duration) {
    return toast(msg, 'info', duration);
  }

  // v4: Actionable toast with undo support
  function withAction(msg, type, actionLabel, actionFn, duration) {
    return toast(msg, type, {
      duration: duration || 6000,
      action: actionFn,
      actionLabel: actionLabel,
      showProgress: true,
    });
  }

  // v4: Persistent toast (no auto-dismiss)
  function persistent(msg, type, actionLabel, actionFn) {
    return toast(msg, type, {
      duration: 0,
      action: actionFn || null,
      actionLabel: actionLabel || '',
      showProgress: false,
    });
  }

  // v4: Clear all toasts
  function clearAll() {
    activeToasts.slice().forEach(function (t) { removeToast(t); });
  }

  // v4: Get active toast count
  function count() {
    return activeToasts.length;
  }

  window.Toast = {
    toast: toast,
    success: success,
    error: error,
    warning: warning,
    info: info,
    withAction: withAction,
    persistent: persistent,
    removeToast: removeToast,
    clearAll: clearAll,
    count: count,
  };
})();
