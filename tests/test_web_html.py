from __future__ import annotations

import re
from pathlib import Path
import threading

import pytest

from brain_alpha_ops import web_html


@pytest.fixture(autouse=True)
def _reset_html_cache():
    web_html.reset_html_cache()
    yield
    web_html.reset_html_cache()


def test_render_html_replaces_session_placeholders_without_touching_cache(tmp_path):
    source = (
        "<html>"
        f"'{web_html.CSRF_TOKEN_PLACEHOLDER}'"
        f'"{web_html.STREAM_TOKEN_PLACEHOLDER}"'
        "</html>"
    )
    path = tmp_path / "index.html"
    path.write_text(source, encoding="utf-8")

    assert web_html.load_html(path) == source
    assert web_html.render_html("csrf-token", "stream-token", source) == "<html>'csrf-token'\"stream-token\"</html>"


def test_render_html_keeps_react_window_token_property_names():
    source = (
        f"<script>window.{web_html.CSRF_TOKEN_PLACEHOLDER} = '{web_html.CSRF_TOKEN_PLACEHOLDER}';"
        f"const csrf = window.{web_html.CSRF_TOKEN_PLACEHOLDER};"
        f"window.{web_html.STREAM_TOKEN_PLACEHOLDER} = \"{web_html.STREAM_TOKEN_PLACEHOLDER}\";"
        f"const stream = window.{web_html.STREAM_TOKEN_PLACEHOLDER};</script>"
    )

    rendered = web_html.render_html("csrf-token", "stream-token", source)

    assert f"window.{web_html.CSRF_TOKEN_PLACEHOLDER} = 'csrf-token';" in rendered
    assert f"const csrf = window.{web_html.CSRF_TOKEN_PLACEHOLDER};" in rendered
    assert f"window.{web_html.STREAM_TOKEN_PLACEHOLDER} = \"stream-token\";" in rendered
    assert f"const stream = window.{web_html.STREAM_TOKEN_PLACEHOLDER};" in rendered


def test_default_load_html_uses_cache(monkeypatch, tmp_path):
    path = tmp_path / "index.html"
    path.write_text("<html>first</html>", encoding="utf-8")
    monkeypatch.setattr(web_html, "default_html_path", lambda: path)

    web_html.reset_html_cache()
    assert web_html.load_html() == "<html>first</html>"
    path.write_text("<html>second</html>", encoding="utf-8")
    assert web_html.load_html() == "<html>first</html>"

    web_html.reset_html_cache()
    assert web_html.load_html() == "<html>second</html>"


def test_default_html_path_falls_back_to_react_dist_when_production_html_is_absent(monkeypatch, tmp_path):
    module_path = tmp_path / "brain_alpha_ops" / "web_html.py"
    react_dist = tmp_path / "brain_alpha_ops" / "web" / "react_app" / "dist"
    react_dist.mkdir(parents=True)
    react_index = react_dist / "index.html"
    react_index.write_text("<html>react</html>", encoding="utf-8")
    monkeypatch.setattr(web_html, "__file__", str(module_path))

    assert web_html.default_html_path() == react_index


def test_default_html_path_selects_react_dist_only_when_explicitly_enabled(monkeypatch, tmp_path):
    module_path = tmp_path / "brain_alpha_ops" / "web_html.py"
    web_dir = tmp_path / "brain_alpha_ops" / "web"
    react_dist = web_dir / "react_app" / "dist"
    react_dist.mkdir(parents=True)
    inline_index = web_dir / "index.html"
    inline_index.write_text("<html>inline</html>", encoding="utf-8")
    react_index = react_dist / "index.html"
    react_index.write_text("<html>react</html>", encoding="utf-8")
    monkeypatch.setattr(web_html, "__file__", str(module_path))

    assert web_html.default_html_path() == inline_index
    monkeypatch.setenv(web_html.WEB_FRONTEND_ENV, web_html.REACT_FRONTEND)
    assert web_html.default_html_path() == react_index


def test_default_load_html_cache_tracks_selected_frontend(monkeypatch, tmp_path):
    module_path = tmp_path / "brain_alpha_ops" / "web_html.py"
    web_dir = tmp_path / "brain_alpha_ops" / "web"
    react_dist = web_dir / "react_app" / "dist"
    react_dist.mkdir(parents=True)
    (web_dir / "index.html").write_text("<html>inline</html>", encoding="utf-8")
    (react_dist / "index.html").write_text("<html>react</html>", encoding="utf-8")
    monkeypatch.setattr(web_html, "__file__", str(module_path))

    assert web_html.load_html() == "<html>inline</html>"
    monkeypatch.setenv(web_html.WEB_FRONTEND_ENV, web_html.REACT_FRONTEND)
    assert web_html.load_html() == "<html>react</html>"


