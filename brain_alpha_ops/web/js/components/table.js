// brain_alpha_ops/web/js/components/table.js
// Generic table rendering — column-driven, with empty states and mobile cards.
// v3: Enhanced with hover, selection, sort hints, and accessibility.

(function () {
  'use strict';

  var $ = window.Utils.$;
  var esc = window.Utils.escapeHtml;
  var escapeAttr = window.Utils.escapeAttr;
  var renderSafeHtmlFragment = window.Utils.renderSafeHtmlFragment;
  var setSafeHtml = window.Utils.setSafeHtml;
  var statusBadge = window.Utils.statusBadge;
  var scoreSpan = window.Utils.scoreSpan;

  function attachRowActionHandlers(container, mobileEl, onClick) {
    function detach(el) {
      if (el && el._tableActionClick) {
        el.removeEventListener('click', el._tableActionClick);
        el.removeEventListener('keydown', el._tableActionKeydown);
        el._tableActionClick = null;
        el._tableActionKeydown = null;
      }
    }
    function invoke(target, event) {
      var row = target;
      while (row && row.getAttribute && row.getAttribute('data-table-action') !== 'row-click') row = row.parentElement;
      if (!row) return;
      if (event && event.preventDefault) event.preventDefault();
      if (event && event.stopPropagation) event.stopPropagation();
      if (typeof onClick === 'function') onClick(row);
      else if (typeof onClick === 'string' && typeof window[onClick] === 'function') window[onClick](row);
    }
    function attach(el) {
      if (!el) return;
      detach(el);
      if (!onClick) return;
      el._tableActionClick = function (event) { invoke(event.target, event); };
      el._tableActionKeydown = function (event) {
        if (event.key === 'Enter' || event.key === ' ') invoke(event.target, event);
      };
      el.addEventListener('click', el._tableActionClick);
      el.addEventListener('keydown', el._tableActionKeydown);
    }
    attach(container);
    attach(mobileEl);
  }

  /**
   * v3: Full-featured table renderer.
   * @param {string} containerId - Tbody element ID
   * @param {Array} columns - [{ accessor, render, htmlType, className }]
   * @param {Array} rows - Row data objects
   * @param {object} options - { maxRows, emptyText, emptyDesc, emptyIcon, onClick, mobileColumns, mobileTitle, mobileActions }
   */
  function renderTable(containerId, columns, rows, options) {
    options = options || {};
    var container = $(containerId);
    if (!container) return;

    var maxRows = options.maxRows || 300;
    var emptyEl = document.getElementById('tableEmptyState');
    var tableEl = document.getElementById('candidateTable');
    var mobileEl = document.getElementById('mobileCardList');

    // Empty state
    if (!rows || !rows.length) {
      setSafeHtml(container, '');
      if (emptyEl) emptyEl.classList.remove('hidden');
      if (tableEl) tableEl.classList.add('hidden');
      if (mobileEl) mobileEl.classList.add('hidden');
      if (!emptyEl && options.emptyText) {
        setSafeHtml(container, '<tr><td colspan="' + Math.max(1, columns.length) + '">' + esc(options.emptyText) + '</td></tr>');
      }

      if (emptyEl && options.emptyText) {
        var iconEl = document.getElementById('tableEmptyIcon');
        var titleEl = emptyEl.querySelector('.empty-state-title');
        var descEl = document.getElementById('tableEmptyDescription');
        if (iconEl) iconEl.textContent = options.emptyIcon || '--';
        if (titleEl) titleEl.textContent = options.emptyText || '暂无数据';
        if (descEl) descEl.textContent = options.emptyDesc || '';
      }
      return;
    }

    if (emptyEl) emptyEl.classList.add('hidden');

    var displayRows = rows.slice(0, maxRows);

    // Desktop table
    if (tableEl) tableEl.classList.remove('hidden');
    if (container) {
      setSafeHtml(container, displayRows.map(function (row, idx) {
        var rowId = row.id || '';
        var rowKind = row.kind || '';
        var rowTitle = rowId || ('row ' + (idx + 1));
        var selectedCls = row._selected ? ' class="is-selected"' : '';
        var clickAction = options.onClick ? ' data-table-action="row-click"' : '';

        return '<tr data-kind="' + escapeAttr(rowKind) + '" data-id="' + escapeAttr(rowId) + '"' +
          selectedCls + ' tabindex="0" role="row" aria-keyshortcuts="Enter Space" aria-label="打开详情：' + escapeAttr(rowTitle) + '"' + clickAction + '>' +
          columns.map(function (col) {
            var value = typeof col.accessor === 'function'
              ? col.accessor(row, idx)
              : (row[col.accessor] !== undefined ? row[col.accessor] : (row.raw || {})[col.accessor]);
            var cls = col.className || '';
            if (col.render) {
              var rendered = col.render(value, row, idx);
              return '<td class="' + esc(cls) + '">' + renderSafeHtmlFragment(rendered, col.htmlType) + '</td>';
            }
            return '<td class="' + esc(cls) + '">' + esc(String(value ?? '')) + '</td>';
          }).join('') + '</tr>';
      }).join(''));
    }

    // Mobile cards
    if (mobileEl && options.mobileColumns) {
      var isMobile = window.innerWidth <= 640;
      mobileEl.classList.toggle('hidden', !isMobile);
      if (isMobile) {
        setSafeHtml(mobileEl, displayRows.map(function (row, idx) {
          var rowId = row.id || '';
          var rowKind = row.kind || '';
          var title = options.mobileTitle ? options.mobileTitle(row) : (rowId || ('条目 ' + (idx + 1)));
          var subtitle = options.mobileSubtitle ? options.mobileSubtitle(row) : '';
          var selectedCls = row._selected ? ' is-selected' : '';

          var metaItems = options.mobileColumns.map(function (col) {
            var value = typeof col.accessor === 'function' ? col.accessor(row, idx) : (row[col.accessor] !== undefined ? row[col.accessor] : (row.raw || {})[col.accessor]);
            var rendered = col.render ? col.render(value, row, idx) : String(value ?? '');
            return '<div class="mobile-card-meta-item">' +
              '<span class="mobile-card-meta-label">' + esc(col.label || '') + '</span><br>' +
              renderSafeHtmlFragment(rendered || '-', col.htmlType) +
              '</div>';
          });

          var actions = options.mobileActions ? options.mobileActions(row, idx) : '';

          return '<div class="mobile-card' + selectedCls + '" ' +
            'data-kind="' + esc(rowKind) + '" data-id="' + esc(rowId) + '" ' +
            (options.onClick ? 'tabindex="0" role="button" data-table-action="row-click"' : '') + '>' +
            '<div class="mobile-card-header">' +
            '<div class="mobile-card-title">' + esc(String(title)) + '</div>' +
            (subtitle ? '<div class="text-xs text-muted">' + subtitle + '</div>' : '') +
            '</div>' +
            '<div class="mobile-card-meta">' + metaItems.join('') + '</div>' +
            (actions ? '<div class="mobile-card-actions">' + actions + '</div>' : '') +
            '</div>';
        }).join(''));
      }
    }

    attachRowActionHandlers(container, mobileEl, options.onClick);
  }

  window.Table = {
    render: renderTable,
    statusBadge: statusBadge,
    scoreSpan: scoreSpan,
  };
})();
