from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import json
import os
import urllib.request

import pytest

from brain_alpha_ops import web
from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.repository import ResearchRepository
from brain_alpha_ops.research.safety import SubmissionLedger
from brain_alpha_ops.tasks import JobStore
from brain_alpha_ops.web import _load_html, anti_overfit_snapshot, assistant_context_snapshot, assistant_cross_review_payload, assistant_guidance_snapshot, assistant_request_snapshot, assistant_response_guidance_payload, assistant_response_parse_payload, cloud_alpha_snapshot, config_from_payload, generate_candidates_payload, passed_candidates_from_payload, public_run_config, research_memory_snapshot, research_observability_snapshot, rolling_validation_snapshot, save_assistant_guidance_payload, sqlite_expression_lookup_payload, sqlite_index_snapshot, sqlite_record_lookup_payload
from brain_alpha_ops.web_routes import GET_ROUTES, POST_ROUTES, route_for
from scripts.check_frontend_syntax import check_scripts


def test_web_html_contains_chinese_console():
    HTML = _load_html()
    assert "官方回测槽位" in HTML
    assert "系统策略" in HTML
    assert "停止连续生产" in HTML
    assert "backtestPanel" in HTML
    assert "insightCardHtml" in HTML
    assert "insightGroupHtml" in HTML
    assert "生产流程" in HTML
    assert "辅助追踪" in HTML
    assert "switchView" in HTML
    assert "configuredBacktestSlotLimit" in HTML
    assert "syncButton" in HTML
    assert "setSyncBusy" in HTML
    assert "setSubmitBusy" in HTML
    assert "switchTab" not in HTML
    assert 'class="tabs"' not in HTML
    assert "data-tab" not in HTML
    assert "达标" in HTML
    assert "可提交" in HTML
    assert "不达标" in HTML
    assert "数据统计" in HTML
    assert "sync_status" in HTML
    assert "快速检查" in HTML
    assert "全部检查" in HTML
    assert "排序分" in HTML
    assert "checkMode" in HTML
    assert "checkButton" in HTML
    assert "提交勾选" in HTML
    assert "自动提交可提交" not in HTML
    assert "check_batch" in HTML
    assert "submit_batch" in HTML
    assert "detailModal" in HTML
    assert "checkProgressFill" in HTML
    assert "cloudSyncMeta" in HTML
    assert "monitorCloudMeta" in HTML
    assert "cloudStatsPanel" in HTML
    assert "renderCloudStatsPanel" in HTML
    assert "renderResearchMemoryPanel" in HTML
    assert "stats-dashboard" in HTML
    assert "checkProgressMeta" in HTML
    assert "isSubmittedCloudStatus" in HTML
    assert "isCloudFailedAlpha" in HTML
    assert "cloudPassedCandidates" in HTML
    assert "detailedSyncStatusCode" in HTML
    assert "contextScopeText" in HTML
    assert "checkFailureSummary" in HTML
    assert "priorBreakdown" in HTML
    assert "状态码" not in HTML
    assert "预计剩余" in HTML
    assert "下次刷新" not in HTML
    assert "倒计时" in HTML
    assert "CHECK_STALE_MS" in HTML
    assert "autoSubmitToggle" in HTML
    assert "Instrument Type" in HTML
    assert "Truncation" in HTML
    assert "controlButton" in HTML
    assert "payload.guided = true" in HTML
    assert "resumeProductionFromCheckpoint" in HTML
    assert "runButton" not in HTML
    assert "复制当前最佳 Alpha" not in HTML
    assert "快速检查选中" not in HTML
    assert "运行、同步和三槽回测监控已固定在右侧顶部" not in HTML
    assert "waitForJob" in HTML
    assert "slotTarget" in HTML
    assert "openBacktestSlot" in HTML
    assert "slotCountdownText" in HTML
    assert "WAITING_CAPACITY" in HTML
    assert "WAITING_SUBMIT" in HTML
    assert "CONTEXT_READY" in HTML
    assert "回测前预检" in HTML
    assert "官方容量等待" in HTML
    assert "/api/config" in HTML
    assert "/api/active_job" in HTML
    assert "/api/cloud_alphas" in HTML
    assert "/api/research_memory" in HTML
    assert "/api/research_knowledge" in HTML
    assert "/api/research_observability" in HTML
    assert "/api/prompt_runs" in HTML
    assert "/api/sqlite_indexes" in HTML
    assert "/api/sqlite_expression_lookup" in HTML
    assert "/api/sqlite_record_lookup" in HTML
    assert "/api/rolling_validation" in HTML
    assert "/api/assistant_context" in HTML
    assert "/api/assistant_guidance" in HTML
    assert "/api/assistant_request" in HTML
    assert "loadCloudSnapshot" in HTML
    assert "loadResearchMemory" in HTML
    assert "loadResearchKnowledge" in HTML
    assert "loadResearchObservability" in HTML
    assert "loadPromptRuns" in HTML
    assert "loadSqliteIndexes" in HTML
    assert "renderResearchKnowledgePanel" in HTML
    assert "renderPromptRunLedgerPanel" in HTML
    assert "renderSqliteIndexPanel" in HTML
    assert "renderRobustnessPanel" in HTML
    assert "runSqliteExpressionLookup" in HTML
    assert "runSqliteRecordLookup" in HTML
    assert "buildRobustnessSnapshot" in HTML
    assert "runAntiOverfitForCandidate" in HTML
    assert "runRollingValidationForCandidate" in HTML
    assert "openSqliteLookupDetail" in HTML
    assert "updateSqliteLookupDetailControls" in HTML
    assert "copySqliteLookupJson" in HTML
    assert "openRobustnessDetail" in HTML
    assert "runRobustnessBatchForVisible" in HTML
    assert "applyRobustnessResultToCandidate" in HTML
    assert "candidateMatchesId" in HTML
    assert "runAntiOverfitForInput" in HTML
    assert "runRollingValidationForInput" in HTML
    assert "renderSimpleDetailTable" in HTML
    assert "renderResearchObservabilityPanel" in HTML
    assert "Generation Guidance" in HTML
    assert "currentObservabilityGenerationGuidance" in HTML
    assert "Official Guard" in HTML
    assert "currentObservabilityOfficialCallGuard" in HTML
    assert "snapshot.official_call_guard" in HTML
    assert "Guard blocked" in HTML
    assert "observabilityConfirmationMessage" in HTML
    assert "Preflight unavailable:" in HTML
    assert "Partial Errors" in HTML
    assert "research_observability" in HTML
    assert "loadAssistantContext" in HTML
    assert "loadAssistantGuidance" in HTML
    assert "useAssistantGuidance" in HTML
    assert "strategyPluginsEnabled" in HTML
    assert "strategyPluginSpecs" in HTML
    assert "assistantGuidanceScoreMinConfidence" in HTML
    assert "assistantGuidanceScoreMinOutcomeCount" in HTML
    assert "useOfflineAssistantDraft" in HTML
    assert "assistantUseDraftButton" in HTML
    assert "saveOfflineAssistantDraftGuidance" in HTML
    assert "assistantSaveDraftButton" in HTML
    assert "useLatestAssistantGuidance" in HTML
    assert "useSavedAssistantGuidance" in HTML
    assert "assistantUseLatestButton" in HTML
    assert "offline_draft" in HTML
    assert "previewAssistantGuidance" in HTML
    assert "assistantPreviewGuidanceButton" in HTML
    assert "/api/assistant_response/guidance" in HTML
    assert "saveAssistantGuidance" in HTML
    assert "assistantSaveGuidanceButton" in HTML
    assert "copyAssistantRequest" in HTML
    assert "renderAssistantContextDetail" in HTML


def test_api_client_maps_submit_preflight_error_codes():
    js = Path("brain_alpha_ops/web/js/api-client.js").read_text(encoding="utf-8")
    html = _load_html()
    for code in (
        "SUBMIT_NON_PRODUCTION_CANDIDATE",
        "SUBMIT_NOT_READY",
        "SUBMIT_FAILED_CANDIDATE",
        "SUBMIT_DUPLICATE_OFFICIAL_ID",
        "SUBMIT_DUPLICATE_EXPRESSION",
        "SUBMIT_CLOUD_SYNC_REQUIRED",
        "SUBMIT_CLOUD_SYNC_STALE",
        "SUBMIT_CLOUD_ALREADY_SUBMITTED",
        "SUBMIT_OBSERVABILITY_CONFIRMATION_REQUIRED",
        "SUBMIT_BATCH_ERROR",
    ):
        assert code in js
        assert code in html
    assert "renderAssistantGuidanceDetail" in html
    assert "applyCloudSnapshot" in html
    assert "research_memory" in html
    assert "云端已提交" in html
    assert "云端不达标" in html
    assert '<option value="production" selected>' in html
    assert '<option value="3d" selected>近 3 天</option>' in html


