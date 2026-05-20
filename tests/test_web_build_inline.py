from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def _load_build_inline(path: Path):
    spec = importlib.util.spec_from_file_location("web_build_inline", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


build_inline = _load_build_inline(ROOT / "brain_alpha_ops" / "web" / "build_inline.py")


def test_build_inline_replaces_template_markers_with_js_sources():
    html, stats = build_inline.build_inline("<body><!-- inline:js/utils.js --></body>")

    assert stats["replaced"] == 1
    assert stats["missing"] == []
    assert "window.Utils = Utils" in html
    assert "<!-- inline:" not in html


def test_build_inline_check_detects_stale_output(tmp_path):
    output = tmp_path / "index.html"
    output.write_text("<html>stale</html>", encoding="utf-8")

    result = build_inline.check(output)

    assert result["ok"] is False
    assert "stale" in result["error"]
    assert result["actual_bytes"] == len("<html>stale</html>".encode("utf-8"))


def test_build_inline_writes_expected_output(tmp_path):
    output = tmp_path / "index.html"

    result = build_inline.build(output_path=output)

    assert result["ok"] is True
    assert output.is_file()
    assert build_inline.check(output)["ok"] is True
    assert result["replaced"] >= 13


def test_legacy_build_inline_entrypoint_delegates_to_web_builder():
    legacy = _load_build_inline(ROOT / "brain_alpha_ops" / "build_inline.py")

    html, stats = legacy.build_inline("<body><!-- inline:js/utils.js --></body>")

    assert stats["replaced"] == 1
    assert "window.Utils = Utils" in html
    assert legacy.check(ROOT / "brain_alpha_ops" / "web" / "index.html")["ok"] is True


def test_legacy_build_inline_cli_check_uses_current_template():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "brain_alpha_ops" / "build_inline.py"), "--check", "--json"],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
    )

    assert proc.returncode == 0
    assert '"ok": true' in proc.stdout
    assert '"replaced": 13' in proc.stdout
