from __future__ import annotations

import json
from pathlib import Path

import brain_alpha_ops.build_inline as build_inline


ROOT = Path(__file__).resolve().parents[1]


def test_react_dist_check_reports_current_assets():
    result = build_inline.check()

    assert result["ok"] is True
    assert result["frontend"] == "react"
    assert result["asset_count"] >= 2
    assert result["missing"] == []
    assert all(ref.startswith("/assets/") for ref in result["asset_refs"])


def test_react_dist_check_detects_missing_hashed_asset(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    index = dist / "index.html"
    index.write_text('<script type="module" src="/assets/missing.js"></script>', encoding="utf-8")

    result = build_inline.check(index)

    assert result["ok"] is False
    assert result["missing"] == ["/assets/missing.js"]
    assert "missing assets" in result["error"]


def test_react_dist_check_rejects_legacy_inline_markers(tmp_path):
    index = tmp_path / "index.html"
    index.write_text("<body><!-- inline:js/app.js --></body>", encoding="utf-8")

    result = build_inline.check(index)

    assert result["ok"] is False
    assert "Legacy inline placeholders" in result["error"]


def test_compat_build_inline_strips_bom_without_replacing_markers():
    html, stats = build_inline.build_inline("\ufeff<body><!-- inline:js/app.js --></body>")

    assert html == "<body><!-- inline:js/app.js --></body>"
    assert stats["deprecated"] is True
    assert stats["replaced"] == 0
    assert stats["css_replaced"] == 0


def test_compat_cli_check_reports_react_dist(capsys):
    return_code = build_inline.main(["--check", "--json"])
    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert return_code == 0
    assert data["ok"] is True
    assert data["schema_version"] == "react_dist_readiness.v1"
