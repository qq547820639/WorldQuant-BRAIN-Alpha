// brain_alpha_ops/web/js/result-table.js
// Main result table, mobile cards, and empty-state rendering.
(function () {
  'use strict';

  var Utils = window.Utils;
  var Registry = window.ViewRegistry;
  var VM = window.ViewModel;
  var $ = Utils.$;
  var esc = Utils.escapeHtml;
  var escapeAttr = Utils.escapeAttr;
  var renderSafeHtmlFragment = Utils.renderSafeHtmlFragment;
  var candidateIdentity = VM.candidateIdentity;

  function create(deps) {
    deps = deps || {};
    var state = deps.state || window.AppState;
    var maxRows = deps.maxRows || state.MAX_RENDERED_ROWS || 300;

    function activeView() {
      return deps.activeView ? deps.activeView() : (state.get('activeView') || 'candidates');
    }

    function rowsFor(view) {
      return deps.getRowsForView ? deps.getRowsForView(view) : [];
    }

    function renderCurrentView() {
      var view = activeView();
      var rows = rowsFor(view);
      if (deps.applySearchFilter) deps.applySearchFilter(rows);
      var columns = deps.getColumnsForView ? deps.getColumnsForView(view) : [];
      var tableBody = $('candidateRows');
      var emptyEl = document.getElementById('tableEmptyState');
      var tableEl = document.getElementById('candidateTable');
      var mobileEl = document.getElementById('mobileCardList');
      if (!rows.length) {
        if (tableBody) tableBody.innerHTML = '';
        if (tableEl) tableEl.classList.add('hidden');
        if (mobileEl) mobileEl.classList.add('hidden');
        if (emptyEl) {
          emptyEl.classList.remove('hidden');
          renderEmptyState(view);
        }
        updateCountPill(rows.length);
        updateSortHint(view);
        return;
      }
      if (emptyEl) emptyEl.classList.add('hidden');
      if (tableEl) tableEl.classList.remove('hidden');
      var displayRows = rows.slice(0, maxRows);
      renderDesktopRows(tableBody, displayRows, columns);
      renderMobileRows(mobileEl, displayRows, view);
      updateCountPill(rows.length);
      updateSortHint(view);
    }

    function renderEmptyState(view) {
      var descEl = document.getElementById('tableEmptyDescription');
      if (descEl) descEl.textContent = getEmptyDescription(view);
      var iconEl = document.getElementById('tableEmptyIcon');
      if (iconEl) iconEl.textContent = (Registry.VIEW_ICONS || {})[view] || '--';
      var actionsEl = document.getElementById('tableEmptyActions');
      if (actionsEl) actionsEl.innerHTML = getEmptyActionsHtml(view);
    }

    function renderDesktopRows(tableBody, rows, columns) {
      if (!tableBody) return;
      tableBody.innerHTML = rows.map(function (row, idx) {
        var isSelected = isSelectedRow(row);
        state.setCached(row, row.raw || row);
        var rowHtml = '<tr data-action="open-row" data-kind="' + escapeAttr(row.kind || '') + '" data-id="' + escapeAttr(row.id || '') + '"' +
          (isSelected ? ' class="is-selected"' : '') + ' tabindex="0" role="button" aria-label="查看详情">';
        rowHtml += columns.map(function (col) {
          var value = typeof col.accessor === 'function' ? col.accessor(row, idx) : (row.raw || row)[col.accessor];
          var rendered = col.render ? col.render(value, row, idx) : String(value ?? '');
          return '<td>' + renderSafeHtmlFragment(rendered, col.htmlType) + '</td>';
        }).join('');
        return rowHtml + '</tr>';
      }).join('');
    }

    function renderMobileRows(mobileEl, rows, view) {
      if (!mobileEl) return;
      if (window.innerWidth > 640) {
        mobileEl.classList.add('hidden');
        return;
      }
      mobileEl.classList.remove('hidden');
      var mobileCols = deps.getMobileColumns ? deps.getMobileColumns(view) : [];
      mobileEl.innerHTML = rows.map(function (row, idx) {
        var isSelected = isSelectedRow(row);
        var title = row.id || candidateIdentity(row.raw || {}) || ('条目 ' + (idx + 1));
        var metaHtml = mobileCols.map(function (col) {
          var value = typeof col.accessor === 'function' ? col.accessor(row, idx) : (row.raw || row)[col.accessor];
          var rendered = col.render ? col.render(value, row, idx) : String(value ?? '');
          return '<div class="mobile-card-meta-item">' + renderSafeHtmlFragment(rendered || '-', col.htmlType) + '</div>';
        }).join('');
        var actionsHtml = deps.renderMobileActions ? deps.renderMobileActions(row, view) : '';
        state.setCached(row, row.raw || row);
        return '<div class="mobile-card' + (isSelected ? ' is-selected' : '') + '"' +
          ' data-kind="' + escapeAttr(row.kind || '') + '" data-id="' + escapeAttr(row.id || '') + '">' +
          '<div class="mobile-card-header"><div class="mobile-card-title">' + esc(String(title)) + '</div></div>' +
          '<div class="mobile-card-meta">' + metaHtml + '</div>' +
          (actionsHtml ? '<div class="mobile-card-actions">' + actionsHtml + '</div>' : '') +
          '</div>';
      }).join('');
    }

    function isSelectedRow(row) {
      if (!deps.isSelectedSubmitId) return false;
      return deps.isSelectedSubmitId(row.id || candidateIdentity(row.raw || {}));
    }

    function getEmptyDescription(view) {
      var defaults = {
        candidates: '启动生产搜索会自动生成、评分并维护候选池；也可以先同步云端数据了解当前状态。',
        pending_backtest: '当前没有排队回测项。新的候选进入官方模拟前会显示在这里。',
        running_backtest: '当前没有正在等待官方结果的回测。运行中的槽位会实时更新。',
        backtest_rework: '没有需要返工的 Alpha。失败或被拒绝的回测会集中到这里。',
        passed: '还没有达到提交门槛的 Alpha。生产任务产生达标项后，可以在这里发起官方预提交检查。',
        submittable: '没有处于有效检查期内的 Alpha。请先在达标视图执行快速或全部检查。',
        submitted: '当前没有本地提交记录。提交成功后会自动刷新检查状态。',
        failed: '当前没有失败、拒绝或被阻断的 Alpha。',
        cloud: '还没有云端快照。同步云端数据后可查看官方 Alpha 状态和风险信息。',
        lifecycle: '还没有生命周期事件。生产、检查和提交动作会在这里留下审计记录。',
      };
      var query = String(($('tableSearch') || {}).value || '').trim();
      if (query) return '没有匹配当前筛选条件的数据，请调整搜索词或清空筛选。';
      return defaults[view] || '当前视图暂无数据，请调整筛选条件或开始生产。';
    }

    function emptyAction(action, label, primary, attrs) {
      return '<button class="btn ' + (primary ? 'btn-primary' : 'btn-secondary') + '"' +
        ' data-action="' + escapeAttr(action) + '"' + (attrs || '') + '>' + esc(label) + '</button>';
    }

    function getEmptyActionsHtml(view) {
      var query = String(($('tableSearch') || {}).value || '').trim();
      if (query) return emptyAction('clear-search', '清空搜索', true) + emptyAction('sync-cloud', '同步云端数据', false);
      if (view === 'passed') return emptyAction('toggle-run', '继续生产', true) + emptyAction('sync-cloud', '同步云端数据', false);
      if (view === 'submittable') return emptyAction('switch-view', '去达标检查', true, ' data-view="passed"') + emptyAction('check-batch', '执行检查', false);
      if (view === 'cloud') return emptyAction('sync-cloud', '同步云端数据', true) + emptyAction('switch-view', '查看候选池', false, ' data-view="candidates"');
      if (view === 'lifecycle') return emptyAction('toggle-run', '开始生产搜索', true) + emptyAction('sync-cloud', '同步云端数据', false);
      if (Registry.RESEARCH_VIEWS && Registry.RESEARCH_VIEWS.indexOf(view) !== -1) return emptyAction('switch-view', '查看候选池', true, ' data-view="candidates"') + emptyAction('toggle-run', '开始生产搜索', false);
      return emptyAction('toggle-run', '开始生产搜索', true) + emptyAction('sync-cloud', '同步云端数据', false);
    }

    function updateSortHint(view) {
      var el = $('sortHint');
      if (!el) return;
      var hints = { candidates: '按排序分降序', passed: '按排序分降序', submittable: '按可提交状态排序' };
      el.textContent = hints[view] || '';
    }

    function updatePanelHeader() {
      var view = activeView();
      var titleEl = $('tableTitle');
      var hintEl = $('panelHint');
      if (titleEl) titleEl.textContent = (Registry.VIEW_TITLES || {})[view] || view;
      if (hintEl) hintEl.textContent = (Registry.VIEW_HINTS || {})[view] || '';
      updateCountPill();
    }

    function updateCountPill(countOverride) {
      var pill = $('countPill');
      if (!pill) return;
      var rows = rowsFor(activeView());
      var count = typeof countOverride === 'number' ? countOverride : rows.length;
      pill.textContent = count + ' 条';
      pill.className = 'badge ' + (count > 0 ? 'badge-accent' : 'badge-default');
    }

    function actionButton(action, label, row, className, options) {
      options = options || {};
      var pressed = options.pressed === undefined ? '' : ' aria-pressed="' + Boolean(options.pressed) + '"';
      return '<button type="button" class="' + escapeAttr(className || 'btn btn-secondary btn-sm') + '"' +
        ' data-action="' + escapeAttr(action) + '"' +
        ' data-kind="' + escapeAttr((row && row.kind) || '') + '"' +
        ' data-id="' + escapeAttr((row && row.id) || '') + '"' + pressed + '>' +
        esc(label) + '</button>';
    }

    return {
      actionButton: actionButton,
      getEmptyActionsHtml: getEmptyActionsHtml,
      getEmptyDescription: getEmptyDescription,
      renderCurrentView: renderCurrentView,
      updateCountPill: updateCountPill,
      updatePanelHeader: updatePanelHeader,
      updateSortHint: updateSortHint,
    };
  }

  window.ResultTableView = { create: create };
})();