def test_web_inline_scripts_pass_syntax_check():
    result = check_scripts(Path(__file__).resolve().parents[1] / "brain_alpha_ops" / "web" / "index.html")

    assert result["ok"] is True
    assert result["checked"] >= 1
    assert result["failures"] == []


def test_web_inline_html_matches_modular_js_sources():
    import importlib.util

    build_path = Path(__file__).resolve().parents[1] / "brain_alpha_ops" / "web" / "build_inline.py"
    spec = importlib.util.spec_from_file_location("web_build_inline", build_path)
    build_inline = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(build_inline)

    result = build_inline.check(Path(__file__).resolve().parents[1] / "brain_alpha_ops" / "web" / "index.html")

    assert result["ok"] is True
    assert result["replaced"] >= 13
    assert "js/app.js" in result["sources"]


def test_research_observability_cards_escape_dynamic_text():
    app_js = (Path(__file__).resolve().parents[1] / "brain_alpha_ops" / "web" / "js" / "app.js").read_text(encoding="utf-8")
    start = app_js.index("function renderResearchObservabilityPanel")
    end = app_js.index("  function researchMemoryRows", start)
    render_block = app_js[start:end]

    assert "'<div class=\"stat-label\">' + esc(row.name || '')" in render_block
    assert "'<div class=\"stat-value\">' + esc(value)" in render_block
    assert "'<div class=\"stat-note\">' + esc(row.note || '')" in render_block


def test_additional_stats_panels_escape_dynamic_text():
    app_js = (Path(__file__).resolve().parents[1] / "brain_alpha_ops" / "web" / "js" / "app.js").read_text(encoding="utf-8")
    start = app_js.index("function renderStatsPanelForView")
    end = app_js.index("  function renderModuleActions", start)
    render_block = app_js[start:end]

    assert "function renderResearchKnowledgePanel" in app_js
    assert "function renderPromptRunLedgerPanel" in app_js
    assert "function renderSqliteIndexPanel" in app_js
    assert "function renderRobustnessPanel" in app_js
    assert "function renderSimpleDetailTable" in app_js
    assert "openSqliteLookupDetail" in app_js
    assert "updateSqliteLookupDetailControls" in app_js
    assert "copySqliteLookupJson" in app_js
    assert "function filteredLookupRows" in app_js
    assert "function sortedLookupRows" in app_js
    assert "openRobustnessDetail" in app_js
    assert "function applyRobustnessResultToCandidate" in app_js
    assert "function candidateMatchesId" in app_js
    assert "'<div class=\"stat-label\">' + esc(row.name || '')" in render_block
    assert "'<div class=\"stat-value\">' + esc(value)" in render_block
    assert "'<div class=\"stat-note\">' + esc(row.note || '')" in render_block


def test_sqlite_lookup_detail_controls_escape_and_reuse_lookup_state():
    app_js = (Path(__file__).resolve().parents[1] / "brain_alpha_ops" / "web" / "js" / "app.js").read_text(encoding="utf-8")
    start = app_js.index("window.openSqliteLookupDetail = function")
    end = app_js.index("  window.openRobustnessDetail", start)
    block = app_js[start:end]

    assert "escapeAttr(filterText)" in block
    assert "renderSimpleDetailTable(expressionRows.slice(0, 20)" in block
    assert "renderSimpleDetailTable(recordRows.slice(0, 30)" in block
    assert "S.merge('currentResult.sqlite_lookup'" in block
    assert "window.copyText(JSON.stringify(currentSqliteLookup(), null, 2))" in block


def test_robustness_results_write_back_to_candidate_submissions():
    app_js = (Path(__file__).resolve().parents[1] / "brain_alpha_ops" / "web" / "js" / "app.js").read_text(encoding="utf-8")
    start = app_js.index("function applyRobustnessResultToCandidate")
    end = app_js.index("  async function loadAssistantContext", start)
    block = app_js[start:end]

    assert "submission.anti_overfit_report = result.anti_overfit.anti_overfit_report" in block
    assert "submission.rolling_validation_report = result.rolling_validation.rolling_validation_report" in block
    assert "S.set('currentResult.candidates', candidateUpdate.rows)" in block
    assert "S.set('currentResult.passed_candidates', passedUpdate.rows)" in block
    assert "candidateIdentity(candidate || {})" in block


def test_stats_cards_sanitize_dynamic_class_and_action_handlers():
    app_js = (Path(__file__).resolve().parents[1] / "brain_alpha_ops" / "web" / "js" / "app.js").read_text(encoding="utf-8")
    start = app_js.index("function safeClassTokens")
    end = app_js.index("  function renderModuleActions", start)
    render_block = app_js[start:end]

    assert "function safeClassTokens" in render_block
    assert "return allowed[String(handler || '')] ? String(handler) : ''" in render_block
    assert "var cls = safeClassTokens(row.cls || (index <= 2 ? 'primary' : ''))" in render_block
    assert "var handler = safeStatActionHandler(action.handler)" in render_block
    assert "onclick=\"' + action.handler + '\"" not in render_block
    assert "var cls = row.cls ||" not in render_block


def test_charts_handle_empty_and_large_datasets():
    charts_js = (Path(__file__).resolve().parents[1] / "brain_alpha_ops" / "web" / "js" / "views" / "charts.js").read_text(encoding="utf-8")

    assert "MAX_CHART_POINTS = 300" in charts_js
    assert "function renderEmptyChart" in charts_js
    assert "function sampleRows" in charts_js
    assert "function candidateRows" in charts_js
    assert "sampleRows(candidateRows(candidates)" in charts_js
    assert "sharpes = [0]" not in charts_js


def test_view_model_helpers_are_modular_and_inlined():
    root = Path(__file__).resolve().parents[1]
    view_model_js = (root / "brain_alpha_ops" / "web" / "js" / "view-model.js").read_text(encoding="utf-8")
    app_js = (root / "brain_alpha_ops" / "web" / "js" / "app.js").read_text(encoding="utf-8")
    html = _load_html()

    assert "window.ViewModel" in view_model_js
    assert "uniqueBacktestSlots" in view_model_js
    assert "var VM = window.ViewModel" in app_js
    assert "function uniqueBacktestSlots" not in app_js
    assert "// brain_alpha_ops/web/js/view-model.js" in html


def test_web_inline_script_syntax_check_reports_failures(tmp_path):
    html = tmp_path / "bad.html"
    html.write_text("<html><body><script>function broken( {</script></body></html>", encoding="utf-8")

    result = check_scripts(html)

    assert result["ok"] is False
    assert result["checked"] == 1
    assert result["failures"][0]["html_line"] == 1


def test_web_config_from_payload():
    config = config_from_payload(
        {
            "settings": {"region": "USA", "universe": "TOP1000", "delay": 1, "neutralization": "INDUSTRY"},
            "candidates": 12,
            "validations": 8,
            "simulations": 5,
            "concurrentSimulations": 3,
            "poolSize": 10,
            "backtestBatchSize": 3,
            "minPriorValidation": 62,
            "minPriorSimulation": 72,
            "continuousMode": True,
            "cyclePauseSeconds": 1,
            "officialRetryPauseSeconds": 2,
            "syncRange": "3d",
            "requireCloudSync": True,
            "cycles": 10,
            "useAssistantGuidance": False,
            "assistantGuidanceMinConfidence": 0.85,
            "strategyPluginsEnabled": True,
            "strategyPluginSpecs": "brain_alpha_ops.examples.strategy_plugin:ConservativeMeanReversionPlugin",
            "assistantGuidanceScoreAdjustment": False,
            "assistantGuidanceScoreMinConfidence": 0.75,
            "assistantGuidanceScoreMinOutcomeCount": 2,
            "assistantGuidanceScoreBonusCap": 2.5,
            "assistantGuidanceScorePenaltyCap": 3.5,
        }
    )
    assert config.settings.universe == "TOP1000"
    assert config.budget.max_candidates_per_cycle == 12
    assert config.budget.max_official_simulations_per_cycle == 5
    assert config.budget.max_official_concurrent_simulations == 3
    assert config.budget.retained_alpha_pool_size == 10
    assert config.budget.official_backtest_batch_size == 3
    assert config.budget.min_prior_score_for_official_validation == 62
    assert config.budget.min_prior_score_for_official_simulation == 72
    assert config.budget.run_forever is True
    assert config.budget.cycle_pause_seconds == 1
    assert config.budget.official_retry_pause_seconds == 2
    assert config.budget.cloud_sync_range == "3d"
    assert config.budget.require_cloud_sync is True
    assert config.budget.max_cycles == 10
    assert config.budget.use_assistant_guidance is False
    assert config.budget.assistant_guidance_min_confidence == 0.85
    assert config.budget.strategy_plugins_enabled is True
    assert config.budget.strategy_plugin_specs == [
        "brain_alpha_ops.examples.strategy_plugin:ConservativeMeanReversionPlugin"
    ]
    assert config.scoring.assistant_guidance_score_adjustment_enabled is False
    assert config.scoring.assistant_guidance_score_min_confidence == 0.75
    assert config.scoring.assistant_guidance_score_min_outcome_count == 2
    assert config.scoring.assistant_guidance_score_bonus_cap == 2.5
    assert config.scoring.assistant_guidance_score_penalty_cap == 3.5


