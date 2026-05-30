/** Root application component with tab-based navigation. */

import { useState, useCallback, useMemo } from "react";
import type { KeyboardEvent } from "react";
import type { Candidate, TabId } from "@/types";
import { useToast } from "@/hooks/useToast";
import ToastContainer from "@/components/ToastContainer";
import Dashboard from "@/components/Dashboard";
import CandidateTable from "@/components/CandidateTable";
import ScoringPanel from "@/components/ScoringPanel";
import SubmissionPanel from "@/components/SubmissionPanel";
import ConfigPanel from "@/components/ConfigPanel";
import SnapshotPanel from "@/components/SnapshotPanel";
import type { SnapshotView } from "@/components/SnapshotPanel";

const TABS: { id: TabId; label: string; icon: string }[] = [
  { id: "dashboard", label: "Dashboard", icon: "📊" },
  { id: "candidates", label: "Candidates", icon: "🧬" },
  { id: "pending_backtest", label: "Waiting", icon: "02" },
  { id: "running_backtest", label: "Backtesting", icon: "03" },
  { id: "backtest_rework", label: "Rework", icon: "04" },
  { id: "passed", label: "Passed", icon: "05" },
  { id: "submittable", label: "Ready", icon: "06" },
  { id: "submitted", label: "Submitted", icon: "07" },
  { id: "failed", label: "Blocked", icon: "08" },
  { id: "cloud", label: "Cloud", icon: "CL" },
  { id: "lifecycle", label: "Lifecycle", icon: "LC" },
  { id: "research_memory", label: "Memory", icon: "RM" },
  { id: "research_knowledge", label: "Knowledge", icon: "KB" },
  { id: "research_observability", label: "Observability", icon: "OB" },
  { id: "prompt_runs", label: "Prompts", icon: "PR" },
  { id: "sqlite_indexes", label: "SQLite", icon: "DB" },
  { id: "robustness", label: "Robustness", icon: "RV" },
  { id: "scoring", label: "Scoring", icon: "📈" },
  { id: "submission", label: "Submit", icon: "🚀" },
  { id: "config", label: "Config", icon: "⚙️" },
];

const SNAPSHOT_TABS = new Set<TabId>([
  "cloud",
  "lifecycle",
  "research_memory",
  "research_knowledge",
  "research_observability",
  "prompt_runs",
  "sqlite_indexes",
  "robustness",
]);

const tabButtonId = (id: TabId) => `app-tab-${id}`;
const tabPanelId = (id: TabId) => `app-tabpanel-${id}`;

export default function App() {
  const [activeTab, setActiveTab] = useState<TabId>("dashboard");
  const [selectedCandidate, setSelectedCandidate] = useState<Candidate | null>(null);
  const { toasts, addToast, dismissToast } = useToast();

  const notify = useCallback(
    (type: "success" | "error" | "warning" | "info", msg: string, action?: { label: string; onClick: () => void }) => {
      addToast(type, msg, 5000, action);
    },
    [addToast],
  );

  const activateTabByIndex = useCallback((index: number) => {
    const tab = TABS[(index + TABS.length) % TABS.length];
    setActiveTab(tab.id);
    requestAnimationFrame(() => document.getElementById(tabButtonId(tab.id))?.focus());
  }, []);

  const handleTabKeyDown = useCallback((event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      event.preventDefault();
      activateTabByIndex(index + 1);
    } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      event.preventDefault();
      activateTabByIndex(index - 1);
    } else if (event.key === "Home") {
      event.preventDefault();
      activateTabByIndex(0);
    } else if (event.key === "End") {
      event.preventDefault();
      activateTabByIndex(TABS.length - 1);
    }
  }, [activateTabByIndex]);

  const tabContent = useMemo(() => {
    if (SNAPSHOT_TABS.has(activeTab)) {
      return <SnapshotPanel key={activeTab} notify={notify} viewMode={activeTab as SnapshotView} />;
    }
    switch (activeTab) {
      case "dashboard":
        return <Dashboard notify={notify} />;
      case "candidates":
        return (
          <CandidateTable
            key="candidates"
            notify={notify}
            onScore={(candidate) => {
              setSelectedCandidate(candidate);
              setActiveTab("scoring");
            }}
          />
        );
      case "pending_backtest":
      case "running_backtest":
      case "backtest_rework":
      case "passed":
      case "submittable":
      case "submitted":
      case "failed":
        return (
          <CandidateTable
            key={activeTab}
            notify={notify}
            viewMode={activeTab}
            onScore={(candidate) => {
              setSelectedCandidate(candidate);
              setActiveTab("scoring");
            }}
          />
        );
      case "scoring":
        return <ScoringPanel notify={notify} candidate={selectedCandidate} />;
      case "submission":
        return <SubmissionPanel notify={notify} />;
      case "config":
        return <ConfigPanel notify={notify} />;
      default:
        return null;
    }
  }, [activeTab, notify, selectedCandidate]);

  return (
    <div className="min-h-screen min-w-0 flex flex-col">
      {/* Header */}
      <header className="bg-gray-900 border-b border-gray-800 px-4 py-3 sm:px-6 flex flex-wrap items-center justify-between gap-3 shrink-0">
        <div className="flex min-w-0 items-center gap-3">
          <span className="text-2xl" aria-hidden="true">🧠</span>
          <div className="min-w-0">
            <h1 className="text-lg font-bold text-white tracking-tight">BRAIN Alpha Ops</h1>
            <p className="text-xs text-muted">Research Console v0.3</p>
          </div>
        </div>
        <div className="flex min-w-0 items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-success animate-pulse" aria-hidden="true" />
          <span className="truncate text-xs text-muted">api.worldquantbrain.com</span>
        </div>
      </header>

      {/* Tabs */}
      <nav
        className="bg-gray-900/80 backdrop-blur border-b border-gray-800 px-4 sm:px-6 flex gap-1 shrink-0 overflow-x-auto"
        role="tablist"
        aria-label="Primary sections"
      >
        {TABS.map((tab, index) => (
          <button
            key={tab.id}
            id={tabButtonId(tab.id)}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            aria-controls={tabPanelId(tab.id)}
            tabIndex={activeTab === tab.id ? 0 : -1}
            onClick={() => setActiveTab(tab.id)}
            onKeyDown={(event) => handleTabKeyDown(event, index)}
            className={`shrink-0 px-3 py-2.5 sm:px-4 text-sm font-medium rounded-t-lg transition-colors border-b-2 -mb-px ${
              activeTab === tab.id
                ? "text-brand-500 border-brand-500 bg-gray-800/50"
                : "text-gray-400 border-transparent hover:text-gray-200 hover:bg-gray-800/30"
              }`}
          >
            <span className="mr-1.5" aria-hidden="true">{tab.icon}</span>
            {tab.label}
          </button>
        ))}
      </nav>

      {/* Content */}
      <main
        className="flex-1 min-w-0 p-4 sm:p-6 overflow-auto"
        id={tabPanelId(activeTab)}
        role="tabpanel"
        aria-labelledby={tabButtonId(activeTab)}
        tabIndex={0}
      >
        {tabContent}
      </main>

      {/* Toast notifications */}
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}
