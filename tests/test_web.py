from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

import pytest

from brain_alpha_ops import web
from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.brain_api.canonical import CANONICAL_SETTINGS
from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.repository import ResearchRepository
from brain_alpha_ops.research.safety import SubmissionLedger
from brain_alpha_ops.tasks import JobStore
from brain_alpha_ops.web import _load_html, anti_overfit_snapshot, assistant_context_snapshot, assistant_cross_review_payload, assistant_guidance_snapshot, assistant_request_snapshot, assistant_response_guidance_payload, assistant_response_parse_payload, cloud_alpha_snapshot, config_from_payload, generate_candidates_payload, passed_candidates_from_payload, public_run_config, research_memory_snapshot, research_observability_snapshot, rolling_validation_snapshot, save_assistant_guidance_payload, sqlite_expression_lookup_payload, sqlite_index_snapshot, sqlite_record_lookup_payload
from brain_alpha_ops.web_config import save_run_config_payload as save_run_config_payload_service
from brain_alpha_ops.web_job_registry import WebJobRegistry
from brain_alpha_ops.web_rate_limit import RateLimitPolicy, RequestRateLimiter
from brain_alpha_ops.web_routes import GET_ROUTES, POST_ROUTES, route_for
from scripts.check_frontend_syntax import check_scripts


_MISSING_WEB_ATTR = object()
_WEB_JOB_EXPORTS = (
    "JOBS",
    "SYNC_JOBS",
    "CHECK_JOBS",
    "ASYNC_JOBS",
    "SUBMIT_LOCK",
    "RATE_LIMITER",
    "TASK_EXECUTOR",
)


def _snapshot_web_attrs(*names: str) -> dict[str, object]:
    return {name: web.__dict__.get(name, _MISSING_WEB_ATTR) for name in names}


def _restore_web_attrs(snapshot: dict[str, object]) -> None:
    for name, value in snapshot.items():
        if value is _MISSING_WEB_ATTR:
            web.__dict__.pop(name, None)
        else:
            setattr(web, name, value)


def _free_port_or_skip(start: int, host: str = "127.0.0.1") -> int:
    try:
        return web.find_free_port(start=start, host=host)
    except (OSError, RuntimeError, PermissionError) as exc:
        pytest.skip(f"local web server ports unavailable in this environment: {exc}")


def _live_session_credentials(url: str) -> tuple[str, str]:
    root_response = urllib.request.urlopen(url, timeout=5)
    cookie = str(root_response.headers.get("Set-Cookie", "")).split(";", 1)[0]
    html = root_response.read().decode("utf-8")
    csrf_match = re.search(r'<meta name="brain-alpha-csrf" content="([^"]+)"', html)
    if not csrf_match:
        csrf_match = re.search(r"var CSRF_TOKEN = '([^']+)'", html)
    assert csrf_match
    assert csrf_match.group(1) != "__BRAIN_ALPHA_OPS_CSRF_TOKEN__"
    return cookie, csrf_match.group(1)


def _live_react_session_credentials(url: str) -> tuple[str, str, str]:
    root_response = urllib.request.urlopen(url, timeout=5)
    cookie = str(root_response.headers.get("Set-Cookie", "")).split(";", 1)[0]
    html = root_response.read().decode("utf-8")
    csrf_match = re.search(r'<meta name="brain-alpha-csrf" content="([^"]+)"', html)
    stream_match = re.search(r'<meta name="brain-alpha-stream" content="([^"]+)"', html)
    assert csrf_match
    assert stream_match
    assert csrf_match.group(1) != "__BRAIN_ALPHA_OPS_CSRF_TOKEN__"
    assert stream_match.group(1) != "__BRAIN_ALPHA_OPS_STREAM_TOKEN__"
    return cookie, csrf_match.group(1), html


def _live_json_post(
    url: str,
    path: str,
    payload: dict,
    *,
    cookie: str,
    csrf_token: str,
    request_id: str,
):
    request = urllib.request.Request(
        f"{url.rstrip('/')}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Cookie": cookie,
            "X-Brain-Alpha-CSRF": csrf_token,
            "X-Brain-Alpha-Request-ID": request_id,
            "X-Brain-Alpha-Request-Timestamp": str(int(time.time() * 1000)),
        },
        method="POST",
    )
    return urllib.request.urlopen(request, timeout=5)


def _react_source(*parts: str) -> str:
    return (Path(__file__).resolve().parents[1] / "brain_alpha_ops" / "web" / "react_app" / "src" / Path(*parts)).read_text(encoding="utf-8")


def _complete_official_metrics(**overrides):
    metrics = {
        "pass_fail": "PASS",
        "sharpe": 1.5,
        "fitness": 1.1,
        "turnover": 0.2,
        "self_correlation": 0.1,
        "prod_correlation": 0.2,
        "weight_concentration": 0.03,
    }
    metrics.update(overrides)
    return metrics


def test_web_html_serves_current_react_shell():
    html = _load_html()

    assert "<title>BRAIN Alpha Ops</title>" in html
    assert '<div id="root"></div>' in html
    assert '<meta name="brain-alpha-csrf"' in html
    assert '<meta name="brain-alpha-stream"' in html
    assert 'type="module"' in html
    assert "/assets/" in html
    assert "OfficialBrainAPI" not in html

    app_tsx = _react_source("App.tsx")
    state_cards_tsx = _react_source("components", "StateCards.tsx")
    job_monitor_tsx = _react_source("components", "JobMonitor.tsx")
    for text in (
        "BRAIN Alpha Ops",
        "生产验证工作台",
        "候选管理",
        "回测监控",
        "质量门禁",
        "提交确认",
        "系统配置",
        "云端快照",
        "返回状态卡",
    ):
        assert text in app_tsx or text in state_cards_tsx

    for path in (
        "/api/research_knowledge",
        "/api/research_observability",
        "/api/prompt_runs",
        "/api/sqlite_indexes",
        "/api/sqlite_expression_lookup",
        "/api/sqlite_record_lookup",
        "/api/anti_overfit",
        "/api/rolling_validation",
    ):
        assert path in GET_ROUTES