def test_web_config_from_payload_rejects_invalid_numbers():
    with pytest.raises(ValueError, match="candidates must be an integer"):
        config_from_payload({"candidates": "many"})

    with pytest.raises(ValueError, match="settings.truncation must be finite"):
        config_from_payload({"settings": {"truncation": "NaN"}})

    with pytest.raises(ValueError, match="cyclePauseSeconds must be >= 0.0"):
        config_from_payload({"cyclePauseSeconds": -1})


def test_web_config_from_payload_clamps_large_numeric_limits():
    config = config_from_payload(
        {
            "candidates": web._MAX_CANDIDATES + 100,
            "simulations": web._MAX_SIMULATIONS + 100,
            "cyclePauseSeconds": web._MAX_CYCLE_PAUSE_SECONDS + 100,
        }
    )

    assert config.budget.max_candidates_per_cycle == web._MAX_CANDIDATES
    assert config.budget.max_official_simulations_per_cycle == web._MAX_SIMULATIONS
    assert config.budget.cycle_pause_seconds == web._MAX_CYCLE_PAUSE_SECONDS


def test_public_config_redacts_credentials():
    config = public_run_config()
    assert config["credentials"]["username"] == ""
    assert config["credentials"]["password"] == ""
    assert config["credentials"]["token"] == ""


def test_web_routes_define_session_policy_and_known_paths():
    assert route_for("GET", "/api/health").requires_session is False
    assert route_for("GET", "/").category == "html"
    assert route_for("POST", "/api/run").requires_session is True
    assert route_for("GET", "/missing") is None
    assert "/api/assistant_request" in GET_ROUTES
    assert "/api/research_knowledge" in GET_ROUTES
    assert "/api/prompt_runs" in GET_ROUTES
    assert "/api/sqlite_indexes" in GET_ROUTES
    assert "/api/sqlite_expression_lookup" in GET_ROUTES
    assert "/api/sqlite_record_lookup" in GET_ROUTES
    assert "/api/anti_overfit" in GET_ROUTES
    assert "/api/rolling_validation" in GET_ROUTES
    assert "/api/assistant_cross_review" in POST_ROUTES
    assert "/api/submit_batch" in POST_ROUTES


def test_official_context_save_writes_cache_metadata(monkeypatch, tmp_path):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path)
    config.ops.official_api.context_cache_ttl_seconds = 123
    monkeypatch.setattr(web, "load_run_config", lambda *args, **kwargs: config)

    web._save_official_context_json("official_fields.json", [{"id": "close"}, {"name": "volume"}])

    metadata_path = tmp_path / "official_fields.meta.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    counts = web._official_context_file_counts()

    assert metadata["schema_version"] == "official_context_cache_metadata.v1"
    assert metadata["filename"] == "official_fields.json"
    assert metadata["source"] == "official_api"
    assert metadata["ttl_seconds"] == 123
    assert metadata["record_count"] == 2
    assert metadata["complete"] is True
    assert metadata["sha256"]
    assert counts["context_cache_metadata"]["official_fields.json"]["sha256"] == metadata["sha256"]
    assert counts["context_cache_metadata"]["official_fields.json"]["is_stale"] is False
    assert counts["context_cache_manifest"]["schema_version"] == "official_context_cache_manifest.v1"
    assert counts["context_cache_manifest"]["sha256"]
    assert counts["context_cache_manifest"]["record_counts"]["official_fields.json"] == 2


def test_web_uses_durable_job_stores():
    assert isinstance(web.JOBS, JobStore)
    assert isinstance(web.SYNC_JOBS, JobStore)
    assert isinstance(web.CHECK_JOBS, JobStore)
    assert web.TASK_EXECUTOR.__class__.__name__ == "ThreadTaskExecutor"
    assert web.JOBS.persistence_path.name == "jobs_production.json"
    assert web.SYNC_JOBS.persistence_path.name == "jobs_sync.json"
    assert web.CHECK_JOBS.persistence_path.name == "jobs_check.json"


def test_run_job_failure_records_error_context(monkeypatch, tmp_path):
    original_jobs = web.JOBS
    web.JOBS = JobStore(tmp_path / "jobs.json")
    job_id = web.JOBS.create()

    def boom(_run_config, **_kwargs):
        raise RuntimeError("secret-token-123 failed")

    monkeypatch.setattr(web, "run_config_from_payload", lambda payload: RunConfig(environment="mock"))
    monkeypatch.setattr(web, "run_pipeline_from_config", boom)
    try:
        web.run_job(job_id, {})
        job = web.JOBS.get(job_id)
    finally:
        web.JOBS = original_jobs

    assert job["status"] == "failed"
    assert "secret-token-123" not in job["error"]
    context = job["progress"]["error_context"]
    assert context["schema_version"] == "observability.v1"
    assert context["job_id"] == job_id
    assert context["phase"] == "run_job"
    assert context["error_code"] == "RUN_JOB_FAILED"
    assert "secret-token-123" not in context["error"]
    assert context["error_type"] == "RuntimeError"
    assert context["error_category"] == "internal"
    assert context["retryable"] is False


def test_safe_error_payload_classifies_rate_limit():
    payload = web.safe_error_payload(
        BrainAPIError("HTTP 429: rate limit", status_code=429, retry_after=5),
        error_code="SYNC_ERROR",
    )

    assert payload["ok"] is False
    assert payload["error_code"] == "SYNC_ERROR"
    assert payload["error_category"] == "rate_limit"
    assert payload["retryable"] is True
    assert payload["status_code"] == 429
    assert payload["retry_after"] == 5


def test_web_error_payload_preserves_endpoint_code_and_classification():
    payload = web._web_error(ValueError("invalid request body"), "RUN_ERROR")

    assert payload["ok"] is False
    assert payload["error_code"] == "RUN_ERROR"
    assert payload["error_category"] == "validation"
    assert payload["retryable"] is False
    assert payload["error_type"] == "ValueError"
    assert payload["redacted_message"] == payload["error"]


@pytest.mark.skipif(os.getenv("CI") == "true", reason="skipping live server test in CI environment")
def test_web_smoke_test_server_exercises_session_lifecycle():
    port = web.find_free_port(start=8876)

    result = web.smoke_test_server(port=port)

    assert result["ok"] is True
    assert result["config_ok"] is True
    assert result["url"].startswith(f"http://127.0.0.1:{port}")


def test_api_rejects_query_string_csrf_for_regular_endpoints():
    session_id, csrf_token = web._create_session()
    try:
        assert web._validate_session(session_id, csrf_token) is True
        assert web._validate_session(session_id, "bad-token") is False
        assert web._validate_stream_session(session_id, csrf_token) is False
    finally:
        web._expire_session(session_id)


def test_stream_uses_separate_session_token():
    session_id, csrf_token = web._create_session()
    try:
        stream_token = web._stream_token_for_session(session_id)
        assert stream_token
        assert stream_token != csrf_token
        assert web._validate_stream_session(session_id, stream_token) is True
        assert web._validate_stream_session(session_id, csrf_token) is False
    finally:
        web._expire_session(session_id)


@pytest.mark.skipif(os.getenv("CI") == "true", reason="skipping live server test in CI environment")
def test_web_responses_include_security_headers():
    port = web.find_free_port(start=8976)
    url = web.serve(port=port, open_browser=False)
    try:
        root_response = urllib.request.urlopen(url, timeout=5)
        assert root_response.headers.get("X-Content-Type-Options") == "nosniff"
        assert root_response.headers.get("X-Frame-Options") == "DENY"
        assert root_response.headers.get("Referrer-Policy") == "no-referrer"
        assert "frame-ancestors 'none'" in root_response.headers.get("Content-Security-Policy", "")
    finally:
        web.shutdown_server()


def test_remote_bind_requires_explicit_allow_remote():
    port = web.find_free_port(start=9076, host="127.0.0.1")

    with pytest.raises(ValueError, match="allow_remote"):
        web.serve(port=port, host="0.0.0.0", open_browser=False)


