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
    el.value = String(value);
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
    var alphaType = fieldValue('alphaType');
    return {
      environment: 'production',
      username: fieldValue('username'),
      password: fieldValue('password'),
      token: fieldValue('token'),
      baseUrl: fieldValue('baseUrl'),
      preset: fieldValue('preset'),
      autoSubmit: checkedValue('autoSubmitToggle'),
      settings: {
        region: fieldValue('region'),
        universe: fieldValue('universe'),
        delay: numericValue('delay', 1),
        neutralization: fieldValue('neutralization'),
        instrumentType: fieldValue('instrumentType'),
        type: alphaType,
        decay: numericValue('decay', 0),
        truncation: numericValue('truncation', 0),
        pasteurization: fieldValue('pasteurization'),
        nanHandling: fieldValue('nanHandling'),
        unitHandling: fieldValue('unitHandling'),
        language: fieldValue('language'),
      },
      syncRange: fieldValue('syncRange'),
      useAssistantGuidance: checkedValue('useAssistantGuidance'),
      assistantGuidanceMinConfidence: numericValue('assistantGuidanceMinConfidence', 0.6),
      assistantGuidanceScoreAdjustment: checkedValue('assistantGuidanceScoreAdjustment'),
      assistantGuidanceScoreMinConfidence: numericValue('assistantGuidanceScoreMinConfidence', 0.6),
      assistantGuidanceScoreMinOutcomeCount: numericValue('assistantGuidanceScoreMinOutcomeCount', 1),
      assistantGuidanceScoreBonusCap: numericValue('assistantGuidanceScoreBonusCap', 4),
      assistantGuidanceScorePenaltyCap: numericValue('assistantGuidanceScorePenaltyCap', 5),
      strategyPluginsEnabled: checkedValue('strategyPluginsEnabled'),
      strategyPluginSpecs: fieldValue('strategyPluginSpecs'),
    };
  }

  function applyPreset(presets) {
    var preset = (presets || {})[fieldValue('preset')];
    if (!preset || !preset.settings) return false;
    var settings = preset.settings;
    [
      'region', 'universe', 'delay', 'neutralization', 'instrumentType',
      'decay', 'truncation', 'pasteurization', 'nanHandling',
      'unitHandling', 'language',
    ].forEach(function (id) { setControlValue(id, settings[id]); });
    setControlValue('alphaType', settings.type || settings.alphaType);
    return true;
  }

  function applyConfig(config) {
    var ops = (config || {}).ops || {};
    var officialApi = ops.official_api || {};
    var settings = ops.settings || {};
    var budget = ops.budget || {};
    var scoring = ops.scoring || {};
    [
      'region', 'universe', 'delay', 'neutralization', 'instrumentType',
      'decay', 'truncation', 'pasteurization', 'nanHandling',
      'unitHandling', 'language',
    ].forEach(function (id) { setControlValue(id, settings[id]); });
    setControlValue('alphaType', settings.type || settings.alphaType);
    setControlValue('environment', (config || {}).environment || 'production');
    setControlValue('baseUrl', officialApi.base_url);
    setControlValue('autoSubmitToggle', Boolean((config || {}).auto_submit));
    setControlValue('syncRange', budget.cloud_sync_range);
    setControlValue('useAssistantGuidance', budget.use_assistant_guidance !== false);
    setControlValue('assistantGuidanceMinConfidence', budget.assistant_guidance_min_confidence);
    setControlValue('assistantGuidanceScoreAdjustment', scoring.assistant_guidance_score_adjustment_enabled !== false);
    setControlValue('assistantGuidanceScoreMinConfidence', scoring.assistant_guidance_score_min_confidence);
    setControlValue('assistantGuidanceScoreMinOutcomeCount', scoring.assistant_guidance_score_min_outcome_count);
    setControlValue('assistantGuidanceScoreBonusCap', scoring.assistant_guidance_score_bonus_cap);
    setControlValue('assistantGuidanceScorePenaltyCap', scoring.assistant_guidance_score_penalty_cap);
    setControlValue('strategyPluginsEnabled', Boolean(budget.strategy_plugins_enabled));
    setControlValue(
      'strategyPluginSpecs',
      Array.isArray(budget.strategy_plugin_specs) ? budget.strategy_plugin_specs.join('\n') : budget.strategy_plugin_specs
    );
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
