/**
 * 根应用组件 - 简洁状态卡导航模式
 * 
 * 设计原则：
 * 1. 状态卡作为核心导航入口
 * 2. 简化交互元素，突出核心操作
 * 3. 统一中文界面
 * 4. 渐进式披露复杂功能
 */

import { useState, useCallback, useRef } from "react";
import type { BrainCredentials, Candidate, CardViewId } from "@/types";
import { useApi } from "@/hooks/useApi";
import { useToast } from "@/hooks/useToast";
import ToastContainer from "@/components/ToastContainer";
import StateCards from "@/components/StateCards";
import Dashboard from "@/components/Dashboard";
import JobMonitor from "@/components/JobMonitor";
import CandidateTable from "@/components/CandidateTable";
import OfficialBacktestSlots from "@/components/OfficialBacktestSlots";
import QualityCheckPanel from "@/components/QualityCheckPanel";
import ScoringPanel from "@/components/ScoringPanel";
import SubmissionConfirmPanel from "@/components/SubmissionConfirmPanel";
import SubmissionPanel from "@/components/SubmissionPanel";
import ConfigPanel from "@/components/ConfigPanel";
import SnapshotPanel from "@/components/SnapshotPanel";

// 状态卡配置 - 核心流程入口
const CARD_CONFIG = {
  dashboard: { title: "运行总览", subtitle: "流水线状态、进度与运行快照" },
  candidates: { title: "候选管理", subtitle: "生成、查看、筛选候选Alpha" },
  official_backtests: { title: "回测监控", subtitle: "官方回测槽位状态监控" },
  scoring: { title: "科学评分", subtitle: "官方指标、归因与门禁评分" },
  quality_check: { title: "质量门禁", subtitle: "达标检查与质量评估" },
  submission_confirm: { title: "提交确认", subtitle: "提交前阻断原因与候选审计" },
  submission: { title: "手动提交", subtitle: "人工确认后的检查与提交操作" },
  checkpoint_status: { title: "断点历史", subtitle: "断点续跑与运行历史回溯" },
  config: { title: "系统配置", subtitle: "参数、阈值与运行预算" },
  cloud: { title: "云端快照", subtitle: "云端Alpha缓存与同步状态" },
} as const;

interface ConnectionTestResponse {
  ok: boolean;
  environment?: string;
  auth?: string;
  error?: string;
  error_code?: string;
}

function SessionBadge({ credentials }: { credentials: BrainCredentials }) {
  const hasSessionCredentials = Boolean(credentials.username || credentials.password || credentials.token);
  return (
    <div className={`flex items-center gap-2 rounded-full border px-3 py-1.5 ${hasSessionCredentials ? "border-emerald-300 bg-emerald-50" : "border-slate-300 bg-white"}`}>
      <span className={`h-2 w-2 rounded-full ${hasSessionCredentials ? "bg-success animate-pulse" : "bg-gray-500"}`} aria-hidden="true" />
      <span className={`text-sm font-medium ${hasSessionCredentials ? "text-emerald-700" : "text-slate-600"}`}>
        {hasSessionCredentials ? "本页凭证已填写" : "未连接 BRAIN"}
      </span>
    </div>
  );
}

function SettingsShortcut({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition-all duration-200 hover:border-slate-400 hover:bg-slate-50 hover:text-slate-950 focus:outline-none focus:ring-2 focus:ring-brand-500/50 focus:ring-offset-2 focus:ring-offset-white"
      aria-label="打开系统配置"
      title="系统配置"
    >
      <svg aria-hidden="true" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="3" />
        <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1 1.55V21a2 2 0 1 1-4 0v-.08a1.7 1.7 0 0 0-1-1.55 1.7 1.7 0 0 0-1.88.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.55-1H3a2 2 0 1 1 0-4h.08a1.7 1.7 0 0 0 1.55-1 1.7 1.7 0 0 0-.34-1.88l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.55V3a2 2 0 1 1 4 0v.08a1.7 1.7 0 0 0 1 1.55 1.7 1.7 0 0 0 1.88-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.4 9c.25.6.84 1 1.55 1H21a2 2 0 1 1 0 4h-.08a1.7 1.7 0 0 0-1.52 1Z" />
      </svg>
      <span className="hidden sm:inline">系统配置</span>
    </button>
  );
}