def test_batch_check_targets_all_passed_candidates():
    rows = passed_candidates_from_payload(
        {
            "candidates": [
                {"alpha_id": "a1", "gate": {"submission_ready": True}},
                {"alpha_id": "a2", "gate": {"submission_ready": False}},
                {"alpha_id": "a3", "lifecycle_status": "submission_ready"},
            ]
        }
    )
    assert [row["alpha_id"] for row in rows] == ["a1", "a3"]


def test_cloud_snapshot_classifies_persisted_rows():
    with TemporaryDirectory() as tmp:
        storage = Path(tmp) / "data"
        storage.mkdir()
        (storage / "cloud_alphas.jsonl").write_text(
            "\n".join(
                [
                    '{"id":"mock_cloud_alpha_001","status":"SUBMITTED","metrics":{"pass_fail":"PASS"}}',
                    '{"id":"real_active","status":"ACTIVE","metrics":{"pass_fail":"PASS"}}',
                    '{"id":"real_passed","status":"UNSUBMITTED","metrics":{"pass_fail":"PASS"}}',
                    '{"id":"real_failed","status":"UNSUBMITTED","metrics":{"pass_fail":"FAIL"}}',
                    '{"id":"real_failed","status":"UNSUBMITTED","metrics":{"pass_fail":"FAIL","failure_reason":"Low Sharpe"},"timestamp":"z"}',
                ]
            ),
            encoding="utf-8",
        )
        original = web.load_run_config
        web.load_run_config = lambda: SimpleNamespace(
            ops=SimpleNamespace(
                storage_dir=str(storage),
                official_api=SimpleNamespace(cache_dir=str(storage / "api_cache")),
            )
        )
        try:
            snapshot = cloud_alpha_snapshot()
        finally:
            web.load_run_config = original

        summary = snapshot["summary"]
        assert summary["count"] == 3
        assert summary["submitted_count"] == 1
        assert summary["passed_unsubmitted_count"] == 1
        assert summary["failed_unsubmitted_count"] == 1
        assert {row["id"] for row in snapshot["alphas"]} == {"real_active", "real_passed", "real_failed"}


def test_cloud_status_uses_expression_canonical_key():
    candidate = {"expression": "rank(ts_delta(close, 20)) + rank(ts_mean(volume, 10))"}
    cloud_rows = [
        {
            "id": "cloud_same",
            "status": "UNSUBMITTED",
            "expression": "rank(ts_mean(volume, 10)) + rank(ts_delta(close, 20))",
        }
    ]

    status = web.cloud_status_for(candidate, cloud_rows)

    assert status["id"] == "cloud_same"
    assert status["match"] == "expression"


def test_check_candidate_availability_uses_canonical_duplicate_records(tmp_path):
    ledger = SubmissionLedger(str(tmp_path))
    candidate = Candidate(
        alpha_id="a1",
        expression="rank(ts_delta(close, 20)) + rank(ts_mean(volume, 10))",
        family="Momentum",
        hypothesis="canonical duplicate",
        official_alpha_id="official_1",
        official_metrics={
            "sharpe": 1.8,
            "fitness": 1.2,
            "turnover": 0.2,
            "correlation": 0.2,
            "weight_concentration": 0.02,
            "pass_fail": "PASS",
        },
        gate={"submission_ready": True, "failed_reasons": []},
        lifecycle_status="submission_ready",
    )
    ledger.record(candidate, {"status": "SUBMITTED"}, mode="manual")
    candidate_payload = candidate.to_dict()
    candidate_payload["official_alpha_id"] = "official_2"
    candidate_payload["expression"] = " rank ( ts_mean ( volume , 10 ) ) + rank ( ts_delta ( close , 20 ) ) "
    api = SimpleNamespace(check_alpha=lambda alpha_id: {"status": "PASSED"})

    result = web.check_candidate_availability(candidate_payload, "quick", api, ledger, [], "")

    duplicate_check = next(item for item in result["checks"] if item["name"] == "not_submitted_before")
    assert duplicate_check["passed"] is False


def test_check_candidate_availability_includes_observability_preflight(tmp_path):
    ledger = SubmissionLedger(str(tmp_path))
    candidate = Candidate(
        alpha_id="a1",
        expression="rank(ts_delta(close, 20))",
        family="Momentum",
        hypothesis="observable submit",
        official_alpha_id="official_1",
        official_metrics={"pass_fail": "PASS"},
        gate={"submission_ready": True, "failed_reasons": []},
        lifecycle_status="submission_ready",
    ).to_dict()
    api = SimpleNamespace(check_alpha=lambda alpha_id: {"status": "PASSED"})
    advisory = {
        "ok": True,
        "schema_version": "submission_observability_preflight.v1",
        "risk_level": "blocked",
        "health_flags": ["rate_limit_pressure"],
        "blocking_flags": ["rate_limit_pressure"],
        "warning_flags": ["rate_limit_pressure"],
        "actions": ["Pause official calls."],
        "requires_confirmation": True,
    }

    result = web.check_candidate_availability(
        candidate,
        "quick",
        api,
        ledger,
        [],
        "",
        observability_preflight=advisory,
    )

    assert result["submittable"] is True
    assert result["observability_preflight"]["requires_confirmation"] is True
    assert result["observability_preflight"]["blocking_flags"] == ["rate_limit_pressure"]


def test_observability_submission_preflight_includes_official_call_guard(monkeypatch, tmp_path):
    storage = tmp_path / "data"
    storage.mkdir()
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(storage)
    repo = ResearchRepository(str(storage))
    repo.save_lifecycle_record(
        "run_1",
        {
            "alpha_id": "dup_candidate",
            "stage": "observability_duplicate_blocked",
            "status": "observability_duplicate_blocked",
            "note": "official_validation",
            "family": "Momentum",
            "score": 95,
            "expression": "rank(ts_delta(close, 20))",
            "gate": {
                "status": "OBSERVABILITY_DUPLICATE_EXPRESSION_BLOCKED",
                "failed_reasons": ["observability duplicate expression history blocked official call before official_validation"],
            },
        },
    )
    monkeypatch.setattr(web, "load_run_config", lambda: config)

    advisory = web.observability_submission_preflight(str(storage), limit=100, top_n=5)

    assert advisory["ok"] is True
    assert advisory["official_call_guard"]["blocked_count"] == 1
    assert advisory["official_call_guard"]["validation_blocked_count"] == 1
    assert advisory["official_call_guard"]["recent_blocks"][0]["alpha_id"] == "dup_candidate"


def test_observability_submission_preflight_failure_requires_confirmation(monkeypatch, tmp_path):
    def fail_snapshot(*args, **kwargs):
        raise RuntimeError("observability down token=SECRET123")

    monkeypatch.setattr(web, "build_research_observability_snapshot", fail_snapshot)

    advisory = web.observability_submission_preflight(str(tmp_path), limit=100, top_n=5)

    assert advisory["ok"] is False
    assert advisory["requires_confirmation"] is True
    assert advisory["blocking_flags"] == ["observability_preflight_unavailable"]
    assert "SECRET123" not in advisory["error"]
    assert advisory["error"]


def test_submit_candidate_reports_duplicate_expression_code(monkeypatch, tmp_path):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path)
    config.ops.budget.require_cloud_sync = False
    expression = "rank(ts_delta(close, 20))"
    existing = Candidate(
        alpha_id="old",
        expression=expression,
        family="Momentum",
        hypothesis="already submitted",
        official_alpha_id="official_old",
        official_metrics={"pass_fail": "PASS"},
        gate={"submission_ready": True},
        lifecycle_status="submission_ready",
    )
    SubmissionLedger(str(tmp_path)).record(existing, {"status": "SUBMITTED"}, mode="manual")
    candidate = Candidate(
        alpha_id="new",
        expression=expression,
        family="Momentum",
        hypothesis="duplicate expression",
        official_alpha_id="official_new",
        official_metrics={"pass_fail": "PASS"},
        gate={"submission_ready": True, "failed_reasons": []},
        lifecycle_status="submission_ready",
    ).to_dict()

    monkeypatch.setattr(web, "run_config_from_payload", lambda payload: config)

    result = web.submit_candidate({"candidate": candidate})

    assert result["ok"] is False
    assert result["error_code"] == "SUBMIT_DUPLICATE_EXPRESSION"
    assert result["error_category"] == "conflict"
    assert "action" in result


def test_submission_preflight_reports_stale_cloud_code(monkeypatch, tmp_path):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path)
    config.ops.budget.require_cloud_sync = True
    candidate = Candidate(
        alpha_id="a1",
        expression="rank(ts_delta(close, 20))",
        family="Momentum",
        hypothesis="stale cloud",
        official_alpha_id="official_1",
        official_metrics={"pass_fail": "PASS"},
        gate={"submission_ready": True, "failed_reasons": []},
        lifecycle_status="submission_ready",
    ).to_dict()

    monkeypatch.setattr(
        web,
        "cloud_alpha_snapshot",
        lambda limit=2000: {"alphas": [{"id": "other", "status": "UNSUBMITTED"}], "summary": {"is_stale": True}},
    )

    result = web.submission_preflight_advisory(candidate, config)

    assert result["ok"] is False
    assert result["error_code"] == "SUBMIT_CLOUD_SYNC_STALE"
    assert result["error_category"] == "conflict"


