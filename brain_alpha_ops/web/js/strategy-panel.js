// brain_alpha_ops/web/js/strategy-panel.js
// Strategy policy summary and plugin-control state.
(function () {
  'use strict';

  var Utils = window.Utils;
  var $ = Utils.$;
  var esc = Utils.escapeHtml;
  var escapeAttr = Utils.escapeAttr;

  function syncPluginControls() {
    var enabled = Boolean(($('strategyPluginsEnabled') || {}).checked);
    var group = $('strategyPluginSpecsGroup');
    var specs = $('strategyPluginSpecs');
    var help = $('strategyPluginSpecsHelp');
    if (group) group.classList.toggle('is-disabled', !enabled);
    if (specs) {
      specs.disabled = !enabled;
      specs.setAttribute('aria-disabled', String(!enabled));
      specs.placeholder = enabled ? 'module.path:PluginClass，每行一个' : '开启策略插件后填写 module.path:PluginClass';
    }
    if (help) help.textContent = enabled
      ? '每行填写一个 module.path:PluginClass，保存配置后下一轮生产会加载。'
      : '未启用策略插件时不会加载插件；启用后每行填写一个 module.path:PluginClass。';
  }

  function renderPolicy(config) {
    var target = $('strategyText');
    if (!target) return;
    var ops = (config || {}).ops || {};
    var budget = ops.budget || {};
    var slotLimits = [
      Number(budget.official_backtest_batch_size) || 3,
      Number(budget.max_official_simulations_per_cycle) || 3,
      Number(budget.max_official_concurrent_simulations) || 3,
    ].filter(function (v) { return Number.isFinite(v) && v > 0; });
    var slotLimit = Math.max(1, Math.round(Math.min.apply(Math, slotLimits)));
    if ($('slotPolicyText')) $('slotPolicyText').textContent = slotLimit + ' 槽';
    var runForever = Boolean(budget.run_forever);
    var pluginSpecs = Array.isArray(budget.strategy_plugin_specs) ? budget.strategy_plugin_specs : [];
    var items = [
      { label: '候选上限', value: (budget.max_candidates_per_cycle || 20) + ' / 轮', note: '每轮最多生成并评分的候选数' },
      { label: '池容量', value: (budget.retained_alpha_pool_size || 10), note: '本地候选池保留上限' },
      { label: '回测槽位', value: slotLimit + ' 并发槽', note: '批量 ' + (budget.official_backtest_batch_size || 3) },
      { label: '连续生产', value: runForever ? '开启' : '单轮', note: runForever ? '持续生产' : '单轮后停止' },
      {
        label: '策略插件',
        value: budget.strategy_plugins_enabled ? ('开启 | ' + pluginSpecs.length + ' 条') : '关闭',
        note: budget.strategy_plugins_enabled
          ? (pluginSpecs.length ? pluginSpecs.join(', ') : '已开启，未配置插件规格')
          : '关闭时不会加载插件规格',
        className: 'is-wide',
      },
    ];
    target.innerHTML = '<div class="policy-grid">' +
      items.map(function (item) {
        return '<div class="policy-card' + (item.className ? ' ' + escapeAttr(item.className) : '') + '">' +
          '<div class="policy-label">' + esc(item.label) + '</div>' +
          '<div class="policy-value">' + esc(String(item.value)) + '</div>' +
          '<div class="policy-note">' + esc(item.note) + '</div>' +
          '</div>';
      }).join('') + '</div>';
  }

  window.StrategyPanel = {
    renderPolicy: renderPolicy,
    syncPluginControls: syncPluginControls,
  };
})();