def test_web_settings_select_options_match_canonical_contract():
    schema = web.public_config_schema()
    options = schema["settings_options"]

    assert set(options["region"]) == CANONICAL_SETTINGS["region"]
    assert set(options["universe"]) == CANONICAL_SETTINGS["universe"]
    assert {int(value) for value in options["delay"]} == CANONICAL_SETTINGS["delay"]
    assert set(options["neutralization"]) == CANONICAL_SETTINGS["neutralization"]
    assert set(options["instrumentType"]) == CANONICAL_SETTINGS["instrumentType"]
    assert set(options["type"]) == CANONICAL_SETTINGS["type"]
    assert set(options["pasteurization"]) == CANONICAL_SETTINGS["pasteurization"]
    assert set(options["unitHandling"]) == CANONICAL_SETTINGS["unitHandling"]
    assert set(options["nanHandling"]) == CANONICAL_SETTINGS["nanHandling"]
    assert set(options["language"]) == CANONICAL_SETTINGS["language"]


def test_submit_preflight_errors_are_backend_owned_and_react_readable():
    hook_js = _react_source("hooks", "useApi.ts")
    submission_tsx = _react_source("components", "SubmissionConfirmPanel.tsx")
    quality_tsx = _react_source("components", "QualityCheckPanel.tsx")
    safety_py = (Path(__file__).resolve().parents[1] / "brain_alpha_ops" / "web_submission_safety.py").read_text(encoding="utf-8")
    submission_batch_py = (Path(__file__).resolve().parents[1] / "brain_alpha_ops" / "web_submission_single.py").read_text(encoding="utf-8")

    for code in (
        "SUBMIT_NOT_READY",
        "SUBMIT_FAILED_CANDIDATE",
        "SUBMIT_DUPLICATE_OFFICIAL_ID",
        "SUBMIT_DUPLICATE_EXPRESSION",
        "SUBMIT_CLOUD_SYNC_REQUIRED",
        "SUBMIT_CLOUD_SYNC_STALE",
        "SUBMIT_CLOUD_ALREADY_SUBMITTED",
        "SUBMIT_OBSERVABILITY_CONFIRMATION_REQUIRED",
    ):
        assert code in safety_py or code in submission_batch_py

    assert "/api/submit_readiness" in submission_tsx
    assert "/api/backtest_slots" in quality_tsx
    assert "json.error || json.error_code || \"Request failed\"" in hook_js
    assert "提交确认数据加载失败" in submission_tsx
    assert "达标检查数据加载失败" in quality_tsx
    assert "X-Brain-Alpha-CSRF" in hook_js
    assert "brain-alpha-csrf" in hook_js


def test_web_react_dist_shell_has_build_assets():
    root = Path(__file__).resolve().parents[1]
    dist = root / "brain_alpha_ops" / "web" / "react_app" / "dist"
    html = (dist / "index.html").read_text(encoding="utf-8")

    assert '<div id="root"></div>' in html
    assert 'type="module"' in html
    assert "/assets/" in html
    assert any(path.suffix == ".js" for path in (dist / "assets").iterdir())
    assert any(path.suffix == ".css" for path in (dist / "assets").iterdir())


def test_web_react_sources_are_current_frontend_contract():
    app_tsx = _react_source("App.tsx")
    candidate_tsx = _react_source("components", "CandidateTable.tsx")
    snapshot_tsx = _react_source("components", "SnapshotPanel.tsx")

    assert "StateCards" in app_tsx
    assert "switchTab" not in app_tsx
    assert "/api/candidates?limit=" in candidate_tsx
    assert "/api/check_results" in candidate_tsx
    assert "/api/generate_candidates" in candidate_tsx
    assert "sanitizeTextInput" in candidate_tsx
    assert "/api/snapshot/cloud?limit=100" in snapshot_tsx
    assert "max-w-full overflow-auto" in snapshot_tsx


def test_web_react_shell_has_no_inline_event_handlers():
    html = _load_html()

    assert "onclick=" not in html
    assert "onchange=" not in html
    assert "oninput=" not in html
    assert "onkeydown=" not in html
    assert 'value="mock"' not in html
    assert "本地模拟环境" not in html


def test_web_static_html_has_no_inline_style_attributes():
    html = _load_html()

    assert " style=" not in html
    assert "style-src 'self' 'unsafe-inline'" not in web.content_security_policy_for_html(html)


def test_web_csp_hashes_inline_scripts_without_unsafe_inline():
    from brain_alpha_ops.web import content_security_policy_for_html

    html = "<style>.ok{color:red}</style><script>console.log('ok')</script><script>window.x=1</script>"
    csp = content_security_policy_for_html(html)

    assert "script-src 'self'" in csp
    assert "script-src 'self' 'unsafe-inline'" not in csp
    assert "style-src 'self'" in csp
    assert "style-src 'self' 'unsafe-inline'" not in csp
    assert csp.count("'sha256-") == 3


def test_react_snapshot_views_cover_readonly_research_surfaces():
    snapshot_tsx = _react_source("components", "SnapshotPanel.tsx")

    for endpoint in (
        "/api/snapshot/cloud?limit=100",
        "/api/lifecycle",
        "/api/research_memory?limit=5000&top_n=10",
        "/api/research_knowledge?limit=100&min_confidence=0",
        "/api/research_observability?limit=5000&top_n=10&include_cloud=true",
        "/api/prompt_runs?limit=100",
        "/api/sqlite_indexes?top_n=10",
        "/api/latest_result",
    ):
        assert endpoint in snapshot_tsx

    for helper in (
        "cloudRows",
        "lifecycleRows",
        "researchMemoryRows",
        "researchKnowledgeRows",
        "researchObservabilityRows",
        "promptRunRows",
        "sqliteIndexRows",
        "robustnessRows",
    ):
        assert f"rows: {helper}" in snapshot_tsx or f"function {helper}" in snapshot_tsx

    assert "const MAX_FILTER_LENGTH = 200" in snapshot_tsx
    assert "sanitizeTextInput" in snapshot_tsx
    assert "max-w-full overflow-auto" in snapshot_tsx
    assert "function text(value: unknown)" in snapshot_tsx
    assert "/api/sqlite_expression_lookup" in GET_ROUTES
    assert "/api/sqlite_record_lookup" in GET_ROUTES
    assert "/api/anti_overfit" in GET_ROUTES
    assert "/api/rolling_validation" in GET_ROUTES


def test_react_candidate_table_keeps_filter_sort_and_mobile_safe_table_contract():
    candidate_tsx = _react_source("components", "CandidateTable.tsx")

    for contract in (
        "const MAX_FILTER_LENGTH = 200",
        "const CANDIDATE_FETCH_LIMIT = 1000",
        "const PAGE_SIZE = 20",
        'aria-label="过滤候选"',
        "sanitizeTextInput",
        "max-w-full overflow-auto",
        "candidateText(c.expression)",
        "candidateText(c.family)",
        "candidateIdentity(c)",
        'column="score"',
        "没有匹配的候选",
        "暂无候选记录",
        "上一页",
        "下一页",
    ):
        assert contract in candidate_tsx

    assert 'onclick="' not in candidate_tsx.lower()
    assert 'onkeydown="' not in candidate_tsx.lower()
    assert 'role="button"' not in candidate_tsx


