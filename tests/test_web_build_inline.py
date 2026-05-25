from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_build_inline(path: Path):
    spec = importlib.util.spec_from_file_location("web_build_inline", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
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
    assert result["css_replaced"] == 1
    assert "css/app.css" in result["css_sources"]
    assert "\ufeff" not in output.read_text(encoding="utf-8")


def test_build_inline_strips_bom_from_template_and_inlined_sources():
    html, stats = build_inline.build_inline(
        "\ufeff<body><!-- inline-css:css/app.css --><!-- inline:js/app.js --></body>"
    )

    assert stats["replaced"] == 1
    assert stats["css_replaced"] == 1
    assert "\ufeff" not in html


def test_legacy_build_inline_entrypoint_delegates_to_web_builder():
    legacy = _load_build_inline(ROOT / "brain_alpha_ops" / "build_inline.py")

    html, stats = legacy.build_inline("<body><!-- inline:js/utils.js --></body>")

    assert stats["replaced"] == 1
    assert "window.Utils = Utils" in html
    assert legacy.check(ROOT / "brain_alpha_ops" / "web" / "index.html")["ok"] is True


def test_legacy_build_inline_cli_check_uses_current_template(capsys):
    legacy = _load_build_inline(ROOT / "brain_alpha_ops" / "build_inline.py")

    return_code = legacy.main(["--check", "--json"])
    captured = capsys.readouterr()

    assert return_code == 0
    assert '"ok": true' in captured.out
    assert '"replaced":' in captured.out
