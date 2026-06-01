from __future__ import annotations

from brain_alpha_ops import web
from scripts.check_web_facade_contract import check_web_facade_contract


def test_web_facade_contract_accepts_current_web_module():
    result = check_web_facade_contract()

    assert result["ok"] is True
    assert result["schema_version"] == "web_facade_contract_check.v1"
    assert result["has_context_class"] is True
    assert result["has_context_factory"] is True
    assert result["direct_sys_modules_count"] == 1
    assert result["runtime_facade_sys_modules_count"] == 0
    assert result["lambda_alias_count"] == 0
    assert result["public_brain_alpha_import_count"] == 0


def test_web_application_context_is_exposed():
    ctx = web.web_application_context()

    assert ctx is web.WEB_APPLICATION_CONTEXT
    assert ctx._module is web


def test_web_application_context_builds_grouped_dispatch_context():
    ctx = web._handler_dispatch_context()

    assert isinstance(ctx.core, web.WebDispatchCoreContext)
    assert isinstance(ctx.job, web.WebDispatchJobContext)
    assert ctx.route_for is web.route_for
    assert ctx.jobs is web.JOBS


def test_web_facade_contract_rejects_runtime_facade_sys_modules(tmp_path):
    web_path = tmp_path / "web.py"
    web_path.write_text(
        """
import sys

class WebApplicationContext:
    pass

def web_application_context():
    return None

WEB_APPLICATION_CONTEXT = WebApplicationContext(sys.modules[__name__])
bad = lambda payload: _runtime_facade.test_connection(sys.modules[__name__], payload)
""",
        encoding="utf-8",
    )

    result = check_web_facade_contract(web_path)

    assert result["ok"] is False
    assert any(finding["code"] == "runtime_facade_sys_modules_call" for finding in result["findings"])


def test_web_facade_contract_rejects_public_brain_alpha_imports(tmp_path):
    web_path = tmp_path / "web.py"
    web_path.write_text(
        """
import sys
from brain_alpha_ops.web_routes import route_for

class WebApplicationContext:
    pass

def web_application_context():
    return None

WEB_APPLICATION_CONTEXT = WebApplicationContext(sys.modules[__name__])
""",
        encoding="utf-8",
    )

    result = check_web_facade_contract(web_path)

    assert result["ok"] is False
    assert result["public_brain_alpha_import_count"] == 1
    assert any(finding["code"] == "public_brain_alpha_import" for finding in result["findings"])