def test_react_state_cards_keep_core_flow_visible_and_actionable():
    app_tsx = _react_source("App.tsx")
    state_cards_tsx = _react_source("components", "StateCards.tsx")
    job_monitor_tsx = _react_source("components", "JobMonitor.tsx")

    for contract in (
        'useState<CardViewId | "cards">("cards")',
        'aria-label="返回状态卡"',
        "StateCards onNavigate={handleNavigate}",
        "登录、运行、证明可用",
        "输入 BRAIN 账户，测试连接，启动强制非提交的生产验证",
        "BRAIN 账户连接",
        "非提交生产验证",
        "填写 BRAIN 凭证",
        "未连接 BRAIN",
        "打开系统配置",
        "/api/candidates?limit=1000",
        "/api/backtest_slots",
        "/api/config",
        "/api/snapshot/cloud?limit=10",
        "grid w-full max-w-full grid-cols-1",
        "2xl:grid-cols-5",
        "onClick={() => onNavigate(config.id)}",
        'caption: "提交审计"',
    ):
        assert contract in app_tsx or contract in state_cards_tsx or contract in job_monitor_tsx

    assert "/api/submit_readiness" not in state_cards_tsx

    for view_id in (
        'id: "candidates"',
        'id: "official_backtests"',
        'id: "quality_check"',
        'id: "submission_confirm"',
        'id: "checkpoint_status"',
        'id: "config"',
        'id: "cloud"',
    ):
        assert view_id in state_cards_tsx

    assert "import ConfigPanel" in app_tsx
    assert 'case "config":' in app_tsx
    assert "detailContent = <ConfigPanel notify={notify} credentials={credentials} onCredentialsChange={setCredentials} />" in app_tsx


def test_react_quality_submit_and_backtest_panels_cover_conflict_guards():
    backtest_tsx = _react_source("components", "OfficialBacktestSlots.tsx")
    quality_tsx = _react_source("components", "QualityCheckPanel.tsx")
    submission_tsx = _react_source("components", "SubmissionConfirmPanel.tsx")

    for contract in (
        "/api/backtest_slots",
        "POLL_INTERVAL_MS = 5000",
        "BacktestQueueSummaryStrip",
        "Review blockers",
        "Submit evidence",
        "official_api_called",
        "等待官方容量",
    ):
        assert contract in backtest_tsx

    for contract in (
        "/api/candidates?limit=1000",
        "/api/backtest_slots",
        "/api/submit_readiness",
        "达标检查",
        "本地通过",
        "官方仿真",
        "可提交",
        "Thresholds:",
        "Blocking:",
        "Family blockers:",
    ):
        assert contract in quality_tsx

    for contract in (
        "/api/candidates?limit=1000",
        "/api/check_results",
        "/api/submit_readiness",
        "提交前确认",
        "ready_to_submit",
        "production_gaps",
        "required_next_steps",
        "预检查通过",
        "阻断与待处理",
        "READY",
    ):
        assert contract in submission_tsx


def test_react_sources_avoid_legacy_inline_globals_and_external_assets():
    root = Path(__file__).resolve().parents[1] / "brain_alpha_ops" / "web" / "react_app" / "src"
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.tsx"))

    for legacy_marker in (
        "window.AppState",
        "switchTab",
        "data-tab=",
        "onclick=",
        "onkeydown=",
        "cdn.jsdelivr.net",
        "api.fontshare.com",
        "code.iconify.design",
    ):
        assert legacy_marker not in source


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
            "cloudSyncMaxElapsedSeconds": 30,
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
    assert config.budget.cloud_sync_max_elapsed_seconds == 30
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


def test_web_config_from_payload_accepts_alpha_type_alias():
    config = config_from_payload({"settings": {"alphaType": "PYRAMID", "unitHandling": "NONE"}})

    assert config.settings.type == "PYRAMID"
    assert config.settings.unitHandling == "NONE"


def test_web_config_from_payload_rejects_invalid_numbers():
    with pytest.raises(ValueError, match="candidates must be an integer"):
        config_from_payload({"candidates": "many"})

    with pytest.raises(ValueError, match="settings.truncation must be finite"):
        config_from_payload({"settings": {"truncation": "NaN"}})

    with pytest.raises(ValueError, match="cyclePauseSeconds must be >= 0.0"):
        config_from_payload({"cyclePauseSeconds": -1})

    with pytest.raises(ValueError, match="cloudSyncMaxElapsedSeconds must be >= 0.0"):
        config_from_payload({"cloudSyncMaxElapsedSeconds": -1})


def test_web_config_from_payload_rejects_non_production_environment():
    with pytest.raises(ValueError, match="only supports production"):
        config_from_payload({"environment": "mock"})


def test_web_config_from_payload_rejects_non_official_base_url_in_production():
    with pytest.raises(ValueError, match="baseUrl not allowed"):
        config_from_payload({"environment": "production", "baseUrl": "http://127.0.0.1:1"})


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


def test_save_run_config_payload_persists_editable_config_surface(tmp_path):
    base = RunConfig(environment="production")
    base.ops.settings.dataset = "pv1"
    saved = []

    def writer(config):
        saved.append(config)
        return tmp_path / "run_config.json"

    payload = {
        "environment": "production",
        "autoSubmit": True,
        "auto_submit": True,
        "username": "researcher@example.com",
        "password": "plain-password",
        "token": "plain-token",
        "settings": {
            "region": "USA",
            "universe": "TOP3000",
            "delay": 1,
            "decay": 12,
            "neutralization": "INDUSTRY",
            "dataset": "pv1",
        },
        "candidates": 33,
        "cycles": 7,
        "poolSize": 21,
        "backtestBatchSize": 4,
        "requireCloudSync": False,
        "minSharpe": 1.5,
        "minFitness": 1.1,
        "minTurnover": 0.02,
        "platformMaxTurnover": 0.6,
        "maxSelfCorrelation": 0.65,
        "maxWeightConcentration": 0.08,
    }

    result = save_run_config_payload_service(payload, loader=lambda: base, writer=writer)

    assert result["ok"] is True
    assert result["config"]["credentials"]["username"] == ""
    assert result["config"]["credentials"]["password"] == ""
    assert result["config"]["credentials"]["token"] == ""
    assert saved[0].credentials.username == ""
    assert saved[0].credentials.password == ""
    assert saved[0].credentials.token == ""
    assert result["config"]["auto_submit"] is False
    assert saved[0].auto_submit is False
    assert saved[0].ops.settings.decay == 12
    assert saved[0].ops.budget.max_candidates_per_cycle == 33
    assert saved[0].ops.budget.require_cloud_sync is False
    assert saved[0].ops.thresholds.min_sharpe == 1.5
    assert saved[0].ops.thresholds.platform_max_turnover == 0.6


