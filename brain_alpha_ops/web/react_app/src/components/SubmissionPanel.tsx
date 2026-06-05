/** Submission panel with pre-flight safety checks and confirmations. */

import { useState, useCallback, useEffect, useMemo, useRef } from "react";
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
  const [batchConfirmEnabled, setBatchConfirmEnabled] = useState(false);
  const [checkedAlphaId, setCheckedAlphaId] = useState("");
  const [batchCheckedSignature, setBatchCheckedSignature] = useState("");
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
  const batchCandidateSignature = useMemo(() => candidateBatchSignature(submitCandidates), [submitCandidates]);
  const hasFreshSingleCheck = Boolean(checkResult && checkedAlphaId === normalizedAlphaId);
  const hasFreshBatchCheck = Boolean(batchCheckResult && batchCheckedSignature === batchCandidateSignature);

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
    setBatchConfirmEnabled(false);
    setBatchCheckResult(null);
    setBatchCheckedSignature("");
    if (candidateJson.trim()) {
      try {
        const parsed = JSON.parse(candidateJson);
        if (!Array.isArray(parsed)) {
          setSubmitCandidates([]);
          setCandidateJsonError("候选JSON必须为数组。");
          return;
        }
        const rows = parsed.filter((row): row is Candidate => Boolean(row && typeof row === "object"));
        setSubmitCandidates(rows);
        if (rows.length !== parsed.length) {
          setCandidateJsonError("每个候选行必须为对象。");
          return;
        }
        if (rows.length > MAX_BATCH_ALPHA_IDS) {
          setCandidateJsonError(`候选JSON最多包含 ${MAX_BATCH_ALPHA_IDS} 行。`);
          return;
        }
        setCandidateJsonError(validateCandidateJsonRows(rows));
      } catch {
        setSubmitCandidates([]);
        setCandidateJsonError("候选JSON不是有效的JSON。");
      }
    } else {
      setSubmitCandidates([]);
      setCandidateJsonError("");
    }
  }, [candidateJson]);

  useEffect(() => {
    setConfirmEnabled(false);
    if (checkedAlphaId !== normalizedAlphaId) {
      setCheckResult(null);
    }
  }, [checkedAlphaId, normalizedAlphaId]);

  const runCheck = useCallback(async () => {
    if (!normalizedAlphaId) {
      notify("warning", "请输入要检查的Alpha ID");
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
      setCheckedAlphaId(normalizedAlphaId);
      notify("success", `${normalizedAlphaId} 检查完成`);
    } else {
      notify("error", result?.error || "检查失败");
    }
  }, [alphaIdError, checkApi, normalizedAlphaId, notify]);

  const handleSubmit = useCallback(async () => {
    if (!confirmEnabled) {
      notify("warning", "提交前请先确认");
      return;
    }
    if (!normalizedAlphaId) {
      notify("warning", "请输入要提交的Alpha ID");
      return;
    }
    if (alphaIdError) {
      notify("warning", alphaIdError);
      return;
    }
    if (!hasFreshSingleCheck) {
      notify("warning", "提交前请先完成同一Alpha ID的检查");
      return;
    }
    const result = await api.call("/api/submit", {
      method: "POST",
      body: JSON.stringify({ alpha_id: normalizedAlphaId, confirm_submit: true }),
    });
    if (result?.ok) {
      const submittedAlphaId = normalizedAlphaId;
      setLastSubmission({ alphaId: submittedAlphaId, submittedAt: new Date().toISOString() });
      notify("success", `Alpha ${submittedAlphaId} 提交成功`, {
        label: "查看回执",
        onClick: focusSubmissionReceipt,
      });
      setCheckResult(null);
      setAlphaId("");
      setConfirmEnabled(false);
    } else {
      notify("error", result?.error || "提交失败");
    }
  }, [api, alphaIdError, confirmEnabled, focusSubmissionReceipt, hasFreshSingleCheck, normalizedAlphaId, notify]);

  const runBatchCheck = useCallback(async () => {
    if (!submitCandidates.length) {
      notify("warning", "请粘贴候选JSON以运行批量检查");
      return;
    }
    const validationError = candidateJsonError || validateCandidateJsonRows(submitCandidates);
    if (validationError) {
      notify("warning", validationError);
      return;
    }
    setBatchCheckState("loading");
    setBatchCheckError(null);
    setBatchCheckProgress({ phase: "checking", status_message: "正在启动批量检查。", percent_complete: 0 });
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
      setBatchCheckedSignature("");
      notify("info", `批量检查已启动: ${nextTaskId}`);
    } else {
      setBatchCheckState("error");
      setBatchCheckError(result?.error || "批量检查失败");
      notify("error", result?.error || "批量检查失败");
    }
  }, [batchCheckApi, candidateJsonError, notify, submitCandidates]);

  const runBatchSubmit = useCallback(async () => {
    if (!submitCandidates.length) {
      notify("warning", "请粘贴候选JSON以运行批量提交");
      return;
    }
    const validationError = candidateJsonError || validateBatchSubmitCandidates(submitCandidates);
    if (validationError) {
      notify("warning", validationError);
      return;
    }
    if (!batchConfirmEnabled) {
      notify("warning", "批量提交前请先确认候选已通过提交前检查");
      return;
    }
    if (!hasFreshBatchCheck) {
      notify("warning", "批量提交前请先完成当前候选集的批量检查");
      return;
    }
    setSubmitState("loading");
    setSubmitError(null);
    setSubmitProgress({ phase: "submitting", status_message: "正在启动批量提交。", percent_complete: 0 });
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
      notify("info", `批量提交已启动: ${nextTaskId}`);
    } else {
      setSubmitState("error");
      setSubmitError(result?.error || "批量提交失败");
      notify("error", result?.error || "批量提交失败");
    }
  }, [batchConfirmEnabled, batchSubmitApi, candidateJsonError, hasFreshBatchCheck, notify, submitCandidates]);

  const handleBatchCheckEvent = useCallback((event: SSEEvent) => {
    const progress = (event.progress || event.data || {}) as UnifiedProgress;
    setBatchCheckProgress(progress);
    if (event.type === "error" || event.ok === false || event.status === "failed") {
      const message = event.error || event.status_message || "批量检查失败";
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
      setBatchCheckResult(result ? (result as Record<string, unknown>) : { ok: true });
      setBatchCheckedSignature(batchCandidateSignature);
      notify("success", "批量检查完成");
      return;
    }
    setBatchCheckState("progress");
  }, [batchCandidateSignature, notify]);

  const handleBatchSubmitEvent = useCallback((event: SSEEvent) => {
    const progress = (event.progress || event.data || {}) as UnifiedProgress;
    setSubmitProgress(progress);
    if (event.type === "error" || event.ok === false || event.status === "failed") {
      const message = event.error || event.status_message || "批量提交失败";
      setSubmitState("error");
      setSubmitError(message);
      notify("error", message);
      setSubmitTaskId(null);
      return;
    }
    if (event.type === "complete") {
      setSubmitState("success");
      setSubmitTaskId(null);
      notify("success", "批量提交完成", {
        label: "查看状态",
        onClick: focusBatchSubmissionStatus,
      });
      return;
    }
    setSubmitState("progress");
  }, [focusBatchSubmissionStatus, notify]);

  const handleBatchCheckStreamExhausted = useCallback(() => {
    const message = "批量检查实时流已断开，请稍后重试或刷新状态。";
    setBatchCheckState("error");
    setBatchCheckError(message);
    notify("warning", message);
  }, [notify]);

  const handleBatchSubmitStreamExhausted = useCallback(() => {
    const message = "批量提交实时流已断开，请刷新状态确认提交结果。";
    setSubmitState("error");
    setSubmitError(message);
    notify("warning", message);
  }, [notify]);

  useSSE(batchCheckTaskId ? `/sse?job_id=${encodeURIComponent(batchCheckTaskId)}` : null, {
    onEvent: handleBatchCheckEvent,
    onExhausted: handleBatchCheckStreamExhausted,
  });
  useSSE(submitTaskId ? `/sse?job_id=${encodeURIComponent(submitTaskId)}` : null, {
    onEvent: handleBatchSubmitEvent,
    onExhausted: handleBatchSubmitStreamExhausted,
  });

  return (
    <div className="w-full max-w-3xl min-w-0 space-y-6 animate-fade-in">
      <div className="bg-warning/10 border border-warning/30 rounded-xl p-4">
        <div className="flex items-start gap-3">
          <span className="text-warning text-lg" aria-hidden="true">⚠</span>
          <div className="min-w-0 text-sm">
            <p className="font-semibold text-warning mb-1">账户安全提醒</p>
            <p className="text-gray-300">
              所有提交均记录在SubmissionLedger中以确保可审计性。
              BRAIN API配额和速率限制适用。提交前请验证检查结果。
            </p>
          </div>
        </div>
      </div>

      <div className="card space-y-4">
        <h3 className="text-sm font-semibold text-gray-200">单个Alpha提交</h3>
        <div>
          <label className="block text-xs text-muted mb-1">Alpha ID（来自BRAIN验证）</label>
          <input
            type="text"
            value={alphaId}
            onChange={(e) => setAlphaId(e.target.value.slice(0, MAX_ALPHA_ID_LENGTH))}
            placeholder="例如 alpha_abc123..."
            maxLength={MAX_ALPHA_ID_LENGTH}
            aria-invalid={Boolean(alphaIdError)}
            aria-describedby="alpha-id-validation"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-brand-500 font-mono"
          />
          <p id="alpha-id-validation" className={`mt-1 text-xs ${alphaIdError ? "text-danger" : "text-muted"}`}>
            {alphaIdError || `使用字母、数字、_、-、.或:；最多 ${MAX_ALPHA_ID_LENGTH} 个字符。`}
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <button onClick={runCheck} disabled={!normalizedAlphaId || Boolean(alphaIdError) || checkApi.loading} className="btn-secondary text-sm">
            提交前检查
          </button>
          <button
            onClick={handleSubmit}
            disabled={!normalizedAlphaId || !confirmEnabled || !hasFreshSingleCheck || Boolean(alphaIdError) || api.loading}
            className="btn-danger text-sm"
          >
            提交Alpha
          </button>
        </div>

        <ProgressFeedback
          state={checkApi.error ? "error" : checkApi.loading ? "loading" : checkResult ? "success" : "idle"}
          title="提交前检查"
          progress={{
            phase: checkApi.loading ? "checking" : checkResult ? "completed" : "idle",
            status_message: checkApi.loading ? `正在检查 ${normalizedAlphaId}。` : checkResult ? "提交前检查完成。" : "就绪，可开始检查。",
          }}
          error={checkApi.error}
          onRetry={runCheck}
          compact={!checkApi.loading && !checkApi.error}
        />

        <ProgressFeedback
          state={api.error ? "error" : api.loading ? "loading" : "idle"}
          title="提交"
          progress={{
            phase: api.loading ? "submitting" : "idle",
            status_message: api.loading ? `正在提交 ${normalizedAlphaId}。` : "就绪，可开始提交。",
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
            我确认此Alpha已通过所有提交前检查，并希望将其提交至BRAIN。
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
            <p className="text-xs font-semibold text-success">最新提交回执</p>
            <p className="text-xs text-gray-300">
              Alpha <span className="font-mono">{lastSubmission.alphaId}</span> 已于{" "}
              <span className="font-mono">{lastSubmission.submittedAt}</span> 提交。
            </p>
          </div>
        )}
      </div>

      <div className="card space-y-4">
        <h3 className="text-sm font-semibold text-gray-200">批量操作</h3>
        <div>
          <label className="block text-xs text-muted mb-1">候选JSON数组</label>
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
            {candidateJsonError || "在运行批量操作前，请粘贴候选对象的JSON数组。"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={runBatchCheck} disabled={!submitCandidates.length || Boolean(candidateJsonError) || batchCheckApi.loading} className="btn-secondary text-sm">
            批量检查
          </button>
          <button
            onClick={runBatchSubmit}
            disabled={!submitCandidates.length || !batchConfirmEnabled || !hasFreshBatchCheck || Boolean(candidateJsonError) || Boolean(batchSubmitError) || batchSubmitApi.loading}
            className="btn-danger text-sm"
          >
            批量提交
          </button>
        </div>
        <label className="flex items-start gap-2 text-xs text-gray-300 cursor-pointer">
          <input
            type="checkbox"
            checked={batchConfirmEnabled}
            onChange={(e) => setBatchConfirmEnabled(e.target.checked)}
            disabled={!submitCandidates.length || Boolean(candidateJsonError) || Boolean(batchSubmitError)}
            aria-describedby="batch-confirm-submit-help"
            className="mt-0.5 rounded border-gray-600 bg-gray-800 text-brand-500 focus:ring-brand-500"
          />
          <span id="batch-confirm-submit-help">
            我确认这些候选已完成官方检查、提交前阻断项已复核，并允许执行批量提交。
          </span>
        </label>
        {batchSubmitError && !candidateJsonError && (
          <p id="batch-submit-validation" className="text-xs text-warning" role="alert">
            {batchSubmitError}
          </p>
        )}

        <ProgressFeedback
          state={batchCheckError ? "error" : batchCheckState}
          title="批量检查"
          progress={batchCheckProgress}
          error={batchCheckError}
          onRetry={runBatchCheck}
          compact={batchCheckState === "idle" || batchCheckState === "success"}
        />

        <div ref={batchSubmissionStatusRef} tabIndex={-1} className="min-w-0 outline-none focus:ring-2 focus:ring-brand-500/50">
          <ProgressFeedback
            state={submitError ? "error" : submitState}
            title="批量提交"
            progress={submitProgress}
            error={submitError}
            onRetry={runBatchSubmit}
            compact={submitState === "idle" || submitState === "success"}
          />
        </div>

        {batchCheckResult && (
          <div className="card bg-gray-950 border-gray-800 p-4">
            <h4 className="text-xs font-semibold text-gray-300 mb-2">批量检查结果</h4>
            <pre className="text-xs text-gray-300 font-mono overflow-x-auto max-h-56 overflow-y-auto">
              {JSON.stringify(batchCheckResult, null, 2)}
            </pre>
          </div>
        )}
      </div>

      {checkResult && (
        <div className="card space-y-2">
          <h3 className="text-sm font-semibold text-gray-200">提交前检查结果</h3>
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
  if (!text) return "Alpha ID为必填项。";
  if (text.length > MAX_ALPHA_ID_LENGTH) return `Alpha ID不能超过 ${MAX_ALPHA_ID_LENGTH} 个字符。`;
  if (!ALPHA_ID_PATTERN.test(text)) return "Alpha ID只能包含字母、数字、下划线、短横线、点或冒号。";
  return "";
}

function validateCandidateJsonRows(candidates: Candidate[]) {
  for (const [index, candidate] of candidates.entries()) {
    for (const field of ["alpha_id", "official_alpha_id", "simulation_id"] as const) {
      const value = candidate[field];
      if (value == null || value === "") continue;
      if (typeof value !== "string") return `候选行 ${index + 1} 的 ${field} 必须为字符串。`;
      const error = validateAlphaId(value);
      if (error) return `候选行 ${index + 1} 的 ${field}: ${error}`;
    }
  }
  return "";
}

function validateBatchSubmitCandidates(candidates: Candidate[]) {
  if (candidates.length > MAX_BATCH_ALPHA_IDS) return `批量提交最多支持 ${MAX_BATCH_ALPHA_IDS} 个候选。`;
  const alphaIds = candidates.map(candidateAlphaId).filter(Boolean);
  if (!alphaIds.length) return "批量提交前，至少一个候选行必须包含 alpha_id 或 official_alpha_id。";
  for (const alphaId of alphaIds) {
    const error = validateAlphaId(alphaId);
    if (error) return error;
  }
  return "";
}

function candidateAlphaId(candidate: Candidate) {
  return String(candidate.alpha_id || candidate.official_alpha_id || "").trim();
}

function candidateBatchSignature(candidates: Candidate[]) {
  return JSON.stringify(
    candidates.map((candidate) => ({
      alpha_id: candidateAlphaId(candidate),
      official_alpha_id: candidate.official_alpha_id || "",
      simulation_id: candidate.simulation_id || "",
      expression: candidate.expression || "",
    })),
  );
}
