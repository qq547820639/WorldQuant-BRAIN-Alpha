from __future__ import annotations

from types import SimpleNamespace

from scripts import check_tracked_data_inventory


def test_tracked_data_inventory_classifies_known_data_paths(monkeypatch, tmp_path):
    stdout = "\n".join(
        [
            "data/jobs_production.json",
            "data/run_history/run_123.json",
            "data/checkpoints/run.checkpoint.json",
            "data/official_fields.json",
            "data/official_fields.meta.json",
            "data/prd_alpha_ops_v3.md",
            "data/qa_ui_refactor_report.md",
        ]
    )

    def fake_run(*args, **kwargs):
        command = args[0]
        if command[:3] == ["git", "ls-files", "data"]:
            return SimpleNamespace(returncode=0, stdout=stdout, stderr="")
        if command[:2] == ["git", "diff"] and "--cached" not in command:
            return SimpleNamespace(returncode=0, stdout="data/jobs_production.json\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(check_tracked_data_inventory.subprocess, "run", fake_run)

    result = check_tracked_data_inventory.inventory_tracked_data(tmp_path)

    assert result["ok"] is True
    assert result["tracked_count"] == 7
    assert result["categories"]["runtime_generated"] == [
        "data/checkpoints/run.checkpoint.json",
        "data/jobs_production.json",
        "data/run_history/run_123.json",
    ]
    assert result["categories"]["official_snapshot"] == [
        "data/official_fields.json",
        "data/official_fields.meta.json",
    ]
    assert result["categories"]["review_artifact"] == [
        "data/prd_alpha_ops_v3.md",
        "data/qa_ui_refactor_report.md",
    ]
    assert result["findings"] == []


def test_tracked_data_inventory_flags_unclassified_data_file(monkeypatch, tmp_path):
    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="data/manual_dump.json\n", stderr="")

    monkeypatch.setattr(check_tracked_data_inventory.subprocess, "run", fake_run)

    result = check_tracked_data_inventory.inventory_tracked_data(tmp_path)

    assert result["ok"] is False
    assert result["categories"]["unclassified"] == ["data/manual_dump.json"]
    assert result["findings"] == [
        {
            "code": "unclassified_tracked_data",
            "path": "data/manual_dump.json",
            "message": "Tracked data file does not match a known category: data/manual_dump.json",
        }
    ]


