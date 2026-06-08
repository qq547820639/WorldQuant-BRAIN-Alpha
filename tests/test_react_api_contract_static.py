from __future__ import annotations

import re
from pathlib import Path

from brain_alpha_ops.web_routes import GET_ROUTES, POST_ROUTES, route_for


ROOT = Path(__file__).resolve().parents[1]
REACT_SRC = ROOT / "brain_alpha_ops" / "web" / "react_app" / "src"
REACT_INDEX = ROOT / "brain_alpha_ops" / "web" / "react_app" / "index.html"
REACT_DIST = ROOT / "brain_alpha_ops" / "web" / "react_app" / "dist"
README = ROOT / "README.md"
SYSTEM_EVALUATION_DOC = ROOT / "docs" / "COMPREHENSIVE_SYSTEM_EVALUATION_20260514.md"
SMOKE_SCRIPT = ROOT / "scripts" / "browser_react_artifact_smoke.mjs"


def _source(path: str) -> str:
    return (REACT_SRC / path).read_text(encoding="utf-8")


def _react_source_files() -> list[Path]:
    return sorted(path for path in REACT_SRC.rglob("*") if path.suffix in {".ts", ".tsx"})


def _normalize_route(url: str) -> str:
    path = url.split("?", 1)[0].split("${", 1)[0]
    return path.rstrip("/")


def test_react_api_paths_are_registered_in_backend_routes():
    backend_paths = set(GET_ROUTES) | set(POST_ROUTES)
    frontend_paths: set[str] = set()

    for path in _react_source_files():
        source = path.read_text(encoding="utf-8")
        for match in re.finditer(r'["`](/(?:api|sse)[^"`]*)["`]', source):
            frontend_paths.add(_normalize_route(match.group(1)))

    assert frontend_paths
    assert frontend_paths <= backend_paths


def test_react_dashboard_contract_uses_snapshot_aliases_backed_by_get_routes():
    source = _source("components/Dashboard.tsx")

    assert 'statusApi.call("/api/production-validation/status")' in source
    assert 'cloudApi.call("/api/snapshot/cloud?limit=10")' in source
    assert 'memoryApi.call("/api/snapshot/memory?limit=100&top_n=5")' in source
    assert route_for("GET", "/api/production-validation/status") is not None
    assert route_for("GET", "/api/snapshot/cloud").handler == "cloud_alphas"
    assert route_for("GET", "/api/snapshot/memory").handler == "research_memory"


def test_react_candidate_and_scoring_contracts_match_backend_routes():
    candidates = _source("components/CandidateTable.tsx")
    scoring = _source("components/ScoringPanel.tsx")

    assert "callApi(`/api/candidates?limit=${CANDIDATE_FETCH_LIMIT}`)" in candidates
    assert 'callCheckResultsApi<{ items?: CandidateCheckResult[] }>("/api/check_results")' in candidates
    assert 'callApi<{ job_id: string; task_id?: string }>("/api/generate_candidates"' in candidates
    assert "useSSE(taskId ? `/sse?job_id=${encodeURIComponent(taskId)}`" in candidates
    assert 'scoreApi.call("/api/scoring/evaluate"' in scoring
    assert 'attributionApi.call("/api/scoring/attribution"' in scoring
    assert "useSSE(scoreTaskId ? `/sse?job_id=${encodeURIComponent(scoreTaskId)}`" in scoring
    assert "nonEmpty(scoring?.hard_gates) || nonEmpty(attributionApi.data?.hard_gates)" in scoring
    assert "页面会自动完成官方评分、归因分析和门禁复核" not in scoring
    assert "归因分析" in scoring
    assert "官方门禁检查" in scoring
    assert "点击评分以通过 /api/scoring/evaluate" not in scoring

    assert route_for("GET", "/api/candidates") is not None
    assert route_for("GET", "/api/check_results") is not None
    assert route_for("POST", "/api/generate_candidates") is not None
    assert route_for("GET", "/sse") is not None
    assert route_for("POST", "/api/scoring/evaluate") is not None
    assert route_for("POST", "/api/scoring/attribution") is not None


