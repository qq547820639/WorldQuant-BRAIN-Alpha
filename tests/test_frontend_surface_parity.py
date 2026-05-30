from __future__ import annotations

from scripts import check_frontend_surface_parity


def test_frontend_surface_parity_accepts_matching_fixture(tmp_path):
    inline_registry = tmp_path / "view-registry.js"
    react_app = tmp_path / "App.tsx"
    inline_registry.write_text(
        """
var WORKFLOW_VIEWS = ['dashboard', 'candidates'];
var DATA_VIEWS = ['config'];
var RESEARCH_VIEWS = [];
var ViewRegistry = {
  VIEW_ORDER: WORKFLOW_VIEWS.concat(DATA_VIEWS, RESEARCH_VIEWS),
  WORKFLOW_VIEWS: WORKFLOW_VIEWS,
  VIEW_TITLES: {
    dashboard: 'Dashboard',
    candidates: 'Candidates',
    config: 'Config',
  },
  VIEW_ICONS: {},
};
""",
        encoding="utf-8",
    )
    react_app.write_text(
        """
const TABS = [
  { id: "dashboard", label: "Dashboard", icon: "D" },
  { id: "candidates", label: "Candidates", icon: "C" },
  { id: "config", label: "Config", icon: "G" },
];
""",
        encoding="utf-8",
    )

    result = check_frontend_surface_parity.check_frontend_surface_parity(
        inline_registry,
        react_app,
        fail_on_gaps=True,
    )

    assert result["ok"] is True
    assert result["parity"]["matches"] is True
    assert result["parity"]["strict_matches"] is True
    assert result["parity"]["shared_ids"] == ["dashboard", "candidates", "config"]
    assert result["parity"]["inline_only_views"] == []
    assert result["parity"]["react_only_tabs"] == []
    assert result["parity"]["accepted_react_only_tabs"] == []
    assert result["parity"]["unaccepted_react_only_tabs"] == []


def test_frontend_surface_parity_reports_gaps_without_failing_by_default(tmp_path):
    inline_registry = tmp_path / "view-registry.js"
    react_app = tmp_path / "App.tsx"
    inline_registry.write_text(
        """
var WORKFLOW_VIEWS = ['candidates', 'passed'];
var DATA_VIEWS = ['cloud'];
var RESEARCH_VIEWS = ['research_memory'];
var ViewRegistry = {
  VIEW_ORDER: WORKFLOW_VIEWS.concat(DATA_VIEWS, RESEARCH_VIEWS),
  WORKFLOW_VIEWS: WORKFLOW_VIEWS,
  VIEW_TITLES: { candidates: '候选池', passed: '达标', cloud: '云端数据', research_memory: '研究记忆' },
  VIEW_ICONS: {},
};
""",
        encoding="utf-8",
    )
    react_app.write_text(
        """
const TABS = [
  { id: "dashboard", label: "Dashboard", icon: "D" },
  { id: "candidates", label: "Candidates", icon: "C" },
  { id: "submission", label: "Submit", icon: "S" },
];
""",
        encoding="utf-8",
    )

    result = check_frontend_surface_parity.check_frontend_surface_parity(inline_registry, react_app)

    assert result["ok"] is True
    assert result["parity"]["matches"] is False
    assert result["parity"]["shared_ids"] == ["candidates"]
    assert result["parity"]["inline_only_views"] == ["passed", "cloud", "research_memory"]
    assert result["parity"]["react_only_tabs"] == ["dashboard", "submission"]
    assert result["findings"] == []