def test_public_config_schema_exposes_required_panel_contract():
    schema = web.public_config_schema()
    control_paths = {item["payload_path"] for item in schema["controls"]}

    assert schema["schema_version"] == "web_config_schema.v1"
    assert schema["environment"]["allowed"] == ["production"]
    assert "type" in schema["required_settings_fields"]
    assert "settings.type" in control_paths
    assert "settings.alphaType" not in control_paths
    assert "settings.dataset" in control_paths
    assert schema["settings_options"]["unitHandling"] == ["NONE", "RAW", "VERIFY"]
    assert "pv1" in schema["settings_options"]["dataset"]
    assert any(
        item["id"] == "pv1" and item["label"].startswith("pv1 -")
        for item in schema["dataset_options"]
    )
    assert "assistantGuidanceScoreMinOutcomeCount" in control_paths
    assert "strategyPluginSpecs" in control_paths
    assert schema["operation_layout"]["primary_console"] == [
        "toggle-run",
        "sync-cloud",
        "check-batch",
        "submit-selected",
    ]


def test_web_routes_define_session_policy_and_known_paths():
    assert route_for("GET", "/api/health").requires_session is False
    assert route_for("GET", "/").category == "html"
    assert route_for("POST", "/api/run").requires_session is True
    assert route_for("POST", "/api/config").handler == "config"
    assert route_for("GET", "/api/config_schema").handler == "config_schema"
    assert route_for("GET", "/api/snapshot/cloud").handler == "cloud_alphas"
    assert route_for("GET", "/api/snapshot/memory").handler == "research_memory"
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
    config = RunConfig(environment="production")
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
    assert web.job_registry() is web.JOB_REGISTRY
    assert web.JOB_REGISTRY.jobs is web.JOBS
    assert web.JOB_REGISTRY.sync_jobs is web.SYNC_JOBS
    assert web.JOB_REGISTRY.check_jobs is web.CHECK_JOBS
    assert web.JOB_REGISTRY.async_jobs is web.ASYNC_JOBS
    assert web.JOB_REGISTRY.submit_lock is web.SUBMIT_LOCK
    assert web.JOB_REGISTRY.rate_limiter is web.RATE_LIMITER
    assert web.JOB_REGISTRY.task_executor is web.TASK_EXECUTOR


def test_web_job_registry_creates_durable_stores_under_project_root(tmp_path):
    registry = WebJobRegistry.create(tmp_path, max_workers=1)
    exports = registry.legacy_exports()

    assert registry.jobs.persistence_path == tmp_path / "data" / "jobs_production.json"
    assert registry.sync_jobs.persistence_path == tmp_path / "data" / "jobs_sync.json"
    assert registry.check_jobs.persistence_path == tmp_path / "data" / "jobs_check.json"
    assert registry.async_jobs.persistence_path == tmp_path / "data" / "jobs_async.json"
    assert registry.sync_jobs.job_prefix == "sync"
    assert registry.check_jobs.job_prefix == "check"
    assert registry.async_jobs.job_prefix == "task"
    assert exports["JOBS"] is registry.jobs
    assert exports["SUBMIT_LOCK"] is registry.submit_lock
    assert exports["TASK_EXECUTOR"] is registry.task_executor


def test_web_job_registry_view_tracks_legacy_alias_overrides():
    class Limiter:
        def check(self, **kwargs):
            return {"ok": True, **kwargs}

    class Executor:
        def __init__(self):
            self.calls = []

        def submit(self, target, *args):
            self.calls.append((target, args))

    original_web_attrs = _snapshot_web_attrs(*_WEB_JOB_EXPORTS)
    override_jobs = JobStore()
    override_sync_jobs = JobStore()
    override_check_jobs = JobStore()
    override_lock = threading.Lock()
    override_limiter = Limiter()
    override_executor = Executor()

    web.JOBS = override_jobs
    web.SYNC_JOBS = override_sync_jobs
    web.CHECK_JOBS = override_check_jobs
    web.SUBMIT_LOCK = override_lock
    web.RATE_LIMITER = override_limiter
    web.TASK_EXECUTOR = override_executor
    try:
        registry = web._job_registry_view()
        assert registry.jobs is override_jobs
        assert registry.sync_jobs is override_sync_jobs
        assert registry.check_jobs is override_check_jobs
        assert registry.submit_lock is override_lock
        assert registry.rate_limiter is override_limiter
        assert registry.task_executor is override_executor

        override_lock.acquire()
        try:
            conflict = web.active_auxiliary_operation()
        finally:
            override_lock.release()
        assert conflict[0] == "submit"

        assert web.rate_limit_request("session", "POST", "/api/config") == {
            "ok": True,
            "key": "session",
            "method": "POST",
            "path": "/api/config",
        }

        target = object()
        web._submit_background_job(target, "payload")
        assert override_executor.calls == [(target, ("payload",))]
    finally:
        _restore_web_attrs(original_web_attrs)


def test_run_job_failure_records_error_context(monkeypatch, tmp_path):
    original_web_attrs = _snapshot_web_attrs("JOBS")
    web.JOBS = JobStore(tmp_path / "jobs.json")
    job_id = web.JOBS.create()

    def boom(_run_config, **_kwargs):
        raise RuntimeError("secret-token-123 failed")

    monkeypatch.setattr(web, "run_config_from_payload", lambda payload: RunConfig(environment="production"))
    monkeypatch.setattr(web, "run_pipeline_from_config", boom)
    try:
        web.run_job(job_id, {})
        job = web.JOBS.get(job_id)
    finally:
        _restore_web_attrs(original_web_attrs)

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
    port = _free_port_or_skip(start=8876)

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


