// brain_alpha_ops/web/js/components/table.js
// Generic table rendering — column-driven, with empty states and mobile cards.
// v3: Enhanced with hover, selection, sort hints, and accessibility.

(function () {
  'use strict';

  var $ = window.Utils.$;
  var esc = window.Utils.escapeHtml;
  var statusBadge = window.Utils.statusBadge;
  var scoreSpan = window.Utils.scoreSpan;

  /**
   * v3: Full-featured table renderer.
   * @param {string} containerId - Tbody element ID
   * @param {Array} columns - [{ accessor, render, trustedHtml, className }]
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
      if (container) container.innerHTML = '';
      if (emptyEl) emptyEl.classList.remove('hidden');
      if (tableEl) tableEl.classList.add('hidden');
      if (mobileEl) mobileEl.classList.add('hidden');

      if (emptyEl && options.emptyText) {
        var iconEl = document.getElementById('tableEmptyIcon');
        var titleEl = emptyEl.querySelector('.empty-state-title');
        var descEl = document.getElementById('tableEmptyDescription');
        if (iconEl) iconEl.textContent = options.emptyIcon || '📊';
        if (titleEl) titleEl.textContent = options.emptyText || '暂无数据';
        if (descEl) descEl.textContent = options.emptyDesc || '';
      }
      return;
    }

    if (emptyEl) emptyEl.classList.add('hidden');

    var displayRows = rows.slice(0, maxRows);

    // Desktop table
    if (tableEl) {
      tableEl.classList.remove('hidden');
      if (container) {
        container.innerHTML = displayRows.map(function (row, idx) {
          var rowId = row.id || '';
          var rowKind = row.kind || '';
          var selectedCls = row._selected ? ' class="is-selected"' : '';
          var clickHandler = options.onClick ? ' onclick="' + options.onClick + '(this)"' : '';

          return '<tr data-kind="' + esc(rowKind) + '" data-id="' + esc(rowId) + '"' +
            selectedCls + ' tabindex="0" role="button" aria-label="查看详情"' + clickHandler +
            ' onkeydown="if(event.key===\'Enter\')this.click()">' +
            columns.map(function (col) {
              var value = typeof col.accessor === 'function'
                ? col.accessor(row, idx)
                : (row.raw || row)[col.accessor];
              var cls = col.className || '';
              if (col.render) {
                var rendered = col.render(value, row, idx);
                return '<td class="' + esc(cls) + '">' + (col.trustedHtml ? rendered : esc(String(rendered ?? ''))) + '</td>';
              }
              return '<td class="' + esc(cls) + '">' + esc(String(value ?? '')) + '</td>';
            }).join('') + '</tr>';
        }).join('');
      }
    }

    // Mobile cards
    if (mobileEl && options.mobileColumns) {
      var isMobile = window.innerWidth <= 640;
      mobileEl.classList.toggle('hidden', !isMobile);
      if (isMobile) {
        mobileEl.innerHTML = displayRows.map(function (row, idx) {
          var rowId = row.id || '';
          var rowKind = row.kind || '';
          var title = options.mobileTitle ? options.mobileTitle(row) : (rowId || ('条目 ' + (idx + 1)));
          var subtitle = options.mobileSubtitle ? options.mobileSubtitle(row) : '';
          var selectedCls = row._selected ? ' is-selected' : '';

          var metaItems = options.mobileColumns.map(function (col) {
            var value = typeof col.accessor === 'function' ? col.accessor(row, idx) : (row.raw || row)[col.accessor];
            var rendered = col.render ? col.render(value, row, idx) : esc(String(value ?? ''));
            return '<div class="mobile-card-meta-item">' +
              '<span style="color:var(--text-muted);font-size:var(--fs-2xs)">' + esc(col.label || '') + '</span><br>' +
              (col.trustedHtml ? rendered : esc(String(rendered ?? '-'))) +
              '</div>';
          });

          var actions = options.mobileActions ? options.mobileActions(row, idx) : '';

          return '<div class="mobile-card' + selectedCls + '" ' +
            'data-kind="' + esc(rowKind) + '" data-id="' + esc(rowId) + '" ' +
            'tabindex="0" role="button"' + (options.onClick ? ' onclick="' + options.onClick + '(this)"' : '') +
            ' onkeydown="if(event.key===\'Enter\')this.click()">' +
            '<div class="mobile-card-header">' +
            '<div class="mobile-card-title">' + esc(String(title)) + '</div>' +
            (subtitle ? '<div class="text-xs text-muted">' + subtitle + '</div>' : '') +
            '</div>' +
            '<div class="mobile-card-meta">' + metaItems.join('') + '</div>' +
            (actions ? '<div class="mobile-card-actions">' + actions + '</div>' : '') +
            '</div>';
        }).join('');
      }
    }
  }

  window.Table = {
    render: renderTable,
    statusBadge: statusBadge,
    scoreSpan: scoreSpan,
  };
})();
