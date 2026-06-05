/**
 * 根应用组件 - 简洁状态卡导航模式
 * 
 * 设计原则：
 * 1. 状态卡作为核心导航入口
 * 2. 简化交互元素，突出核心操作
 * 3. 统一中文界面
 * 4. 渐进式披露复杂功能
 */

import { useState, useCallback } from "react";
import type { CardViewId } from "@/types";
import { useToast } from "@/hooks/useToast";
import ToastContainer from "@/components/ToastContainer";
import StateCards from "@/components/StateCards";
import CandidateTable from "@/components/CandidateTable";
import OfficialBacktestSlots from "@/components/OfficialBacktestSlots";
import QualityCheckPanel from "@/components/QualityCheckPanel";
import SubmissionConfirmPanel from "@/components/SubmissionConfirmPanel";
import ConfigPanel from "@/components/ConfigPanel";
import SnapshotPanel from "@/components/SnapshotPanel";

// 状态卡配置 - 核心流程入口
const CARD_CONFIG = {
  candidates: { title: "候选管理", subtitle: "生成、查看、筛选候选Alpha" },
  official_backtests: { title: "回测监控", subtitle: "官方回测槽位状态监控" },
  quality_check: { title: "质量门禁", subtitle: "达标检查与质量评估" },
  submission_confirm: { title: "提交管理", subtitle: "提交前确认与提交操作" },
  checkpoint_status: { title: "断点历史", subtitle: "断点续跑与运行历史回溯" },
  config: { title: "系统配置", subtitle: "参数、阈值与运行预算" },
  cloud: { title: "云端快照", subtitle: "云端Alpha缓存与同步状态" },
} as const;

function SessionBadge() {
  return (
    <div className="flex items-center gap-2 rounded-full border border-success/20 bg-success/10 px-3 py-1.5">
      <span className="h-2 w-2 rounded-full bg-success animate-pulse" aria-hidden="true" />
      <span className="text-sm font-medium text-success">本地会话</span>
    </div>
  );
}

function SettingsShortcut({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-2 rounded-lg border border-gray-700/60 bg-gray-900/70 px-3 py-2 text-sm font-medium text-gray-200 transition-all duration-200 hover:border-gray-600 hover:bg-gray-800 hover:text-white focus:outline-none focus:ring-2 focus:ring-brand-500/50 focus:ring-offset-2 focus:ring-offset-gray-950"
      aria-label="打开系统配置"
      title="系统配置"
    >
      <svg aria-hidden="true" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="3" />
        <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1 1.55V21a2 2 0 1 1-4 0v-.08a1.7 1.7 0 0 0-1-1.55 1.7 1.7 0 0 0-1.88.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.55-1H3a2 2 0 1 1 0-4h.08a1.7 1.7 0 0 0 1.55-1 1.7 1.7 0 0 0-.34-1.88l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.55V3a2 2 0 1 1 4 0v.08a1.7 1.7 0 0 0 1 1.55 1.7 1.7 0 0 0 1.88-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.4 9c.25.6.84 1 1.55 1H21a2 2 0 1 1 0 4h-.08a1.7 1.7 0 0 0-1.52 1Z" />
      </svg>
      <span>系统配置</span>
    </button>
  );
}

