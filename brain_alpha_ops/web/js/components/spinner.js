// brain_alpha_ops/web/js/components/spinner.js
// Loading spinner overlay component.
// v4: Enhanced with skeleton screens, staged messages, and progress feedback.

(function () {
  'use strict';

  var $ = window.Utils.$;
  var esc = window.Utils.escapeHtml;
  var setSafeHtml = window.Utils.setSafeHtml;
  var visible = false;
  var _messageTimer = null;
  var _stageMessages = [];
  var _stageInterval = 2000;

  // ── Spinner Overlay ───────────────────────────────────────────────────

  function showSpinner(text) {
    text = text || '处理中...';
    var overlay = $('spinnerOverlay');
    var spinnerText = $('spinnerText');
    if (overlay) {
      overlay.classList.remove('hidden');
      overlay.setAttribute('aria-hidden', 'false');
      overlay.setAttribute('aria-label', text);
    }
    if (spinnerText) {
      spinnerText.textContent = text;
    }
    visible = true;

    // Announce to screen readers
    announceToScreenReader(text);

    // Trap focus to prevent interaction with background
    if (overlay) {
      overlay.addEventListener('keydown', trapFocus);
    }
  }

  function hideSpinner() {
    var overlay = $('spinnerOverlay');
    if (overlay) {
      overlay.classList.add('hidden');
      overlay.setAttribute('aria-hidden', 'true');
      if (typeof overlay.removeAttribute === 'function') overlay.removeAttribute('aria-label');
      overlay.removeEventListener('keydown', trapFocus);
    }
    visible = false;
    stopStageMessages();
  }

  function isSpinnerVisible() {
    return visible;
  }

  function trapFocus(e) {
    if (e.key === 'Tab') {
      e.preventDefault();
    }
  }

  // v4: Staged messages — cycles through messages during long operations
  function startStageMessages(messages, interval) {
    stopStageMessages();
    _stageMessages = Array.isArray(messages) ? messages : [];
    _stageInterval = interval || 2000;
    if (!_stageMessages.length || !visible) return;

    var idx = 0;
    _messageTimer = setInterval(function () {
      idx = (idx + 1) % _stageMessages.length;
      var spinnerText = $('spinnerText');
      if (spinnerText) spinnerText.textContent = _stageMessages[idx];
    }, _stageInterval);
  }

  function stopStageMessages() {
    if (_messageTimer) {
      clearInterval(_messageTimer);
      _messageTimer = null;
    }
    _stageMessages = [];
  }

  // v4: Update spinner text in-place
  function updateSpinnerText(text) {
    var spinnerText = $('spinnerText');
    if (spinnerText && visible) {
      spinnerText.textContent = text;
    }
  }

  // ── Skeleton Screens ──────────────────────────────────────────────────

  /**
   * v4: Show a table skeleton with N rows.
   * @param {number} rowCount - number of skeleton rows (default 5)
   */
  function showTableSkeleton(rowCount) {
    rowCount = rowCount || 5;
    var tableBody = $('candidateRows');
    if (!tableBody) return;

    var cells = [32, 1, 80, 100, 72, 96, 120, 80]; // column widths pattern
    var skeletonHtml = '';
    for (var r = 0; r < rowCount; r++) {
      skeletonHtml += '<tr class="skeleton-row" aria-hidden="true">';
      for (var c = 0; c < cells.length; c++) {
        skeletonHtml += '<td><div class="skeleton skeleton-cell"></div></td>';
      }
      skeletonHtml += '</tr>';
    }
    setSafeHtml(tableBody, skeletonHtml);

    // Hide empty state
    var emptyEl = $('tableEmptyState');
    if (emptyEl) emptyEl.classList.add('hidden');
  }

  function hideTableSkeleton() {
    // Skeleton is replaced by actual render, no explicit hide needed
  }

  /**
   * v4: Show a content area skeleton (sidebar, workflow, etc.)
   */
  function showContentSkeleton(containerId, blockCount) {
    blockCount = blockCount || 3;
    var container = typeof containerId === 'string' ? $(containerId) : containerId;
    if (!container) return;

    var blocks = '';
    for (var i = 0; i < blockCount; i++) {
      var delay = i * 80;
      blocks += '<div class="skeleton skeleton-content" data-delay="' + delay + '"></div>';
    }
    setSafeHtml(container, blocks);
    var nodes = container.querySelectorAll('.skeleton-content');
    for (var j = 0; j < nodes.length; j++) {
      nodes[j].style.height = '48px';
      nodes[j].style.marginBottom = '8px';
      var nodeDelay = typeof nodes[j].getAttribute === 'function' ? nodes[j].getAttribute('data-delay') : '0';
      nodes[j].style.animationDelay = nodeDelay + 'ms';
    }
  }

  // ── Async wrapper ─────────────────────────────────────────────────────

  // v4: Enhanced with staged messages support
  async function withSpinner(text, action, stageMessages) {
    showSpinner(text);
    if (stageMessages && stageMessages.length) {
      startStageMessages(stageMessages, 1800);
    }
    try {
      return await action();
    } finally {
      hideSpinner();
    }
  }

  // ── Screen reader announcements ───────────────────────────────────────

  function announceToScreenReader(message) {
    var announcer = $('srAnnouncer');
    if (!announcer) {
      announcer = document.createElement('div');
      announcer.id = 'srAnnouncer';
      announcer.className = 'sr-only';
      announcer.setAttribute('aria-live', 'assertive');
      announcer.setAttribute('aria-atomic', 'true');
      document.body.appendChild(announcer);
    }
    // Clear and repopulate to trigger announcement
    announcer.textContent = '';
    setTimeout(function () {
      announcer.textContent = message;
    }, 50);
  }

  // ── Export ────────────────────────────────────────────────────────────

  window.Spinner = {
    showSpinner: showSpinner,
    hideSpinner: hideSpinner,
    isSpinnerVisible: isSpinnerVisible,
    withSpinner: withSpinner,
    updateSpinnerText: updateSpinnerText,
    startStageMessages: startStageMessages,
    stopStageMessages: stopStageMessages,
    showTableSkeleton: showTableSkeleton,
    hideTableSkeleton: hideTableSkeleton,
    showContentSkeleton: showContentSkeleton,
    announceToScreenReader: announceToScreenReader,
  };
})();
