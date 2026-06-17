from __future__ import annotations

from pathlib import Path

from scripts.check_frontend_silent_catches import check_frontend_silent_catches


def test_frontend_silent_catches_guard_accepts_current_tree():
    result = check_frontend_silent_catches()

    assert result["ok"] is True
    assert result["schema_version"] == "frontend_silent_catches.v1"
    assert result["checked_files"] > 0
    assert result["silent_catch_count"] == 0
    assert result["findings"] == []


def test_frontend_silent_catches_guard_rejects_silent_catch(tmp_path):
    root = tmp_path / "brain_alpha_ops" / "web"
    js_root = root / "js"
    react_src = root / "react_app" / "src"
    js_root.mkdir(parents=True)
    react_src.mkdir(parents=True)
    (root / "index.html").write_text("<html></html>", encoding="utf-8")
    (js_root / "sample.js").write_text(
        "function demo() { try { run(); } catch (e) { /* ignore */ } }",
        encoding="utf-8",
    )
    (react_src / "sample.tsx").write_text(
        "export function Demo() { try { run(); } catch (e) { // ignore\n } return null; }",
        encoding="utf-8",
    )

    result = check_frontend_silent_catches(root)

    assert result["ok"] is False
    assert result["silent_catch_count"] == 2
    assert [finding["file"] for finding in result["findings"]] == [
        "js/sample.js",
        "react_app/src/sample.tsx",
    ]
