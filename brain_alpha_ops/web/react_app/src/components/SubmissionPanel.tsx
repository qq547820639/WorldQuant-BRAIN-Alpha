/** Submission panel with pre-flight safety checks and confirmations. */

import { useState, useCallback } from "react";
import { useApi } from "@/hooks/useApi";
import type { Candidate } from "@/types";

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
}

export default function SubmissionPanel({ notify }: Props) {
  const [alphaId, setAlphaId] = useState("");
  const [confirmEnabled, setConfirmEnabled] = useState(false);
  const [checkResult, setCheckResult] = useState<Record<string, unknown> | null>(null);
  const api = useApi();
  const checkApi = useApi();

  const runCheck = useCallback(async () => {
    if (!alphaId) { notify("warning", "Enter an alpha ID to check"); return; }
    const result = await checkApi.call(`/api/check?alpha_id=${encodeURIComponent(alphaId)}`, { method: "POST" });
    if (result?.ok) {
      const data = result as unknown as Record<string, unknown>;
      setCheckResult(data);
      notify("success", `Check completed for ${alphaId}`);
    } else {
      notify("error", result?.error || "Check failed");
    }
  }, [alphaId, checkApi, notify]);

  const handleSubmit = useCallback(async () => {
    if (!confirmEnabled) {
      notify("warning", "Confirm submission before proceeding");
      return;
    }
    const result = await api.call("/api/submit", {
      method: "POST",
      body: JSON.stringify({ alpha_id: alphaId, confirm_submit: true }),
    });
    if (result?.ok) {
      notify("success", `Alpha ${alphaId} submitted successfully`);
      setCheckResult(null);
      setAlphaId("");
      setConfirmEnabled(false);
    } else {
      notify("error", result?.error || "Submission failed");
    }
  }, [api, alphaId, confirmEnabled, notify]);

  return (
    <div className="max-w-2xl space-y-6 animate-fade-in">
      {/* Safety Reminder */}
      <div className="bg-warning/10 border border-warning/30 rounded-xl p-4">
        <div className="flex items-start gap-3">
          <span className="text-warning text-lg">⚠</span>
          <div className="text-sm">
            <p className="font-semibold text-warning mb-1">Account Safety Reminder</p>
            <p className="text-gray-300">
              All submissions are recorded in the SubmissionLedger for auditability.
              BRAIN API quota and rate limits apply. Verify check results before submitting.
            </p>
          </div>
        </div>
      </div>

      {/* Alpha ID Input */}
      <div className="card space-y-4">
        <h3 className="text-sm font-semibold text-gray-200">Submit Alpha</h3>
        <div>
          <label className="block text-xs text-muted mb-1">Alpha ID (from BRAIN validation)</label>
          <input
            type="text"
            value={alphaId}
            onChange={(e) => setAlphaId(e.target.value)}
            placeholder="e.g. alpha_abc123..."
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-brand-500 font-mono"
          />
        </div>

        <div className="flex gap-2">
          <button onClick={runCheck} disabled={!alphaId || checkApi.loading} className="btn-secondary text-sm">
            {checkApi.loading ? "Checking..." : "✓ Pre-Submit Check"}
          </button>
          <button
            onClick={handleSubmit}
            disabled={!alphaId || api.loading}
            className="btn-danger text-sm"
          >
            {api.loading ? "Submitting..." : "🚀 Submit Alpha"}
          </button>
        </div>

        {/* Confirmation toggle */}
        <label className="flex items-center gap-2 text-xs text-gray-300 cursor-pointer">
          <input
            type="checkbox"
            checked={confirmEnabled}
            onChange={(e) => setConfirmEnabled(e.target.checked)}
            className="rounded border-gray-600 bg-gray-800 text-brand-500 focus:ring-brand-500"
          />
          I confirm this alpha has passed all pre-submit checks and I want to submit it to BRAIN.
        </label>
      </div>

      {/* Check Result */}
      {checkResult && (
        <div className="card space-y-2">
          <h3 className="text-sm font-semibold text-gray-200">Pre-Submit Check Result</h3>
          <pre className="bg-gray-950 rounded-lg p-3 text-xs text-gray-300 font-mono overflow-x-auto max-h-60 overflow-y-auto">
            {JSON.stringify(checkResult, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