def test_react_submission_config_and_job_contracts_match_backend_routes():
    submission = _source("components/SubmissionPanel.tsx")
    confirm = _source("components/SubmissionConfirmPanel.tsx")
    app = _source("App.tsx")
    config = _source("components/ConfigPanel.tsx")
    monitor = _source("components/JobMonitor.tsx")

    assert "SubmissionConfirmPanel notify={notify}" in submission
    assert "/api/submit" not in submission
    assert "/api/submit_batch" not in submission
    assert 'callReadiness<SubmitReadinessResponse>("/api/submit_readiness")' in confirm
    assert route_for("GET", "/api/submit_readiness") is not None
    for endpoint in ("/api/config", "/api/config_schema"):
        assert f'"{endpoint}"' in config
        assert route_for("GET", endpoint) is not None
    assert 'connectionApi.call("/api/test_connection"' in config
    assert route_for("POST", "/api/config") is not None
    assert route_for("POST", "/api/test_connection") is not None
    assert 'lazy(() => import("@/components/ConfigPanel"))' in app
    assert "import SubmissionPanel" not in app
    assert "function CredentialQuickStart" in app
    assert 'connectionApi.call("/api/test_connection"' in app
    assert "JobMonitor notify={notify} credentials={credentials} jobState={jobState}" in app
    assert "凭证与连接" in app
    assert "凭证只保留在当前页面，不写入文件或运行记录。" in app
    assert 'case "config":' in app
    assert "credentials={credentials}" in app
    assert "onCredentialsChange={setCredentials}" in app
    assert 'api.call<{ job_id: string }>("/api/run"' in monitor
    assert 'api.call("/api/production-validation/stop", { method: "POST"' in monitor
    assert "const sseUrl = jobId ? `/sse?job_id=${encodeURIComponent(jobId)}` : null;" in monitor
    assert "body: JSON.stringify(buildRunPayload(resume, credentials))" in monitor
    assert "autoSubmit: false" not in monitor
    assert "auto_submit: false" not in monitor
    assert "auto_submitted" in monitor
    assert "页面凭证为空" in monitor
    assert "填写凭证" in monitor
    assert "if (!running || !jobId) return;" in monitor
    assert "api.call<JobStatus>(`/api/production-validation/status?job_id=${encodeURIComponent(jobId)}`)" in monitor
    assert "运行证明" not in monitor
    assert "submittedThisRun" in monitor
    assert "autoSubmitted" in monitor
    assert route_for("POST", "/api/run") is not None
    assert route_for("POST", "/api/production-validation/stop") is not None
    assert route_for("GET", "/api/production-validation/status") is not None


def test_react_cancel_helper_stays_on_production_validation_stop_route():
    source_text = "\n".join(path.read_text(encoding="utf-8") for path in _react_source_files())
    cancel = _source("api/jobCancel.ts")

    assert '"/api/production-validation/stop"' in cancel
    assert '"/api/stop"' not in source_text
    assert '"/api/cancel"' not in source_text


def test_default_react_app_and_dist_do_not_expose_raw_submit_surface():
    app = _source("App.tsx")
    state_cards = _source("components/StateCards.tsx")
    source_text = "\n".join(path.read_text(encoding="utf-8") for path in _react_source_files())
    dist_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in REACT_DIST.rglob("*")
        if path.suffix in {".html", ".js", ".css"}
    )
    raw_submit_pattern = re.compile(r"/api/(?:submit|submit_batch)(?:$|[?#'\"`])")

    assert "import SubmissionPanel" not in app
    assert "SubmissionPanel notify={notify}" not in app
    assert '<SubmissionConfirmPanel notify={notify} />' in app
    assert 'title: "手动提交"' not in state_cards
    assert "进入提交" not in state_cards
    assert raw_submit_pattern.search(source_text) is None
    assert raw_submit_pattern.search(dist_text) is None
    assert "手动提交" not in dist_text


