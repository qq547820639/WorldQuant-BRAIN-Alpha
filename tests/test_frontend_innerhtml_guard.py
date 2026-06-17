from __future__ import annotations

from scripts.check_frontend_innerhtml import check_frontend_innerhtml


def test_frontend_innerhtml_guard_scans_current_react_source_by_default():
    result = check_frontend_innerhtml()

    assert result["ok"] is True
    assert result["files_checked"] > 0


def test_frontend_innerhtml_guard_allows_safe_and_raw_html_wrappers(tmp_path):
    (tmp_path / "utils.js").write_text(
        "Utils.setSafeHtml = function (el, html) {\n"
        "  el.innerHTML = Utils.escapeHtml(String(html ?? ''));\n"
        "}\n"
        "Utils.setRawHtml = function (el, html) {\n"
        "  el.innerHTML = String(html ?? '');\n"
        "}\n",
        encoding="utf-8",
    )

    result = check_frontend_innerhtml(tmp_path)

    assert result["ok"] is True
    assert result["checked"] == 2
    assert result["findings"] == []


def test_frontend_innerhtml_guard_rejects_raw_set_safe_html_wrapper(tmp_path):
    (tmp_path / "utils.js").write_text(
        "Utils.setSafeHtml = function (el, html) {\n"
        "  el.innerHTML = String(html ?? '');\n"
        "}\n",
        encoding="utf-8",
    )

    result = check_frontend_innerhtml(tmp_path)

    assert result["ok"] is False
    assert result["findings"][0]["file"] == "utils.js"


def test_frontend_innerhtml_guard_rejects_misnamed_raw_html_alias(tmp_path):
    (tmp_path / "app.js").write_text(
        "var setSafeHtml = window.Utils.setRawHtml;\n",
        encoding="utf-8",
    )

    result = check_frontend_innerhtml(tmp_path)

    assert result["ok"] is False
    assert result["findings"][0]["sink"] == "misnamed_raw_alias"


def test_frontend_innerhtml_guard_rejects_unapproved_html_sinks(tmp_path):
    (tmp_path / "app.js").write_text(
        "function renderRaw(el, html, range) {\n"
        "  el.innerHTML = html;\n"
        "  el.outerHTML = html;\n"
        "  el.insertAdjacentHTML('beforeend', html);\n"
        "  document.write(html);\n"
        "  document.writeln(html);\n"
        "  range.createContextualFragment(html);\n"
        "}\n",
        encoding="utf-8",
    )

    result = check_frontend_innerhtml(tmp_path)

    assert result["ok"] is False
    assert result["checked"] == 6
    assert {finding["sink"] for finding in result["findings"]} == {
        "innerHTML",
        "outerHTML",
        "insertAdjacentHTML",
        "document.write",
        "document.writeln",
        "createContextualFragment",
    }


def test_frontend_innerhtml_guard_rejects_unapproved_set_raw_html_calls(tmp_path):
    (tmp_path / "app.js").write_text(
        "function renderUser(el, html) {\n"
        "  setRawHtml(el, html);\n"
        "}\n",
        encoding="utf-8",
    )

    result = check_frontend_innerhtml(tmp_path)

    assert result["ok"] is False
    assert result["findings"][0]["sink"] == "setRawHtml"


def test_frontend_innerhtml_guard_allows_reviewed_escaped_table_renderer(tmp_path):
    (tmp_path / "result-table.js").write_text(
        "function renderDesktopRows(tableBody, rows, columns) {\n"
        "  setRawHtml(tableBody, rows.map(function (row, idx) {\n"
        "    var title = row.id || ('row ' + (idx + 1));\n"
        "    var rowHtml = '<tr data-id=\"' + escapeAttr(row.id || '') + '\" aria-label=\"打开详情：' + escapeAttr(title) + '\">';\n"
        "    rowHtml += columns.map(function (col) {\n"
        "      var rendered = col.render ? col.render(row.id, row, idx) : String(row.id ?? '');\n"
        "      return '<td>' + renderSafeHtmlFragment(rendered, col.htmlType) + '</td>';\n"
        "    }).join('');\n"
        "    return rowHtml + '</tr>';\n"
        "  }).join(''));\n"
        "}\n",
        encoding="utf-8",
    )

    result = check_frontend_innerhtml(tmp_path)

    assert result["ok"] is True
    assert result["raw_calls_checked"] == 1