export default function App() {
  const [activeView, setActiveView] = useState<CardViewId | "cards">("cards");
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

  /* ── 状态卡着陆页 ─────────────────────────────────────────── */
  if (activeView === "cards") {
    return (
      <div className="min-h-[100dvh] min-w-0 flex flex-col bg-gray-950 text-gray-100 antialiased">
        {/* 顶部导航栏 */}
        <header className="bg-gray-900/80 backdrop-blur-sm border-b border-gray-800/50 px-4 py-4 sm:px-6 lg:px-8 shrink-0">
          <div className="mx-auto flex max-w-7xl flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-4">
              {/* 品牌标识 */}
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center shadow-lg shadow-brand-500/20">
                <span className="text-lg font-bold text-white">B</span>
              </div>
              <div>
                <h1 className="text-xl font-bold text-white tracking-tight">
                  BRAIN Alpha Ops
                </h1>
                <p className="text-sm text-gray-400 mt-0.5">
                  本地研究控制台
                </p>
              </div>
            </div>
            
            {/* 状态与设置入口 */}
            <div className="flex w-full items-center justify-between gap-3 sm:w-auto sm:justify-end">
              <SessionBadge />
              <SettingsShortcut onClick={openConfig} />
            </div>
          </div>
        </header>

        {/* 主内容区 */}
        <main className="flex-1 min-w-0 p-4 sm:p-6 lg:p-8 overflow-auto">
          <div className="max-w-7xl mx-auto">
            {/* 页面标题 */}
            <div className="mb-8">
              <h2 className="text-2xl font-bold text-white tracking-tight">
                生产流程
              </h2>
              <p className="text-base text-gray-400 mt-2">
                候选生成 → 官方回测 → 质量检查 → 提交确认
              </p>
            </div>
            
            {/* 状态卡组件 */}
            <StateCards onNavigate={handleNavigate} notify={notify} />
          </div>
        </main>

        {/* 底部信息 */}
        <footer className="bg-gray-900/50 border-t border-gray-800/30 px-4 py-3 sm:px-6 lg:px-8 shrink-0">
          <div className="max-w-7xl mx-auto flex items-center justify-between text-sm text-gray-500">
            <span>本地只读快照</span>
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
    case "candidates":
      detailContent = (
        <CandidateTable
          key="candidates"
          notify={notify}
          showProductionControls
          showRowActions={false}
        />
      );
      break;
    case "official_backtests":
      detailContent = <OfficialBacktestSlots notify={notify} />;
      break;
    case "quality_check":
      detailContent = <QualityCheckPanel notify={notify} />;
      break;
    case "submission_confirm":
      detailContent = <SubmissionConfirmPanel notify={notify} />;
      break;
    case "checkpoint_status":
      detailContent = <SnapshotPanel key="checkpoint_status" notify={notify} viewMode="checkpoint_status" onNavigate={handleNavigate} />;
      break;
    case "config":
      detailContent = <ConfigPanel notify={notify} />;
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
    <div className="min-h-[100dvh] min-w-0 flex flex-col bg-gray-950 text-gray-100 antialiased">
      {/* 详情页头部 */}
      <header className="bg-gray-900/80 backdrop-blur-sm border-b border-gray-800/50 px-4 py-4 sm:px-6 lg:px-8 shrink-0">
        <div className="mx-auto flex max-w-7xl flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 items-center gap-4">
            {/* 返回按钮 */}
            <button
              type="button"
              onClick={handleBack}
              className="flex items-center gap-2 px-3 py-2 rounded-lg text-gray-300 hover:text-white hover:bg-gray-800/50 transition-all duration-200"
              aria-label="返回状态卡"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M19 12H5M12 19l-7-7 7-7" />
              </svg>
              <span className="text-sm font-medium">返回</span>
            </button>
            
            {/* 分隔线 */}
            <div className="h-6 w-px bg-gray-700" />
            
            {/* 页面标题 */}
            <div>
              <h1 className="text-xl font-bold text-white tracking-tight">
                {cardTitle}
              </h1>
              {cardSubtitle && (
                <p className="text-sm text-gray-400 mt-0.5">
                  {cardSubtitle}
                </p>
              )}
            </div>
          </div>
          
          {/* 状态与设置入口 */}
          <div className="flex w-full items-center justify-between gap-3 sm:w-auto sm:justify-end">
            <span className="text-sm text-gray-400">
              {activeView === "candidates" && "候选管理"}
              {activeView === "official_backtests" && "回测监控"}
              {activeView === "quality_check" && "质量门禁"}
              {activeView === "submission_confirm" && "提交管理"}
              {activeView === "checkpoint_status" && "断点历史"}
              {activeView === "config" && "系统配置"}
              {activeView === "cloud" && "云端快照"}
            </span>
            {activeView !== "config" ? <SettingsShortcut onClick={openConfig} /> : <SessionBadge />}
          </div>
        </div>
      </header>

      {/* 详情内容 */}
      <main className="flex-1 min-w-0 p-4 sm:p-6 lg:p-8 overflow-auto">
        <div className="max-w-7xl mx-auto">
          {detailContent}
        </div>
      </main>

      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}
