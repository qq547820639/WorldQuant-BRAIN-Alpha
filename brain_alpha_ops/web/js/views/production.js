// brain_alpha_ops/web/js/views/production.js
// SSE-based production control — real-time progress without polling.
// Replaces the legacy setInterval polling with EventSource stream.
// IIFE exposes to window namespace.

(function () {
  'use strict';

  var STREAM_TOKEN = "__BRAIN_ALPHA_OPS_STREAM_TOKEN__";
  var $ = window.Utils.$;
  var esc = window.Utils.escapeHtml;
  var Api = window.ApiClient;
  var S = window.AppState;
  var Toast = window.Toast;

  // ------------------------------------------------------------------
  // State
  // ------------------------------------------------------------------
  var _running = false;
  var _jobId = "";
  var _pollTimer = null;     // polling fallback
  var _eventSource = null;   // SSE primary

  // ------------------------------------------------------------------
  // SSE connection
  // ------------------------------------------------------------------
  function connectSSE(jobId) {
    disconnectSSE();

    var url = "/api/stream?job_id=" + encodeURIComponent(jobId) +
              "&stream_token=" + encodeURIComponent(STREAM_TOKEN);

    try {
      _eventSource = new EventSource(url);

      _eventSource.onmessage = function (event) {
        try {
          var data = JSON.parse(event.data);
          handleSSEMessage(data);
        } catch (e) {
          // Ignore malformed SSE messages
        }
      };

      _eventSource.onerror = function () {
        // EventSource auto-reconnects; if persistent, fall back to polling
        if (_eventSource && _eventSource.readyState === EventSource.CLOSED) {
          disconnectSSE();
          if (_running && _jobId) {
            // Fallback: start polling if SSE fails
            if (!_pollTimer) {
              _pollTimer = setInterval(pollJobProgress, 5000);
            }
          }
        }
      };
    } catch (e) {
      // EventSource not supported or failed — fallback to polling
      _eventSource = null;
      if (_running && _jobId && !_pollTimer) {
        _pollTimer = setInterval(pollJobProgress, 5000);
      }
    }
  }

  function disconnectSSE() {
    if (_eventSource) {
      try { _eventSource.close(); } catch (e) { /* ignore */ }
      _eventSource = null;
    }
  }

  // ------------------------------------------------------------------
  // SSE message handler
  // ------------------------------------------------------------------
  function handleSSEMessage(data) {
    if (!data.ok) return;

    // Update state
    S.set("activeJobId", data.job_id || _jobId);
    S.set("isRunning", true);

    // Update live progress
    var progress = data.progress || {};
    S.set("liveProgress", { phase: progress.phase || "", data: progress });

    // Update status display
    var statusEl = $("status");
    if (statusEl) {
      var phaseLabel = progress.phase_label || window.Utils.phaseName(progress.phase);
      var msg = progress.message || "";
      statusEl.textContent = phaseLabel + (msg ? ": " + msg : "");
    }

    // Update progress bar
    var progressBar = $("progressFill");
    if (progressBar && progress.percent != null) {
      progressBar.style.width = Math.min(100, Math.max(0, progress.percent)) + "%";
    }

    if (progress.data && window._app && window._app.renderJobSnapshot) {
      window._app.renderJobSnapshot({
        job_id: data.job_id || _jobId,
        status: data.status || "running",
        progress: progress,
        result: {},
      });
    } else {
      if (typeof window.renderOpsMonitor === "function") {
        window.renderOpsMonitor();
      }
      if (typeof window.renderInsight === "function") {
        window.renderInsight();
      }
    }

    // Check for terminal states
    var status = data.status || "";
    if (status === "completed" || status === "failed" || status === "stopped") {
      onJobComplete(status);
    }
  }

  // ------------------------------------------------------------------
  // Polling fallback (only used when SSE is unavailable)
  // ------------------------------------------------------------------
  async function pollJobProgress() {
    try {
      var d = await Api.get("/api/active_job");
      if (!d.ok || !d.job) return;
      var job = d.job;

      // Emulate SSE message format
      handleSSEMessage({
        ok: true,
        job_id: _jobId,
        status: job.status || "running",
        progress: job.progress || {},
      });

      // Update error display
      if (job.error) {
        var statusEl = $("status");
        if (statusEl) statusEl.textContent += " [错误: " + esc(job.error.slice(0, 80)) + "]";
      }
    } catch (e) {
      // Polling silently fails to avoid noise
    }
  }

  // ------------------------------------------------------------------
  // Job completion handler
  // ------------------------------------------------------------------
  function onJobComplete(status) {
    disconnectSSE();
    if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
    _running = false;
    S.set("isRunning", false);
    updateRunButton();

    var isSuccess = status === "completed";
    Toast.toast(
      "生产任务" + (isSuccess ? "已完成" : "结束") +
      (status === "failed" ? " (失败)" : ""),
      isSuccess ? "success" : "error"
    );

    // Refresh data after completion
    if (typeof window._app === "object" && window._app) {
      if (window._app.renderJobSnapshot && _jobId) {
        Api.get("/api/status?job_id=" + encodeURIComponent(_jobId))
          .then(function (snapshot) { window._app.renderJobSnapshot(snapshot); })
          .catch(function () { /* best-effort snapshot refresh */ });
      }
      if (window._app.loadConfig) window._app.loadConfig();
      if (window._app.loadCheckResults) window._app.loadCheckResults();
      if (window._app.loadCloudSnapshot) window._app.loadCloudSnapshot();
      if (window._app.loadResearchMemory) window._app.loadResearchMemory();
    }
  }

  // ------------------------------------------------------------------
  // UI
  // ------------------------------------------------------------------
  function updateRunButton() {
    var btn = $("controlButton");
    if (!btn) return;
    btn.textContent = _running ? "停止连续生产" : "开始生产搜索";
    btn.className = _running ? "full stop" : "full";
  }

  // ------------------------------------------------------------------
  // Production control — exposed to window for HTML onclick handlers
  // ------------------------------------------------------------------
  window.toggleRun = async function () {
    if (_running) {
      await stopProduction();
      return;
    }
    await startProduction();
  };

  async function startProduction() {
    _running = true;
    S.set("isRunning", true);
    updateRunButton();
    Toast.toast("正在创建生产任务...", "info");

    try {
      var payload = window.collectPayload ? window.collectPayload() : {};
      payload.continuousMode = true;
      var resp = await Api.post("/api/run", payload);
      if (!resp.ok) throw new Error(resp.error || "启动失败");
      _jobId = resp.job_id;
      S.set("activeJobId", _jobId);
      Toast.toast("生产已启动 (job: " + _jobId.slice(0, 8) + ")", "success");

      // Primary: SSE real-time stream
      connectSSE(_jobId);
    } catch (e) {
      _running = false;
      S.set("isRunning", false);
      updateRunButton();
      disconnectSSE();
      Toast.toast("启动失败: " + e.message, "error");
    }
  }

  async function stopProduction() {
    disconnectSSE();
    if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }

    try {
      var resp = await Api.post("/api/stop", { job_id: _jobId });
      if (resp.ok) {
        Toast.toast("生产已停止", "info");
      }
    } catch (e) {
      // Force stop by cancelling job trackers
    }

    _running = false;
    _jobId = "";
    S.set("isRunning", false);
    S.set("activeJobId", "");
    updateRunButton();
  }

  // ------------------------------------------------------------------
  // Init — register state listener for external isRunning changes
  // ------------------------------------------------------------------
  S.onUpdate(function (path) {
    if (path === "isRunning" || (path === "activeJobId" && !S.get("isRunning"))) {
      updateRunButton();
    }
  });

  // Expose
  window.startProduction = startProduction;
  window.stopProduction = stopProduction;
  window.connectSSE = connectSSE;
  window.disconnectSSE = disconnectSSE;

})();