def test_submit_candidate_requires_observability_confirmation(monkeypatch, tmp_path):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path)
    config.ops.budget.require_cloud_sync = False
    candidate = Candidate(
        alpha_id="a1",
        expression="rank(ts_delta(close, 20))",
        family="Momentum",
        hypothesis="blocked observability",
        official_alpha_id="official_1",
        official_metrics={"pass_fail": "PASS"},
        gate={"submission_ready": True, "failed_reasons": []},
        lifecycle_status="submission_ready",
    ).to_dict()
    advisory = {
        "ok": True,
        "schema_version": "submission_observability_preflight.v1",
        "risk_level": "blocked",
        "health_flags": ["rate_limit_pressure"],
        "blocking_flags": ["rate_limit_pressure"],
        "warning_flags": ["rate_limit_pressure"],
        "actions": ["Pause official calls."],
        "requires_confirmation": True,
    }
    submitted = {"called": 0}

    class FakeApi:
        def authenticate(self):
            return {"ok": True}

        def submit_alpha(self, alpha_id, expression, settings):
            submitted["called"] += 1
            return {"status": "SUBMITTED", "alpha_id": alpha_id}

    monkeypatch.setattr(web, "run_config_from_payload", lambda payload: config)
    monkeypatch.setattr(web, "cloud_alpha_snapshot", lambda limit=2000: {"alphas": [], "summary": {"is_stale": False}})
    monkeypatch.setattr(web, "api_from_run_config", lambda run_config: FakeApi())
    monkeypatch.setattr(web, "observability_submission_preflight", lambda storage_dir: advisory)

    blocked = web.submit_candidate({"candidate": candidate})
    confirmed = web.submit_candidate({"candidate": candidate, "confirm_observability_risk": True})

    assert blocked["ok"] is False
    assert blocked["error_code"] == "SUBMIT_OBSERVABILITY_CONFIRMATION_REQUIRED"
    assert blocked["observability_preflight"]["blocking_flags"] == ["rate_limit_pressure"]
    assert confirmed["ok"] is True
    assert submitted["called"] == 1


def test_submit_candidate_requires_confirmation_when_observability_preflight_fails(monkeypatch, tmp_path):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path)
    config.ops.budget.require_cloud_sync = False
    candidate = Candidate(
        alpha_id="a1",
        expression="rank(ts_delta(close, 20))",
        family="Momentum",
        hypothesis="preflight unavailable",
        official_alpha_id="official_1",
        official_metrics={"pass_fail": "PASS"},
        gate={"submission_ready": True, "failed_reasons": []},
        lifecycle_status="submission_ready",
    ).to_dict()
    advisory = {
        "ok": False,
        "schema_version": "submission_observability_preflight.v1",
        "risk_level": "unknown",
        "health_flags": ["observability_preflight_unavailable"],
        "blocking_flags": ["observability_preflight_unavailable"],
        "warning_flags": ["observability_preflight_unavailable"],
        "actions": ["Review local observability errors before submission or confirm the risk explicitly."],
        "requires_confirmation": True,
        "error": "observability down",
    }
    submitted = {"called": 0}

    class FakeApi:
        def authenticate(self):
            return {"ok": True}

        def submit_alpha(self, alpha_id, expression, settings):
            submitted["called"] += 1
            return {"status": "SUBMITTED", "alpha_id": alpha_id}

    monkeypatch.setattr(web, "run_config_from_payload", lambda payload: config)
    monkeypatch.setattr(web, "cloud_alpha_snapshot", lambda limit=2000: {"alphas": [], "summary": {"is_stale": False}})
    monkeypatch.setattr(web, "api_from_run_config", lambda run_config: FakeApi())
    monkeypatch.setattr(web, "observability_submission_preflight", lambda storage_dir: advisory)

    blocked = web.submit_candidate({"candidate": candidate})
    confirmed = web.submit_candidate({"candidate": candidate, "confirm_observability_risk": True})

    assert blocked["ok"] is False
    assert blocked["error_code"] == "SUBMIT_OBSERVABILITY_CONFIRMATION_REQUIRED"
    assert blocked["observability_preflight"]["blocking_flags"] == ["observability_preflight_unavailable"]
    assert confirmed["ok"] is True
    assert submitted["called"] == 1


def test_submit_batch_requires_observability_confirmation(monkeypatch, tmp_path):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path)
    candidate = Candidate(
        alpha_id="a1",
        expression="rank(ts_delta(close, 20))",
        family="Momentum",
        hypothesis="batch blocked observability",
        official_alpha_id="official_1",
        official_metrics={"pass_fail": "PASS"},
        gate={"submission_ready": True, "failed_reasons": []},
        lifecycle_status="submission_ready",
    ).to_dict()
    advisory = {
        "ok": True,
        "schema_version": "submission_observability_preflight.v1",
        "risk_level": "blocked",
        "health_flags": ["backtest_failure_rate_elevated"],
        "blocking_flags": ["backtest_failure_rate_elevated"],
        "warning_flags": ["backtest_failure_rate_elevated"],
        "actions": ["Fix failure modes."],
        "requires_confirmation": True,
    }

    monkeypatch.setattr(web, "run_config_from_payload", lambda payload: config)
    monkeypatch.setattr(web, "observability_submission_preflight", lambda storage_dir: advisory)

    result = web.submit_batch({"alpha_ids": ["a1"], "submit_candidates": [candidate]})

    assert result["ok"] is False
    assert result["error_code"] == "SUBMIT_OBSERVABILITY_CONFIRMATION_REQUIRED"
    assert result["observability_preflight"]["blocking_flags"] == ["backtest_failure_rate_elevated"]


def test_submit_batch_requires_confirmation_when_observability_preflight_fails(monkeypatch, tmp_path):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path)
    candidate = Candidate(
        alpha_id="a1",
        expression="rank(ts_delta(close, 20))",
        family="Momentum",
        hypothesis="batch preflight unavailable",
        official_alpha_id="official_1",
        official_metrics={"pass_fail": "PASS"},
        gate={"submission_ready": True, "failed_reasons": []},
        lifecycle_status="submission_ready",
    ).to_dict()
    advisory = {
        "ok": False,
        "schema_version": "submission_observability_preflight.v1",
        "risk_level": "unknown",
        "health_flags": ["observability_preflight_unavailable"],
        "blocking_flags": ["observability_preflight_unavailable"],
        "warning_flags": ["observability_preflight_unavailable"],
        "actions": ["Review local observability errors before submission or confirm the risk explicitly."],
        "requires_confirmation": True,
        "error": "observability down",
    }

    monkeypatch.setattr(web, "run_config_from_payload", lambda payload: config)
    monkeypatch.setattr(web, "observability_submission_preflight", lambda storage_dir: advisory)

    result = web.submit_batch({"alpha_ids": ["a1"], "submit_candidates": [candidate]})

    assert result["ok"] is False
    assert result["error_code"] == "SUBMIT_OBSERVABILITY_CONFIRMATION_REQUIRED"
    assert result["observability_preflight"]["blocking_flags"] == ["observability_preflight_unavailable"]


def test_research_memory_snapshot_reads_local_records():
    with TemporaryDirectory() as tmp:
        storage = Path(tmp) / "data"
        storage.mkdir()
        repo = ResearchRepository(str(storage))
        repo.save_candidate(
            "run_1",
            Candidate(
                alpha_id="a1",
                expression="rank(ts_delta(close, 20))",
                family="Momentum",
                hypothesis="price momentum",
                data_fields=["close"],
                operators=["rank", "ts_delta"],
                official_metrics={"sharpe": 1.8, "fitness": 1.1, "pass_fail": "PASS"},
                scorecard={"total_score": 91},
                gate={"submission_ready": True},
                lifecycle_status="submission_ready",
            ),
        )
        repo.save_lifecycle_record("run_1", {"alpha_id": "a1", "stage": "submitted", "status": "SUBMITTED", "note": "cloud synced"})
        repo.save_check_record({"alpha_id": "a1", "error": "LOW_SHARPE"})
        (storage / "alpha_features.jsonl").write_text(
            '{"alpha_id":"a1","field_set":["close"],"operator_set":["rank","ts_delta"],"sharpe":1.8,"fitness":1.1,"pass_fail":"PASS"}\n',
            encoding="utf-8",
        )
        original = web.load_run_config
        web.load_run_config = lambda: SimpleNamespace(ops=SimpleNamespace(storage_dir=str(storage)))
        try:
            snapshot = research_memory_snapshot(limit=100, top_n=5)
        finally:
            web.load_run_config = original

        assert snapshot["ok"] is True
        assert snapshot["total_candidates"] == 1
        assert snapshot["fields"][0]["name"] == "close"
        assert any(row["name"] == "rank" for row in snapshot["operators"])
        assert any(item["reason"] == "LOW_SHARPE" for item in snapshot["failure_patterns"])
        assert snapshot["lineage"] == []