def test_frontend_surface_parity_can_fail_on_gaps(tmp_path):
    inline_registry = tmp_path / "view-registry.js"
    react_app = tmp_path / "App.tsx"
    inline_registry.write_text(
        """
var WORKFLOW_VIEWS = ['candidates', 'passed'];
var DATA_VIEWS = [];
var RESEARCH_VIEWS = [];
var ViewRegistry = {
  VIEW_ORDER: WORKFLOW_VIEWS.concat(DATA_VIEWS, RESEARCH_VIEWS),
  WORKFLOW_VIEWS: WORKFLOW_VIEWS,
  VIEW_TITLES: { candidates: '候选池', passed: '达标' },
  VIEW_ICONS: {},
};
""",
        encoding="utf-8",
    )
    react_app.write_text(
        """
const TABS = [
  { id: "candidates", label: "Candidates", icon: "C" },
];
""",
        encoding="utf-8",
    )

    result = check_frontend_surface_parity.check_frontend_surface_parity(
        inline_registry,
        react_app,
        fail_on_gaps=True,
    )

    assert result["ok"] is False
    assert result["findings"][0]["code"] == "frontend_surface_mismatch"
    assert result["findings"][0]["inline_only_views"] == ["passed"]
    assert result["findings"][0]["react_only_tabs"] == []


def test_frontend_surface_parity_accepts_planned_react_only_tabs(tmp_path):
    inline_registry = tmp_path / "view-registry.js"
    react_app = tmp_path / "App.tsx"
    plan = tmp_path / "plan.json"
    inline_registry.write_text(
        """
var WORKFLOW_VIEWS = ['candidates'];
var DATA_VIEWS = [];
var RESEARCH_VIEWS = [];
var ViewRegistry = {
  VIEW_ORDER: WORKFLOW_VIEWS.concat(DATA_VIEWS, RESEARCH_VIEWS),
  WORKFLOW_VIEWS: WORKFLOW_VIEWS,
  VIEW_TITLES: { candidates: '候选池' },
  VIEW_ICONS: {},
};
""",
        encoding="utf-8",
    )
    react_app.write_text(
        """
const TABS = [
  { id: "dashboard", label: "Dashboard", icon: "D" },
  { id: "candidates", label: "Candidates", icon: "C" },
  { id: "submission", label: "Submit", icon: "S" },
];
""",
        encoding="utf-8",
    )
    plan.write_text(
        """
{
  "schema_version": "frontend_surface_parity_plan.v1",
  "inline_view_mappings": {
    "candidates": {"react_target": "candidates", "status": "implemented"}
  },
  "react_only_tab_policy": {
    "dashboard": {"status": "accepted"},
    "submission": {"status": "accepted"}
  }
}
""",
        encoding="utf-8",
    )

    result = check_frontend_surface_parity.check_frontend_surface_parity(
        inline_registry,
        react_app,
        plan_path=plan,
        fail_on_gaps=True,
    )

    assert result["ok"] is True
    assert result["parity"]["matches"] is False
    assert result["parity"]["strict_matches"] is True
    assert result["parity"]["react_only_tabs"] == ["dashboard", "submission"]
    assert result["parity"]["accepted_react_only_tabs"] == ["dashboard", "submission"]
    assert result["parity"]["unaccepted_react_only_tabs"] == []


def test_frontend_surface_parity_still_fails_unaccepted_react_only_tabs(tmp_path):
    inline_registry = tmp_path / "view-registry.js"
    react_app = tmp_path / "App.tsx"
    plan = tmp_path / "plan.json"
    inline_registry.write_text(
        """
var WORKFLOW_VIEWS = ['candidates'];
var DATA_VIEWS = [];
var RESEARCH_VIEWS = [];
var ViewRegistry = {
  VIEW_ORDER: WORKFLOW_VIEWS.concat(DATA_VIEWS, RESEARCH_VIEWS),
  WORKFLOW_VIEWS: WORKFLOW_VIEWS,
  VIEW_TITLES: { candidates: '候选池' },
  VIEW_ICONS: {},
};
""",
        encoding="utf-8",
    )
    react_app.write_text(
        """
const TABS = [
  { id: "dashboard", label: "Dashboard", icon: "D" },
  { id: "candidates", label: "Candidates", icon: "C" },
];
""",
        encoding="utf-8",
    )
    plan.write_text(
        """
{
  "schema_version": "frontend_surface_parity_plan.v1",
  "inline_view_mappings": {
    "candidates": {"react_target": "candidates", "status": "implemented"}
  }
}
""",
        encoding="utf-8",
    )

    result = check_frontend_surface_parity.check_frontend_surface_parity(
        inline_registry,
        react_app,
        plan_path=plan,
        fail_on_gaps=True,
    )

    assert result["ok"] is False
    assert result["parity"]["strict_matches"] is False
    assert result["findings"][0]["code"] == "frontend_surface_mismatch"
    assert result["findings"][0]["inline_only_views"] == []
    assert result["findings"][0]["react_only_tabs"] == ["dashboard"]


