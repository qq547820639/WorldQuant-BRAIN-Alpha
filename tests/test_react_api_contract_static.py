from __future__ import annotations

import re
from pathlib import Path

from brain_alpha_ops.web_routes import GET_ROUTES, POST_ROUTES, route_for


ROOT = Path(__file__).resolve().parents[1]
REACT_SRC = ROOT / "brain_alpha_ops" / "web" / "react_app" / "src"
REACT_INDEX = ROOT / "brain_alpha_ops" / "web" / "react_app" / "index.html"


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

    assert 'statusApi.call("/api/status")' in source
    assert 'cloudApi.call("/api/snapshot/cloud?limit=10")' in source
    assert 'memoryApi.call("/api/snapshot/memory?limit=100&top_n=5")' in source
    assert route_for("GET", "/api/status") is not None
    assert route_for("GET", "/api/snapshot/cloud").handler == "cloud_alphas"
    assert route_for("GET", "/api/snapshot/memory").handler == "research_memory"


def test_react_candidate_and_scoring_contracts_match_backend_routes():
    candidates = _source("components/CandidateTable.tsx")
    scoring = _source("components/ScoringPanel.tsx")

    assert "callApi(`/api/candidates?limit=${CANDIDATE_FETCH_LIMIT}`)" in candidates
    assert 'callCheckResultsApi<{ items?: CandidateCheckResult[] }>("/api/check_results")' in candidates
    assert 'callApi<{ job_id: string; task_id?: string }>("/api/generate_candidates"' in candidates
    assert "useSSE(taskId ? `/sse?job_id=${encodeURIComponent(taskId)}`" in candidates
    assert 'callScoreApi("/api/scoring/evaluate"' in scoring
    assert 'callAttributionApi("/api/scoring/attribution"' in scoring
    assert "useSSE(scoreTaskId ? `/sse?job_id=${encodeURIComponent(scoreTaskId)}`" in scoring

    assert route_for("GET", "/api/candidates") is not None
    assert route_for("GET", "/api/check_results") is not None
    assert route_for("POST", "/api/generate_candidates") is not None
    assert route_for("GET", "/sse") is not None
    assert route_for("POST", "/api/scoring/evaluate") is not None
    assert route_for("POST", "/api/scoring/attribution") is not None


def test_react_submission_config_and_job_contracts_match_backend_routes():
    submission = _source("components/SubmissionPanel.tsx")
    config = _source("components/ConfigPanel.tsx")
    monitor = _source("components/JobMonitor.tsx")

    for endpoint in ("/api/check", "/api/submit", "/api/check_batch", "/api/submit_batch"):
        assert f'"{endpoint}"' in submission
        assert route_for("POST", endpoint) is not None
    for endpoint in ("/api/config", "/api/config_schema"):
        assert f'"{endpoint}"' in config
        assert route_for("GET", endpoint) is not None
    assert route_for("POST", "/api/config") is not None
    assert 'api.call<{ job_id: string }>("/api/run"' in monitor
    assert 'api.call("/api/stop", { method: "POST"' in monitor
    assert "const sseUrl = jobId ? `/sse?job_id=${encodeURIComponent(jobId)}` : null;" in monitor
    assert "api.call<JobStatus>(`/api/status?job_id=${encodeURIComponent(jobId || \"\")}`)" in monitor
    assert route_for("POST", "/api/run") is not None
    assert route_for("POST", "/api/stop") is not None
    assert route_for("GET", "/api/status") is not None


def test_react_snapshot_panel_contracts_match_backend_routes():
    snapshot = _source("components/SnapshotPanel.tsx")

    for endpoint in (
        "/api/snapshot/cloud",
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


def test_react_fetch_helpers_keep_session_csrf_replay_and_sse_credentials():
    use_api = _source("hooks/useApi.ts")
    use_sse = _source("hooks/useSSE.ts")

    assert 'credentials: "same-origin"' in use_api
    assert 'headers["X-Brain-Alpha-CSRF"] = csrf' in use_api
    assert 'headers["X-Brain-Alpha-Request-ID"] = createRequestId();' in use_api
    assert 'headers["X-Brain-Alpha-Request-Timestamp"] = String(Date.now());' in use_api
    assert 'headers["Content-Type"] = "application/json";' in use_api
    assert "new EventSource(withStreamToken(streamUrl), { withCredentials: true })" in use_sse
    assert 'meta[name="brain-alpha-stream"]' in use_sse
    assert "stream_token=${encodeURIComponent(token)}" in use_sse


def test_react_build_template_exposes_backend_token_placeholders():
    html = REACT_INDEX.read_text(encoding="utf-8")
    use_api = _source("hooks/useApi.ts")

    assert 'name="brain-alpha-csrf" content="__BRAIN_ALPHA_OPS_CSRF_TOKEN__"' in html
    assert 'name="brain-alpha-stream" content="__BRAIN_ALPHA_OPS_STREAM_TOKEN__"' in html
    assert 'meta[name="brain-alpha-csrf"]' in use_api