def test_research_observability_snapshot_summarizes_expression_backtest_and_errors(monkeypatch, tmp_path):
    storage = tmp_path / "data"
    storage.mkdir()
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(storage)
    repo = ResearchRepository(str(storage))
    repo.save_candidate(
        "run_1",
        Candidate(
            alpha_id="a1",
            expression="rank(ts_delta(close, 20))",
            family="Momentum",
            hypothesis="momentum",
            data_fields=["close"],
            operators=["rank", "ts_delta"],
            scorecard={"total_score": 88},
            lifecycle_status="submission_ready",
        ),
    )
    repo.save_backtest_record(
        "run_1",
        {
            "action": "simulation_result",
            "alpha_id": "a1",
            "simulation_id": "sim_1",
            "status": "simulation_failed",
            "lifecycle_status": "simulation_failed",
            "family": "Momentum",
            "score": 88,
            "expression": " rank ( ts_delta ( close , 20 ) ) ",
            "note": "rate limit retry pending",
        },
    )
    repo.save_check_record(
        {
            "alpha_id": "a1",
            "expression": "rank(ts_delta(close, 20))",
            "error": "Too many requests",
        }
    )
    monkeypatch.setattr(web, "load_run_config", lambda: config)

    snapshot = research_observability_snapshot(limit=100, top_n=5, include_cloud=False)

    assert snapshot["ok"] is True
    assert snapshot["schema_version"] == "research_observability_snapshot.v1"
    assert snapshot["expression_index"]["total_expression_records"] == 3
    assert snapshot["expression_index"]["duplicate_expression_count"] == 1
    assert snapshot["backtests"]["failed_count"] == 1
    assert snapshot["backtests"]["retryable_count"] == 1
    assert snapshot["errors"]["category_counts"]["rate_limit"] == 2
    assert snapshot["sqlite_cache"]["exists"] is True
    assert snapshot["sqlite_cache"]["error"] == ""
    assert snapshot["jsonl"]["backtests.jsonl"]["parsed_count"] == 1
    assert snapshot["health"]["risk_level"] in {"medium", "high"}
    assert "duplicate_expression_history" in snapshot["health"]["health_flags"]
    assert "retryable_official_errors_present" in snapshot["health"]["warning_flags"]
    assert snapshot["recommendations"]


def test_assistant_context_snapshot_uses_web_runtime_sources(monkeypatch, tmp_path):
    storage = tmp_path / "data"
    storage.mkdir()
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(storage)
    ResearchRepository(str(storage)).save_candidate(
        "run_1",
        Candidate(
            alpha_id="a1",
            expression="rank(ts_delta(close, 20))",
            family="Momentum",
            hypothesis="price momentum",
            data_fields=["close"],
            operators=["rank", "ts_delta"],
            official_metrics={"sharpe": 1.8, "fitness": 1.2, "pass_fail": "PASS"},
            scorecard={"total_score": 88},
            gate={"submission_ready": True},
            lifecycle_status="submission_ready",
        ),
    )
    monkeypatch.setattr(web, "load_run_config", lambda: config)
    monkeypatch.setattr(
        web,
        "latest_result_snapshot",
        lambda: {
            "ok": True,
            "source": "job_store",
            "job_id": "job_1",
            "status": "completed",
            "result": {"summary": {"candidates": [{"alpha_id": "a1", "expression": "rank(ts_delta(close, 20))"}]}},
            "progress": {},
        },
    )
    monkeypatch.setattr(
        web,
        "cloud_alpha_snapshot",
        lambda: {
            "summary": {
                "source": "cache",
                "count": 1,
                "submitted_count": 0,
                "passed_unsubmitted_count": 1,
                "failed_unsubmitted_count": 0,
                "is_stale": True,
            },
            "alphas": [{"id": "cloud_a1", "status": "UNSUBMITTED", "metrics": {"pass_fail": "PASS"}}],
        },
    )

    snapshot = assistant_context_snapshot(limit=100, top_n=5)

    assert snapshot["ok"] is True
    assert snapshot["schema_version"] == "assistant_context_pack.v1"
    assert snapshot["latest_result"]["source"] == "job_store"
    assert snapshot["cloud_alphas"]["is_stale"] is True
    assert snapshot["generation_focus"]["operators"] == ["rank", "ts_delta"]
    assert any("Refresh cloud alpha cache" in item for item in snapshot["recommended_next_actions"])
    assert "WorldQuant BRAIN FASTEXPR" in snapshot["prompt"]
    assert "storage_dir" not in snapshot
    assert snapshot["sensitive_fields_redacted"] == ["storage_dir"]

    full_snapshot = assistant_context_snapshot(limit=100, top_n=5, include_sensitive=True)
    assert full_snapshot["storage_dir"] == str(storage)


def test_assistant_guidance_snapshot_reads_latest_usable_guidance(monkeypatch, tmp_path):
    storage = tmp_path / "data"
    storage.mkdir()
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(storage)
    config.ops.budget.use_assistant_guidance = False
    config.ops.budget.assistant_guidance_min_confidence = 0.7
    config.ops.scoring.assistant_guidance_score_min_confidence = 0.8
    config.ops.scoring.assistant_guidance_score_min_outcome_count = 1
    repo = ResearchRepository(str(storage))
    repo.save_assistant_guidance(
        {
            "ok": True,
            "usable": True,
            "confidence": 0.9,
            "guidance_digest": "ag_webdigest",
            "top_fields": ["close"],
            "top_operators": ["rank", "ts_delta"],
            "preferred_windows": [20],
            "field_combinations": [["close"]],
            "historical_outcome_status": "strong",
            "historical_outcome": {
                "count": 3,
                "success_count": 2,
                "success_rate": 0.667,
                "avg_score": 82.5,
                "avg_sharpe": 1.6,
                "avg_fitness": 1.2,
            },
        },
        source="test",
    )
    repo.save_candidate(
        "run_1",
        Candidate(
            alpha_id="guided_1",
            expression="rank(ts_delta(close, 20))",
            family="Momentum",
            hypothesis="guided",
            data_fields=["close"],
            operators=["rank", "ts_delta"],
            source_tags=["assistant_guided"],
            submission={"assistant_guidance_digest": "ag_webdigest"},
            official_metrics={"pass_fail": "PASS", "sharpe": 1.4, "fitness": 1.1},
            scorecard={"total_score": 82},
            gate={"submission_ready": True},
            lifecycle_status="submission_ready",
        ),
    )
    monkeypatch.setattr(web, "load_run_config", lambda: config)

    snapshot = assistant_guidance_snapshot(limit=100)

    assert snapshot["ok"] is True
    assert snapshot["enabled"] is False
    assert snapshot["configured_min_confidence"] == 0.7
    assert snapshot["scoring_policy"]["enabled"] is True
    assert snapshot["scoring_policy"]["min_confidence"] == 0.8
    assert snapshot["score_adjustment_eligibility"]["eligible"] is True
    assert snapshot["score_adjustment_eligibility"]["outcome_count"] == 1
    assert snapshot["score_adjustment_eligibility"]["reason"] == "eligible for local ranking adjustment"
    assert snapshot["history_count"] == 1
    assert len(snapshot["history"]) == 1
    assert snapshot["history"][0]["guidance_digest"] == "ag_webdigest"
    assert snapshot["history"][0]["outcomes"]["count"] == 1
    assert snapshot["history"][0]["score_adjustment_eligible"] is True
    assert snapshot["history"][0]["score_adjustment_eligibility"]["min_confidence"] == 0.8
    assert snapshot["history"][0]["historical_outcome_status"] == "strong"
    assert snapshot["history"][0]["has_healthy_outcome"] is True
    assert snapshot["history"][0]["meets_min_confidence"] is True
    assert snapshot["history"][0]["has_generator_bias"] is True
    assert snapshot["history"][0]["assistant_guidance"]["top_fields"] == ["close"]
    assert snapshot["guidance"]["usable"] is True
    assert snapshot["guidance"]["historical_outcome_status"] == "strong"
    assert snapshot["guidance"]["historical_outcome"]["guidance_digest"] == "ag_webdigest"
    assert snapshot["guidance"]["top_operators"] == ["rank", "ts_delta"]
    assert snapshot["outcomes"]["count"] == 1
    assert snapshot["history"][0]["assistant_guidance"]["historical_outcome_status"] == "strong"
    assert snapshot["history"][0]["assistant_guidance"]["historical_outcome"]["avg_score"] == 82.5


