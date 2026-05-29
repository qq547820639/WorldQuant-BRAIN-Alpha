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

  // ── v4: Inline Validation ──────────────────────────────────────────────

  /**
   * Validate a single field and show/hide error message.
   * @returns {boolean} whether the field is valid
   */
  function validateField(fieldId, rules) {
    var el = $(fieldId);
    if (!el) return true;
    rules = rules || {};

    var value = String(el.value || '').trim();
    var group = el.closest('.form-group');
    if (!group) return true;

    // Remove previous error
    var existingError = group.querySelector('.form-error-message');
    if (existingError) existingError.remove();
    group.classList.remove('has-error', 'has-success');

    var errorMsg = '';

    // Required check
    if (rules.required && !value) {
      errorMsg = (rules.requiredMessage || '此字段为必填项。');
    }

    // Min length check
    if (!errorMsg && rules.minLength && value.length < rules.minLength) {
      errorMsg = '\u81F3\u5C11\u9700\u8981 ' + rules.minLength + ' \u4E2A\u5B57\u7B26\u3002'; // 至少需要 X 个字符
    }

    // Max length check
    if (!errorMsg && rules.maxLength && value.length > rules.maxLength) {
      errorMsg = '\u6700\u591A\u5141\u8BB8 ' + rules.maxLength + ' \u4E2A\u5B57\u7B26\u3002'; // 最多允许 X 个字符
    }

    // Pattern check
    if (!errorMsg && rules.pattern && value) {
      var re = new RegExp(rules.pattern);
      if (!re.test(value)) {
        errorMsg = rules.patternMessage || '\u683C\u5F0F\u4E0D\u6B63\u786E\u3002'; // 格式不正确
      }
    }

    // Number range check
    if (!errorMsg && rules.min !== undefined && value) {
      var num = Number(value);
      if (Number.isFinite(num) && num < rules.min) {
        errorMsg = '\u6700\u5C0F\u503C\u4E3A ' + rules.min + '\u3002'; // 最小值为 X
      }
    }
    if (!errorMsg && rules.max !== undefined && value) {
      var num2 = Number(value);
      if (Number.isFinite(num2) && num2 > rules.max) {
        errorMsg = '\u6700\u5927\u503C\u4E3A ' + rules.max + '\u3002'; // 最大值为 X
      }
    }

    // URL format check
    if (!errorMsg && rules.isUrl && value && !/^https?:\/\/.+/.test(value)) {
      errorMsg = '\u8BF7\u8F93\u5165\u6709\u6548\u7684 URL\uFF0C\u4EE5 http:// \u6216 https:// \u5F00\u5934\u3002'; // 请输入有效的URL
    }

    if (errorMsg) {
      group.classList.add('has-error');
      el.classList.add('is-invalid');
      el.setAttribute('aria-invalid', 'true');
      el.setAttribute('aria-describedby', fieldId + '-error');

      var errorEl = document.createElement('div');
      errorEl.id = fieldId + '-error';
      errorEl.className = 'form-error-message';
      errorEl.setAttribute('role', 'alert');
      var iconEl = document.createElement('span');
      iconEl.className = 'form-error-icon';
      iconEl.setAttribute('aria-hidden', 'true');
      iconEl.textContent = '!';
      errorEl.appendChild(iconEl);
      errorEl.appendChild(document.createTextNode(errorMsg));
      group.appendChild(errorEl);

      return false;
    }

    // Valid
    if (value) {
      group.classList.add('has-success');
    }
    el.classList.remove('is-invalid');
    el.removeAttribute('aria-invalid');
    el.removeAttribute('aria-describedby');
    return true;
  }

  /**
   * Clear validation for a field.
   */
  function clearFieldValidation(fieldId) {
    var el = $(fieldId);
    if (!el) return;
    var group = el.closest('.form-group');
    if (!group) return;
    var existingError = group.querySelector('.form-error-message');
    if (existingError) existingError.remove();
    group.classList.remove('has-error', 'has-success');
    el.classList.remove('is-invalid');
    el.removeAttribute('aria-invalid');
    el.removeAttribute('aria-describedby');
  }

  /**
   * Validate connection form fields.
   */
  function validateConnection() {
    var valid = true;
    clearFieldValidation('username');
    clearFieldValidation('password');
    clearFieldValidation('token');
    valid = validateField('baseUrl', {
      isUrl: true,
      patternMessage: '\u8BF7\u8F93\u5165\u6709\u6548\u7684 API \u5730\u5740\u3002', // 请输入有效的API地址
    }) && valid;
    return valid;
  }

  /**
   * v4: Bind live validation to form fields with debounce.
   */
  function bindFieldValidation(fieldId, rules) {
    var el = $(fieldId);
    if (!el) return;
    var timer = null;

    var handler = function () {
      if (timer) clearTimeout(timer);
      timer = setTimeout(function () {
        validateField(fieldId, rules);
      }, 400);
    };

    el.addEventListener('input', handler);
    el.addEventListener('change', handler);
    el.addEventListener('blur', function () {
      if (timer) clearTimeout(timer);
      validateField(fieldId, rules);
    });

    // Clear validation on focus
    el.addEventListener('focus', function () {
      if (el.classList.contains('is-invalid')) {
        clearFieldValidation(fieldId);
      }
    });
  }

  window.FormControls = {
    applyConfig: applyConfig,
    applyPreset: applyPreset,
    collectPayload: collectPayload,
    connectionPayload: connectionPayload,
    fieldValue: fieldValue,
    numericValue: numericValue,
    setControlValue: setControlValue,
    // v4: Validation
    validateField: validateField,
    clearFieldValidation: clearFieldValidation,
    validateConnection: validateConnection,
    bindFieldValidation: bindFieldValidation,
  };
})();
