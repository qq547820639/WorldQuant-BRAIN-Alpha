// brain_alpha_ops/web/js/utils.js
// Pure utility functions — no DOM, no state.

(function () {
  var Utils = {};

  // DOM shortcuts
  Utils.$ = function (id) { return document.getElementById(id); };

  // HTML escape
  Utils.escapeHtml = function (s) {
    return String(s).replace(/[&<>"']/g, function (ch) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch];
    });
  };

  Utils.escapeAttr = function (s) {
    return Utils.escapeHtml(s).replace(/\\/g, "\\\\").replace(/\n/g, "\\n");
  };

  Utils.jsStringAttr = function (s) {
    return Utils.escapeHtml(JSON.stringify(String(s ?? "")));
  };

  Utils.escapeId = function (s) {
    return String(s).replace(/[^a-zA-Z0-9_-]/g, "_");
  };

  // B3: phaseName — prefer backend phase_label, fallback to hardcoded map
  Utils.phaseName = function (phaseOrProgress) {
    if (typeof phaseOrProgress === "object" && phaseOrProgress && phaseOrProgress.phase_label) {
      return phaseOrProgress.phase_label;
    }
    var phase = typeof phaseOrProgress === "string" ? phaseOrProgress : String(phaseOrProgress || "");
    var map = {
      queued: "排队", auth: "认证", scan: "扫描", merge: "合并",
      startup: "启动", cloud_sync: "云端数据同步", context: "加载上下文",
      production_loop: "循环生产", local_scoring: "本地评分排序",
      candidate_pool: "候选池维护", official_validation: "回测前预检",
      simulation_submit: "提交回测", simulation_wait: "等待回测结果",
      official_deferred: "官方调用延后", official_simulation: "官方回测等待",
      strategy_switch: "自动切换策略", completed: "完成", stopped: "已停止",
      failed: "失败", stopping: "正在停止", checking: "批量检查", submitting: "提交",
    };
    return map[phase] || phase;
  };

  // B2: humanCheckName — prefer backend label_cn
  Utils.humanCheckName = function (nameOrCheck) {
    if (typeof nameOrCheck === "object" && nameOrCheck && nameOrCheck.label_cn) {
      return nameOrCheck.label_cn;
    }
    var name = typeof nameOrCheck === "string" ? nameOrCheck : String(nameOrCheck || "");
    var map = {
      production_gate: "未达提交门禁",
      official_alpha_id: "缺少官方 ID",
      not_failed_locally: "本地状态异常",
      cloud_sync_available: "云端数据未就绪",
      not_submitted_before: "本地已有提交记录",
      cloud_status_not_already_submitted: "云端已提交",
      cloud_self_correlation: "云端相似度过高",
      official_pre_submit_check: "官方预提交检查未过",
      LOW_SHARPE: "低 Sharpe",
      LOW_FITNESS: "低 Fitness",
      LOW_TURNOVER: "低换手率",
      HIGH_TURNOVER: "高换手率",
      CONCENTRATED_WEIGHT: "权重集中",
      SELF_CORRELATION: "自相关过高",
      LOW_SUB_UNIVERSE_SHARPE: "子宇宙低 Sharpe",
    };
    return map[name] || name;
  };

  // Value formatting
  Utils.formatScore = function (v) {
    if (v == null) return "-";
    return Number(v).toFixed(1);
  };

  Utils.formatPct = function (v) {
    if (v == null) return "-";
    return (Number(v) * 100).toFixed(1) + "%";
  };

  Utils.payloadTruthy = function (value) {
    if (typeof value === "boolean") return value;
    if (typeof value === "string") return value.trim().toLowerCase() === "true" || value === "1" || value === "yes" || value === "on";
    return Boolean(value);
  };

  window.Utils = Utils;
})();
