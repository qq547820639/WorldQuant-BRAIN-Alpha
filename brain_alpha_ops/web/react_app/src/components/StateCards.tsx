/**
 * 状态卡着陆页 - 核心导航入口
 * 
 * 设计原则：
 * 1. 简洁直观的卡片设计
 * 2. 核心指标突出显示
 * 3. 操作引导清晰
 * 4. 统一中文界面
 */

import { useCallback, useEffect, useMemo } from "react";
import { useApi } from "@/hooks/useApi";
import type {
  BacktestSlotsResponse,
  Candidate,
  CardViewId,
  CloudAlphaSummary,
  RunConfig,
  SubmitReadinessResponse,
} from "@/types";
import ProgressFeedback from "@/components/ProgressFeedback";

interface Props {
  onNavigate: (view: CardViewId) => void;
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
}

interface CheckpointStatusSummary {
  checkpoint_count?: number;
  history_count?: number;
  resume_available?: boolean;
}

// 状态卡配置 - 简化版
interface CardConfig {
  id: CardViewId;
  title: string;
  description: string;
  icon: string;
  color: string;
  action: string;
}

const CARD_CONFIGS: CardConfig[] = [
  {
    id: "candidates",
    title: "候选管理",
    description: "生成、查看、筛选候选Alpha",
    icon: "📊",
    color: "from-brand-500 to-brand-700",
    action: "管理候选",
  },
  {
    id: "official_backtests",
    title: "回测监控",
    description: "官方回测槽位状态监控",
    icon: "⏱",
    color: "from-blue-500 to-blue-700",
    action: "监控回测",
  },
  {
    id: "quality_check",
    title: "质量门禁",
    description: "达标检查与质量评估",
    icon: "✅",
    color: "from-success to-emerald-700",
    action: "检查质量",
  },
  {
    id: "submission_confirm",
    title: "提交管理",
    description: "提交前确认与提交操作",
    icon: "🚀",
    color: "from-warning to-amber-700",
    action: "管理提交",
  },
  {
    id: "checkpoint_status",
    title: "断点历史",
    description: "断点续跑与运行历史回溯",
    icon: "↻",
    color: "from-teal-500 to-emerald-700",
    action: "查看历史",
  },
  {
    id: "config",
    title: "系统配置",
    description: "参数、阈值与运行预算",
    icon: "⚙",
    color: "from-indigo-500 to-indigo-700",
    action: "系统设置",
  },
  {
    id: "cloud",
    title: "云端快照",
    description: "云端Alpha缓存与同步状态",
    icon: "☁",
    color: "from-cyan-500 to-blue-700",
    action: "查看快照",
  },
];

