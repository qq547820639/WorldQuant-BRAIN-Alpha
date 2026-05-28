// brain_alpha_ops/web/js/header-status.js
// Header connection and runtime status rendering.

(function () {
  'use strict';

  var $ = window.Utils.$;
  var phaseName = window.Utils.phaseName;
  var S = window.AppState;

  function render(runtimeKind, runtimeKindLabel) {
    var statusEl = $('globalStatus');
    var dotEl = $('headerStatusDot');
    if (!statusEl && !dotEl) return;
    var live = S.get('liveProgress') || {};
    var phase = live.phase || '';
    var connectionStatus = String(S.get('connectionStatus') || 'disconnected');
    var env = S.get('connectionEnvironment') || '';
    var auth = S.get('connectionAuth') || '';
    var label = '系统空闲';
    var textClass = 'text-sm text-muted';
    var dotClass = 'header-status-dot';
    if (runtimeKind) {
      label = runtimeKindLabel(runtimeKind) + '中';
      if (phase) label += ' — ' + phaseName(phase);
      textClass = 'text-sm text-success fw-bold';
      dotClass += ' is-running';
    } else if (connectionStatus === 'connected') {
      label = '已连接' + (env ? ' — ' + env : '') + (auth ? ' · ' + auth : '');
      textClass = 'text-sm text-success fw-bold';
      dotClass += ' is-connected';
    } else if (connectionStatus === 'failed') {
      label = '连接失败';
      textClass = 'text-sm text-danger fw-bold';
      dotClass += ' is-error';
    }
    if (statusEl) {
      statusEl.textContent = label;
      statusEl.className = textClass;
    }
    if (dotEl) dotEl.className = dotClass;
  }

  window.HeaderStatus = { render: render };
})();
