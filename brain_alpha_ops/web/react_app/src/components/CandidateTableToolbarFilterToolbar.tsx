import { useCallback, useRef, useState } from "react";
import type { Candidate } from "@/types";
import {
  candidateIdentity,
  candidateText,
} from "./CandidateTableUtils";
import Tooltip from "./Tooltip";

export interface FilterToolbarProps {
  filter: string;
  filterInput?: string;
  apiLoading: boolean;
  onFilterChange: (value: string) => void;
  onRetryLoad: () => void;
  showStarredOnly?: boolean;
  onToggleStarFilter?: () => void;
  sortedCandidates: Candidate[];
}

function exportCSV(candidates: Candidate[], filename: string): void {
  const headers = ["ID", "表达式", "家族", "状态", "总分", "Sharpe", "Fitness", "Turnover", "阻断原因"];
  const rows = candidates.map((c) => [
    candidateIdentity(c) ?? "",
    candidateText(c.expression) ?? "",
    candidateText(c.family) ?? "",
    c.status ?? "",
    c.scorecard?.total_score ?? "",
    c.scorecard?.sharpe ?? "",
    c.scorecard?.fitness ?? "",
    c.scorecard?.turnover ?? "",
    (Array.isArray(c.blocking_reasons) ? c.blocking_reasons.join(";") : "") ?? "",
  ]);
  const csv = [headers, ...rows]
    .map((r) => r.map((v) => `"${String(v ?? "")}"`).join(","))
    .join("\n");
  const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function exportJSON(candidates: Candidate[], filename: string): void {
  const json = JSON.stringify(candidates, null, 2);
  const blob = new Blob([json], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function FilterToolbar({
  filter,
  filterInput,
  apiLoading,
  onFilterChange,
  onRetryLoad,
  showStarredOnly = false,
  onToggleStarFilter,
  sortedCandidates,
}: FilterToolbarProps) {
  const [exportOpen, setExportOpen] = useState(false);
  const exportRef = useRef<HTMLDivElement>(null);

  const handleExportCSV = useCallback(() => {
    const ts = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
    exportCSV(sortedCandidates, `candidates_${ts}.csv`);
    setExportOpen(false);
  }, [sortedCandidates]);

  const handleExportJSON = useCallback(() => {
    const ts = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
    exportJSON(sortedCandidates, `candidates_${ts}.json`);
    setExportOpen(false);
  }, [sortedCandidates]);

  return (
    <div className="flex flex-col sm:flex-row gap-3 mb-4">
      <input
        type="text"
        aria-label="过滤候选"
        placeholder="按表达式、家族、ID、质量原因搜索..."
        value={filterInput ?? filter}
        maxLength={200}
        onChange={(event) => onFilterChange(event.target.value)}
        className="form-input flex-1"
      />
      <button type="button" onClick={onRetryLoad} disabled={apiLoading} aria-busy={apiLoading} className="btn btn-secondary btn-sm">
        {apiLoading ? "刷新中..." : "刷新"}
      </button>
      {onToggleStarFilter && (
        <Tooltip content={showStarredOnly ? "点击显示全部候选" : "点击仅显示收藏的候选"} placement="bottom">
          <button
            type="button"
            onClick={onToggleStarFilter}
            className={`btn btn-sm ${showStarredOnly ? "btn-primary" : "btn-secondary"}`}
            aria-pressed={showStarredOnly}
            aria-label={showStarredOnly ? "显示全部候选" : "仅显示收藏的候选"}
          >
            ⭐ {showStarredOnly ? "收藏中" : "仅收藏"}
          </button>
        </Tooltip>
      )}
      <div ref={exportRef} style={{ position: "relative" }}>
        <Tooltip content="导出当前候选列表为 CSV 或 JSON 格式" placement="bottom">
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            disabled={sortedCandidates.length === 0}
            onClick={() => setExportOpen((v) => !v)}
            aria-haspopup="true"
            aria-expanded={exportOpen}
          >
            导出 ▾
          </button>
        </Tooltip>
        {exportOpen && (
          <div
            className="dropdown-menu"
            role="menu"
            aria-label="导出选项"
            style={{
              position: "absolute",
              right: 0,
              top: "100%",
              marginTop: 4,
              zIndex: 50,
              minWidth: 120,
              background: "var(--color-divider)",
              border: "1px solid var(--color-scrollbar-thumb)",
              borderRadius: 6,
              padding: "4px 0",
              boxShadow: "0 4px 12px rgba(0,0,0,0.3)",
            }}
          >
            <button
              type="button"
              role="menuitem"
              className="btn btn-ghost btn-sm"
              style={{ display: "block", width: "100%", textAlign: "left", padding: "6px 12px" }}
              onClick={handleExportCSV}
              aria-label="导出为 CSV 格式"
            >
              CSV
            </button>
            <button
              type="button"
              role="menuitem"
              className="btn btn-ghost btn-sm"
              style={{ display: "block", width: "100%", textAlign: "left", padding: "6px 12px" }}
              onClick={handleExportJSON}
              aria-label="导出为 JSON 格式"
            >
              JSON
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