export default function StateCards({ onNavigate, notify }: Props) {
  // API调用
  const candidatesApi = useApi<{ candidates?: Candidate[]; items?: Candidate[]; total?: number }>();
  const slotsApi = useApi<BacktestSlotsResponse>();
  const readinessApi = useApi<SubmitReadinessResponse>();
  const configApi = useApi<{ config?: RunConfig }>();
  const checkpointApi = useApi<CheckpointStatusSummary>();
  const cloudApi = useApi<CloudAlphaSummary & { summary?: Record<string, unknown>; total?: number }>();

  const loadStateSnapshots = useCallback(() => {
    void candidatesApi.call("/api/candidates?limit=1000");
    void slotsApi.call("/api/backtest_slots");
    void readinessApi.call("/api/submit_readiness");
    void configApi.call("/api/config");
    void checkpointApi.call("/api/checkpoint_status");
    void cloudApi.call("/api/snapshot/cloud?limit=10");
  }, [candidatesApi.call, slotsApi.call, readinessApi.call, configApi.call, checkpointApi.call, cloudApi.call]);

  // 加载数据
  useEffect(() => {
    loadStateSnapshots();
  }, [loadStateSnapshots]);

  // 错误处理
  const stateErrors = useMemo(
    () => [
      labeledError("候选", candidatesApi.error),
      labeledError("回测", slotsApi.error),
      labeledError("提交", readinessApi.error),
      labeledError("配置", configApi.error),
      labeledError("历史", checkpointApi.error),
      labeledError("云端", cloudApi.error),
    ].filter(Boolean),
    [candidatesApi.error, slotsApi.error, readinessApi.error, configApi.error, checkpointApi.error, cloudApi.error],
  );

  useEffect(() => {
    if (stateErrors.length) notify("warning", `状态快照加载不完整: ${stateErrors.join("；")}`);
  }, [notify, stateErrors]);

  // 计算核心指标
  const candidates = candidatesApi.data?.candidates || candidatesApi.data?.items || [];
  const metrics = useMemo(() => {
    const slots = normalizeSlots(slotsApi.data);
    const slotLimit = backtestSlotLimit(slotsApi.data);
    const activeSlots = slots.filter((slot) => isActiveSlot(slot.status)).length;
    const qualityCount = candidates.filter(isSubmissionReadyCandidate).length;
    const submitCount = readinessApi.data?.eligible_count ?? 0;
    const cloudCount = cloudTotal(cloudApi.data);

    return {
      candidates: {
        total: candidatesApi.data?.total ?? candidates.length,
        label: "候选总数",
      },
      official_backtests: `${activeSlots}/${slotLimit}`,
      quality_check: {
        ready: qualityCount,
        label: "达标数量",
      },
      submission_confirm: {
        eligible: submitCount,
        caption: "可提交 Alpha",
        label: "可提交数",
      },
      checkpoint_status: {
        history: checkpointApi.data?.history_count ?? 0,
        label: "历史记录",
      },
      config: {
        environment: configApi.data?.config?.environment || "-",
        label: "运行环境",
      },
      cloud: {
        total: cloudCount,
        label: "云端缓存",
      },
    };
  }, [candidates, candidatesApi.data?.total, readinessApi.data, configApi.data, checkpointApi.data, cloudApi.data, slotsApi.data]);

  // 加载状态
  const loading = candidatesApi.loading && !candidatesApi.data;
  const loadError = stateErrors.length ? stateErrors.join("；") : "";

  // 获取指标值
  const getMetricValue = (id: CardViewId): string => {
    switch (id) {
      case "candidates":
        return String(metrics.candidates.total);
      case "official_backtests":
        return metrics.official_backtests;
      case "quality_check":
        return String(metrics.quality_check.ready);
      case "submission_confirm":
        return String(metrics.submission_confirm.eligible);
      case "checkpoint_status":
        return String(metrics.checkpoint_status.history);
      case "config":
        return metrics.config.environment;
      case "cloud":
        return metrics.cloud.total;
      default:
        return "-";
    }
  };

  // 获取指标标签
  const getMetricLabel = (id: CardViewId): string => {
    switch (id) {
      case "candidates":
        return metrics.candidates.label;
      case "official_backtests":
        return "回测槽位";
      case "quality_check":
        return metrics.quality_check.label;
      case "submission_confirm":
        return metrics.submission_confirm.label;
      case "checkpoint_status":
        return metrics.checkpoint_status.label;
      case "config":
        return metrics.config.label;
      case "cloud":
        return metrics.cloud.label;
      default:
        return "";
    }
  };

  return (
    <div className="min-w-0 animate-fade-in">
      {/* 加载状态 */}
      {loading && (
        <div className="mb-8">
          <ProgressFeedback
            state="loading"
            title="状态卡"
            progress={{ phase: "state_cards_load", status_message: "正在加载本地状态快照。" }}
          />
        </div>
      )}

      {/* 错误提示 */}
      {loadError && !loading && (
        <div className="mb-8 p-4 rounded-xl border border-danger/30 bg-danger/5" role="alert" aria-live="assertive">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex min-w-0 items-start gap-3">
              <span className="text-danger" aria-hidden="true">⚠</span>
              <div className="min-w-0">
                <p className="text-sm font-medium text-danger">状态快照加载不完整</p>
                <p className="mt-1 break-words text-sm text-danger/90">{loadError}</p>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={loadStateSnapshots} className="btn-secondary min-h-11 text-sm">
                重试全部
              </button>
              <button type="button" onClick={() => onNavigate("config")} className="btn-ghost min-h-11 text-sm">
                检查配置
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 状态卡网格 */}
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-7">
        {CARD_CONFIGS.map((config) => (
          <button
            key={config.id}
            type="button"
            onClick={() => onNavigate(config.id)}
            className="group relative overflow-hidden rounded-2xl border border-gray-800/50 bg-gray-900/80 p-6 text-left transition-all duration-300 hover:border-gray-700/50 hover:bg-gray-900 hover:shadow-xl hover:shadow-gray-900/50 focus:outline-none focus:ring-2 focus:ring-brand-500/50 focus:ring-offset-2 focus:ring-offset-gray-950"
          >
            {/* 背景渐变 */}
            <div className={`absolute inset-0 bg-gradient-to-br ${config.color} opacity-0 group-hover:opacity-5 transition-opacity duration-300`} />
            
            {/* 图标 */}
            <div className="relative mb-4">
              <span className="text-3xl" aria-hidden="true">{config.icon}</span>
            </div>
            
            {/* 标题和描述 */}
            <div className="relative">
              <h3 className="text-lg font-bold text-white tracking-tight">
                {config.title}
              </h3>
              <p className="mt-2 text-sm text-gray-400 leading-relaxed">
                {config.description}
              </p>
            </div>
            
            {/* 指标显示 */}
            <div className="relative mt-6 pt-4 border-t border-gray-800/50">
              <div className="grid min-w-0 gap-2">
                <span className="min-w-0 text-sm font-medium leading-tight text-gray-300">
                  {getMetricLabel(config.id)}
                </span>
                <span className="min-w-0 max-w-full break-words text-right text-2xl font-bold leading-tight tabular-nums text-white xl:text-xl 2xl:text-2xl">
                  {getMetricValue(config.id)}
                </span>
              </div>
            </div>
            
            {/* 操作提示 */}
            <div className="relative mt-4">
              <span className="inline-flex items-center gap-2 text-sm font-medium text-brand-400 group-hover:text-brand-300 transition-colors">
                {config.action}
                <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="transition-transform group-hover:translate-x-1">
                  <path d="M5 12h14M12 5l7 7-7 7" />
                </svg>
              </span>
            </div>
          </button>
        ))}
      </div>

      {/* 流程说明 */}
      <div className="mt-8 p-4 rounded-xl border border-gray-800/30 bg-gray-900/30">
        <div className="flex items-center gap-3">
          <span className="text-gray-500" aria-hidden="true">💡</span>
          <p className="text-sm text-gray-400">
            点击状态卡进入对应功能模块，完成从候选生成到提交的全流程管理
          </p>
        </div>
      </div>
    </div>
  );
}

// 辅助函数
function normalizeSlots(payload: BacktestSlotsResponse | null) {
  const slots = Array.isArray(payload?.slots) ? payload.slots : [];
  return Array.from({ length: backtestSlotLimit(payload) }, (_, index) => index + 1)
    .map((slot) => slots.find((row) => Number(row.slot) === slot) || { slot, status: "EMPTY" });
}

function backtestSlotLimit(payload: BacktestSlotsResponse | null) {
  const fromPayload = Number(payload?.slot_limit);
  const fromSummary = Number(payload?.queue_summary?.slot_limit);
  const value = Number.isFinite(fromPayload) && fromPayload > 0 ? fromPayload : fromSummary;
  return Math.max(3, Number.isFinite(value) && value > 0 ? Math.trunc(value) : 3);
}

function isActiveSlot(status: unknown) {
  const text = String(status || "").toUpperCase();
  return Boolean(text && !["", "EMPTY", "COMPLETED", "FAILED", "ERROR", "CAPACITY_WAIT"].includes(text));
}

function isSubmissionReadyCandidate(candidate: Candidate) {
  const status = String(candidate.lifecycle_status || "").toLowerCase();
  return status === "submission_ready" || Boolean((candidate.gate as { submission_ready?: unknown } | undefined)?.submission_ready);
}

function cloudTotal(payload: (CloudAlphaSummary & { summary?: Record<string, unknown>; total?: number }) | null) {
  const summary = payload?.summary || {};
  const value = payload?.count ?? payload?.total ?? summary.total_count ?? summary.returned_count;
  return value == null ? "-" : String(value);
}

function labeledError(label: string, error: string | null) {
  if (!error) return "";
  return `${label}: ${userFacingError(error)}`;
}

function userFacingError(error: string) {
  const text = String(error || "").trim();
  if (!text) return "请求失败";
  if (/failed to fetch|network error|load failed/i.test(text)) return "本地服务暂不可达，请重试或检查服务状态";
  return text.length > 140 ? `${text.slice(0, 140)}...` : text;
}
