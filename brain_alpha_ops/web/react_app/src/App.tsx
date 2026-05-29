/** Root application component with tab-based navigation. */

import { useState, useCallback, useMemo } from "react";
import type { Candidate, TabId } from "@/types";
import { useToast } from "@/hooks/useToast";
import ToastContainer from "@/components/ToastContainer";
import Dashboard from "@/components/Dashboard";
import CandidateTable from "@/components/CandidateTable";
import ScoringPanel from "@/components/ScoringPanel";
import SubmissionPanel from "@/components/SubmissionPanel";
import ConfigPanel from "@/components/ConfigPanel";

const TABS: { id: TabId; label: string; icon: string }[] = [
  { id: "dashboard", label: "Dashboard", icon: "📊" },
  { id: "candidates", label: "Candidates", icon: "🧬" },
  { id: "scoring", label: "Scoring", icon: "📈" },
  { id: "submission", label: "Submit", icon: "🚀" },
  { id: "config", label: "Config", icon: "⚙️" },
];

export default function App() {
  const [activeTab, setActiveTab] = useState<TabId>("dashboard");
  const [selectedCandidate, setSelectedCandidate] = useState<Candidate | null>(null);
  const { toasts, addToast, dismissToast } = useToast();

  const notify = useCallback(
    (type: "success" | "error" | "warning" | "info", msg: string) => {
      addToast(type, msg);
    },
    [addToast],
  );

  const tabContent = useMemo(() => {
    switch (activeTab) {
      case "dashboard":
        return <Dashboard notify={notify} />;
      case "candidates":
        return (
          <CandidateTable
            notify={notify}
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
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="bg-gray-900 border-b border-gray-800 px-6 py-3 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <span className="text-2xl">🧠</span>
          <div>
            <h1 className="text-lg font-bold text-white tracking-tight">BRAIN Alpha Ops</h1>
            <p className="text-xs text-muted">Research Console v0.3</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-success animate-pulse" />
          <span className="text-xs text-muted">api.worldquantbrain.com</span>
        </div>
      </header>

      {/* Tabs */}
      <nav className="bg-gray-900/80 backdrop-blur border-b border-gray-800 px-6 flex gap-1 shrink-0">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2.5 text-sm font-medium rounded-t-lg transition-colors border-b-2 -mb-px ${
              activeTab === tab.id
                ? "text-brand-500 border-brand-500 bg-gray-800/50"
                : "text-gray-400 border-transparent hover:text-gray-200 hover:bg-gray-800/30"
            }`}
          >
            <span className="mr-1.5">{tab.icon}</span>
            {tab.label}
          </button>
        ))}
      </nav>

      {/* Content */}
      <main className="flex-1 p-6 overflow-auto">
        {tabContent}
      </main>

      {/* Toast notifications */}
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}
