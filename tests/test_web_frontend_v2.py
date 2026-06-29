"""React web-console contract tests for the retired inline frontend surface.
from __future__ import annotations

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
import brain_alpha_ops.web  # noqa: F401  install meta-path bridge for web_* modules
import brain_alpha_ops.web_html as web_html
from brain_alpha_ops.web_routes import GET_ROUTES, POST_ROUTES, route_for
from _react_source_utils import resolve_react_source
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
    return resolve_react_source(REACT_SRC / relative)


def _component(name: str) -> str:
    return resolve_react_source(REACT_COMPONENTS / name)


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
    types = _source("types/ui.ts")
    state_cards = _component("StateCards.tsx")
    base_state = _source("hooks/useAppState/useBaseState.ts")
    card_configs = _component("StateCards/cardConfigs.ts")
    render_view = _source("components/views/renderView.tsx")

    assert "useState<CardViewId>(readViewFromHash)" in base_state
    assert "const VIEW_LABELS: Record<string, string> = {" in app
    assert "phase-group" in _component("Sidebar.tsx")  # v3.0 phase grouped nav
    assert "CandidateTable" in render_view
    assert 'viewMode="checkpoint_status"' in render_view
    assert "selectedCandidate" in render_view
    assert "OfficialBacktestSlots" in render_view
    assert "QualityCheckPanel" in render_view
    assert "SubmissionConfirmPanel" in render_view
    assert "SnapshotPanel" in render_view
    assert "ConfigPanel" in render_view
    for view_id in CARD_VIEW_IDS:
        assert f"| '{view_id}'" in types
        assert f'{view_id}:' in app
        assert f"id: '{view_id}'" in card_configs
        assert f"case '{view_id}':" in render_view
    for view_id in COMPAT_CARD_VIEW_IDS:
        # Legacy compat aliases have been removed; verify they are absent from
        # the view registry, card configs, and render switch. The type file is
        # not checked because the same string may appear in unrelated types.
        assert f'{view_id}:' not in app
        assert f"id: '{view_id}'" not in card_configs
        assert f"case '{view_id}':" not in render_view


def test_state_card_navigation_preserves_priority_and_minimal_chrome():
    app = _source("App.tsx")
    state_cards = _component("StateCards.tsx")
    card_configs = _component("StateCards/cardConfigs.ts")
    handlers = _source("hooks/useAppState/useHandlers.ts")
    state_card_item = _component("StateCards/StateCardItem.tsx")

    ordered_ids = re.findall(r"id: '([^']+)'", card_configs)
    assert ordered_ids[: len(CARD_VIEW_IDS)] == list(CARD_VIEW_IDS)
    _assert_snippets(
        app + state_cards + card_configs + handlers + state_card_item,
        [
            "BRAIN Alpha Ops",
            "Sidebar",
            "setActiveView(view)",
            'aria-label="切换导航菜单"',
            "import Sidebar from '@/components/Sidebar'",
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
    generation = _source("hooks/useCandidateGeneration.ts")
    table_sse = _source("components/CandidateTable/useCandidateTableSse.ts")
    submission = _component("SubmissionPanel.tsx")

    _assert_snippets(
        generation,
        [
            "const result = event.result as",
            "candidates?: Candidate[];",
            "candidates_preview?: Candidate[];",
            "const rows = result?.candidates || [];",
            "result?.task_id || result?.job_id || ''",
            "pipeline.task.setError(apiErrorMessage(result, '启动候选池自动推进失败'))",
        ],
    )
    _assert_snippets(
        table_sse,
        [
            "sseManager.connect('task', `/sse?job_id=${encodeURIComponent(pipeline.task.jobId)}`",
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
    global_data = _source("hooks/useGlobalData.ts")

    loader_body = re.search(r"const loadStateSnapshots = useCallback\(\(\) => \{(?P<body>.*?)\}, \[", state_cards, re.S)
    assert loader_body, "StateCards startup loader missing"
    body = loader_body.group("body")
    assert "refreshAll()" in body
    assert "void checkpointApi.call('/api/checkpoint_status');" in body
    assert "await " not in body

    refresh_body = re.search(r"const refreshAll = useCallback\(\(\) => \{(?P<body>.*?)\}, \[", global_data, re.S)
    assert refresh_body, "GlobalData refreshAll missing"
    gbody = refresh_body.group("body")
    expected_global_calls = [
        "void candidatesApi.call('/api/candidates');",
        "void slotsApi.call('/api/backtest_slots');",
        "void cloudApi.call('/api/snapshot/cloud');",
        "void configApi.call('/api/config');",
    ]
    for call in expected_global_calls:
        assert call in gbody
    assert "await " not in gbody

    assert "useEffect(() => {\n    loadStateSnapshots();\n  }, [loadStateSnapshots]);" in state_cards
    assert "ProgressFeedback" in state_cards
    assert "phase: 'state_cards_load'" in state_cards


def test_app_apply_preset_reads_presets_from_app_state():
    """ConfigPanel hydrates form state from backend config/schema before edits."""
    config = _component("ConfigPanel.tsx")
    config_form = _source("hooks/useConfigForm.ts")
    global_data = _source("hooks/useGlobalData.ts")
    local_cache = _component("ConfigPanel/LocalCacheConnectionSection.tsx")
    basic_group = _component("ConfigPanel/BasicConfigGroup.tsx")

    _assert_snippets(
        global_data,
        [
            "void configApi.call('/api/config');",
        ],
    )
    _assert_snippets(
        config_form,
        [
            "void schemaApi.call('/api/config_schema');",
            "const next = formFromConfig(config);",
            "setFormValues(next);",
            "setInitialForm(next);",
            "isDirty: dirty,",
            "payloadFromForm(form)",
            "datasetSelectOptions(schema, form.dataset)",
            "validateForm(form, schema)",
            "onLoggedOut?.();",
        ],
    )
    _assert_snippets(
        config + basic_group + local_cache,
        [
            "payloadFromForm(form)",
            "optionValues(options,",
            "const cacheOnlyMode = contextFresh && !connected;",
            "onClick={resetForm}",
            "临时连接官方服务",
            "退出本地会话",
        ],
    )


def test_spinner_component():
    """The React progress spinner keeps accessible loading and retry states."""
    progress = _component("ProgressFeedback.tsx")
    progress_sub = _component("ProgressFeedback")
    progress_hook = _source("hooks/useProgressFeedback.ts")
    css = _source("styles")

    _assert_snippets(
        progress,
        [
            "role={isBusy ? 'status' : undefined}",
            "aria-live={state === 'error' ? 'assertive' : 'polite'}",
            "onRetry",
        ],
    )
    _assert_snippets(
        progress_sub,
        [
            'className="spinner"',
            'role="progressbar"',
            "aria-label={`${title}: ${label}`}",
            "aria-valuenow={isDeterminate ? roundedPercent : undefined}",
        ],
    )
    _assert_snippets(
        progress_hook,
        [
            "normalizedPercent(progress, progressState)",
            "fmtDuration(estimatedEta)",
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
    gates = _component("SubmissionGates")

    assert "callReadiness<SubmitReadinessResponse>('/api/submit_readiness')" in confirm
    assert "'/api/submit'" not in confirm
    assert "'/api/submit_batch'" not in confirm
    _assert_snippets(
        confirm,
        [
            "readiness?.ready_to_submit",
            "readiness?.real_submit_performed",
            "job_family_candidate_count",
            "buildRows(candidates, checks)",
        ],
    )
    _assert_snippets(
        gates,
        [
            "readiness?.official_api_called",
            "readiness?.authoritative_stop_rule",
            "readiness?.submit_ready_claim_allowed",
            "readiness?.production_gaps",
            "readiness?.required_next_steps",
            "top_family_blocking_reasons",
        ],
    )


def test_sse_hook_preserves_stream_token_credentials_and_reconnect_contract():
    use_sse = _source("hooks/useSSE.ts")
    types = _source("types/api.ts")
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
            "!token.startsWith('__BRAIN_ALPHA_OPS')",
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