def test_sse_handler_accepts_stream_token_query_for_session_auth():
    session_id, _csrf_token = web._create_session()
    try:
        stream_token = web._stream_token_for_session(session_id)

        class _Probe(web.Handler):
            def __init__(self, path):
                self.path = path
                self.headers = {"Cookie": web._session_cookie_header(session_id)}
                self.json_calls = []

            def _json(self, payload, status=200, *, extra_headers=None):
                self.json_calls.append((payload, status, extra_headers or []))

        for path in ("/api/stream", "/sse"):
            handler = _Probe(path)
            handler._handle_sse_stream(f"stream_token={stream_token}")

            assert handler.json_calls
            payload, status, _headers = handler.json_calls[0]
            assert status == 400
            assert payload["error_code"] == "VALIDATION_ERROR"
            assert payload["error"] == "missing job_id"
    finally:
        web._expire_session(session_id)


@pytest.mark.skipif(os.getenv("CI") == "true", reason="skipping live server test in CI environment")
def test_live_sse_alias_accepts_rendered_stream_token():
    port = _free_port_or_skip(start=8986)
    url = web.serve(port=port, open_browser=False)
    try:
        root_response = urllib.request.urlopen(url, timeout=5)
        cookie = root_response.headers.get("Set-Cookie", "")
        html = root_response.read().decode("utf-8")
        stream_match = re.search(r'<meta name="brain-alpha-stream" content="([^"]+)"', html)
        if not stream_match:
            stream_match = re.search(r"var STREAM_TOKEN = '([^']+)'", html)
        assert stream_match
        assert stream_match.group(1) != "__BRAIN_ALPHA_OPS_STREAM_TOKEN__"

        request = urllib.request.Request(
            f"{url.rstrip('/')}/sse?job_id=missing_job&stream_token={stream_match.group(1)}",
            headers={"Cookie": cookie},
        )
        with urllib.request.urlopen(request, timeout=5) as sse_response:
            event_line = sse_response.readline().decode("utf-8")

            assert sse_response.status == 200
            assert sse_response.headers.get("Content-Type") == "text/event-stream"
            assert '"job_id": "missing_job"' in event_line
            assert '"error": "job not found"' in event_line
    finally:
        web.shutdown_server()


@pytest.mark.skipif(os.getenv("CI") == "true", reason="skipping live server test in CI environment")
def test_live_react_preview_serves_dist_assets_and_keeps_inline_default(monkeypatch):
    port = _free_port_or_skip(start=9046)
    monkeypatch.setenv("BRAIN_ALPHA_OPS_WEB_FRONTEND", "react")
    web.web_html.reset_html_cache()
    url = web.serve(port=port, open_browser=False)
    try:
        cookie, csrf_token, html = _live_react_session_credentials(url)
        asset_paths = re.findall(r'/(assets/[^"\']+)', html)

        assert '<div id="root"></div>' in html
        assert "var CSRF_TOKEN" not in html
        assert asset_paths
        assert any(path.endswith(".js") for path in asset_paths)
        assert any(path.endswith(".css") for path in asset_paths)

        for asset_path in asset_paths:
            asset_response = urllib.request.urlopen(f"{url.rstrip('/')}/{asset_path}", timeout=5)
            asset_body = asset_response.read(128)
            assert asset_response.status == 200
            assert asset_body
            assert asset_response.headers.get("Cache-Control") == "no-store"
            assert asset_response.headers.get("X-Content-Type-Options") == "nosniff"

        config_request = urllib.request.Request(
            f"{url.rstrip('/')}/api/config",
            headers={
                "Cookie": cookie,
                "X-Brain-Alpha-CSRF": csrf_token,
            },
        )
        config_response = urllib.request.urlopen(config_request, timeout=5)
        config_body = json.loads(config_response.read().decode("utf-8"))
        assert config_response.status == 200
        assert config_body["ok"] is True
        assert config_body["config"]["environment"]
    finally:
        web.shutdown_server()
        web.web_html.reset_html_cache()

    default_port = _free_port_or_skip(start=9056)
    monkeypatch.delenv("BRAIN_ALPHA_OPS_WEB_FRONTEND", raising=False)
    web.web_html.reset_html_cache()
    default_url = web.serve(port=default_port, open_browser=False)
    try:
        default_response = urllib.request.urlopen(default_url, timeout=5)
        default_html = default_response.read().decode("utf-8")
        assert default_response.status == 200
        assert 'lang="zh-CN"' in default_html
        assert 'name="brain-alpha-csrf"' in default_html
        assert '<div id="root"></div>' in default_html
    finally:
        web.shutdown_server()
        web.web_html.reset_html_cache()


