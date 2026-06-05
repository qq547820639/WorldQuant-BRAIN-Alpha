from __future__ import annotations

from scripts.check_python_silent_broad_exceptions import check_python_silent_broad_exceptions


def test_python_silent_broad_exceptions_guard_accepts_current_tree():
    result = check_python_silent_broad_exceptions()

    assert result["ok"] is True
    assert result["schema_version"] == "python_silent_broad_exceptions.v1"
    assert result["silent_broad_exception_count"] == 0
    assert result["findings"] == []


def test_python_silent_broad_exceptions_guard_rejects_pass_body(tmp_path):
    root = tmp_path / "repo"
    pkg = root / "brain_alpha_ops"
    pkg.mkdir(parents=True)
    (pkg / "sample.py").write_text(
        "def demo():\n    try:\n        run()\n    except Exception:\n        pass\n",
        encoding="utf-8",
    )

    result = check_python_silent_broad_exceptions(root)

    assert result["ok"] is False
    assert result["silent_broad_exception_count"] == 1
    assert result["findings"][0]["file"] == "brain_alpha_ops/sample.py"
