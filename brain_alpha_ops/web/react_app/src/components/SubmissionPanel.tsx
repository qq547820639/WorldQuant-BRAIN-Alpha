/** Submission panel with pre-flight safety checks and confirmations. */

import { useState, useCallback, useEffect, useRef } from "react";
import { useApi } from "@/hooks/useApi";
import { useSSE } from "@/hooks/useSSE";
import ProgressFeedback from "@/components/ProgressFeedback";
import type { Candidate, SSEEvent, UnifiedProgress } from "@/types";

interface Props {
  notify: (
    type: "success" | "error" | "warning" | "info",
    msg: string,
    action?: { label: string; onClick: () => void },
  ) => void;
}

const MAX_ALPHA_ID_LENGTH = 128;
const MAX_BATCH_ALPHA_IDS = 100;
const ALPHA_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_.:-]*$/;

export default function SubmissionPanel({ notify }: Props) {
  const [alphaId, setAlphaId] = useState("");
  const [candidateJson, setCandidateJson] = useState("");
  const [candidateJsonError, setCandidateJsonError] = useState("");
  const [confirmEnabled, setConfirmEnabled] = useState(false);
  const [lastSubmission, setLastSubmission] = useState<{ alphaId: string; submittedAt: string } | null>(null);
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
  const submissionReceiptRef = useRef<HTMLDivElement | null>(null);
  const batchSubmissionStatusRef = useRef<HTMLDivElement | null>(null);
  const normalizedAlphaId = alphaId.trim();
  const alphaIdError = alphaId ? validateAlphaId(alphaId) : "";
  const batchSubmitError = submitCandidates.length ? validateBatchSubmitCandidates(submitCandidates) : "";

  const focusSubmissionReceipt = useCallback(() => {
    requestAnimationFrame(() => {
      submissionReceiptRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      submissionReceiptRef.current?.focus();
    });
  }, []);

  const focusBatchSubmissionStatus = useCallback(() => {
    requestAnimationFrame(() => {
      batchSubmissionStatusRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      batchSubmissionStatusRef.current?.focus();
    });
  }, []);

  useEffect(() => {
    if (candidateJson.trim()) {
      try {
        const parsed = JSON.parse(candidateJson);
        if (!Array.isArray(parsed)) {
          setSubmitCandidates([]);
          setCandidateJsonError("Candidate JSON must be an array.");
          return;
        }
        const rows = parsed.filter((row): row is Candidate => Boolean(row && typeof row === "object"));
        setSubmitCandidates(rows);
        if (rows.length !== parsed.length) {
          setCandidateJsonError("Every candidate row must be an object.");
          return;
        }
        if (rows.length > MAX_BATCH_ALPHA_IDS) {
          setCandidateJsonError(`Candidate JSON must contain at most ${MAX_BATCH_ALPHA_IDS} rows.`);
          return;
        }
        setCandidateJsonError(validateCandidateJsonRows(rows));
      } catch {
        setSubmitCandidates([]);
        setCandidateJsonError("Candidate JSON is not valid JSON.");
      }
    } else {
      setSubmitCandidates([]);
      setCandidateJsonError("");
    }
  }, [candidateJson]);

  const runCheck = useCallback(async () => {
    if (!normalizedAlphaId) {
      notify("warning", "Enter an alpha ID to check");
      return;
    }
    if (alphaIdError) {
      notify("warning", alphaIdError);
      return;
    }
    const result = await checkApi.call("/api/check", {
      method: "POST",
      body: JSON.stringify({ alpha_id: normalizedAlphaId }),
    });
    if (result?.ok) {
      const data = result as unknown as Record<string, unknown>;
      setCheckResult(data);
      notify("success", `Check completed for ${normalizedAlphaId}`);
    } else {
      notify("error", result?.error || "Check failed");
    }
  }, [alphaIdError, checkApi, normalizedAlphaId, notify]);

  const handleSubmit = useCallback(async () => {
    if (!confirmEnabled) {
      notify("warning", "Confirm submission before proceeding");
      return;
    }
    if (!normalizedAlphaId) {
      notify("warning", "Enter an alpha ID to submit");
      return;
    }
    if (alphaIdError) {
      notify("warning", alphaIdError);
      return;
    }
    const result = await api.call("/api/submit", {
      method: "POST",
      body: JSON.stringify({ alpha_id: normalizedAlphaId, confirm_submit: true }),
    });
    if (result?.ok) {
      const submittedAlphaId = normalizedAlphaId;
      setLastSubmission({ alphaId: submittedAlphaId, submittedAt: new Date().toISOString() });
      notify("success", `Alpha ${submittedAlphaId} submitted successfully`, {
        label: "View receipt",
        onClick: focusSubmissionReceipt,
      });
      setCheckResult(null);
      setAlphaId("");
      setConfirmEnabled(false);
    } else {
      notify("error", result?.error || "Submission failed");
    }
  }, [api, alphaIdError, confirmEnabled, focusSubmissionReceipt, normalizedAlphaId, notify]);

  const runBatchCheck = useCallback(async () => {
    if (!submitCandidates.length) {
      notify("warning", "Paste candidate JSON to run batch check");
      return;
    }
    const validationError = candidateJsonError || validateCandidateJsonRows(submitCandidates);
    if (validationError) {
      notify("warning", validationError);
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
  }, [batchCheckApi, candidateJsonError, notify, submitCandidates]);

  const runBatchSubmit = useCallback(async () => {
    if (!submitCandidates.length) {
      notify("warning", "Paste candidate JSON to run batch submit");
      return;
    }
    const validationError = candidateJsonError || validateBatchSubmitCandidates(submitCandidates);
    if (validationError) {
      notify("warning", validationError);
      return;
    }
    setSubmitState("loading");
    setSubmitError(null);
    setSubmitProgress({ phase: "submitting", status_message: "Starting batch submission.", percent_complete: 0 });
    const payload = {
      alpha_ids: submitCandidates.map(candidateAlphaId).filter(Boolean),
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
  }, [batchSubmitApi, candidateJsonError, notify, submitCandidates]);

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
      notify("success", "Batch submission completed", {
        label: "View status",
        onClick: focusBatchSubmissionStatus,
      });
      return;
    }
    setSubmitState("progress");
  }, [focusBatchSubmissionStatus, notify]);

  useSSE(batchCheckTaskId ? `/sse?job_id=${encodeURIComponent(batchCheckTaskId)}` : null, { onEvent: handleBatchCheckEvent });
  useSSE(submitTaskId ? `/sse?job_id=${encodeURIComponent(submitTaskId)}` : null, { onEvent: handleBatchSubmitEvent });

  return (
    <div className="w-full max-w-3xl min-w-0 space-y-6 animate-fade-in">
      <div className="bg-warning/10 border border-warning/30 rounded-xl p-4">
        <div className="flex items-start gap-3">
          <span className="text-warning text-lg" aria-hidden="true">⚠</span>
          <div className="min-w-0 text-sm">
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
            onChange={(e) => setAlphaId(e.target.value.slice(0, MAX_ALPHA_ID_LENGTH))}
            placeholder="e.g. alpha_abc123..."
            maxLength={MAX_ALPHA_ID_LENGTH}
            aria-invalid={Boolean(alphaIdError)}
            aria-describedby="alpha-id-validation"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-brand-500 font-mono"
          />
          <p id="alpha-id-validation" className={`mt-1 text-xs ${alphaIdError ? "text-danger" : "text-muted"}`}>
            {alphaIdError || `Use letters, numbers, _, -, ., or :; max ${MAX_ALPHA_ID_LENGTH} characters.`}
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <button onClick={runCheck} disabled={!normalizedAlphaId || Boolean(alphaIdError) || checkApi.loading} className="btn-secondary text-sm">
            Pre-Submit Check
          </button>
          <button
            onClick={handleSubmit}
            disabled={!normalizedAlphaId || Boolean(alphaIdError) || api.loading}
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
            status_message: checkApi.loading ? `Checking ${normalizedAlphaId}.` : checkResult ? "Pre-submit check completed." : "Ready to check.",
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
            status_message: api.loading ? `Submitting ${normalizedAlphaId}.` : "Ready to submit.",
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
            aria-describedby="confirm-submit-help"
            className="rounded border-gray-600 bg-gray-800 text-brand-500 focus:ring-brand-500"
          />
          <span id="confirm-submit-help">
            I confirm this alpha has passed all pre-submit checks and I want to submit it to BRAIN.
          </span>
        </label>

        {lastSubmission && (
          <div
            ref={submissionReceiptRef}
            tabIndex={-1}
            className="rounded-lg border border-success/30 bg-success/10 p-3 outline-none focus:ring-2 focus:ring-success/50"
            role="status"
            aria-live="polite"
          >
            <p className="text-xs font-semibold text-success">Latest submission receipt</p>
            <p className="text-xs text-gray-300">
              Alpha <span className="font-mono">{lastSubmission.alphaId}</span> submitted at{" "}
              <span className="font-mono">{lastSubmission.submittedAt}</span>.
            </p>
          </div>
        )}
      </div>

      <div className="card space-y-4">
        <h3 className="text-sm font-semibold text-gray-200">Batch Workflows</h3>
        <div>
          <label className="block text-xs text-muted mb-1">Candidate JSON array</label>
          <textarea
            value={candidateJson}
            onChange={(e) => setCandidateJson(e.target.value)}
            placeholder='[{"alpha_id":"...","expression":"...","official_alpha_id":"...","simulation_id":"..."}]'
            aria-invalid={Boolean(candidateJsonError)}
            aria-describedby="candidate-json-validation"
            className="w-full min-h-40 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-brand-500 font-mono"
          />
          <p
            id="candidate-json-validation"
            className={`mt-1 text-xs ${candidateJsonError ? "text-danger" : "text-muted"}`}
            role={candidateJsonError ? "alert" : undefined}
          >
            {candidateJsonError || "Paste a JSON array of candidate objects before running batch workflows."}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={runBatchCheck} disabled={!submitCandidates.length || Boolean(candidateJsonError) || batchCheckApi.loading} className="btn-secondary text-sm">
            Batch Check
          </button>
          <button
            onClick={runBatchSubmit}
            disabled={!submitCandidates.length || Boolean(candidateJsonError) || Boolean(batchSubmitError) || batchSubmitApi.loading}
            className="btn-danger text-sm"
          >
            Batch Submit
          </button>
        </div>
        {batchSubmitError && !candidateJsonError && (
          <p id="batch-submit-validation" className="text-xs text-warning" role="alert">
            {batchSubmitError}
          </p>
        )}

        <ProgressFeedback
          state={batchCheckError ? "error" : batchCheckState}
          title="Batch check"
          progress={batchCheckProgress}
          error={batchCheckError}
          onRetry={runBatchCheck}
          compact={batchCheckState === "idle" || batchCheckState === "success"}
        />

        <div ref={batchSubmissionStatusRef} tabIndex={-1} className="min-w-0 outline-none focus:ring-2 focus:ring-brand-500/50">
          <ProgressFeedback
            state={submitError ? "error" : submitState}
            title="Batch submission"
            progress={submitProgress}
            error={submitError}
            onRetry={runBatchSubmit}
            compact={submitState === "idle" || submitState === "success"}
          />
        </div>

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

function validateAlphaId(value: string) {
  const text = value.trim();
  if (!text) return "Alpha ID is required.";
  if (text.length > MAX_ALPHA_ID_LENGTH) return `Alpha ID must be ${MAX_ALPHA_ID_LENGTH} characters or fewer.`;
  if (!ALPHA_ID_PATTERN.test(text)) return "Alpha ID may only contain letters, numbers, underscore, dash, dot, or colon.";
  return "";
}

function validateCandidateJsonRows(candidates: Candidate[]) {
  for (const [index, candidate] of candidates.entries()) {
    for (const field of ["alpha_id", "official_alpha_id", "simulation_id"] as const) {
      const value = candidate[field];
      if (value == null || value === "") continue;
      if (typeof value !== "string") return `Candidate row ${index + 1} ${field} must be a string.`;
      const error = validateAlphaId(value);
      if (error) return `Candidate row ${index + 1} ${field}: ${error}`;
    }
  }
  return "";
}

function validateBatchSubmitCandidates(candidates: Candidate[]) {
  if (candidates.length > MAX_BATCH_ALPHA_IDS) return `Batch submit supports at most ${MAX_BATCH_ALPHA_IDS} candidates.`;
  const alphaIds = candidates.map(candidateAlphaId).filter(Boolean);
  if (!alphaIds.length) return "At least one candidate row must include alpha_id or official_alpha_id before batch submit.";
  for (const alphaId of alphaIds) {
    const error = validateAlphaId(alphaId);
    if (error) return error;
  }
  return "";
}

function candidateAlphaId(candidate: Candidate) {
  return String(candidate.alpha_id || candidate.official_alpha_id || "").trim();
}