@pytest.mark.skipif(os.getenv("CI") == "true", reason="skipping live server test in CI environment")
def test_live_run_post_requires_rendered_session_csrf_and_replay_headers():
    port = _free_port_or_skip(start=9086)
    url = web.serve(port=port, open_browser=False)
    try:
        root_response = urllib.request.urlopen(url, timeout=5)
        html = root_response.read().decode("utf-8")

        assert root_response.headers.get("Set-Cookie", "")
        assert "brain-alpha-csrf" in html or "CSRF_TOKEN" in html

        request = urllib.request.Request(
            f"{url.rstrip('/')}/api/run",
            data=json.dumps({"autoSubmit": True, "auto_submit": True}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(request, timeout=5)

        body = json.loads(exc_info.value.read().decode("utf-8"))
        assert exc_info.value.code == 403
        assert body["error_code"] == "SESSION_INVALID"
    finally:
        web.shutdown_server()


@pytest.mark.skipif(os.getenv("CI") == "true", reason="skipping live server test in CI environment")
def test_live_config_save_accepts_rendered_session_csrf_and_replay_headers():
    port = _free_port_or_skip(start=8996)
    saved_payloads = []
    original_save = web.save_run_config_payload
    web.save_run_config_payload = lambda payload: (
        saved_payloads.append(payload)
        or {"ok": True, "path": "config/run_config.json", "config": {"environment": payload.get("environment")}}
    )
    url = web.serve(port=port, open_browser=False)
    try:
        root_response = urllib.request.urlopen(url, timeout=5)
        cookie = str(root_response.headers.get("Set-Cookie", "")).split(";", 1)[0]
        html = root_response.read().decode("utf-8")
        csrf_match = re.search(r'<meta name="brain-alpha-csrf" content="([^"]+)"', html)
        assert csrf_match
        assert csrf_match.group(1) != "__BRAIN_ALPHA_OPS_CSRF_TOKEN__"

        payload = {"environment": "production", "settings": {"region": "USA"}}
        request = urllib.request.Request(
            f"{url.rstrip('/')}/api/config",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Cookie": cookie,
                "X-Brain-Alpha-CSRF": csrf_match.group(1),
                "X-Brain-Alpha-Request-ID": f"config_save_{int(time.time() * 1000)}",
                "X-Brain-Alpha-Request-Timestamp": str(int(time.time() * 1000)),
            },
            method="POST",
        )
        response = urllib.request.urlopen(request, timeout=5)
        body = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert body["ok"] is True
        assert body["config"]["environment"] == "production"
        assert saved_payloads == [payload]
    finally:
        web.save_run_config_payload = original_save
        web.shutdown_server()


@pytest.mark.skipif(os.getenv("CI") == "true", reason="skipping live server test in CI environment")
def test_live_generate_candidates_accepts_count_and_rejects_out_of_range_value():
    port = _free_port_or_skip(start=9006)
    submitted_jobs = []
    original_web_attrs = _snapshot_web_attrs("ASYNC_JOBS")
    original_submit = web._submit_background_job
    web.ASYNC_JOBS = JobStore()
    web._submit_background_job = lambda target, *args: submitted_jobs.append((target, *args))
    url = web.serve(port=port, open_browser=False)
    try:
        root_response = urllib.request.urlopen(url, timeout=5)
        cookie = str(root_response.headers.get("Set-Cookie", "")).split(";", 1)[0]
        html = root_response.read().decode("utf-8")
        csrf_match = re.search(r'<meta name="brain-alpha-csrf" content="([^"]+)"', html)
        assert csrf_match

        def post_count(count: int, request_id: str):
            request = urllib.request.Request(
                f"{url.rstrip('/')}/api/generate_candidates",
                data=json.dumps({"count": count}).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Cookie": cookie,
                    "X-Brain-Alpha-CSRF": csrf_match.group(1),
                    "X-Brain-Alpha-Request-ID": request_id,
                    "X-Brain-Alpha-Request-Timestamp": str(int(time.time() * 1000)),
                },
                method="POST",
            )
            return urllib.request.urlopen(request, timeout=5)

        response = post_count(7, f"generate_valid_{int(time.time() * 1000)}")
        body = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert body["ok"] is True
        assert body["task_id"]
        assert len(submitted_jobs) == 1
        assert submitted_jobs[0][2] == {"count": 7}

        with pytest.raises(urllib.error.HTTPError) as exc_info:
            post_count(101, f"generate_invalid_{int(time.time() * 1000)}")
        error_body = json.loads(exc_info.value.read().decode("utf-8"))
        assert exc_info.value.code == 400
        assert error_body["error_code"] == "VALIDATION_ERROR"
        assert "between 1 and 100" in error_body["error"]
        assert len(submitted_jobs) == 1
    finally:
        _restore_web_attrs(original_web_attrs)
        web._submit_background_job = original_submit
        web.shutdown_server()


@pytest.mark.skipif(os.getenv("CI") == "true", reason="skipping live server test in CI environment")
def test_live_api_rate_limiter_throttles_same_session_writes_and_recovers_after_window():
    port = _free_port_or_skip(start=9016)
    saved_payloads = []
    now = [100.0]
    limiter = RequestRateLimiter(RateLimitPolicy(window_seconds=10, read_requests=99, write_requests=1, submit_requests=1))
    original_save = web.save_run_config_payload
    original_rate_limit_request = web.rate_limit_request
    web.save_run_config_payload = lambda payload: (
        saved_payloads.append(payload)
        or {"ok": True, "path": "config/run_config.json", "config": {"environment": payload.get("environment")}}
    )
    web.rate_limit_request = lambda key, method, path: limiter.check(key=key, method=method, path=path, now=now[0])
    url = web.serve(port=port, open_browser=False)
    try:
        cookie, csrf_token = _live_session_credentials(url)

        response = _live_json_post(
            url,
            "/api/config",
            {"environment": "production"},
            cookie=cookie,
            csrf_token=csrf_token,
            request_id=f"rate_first_{time.time_ns()}",
        )
        body = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert body["ok"] is True
        assert len(saved_payloads) == 1

        now[0] = 101.0
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            _live_json_post(
                url,
                "/api/config",
                {"environment": "staging"},
                cookie=cookie,
                csrf_token=csrf_token,
                request_id=f"rate_second_{time.time_ns()}",
            )
        error_body = json.loads(exc_info.value.read().decode("utf-8"))
        assert exc_info.value.code == 429
        assert exc_info.value.headers.get("Retry-After") == "9"
        assert error_body["error_code"] == "RATE_LIMITED"
        assert len(saved_payloads) == 1

        now[0] = 111.0
        recovered = _live_json_post(
            url,
            "/api/config",
            {"environment": "research"},
            cookie=cookie,
            csrf_token=csrf_token,
            request_id=f"rate_recovered_{time.time_ns()}",
        )
        recovered_body = json.loads(recovered.read().decode("utf-8"))
        assert recovered.status == 200
        assert recovered_body["ok"] is True
        assert saved_payloads == [{"environment": "production"}, {"environment": "research"}]
    finally:
        web.save_run_config_payload = original_save
        web.rate_limit_request = original_rate_limit_request
        web.shutdown_server()


@pytest.mark.skipif(os.getenv("CI") == "true", reason="skipping live server test in CI environment")
def test_live_check_batch_rejects_malformed_candidates_before_starting_background_job():
    port = _free_port_or_skip(start=9026)
    submitted_jobs = []
    original_web_attrs = _snapshot_web_attrs("CHECK_JOBS", "SYNC_JOBS", "SUBMIT_LOCK")
    original_submit = web._submit_background_job
    web.CHECK_JOBS = JobStore()
    web.SYNC_JOBS = JobStore()
    web.SUBMIT_LOCK = threading.Lock()
    web._submit_background_job = lambda target, *args: submitted_jobs.append((target, *args))
    url = web.serve(port=port, open_browser=False)
    try:
        cookie, csrf_token = _live_session_credentials(url)

        with pytest.raises(urllib.error.HTTPError) as exc_info:
            _live_json_post(
                url,
                "/api/check_batch",
                {"check_candidates": {}},
                cookie=cookie,
                csrf_token=csrf_token,
                request_id=f"check_batch_invalid_{time.time_ns()}",
            )
        error_body = json.loads(exc_info.value.read().decode("utf-8"))
        assert exc_info.value.code == 400
        assert error_body["error_code"] == "VALIDATION_ERROR"
        assert "check_candidates" in error_body["error"]
        assert submitted_jobs == []
        assert web.CHECK_JOBS.latest_active() is None

        response = _live_json_post(
            url,
            "/api/check_batch",
            {"check_candidates": [{"alpha_id": "alpha_live_1"}]},
            cookie=cookie,
            csrf_token=csrf_token,
            request_id=f"check_batch_valid_{time.time_ns()}",
        )
        body = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert body["ok"] is True
        assert body["job_id"]
        assert len(submitted_jobs) == 1
        assert submitted_jobs[0][2] == {"check_candidates": [{"alpha_id": "alpha_live_1"}]}
    finally:
        _restore_web_attrs(original_web_attrs)
        web._submit_background_job = original_submit
        web.shutdown_server()


