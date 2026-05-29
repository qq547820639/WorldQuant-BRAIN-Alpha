/** Submission panel with pre-flight safety checks and confirmations. */

import { useState, useCallback, useEffect } from "react";
import { useApi } from "@/hooks/useApi";
import { useSSE } from "@/hooks/useSSE";
import ProgressFeedback from "@/components/ProgressFeedback";
import type { Candidate, SSEEvent, UnifiedProgress } from "@/types";

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
}

export default function SubmissionPanel({ notify }: Props) {
  const [alphaId, setAlphaId] = useState("");
  const [candidateJson, setCandidateJson] = useState("");
  const [confirmEnabled, setConfirmEnabled] = useState(false);
  const [checkResult, setCheckResult] = useState<Record<string, unknown> | null>(null);
  const [batchCheckResult, setBatchCheckResult] = useState<Record<string, unknown> | null>(null);
  const [submitCandidates, setSubmitCandidates] = useState<Candidate[]>([]);
  const [submitTaskId, setSubmitTaskId] = useState<string | null>(null);
  const [submitState, setSubmitState] = useState<"idle" | "loading" | "progress" | "success" | "error">("idle");
  const [submitProgress, setSubmitProgress] = useState<UnifiedProgress | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [batchCheckTaskId, setBatchCheckTaskId] = useState<string | null>(null);
  const [batchCheckState, setBatchCheckState] = useState<"idle" | "loading" | "progress" | "success" | "error">("idle");
  const [batchCheckProgress, setBatchCheckProgress] = useState<UnifiedProgress | null>(null);
  const [batchCheckError, setBatchCheckError] = useState<string | null>(null);
  const api = useApi();
  const checkApi = useApi();
  const batchCheckApi = useApi();
  const batchSubmitApi = useApi();

  useEffect(() => {
    if (candidateJson.trim()) {
      try {
        const parsed = JSON.parse(candidateJson);
        setSubmitCandidates(Array.isArray(parsed) ? parsed.filter((row): row is Candidate => Boolean(row && typeof row === "object")) : []);
      } catch {
        setSubmitCandidates([]);
      }
    } else {
      setSubmitCandidates([]);
    }
  }, [candidateJson]);

  const runCheck = useCallback(async () => {
    if (!alphaId) {
      notify("warning", "Enter an alpha ID to check");
      return;
    }
    const result = await checkApi.call("/api/check", {
      method: "POST",
      body: JSON.stringify({ alpha_id: alphaId }),
    });
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

  const runBatchCheck = useCallback(async () => {
    if (!submitCandidates.length) {
      notify("warning", "Paste candidate JSON to run batch check");
      return;
    }
    setBatchCheckState("loading");
    setBatchCheckError(null);
    setBatchCheckProgress({ phase: "checking", status_message: "Starting batch check.", percent_complete: 0 });
    const payload = {
      job_id: "manual_batch_check",
      mode: "quick",
      syncRange: "7d",
      candidates: submitCandidates,
      check_candidates: submitCandidates,
    };
    const result = await batchCheckApi.call("/api/check_batch", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const nextTaskId = String((result as unknown as { task_id?: string; job_id?: string } | null)?.task_id || (result as unknown as { job_id?: string } | null)?.job_id || "");
    if (result?.ok && nextTaskId) {
      setBatchCheckTaskId(nextTaskId);
      setBatchCheckState("progress");
      notify("info", `Batch check started: ${nextTaskId}`);
    } else {
      setBatchCheckState("error");
      setBatchCheckError(result?.error || "Batch check failed");
      notify("error", result?.error || "Batch check failed");
    }
  }, [batchCheckApi, notify, submitCandidates]);

  const runBatchSubmit = useCallback(async () => {
    if (!submitCandidates.length) {
      notify("warning", "Paste candidate JSON to run batch submit");
      return;
    }
    setSubmitState("loading");
    setSubmitError(null);
    setSubmitProgress({ phase: "submitting", status_message: "Starting batch submission.", percent_complete: 0 });
    const payload = {
      alpha_ids: submitCandidates.map((candidate) => candidate.alpha_id).filter(Boolean),
      submit_candidates: submitCandidates,
      confirm_observability_risk: true,
    };
    const result = await batchSubmitApi.call("/api/submit_batch", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const nextTaskId = String((result as unknown as { task_id?: string; job_id?: string } | null)?.task_id || (result as unknown as { job_id?: string } | null)?.job_id || "");
    if (result?.ok && nextTaskId) {
      setSubmitTaskId(nextTaskId);
      setSubmitState("progress");
      notify("info", `Batch submission started: ${nextTaskId}`);
    } else {
      setSubmitState("error");
      setSubmitError(result?.error || "Batch submission failed");
      notify("error", result?.error || "Batch submission failed");
    }
  }, [batchSubmitApi, notify, submitCandidates]);

  const handleBatchCheckEvent = useCallback((event: SSEEvent) => {
    const progress = (event.progress || event.data || {}) as UnifiedProgress;
    setBatchCheckProgress(progress);
    if (event.type === "error" || event.ok === false || event.status === "failed") {
      const message = event.error || event.status_message || "Batch check failed";
      setBatchCheckState("error");
      setBatchCheckError(message);
      notify("error", message);
      setBatchCheckTaskId(null);
      return;
    }
    if (event.type === "complete") {
      const result = event.result as { items?: unknown[] } | undefined;
      setBatchCheckState("success");
      setBatchCheckTaskId(null);
      setBatchCheckResult(result ? (result as Record<string, unknown>) : null);
      notify("success", "Batch check completed");
      return;
    }
    setBatchCheckState("progress");
  }, [notify]);

  const handleBatchSubmitEvent = useCallback((event: SSEEvent) => {
    const progress = (event.progress || event.data || {}) as UnifiedProgress;
    setSubmitProgress(progress);
    if (event.type === "error" || event.ok === false || event.status === "failed") {
      const message = event.error || event.status_message || "Batch submission failed";
      setSubmitState("error");
      setSubmitError(message);
      notify("error", message);
      setSubmitTaskId(null);
      return;
    }
    if (event.type === "complete") {
      setSubmitState("success");
      setSubmitTaskId(null);
      notify("success", "Batch submission completed");
      return;
    }
    setSubmitState("progress");
  }, [notify]);

  useSSE(batchCheckTaskId ? `/sse?job_id=${encodeURIComponent(batchCheckTaskId)}` : null, { onEvent: handleBatchCheckEvent });
  useSSE(submitTaskId ? `/sse?job_id=${encodeURIComponent(submitTaskId)}` : null, { onEvent: handleBatchSubmitEvent });

  return (
    <div className="max-w-3xl space-y-6 animate-fade-in">
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

      <div className="card space-y-4">
        <h3 className="text-sm font-semibold text-gray-200">Single Alpha</h3>
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

        <div className="flex flex-wrap gap-2">
          <button onClick={runCheck} disabled={!alphaId || checkApi.loading} className="btn-secondary text-sm">
            Pre-Submit Check
          </button>
          <button
            onClick={handleSubmit}
            disabled={!alphaId || api.loading}
            className="btn-danger text-sm"
          >
            Submit Alpha
          </button>
        </div>

        <ProgressFeedback
          state={checkApi.error ? "error" : checkApi.loading ? "loading" : checkResult ? "success" : "idle"}
          title="Pre-submit check"
          progress={{
            phase: checkApi.loading ? "checking" : checkResult ? "completed" : "idle",
            status_message: checkApi.loading ? `Checking ${alphaId}.` : checkResult ? "Pre-submit check completed." : "Ready to check.",
          }}
          error={checkApi.error}
          onRetry={runCheck}
          compact={!checkApi.loading && !checkApi.error}
        />

        <ProgressFeedback
          state={api.error ? "error" : api.loading ? "loading" : "idle"}
          title="Submission"
          progress={{
            phase: api.loading ? "submitting" : "idle",
            status_message: api.loading ? `Submitting ${alphaId}.` : "Ready to submit.",
          }}
          error={api.error}
          onRetry={handleSubmit}
          compact={!api.loading && !api.error}
        />

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

      <div className="card space-y-4">
        <h3 className="text-sm font-semibold text-gray-200">Batch Workflows</h3>
        <div>
          <label className="block text-xs text-muted mb-1">Candidate JSON array</label>
          <textarea
            value={candidateJson}
            onChange={(e) => setCandidateJson(e.target.value)}
            placeholder='[{"alpha_id":"...","expression":"...","official_alpha_id":"..."}]'
            className="w-full min-h-40 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-brand-500 font-mono"
          />
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={runBatchCheck} disabled={!submitCandidates.length || batchCheckApi.loading} className="btn-secondary text-sm">
            Batch Check
          </button>
          <button onClick={runBatchSubmit} disabled={!submitCandidates.length || batchSubmitApi.loading} className="btn-danger text-sm">
            Batch Submit
          </button>
        </div>

        <ProgressFeedback
          state={batchCheckError ? "error" : batchCheckState}
          title="Batch check"
          progress={batchCheckProgress}
          error={batchCheckError}
          onRetry={runBatchCheck}
          compact={batchCheckState === "idle" || batchCheckState === "success"}
        />

        <ProgressFeedback
          state={submitError ? "error" : submitState}
          title="Batch submission"
          progress={submitProgress}
          error={submitError}
          onRetry={runBatchSubmit}
          compact={submitState === "idle" || submitState === "success"}
        />

        {batchCheckResult && (
          <div className="card bg-gray-950 border-gray-800 p-4">
            <h4 className="text-xs font-semibold text-gray-300 mb-2">Batch Check Result</h4>
            <pre className="text-xs text-gray-300 font-mono overflow-x-auto max-h-56 overflow-y-auto">
              {JSON.stringify(batchCheckResult, null, 2)}
            </pre>
          </div>
        )}
      </div>

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