def test_frontend_surface_parity_checks_plan_mapping(tmp_path):
    inline_registry = tmp_path / "view-registry.js"
    react_app = tmp_path / "App.tsx"
    plan = tmp_path / "plan.json"
    inline_registry.write_text(
        """
var WORKFLOW_VIEWS = ['candidates', 'passed'];
var DATA_VIEWS = ['cloud'];
var RESEARCH_VIEWS = [];
var ViewRegistry = {
  VIEW_ORDER: WORKFLOW_VIEWS.concat(DATA_VIEWS, RESEARCH_VIEWS),
  WORKFLOW_VIEWS: WORKFLOW_VIEWS,
  VIEW_TITLES: { candidates: '候选池', passed: '达标', cloud: '云端数据' },
  VIEW_ICONS: {},
};
""",
        encoding="utf-8",
    )
    react_app.write_text(
        """
const TABS = [
  { id: "candidates", label: "Candidates", icon: "C" },
  { id: "submission", label: "Submit", icon: "S" },
];
""",
        encoding="utf-8",
    )
    plan.write_text(
        """
{
  "schema_version": "frontend_surface_parity_plan.v1",
  "inline_view_mappings": {
    "candidates": {"react_target": "candidates", "status": "implemented"},
    "passed": {"react_target": "submission", "status": "planned"},
    "cloud": {"react_target": "future:data", "status": "planned"}
  }
}
""",
        encoding="utf-8",
    )

    result = check_frontend_surface_parity.check_frontend_surface_parity(
        inline_registry,
        react_app,
        plan_path=plan,
        fail_on_unmapped_plan=True,
    )

    assert result["ok"] is True
    assert result["plan"]["unmapped_inline_views"] == []
    assert result["plan"]["implemented_inline_views"] == ["candidates"]
    assert result["plan"]["planned_inline_views"] == ["passed", "cloud"]


def test_frontend_surface_parity_can_fail_on_unmapped_plan(tmp_path):
    inline_registry = tmp_path / "view-registry.js"
    react_app = tmp_path / "App.tsx"
    plan = tmp_path / "plan.json"
    inline_registry.write_text(
        """
var WORKFLOW_VIEWS = ['candidates', 'passed'];
var DATA_VIEWS = [];
var RESEARCH_VIEWS = [];
var ViewRegistry = {
  VIEW_ORDER: WORKFLOW_VIEWS.concat(DATA_VIEWS, RESEARCH_VIEWS),
  WORKFLOW_VIEWS: WORKFLOW_VIEWS,
  VIEW_TITLES: { candidates: '候选池', passed: '达标' },
  VIEW_ICONS: {},
};
""",
        encoding="utf-8",
    )
    react_app.write_text(
        """
const TABS = [
  { id: "candidates", label: "Candidates", icon: "C" },
];
""",
        encoding="utf-8",
    )
    plan.write_text(
        """
{
  "schema_version": "frontend_surface_parity_plan.v1",
  "inline_view_mappings": {
    "candidates": {"react_target": "candidates", "status": "implemented"}
  }
}
""",
        encoding="utf-8",
    )

    result = check_frontend_surface_parity.check_frontend_surface_parity(
        inline_registry,
        react_app,
        plan_path=plan,
        fail_on_unmapped_plan=True,
    )

    assert result["ok"] is False
    assert result["findings"][0]["code"] == "frontend_surface_unmapped_views"
    assert result["findings"][0]["unmapped_inline_views"] == ["passed"]