@pytest.mark.skipif(os.getenv("CI") == "true", reason="skipping live server test in CI environment")
def test_live_alpha_id_validation_rejects_check_submit_and_batch_before_side_effects():
    port = _free_port_or_skip(start=9036)
    checked_payloads = []
    submitted_payloads = []
    background_jobs = []
    original_check_candidate = web.check_candidate
    original_submit_candidate = web.submit_candidate
    original_web_attrs = _snapshot_web_attrs("ASYNC_JOBS", "SUBMIT_LOCK")
    original_submit_background = web._submit_background_job
    web.check_candidate = lambda payload: checked_payloads.append(payload) or {"ok": True}
    web.submit_candidate = lambda payload: submitted_payloads.append(payload) or {"ok": True}
    web.ASYNC_JOBS = JobStore()
    web._submit_background_job = lambda target, *args: background_jobs.append((target, *args))
    web.SUBMIT_LOCK = threading.Lock()
    url = web.serve(port=port, open_browser=False)
    try:
        cookie, csrf_token = _live_session_credentials(url)

        for path, payload, expected_fragment in (
            ("/api/check", {"alpha_id": "bad id!"}, "alpha_id"),
            ("/api/submit", {"alpha_id": "bad id!"}, "alpha_id"),
            ("/api/submit_batch", {"alpha_ids": ["good_1", "bad id!"]}, "alpha_ids[]"),
        ):
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                _live_json_post(
                    url,
                    path,
                    payload,
                    cookie=cookie,
                    csrf_token=csrf_token,
                    request_id=f"invalid_alpha_{path.rsplit('/', 1)[-1]}_{time.time_ns()}",
                )
            error_body = json.loads(exc_info.value.read().decode("utf-8"))
            assert exc_info.value.code == 400
            assert error_body["error_code"] == "VALIDATION_ERROR"
            assert expected_fragment in error_body["error"]

        assert checked_payloads == []
        assert submitted_payloads == []
        assert background_jobs == []
        assert web.SUBMIT_LOCK.locked() is False
        assert web.ASYNC_JOBS.latest_active() is None
    finally:
        web.check_candidate = original_check_candidate
        web.submit_candidate = original_submit_candidate
        _restore_web_attrs(original_web_attrs)
        web._submit_background_job = original_submit_background
        web.shutdown_server()


@pytest.mark.skipif(os.getenv("CI") == "true", reason="skipping live server test in CI environment")
def test_web_responses_include_security_headers():
    port = _free_port_or_skip(start=8976)
    url = web.serve(port=port, open_browser=False)
    try:
        root_response = urllib.request.urlopen(url, timeout=5)
        assert root_response.headers.get("X-Content-Type-Options") == "nosniff"
        assert root_response.headers.get("X-Frame-Options") == "DENY"
        assert root_response.headers.get("Referrer-Policy") == "no-referrer"
        csp = root_response.headers.get("Content-Security-Policy", "")
        assert "frame-ancestors 'none'" in csp
        assert "script-src 'self'" in csp
        assert "script-src 'self' 'unsafe-inline'" not in csp
        assert "style-src 'self'" in csp
        assert "style-src 'self' 'unsafe-inline'" not in csp
        assert "'sha256-" in csp
    finally:
        web.shutdown_server()


def test_remote_bind_requires_explicit_allow_remote():
    port = _free_port_or_skip(start=9076, host="127.0.0.1")

    with pytest.raises(ValueError, match="allow_remote"):
        web.serve(port=port, host="0.0.0.0", open_browser=False)


def test_remote_bind_requires_admin_token_env(monkeypatch):
    config = RunConfig(environment="production")
    config.web.admin_token_env = "BRAIN_ALPHA_OPS_TEST_ADMIN_TOKEN"
    monkeypatch.setattr(web, "load_run_config", lambda *args, **kwargs: config)
    monkeypatch.delenv("BRAIN_ALPHA_OPS_TEST_ADMIN_TOKEN", raising=False)

    with pytest.raises(ValueError, match="admin token env var"):
        web.serve(port=9077, host="127.0.0.1", open_browser=False, allow_remote=True)


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
        official_metrics=_complete_official_metrics(),
        scorecard={"total_score": 91, "decision_band": "submit_candidate"},
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

    assert result["submittable"] is False
    assert result["status"] == "BLOCKED"
    context_check = next(item for item in result["checks"] if item["name"] == "context_health_preflight")
    assert context_check["passed"] is False
    assert result["context_health"]["blocking_flags"] == ["rate_limit_pressure"]
    assert result["observability_preflight"]["requires_confirmation"] is True
    assert result["observability_preflight"]["blocking_flags"] == ["rate_limit_pressure"]


def test_observability_submission_preflight_includes_official_call_guard(monkeypatch, tmp_path):
    storage = tmp_path / "data"
    storage.mkdir()
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(storage)
    registry = WebJobRegistry.create(storage)
    monkeypatch.setattr(web, "JOB_REGISTRY", registry)
    for name, value in registry.legacy_exports().items():
        monkeypatch.setattr(web, name, value, raising=False)
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
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path)
    config.ops.budget.require_cloud_sync = False
    expression = "rank(ts_delta(close, 20))"
    existing = Candidate(
        alpha_id="old",
        expression=expression,
        family="Momentum",
        hypothesis="already submitted",
        official_alpha_id="official_old",
        official_metrics=_complete_official_metrics(),
        scorecard={"total_score": 91, "decision_band": "submit_candidate"},
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
        official_metrics=_complete_official_metrics(),
        scorecard={"total_score": 91, "decision_band": "submit_candidate"},
        gate={"submission_ready": True, "failed_reasons": []},
        lifecycle_status="submission_ready",
    ).to_dict()

    monkeypatch.setattr(web, "run_config_from_payload", lambda payload: config)

    result = web.submit_candidate({"candidate": candidate, "confirm_submit": True})

    assert result["ok"] is False
    assert result["error_code"] == "SUBMIT_DUPLICATE_EXPRESSION"
    assert result["error_category"] == "conflict"
    assert "action" in result