function CredentialQuickStart({
  credentials,
  onCredentialsChange,
  notify,
  onOpenConfig,
}: {
  credentials: BrainCredentials;
  onCredentialsChange: (credentials: BrainCredentials) => void;
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
  onOpenConfig: () => void;
}) {
  const connectionApi = useApi<ConnectionTestResponse>();
  const usernameInputRef = useRef<HTMLInputElement | null>(null);
  const hasSessionCredentials = Boolean(credentials.username || credentials.password || credentials.token);
  const credentialMode = credentials.token.trim()
    ? "Token"
    : credentials.username.trim() || credentials.password
      ? "账号密码"
      : "服务端环境变量";

  const updateCredential = <K extends keyof BrainCredentials>(key: K, value: BrainCredentials[K]) => {
    onCredentialsChange({ ...credentials, [key]: value });
  };

  const testConnection = async () => {
    const payload = credentialsPayload(credentials);
    if (!Object.keys(payload).length) {
      notify("info", "未填写页面凭证，将使用服务端环境变量测试 BRAIN 连接");
    }
    const result = await connectionApi.call("/api/test_connection", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (!result?.ok) {
      notify("error", result?.error || result?.error_code || "BRAIN 连接测试失败");
      return;
    }
    notify("success", "BRAIN 连接测试通过");
  };

  const focusCredentials = () => {
    usernameInputRef.current?.focus();
  };

  return (
    <section className="mb-8 grid w-full min-w-0 gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(420px,0.9fr)]" aria-label="BRAIN 凭证与生产验证">
      <div className="workflow-panel workflow-panel-primary min-w-0 space-y-6">
        <div className="flex flex-col gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="badge badge-info">Step 1</span>
              <span className="badge badge-neutral">凭证: {credentialMode}</span>
              <span className="badge badge-neutral">保存: 不落盘</span>
            </div>
            <h3 className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">BRAIN 账户连接</h3>
            <p className="mt-2 max-w-3xl text-base leading-7 text-slate-700">
              在这里输入测试账户。凭证只保留在当前浏览器页面，用于连接测试和本次非提交生产验证，不写入配置文件、导出文件或任务账本。
            </p>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <label className="block min-w-0 text-sm">
              <span className="mb-1 block font-medium text-slate-800">账户邮箱</span>
              <input
                ref={usernameInputRef}
                className="input"
                type="email"
                inputMode="email"
                autoComplete="username"
                value={credentials.username}
                onChange={(event) => updateCredential("username", event.target.value.trim())}
                placeholder="email@example.com"
                maxLength={160}
              />
            </label>
            <label className="block min-w-0 text-sm">
              <span className="mb-1 block font-medium text-slate-800">密码</span>
              <input
                className="input"
                type="password"
                autoComplete="current-password"
                value={credentials.password}
                onChange={(event) => updateCredential("password", event.target.value)}
                placeholder="BRAIN 密码"
                maxLength={256}
              />
            </label>
            <label className="block min-w-0 text-sm md:col-span-2">
              <span className="mb-1 block font-medium text-slate-800">Token（可选）</span>
              <input
                className="input"
                type="password"
                autoComplete="off"
                value={credentials.token}
                onChange={(event) => updateCredential("token", event.target.value.trim())}
                placeholder="已有 token 时可只填 token"
                maxLength={512}
              />
            </label>
          </div>

          <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm leading-6 text-emerald-950">
            当前页面只会把凭证随连接测试和非提交运行请求发送；保存配置、导出配置和任务账本都会去除账号、密码和 token。
          </div>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="workflow-note min-w-0 flex-1 text-sm" role="status" aria-live="polite">
              {connectionApi.error
                ? `连接失败: ${connectionApi.error}`
                : connectionApi.data?.ok
                  ? `连接正常: ${connectionApi.data.environment || "production"}`
                  : hasSessionCredentials
                    ? "凭证已填写，尚未测试"
                    : "也可以留空，使用服务端环境变量"}
            </div>
            <div className="flex flex-wrap gap-2">
              <button type="button" className="btn-secondary text-sm" onClick={onOpenConfig}>
                高级配置
              </button>
              <button type="button" className="btn-primary text-sm" onClick={testConnection} disabled={connectionApi.loading}>
                {connectionApi.loading ? "测试中..." : "测试 BRAIN 连接"}
              </button>
            </div>
          </div>
        </div>
      </div>

      <JobMonitor notify={notify} credentials={credentials} onNeedCredentials={focusCredentials} />
    </section>
  );
}

export default function App() {
  const [activeView, setActiveView] = useState<CardViewId | "cards">("cards");
  const [selectedCandidate, setSelectedCandidate] = useState<Candidate | null>(null);
  const [credentials, setCredentials] = useState<BrainCredentials>({ username: "", password: "", token: "" });
  const { toasts, addToast, dismissToast } = useToast();

  // 统一通知函数
  const notify = useCallback(
    (type: "success" | "error" | "warning" | "info", msg: string, action?: { label: string; onClick: () => void }) => {
      addToast(type, msg, 5000, action);
    },
    [addToast],
  );

  // 导航处理
  const handleNavigate = useCallback((view: CardViewId) => {
    setActiveView(view);
  }, []);

  // 返回状态卡
  const handleBack = useCallback(() => {
    setActiveView("cards");
  }, []);

  const openConfig = useCallback(() => {
    setActiveView("config");
  }, []);

  const openScoring = useCallback((candidate: Candidate) => {
    setSelectedCandidate(candidate);
    setActiveView("scoring");
  }, []);

  /* ── 状态卡着陆页 ─────────────────────────────────────────── */
  if (activeView === "cards") {
    return (
      <div className="app-shell min-h-[100dvh] w-full min-w-0 overflow-x-hidden flex flex-col bg-slate-50 text-slate-900 antialiased">
        {/* 顶部导航栏 */}
        <header className="app-header border-b px-4 py-4 sm:px-6 lg:px-8 shrink-0">
          <div className="mx-auto flex w-full max-w-7xl flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex min-w-0 items-center gap-4">
              {/* 品牌标识 */}
              <div className="w-10 h-10 rounded-lg bg-slate-950 flex items-center justify-center shadow-sm">
                <span className="text-lg font-bold text-white">B</span>
              </div>
              <div>
                <h1 className="text-xl font-bold text-slate-950 tracking-tight">
                  BRAIN Alpha Ops
                </h1>
                <p className="text-sm text-slate-600 mt-0.5">
                  本地研究控制台
                </p>
              </div>
            </div>
            
            {/* 状态与设置入口 */}
            <div className="flex w-full flex-wrap items-center justify-start gap-2 sm:w-auto sm:justify-end">
              <SessionBadge credentials={credentials} />
              <SettingsShortcut onClick={openConfig} />
            </div>
          </div>
        </header>

        {/* 主内容区 */}
        <main className="flex-1 w-full min-w-0 overflow-auto p-4 sm:p-6 lg:p-8">
          <div className="mx-auto w-full max-w-7xl min-w-0">
            {/* 页面标题 */}
            <div className="mb-6 flex min-w-0 flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-brand-700">生产验证工作台</p>
                <h2 className="mt-1 text-3xl font-bold tracking-tight text-slate-950 sm:text-4xl">
                  登录、运行、证明可用
                </h2>
                <p className="mt-3 max-w-4xl text-base leading-7 text-slate-700">
                  按顺序完成：输入 BRAIN 账户，测试连接，启动强制非提交的生产验证。页面会保留 job_id、进度、回测和提交为 0 的证明。
                </p>
              </div>
              <div className="workflow-steps grid min-w-0 grid-cols-3 gap-3 text-center text-xs sm:text-sm">
                <div>
                  <div className="font-semibold text-slate-950">1</div>
                  <div>填凭证</div>
                </div>
                <div>
                  <div className="font-semibold text-slate-950">2</div>
                  <div>测连接</div>
                </div>
                <div>
                  <div className="font-semibold text-slate-950">3</div>
                  <div>跑验证</div>
                </div>
              </div>
            </div>

            <CredentialQuickStart
              credentials={credentials}
              onCredentialsChange={setCredentials}
              notify={notify}
              onOpenConfig={openConfig}
            />
            
            {/* 状态卡组件 */}
            <StateCards onNavigate={handleNavigate} notify={notify} />
          </div>
        </main>

        {/* 底部信息 */}
        <footer className="border-t border-slate-200 bg-white/70 px-4 py-3 sm:px-6 lg:px-8 shrink-0">
          <div className="mx-auto flex w-full max-w-7xl min-w-0 items-center justify-between text-sm text-slate-500">
            <span>本地非提交工作台</span>
            <span>v0.3.0</span>
          </div>
        </footer>

        <ToastContainer toasts={toasts} onDismiss={dismissToast} />
      </div>
    );
  }

  /* ── 详情视图 ──────────────────────────────────────────────── */
  const config = CARD_CONFIG[activeView as keyof typeof CARD_CONFIG];
  const cardTitle = config?.title || activeView;
  const cardSubtitle = config?.subtitle || "";

  // 根据视图类型渲染内容
  let detailContent: React.ReactNode;
  switch (activeView) {
    case "dashboard":
      detailContent = <Dashboard notify={notify} credentials={credentials} />;
      break;
    case "candidates":
      detailContent = (
        <CandidateTable
          key="candidates"
          notify={notify}
          showProductionControls
          showRowActions
          onScore={openScoring}
        />
      );
      break;
    case "official_backtests":
      detailContent = <OfficialBacktestSlots notify={notify} />;
      break;
    case "scoring":
      detailContent = selectedCandidate ? (
        <ScoringPanel notify={notify} candidate={selectedCandidate} />
      ) : (
        <CandidateTable
          key="scoring_candidate_picker"
          notify={notify}
          showRowActions
          onScore={openScoring}
        />
      );
      break;
    case "quality_check":
      detailContent = <QualityCheckPanel notify={notify} />;
      break;
    case "submission_confirm":
      detailContent = <SubmissionConfirmPanel notify={notify} />;
      break;
    case "submission":
      detailContent = <SubmissionPanel notify={notify} />;
      break;
    case "checkpoint_status":
      detailContent = <SnapshotPanel key="checkpoint_status" notify={notify} viewMode="checkpoint_status" onNavigate={handleNavigate} />;
      break;
    case "config":
      detailContent = <ConfigPanel notify={notify} credentials={credentials} onCredentialsChange={setCredentials} />;
      break;
    case "cloud":
      detailContent = <SnapshotPanel key="cloud" notify={notify} viewMode="cloud" onNavigate={handleNavigate} />;
      break;
    default:
      detailContent = (
        <div className="card p-8 text-center">
          <p className="text-gray-400">未知视图</p>
        </div>
      );
  }

  return (
    <div className="app-shell min-h-[100dvh] w-full min-w-0 overflow-x-hidden flex flex-col bg-slate-50 text-slate-900 antialiased">
      {/* 详情页头部 */}
      <header className="app-header border-b px-4 py-4 sm:px-6 lg:px-8 shrink-0">
        <div className="mx-auto flex w-full max-w-7xl flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 items-center gap-4">
            {/* 返回按钮 */}
            <button
              type="button"
              onClick={handleBack}
              className="flex items-center gap-2 px-3 py-2 rounded-lg text-slate-600 hover:text-slate-950 hover:bg-slate-100 transition-all duration-200"
              aria-label="返回状态卡"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M19 12H5M12 19l-7-7 7-7" />
              </svg>
              <span className="text-sm font-medium">返回</span>
            </button>
            
            {/* 分隔线 */}
            <div className="h-6 w-px bg-slate-300" />
            
            {/* 页面标题 */}
            <div className="min-w-0">
              <h1 className="break-words text-xl font-bold text-slate-950 tracking-tight">
                {cardTitle}
              </h1>
              {cardSubtitle && (
                <p className="mt-0.5 break-words text-sm text-slate-600">
                  {cardSubtitle}
                </p>
              )}
            </div>
          </div>
          
          {/* 状态与设置入口 */}
          <div className="flex w-full flex-wrap items-center justify-start gap-2 sm:w-auto sm:justify-end">
            <span className="min-w-0 text-sm text-slate-600">
              {activeView === "dashboard" && "运行总览"}
              {activeView === "candidates" && "候选管理"}
              {activeView === "official_backtests" && "回测监控"}
              {activeView === "scoring" && "科学评分"}
              {activeView === "quality_check" && "质量门禁"}
              {activeView === "submission_confirm" && "提交确认"}
              {activeView === "submission" && "手动提交"}
              {activeView === "checkpoint_status" && "断点历史"}
              {activeView === "config" && "系统配置"}
              {activeView === "cloud" && "云端快照"}
            </span>
            {activeView !== "config" ? <SettingsShortcut onClick={openConfig} /> : <SessionBadge credentials={credentials} />}
          </div>
        </div>
      </header>

      {/* 详情内容 */}
      <main className="flex-1 w-full min-w-0 overflow-auto p-4 sm:p-6 lg:p-8">
        <div className="mx-auto w-full max-w-7xl min-w-0">
          {detailContent}
        </div>
      </main>

      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}

function credentialsPayload(credentials: BrainCredentials) {
  const payload: Record<string, string> = {};
  const username = credentials.username.trim();
  const password = credentials.password;
  const token = credentials.token.trim();
  if (username) payload.username = username;
  if (password) payload.password = password;
  if (token) payload.token = token;
  return payload;
}