def test_frontend_surface_parity_can_fail_on_unimplemented_plan(tmp_path):
    inline_registry = tmp_path / "view-registry.js"
    react_app = tmp_path / "App.tsx"
    plan = tmp_path / "plan.json"
    inline_registry.write_text(
        """
var WORKFLOW_VIEWS = ['candidates', 'passed'];
var DATA_VIEWS = [];
var RESEARCH_VIEWS = [];
var ViewRegistry = {
  VIEW_ORDER: WORKFLOW_VIEWS.concat(DATA_VIEWS, RESEARCH_VIEWS),
  WORKFLOW_VIEWS: WORKFLOW_VIEWS,
  VIEW_TITLES: { candidates: '候选池', passed: '达标' },
  VIEW_ICONS: {},
};
""",
        encoding="utf-8",
    )
    react_app.write_text(
        """
const TABS = [
  { id: "candidates", label: "Candidates", icon: "C" },
  { id: "submission", label: "Submit", icon: "S" },
];
""",
        encoding="utf-8",
    )
    plan.write_text(
        """
{
  "schema_version": "frontend_surface_parity_plan.v1",
  "inline_view_mappings": {
    "candidates": {"react_target": "candidates", "status": "implemented"},
    "passed": {"react_target": "submission", "status": "planned"}
  }
}
""",
        encoding="utf-8",
    )

    result = check_frontend_surface_parity.check_frontend_surface_parity(
        inline_registry,
        react_app,
        plan_path=plan,
        fail_on_unimplemented_plan=True,
    )

    assert result["ok"] is False
    assert result["findings"][0]["code"] == "frontend_surface_unimplemented_views"
    assert result["findings"][0]["planned_inline_views"] == ["passed"]


def test_frontend_surface_parity_can_fail_on_stale_plan_entries(tmp_path):
    inline_registry = tmp_path / "view-registry.js"
    react_app = tmp_path / "App.tsx"
    plan = tmp_path / "plan.json"
    inline_registry.write_text(
        """
var WORKFLOW_VIEWS = ['candidates'];
var DATA_VIEWS = [];
var RESEARCH_VIEWS = [];
var ViewRegistry = {
  VIEW_ORDER: WORKFLOW_VIEWS.concat(DATA_VIEWS, RESEARCH_VIEWS),
  WORKFLOW_VIEWS: WORKFLOW_VIEWS,
  VIEW_TITLES: { candidates: '候选池' },
  VIEW_ICONS: {},
};
""",
        encoding="utf-8",
    )
    react_app.write_text(
        """
const TABS = [
  { id: "candidates", label: "Candidates", icon: "C" },
];
""",
        encoding="utf-8",
    )
    plan.write_text(
        """
{
  "schema_version": "frontend_surface_parity_plan.v1",
  "inline_view_mappings": {
    "candidates": {"react_target": "candidates", "status": "implemented"},
    "retired_old_view": {"react_target": "candidates", "status": "retired"}
  }
}
""",
        encoding="utf-8",
    )

    default_result = check_frontend_surface_parity.check_frontend_surface_parity(
        inline_registry,
        react_app,
        plan_path=plan,
    )
    strict_result = check_frontend_surface_parity.check_frontend_surface_parity(
        inline_registry,
        react_app,
        plan_path=plan,
        fail_on_stale_plan=True,
    )

    assert default_result["ok"] is True
    assert default_result["plan"]["stale_inline_view_mappings"] == ["retired_old_view"]
    assert strict_result["ok"] is False
    assert strict_result["findings"][0]["code"] == "frontend_surface_stale_plan_entries"
    assert strict_result["findings"][0]["stale_inline_view_mappings"] == ["retired_old_view"]