def test_react_official_operations_is_web_operator_console_not_cli_surface():
    app = _source("App.tsx")
    state_cards = _source("components/StateCards.tsx")
    operations = _source("components/OfficialOperationsPanel.tsx")
    types = _source("types/index.ts")

    assert '"official_operations"' in types
    assert '"visual_terminal"' not in types
    assert 'official_operations: "官方操作"' in app
    assert 'case "official_operations":' in app
    assert "OfficialOperationsPanel notify={notify} credentials={credentials}" in app
    assert "VisualTerminalPanel" not in app
    assert "visual_terminal" not in app
    assert 'title: "官方操作"' in state_cards
    assert 'description: "按钮驱动的官方上下文、合规与阻断复核"' in state_cards
    assert "visual_terminal" not in state_cards
    assert "/api/sync_alphas" in operations
    assert "/api/sync_status" in operations
    assert "/api/sync_cancel" in operations
    assert "/api/submit_readiness" in operations
    assert "/api/check_results" in operations
    assert "...credentialsPayload(credentials)" in operations
    assert "if (password) payload.password = password;" in operations
    assert route_for("POST", "/api/sync_alphas") is not None
    assert route_for("GET", "/api/sync_status") is not None
    assert route_for("POST", "/api/sync_cancel") is not None
    assert route_for("GET", "/api/submit_readiness") is not None
    assert route_for("GET", "/api/check_results") is not None
    assert re.search(r"['\"`]\/api\/submit(?:[?/'\"`]|$)", operations) is None
    assert re.search(r"['\"`]\/api\/submit_batch(?:[?/'\"`]|$)", operations) is None
    assert "不展示命令或路径" in operations
    assert "用户只需留在浏览器里查看进度和结果" in operations
    assert "官方操作入口" in operations
    assert "同一个页面" in operations
    assert "Web 控制台内" not in operations
    assert "Web 操作台" not in operations
    assert "可视化终端" not in operations
    assert "任务页" not in operations
    assert "visual_terminal" not in operations
    assert "TerminalMode" not in operations
    assert "TerminalLogEntry" not in operations
    assert "用户打开命令行" not in operations
    assert "shell 命令" not in operations
    assert "终端界面" not in operations
    assert "终端进度" not in operations


def test_browser_react_smoke_fails_when_web_operator_and_alpha_flows_are_not_exercised():
    smoke = SMOKE_SCRIPT.read_text(encoding="utf-8")

    assert "report.officialOperations = {" in smoke
    assert "report.alphaFlow = {" in smoke
    assert "const officialOperations = interactions.officialOperations || {};" in smoke
    assert "official operations card did not expose the button-driven Web flow" in smoke
    assert "official operations did not auto-interrupt unclear refresh state" in smoke
    assert "const alphaFlow = interactions.alphaFlow || {};" in smoke
    assert "candidate generation flow was not exercised through the Web UI" in smoke
    assert "candidate generation did not request backend cancellation after ambiguous SSE state" in smoke
    assert "scoring flow did not request backend cancellation after ambiguous SSE state" in smoke

    for endpoint in (
        "/api/sync_alphas",
        "/api/sync_cancel",
        "/api/generate_candidates",
        "/api/scoring/evaluate",
        "/api/scoring/attribution",
        "/api/production-validation/stop",
    ):
        assert f'"{endpoint}"' in smoke
    assert 'requested("POST", endpoint)' in smoke
    assert "`expected mocked POST ${endpoint}`" in smoke
    assert 'requestCount("POST", endpoint) !== 0' in smoke
    assert "`unexpected submit endpoint request ${endpoint}`" in smoke

    assert 'pathname === "/api/submit" || pathname === "/api/submit_batch"' in smoke
    assert "WEB_ONLY_SUBMIT_REQUIRED" in smoke


def test_readme_keeps_operator_path_in_official_operations_area():
    readme = README.read_text(encoding="utf-8")

    assert "## Operator Quick Start" in readme
    assert "browser-only Web console" in readme
    assert "They do not run commands, pass flags, or inspect shell output" in readme
    assert "### Official Operations" in readme
    assert "does not expose direct submit buttons" in readme
    assert "## Appendix: Maintainer Verification" in readme
    assert "Operators use the Web console and its Official Operations entry instead of running verification commands" in readme
    assert "official-operations area" not in readme
    assert "Operators should stop" not in readme
    assert "大多数量化研究者偏好 CLI" not in readme
    assert "CLI 已满足基本需求" not in readme


