from __future__ import annotations

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
        f"{web_html.CSRF_TOKEN_PLACEHOLDER}"
        f"{web_html.STREAM_TOKEN_PLACEHOLDER}"
        "</html>"
    )
    path = tmp_path / "index.html"
    path.write_text(source, encoding="utf-8")

    assert web_html.load_html(path) == source
    assert web_html.render_html("csrf-token", "stream-token", source) == "<html>csrf-tokenstream-token</html>"


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


def test_html_csp_hashes_inline_blocks_without_unsafe_inline():
    html = "<style>.ok{color:red}</style><script>console.log('ok')</script>"

    csp = web_html.content_security_policy_for_html(html)

    assert "script-src 'self'" in csp
    assert "style-src 'self'" in csp
    assert "unsafe-inline" not in csp
    assert csp.count("'sha256-") == 2
