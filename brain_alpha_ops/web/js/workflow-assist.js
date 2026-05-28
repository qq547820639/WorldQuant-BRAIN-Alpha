// brain_alpha_ops/web/js/workflow-assist.js
// Keyboard shortcuts, quick-start wizard, and view transition helpers.
(function () {
  'use strict';

  function create(deps) {
    deps = deps || {};
    var Utils = window.Utils || {};
    var $ = deps.$ || Utils.$ || function (id) { return document.getElementById(id); };
    var esc = deps.esc || Utils.escapeHtml || function (value) { return String(value ?? ''); };
    var setSafeHtml = deps.setSafeHtml || Utils.setSafeHtml || function (el, html) { if (el) el.textContent = String(html ?? ''); };
    var state = deps.state || window.AppState;
    var Registry = deps.registry || window.ViewRegistry || {};
    var Spinner = deps.spinner || window.Spinner || {};
    var VIEW_ORDER = deps.viewOrder || Registry.VIEW_ORDER || [];
    var VIEW_TITLES = Registry.VIEW_TITLES || {};
    var shortcutsVisible = false;
    var SHORTCUTS = [
      { keys: '?', desc: '显示/隐藏快捷键列表', action: 'toggleShortcuts' },
      { keys: 'Ctrl+Enter', desc: '开始/停止生产搜索', action: 'toggle-run' },
      { keys: 'Ctrl+S', desc: '同步云端数据', action: 'sync-cloud' },
      { keys: 'Ctrl+K', desc: '聚焦搜索框', action: 'focus-search' },
      { keys: 'Ctrl+1', desc: '切换到候选池', action: 'switch-view', arg: 'candidates' },
      { keys: 'Ctrl+2', desc: '切换到达标视图', action: 'switch-view', arg: 'passed' },
      { keys: 'Ctrl+3', desc: '切换到可提交', action: 'switch-view', arg: 'submittable' },
      { keys: 'Ctrl+4', desc: '切换到云端', action: 'switch-view', arg: 'cloud' },
      { keys: 'Escape', desc: '关闭模态框/弹窗', action: 'close-modal' },
      { keys: 'Ctrl+Shift+T', desc: '切换主题', action: 'toggle-theme' },
    ];

    function invoke(name, args) {
      if (deps.invokeWindowAction) {
        deps.invokeWindowAction(name, args || []);
        return;
      }
      if (typeof window[name] === 'function') window[name].apply(window, args || []);
    }

    function findActionElement(target, boundary) {
      if (deps.findActionElement) return deps.findActionElement(target, boundary);
      while (target && target !== boundary && target.getAttribute) {
        if (target.getAttribute('data-action')) return target;
        target = target.parentElement;
      }
      return boundary && boundary.getAttribute && boundary.getAttribute('data-action') ? boundary : null;
    }

    function createShortcutsPanel() {
      var existing = $('shortcutsPanel');
      if (existing) return existing;
      var panel = document.createElement('div');
      panel.id = 'shortcutsPanel';
      panel.className = 'keyboard-shortcuts-panel hidden';
      panel.setAttribute('role', 'dialog');
      panel.setAttribute('aria-modal', 'true');
      panel.setAttribute('aria-label', '键盘快捷键');
      var itemsHtml = SHORTCUTS.map(function (s) {
        var keysHtml = s.keys.split('+').map(function (k) {
          return '<span class="kbd">' + esc(k.trim()) + '</span>';
        }).join('<span class="shortcut-separator">+</span>');
        return '<div class="shortcut-item">' +
          '<span class="shortcut-desc">' + esc(s.desc) + '</span>' +
          '<span class="shortcut-keys">' + keysHtml + '</span>' +
          '</div>';
      }).join('');
      setSafeHtml(panel,
        '<div class="shortcuts-header">' +
          '<h2>键盘快捷键</h2>' +
          '<button class="btn btn-secondary btn-sm" data-action="toggle-shortcuts">关闭</button>' +
        '</div>' +
        '<div class="shortcuts-list">' + itemsHtml + '</div>');
      document.body.appendChild(panel);
      panel.addEventListener('click', function (event) {
        var el = findActionElement(event.target, panel);
        if (el && el.getAttribute('data-action') === 'toggle-shortcuts') toggleShortcutsPanel();
      });
      panel.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') toggleShortcutsPanel();
      });
      return panel;
    }

    function toggleShortcutsPanel() {
      var panel = createShortcutsPanel();
      shortcutsVisible = !shortcutsVisible;
      panel.classList.toggle('hidden', !shortcutsVisible);
      if (shortcutsVisible) {
        var closeBtn = panel.querySelector('.btn-secondary');
        if (closeBtn) setTimeout(function () { closeBtn.focus(); }, 60);
      }
    }

    function focusSearchInput() {
      var searchEl = $('tableSearch');
      if (searchEl) {
        searchEl.focus();
        searchEl.select();
      }
    }

    function modalIsOpen(id) {
      var el = $(id);
      return Boolean(el && !el.classList.contains('hidden'));
    }

    function handleKeyboardShortcut(event) {
      var target = event.target || {};
      var tag = String(target.tagName || '').toUpperCase();
      var isInput = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable;
      if (event.key === 'Escape') {
        if (shortcutsVisible) { toggleShortcutsPanel(); event.preventDefault(); return; }
        if (window.closeDetailModal && modalIsOpen('detailModal')) { window.closeDetailModal(); event.preventDefault(); return; }
        if (window.hideConfirm && modalIsOpen('confirmOverlay')) { window.hideConfirm(); event.preventDefault(); return; }
        focusSearchInput();
        return;
      }
      if (isInput && event.key !== '?') return;
      var ctrl = event.ctrlKey || event.metaKey;
      var shift = event.shiftKey;
      if (event.key === '?') { toggleShortcutsPanel(); event.preventDefault(); return; }
      if (ctrl && event.key === 'Enter') { invoke('toggleRun'); event.preventDefault(); return; }
      if (ctrl && !shift && (event.key === 's' || event.key === 'S')) { invoke('syncCloud'); event.preventDefault(); return; }
      if (ctrl && !shift && (event.key === 'k' || event.key === 'K')) { focusSearchInput(); event.preventDefault(); return; }
      if (ctrl && shift && (event.key === 't' || event.key === 'T')) { invoke('toggleTheme'); event.preventDefault(); return; }
      if (ctrl && !shift) {
        var view = { '1': 'candidates', '2': 'passed', '3': 'submittable', '4': 'cloud' }[event.key];
        if (view) { invoke('switchView', [view]); event.preventDefault(); }
      }
    }

    function showWorkflowWizard() {
      var existing = $('workflowWizardOverlay');
      if (existing) existing.remove();
      var candidateCount = state.viewCount('candidates');
      var passedCount = state.viewCount('passed');
      var submittableCount = state.viewCount('submittable');
      var cloudCount = state.viewCount('cloud');
      var steps = [
        { title: '连接与配置', desc: '填写 BRAIN 账号并测试连接', completed: Boolean((state.get('userProfile') || {}).tier && (state.get('userProfile') || {}).tier !== '--'), icon: '1' },
        { title: '生产候选 Alpha', desc: '启动引导式生产搜索，生成并回测 Alpha', completed: candidateCount > 0, icon: '2' },
        { title: '达标检查与提交', desc: '对达标 Alpha 执行预提交检查并提交', completed: submittableCount > 0, icon: '3' },
        { title: '云端同步', desc: '刷新官方数据快照，核对线上状态', completed: cloudCount > 0, icon: '4' },
      ];
      var stepsHtml = steps.map(function (step) {
        return '<div class="workflow-wizard-step' + (step.completed ? ' is-completed' : '') + '">' +
          '<div class="workflow-wizard-step-icon">' + (step.completed ? '\u2713' : step.icon) + '</div>' +
          '<div class="workflow-wizard-step-body"><h3>' + esc(step.title) + '</h3><p>' + esc(step.desc) + '</p></div>' +
          '</div>';
      }).join('');
      var overlay = document.createElement('div');
      overlay.id = 'workflowWizardOverlay';
      overlay.className = 'workflow-wizard-overlay';
      overlay.setAttribute('role', 'dialog');
      overlay.setAttribute('aria-modal', 'true');
      overlay.setAttribute('aria-label', '操作指引');
      setSafeHtml(overlay,
        '<div class="workflow-wizard">' +
          '<div class="workflow-wizard-header"><h2>快速开始</h2><p>按 ? 查看键盘快捷键，或按以下步骤操作：</p></div>' +
          '<div class="workflow-wizard-steps">' + stepsHtml + '</div>' +
          '<div class="workflow-wizard-actions">' +
            '<button class="btn btn-secondary btn-sm" data-action="close-wizard">跳过</button>' +
            '<button class="btn btn-primary btn-sm" data-action="start-wizard-run">开始生产</button>' +
          '</div>' +
        '</div>');
      document.body.appendChild(overlay);
      overlay.addEventListener('click', function (event) { if (event.target === overlay) removeWizard(); });
      overlay.addEventListener('keydown', function (event) { if (event.key === 'Escape') { removeWizard(); event.preventDefault(); } });
      overlay.querySelector('.workflow-wizard').addEventListener('click', function (event) {
        var el = findActionElement(event.target, overlay.querySelector('.workflow-wizard'));
        if (!el) return;
        var action = el.getAttribute('data-action');
        if (action === 'close-wizard' || action === 'start-wizard-run') {
          removeWizard();
          if (action === 'start-wizard-run') invoke('toggleRun');
        }
      });
      var startBtn = overlay.querySelector('[data-action="start-wizard-run"]');
      if (startBtn) setTimeout(function () { startBtn.focus(); }, 80);
    }

    function removeWizard() {
      var overlay = $('workflowWizardOverlay');
      if (overlay) overlay.remove();
    }

    function wrapSwitchView(previousSwitchView) {
      return function (view) {
        if (VIEW_ORDER.indexOf(view) === -1) view = 'candidates';
        if (view !== deps.activeView() && Spinner.showTableSkeleton) {
          Spinner.showTableSkeleton(Math.min(5, state.viewCount(view) || 5));
        }
        if (previousSwitchView) {
          previousSwitchView(view);
        } else {
          state.set('activeView', view);
          if (deps.renderViewTabs) deps.renderViewTabs();
          if (deps.renderCurrentView) deps.renderCurrentView();
          if (deps.updatePanelHeader) deps.updatePanelHeader();
          if (deps.updateActionBarVisibility) deps.updateActionBarVisibility(view);
          if (deps.renderTaskRail) deps.renderTaskRail();
        }
        if (Spinner.announceToScreenReader) Spinner.announceToScreenReader('已切换到' + (VIEW_TITLES[view] || view));
      };
    }

    return {
      SHORTCUTS: SHORTCUTS,
      handleKeyboardShortcut: handleKeyboardShortcut,
      showWorkflowWizard: showWorkflowWizard,
      toggleShortcutsPanel: toggleShortcutsPanel,
      wrapSwitchView: wrapSwitchView,
    };
  }

  window.AppEnhancements = { create: create };
})();