def test_submission_preflight_reports_stale_cloud_code(monkeypatch, tmp_path):
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path)
    config.ops.budget.require_cloud_sync = True
    candidate = Candidate(
        alpha_id="a1",
        expression="rank(ts_delta(close, 20))",
        family="Momentum",
        hypothesis="stale cloud",
        official_alpha_id="official_1",
        official_metrics=_complete_official_metrics(),
        scorecard={"total_score": 91, "decision_band": "submit_candidate"},
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
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path)
    config.ops.budget.require_cloud_sync = False
    candidate = Candidate(
        alpha_id="a1",
        expression="rank(ts_delta(close, 20))",
        family="Momentum",
        hypothesis="blocked observability",
        official_alpha_id="official_1",
        official_metrics=_complete_official_metrics(),
        scorecard={"total_score": 91, "decision_band": "submit_candidate"},
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

    blocked = web.submit_candidate({"candidate": candidate, "confirm_submit": True})
    confirmed = web.submit_candidate({"candidate": candidate, "confirm_submit": True, "confirm_observability_risk": True})

    assert blocked["ok"] is False
    assert blocked["error_code"] == "SUBMIT_OBSERVABILITY_CONFIRMATION_REQUIRED"
    assert blocked["observability_preflight"]["blocking_flags"] == ["rate_limit_pressure"]
    assert confirmed["ok"] is True
    assert submitted["called"] == 1


def test_submit_candidate_requires_confirmation_when_observability_preflight_fails(monkeypatch, tmp_path):
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path)
    config.ops.budget.require_cloud_sync = False
    candidate = Candidate(
        alpha_id="a1",
        expression="rank(ts_delta(close, 20))",
        family="Momentum",
        hypothesis="preflight unavailable",
        official_alpha_id="official_1",
        official_metrics=_complete_official_metrics(),
        scorecard={"total_score": 91, "decision_band": "submit_candidate"},
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

    blocked = web.submit_candidate({"candidate": candidate, "confirm_submit": True})
    confirmed = web.submit_candidate({"candidate": candidate, "confirm_submit": True, "confirm_observability_risk": True})

    assert blocked["ok"] is False
    assert blocked["error_code"] == "SUBMIT_OBSERVABILITY_CONFIRMATION_REQUIRED"
    assert blocked["observability_preflight"]["blocking_flags"] == ["observability_preflight_unavailable"]
    assert confirmed["ok"] is True
    assert submitted["called"] == 1


def test_submit_batch_requires_observability_confirmation(monkeypatch, tmp_path):
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path)
    candidate = Candidate(
        alpha_id="a1",
        expression="rank(ts_delta(close, 20))",
        family="Momentum",
        hypothesis="batch blocked observability",
        official_alpha_id="official_1",
        official_metrics=_complete_official_metrics(),
        scorecard={"total_score": 91, "decision_band": "submit_candidate"},
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

    result = web.submit_batch({"alpha_ids": ["a1"], "submit_candidates": [candidate], "confirm_submit": True})

    assert result["ok"] is False
    assert result["error_code"] == "SUBMIT_OBSERVABILITY_CONFIRMATION_REQUIRED"
    assert result["observability_preflight"]["blocking_flags"] == ["backtest_failure_rate_elevated"]


def test_submit_batch_requires_confirmation_when_observability_preflight_fails(monkeypatch, tmp_path):
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path)
    candidate = Candidate(
        alpha_id="a1",
        expression="rank(ts_delta(close, 20))",
        family="Momentum",
        hypothesis="batch preflight unavailable",
        official_alpha_id="official_1",
        official_metrics=_complete_official_metrics(),
        scorecard={"total_score": 91, "decision_band": "submit_candidate"},
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

    result = web.submit_batch({"alpha_ids": ["a1"], "submit_candidates": [candidate], "confirm_submit": True})

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
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(storage)
    registry = WebJobRegistry.create(storage)
    monkeypatch.setattr(web, "JOB_REGISTRY", registry)
    for name, value in registry.legacy_exports().items():
        monkeypatch.setattr(web, name, value, raising=False)
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
    config = RunConfig(environment="production")
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
    config = RunConfig(environment="production")
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
    config = RunConfig(environment="production")
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
    config = RunConfig(environment="production")
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
    config = RunConfig(environment="production")
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
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path)
    monkeypatch.setattr(web, "load_run_config", lambda *args, **kwargs: config)

    payload = save_assistant_guidance_payload(
        {
            "environment": "production",
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
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path)
    monkeypatch.setattr(web, "load_run_config", lambda *args, **kwargs: config)

    payload = save_assistant_guidance_payload(
        {
            "environment": "production",
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
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path)
    monkeypatch.setattr(web, "load_run_config", lambda *args, **kwargs: config)
    captured = {}

    def fake_set_experience_guidance(self, patterns):
        captured["patterns"] = patterns

    monkeypatch.setattr("brain_alpha_ops.research.generator.CandidateGenerator.set_experience_guidance", fake_set_experience_guidance)

    payload = generate_candidates_payload(
        {
            "environment": "production",
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
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path)
    monkeypatch.setattr(web, "load_run_config", lambda *args, **kwargs: config)
    monkeypatch.setattr(
        "brain_alpha_ops.research.generator.CandidateGenerator.set_experience_guidance",
        lambda self, patterns: None,
    )

    payload = generate_candidates_payload(
        {
            "environment": "production",
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
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path)
    (tmp_path / "checks.jsonl").write_text('{"ok":true}\nnot-json\n', encoding="utf-8")
    monkeypatch.setattr(web, "load_run_config", lambda *args, **kwargs: config)

    stats = web._read_storage_jsonl_stats("checks.jsonl", limit=10)

    assert stats["exists"] is True
    assert stats["parsed_count"] == 1
    assert stats["skipped_invalid_count"] == 1


def test_read_official_context_json_logs_invalid_file(monkeypatch, tmp_path, caplog):
    config = RunConfig(environment="production")
    config.ops.storage_dir = str(tmp_path)
    (tmp_path / "official_fields.json").write_text("{bad-json", encoding="utf-8")
    monkeypatch.setattr(web, "load_run_config", lambda *args, **kwargs: config)
    monkeypatch.setattr(web, "runtime_project_root", lambda: tmp_path / "missing_runtime")

    with caplog.at_level("WARNING", logger="brain_alpha_ops.web"):
        rows = web._read_official_context_json("official_fields.json")

    assert isinstance(rows, list)
    assert "failed to read official context file" in caplog.text
