from __future__ import annotations

from pathlib import Path

from scripts.check_frontend_silent_catches import check_frontend_silent_catches


def test_frontend_silent_catches_guard_accepts_current_tree():
    result = check_frontend_silent_catches()

    assert result["ok"] is True
    assert result["schema_version"] == "frontend_silent_catches.v1"
    assert result["silent_catch_count"] == 0
    assert result["findings"] == []


def test_frontend_silent_catches_guard_rejects_silent_catch(tmp_path):
    root = tmp_path / "brain_alpha_ops" / "web"
    js_root = root / "js"
    js_root.mkdir(parents=True)
    (root / "index.html").write_text("<html></html>", encoding="utf-8")
    (js_root / "sample.js").write_text(
        "function demo() { try { run(); } catch (e) { /* ignore */ } }",
        encoding="utf-8",
    )

    result = check_frontend_silent_catches(root)

    assert result["ok"] is False
    assert result["silent_catch_count"] == 1
    assert result["findings"][0]["file"] == "js/sample.js"