def test_react_asset_resolution_is_opt_in_and_confined_to_dist_assets(monkeypatch, tmp_path):
    module_path = tmp_path / "brain_alpha_ops" / "web_html.py"
    assets_dir = tmp_path / "brain_alpha_ops" / "web" / "react_app" / "dist" / "assets"
    assets_dir.mkdir(parents=True)
    asset_path = assets_dir / "index-test.js"
    asset_path.write_bytes(b"console.log('react')")
    monkeypatch.setattr(web_html, "__file__", str(module_path))

    assert web_html.resolve_react_asset("/assets/index-test.js") is None
    assert web_html.resolve_react_asset("/assets/index-test.js", frontend=web_html.REACT_FRONTEND) == (
        b"console.log('react')",
        "text/javascript",
    )
    assert web_html.resolve_react_asset("/assets/../index.html", frontend=web_html.REACT_FRONTEND) is None
    assert web_html.resolve_react_asset("/assets/%2e%2e/index.html", frontend=web_html.REACT_FRONTEND) is None


def test_selected_frontend_rejects_unknown_value():
    with pytest.raises(ValueError, match=web_html.WEB_FRONTEND_ENV):
        web_html.selected_frontend("unknown")


def test_reset_html_cache_is_safe_under_concurrent_loads(monkeypatch, tmp_path):
    path = tmp_path / "index.html"
    path.write_text("<html>safe</html>", encoding="utf-8")
    monkeypatch.setattr(web_html, "default_html_path", lambda: path)

    errors: list[BaseException] = []

    def worker() -> None:
        try:
            for _ in range(200):
                web_html.reset_html_cache()
                assert web_html.load_html() == "<html>safe</html>"
        except BaseException as exc:  # pragma: no cover - defensive for thread failures
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []


def test_html_csp_hashes_inline_blocks_without_unsafe_inline():
    html = "<style>.ok{color:red}</style><script>console.log('ok')</script>"

    csp = web_html.content_security_policy_for_html(html)

    assert "script-src 'self'" in csp
    assert "style-src 'self'" in csp
    assert "unsafe-inline" not in csp
    assert csp.count("'sha256-") == 2


def test_html_csp_allows_react_cdn_sources_with_valid_spacing():
    html = (
        '<script src="https://cdn.tailwindcss.com"></script>'
        '<script src="https://unpkg.com/react@18/umd/react.production.min.js"></script>'
        "<script>console.log('app')</script>"
    )

    csp = web_html.content_security_policy_for_html(html)

    assert "script-src 'self' https://unpkg.com https://cdn.tailwindcss.com " in csp
    assert "'self'https://unpkg.com" not in csp
    assert "unsafe-inline" not in csp


def test_react_dist_artifact_uses_csp_compatible_runtime_injection():
    root = Path(__file__).resolve().parents[1]
    dist = root / "brain_alpha_ops" / "web" / "react_app" / "dist"
    html = (dist / "index.html").read_text(encoding="utf-8")

    rendered = web_html.render_html("csrf-token", "stream-token", html)
    csp = web_html.content_security_policy_for_html(rendered)
    asset_paths = re.findall(r'/(assets/[^"\']+)', html)
    asset_text = "\n".join((dist / asset_path).read_text(encoding="utf-8") for asset_path in asset_paths)

    assert "@babel/standalone" not in html
    assert 'type="text/babel"' not in html
    assert asset_paths
    assert re.search(r"/assets/index-[^\"']+\.js", html)
    assert re.search(r"/assets/index-[^\"']+\.css", html)
    assert 'credentials="same-origin"' in asset_text
    assert "X-Brain-Alpha-CSRF" in asset_text
    assert "X-Brain-Alpha-Request-ID" in asset_text
    assert "X-Brain-Alpha-Request-Timestamp" in asset_text
    assert 'stream_token=' in asset_text
    assert f'content="csrf-token"' in rendered
    assert f'content="stream-token"' in rendered
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp
    assert "unpkg.com" not in csp
    assert "cdn.tailwindcss.com" not in csp


def test_production_html_view_navigation_has_tab_semantics():
    html = web_html.load_html()

    assert 'id="mainContent" role="tabpanel" aria-labelledby="tableTitle"' in html
    assert 'id="viewTabs" role="tablist" aria-label="视图导航"' in html
    assert 'role="tab" aria-selected="' in html
    assert 'tabindex="' in html
    assert 'aria-controls="mainContent"' in html
    assert "event.key === 'ArrowRight'" in html
    assert "event.key === 'Home'" in html
    assert "event.key === 'End'" in html


def test_production_html_workflow_progress_and_confirm_dialog_have_accessible_names():
    html = web_html.load_html()

    assert 'id="workflowRail" role="navigation" aria-label="核心任务导航" aria-describedby="workflowStatus"' in html
    assert 'class="workflow-steps" role="group" aria-label="核心任务步骤"' in html
    assert 'id="workflowProduceHint"' in html
    assert 'aria-describedby="workflowProduceHint"' in html
    assert 'id="cloudSyncMeta" class="progress-meta" role="status" aria-live="polite"' in html
    assert 'id="checkProgressMeta" class="progress-meta" role="status" aria-live="polite"' in html
    assert 'role="progressbar" aria-labelledby="syncButton" aria-describedby="cloudSyncMeta"' in html
    assert 'role="progressbar" aria-labelledby="moduleActionTitle" aria-describedby="checkProgressMeta"' in html
    assert 'aria-labelledby="confirmTitle" aria-describedby="confirmText"' in html
    assert 'id="confirmTitle" class="sr-only"' in html
