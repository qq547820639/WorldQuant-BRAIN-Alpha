"""React web-console contract tests for the retired inline frontend surface.

The legacy inline ``brain_alpha_ops/web/js`` modules were removed when the
React state-card console became the served frontend.  This file keeps the old
``test_web_frontend_v2.py`` evidence path alive for defect trackers, but the
assertions now target the current React source, built ``dist`` shell, and
compatibility helpers.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path

import pytest

import brain_alpha_ops.build_inline as build_inline
from brain_alpha_ops import web_html
from brain_alpha_ops.web_routes import GET_ROUTES, POST_ROUTES, route_for
from scripts.check_frontend_syntax import _node_path


ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "brain_alpha_ops" / "web"
REACT_APP = WEB_DIR / "react_app"
REACT_SRC = REACT_APP / "src"
REACT_COMPONENTS = REACT_SRC / "components"
REACT_DIST = REACT_APP / "dist"
REACT_INDEX = REACT_DIST / "index.html"

LEGACY_INLINE_MODULES = (
    "js/api-client.js",
    "js/app.js",
    "js/app-runtime.js",
    "js/components/modal.js",
    "js/components/progress.js",
    "js/components/spinner.js",
    "js/components/table.js",
    "js/components/toast.js",
    "js/cloud-sync.js",
    "js/form-controls.js",
    "js/header-status.js",
    "js/loading-feedback.js",
    "js/result-state.js",
    "js/result-table.js",
    "js/state.js",
    "js/strategy-panel.js",
    "js/utils.js",
    "js/view-model.js",
    "js/view-registry.js",
    "js/view-renderers.js",
    "js/views/charts.js",
    "js/views/detail.js",
    "js/views/monitor.js",
    "js/views/production.js",
)

CARD_VIEW_IDS = (
    "official_operations",
    "dashboard",
    "candidates",
    "official_backtests",
    "scoring",
    "quality_check",
    "submission_confirm",
    "checkpoint_status",
    "config",
    "cloud",
)

COMPAT_CARD_VIEW_IDS = ("submission",)


def _source(relative: str) -> str:
    return (REACT_SRC / relative).read_text(encoding="utf-8")


def _component(name: str) -> str:
    return (REACT_COMPONENTS / name).read_text(encoding="utf-8")


def _dist_html() -> str:
    return REACT_INDEX.read_text(encoding="utf-8")


def _assert_snippets(source: str, snippets: list[str]) -> None:
    for snippet in snippets:
        assert snippet in source, f"Missing source contract: {snippet}"


def _node_path_or_skip() -> str:
    node = _node_path()
    if not node:
        pytest.skip("Node.js not available")
    return node


def _frontend_module_load_order(modules: list[str]) -> list[str]:
    """Preserve the legacy helper for optional QA scripts.

    Current pytest coverage no longer loads the retired inline modules.  If a
    local QA script still imports this helper, keeping the historical dependency
    ordering prevents an import-time regression.
    """
    ordered = list(modules)
    if "js/app.js" not in ordered:
        return ordered
    dependencies = [
        "js/result-state.js",
        "js/result-table.js",
        "js/form-controls.js",
        "js/strategy-panel.js",
        "js/cloud-sync.js",
        "js/header-status.js",
        "js/app-runtime.js",
        "js/loading-feedback.js",
    ]
    app_index = ordered.index("js/app.js")
    before_app = [item for item in ordered[:app_index] if item not in dependencies]
    after_app = [item for item in ordered[app_index + 1:] if item not in dependencies]
    return before_app + dependencies + ["js/app.js"] + after_app


def _build_test_script(modules: list[str], test_code: str) -> str:
    """Build a tiny legacy inline harness, or skip when the surface is retired."""
    missing = [module for module in _frontend_module_load_order(modules) if not (WEB_DIR / module).is_file()]
    if missing:
        pytest.skip("Legacy inline frontend is retired; React source/dist contracts cover the current surface.")
    load_calls = "\n".join(
        f"vm.runInThisContext(fs.readFileSync(path.join(root, 'brain_alpha_ops', 'web', {json.dumps(module)}), 'utf-8'));"
        for module in _frontend_module_load_order(modules)
    )
    return f"""
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const root = process.argv[2];
globalThis.window = globalThis;
globalThis.document = {{
  getElementById() {{ return {{ classList: {{ add() {{}}, remove() {{}}, contains() {{ return false; }} }} }}; }},
  querySelector() {{ return null; }},
  querySelectorAll() {{ return []; }},
  createElement() {{ return {{ classList: {{ add() {{}}, remove() {{}}, contains() {{ return false; }} }} }}; }},
  body: {{ appendChild() {{}} }},
}};
function assert(condition, message) {{ if (!condition) throw new Error(message || 'assertion failed'); }}
function assertEqual(actual, expected, message) {{ if (actual !== expected) throw new Error(message || `${{actual}} !== ${{expected}}`); }}
function assertContains(haystack, needle, message) {{ if (String(haystack).indexOf(String(needle)) === -1) throw new Error(message || 'missing snippet'); }}
{load_calls}
{test_code}
console.log('ALL TESTS PASSED');
"""


def _run_node_script(script: str, timeout: int = 120) -> str:
    node = _node_path_or_skip()
    with tempfile.TemporaryDirectory() as tmp:
        script_path = Path(tmp) / "test.js"
        script_path.write_text(script, encoding="utf-8")
        proc = subprocess.run(
            [node, str(script_path), str(ROOT)],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    if proc.returncode != 0:
        raise AssertionError(
            f"Node script failed (exit={proc.returncode}):\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    return proc.stdout


def test_react_dist_assets_exist_and_legacy_inline_surface_is_retired():
    result = build_inline.check()
    html = _dist_html()

    assert result["ok"] is True
    assert result["frontend"] == "react"
    assert result["schema_version"] == "react_dist_readiness.v1"
    assert result["asset_count"] >= 2
    assert result["missing"] == []
    assert "<!-- inline:" not in html
    assert "<!-- inline-css:" not in html
    assert not (WEB_DIR / "index_template.html").exists()
    assert not (WEB_DIR / "js").exists()
    assert not (WEB_DIR / "css").exists()
    for ref in result["asset_refs"]:
        assert ref.startswith("/assets/")
        assert (REACT_DIST / ref.removeprefix("/")).is_file()


def test_build_inline_compatibility_surface_reports_deprecated_react_contract():
    html, stats = build_inline.build_inline("\ufeff<body><!-- inline:js/app.js --></body>")

    assert html == "<body><!-- inline:js/app.js --></body>"
    assert stats == {
        "schema_version": "react_dist_readiness.v1",
        "replaced": 0,
        "css_replaced": 0,
        "missing": [],
        "deprecated": True,
    }


def test_web_html_loads_react_shell_when_inline_surface_is_absent():
    web_html.reset_html_cache()

    assert web_html.default_html_path() == REACT_INDEX
    html = web_html.load_html()
    rendered = web_html.render_html("csrf-token", "stream-token", html)

    assert '<div id="root">' in html
    assert "/assets/" in html
    assert "__BRAIN_ALPHA_OPS_CSRF_TOKEN__" not in rendered
    assert "__BRAIN_ALPHA_OPS_STREAM_TOKEN__" not in rendered
    assert "csrf-token" in rendered
    assert "stream-token" in rendered


def test_all_card_views_are_typed_configured_and_routed_to_detail_components():
    app = _source("App.tsx")
    types = _source("types/index.ts")
    state_cards = _component("StateCards.tsx")

    assert 'useState<CardViewId>("dashboard")' in app
    assert "const VIEW_LABELS: Record<string, string> = {" in app
    assert "phase-group" in _component("Sidebar.tsx")  # v3.0 phase grouped nav
    assert "CandidateTable" in app
    assert 'key="scoring_picker"' in app
    assert "selectedCandidate" in app
    assert "OfficialBacktestSlots" in app
    assert "QualityCheckPanel" in app
    assert "SubmissionConfirmPanel" in app
    assert "SnapshotPanel" in app
    assert "ConfigPanel" in app
    for view_id in CARD_VIEW_IDS:
        assert f'| "{view_id}"' in types
        assert f'{view_id}:' in app
        assert f'id: "{view_id}"' in state_cards
        assert f'case "{view_id}":' in app
    for view_id in COMPAT_CARD_VIEW_IDS:
        assert f'| "{view_id}"' in types
        assert f'{view_id}:' in app
        assert f'id: "{view_id}"' not in state_cards
        assert f'case "{view_id}":' in app


def test_state_card_navigation_preserves_priority_and_minimal_chrome():
    app = _source("App.tsx")
    state_cards = _component("StateCards.tsx")

    ordered_ids = re.findall(r'id: "([^"]+)"', state_cards)
    assert ordered_ids[: len(CARD_VIEW_IDS)] == list(CARD_VIEW_IDS)
    _assert_snippets(
        app + state_cards,
        [
            "BRAIN Alpha Ops",
            "Sidebar",
            "setActiveView(view)",
            'aria-label="切换导航菜单"',
            'import Sidebar from "@/components/Sidebar"',
            "grid w-full max-w-full grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5",
            "onClick={() => onNavigate(config.id)}",
            'role="alert"',
            'aria-live="assertive"',
        ],
    )


def test_react_core_workflow_api_paths_are_registered_in_backend_routes():
    backend_paths = set(GET_ROUTES) | set(POST_ROUTES)
    frontend_paths: set[str] = set()
    for path in REACT_SRC.rglob("*"):
        if path.suffix not in {".ts", ".tsx"}:
            continue
        source = path.read_text(encoding="utf-8")
        for match in re.finditer(r'["`](/(?:api|sse)[^"`]*)["`]', source):
            frontend_paths.add(match.group(1).split("?", 1)[0].split("${", 1)[0].rstrip("/"))

    assert frontend_paths
    assert frontend_paths <= backend_paths
    for method, endpoint in [
        ("GET", "/api/candidates"),
        ("POST", "/api/generate_candidates"),
        ("GET", "/api/backtest_slots"),
        ("GET", "/api/check_results"),
        ("GET", "/api/submit_readiness"),
        ("POST", "/api/check_batch"),
        ("GET", "/sse"),
    ]:
        assert route_for(method, endpoint) is not None


def test_app_submit_selected_candidates_handles_missing_async_job_result():
    """Async complete payloads can omit result rows without null dereferences."""
    candidates = _component("CandidateTable.tsx")
    submission = _component("SubmissionPanel.tsx")

    _assert_snippets(
        candidates,
        [
            "const result = event.result as { candidates?: Candidate[]; candidates_preview?: Candidate[]; count?: number } | undefined;",
            "const rows = result?.candidates || result?.candidates_preview || [];",
            "if (rows.length) setCandidates(rows);",
            "result?.task_id || result?.job_id || \"\"",
            'setTaskError(result?.error || "启动候选生成失败");',
            'useSSE(taskId ? `/sse?job_id=${encodeURIComponent(taskId)}` : null',
        ],
    )
    _assert_snippets(
        submission,
        [
            "Retired submit surface kept as a compatibility alias",
            "SubmissionConfirmPanel notify={notify}",
            "旧提交面板已退役",
        ],
    )
    assert "/api/submit" not in submission
    assert "/api/submit_batch" not in submission


def test_loading_feedback_runstartup_launches_all_tasks_concurrently():
    """State-card startup launches all dashboard data fetches from one effect."""
    state_cards = _component("StateCards.tsx")

    loader_body = re.search(r"const loadStateSnapshots = useCallback\(\(\) => \{(?P<body>.*?)\}, \[", state_cards, re.S)
    assert loader_body, "StateCards startup loader missing"
    body = loader_body.group("body")
    expected_calls = [
        'void candidatesApi.call("/api/candidates?limit=1000");',
        'void slotsApi.call("/api/backtest_slots");',
        'void configApi.call("/api/config");',
        'void checkpointApi.call("/api/checkpoint_status");',
        'void cloudApi.call("/api/snapshot/cloud?limit=10");',
    ]
    for call in expected_calls:
        assert call in body
    assert "await " not in body
    assert "useEffect(() => {\n    loadStateSnapshots();\n  }, [loadStateSnapshots]);" in state_cards
    assert "ProgressFeedback" in state_cards
    assert 'phase: "state_cards_load"' in state_cards


def test_app_apply_preset_reads_presets_from_app_state():
    """ConfigPanel hydrates form state from backend config/schema before edits."""
    config = _component("ConfigPanel.tsx")

    _assert_snippets(
        config,
        [
            'void configApi.call("/api/config");',
            'void schemaApi.call("/api/config_schema");',
            "const next = formFromConfig(config);",
            "setForm(next);",
            "setInitialForm(next);",
            "const dirty = useMemo(",
            "payloadFromForm(form)",
            "datasetSelectOptions(schema, form.dataset)",
            'onClick={() => initialForm && setForm({ ...initialForm })}',
            "validateForm(form, schema)",
            "optionValues(options,",
        ],
    )


def test_spinner_component():
    """The React progress spinner keeps accessible loading and retry states."""
    progress = _component("ProgressFeedback.tsx")
    css = _source("index.css")

    _assert_snippets(
        progress,
        [
            'role={isBusy ? "status" : undefined}',
            'aria-live={state === "error" ? "assertive" : "polite"}',
            'className="spinner"',
            'role="progressbar"',
            'aria-label={`${title}: ${label}`}',
            "aria-valuenow={isDeterminate ? roundedPercent : undefined}",
            "normalizedPercent(progress)",
            "fmtDuration(remaining)",
            "onRetry",
        ],
    )
    _assert_snippets(
        css,
        [
            ".spinner",
            "animation: spin 0.7s linear infinite;",
            ".progress-bar.indeterminate .progress-bar-fill",
            "@keyframes progress-indeterminate",
        ],
    )


def test_submission_confirmation_panel_stays_read_only_and_local_boundary_aware():
    confirm = _component("SubmissionConfirmPanel.tsx")

    assert 'callReadiness<SubmitReadinessResponse>("/api/submit_readiness")' in confirm
    assert '"/api/submit"' not in confirm
    assert '"/api/submit_batch"' not in confirm
    _assert_snippets(
        confirm,
        [
            "readiness?.ready_to_submit",
            "readiness?.official_api_called ?",
            "readiness?.production_gaps",
            "readiness?.required_next_steps",
            "top_family_blocking_reasons",
            "job_family_candidate_count",
            "buildRows(candidates, checks)",
        ],
    )


def test_sse_hook_preserves_stream_token_credentials_and_reconnect_contract():
    use_sse = _source("hooks/useSSE.ts")
    types = _source("types/index.ts")
    csrf_utils = _source("utils/csrf.ts")

    _assert_snippets(
        use_sse + csrf_utils,
        [
            "new EventSource(withStreamToken(streamUrl), { withCredentials: true })",
            "reconnectIntervalMs = 5000",
            "maxReconnectAttempts = 30",
            "reconnectCountRef.current += 1",
            "onExhaustedRef.current?.();",
            'meta[name="brain-alpha-stream"]',
            "stream_token=${encodeURIComponent(token)}",
            "!token.startsWith(\"__BRAIN_ALPHA_OPS\")",
        ],
    )
    _assert_snippets(
        types,
        [
            "export interface SSEEvent",
            "task_id?: string;",
            "job_id?: string;",
            "result?: unknown;",
        ],
    )


def test_react_dist_check_cli_reports_current_schema(capsys):
    return_code = build_inline.main(["--check", "--json"])
    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert return_code == 0
    assert data["ok"] is True
    assert data["frontend"] == "react"
    assert data["schema_version"] == "react_dist_readiness.v1"