def test_frontend_surface_parity_main_parses_stale_plan_flag(monkeypatch, tmp_path, capsys):
    captured = {}

    def fake_check_frontend_surface_parity(*args, **kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "inline_view_count": 0,
            "react_tab_count": 0,
            "parity": {
                "matches": True,
                "strict_matches": True,
                "shared_ids": [],
                "inline_only_views": [],
                "react_only_tabs": [],
                "accepted_react_only_tabs": [],
                "unaccepted_react_only_tabs": [],
            },
            "plan": {
                "unmapped_inline_views": [],
                "stale_inline_view_mappings": [],
                "implemented_inline_views": [],
                "planned_inline_views": [],
                "retired_inline_views": [],
                "accepted_react_only_tabs": [],
            },
            "findings": [],
        }

    monkeypatch.setattr(check_frontend_surface_parity, "check_frontend_surface_parity", fake_check_frontend_surface_parity)

    code = check_frontend_surface_parity.main(
        [
            "--inline-registry",
            str(tmp_path / "view-registry.js"),
            "--react-app",
            str(tmp_path / "App.tsx"),
            "--fail-on-stale-plan",
            "--json",
        ]
    )

    assert code == 0
    assert captured["fail_on_stale_plan"] is True
    assert '"ok": true' in capsys.readouterr().out


def test_frontend_surface_parity_reports_current_workspace_gap():
    result = check_frontend_surface_parity.check_frontend_surface_parity(
        plan_path=check_frontend_surface_parity.DEFAULT_PARITY_PLAN,
    )

    assert result["ok"] is True
    assert result["parity"]["matches"] is False
    assert result["parity"]["strict_matches"] is True
    assert "candidates" in result["parity"]["shared_ids"]
    assert "pending_backtest" in result["parity"]["shared_ids"]
    assert "running_backtest" in result["parity"]["shared_ids"]
    assert "backtest_rework" in result["parity"]["shared_ids"]
    assert "passed" in result["parity"]["shared_ids"]
    assert "submittable" in result["parity"]["shared_ids"]
    assert "submitted" in result["parity"]["shared_ids"]
    assert "failed" in result["parity"]["shared_ids"]
    assert "cloud" in result["parity"]["shared_ids"]
    assert "lifecycle" in result["parity"]["shared_ids"]
    assert "research_memory" in result["parity"]["shared_ids"]
    assert "research_knowledge" in result["parity"]["shared_ids"]
    assert "research_observability" in result["parity"]["shared_ids"]
    assert "prompt_runs" in result["parity"]["shared_ids"]
    assert "sqlite_indexes" in result["parity"]["shared_ids"]
    assert "robustness" in result["parity"]["shared_ids"]
    assert result["parity"]["inline_only_views"] == []
    assert result["parity"]["react_only_tabs"] == ["dashboard", "scoring", "submission", "config"]
    assert result["parity"]["accepted_react_only_tabs"] == ["dashboard", "scoring", "submission", "config"]
    assert result["parity"]["unaccepted_react_only_tabs"] == []
    assert result["plan"]["unmapped_inline_views"] == []
    assert result["plan"]["stale_inline_view_mappings"] == []
    assert result["plan"]["implemented_inline_views"] == [
        "candidates",
        "pending_backtest",
        "running_backtest",
        "backtest_rework",
        "passed",
        "submittable",
        "submitted",
        "failed",
        "cloud",
        "lifecycle",
        "research_memory",
        "research_knowledge",
        "research_observability",
        "prompt_runs",
        "sqlite_indexes",
        "robustness",
    ]
    assert result["plan"]["planned_inline_views"] == []
    assert result["plan"]["accepted_react_only_tabs"] == ["dashboard", "scoring", "submission", "config"]