def test_assistant_guidance_snapshot_marks_weak_historical_outcomes(monkeypatch, tmp_path):
    storage = tmp_path / "data"
    storage.mkdir()
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(storage)
    repo = ResearchRepository(str(storage))
    repo.save_assistant_guidance(
        {
            "ok": True,
            "usable": True,
            "confidence": 0.9,
            "guidance_digest": "ag_webweak",
            "top_fields": ["volume"],
            "top_operators": ["ts_mean"],
            "preferred_windows": [5],
            "historical_outcome_status": "weak",
            "historical_outcome": {
                "count": 3,
                "success_count": 0,
                "success_rate": 0.0,
                "avg_score": 24.0,
                "avg_sharpe": 0.2,
            },
        },
        source="weak_test",
    )
    for index in range(2):
        repo.save_candidate(
            "run_1",
            Candidate(
                alpha_id=f"weak_web_{index}",
                expression="rank(ts_mean(volume, 5))",
                family="Liquidity",
                hypothesis="weak guidance",
                data_fields=["volume"],
                operators=["rank", "ts_mean"],
                source_tags=["assistant_guided"],
                submission={"assistant_guidance_digest": "ag_webweak"},
                official_metrics={"pass_fail": "FAIL", "sharpe": 0.2, "fitness": 0.1},
                scorecard={"total_score": 24},
                gate={"failed_reasons": ["LOW_SHARPE"]},
                lifecycle_status="official_standard_rejected",
            ),
        )
    monkeypatch.setattr(web, "load_run_config", lambda: config)

    snapshot = assistant_guidance_snapshot(limit=100, min_confidence=0.7)

    assert snapshot["history"][0]["guidance_digest"] == "ag_webweak"
    assert snapshot["history"][0]["historical_outcome_status"] == "weak"
    assert snapshot["history"][0]["has_healthy_outcome"] is False
    assert snapshot["history"][0]["score_adjustment_eligible"] is True
    assert snapshot["history"][0]["score_adjustment_eligibility"]["outcome_status"] == "weak"
    assert snapshot["guidance"]["usable"] is False
    assert snapshot["guidance"]["reason"] == "weak_historical_guidance_outcome"
    assert snapshot["guidance"]["historical_outcome_status"] == "weak"
    assert snapshot["history"][0]["assistant_guidance"]["historical_outcome_status"] == "weak"


def test_assistant_guidance_snapshot_history_filters_confidence_flag(monkeypatch, tmp_path):
    storage = tmp_path / "data"
    storage.mkdir()
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(storage)
    repo = ResearchRepository(str(storage))
    repo.save_assistant_guidance(
        {
            "ok": True,
            "usable": True,
            "confidence": 0.4,
            "top_operators": ["rank"],
            "summary": "Low confidence operator hint.",
        },
        source="low_confidence_test",
    )
    repo.save_assistant_guidance(
        {
            "ok": True,
            "usable": True,
            "confidence": 0.95,
            "summary": "No generator bias.",
        },
        source="no_bias_test",
    )
    monkeypatch.setattr(web, "load_run_config", lambda: config)

    snapshot = assistant_guidance_snapshot(limit=100, min_confidence=0.7)

    assert snapshot["history_count"] == 2
    assert [row["source"] for row in snapshot["history"]] == ["no_bias_test", "low_confidence_test"]
    assert snapshot["history"][0]["meets_min_confidence"] is True
    assert snapshot["history"][0]["has_generator_bias"] is False
    assert snapshot["history"][0]["score_adjustment_eligible"] is False
    assert snapshot["history"][0]["score_adjustment_reason"] == "not enough historical outcome samples"
    assert snapshot["history"][1]["meets_min_confidence"] is False
    assert snapshot["history"][1]["has_generator_bias"] is True
    assert snapshot["history"][1]["score_adjustment_eligible"] is False
    assert snapshot["history"][1]["score_adjustment_reason"] == "guidance confidence is below scoring policy"
    assert snapshot["guidance"]["usable"] is False
    assert snapshot["guidance"]["reason"] == "no_persisted_usable_guidance"


def test_assistant_request_snapshot_returns_llm_envelope(monkeypatch, tmp_path):
    storage = tmp_path / "data"
    storage.mkdir()
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(storage)
    ResearchRepository(str(storage)).save_candidate(
        "run_1",
        Candidate(
            alpha_id="a1",
            expression="rank(ts_delta(close, 20))",
            family="Momentum",
            hypothesis="price momentum",
            data_fields=["close"],
            operators=["rank", "ts_delta"],
        ),
    )
    monkeypatch.setattr(web, "load_run_config", lambda: config)
    monkeypatch.setattr(
        web,
        "latest_result_snapshot",
        lambda: {
            "ok": True,
            "source": "job_store",
            "job_id": "job_1",
            "status": "completed",
            "result": {"summary": {"candidates": [{"alpha_id": "a1", "expression": "rank(ts_delta(close, 20))"}]}},
            "progress": {},
        },
    )
    monkeypatch.setattr(
        web,
        "cloud_alpha_snapshot",
        lambda: {"summary": {"source": "cache", "count": 0, "is_stale": False}, "alphas": []},
    )

    snapshot = assistant_request_snapshot(limit=100, top_n=5, include_prompt=False, include_offline_draft=True)

    assert snapshot["ok"] is True
    assert snapshot["schema_version"] == "assistant_request_pack.v1"
    assert "prompt" not in snapshot
    assert "prompt" not in snapshot["context_pack"]
    assert snapshot["request"]["messages"][0]["role"] == "system"
    assert snapshot["request"]["response_schema"]["schema_version"] == "assistant_response.v1"
    assert snapshot["offline_draft"]["candidate_adjustments"]


def test_assistant_response_parse_payload_normalizes_model_output():
    payload = assistant_response_parse_payload(
        {
            "text": (
                '{"summary":"Keep generation local-first.",'
                '"next_actions":["refresh memory"],'
                '"risks":["submit_requires_confirmation"],'
                '"confidence":0.66}'
            )
        }
    )

    assert payload["ok"] is True
    assert payload["summary"] == "Keep generation local-first."
    assert payload["recommended_next_actions"] == ["refresh memory"]
    assert payload["risk_flags"] == ["submit_requires_confirmation"]


def test_assistant_response_guidance_payload_maps_model_output():
    payload = assistant_response_guidance_payload(
        {
            "text": (
                '{"summary":"Use close momentum.",'
                '"actions":["refresh cloud cache"],'
                '"risks":["submit_requires_confirmation"],'
                '"candidate_adjustments":['
                '{"target":"fields","value":["close"],"rationale":"memory"},'
                '{"target":"operators","value":["rank"],"rationale":"memory"}'
                '],'
                '"confidence":0.9}'
            ),
            "min_confidence": 0.8,
        }
    )

    assert payload["ok"] is True
    assert payload["usable"] is True
    assert payload["top_fields"] == ["close"]
    assert payload["top_operators"] == ["rank"]
    assert payload["operational_flags"]["refresh_cloud_before_submit"] is True


def test_anti_overfit_snapshot_uses_latest_result(monkeypatch):
    monkeypatch.setattr(
        web,
        "latest_result_snapshot",
        lambda: {
            "ok": True,
            "result": {
                "summary": {
                    "candidates": [
                        {
                            "alpha_id": "a1",
                            "expression": "rank(ts_delta(close, 20))",
                            "official_metrics": {"ic_series": [0.03, 0.04, 0.035, 0.025] * 20},
                            "submission": {},
                        }
                    ]
                }
            },
        },
    )

    payload = anti_overfit_snapshot("a1")

    assert payload["ok"] is True
    assert payload["candidate_id"] == "a1"
    assert payload["anti_overfit_report"]["schema_version"] == "anti_overfit_report.v1"


def test_rolling_validation_snapshot_uses_latest_result(monkeypatch):
    candidate = {
        "alpha_id": "a1",
        "expression": "rank(close)",
        "official_metrics": {"rolling_fitness": [1.0, 1.0, 0.95, 0.9, 0.85, 0.8]},
        "submission": {},
    }
    latest = {
        "ok": True,
        "result": {
            "summary": {
                "candidates": [candidate],
            }
        },
    }
    monkeypatch.setattr(web, "latest_result_snapshot", lambda: latest)

    payload = rolling_validation_snapshot("a1", windows=3)

    assert payload["ok"] is True
    assert payload["candidate_id"] == "a1"
    assert payload["rolling_validation_report"]["schema_version"] == "rolling_validation_report.v1"