def test_system_evaluation_keeps_cli_as_internal_automation_only():
    report = SYSTEM_EVALUATION_DOC.read_text(encoding="utf-8")

    assert "### 5.2 内部自动化接口" in report
    assert "不能作为最终用户操作路径" in report
    assert "最终用户只通过 Web 控制台与官方操作区操作" in report
    assert "不维护面向最终用户的 CLI 产品面" in report
    assert "脚本只能作为内部自动化、CI、维护者诊断接口" in report
    assert "不能作为最终用户操作路径" in report
    assert "### 5.2 CLI 交互" not in report
    assert "大多数量化研究者偏好 CLI" not in report
    assert "CLI 已满足基本需求" not in report


def test_react_snapshot_panel_contracts_match_backend_routes():
    snapshot = _source("components/SnapshotPanel.tsx")

    for endpoint in (
        "/api/snapshot/cloud",
        "/api/checkpoint_status",
        "/api/lifecycle",
        "/api/research_memory",
        "/api/research_knowledge",
        "/api/research_observability",
        "/api/prompt_runs",
        "/api/sqlite_indexes",
        "/api/latest_result",
    ):
        assert f'"{endpoint}' in snapshot
        assert route_for("GET", endpoint) is not None


def test_react_state_cards_include_checkpoint_history_entry():
    app = _source("App.tsx")
    state_cards = _source("components/StateCards.tsx")
    types = _source("types/index.ts")

    assert '"checkpoint_status"' in types
    assert 'checkpoint_status: "续跑记录"' in app
    assert 'case "checkpoint_status":' in app
    assert 'viewMode="checkpoint_status"' in app
    assert 'checkpointApi.call("/api/checkpoint_status")' in state_cards
    assert 'title: "续跑记录"' in state_cards
    assert 'description: "上次进度与运行历史回溯"' in state_cards


def test_react_fetch_helpers_keep_session_csrf_replay_and_sse_credentials():
    use_api = _source("hooks/useApi.ts")
    use_sse = _source("hooks/useSSE.ts")
    csrf_utils = _source("utils/csrf.ts")

    assert 'credentials: "same-origin"' in use_api
    assert 'headers["X-Brain-Alpha-CSRF"] = csrf' in use_api
    assert '"X-Brain-Alpha-Request-ID"' in csrf_utils
    assert '"X-Brain-Alpha-Request-Timestamp"' in csrf_utils
    assert 'headers["Content-Type"] = "application/json";' in use_api
    assert "DEFAULT_REQUEST_TIMEOUT_MS = 120000" in use_api
    assert 'signal: options?.signal ?? controller?.signal' in use_api
    assert '"请求超时，请稍后重试。"' in use_api
    assert "new EventSource(withStreamToken(streamUrl), { withCredentials: true })" in use_sse
    assert "onExhaustedRef.current?.();" in use_sse
    assert "return { connected, exhausted, reconnectAttempts, lastEvent, close };" in use_sse
    assert 'meta[name="brain-alpha-stream"]' in csrf_utils
    assert "stream_token=${encodeURIComponent(token)}" in use_sse
    assert 'const namedEvents: NamedSSEEvent[] = ["progress", "complete", "error", "heartbeat"];' in use_sse
    assert "es.addEventListener(eventName" in use_sse


def test_react_build_template_exposes_backend_token_placeholders():
    html = REACT_INDEX.read_text(encoding="utf-8")
    csrf_utils = _source("utils/csrf.ts")

    assert 'name="brain-alpha-csrf" content="__BRAIN_ALPHA_OPS_CSRF_TOKEN__"' in html
    assert 'name="brain-alpha-stream" content="__BRAIN_ALPHA_OPS_STREAM_TOKEN__"' in html
    assert 'meta[name="brain-alpha-csrf"]' in csrf_utils