def test_tracked_data_inventory_can_fail_on_runtime_generated_data(monkeypatch, tmp_path):
    stdout = "\n".join(
        [
            "data/jobs_production.json",
            "data/official_fields.json",
            "data/prd_alpha_ops_v3.md",
        ]
    )

    def fake_run(*args, **kwargs):
        command = args[0]
        if command[:3] == ["git", "ls-files", "data"]:
            return SimpleNamespace(returncode=0, stdout=stdout, stderr="")
        if command[:2] == ["git", "diff"] and "--cached" not in command:
            return SimpleNamespace(returncode=0, stdout="data/jobs_production.json\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(check_tracked_data_inventory.subprocess, "run", fake_run)

    result = check_tracked_data_inventory.inventory_tracked_data(tmp_path, fail_on_runtime_generated=True)

    assert result["ok"] is False
    assert result["categories"]["runtime_generated"] == ["data/jobs_production.json"]
    assert result["findings"] == [
        {
            "code": "tracked_runtime_generated_data",
            "path": "data/jobs_production.json",
            "message": "Runtime-generated data file is still tracked: data/jobs_production.json",
        }
    ]


def test_tracked_data_inventory_can_fail_on_changed_runtime_generated_data(monkeypatch, tmp_path):
    tracked_stdout = "\n".join(
        [
            "data/jobs_production.json",
            "data/official_fields.json",
            "data/prd_alpha_ops_v3.md",
        ]
    )
    changed_stdout = "\n".join(
        [
            "data/jobs_production.json",
            "data/official_fields.json",
        ]
    )

    def fake_run(*args, **kwargs):
        command = args[0]
        if command[:3] == ["git", "ls-files", "data"]:
            return SimpleNamespace(returncode=0, stdout=tracked_stdout, stderr="")
        if command[:2] == ["git", "diff"] and "--cached" not in command:
            return SimpleNamespace(returncode=0, stdout=changed_stdout, stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(check_tracked_data_inventory.subprocess, "run", fake_run)

    result = check_tracked_data_inventory.inventory_tracked_data(
        tmp_path,
        fail_on_changed_runtime_generated=True,
    )

    assert result["ok"] is False
    assert result["changed_tracked_data_files"] == [
        "data/jobs_production.json",
        "data/official_fields.json",
    ]
    assert result["changed_categories"] == {
        "official_snapshot": ["data/official_fields.json"],
        "runtime_generated": ["data/jobs_production.json"],
    }
    assert result["changed_runtime_generated_files"] == ["data/jobs_production.json"]
    assert result["findings"] == [
        {
            "code": "changed_runtime_generated_data",
            "path": "data/jobs_production.json",
            "message": "Runtime-generated data file has local tracked changes: data/jobs_production.json",
        }
    ]


def test_changed_data_inventory_ignores_paths_no_longer_tracked(monkeypatch, tmp_path):
    def fake_run(*args, **kwargs):
        command = args[0]
        if command[:3] == ["git", "ls-files", "data"]:
            return SimpleNamespace(returncode=0, stdout="data/jobs_production.json\n", stderr="")
        if command[:2] == ["git", "diff"] and "--cached" in command:
            return SimpleNamespace(returncode=0, stdout="data/run_history/run_removed.json\n", stderr="")
        if command[:2] == ["git", "diff"]:
            return SimpleNamespace(returncode=0, stdout="data/jobs_production.json\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(check_tracked_data_inventory.subprocess, "run", fake_run)

    result = check_tracked_data_inventory.inventory_tracked_data(tmp_path)

    assert result["changed_tracked_data_files"] == ["data/jobs_production.json"]
    assert result["changed_runtime_generated_files"] == ["data/jobs_production.json"]


def test_changed_runtime_generated_strict_mode_respects_keep_decisions(monkeypatch, tmp_path):
    tracked_stdout = "\n".join(
        [
            "data/jobs_production.json",
            "data/run_history/run_123.json",
        ]
    )
    changed_stdout = "\n".join(
        [
            "data/jobs_production.json",
            "data/run_history/run_123.json",
        ]
    )
    plan = tmp_path / "boundary.json"
    plan.write_text(
        """
{
  "schema_version": "tracked_data_boundary_plan.v1",
  "tracked_runtime_generated_data": {
    "data/jobs_production.json": {"status": "keep"},
    "data/run_history/run_123.json": {"status": "remove"}
  }
}
""",
        encoding="utf-8",
    )

    def fake_run(*args, **kwargs):
        command = args[0]
        if command[:3] == ["git", "ls-files", "data"]:
            return SimpleNamespace(returncode=0, stdout=tracked_stdout, stderr="")
        if command[:2] == ["git", "diff"] and "--cached" not in command:
            return SimpleNamespace(returncode=0, stdout=changed_stdout, stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(check_tracked_data_inventory.subprocess, "run", fake_run)

    result = check_tracked_data_inventory.inventory_tracked_data(
        tmp_path,
        boundary_plan_path=plan,
        fail_on_changed_runtime_generated=True,
    )

    assert result["ok"] is False
    assert result["changed_runtime_generated_files"] == [
        "data/jobs_production.json",
        "data/run_history/run_123.json",
    ]
    assert result["boundary_plan"]["keep_files"] == ["data/jobs_production.json"]
    assert result["boundary_plan"]["recommendations"]["changed_recommended_remove_files"] == [
        "data/run_history/run_123.json"
    ]
    assert result["findings"] == [
        {
            "code": "changed_runtime_generated_data",
            "path": "data/run_history/run_123.json",
            "message": "Runtime-generated data file has local tracked changes: data/run_history/run_123.json",
        }
    ]


def test_tracked_data_inventory_reads_boundary_plan_without_failing_by_default(monkeypatch, tmp_path):
    stdout = "\n".join(
        [
            "data/jobs_production.json",
            "data/run_history/run_123.json",
            "data/checkpoints/run.checkpoint.json",
        ]
    )
    plan = tmp_path / "boundary.json"
    plan.write_text(
        """
{
  "schema_version": "tracked_data_boundary_plan.v1",
  "tracked_runtime_generated_data": {
    "data/jobs_production.json": {"status": "keep"},
    "data/run_history/run_123.json": {"status": "pending_decision"},
    "data/stale.json": {"status": "remove"}
  }
}
""",
        encoding="utf-8",
    )

    def fake_run(*args, **kwargs):
        command = args[0]
        if command[:3] == ["git", "ls-files", "data"]:
            return SimpleNamespace(returncode=0, stdout=stdout, stderr="")
        if command[:2] == ["git", "diff"] and "--cached" not in command:
            return SimpleNamespace(returncode=0, stdout="data/jobs_production.json\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(check_tracked_data_inventory.subprocess, "run", fake_run)

    result = check_tracked_data_inventory.inventory_tracked_data(tmp_path, boundary_plan_path=plan)

    assert result["ok"] is True
    boundary = result["boundary_plan"]
    assert boundary["present"] is True
    assert boundary["keep_files"] == ["data/jobs_production.json"]
    assert boundary["pending_decision_files"] == ["data/run_history/run_123.json"]
    assert boundary["missing_decision_files"] == ["data/checkpoints/run.checkpoint.json"]
    assert boundary["stale_entries"] == ["data/stale.json"]
    assert boundary["unresolved_count"] == 2
    assert boundary["recommendations"]["recommended_remove_files"] == [
        "data/checkpoints/run.checkpoint.json",
        "data/run_history/run_123.json",
    ]
    assert [task["id"] for task in boundary["decision_todo"]] == [
        "decide_runtime_generated_boundary",
        "cleanup_recommended_runtime_generated_data",
    ]
    assert boundary["decision_todo"][0]["strict_gate"] == "--fail-on-unresolved-boundary"
    assert boundary["decision_todo"][0]["count"] == 2
    assert boundary["decision_todo"][1]["strict_gate"] == "--fail-on-runtime-generated"
    assert boundary["decision_todo"][1]["count"] == 2
    assert result["findings"] == []


def test_tracked_data_inventory_can_fail_on_unresolved_boundary_plan(monkeypatch, tmp_path):
    stdout = "\n".join(
        [
            "data/jobs_production.json",
            "data/run_history/run_123.json",
        ]
    )
    plan = tmp_path / "boundary.json"
    plan.write_text(
        """
{
  "schema_version": "tracked_data_boundary_plan.v1",
  "tracked_runtime_generated_data": {
    "data/jobs_production.json": {"status": "remove"}
  }
}
""",
        encoding="utf-8",
    )

    def fake_run(*args, **kwargs):
        command = args[0]
        if command[:3] == ["git", "ls-files", "data"]:
            return SimpleNamespace(returncode=0, stdout=stdout, stderr="")
        if command[:2] == ["git", "diff"] and "--cached" not in command:
            return SimpleNamespace(returncode=0, stdout="data/jobs_production.json\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(check_tracked_data_inventory.subprocess, "run", fake_run)

    result = check_tracked_data_inventory.inventory_tracked_data(
        tmp_path,
        boundary_plan_path=plan,
        fail_on_unresolved_boundary=True,
    )

    assert result["ok"] is False
    assert result["boundary_plan"]["remove_files"] == ["data/jobs_production.json"]
    assert result["boundary_plan"]["missing_decision_files"] == ["data/run_history/run_123.json"]
    assert result["boundary_plan"]["recommendations"]["changed_recommended_remove_files"] == [
        "data/jobs_production.json"
    ]
    assert [task["id"] for task in result["boundary_plan"]["decision_todo"]] == [
        "decide_runtime_generated_boundary",
        "resolve_changed_runtime_generated_data",
        "cleanup_recommended_runtime_generated_data",
    ]
    assert result["boundary_plan"]["decision_todo"][0]["files"] == ["data/run_history/run_123.json"]
    assert result["findings"] == [
        {
            "code": "tracked_data_boundary_unresolved",
            "path": str(plan.resolve()),
            "message": "Tracked runtime-generated data has pending or missing keep/remove decisions.",
            "pending_decision_files": [],
            "missing_decision_files": ["data/run_history/run_123.json"],
        }
    ]


def test_tracked_data_inventory_can_fail_on_stale_boundary_plan(monkeypatch, tmp_path):
    stdout = "data/jobs_production.json\n"
    plan = tmp_path / "boundary.json"
    plan.write_text(
        """
{
  "schema_version": "tracked_data_boundary_plan.v1",
  "tracked_runtime_generated_data": {
    "data/jobs_production.json": {"status": "keep"},
    "data/run_history/run_123.json": {"status": "remove"}
  }
}
""",
        encoding="utf-8",
    )

    def fake_run(*args, **kwargs):
        command = args[0]
        if command[:3] == ["git", "ls-files", "data"]:
            return SimpleNamespace(returncode=0, stdout=stdout, stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(check_tracked_data_inventory.subprocess, "run", fake_run)

    result = check_tracked_data_inventory.inventory_tracked_data(
        tmp_path,
        boundary_plan_path=plan,
        fail_on_stale_boundary=True,
    )

    assert result["ok"] is False
    assert result["boundary_plan"]["keep_files"] == ["data/jobs_production.json"]
    assert result["boundary_plan"]["stale_entries"] == ["data/run_history/run_123.json"]
    assert result["findings"] == [
        {
            "code": "tracked_data_boundary_stale_entries",
            "path": str(plan.resolve()),
            "message": "Tracked data boundary plan references files that are no longer tracked runtime-generated data.",
            "stale_entries": ["data/run_history/run_123.json"],
        }
    ]


def test_runtime_generated_strict_mode_respects_keep_decisions(monkeypatch, tmp_path):
    stdout = "\n".join(
        [
            "data/jobs_production.json",
            "data/run_history/run_123.json",
        ]
    )
    plan = tmp_path / "boundary.json"
    plan.write_text(
        """
{
  "schema_version": "tracked_data_boundary_plan.v1",
  "tracked_runtime_generated_data": {
    "data/jobs_production.json": {"status": "keep"},
    "data/run_history/run_123.json": {"status": "pending_decision"}
  }
}
""",
        encoding="utf-8",
    )

    def fake_run(*args, **kwargs):
        command = args[0]
        if command[:3] == ["git", "ls-files", "data"]:
            return SimpleNamespace(returncode=0, stdout=stdout, stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(check_tracked_data_inventory.subprocess, "run", fake_run)

    result = check_tracked_data_inventory.inventory_tracked_data(
        tmp_path,
        boundary_plan_path=plan,
        fail_on_runtime_generated=True,
    )

    assert result["ok"] is False
    assert result["boundary_plan"]["keep_files"] == ["data/jobs_production.json"]
    assert result["boundary_plan"]["recommendations"]["recommended_remove_files"] == [
        "data/run_history/run_123.json"
    ]
    assert result["findings"] == [
        {
            "code": "tracked_runtime_generated_data",
            "path": "data/run_history/run_123.json",
            "message": "Runtime-generated data file is still tracked: data/run_history/run_123.json",
        }
    ]


def test_runtime_generated_strict_mode_honors_explicit_remove_for_referenced_files(monkeypatch, tmp_path):
    stdout = "data/jobs_production.json\n"
    plan = tmp_path / "boundary.json"
    plan.write_text(
        """
{
  "schema_version": "tracked_data_boundary_plan.v1",
  "tracked_runtime_generated_data": {
    "data/jobs_production.json": {"status": "remove"}
  }
}
""",
        encoding="utf-8",
    )

    def fake_run(*args, **kwargs):
        command = args[0]
        if command[:3] == ["git", "ls-files", "data"]:
            return SimpleNamespace(returncode=0, stdout=stdout, stderr="")
        if command[:2] == ["git", "diff"] and "--cached" not in command:
            return SimpleNamespace(returncode=0, stdout="data/jobs_production.json\n", stderr="")
        if command[:4] == ["git", "grep", "-n", "-F"]:
            return SimpleNamespace(
                returncode=0,
                stdout='brain_alpha_ops/e2e_report.py:18:Path("data/jobs_production.json"),\n',
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(check_tracked_data_inventory.subprocess, "run", fake_run)

    runtime_result = check_tracked_data_inventory.inventory_tracked_data(
        tmp_path,
        boundary_plan_path=plan,
        fail_on_runtime_generated=True,
    )
    changed_result = check_tracked_data_inventory.inventory_tracked_data(
        tmp_path,
        boundary_plan_path=plan,
        fail_on_changed_runtime_generated=True,
    )

    assert runtime_result["ok"] is False
    assert runtime_result["runtime_generated_references"] == {
        "data/jobs_production.json": [
            'brain_alpha_ops/e2e_report.py:18:Path("data/jobs_production.json"),'
        ]
    }
    assert runtime_result["boundary_plan"]["recommendations"]["recommended_remove_files"] == [
        "data/jobs_production.json"
    ]
    assert runtime_result["boundary_plan"]["recommendations"]["referenced_runtime_generated_files"] == [
        "data/jobs_production.json"
    ]
    assert runtime_result["findings"] == [
        {
            "code": "tracked_runtime_generated_data",
            "path": "data/jobs_production.json",
            "message": "Runtime-generated data file is still tracked: data/jobs_production.json",
        }
    ]
    assert changed_result["ok"] is False
    assert changed_result["boundary_plan"]["recommendations"]["changed_recommended_remove_files"] == [
        "data/jobs_production.json"
    ]
    assert changed_result["findings"] == [
        {
            "code": "changed_runtime_generated_data",
            "path": "data/jobs_production.json",
            "message": "Runtime-generated data file has local tracked changes: data/jobs_production.json",
        }
    ]


def test_tracked_data_inventory_main_prints_boundary_summary(monkeypatch, tmp_path, capsys):
    stdout = "\n".join(
        [
            "data/jobs_production.json",
            "data/run_history/run_123.json",
        ]
    )
    plan = tmp_path / "boundary.json"
    plan.write_text(
        """
{
  "schema_version": "tracked_data_boundary_plan.v1",
  "tracked_runtime_generated_data": {
    "data/jobs_production.json": {"status": "keep"}
  }
}
""",
        encoding="utf-8",
    )

    def fake_run(*args, **kwargs):
        command = args[0]
        if command[:3] == ["git", "ls-files", "data"]:
            return SimpleNamespace(returncode=0, stdout=stdout, stderr="")
        if command[:2] == ["git", "diff"] and "--cached" not in command:
            return SimpleNamespace(returncode=0, stdout="data/jobs_production.json\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(check_tracked_data_inventory.subprocess, "run", fake_run)

    code = check_tracked_data_inventory.main(
        ["--root", str(tmp_path), "--boundary-plan", str(plan), "--show-files"]
    )

    assert code == 0
    output = capsys.readouterr().out
    assert "Tracked data inventory passed: 2 files classified." in output
    assert "Categories: runtime_generated=2." in output
    assert "Changed categories: runtime_generated=1." in output
    assert "Boundary plan: 1 unresolved, 0 pending, 1 missing, 0 stale, 1 keep, 0 remove." in output
    assert "Cleanup candidates: 1 recommended, 0 changed, 0 referenced." in output
    assert "- decide_runtime_generated_boundary: 1 files via --fail-on-unresolved-boundary" in output
    assert "- cleanup_recommended_runtime_generated_data: 1 files via --fail-on-runtime-generated" in output
    assert "Runtime-generated files:" in output
    assert "- [keep,changed] data/jobs_production.json" in output
    assert "- [missing] data/run_history/run_123.json" in output


def test_tracked_data_inventory_reports_runtime_generated_references(monkeypatch, tmp_path):
    stdout = "\n".join(
        [
            "data/jobs_production.json",
            "data/run_history/run_123.json",
        ]
    )
    plan = tmp_path / "boundary.json"
    plan.write_text(
        """
{
  "schema_version": "tracked_data_boundary_plan.v1",
  "tracked_runtime_generated_data": {
    "data/jobs_production.json": {"status": "pending_decision"},
    "data/run_history/run_123.json": {"status": "pending_decision"}
  }
}
""",
        encoding="utf-8",
    )

    def fake_run(*args, **kwargs):
        command = args[0]
        if command[:3] == ["git", "ls-files", "data"]:
            return SimpleNamespace(returncode=0, stdout=stdout, stderr="")
        if command[:2] == ["git", "diff"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if command[:4] == ["git", "grep", "-n", "-F"]:
            rel_path = command[-1]
            if rel_path == "data/jobs_production.json":
                    return SimpleNamespace(
                    returncode=0,
                    stdout=(
                        ".gitignore:42:data/jobs_production.json\n"
                        "brain_alpha_ops/e2e_report.py:18:Path(\"data/jobs_production.json\"),\n"
                        "tests/test_tracked_data_inventory.py:11:data/jobs_production.json\n"
                        "docs/TRACKED_DATA_BOUNDARY_PLAN.json:96:data/jobs_production.json\n"
                    ),
                    stderr="",
                )
            return SimpleNamespace(returncode=1, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(check_tracked_data_inventory.subprocess, "run", fake_run)

    result = check_tracked_data_inventory.inventory_tracked_data(tmp_path, boundary_plan_path=plan)

    assert result["runtime_generated_references"] == {
        "data/jobs_production.json": [
            'brain_alpha_ops/e2e_report.py:18:Path("data/jobs_production.json"),'
        ]
    }
    recommendations = result["boundary_plan"]["recommendations"]
    assert recommendations["referenced_runtime_generated_files"] == ["data/jobs_production.json"]
    assert recommendations["referenced_runtime_generated_count"] == 1
    assert recommendations["recommended_remove_files"] == ["data/run_history/run_123.json"]
    assert recommendations["recommended_remove_count"] == 1
    assert recommendations["changed_recommended_remove_files"] == []
    assert recommendations["changed_recommended_remove_count"] == 0
