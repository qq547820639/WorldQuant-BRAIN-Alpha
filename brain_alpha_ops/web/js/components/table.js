// brain_alpha_ops/web/js/components/table.js
// Generic table rendering — column-driven, replaces 6 row functions.

(function () {
  var $ = window.Utils.$;
  var esc = window.Utils.escapeHtml;

  function renderTable(containerId, columns, rows, options) {
    options = options || {};
    var container = $(containerId);
    if (!container) return;

    var maxRows = options.maxRows || 300;
    var emptyText = options.emptyText || "暂无数据";

    if (!rows || !rows.length) {
      container.innerHTML = '<tr><td colspan="' + columns.length + '" style="text-align:center;color:var(--muted);padding:20px">' + esc(emptyText) + '</td></tr>';
      return;
    }

    var displayRows = rows.slice(0, maxRows);

    container.innerHTML = displayRows.map(function (row, idx) {
      return '<tr data-kind="' + esc(row.kind || "") + '" data-id="' + esc(row.id || "") + '">' +
        columns.map(function (col) {
          var value = typeof col.accessor === "function"
            ? col.accessor(row, idx)
            : (row.raw || row)[col.accessor];
          var cls = col.className || "";
          if (col.render) {
            var rendered = col.render(value, row, idx);
            return '<td class="' + esc(cls) + '">' + (col.trustedHtml ? rendered : esc(String(rendered ?? ""))) + '</td>';
          }
          return '<td class="' + esc(cls) + '">' + esc(String(value ?? "")) + '</td>';
        }).join("") +
        '</tr>';
    }).join("");
  }

  // Status badge renderer
  function statusBadge(status, color) {
    return '<span class="pill" style="background:var(--' + (color || 'soft') + ');color:var(--' + (color || 'muted') + ')">' + esc(status || "") + '</span>';
  }

  // Score-colored text
  function scoreSpan(val) {
    var n = Number(val);
    if (!Number.isFinite(n)) return esc(String(val ?? "-"));
    var color = n >= 70 ? "var(--good)" : n >= 50 ? "var(--warn)" : "var(--bad)";
    return '<span style="font-weight:800;color:' + color + '">' + n.toFixed(1) + '</span>';
  }

  window.Table = {
    render: renderTable,
    statusBadge: statusBadge,
    scoreSpan: scoreSpan,
  };
})();
