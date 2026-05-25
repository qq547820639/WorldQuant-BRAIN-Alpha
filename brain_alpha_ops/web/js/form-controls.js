// brain_alpha_ops/web/js/form-controls.js
// Form reads, writes, and payload assembly for BRAIN API actions.
(function () {
  'use strict';

  var $ = window.Utils.$;

  function fieldValue(id) {
    var el = $(id);
    return el ? el.value : '';
  }

  function checkedValue(id) {
    var el = $(id);
    return Boolean(el && el.checked);
  }

  function numericValue(id, fallback) {
    var value = Number(fieldValue(id));
    return Number.isFinite(value) ? value : fallback;
  }

  function setControlValue(id, value) {
    var el = $(id);
    if (!el || value === undefined || value === null) return;
    if (String(el.type || '').toLowerCase() === 'checkbox') {
      el.checked = Boolean(value);
      return;
    }
    el.value = value;
  }

  function connectionPayload() {
    return {
      username: fieldValue('username'),
      password: fieldValue('password'),
      token: fieldValue('token'),
      baseUrl: fieldValue('baseUrl'),
    };
  }

  function collectPayload() {
    return {
      environment: 'production',
      username: fieldValue('username'),
      password: fieldValue('password'),
      token: fieldValue('token'),
      baseUrl: fieldValue('baseUrl'),
      preset: fieldValue('preset'),
      settings: {
        region: fieldValue('region'),
        universe: fieldValue('universe'),
        delay: numericValue('delay', 1),
        neutralization: fieldValue('neutralization'),
        instrumentType: fieldValue('instrumentType'),
        alphaType: fieldValue('alphaType'),
        decay: numericValue('decay', 0),
        truncation: numericValue('truncation', 0),
        pasteurization: fieldValue('pasteurization'),
        nanHandling: fieldValue('nanHandling'),
        unitHandling: fieldValue('unitHandling'),
        language: fieldValue('language'),
      },
      use_assistant_guidance: checkedValue('useAssistantGuidance'),
      assistant_guidance_min_confidence: numericValue('assistantGuidanceMinConfidence', 0.6),
      assistant_guidance_score_adjustment: checkedValue('assistantGuidanceScoreAdjustment'),
      assistant_guidance_score_min_confidence: numericValue('assistantGuidanceScoreMinConfidence', 0.6),
      strategy_plugins_enabled: checkedValue('strategyPluginsEnabled'),
    };
  }

  function applyPreset(presets) {
    var preset = (presets || {})[fieldValue('preset')];
    if (!preset || !preset.settings) return false;
    var settings = preset.settings;
    [
      'region', 'universe', 'delay', 'neutralization', 'instrumentType',
      'alphaType', 'decay', 'truncation', 'pasteurization', 'nanHandling',
      'unitHandling', 'language',
    ].forEach(function (id) { setControlValue(id, settings[id]); });
    return true;
  }

  function applyConfig(config) {
    var ops = (config || {}).ops || {};
    var budget = ops.budget || {};
    setControlValue('useAssistantGuidance', budget.assistant_guidance_enabled !== false);
    setControlValue('assistantGuidanceScoreAdjustment', budget.assistant_guidance_score_adjustment !== false);
    setControlValue('strategyPluginsEnabled', Boolean(budget.strategy_plugins_enabled));
  }

  window.FormControls = {
    applyConfig: applyConfig,
    applyPreset: applyPreset,
    collectPayload: collectPayload,
    connectionPayload: connectionPayload,
    fieldValue: fieldValue,
    numericValue: numericValue,
    setControlValue: setControlValue,
  };
})();