def test_assistant_cross_review_payload_accepts_consistent_responses():
    response = (
        '{"summary":"Keep cloud cache fresh.",'
        '"recommended_next_actions":["refresh cloud cache"],'
        '"risk_flags":["cloud_sync_required"],'
        '"candidate_adjustments":[],"follow_up_questions":[],"confidence":0.9}'
    )

    payload = assistant_cross_review_payload(
        {
            "request_pack": {"prompt_digest": "pd_1"},
            "primary_response": response,
            "reviewer_response": response,
            "min_confidence": 0.7,
        }
    )

    assert payload["ok"] is True
    assert payload["decision"] == "accept"


def test_save_assistant_guidance_payload_persists_usable_guidance(monkeypatch, tmp_path):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path)
    monkeypatch.setattr(web, "load_run_config", lambda *args, **kwargs: config)

    payload = save_assistant_guidance_payload(
        {
            "environment": "mock",
            "min_confidence": 0.7,
            "assistant_response": (
                '{"summary":"Use close momentum.",'
                '"recommended_next_actions":[],"risk_flags":[],'
                '"candidate_adjustments":['
                '{"target":"fields","value":["close"],"rationale":"memory"},'
                '{"target":"operators","value":["rank"],"rationale":"memory"}'
                '],'
                '"follow_up_questions":[],"confidence":0.9}'
            ),
        }
    )

    assert payload["ok"] is True
    assert payload["saved"] is True
    assert payload["assistant_guidance"]["top_fields"] == ["close"]
    assert payload["snapshot"]["history_count"] == 1
    assert (tmp_path / "assistant_guidance.jsonl").is_file()


def test_save_assistant_guidance_payload_skips_low_confidence(monkeypatch, tmp_path):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path)
    monkeypatch.setattr(web, "load_run_config", lambda *args, **kwargs: config)

    payload = save_assistant_guidance_payload(
        {
            "environment": "mock",
            "min_confidence": 0.8,
            "assistant_response": (
                '{"summary":"Weak hint.",'
                '"recommended_next_actions":[],"risk_flags":[],'
                '"candidate_adjustments":[{"target":"operators","value":["rank"],"rationale":"thin"}],'
                '"follow_up_questions":[],"confidence":0.3}'
            ),
        }
    )

    assert payload["ok"] is True
    assert payload["saved"] is False
    assert payload["reason"] == "confidence_below_threshold"
    assert not (tmp_path / "assistant_guidance.jsonl").exists()


def test_generate_candidates_payload_applies_assistant_guidance(monkeypatch, tmp_path):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path)
    monkeypatch.setattr(web, "load_run_config", lambda *args, **kwargs: config)
    captured = {}

    def fake_set_experience_guidance(self, patterns):
        captured["patterns"] = patterns

    monkeypatch.setattr("brain_alpha_ops.research.generator.CandidateGenerator.set_experience_guidance", fake_set_experience_guidance)

    payload = generate_candidates_payload(
        {
            "environment": "mock",
            "count": 2,
            "use_research_memory": False,
            "assistant_min_confidence": 0.7,
            "assistant_response": (
                '{"summary":"Use close momentum.",'
                '"recommended_next_actions":[],'
                '"risk_flags":[],'
                '"candidate_adjustments":['
                '{"target":"fields","value":["close"],"rationale":"memory"},'
                '{"target":"operators","value":["rank","ts_delta"],"rationale":"memory"},'
                '{"target":"windows","value":[20],"rationale":"lookback"}'
                '],'
                '"follow_up_questions":[],"confidence":0.9}'
            ),
        }
    )

    assert payload["ok"] is True
    assert payload["count"] <= 2
    assert payload["assistant_guidance"]["applied"] is True
    assert payload["assistant_guidance"]["guidance_digest"].startswith("ag_")
    assert payload["summary"]["official_api_called"] is False
    assert captured["patterns"]["top_operators"] == ["rank", "ts_delta"]
    if payload["candidates"]:
        assert payload["candidates"][0]["scorecard"]["score_basis"] == "local_prior"
        assert "assistant_guided" in payload["candidates"][0]["source_tags"]
        assert payload["candidates"][0]["submission"]["assistant_guidance_digest"].startswith("ag_")


def test_generate_candidates_payload_attaches_guidance_outcome_metadata(monkeypatch, tmp_path):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path)
    monkeypatch.setattr(web, "load_run_config", lambda *args, **kwargs: config)
    monkeypatch.setattr(
        "brain_alpha_ops.research.generator.CandidateGenerator.set_experience_guidance",
        lambda self, patterns: None,
    )

    payload = generate_candidates_payload(
        {
            "environment": "mock",
            "count": 2,
            "use_research_memory": False,
            "assistant_min_confidence": 0.7,
            "assistant_guidance": {
                "ok": True,
                "usable": True,
                "confidence": 0.9,
                "top_fields": ["close"],
                "top_operators": ["rank"],
                "preferred_windows": [20],
                "historical_outcome_status": "strong",
                "historical_outcome": {
                    "count": 3,
                    "success_count": 2,
                    "success_rate": 0.667,
                    "avg_score": 82.5,
                    "avg_sharpe": 1.6,
                },
            },
        }
    )

    assert payload["ok"] is True
    assert payload["assistant_guidance"]["historical_outcome_status"] == "strong"
    if payload["candidates"]:
        submission = payload["candidates"][0]["submission"]
        assert submission["assistant_guidance_outcome_status"] == "strong"
        assert submission["assistant_guidance_outcome_success_rate"] == 0.667
        assert submission["assistant_guidance_outcome"]["avg_score"] == 82.5
        adjustment = payload["candidates"][0]["scorecard"]["assistant_guidance_adjustment"]
        assert adjustment["outcome_status"] == "strong"
        assert adjustment["adjustment"] > 0
        assert adjustment["applied_to_total"] is True


def test_cloud_alpha_merge_appends_only_new_or_changed_versions():
    with TemporaryDirectory() as tmp:
        repo = ResearchRepository(tmp)
        first = repo.merge_cloud_alphas(
            [
                {"id": "a1", "status": "UNSUBMITTED", "metrics": {"pass_fail": "PASS"}},
                {"id": "a2", "status": "ACTIVE", "metrics": {"pass_fail": "PASS"}},
            ],
            sync_range="3d",
        )
        second = repo.merge_cloud_alphas(
            [
                {"id": "a1", "status": "UNSUBMITTED", "metrics": {"pass_fail": "PASS"}},
                {"id": "a2", "status": "SUBMITTED", "metrics": {"pass_fail": "PASS"}},
                {"id": "a3", "status": "UNSUBMITTED", "metrics": {"pass_fail": "FAIL"}},
            ],
            sync_range="3d",
        )
        rows = (Path(tmp) / "cloud_alphas.jsonl").read_text(encoding="utf-8").splitlines()

        assert first == {"scanned": 2, "added": 2, "updated": 0, "skipped": 0, "failed": 0}
        assert second == {"scanned": 3, "added": 1, "updated": 1, "skipped": 1, "failed": 0}
        assert len(rows) == 4
        assert repo.cloud_alpha_ids() == {"a1", "a2", "a3"}


def test_load_check_results_reports_recovery_warning(monkeypatch, caplog):
    monkeypatch.setattr(web, "_read_storage_jsonl", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("boom")))

    with caplog.at_level("WARNING", logger="brain_alpha_ops.web"):
        payload = web.load_check_results()

    assert payload["items"] == []
    assert payload["count"] == 0
    assert "warning" in payload
    assert "failed to load check results" in caplog.text


def test_web_storage_jsonl_stats_reports_invalid_lines(monkeypatch, tmp_path):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path)
    (tmp_path / "checks.jsonl").write_text('{"ok":true}\nnot-json\n', encoding="utf-8")
    monkeypatch.setattr(web, "load_run_config", lambda *args, **kwargs: config)

    stats = web._read_storage_jsonl_stats("checks.jsonl", limit=10)

    assert stats["exists"] is True
    assert stats["parsed_count"] == 1
    assert stats["skipped_invalid_count"] == 1


def test_read_official_context_json_logs_invalid_file(monkeypatch, tmp_path, caplog):
    config = RunConfig(environment="mock")
    config.ops.storage_dir = str(tmp_path)
    (tmp_path / "official_fields.json").write_text("{bad-json", encoding="utf-8")
    monkeypatch.setattr(web, "load_run_config", lambda *args, **kwargs: config)
    monkeypatch.setattr(web, "runtime_project_root", lambda: tmp_path / "missing_runtime")

    with caplog.at_level("WARNING", logger="brain_alpha_ops.web"):
        rows = web._read_official_context_json("official_fields.json")

    assert isinstance(rows, list)
    assert "failed to read official context file" in caplog.text
