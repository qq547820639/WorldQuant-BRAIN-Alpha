// brain_alpha_ops/web/js/views/detail.js
// Detail modal rendering — candidate, cloud, lifecycle, check details.
// IIFE exposes to window namespace.

(function () {
  'use strict';

  var $ = window.Utils.$;
  var esc = window.Utils.escapeHtml;
  var jsStringAttr = window.Utils.jsStringAttr;
  var formatScore = window.Utils.formatScore;
  var humanCheckName = window.Utils.humanCheckName;
  var statusBadge = window.Table.statusBadge;
  var scoreSpan = window.Table.scoreSpan;

  // ---------- Helpers -------------------------------------------------------

  function fmtVal(val) {
    if (val == null) return '-';
    if (typeof val === 'boolean') return val ? '是' : '否';
    if (typeof val === 'object') return JSON.stringify(val);
    return String(val);
  }

  function formatFieldValue(value, format) {
    if (value == null) return '-';
    switch (format) {
      case 'score': return scoreSpan(value);
      case 'badge': return statusBadge(String(value));
      case 'json': return '<pre class="detail-json">' + esc(JSON.stringify(value, null, 2)) + '</pre>';
      case 'number': {
        var n = Number(value);
        return Number.isFinite(n) ? n.toFixed(Number.isInteger(n) ? 0 : 4) : '-';
      }
      default: return esc(String(value));
    }
  }

  function hasDataObject(obj) {
    return Boolean(obj && typeof obj === 'object' && Object.keys(obj).length);
  }

  function metricValue(candidate, key) {
    var metrics = (candidate || {}).official_metrics || (candidate || {}).metrics || {};
    if (!Object.prototype.hasOwnProperty.call(metrics, key)) return null;
    var n = Number(metrics[key]);
    return Number.isFinite(n) ? n : metrics[key];
  }

  function scorePart(scorecard, key) {
    var section = (scorecard || {})[key] || {};
    return section.score !== undefined && section.score !== null ? section.score : '-';
  }

  function sectionBlock(title, body) {
    return '<div class="detail-section">' +
      '<div class="detail-section-title">' + esc(title) + '</div>' +
      '<div class="detail-section-body">' + body + '</div>' +
      '</div>';
  }

  // ---------- renderFieldTable ----------------------------------------------

  function renderFieldTable(containerId, title, fields) {
    var container = $(containerId);
    if (!container) return;

    var rows = fields.map(function (f) {
      var label = f.label || '';
      var value = formatFieldValue(f.value, f.format || 'text');
      var cls = f.className || '';
      return '<tr>' +
        '<td class="' + cls + ' field-label">' + esc(label) + '</td>' +
        '<td class="' + cls + ' field-value">' + value + '</td>' +
        '</tr>';
    }).join('');

    var html = '<table class="detail-table"><thead><tr><th colspan="2">' + esc(title) + '</th></tr></thead><tbody>' + rows + '</tbody></table>';
    container.innerHTML = html;
  }

  // ---------- renderCandidateDetail -----------------------------------------

  function renderCandidateDetail(candidate) {
    if (!candidate) {
      showEmpty();
      return;
    }

    var titleEl = $('modalTitle');
    if (titleEl) { titleEl.textContent = candidate.alpha_id || '候选详情'; }

    var bodyEl = $('detail');
    if (!bodyEl) return;

    var parts = [];

    // --- 基本信息 ---
    parts.push(renderFieldTableHTML2('基本信息', [
      { label: 'Alpha ID', value: candidate.alpha_id },
      { label: '家族', value: candidate.family },
      { label: '假说', value: candidate.hypothesis },
      { label: '表达式', value: candidate.expression },
      { label: '数据字段', value: (candidate.data_fields || []).join(', ') },
      { label: '算子', value: (candidate.operators || []).join(', ') },
      { label: '来源标签', value: (candidate.source_tags || []).join(', ') },
      { label: '模板来源', value: candidate.template_source || '-' },
      { label: '生命周期', value: candidate.lifecycle_status || '-' },
    ]));

    // --- Scorecard ---
    var sc = candidate.scorecard || {};
    if (hasDataObject(sc) || hasDataObject(candidate.official_metrics)) {
      parts.push(renderScorecardDetail(candidate));
    }

    // --- Scoring Attribution (from scoring API) ---
    if (candidate.alpha_id) {
      parts.push(renderScoringSection(candidate.alpha_id));
    }

    // --- Gate ---
    var gate = candidate.gate || {};
    if (Object.keys(gate).length) {
      parts.push(renderFieldTableHTML2('门禁', [
        { label: '通过', value: gate.passed ? '是' : '否', format: gate.passed ? 'badge' : 'text' },
        { label: '可提交', value: gate.submission_ready ? '是' : '否' },
        { label: '详情', value: gate.details || gate.reason || '-' },
      ]));
    }

    // --- Validation ---
    var v = candidate.validation || {};
    if (Object.keys(v).length) {
      parts.push(renderFieldTableHTML2('校验', [
        { label: 'IS Sharpe', value: v.is_sharpe, format: 'number' },
        { label: 'OOS Sharpe', value: v.oos_sharpe, format: 'number' },
        { label: 'R IC', value: v.r_ic, format: 'number' },
        { label: 'R IC IR', value: v.r_ic_ir, format: 'number' },
        { label: 'Max Drawdown', value: v.max_drawdown, format: 'number' },
        { label: '自相关', value: v.self_correlation, format: 'number' },
        { label: '状态', value: v.status || v.passed != null ? (v.passed ? '通过' : '未通过') : '-' },
      ]));
    }

    // --- 本地质量 ---
    var lq = candidate.local_quality || {};
    if (Object.keys(lq).length) {
      parts.push(renderFieldTableHTML2('本地质量', [
        { label: '排序分', value: lq.rank_score, format: 'score' },
        { label: 'IS Sharpe', value: lq.is_sharpe, format: 'number' },
        { label: 'OOS Sharpe', value: lq.oos_sharpe, format: 'number' },
        { label: 'Fitness', value: lq.fitness, format: 'number' },
        { label: 'Turnover', value: lq.turnover, format: 'number' },
      ]));
    }

    // --- 官方指标 ---
    var om = candidate.official_metrics || {};
    if (Object.keys(om).length) {
      parts.push(renderFieldTableHTML2('官方指标', [
        { label: '官方 Alpha ID', value: candidate.official_alpha_id || '-' },
        { label: 'Sharpe', value: om.sharpe, format: 'number' },
        { label: 'Fitness', value: om.fitness, format: 'number' },
        { label: 'Turnover', value: om.turnover, format: 'number' },
        { label: 'R IC', value: om.r_ic, format: 'number' },
      ]));
    }

    // --- 提交信息 ---
    var sub = candidate.submission || {};
    if (Object.keys(sub).length) {
      parts.push(renderFieldTableHTML2('提交信息', [
        { label: '提交 ID', value: sub.id || sub.submission_id || '-' },
        { label: '状态', value: sub.status || '-' },
        { label: '消息', value: sub.message || sub.reason || '-' },
      ]));
    }

    if (sub.assistant_guidance_digest) {
      var guidanceOutcome = sub.assistant_guidance_outcome || {};
      parts.push(renderFieldTableHTML2('Assistant Guidance', [
        { label: 'Guidance Digest', value: sub.assistant_guidance_digest || '-' },
        { label: 'Source', value: sub.assistant_guidance_source || '-' },
        { label: 'Confidence', value: sub.assistant_guidance_confidence, format: 'number' },
        { label: 'Outcome Status', value: sub.assistant_guidance_outcome_status || '-' },
        { label: 'Outcome Count', value: guidanceOutcome.count || sub.assistant_guidance_outcome_count || 0, format: 'number' },
        { label: 'Outcome Success Rate', value: guidanceOutcome.success_rate || sub.assistant_guidance_outcome_success_rate || 0, format: 'number' },
        { label: 'Outcome Avg Score', value: guidanceOutcome.avg_score || sub.assistant_guidance_outcome_avg_score || 0, format: 'number' },
        { label: 'Outcome Avg Sharpe', value: guidanceOutcome.avg_sharpe || sub.assistant_guidance_outcome_avg_sharpe || 0, format: 'number' },
      ]));
    }

    if (candidate._detail_source_kind) {
      parts.push(renderFieldTableHTML2('状态来源', [
        { label: '来源状态栏', value: candidate._detail_source_kind },
        { label: '槽位', value: candidate.slot || '-' },
        { label: '记录时间', value: candidate.timestamp || candidate.created_at || '-' },
      ]));
    }

    bodyEl.innerHTML = parts.join('');
    showModal();
  }

  // ---------- renderCloudDetail ---------------------------------------------

  function renderCloudDetail(row) {
    if (!row) {
      showEmpty();
      return;
    }

    // Accept element or data object
    var data = row;
    if (row instanceof HTMLElement) {
      var raw = row.getAttribute('data-row');
      if (raw) {
        try { data = JSON.parse(raw); } catch (e) { data = {}; }
      }
    }

    var titleEl = $('modalTitle');
    if (titleEl) { titleEl.textContent = data.alpha_id || data.id || '云端 Alpha 详情'; }

    var bodyEl = $('detail');
    if (!bodyEl) return;

    var parts = [];
    parts.push(renderFieldTableHTML2('云端 Alpha', [
      { label: 'Alpha ID', value: data.alpha_id || data.id },
      { label: '状态', value: data.status },
      { label: 'Sharpe', value: data.sharpe, format: 'number' },
      { label: 'Fitness', value: data.fitness, format: 'number' },
      { label: 'Turnover', value: data.turnover, format: 'number' },
      { label: '自相关', value: data.self_correlation, format: 'number' },
      { label: '子宇宙 Sharpe', value: data.sub_universe_sharpe, format: 'number' },
      { label: 'R IC', value: data.r_ic, format: 'number' },
      { label: '权重集中度', value: data.weight_concentration, format: 'number' },
      { label: '最近日期', value: data.latest_date || data.date || '-' },
      { label: '表达式', value: data.expression || '-' },
      { label: '设置 ID', value: data.settings_id || '-' },
    ]));

    bodyEl.innerHTML = parts.join('');
    showModal();
  }

  function renderAssistantContextDetail(pack) {
    if (!pack) {
      showEmpty();
      return;
    }

    var titleEl = $('modalTitle');
    if (titleEl) { titleEl.textContent = 'LLM Context Pack'; }

    var bodyEl = $('detail');
    if (!bodyEl) return;

    var prompt = String(pack.prompt || '');
    var rawJson = JSON.stringify(pack, null, 2);
    var runConfig = pack.run_config || {};
    var latest = pack.latest_result || {};
    var memory = pack.research_memory || {};
    var focus = pack.generation_focus || {};
    var cloud = pack.cloud_alphas || {};
    var guardrails = pack.risk_controls || {};
    var actions = Array.isArray(pack.recommended_next_actions) ? pack.recommended_next_actions : [];

    var yesNo = function (value) { return value ? 'Yes' : 'No'; };
    var parts = [];
    parts.push(renderFieldTableHTML2('Context Overview', [
      { label: 'Schema', value: pack.schema_version || '-' },
      { label: 'Generated At', value: pack.generated_at || '-' },
      { label: 'Source', value: pack.source || '-' },
      { label: 'Storage Dir', value: pack.storage_dir || '-' },
      { label: 'Environment', value: runConfig.environment || '-' },
      { label: 'Auto Submit', value: yesNo(runConfig.auto_submit), format: runConfig.auto_submit ? 'badge' : 'text' },
    ]));

    parts.push(renderFieldTableHTML2('Latest Result', [
      { label: 'Status', value: latest.status || '-' },
      { label: 'Candidates', value: latest.candidate_count || 0, format: 'number' },
      { label: 'Pending Backtests', value: latest.pending_backtest_count || 0, format: 'number' },
      { label: 'Passed', value: latest.passed_count || 0, format: 'number' },
      { label: 'Active Backtests', value: latest.active_backtest_count || 0, format: 'number' },
      { label: 'Strategy Profile', value: (latest.strategy_profile || {}).name || '-' },
    ]));

    parts.push(renderFieldTableHTML2('Research Memory', [
      { label: 'Samples', value: memory.total_candidates || 0, format: 'number' },
      { label: 'Fields', value: (focus.fields || []).slice(0, 5).join(', ') || '-' },
      { label: 'Operators', value: (focus.operators || []).slice(0, 5).join(', ') || '-' },
      { label: 'Windows', value: (focus.windows || []).slice(0, 5).join(', ') || '-' },
      { label: 'Failure Patterns', value: (focus.failure_patterns || []).slice(0, 3).map(function (row) {
        return String(row.reason || '-') + ' x' + String(row.count || 0);
      }).join(' | ') || '-' },
    ]));

    parts.push(renderFieldTableHTML2('Cloud Risk', [
      { label: 'Cloud Count', value: cloud.count || 0, format: 'number' },
      { label: 'Submitted', value: cloud.submitted_count || 0, format: 'number' },
      { label: 'Passed Unsubmitted', value: cloud.passed_unsubmitted_count || 0, format: 'number' },
      { label: 'Failed Unsubmitted', value: cloud.failed_unsubmitted_count || 0, format: 'number' },
      { label: 'Stale', value: yesNo(cloud.is_stale), format: cloud.is_stale ? 'badge' : 'text' },
      { label: 'Cloud Source', value: cloud.source || '-' },
    ]));

    parts.push(renderFieldTableHTML2('Guardrails', [
      { label: 'Live API Default Allowed', value: yesNo(guardrails.live_api_default_allowed), format: guardrails.live_api_default_allowed ? 'badge' : 'text' },
      { label: 'Submit Requires Confirmation', value: yesNo(guardrails.submit_requires_confirmation), format: guardrails.submit_requires_confirmation ? 'badge' : 'text' },
      { label: 'Cloud Sync Required', value: yesNo(guardrails.cloud_sync_required), format: guardrails.cloud_sync_required ? 'badge' : 'text' },
      { label: 'Max Expression Similarity', value: guardrails.max_expression_similarity, format: 'number' },
      { label: 'Block Micro Variants', value: yesNo(guardrails.block_micro_variants) },
    ]));

    if (actions.length) {
      parts.push(renderFieldTableHTML2('Recommended Actions', actions.map(function (item, index) {
        return { label: 'Action ' + (index + 1), value: item };
      })));
    }

    parts.push(sectionBlock('Prompt', '<div class="copy-box">' + esc(prompt || '-') + '</div>' +
      '<div class="action-row">' +
      '<button class="secondary small" onclick="copyText(' + jsStringAttr(prompt) + ')">Copy Prompt</button>' +
      '<button class="secondary small" onclick="copyText(' + jsStringAttr(rawJson) + ')">Copy JSON</button>' +
      '</div>'));

    parts.push(sectionBlock('Raw JSON', '<div class="copy-box">' + esc(rawJson) + '</div>'));

    bodyEl.innerHTML = parts.join('');
    showModal();
  }

  function renderAssistantGuidanceDetail(snapshot) {
    if (!snapshot) {
      showEmpty();
      return;
    }

    var titleEl = $('modalTitle');
    if (titleEl) { titleEl.textContent = 'Assistant Guidance'; }

    var bodyEl = $('detail');
    if (!bodyEl) return;

    var guidance = snapshot.guidance || {};
    var guidanceOutcome = guidance.historical_outcome || {};
    var outcomes = snapshot.outcomes || {};
    var scoringPolicy = snapshot.scoring_policy || {};
    var scoreEligibility = snapshot.score_adjustment_eligibility || {};
    var history = Array.isArray(snapshot.history) ? snapshot.history : [];
    var rawJson = JSON.stringify(snapshot, null, 2);
    var listText = function (items) {
      return Array.isArray(items) && items.length ? items.join(', ') : '-';
    };
    var yesNo = function (value) { return value ? 'Yes' : 'No'; };
    var parts = [];

    parts.push(renderFieldTableHTML2('Guidance Snapshot', [
      { label: 'Mode', value: snapshot.preview_only ? 'Preview Only' : 'Persisted Snapshot' },
      { label: 'Enabled', value: yesNo(snapshot.enabled), format: snapshot.enabled ? 'badge' : 'text' },
      { label: 'Configured Min Confidence', value: snapshot.configured_min_confidence, format: 'number' },
      { label: 'Effective Min Confidence', value: snapshot.min_confidence, format: 'number' },
      { label: 'Score Adjustment', value: scoringPolicy.enabled === false ? 'Off' : 'On' },
      { label: 'Score Min Confidence', value: scoringPolicy.min_confidence, format: 'number' },
      { label: 'Score Min Outcomes', value: scoringPolicy.min_outcome_count, format: 'number' },
      { label: 'History Count', value: snapshot.history_count || 0, format: 'number' },
      { label: 'History Limit', value: snapshot.history_limit || 0, format: 'number' },
    ]));

    parts.push(renderFieldTableHTML2('Score Adjustment Eligibility', [
      { label: 'Eligible', value: yesNo(scoreEligibility.eligible), format: scoreEligibility.eligible ? 'badge' : 'text' },
      { label: 'Reason', value: scoreEligibility.reason || '-' },
      { label: 'Guidance Digest', value: scoreEligibility.guidance_digest || '-' },
      { label: 'Confidence', value: scoreEligibility.confidence, format: 'number' },
      { label: 'Outcome Count', value: scoreEligibility.outcome_count || 0, format: 'number' },
      { label: 'Outcome Status', value: scoreEligibility.outcome_status || '-' },
      { label: 'Applies To', value: scoringPolicy.applies_to || '-' },
    ]));

    parts.push(renderFieldTableHTML2('Latest Usable Guidance', [
      { label: 'Usable', value: yesNo(guidance.usable), format: guidance.usable ? 'badge' : 'text' },
      { label: 'Reason', value: guidance.reason || '-' },
      { label: 'Source', value: guidance.source || guidance.persistence_source || '-' },
      { label: 'Guidance Digest', value: guidance.guidance_digest || '-' },
      { label: 'Persisted At', value: guidance.persisted_at || '-' },
      { label: 'Confidence', value: guidance.confidence, format: 'number' },
      { label: 'Sample Size', value: guidance.sample_size || 0, format: 'number' },
      { label: 'Outcome Status', value: guidance.historical_outcome_status || '-' },
      { label: 'Outcome Count', value: guidanceOutcome.count || 0, format: 'number' },
      { label: 'Outcome Success Rate', value: guidanceOutcome.success_rate || 0, format: 'number' },
      { label: 'Outcome Avg Score', value: guidanceOutcome.avg_score || 0, format: 'number' },
    ]));

    parts.push(renderFieldTableHTML2('Observed Outcomes', [
      { label: 'Guided Candidates', value: outcomes.count || 0, format: 'number' },
      { label: 'Success Count', value: outcomes.success_count || 0, format: 'number' },
      { label: 'Success Rate', value: outcomes.success_rate || 0, format: 'number' },
      { label: 'Average Score', value: outcomes.avg_score || 0, format: 'number' },
      { label: 'Average Sharpe', value: outcomes.avg_sharpe || 0, format: 'number' },
      { label: 'Average Fitness', value: outcomes.avg_fitness || 0, format: 'number' },
    ]));

    parts.push(renderFieldTableHTML2('Generation Bias', [
      { label: 'Fields', value: listText(guidance.top_fields) },
      { label: 'Operators', value: listText(guidance.top_operators) },
      { label: 'Windows', value: listText(guidance.preferred_windows) },
      { label: 'Field Combinations', value: listText((guidance.field_combinations || []).map(function (combo) {
        return Array.isArray(combo) ? combo.join('+') : String(combo);
      })) },
      { label: 'Risk Flags', value: listText(guidance.risk_flags) },
      { label: 'Summary', value: guidance.summary || '-' },
    ]));

    if (Array.isArray(guidance.recommended_next_actions) && guidance.recommended_next_actions.length) {
      parts.push(renderFieldTableHTML2('Recommended Actions', guidance.recommended_next_actions.map(function (item, index) {
        return { label: 'Action ' + (index + 1), value: item };
      })));
    }

    if (history.length) {
      var rows = history.slice(0, 12).map(function (item) {
        item = item || {};
        var saved = item.assistant_guidance || {};
        var ready = item.usable !== false && item.meets_min_confidence !== false && item.has_generator_bias !== false && item.has_healthy_outcome !== false;
        var fields = listText(item.top_fields || saved.top_fields);
        var ops = listText(item.top_operators || saved.top_operators);
        var windows = listText(item.preferred_windows || saved.preferred_windows);
        var outcome = item.outcomes || {};
        var outcomeText = outcome.count ? (' | generated ' + outcome.count + ' | success ' + String(outcome.success_rate || 0)) : '';
        var outcomeStatus = item.historical_outcome_status && item.historical_outcome_status !== 'unknown' ? (' | outcome ' + item.historical_outcome_status) : '';
        var scoringText = item.score_adjustment_eligible ? ' | scoring eligible' : (' | scoring ' + String(item.score_adjustment_reason || 'not eligible'));
        return '<div class="kv">' +
          '<div><b>' + esc(item.timestamp || '-') + '</b><span class="muted"> ' + esc(item.source || '-') + '</span>' +
          '<div class="muted">conf ' + esc(String(item.confidence == null ? '-' : item.confidence)) +
          ' | digest ' + esc(item.guidance_digest || '-') + outcomeText + outcomeStatus +
          esc(scoringText) +
          ' | fields ' + esc(fields) + ' | ops ' + esc(ops) + ' | windows ' + esc(windows) + '</div>' +
          '<div>' + esc(item.summary || saved.summary || item.reason || '-') + '</div></div>' +
          '<div class="action-row">' +
          '<button class="secondary small" onclick="useSavedAssistantGuidance(' + jsStringAttr(String(item.history_index)) + ')">' + (ready ? 'Use' : 'Load') + '</button>' +
          '<button class="secondary small" onclick="copyText(' + jsStringAttr(JSON.stringify(saved, null, 2)) + ')">Copy</button>' +
          '</div>' +
          '</div>';
      }).join('');
      parts.push(sectionBlock('Recent Saved Guidance', rows));
    }

    parts.push(sectionBlock('Raw JSON', '<div class="copy-box">' + esc(rawJson) + '</div>' +
      '<div class="action-row"><button class="secondary small" onclick="copyText(' + jsStringAttr(rawJson) + ')">Copy JSON</button></div>'));

    bodyEl.innerHTML = parts.join('');
    showModal();
  }

  // ---------- renderLifecycleDetail -----------------------------------------

  function renderLifecycleDetail(row) {
    if (!row) {
      showEmpty();
      return;
    }

    // Accept element or data object
    var data = row;
    if (row instanceof HTMLElement) {
      var raw = row.getAttribute('data-row');
      if (raw) {
        try { data = JSON.parse(raw); } catch (e) { data = {}; }
      }
    }

    var titleEl = $('modalTitle');
    if (titleEl) { titleEl.textContent = data.alpha_id || '生命周期详情'; }

    var bodyEl = $('detail');
    if (!bodyEl) return;

    var parts = [];
    parts.push(renderFieldTableHTML2('生命周期记录', [
      { label: 'Alpha ID', value: data.alpha_id || '-' },
      { label: '运行 ID', value: data.run_id || '-' },
      { label: '阶段', value: data.stage || '-' },
      { label: '状态', value: data.status, format: 'badge' },
      { label: '分类', value: data.status_category || '-' },
      { label: '消息', value: data.message || '-' },
      { label: '时间戳', value: data.timestamp || '-' },
    ]));

    if (data.detail || data.meta) {
      parts.push(renderFieldTableHTML2('附加信息', [
        { label: '详情', value: data.detail || data.meta, format: 'json' },
      ]));
    }

    bodyEl.innerHTML = parts.join('');
    showModal();
  }

  // ---------- renderCheckDetail ---------------------------------------------

  function renderCheckDetail(result) {
    if (!result) {
      showEmpty();
      return;
    }

    var titleEl = $('modalTitle');
    if (titleEl) { titleEl.textContent = result.alpha_id || '检查详情'; }

    var bodyEl = $('detail');
    if (!bodyEl) return;

    var parts = [];
    parts.push(renderFieldTableHTML2('检查结果', [
      { label: 'Alpha ID', value: result.alpha_id || '-' },
      { label: '通过', value: result.passed ? '通过' : '未通过', format: 'badge' },
      { label: '新鲜度', value: result.is_stale === false ? '有效' : result.is_stale === true ? '过期' : '-' },
      { label: '检查时间', value: result.checked_at || '-' },
      { label: '消息', value: result.message || '-' },
    ]));

    var checks = result.checks || [];
    if (checks.length) {
      var checkFields = checks.map(function (c) {
        return { label: humanCheckName(c.name), value: c.passed ? '通过' : '未通过', format: 'badge' };
      });
      parts.push(renderFieldTableHTML2('逐项检查', checkFields));
    }

    bodyEl.innerHTML = parts.join('');
    showModal();
  }

  function renderScorecardDetail(candidate) {
    candidate = candidate || {};
    var sc = candidate.scorecard || {};
    var isMetricScorecard = sc.schema_version === 'ui-metric-scorecard-v1';
    var calibration = sc.calibration || {};
    var guidanceAdjustment = sc.assistant_guidance_adjustment || {};
    var fields = [
      { label: isMetricScorecard ? '本地规则分' : '总分', value: sc.total_score !== undefined ? sc.total_score : candidate.score, format: 'score' },
      { label: '评分来源', value: sc.score_basis || '-' },
      { label: '决策带', value: sc.decision_band || '-' },
      { label: '本地排序分', value: sc.local_rank_score, format: 'score' },
      { label: 'Base Local Rank', value: sc.base_local_rank_score, format: 'score' },
      { label: 'Guidance Adjustment', value: guidanceAdjustment.adjustment || 0, format: 'number' },
      { label: 'Guidance Outcome', value: guidanceAdjustment.outcome_status || '-' },
      { label: '说明', value: calibration.purpose || (isMetricScorecard ? '用于排序参考，不是官方 BRAIN 总评分。' : '-') },
      { label: '先验分', value: scorePart(sc, 'prior'), format: 'score' },
      { label: '实证分', value: scorePart(sc, 'empirical'), format: 'score' },
      { label: '提交清单分', value: scorePart(sc, 'submission_checklist'), format: 'score' },
      { label: 'Sharpe', value: metricValue(candidate, 'sharpe'), format: 'number' },
      { label: 'Fitness', value: metricValue(candidate, 'fitness'), format: 'number' },
      { label: 'Turnover', value: metricValue(candidate, 'turnover'), format: 'number' },
      { label: 'Returns', value: metricValue(candidate, 'returns'), format: 'number' },
      { label: 'Drawdown', value: metricValue(candidate, 'drawdown'), format: 'number' },
      { label: 'Sub-Universe Sharpe', value: metricValue(candidate, 'sub_universe_sharpe'), format: 'number' },
      { label: 'Correlation', value: metricValue(candidate, 'correlation'), format: 'number' },
      { label: 'Pass/Fail', value: ((candidate.official_metrics || {}).pass_fail || (candidate.metrics || {}).pass_fail || '-') },
    ];
    var html = renderFieldTableHTML2('评分卡', fields);

    if (guidanceAdjustment.source && guidanceAdjustment.source !== 'none') {
      html += renderFieldTableHTML2('Guidance Score Adjustment', [
        { label: 'Guidance Digest', value: guidanceAdjustment.guidance_digest || '-' },
        { label: 'Outcome Status', value: guidanceAdjustment.outcome_status || '-' },
        { label: 'Outcome Count', value: guidanceAdjustment.outcome_count || 0, format: 'number' },
        { label: 'Success Rate', value: guidanceAdjustment.success_rate || 0, format: 'number' },
        { label: 'Avg Score', value: guidanceAdjustment.avg_score || 0, format: 'number' },
        { label: 'Confidence', value: guidanceAdjustment.confidence || 0, format: 'number' },
        { label: 'Min Confidence', value: (guidanceAdjustment.configuration || {}).min_confidence || 0, format: 'number' },
        { label: 'Min Outcome Count', value: (guidanceAdjustment.configuration || {}).min_outcome_count || 0, format: 'number' },
        { label: 'Applied To Total', value: guidanceAdjustment.applied_to_total ? 'Yes' : 'No' },
        { label: 'Reason', value: guidanceAdjustment.reason || '-' },
      ]);
    }

    var empiricalItems = ((sc.empirical || {}).items) || [];
    if (empiricalItems.length) {
      html += renderFieldTableHTML2('评分依据', empiricalItems.map(function (item) {
        var actual = item.actual === undefined || item.actual === null ? '-' : item.actual;
        var score = item.score !== undefined ? item.score : item.points !== undefined && item.passed ? item.points : 0;
        return {
          label: item.name || '-',
          value: String(actual) + ' | ' + (item.passed ? 'pass' : 'fail') + ' | +' + score,
        };
      }));
    }

    var dims = (sc.prior || {}).dimensions || {};
    if (Object.keys(dims).length) {
      html += renderFieldTableHTML2('先验维度', Object.keys(dims).map(function (key) {
        return { label: key, value: dims[key], format: 'score' };
      }));
    }
    return html;
  }

  // ---------- Internal helpers ----------------------------------------------

  function renderFieldTableHTML(title, fields) {
    var rows = fields.map(function (f) {
      return '<tr>' +
        '<td class="field-label">' + esc(f.label) + '</td>' +
        '<td class="field-value">' + formatFieldValue(f.value, f.format || 'text') + '</td>' +
        '</tr>';
    }).join('');
    return '<table class="detail-table"><thead><tr><th colspan="2">' + esc(title) + '</th></tr></thead><tbody>' + rows + '</tbody></table>';
  }

  // Renders as section-wrapped table
  function renderFieldTableHTML2(title, fields) {
    return sectionBlock(title, renderFieldTableHTML(title, fields));
  }

  function showModal() {
    var modal = $('detailModal');
    if (modal) { modal.classList.remove('hidden'); }
  }

  function showEmpty() {
    var bodyEl = $('detail');
    if (bodyEl) { bodyEl.innerHTML = '<p style="color:var(--muted);text-align:center;padding:20px">暂无详情。</p>'; }
    showModal();
  }

  function closeDetailModal() {
    var modal = $('detailModal');
    if (modal) { modal.classList.add('hidden'); }
  }

  // ---------- Scoring Attribution & Redline ---------------------------------

  /**
   * Async section that loads scoring attribution from the API.
   * Shows a loading placeholder, then replaces with the result.
   */
  function renderScoringSection(alphaId) {
    var containerId = 'scoringSection_' + alphaId;
    var html = '<div id="' + containerId + '" class="detail-section">' +
      '<div style="color:var(--muted);font-size:13px">评分归因加载中...</div></div>';
    // Load async
    setTimeout(function () {
      var el = document.getElementById(containerId);
      if (!el) return;
      try {
        window.ApiClient.post('/api/scoring/attribution', { alpha_id: alphaId }).then(function (data) {
          if (data && data.attribution) {
            el.innerHTML = renderAttributionTreeHTML(data);
          } else {
            el.innerHTML = '<div style="color:var(--muted);font-size:13px">暂无评分归因数据</div>';
          }
        }).catch(function () {
          el.innerHTML = '';
        });
      } catch (e) {
        el.innerHTML = '';
      }
    }, 10);
    return html;
  }

  function renderAttributionTreeHTML(result) {
    var hg = result.hard_gates || [];
    var sg = result.soft_gates || [];
    var tf = result.top_failures || [];
    var hints = result.improvement_hints || [];

    var body = '';

    // Gate summary
    var gatePassed = hg.every(function (g) { return g.passed; });
    var softWarn = sg.filter(function (g) { return !g.passed; });
    body += '<div style="margin-bottom:8px">' +
      '<span style="color:' + (gatePassed ? 'var(--good)' : 'var(--bad)') + ';font-weight:600">' +
      (gatePassed ? '✓ 硬门禁通过' : '✗ 硬门禁未通过') + '</span>' +
      (softWarn.length ? ' <span style="color:var(--warn);margin-left:8px">⚠ ' + softWarn.length + ' 项软门禁警告</span>' : '') +
      '</div>';

    // Top failures
    if (tf.length) {
      body += '<div style="margin-bottom:8px;font-size:13px;color:var(--bad)">主要失败项: ';
      body += tf.map(function (f) { return f.name + ' (' + f.reason + ')'; }).join(', ');
      body += '</div>';
    }

    // Improvement hints
    if (hints.length) {
      body += '<div style="margin-bottom:8px;font-size:12px;color:var(--muted)">';
      body += hints.map(function (h) { return '💡 ' + h; }).join('<br>');
      body += '</div>';
    }

    // Simple tree
    if (result.attribution) {
      body += renderAttributionNode(result.attribution);
    }

    return body;
  }

  function renderAttributionNode(node) {
    if (!node) return '';
    var indent = 'margin-left:16px;';
    var sign = node.contribution >= 0 ? '' : '';
    var color = node.score > 0.7 ? 'var(--good)' : node.score > 0.4 ? 'var(--warn)' : 'var(--bad)';
    var html = '<div style="font-size:13px;' + (node.weight < 1.0 ? indent : '') + '">' +
      '<span style="color:' + color + ';font-weight:600">' + node.name + '</span>' +
      ' <span style="color:var(--muted);font-size:12px">得分=' + (node.score || 0).toFixed(2) +
      ' 权重=' + (node.weight || 0).toFixed(2) +
      ' 贡献=' + (node.contribution || 0).toFixed(2) + '</span>' +
      (node.explanation ? ' <span style="color:var(--muted);font-size:11px">' + node.explanation + '</span>' : '') +
      '</div>';
    if (node.children && node.children.length) {
      for (var i = 0; i < node.children.length; i++) {
        html += renderAttributionNode(node.children[i]);
      }
    }
    return html;
  }

  /**
   * Fetch and display the redline compliance report.
   */
  function loadRedlineReport() {
    try {
      window.ApiClient.get('/api/redline/report').then(function (data) {
        window.AppState.set('redlineReport', data);
        var el = document.getElementById('redlineSummary');
        if (el && data) {
          var ok = data.ok;
          var vc = data.violations || 0;
          el.innerHTML = ok
            ? '<span style="color:var(--good)">✓ 六大红线验证通过</span>'
            : '<span style="color:var(--bad)">✗ ' + vc + ' 条红线违规</span>';
        }
      }).catch(function () {});
    } catch (e) {}
  }

  // ---------- Public API ----------------------------------------------------

  window.DetailView = {
    renderFieldTable: renderFieldTable,
    renderCandidateDetail: renderCandidateDetail,
    renderCloudDetail: renderCloudDetail,
    renderLifecycleDetail: renderLifecycleDetail,
    renderAssistantContextDetail: renderAssistantContextDetail,
    renderAssistantGuidanceDetail: renderAssistantGuidanceDetail,
    renderCheckDetail: renderCheckDetail,
    closeDetailModal: closeDetailModal,
  };

  // Backward-compat global alias — called from inline onclick handlers
  window.closeDetailModal = closeDetailModal;
  window.viewCandidateDetail = renderCandidateDetail;
  window.viewCloudDetail = renderCloudDetail;
  window.viewLifecycleDetail = renderLifecycleDetail;
  window.viewAssistantContextDetail = renderAssistantContextDetail;
  window.viewAssistantGuidanceDetail = renderAssistantGuidanceDetail;
  window.viewCheckDetail = renderCheckDetail;
  window.loadRedlineReport = loadRedlineReport;
})();
