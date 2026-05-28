from pathlib import Path

from scripts.check_web_console_contract import check_web_console_contract, main


VALID_HTML = """
<!doctype html>
<html>
<head>
  <title>BRAIN Alpha Ops</title>
  <link rel="icon" href="data:image/svg+xml,%3Csvg%3E%3C/svg%3E">
</head>
<body>
  <form id="connectionForm">
    <input id="username">
    <input id="password" type="password">
    <button id="connTestBtn" type="submit" data-action="test-connection">测试连接</button>
  </form>
  <script>
    function submitConnectionForm(event) {}
    connectionForm.addEventListener('submit', submitConnectionForm);
    var DATA_VIEWS = ['cloud', 'lifecycle'];
    var titles = { lifecycle: '生命周期' };
    switch (view) { case 'lifecycle': return buildLifecycleRows(lifecycle); }
  </script>
</body>
</html>
"""


def test_web_console_contract_accepts_current_contract(tmp_path):
    html_path = tmp_path / "index.html"
    html_path.write_text(VALID_HTML, encoding="utf-8")

    result = check_web_console_contract(html_path)

    assert result["ok"] is True
    assert result["schema_version"] == "web_console_contract_check.v1"
    assert result["facts"]["connection_form_tag"] == "form"
    assert result["facts"]["password_inside_connection_form"] is True
    assert result["facts"]["conn_test_button_type"] == "submit"
    assert all(result["facts"]["lifecycle_snippets"].values())


def test_web_console_contract_rejects_default_favicon_and_detached_password(tmp_path):
    html_path = tmp_path / "index.html"
    html_path.write_text(
        VALID_HTML.replace("data:image/svg+xml,%3Csvg%3E%3C/svg%3E", "/favicon.ico")
        .replace('<input id="password" type="password">', '</form><input id="password" type="password"><form>'),
        encoding="utf-8",
    )

    result = check_web_console_contract(html_path)

    assert result["ok"] is False
    codes = {finding["code"] for finding in result["findings"]}
    assert "favicon_no_default_ico" in codes
    assert "password_form_semantics" in codes


def test_web_console_contract_json_cli(tmp_path, capsys):
    html_path = tmp_path / "index.html"
    html_path.write_text(VALID_HTML, encoding="utf-8")

    code = main(["--html", str(html_path), "--json"])

    assert code == 0
    assert '"web_console_contract_check.v1"' in capsys.readouterr().out


def test_web_console_contract_accepts_shipped_html():
    root = Path(__file__).resolve().parents[1]

    result = check_web_console_contract(root / "brain_alpha_ops" / "web" / "index.html")

    assert result["ok"] is True
