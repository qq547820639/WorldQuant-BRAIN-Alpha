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
import { useGlobalData } from "@/hooks/useGlobalData";
import type {
  Candidate,
  CardViewId,
} from "@/types";
import ProgressFeedback from "@/components/ProgressFeedback";
import { safeDisplayErrorMessage } from "@/helpers/errorExperience";
import { backtestActiveCount, backtestSlotLimit } from "@/utils/backtestSlots";

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
    id: "official_operations",
    title: "官方操作",
    description: "按钮驱动的官方上下文、合规与阻断复核",
    icon: "00",
    color: "from-emerald-500 to-slate-700",
    action: "打开操作",
  },
  {
    id: "dashboard",
    title: "运行总览",
    description: "流水线状态、进度与运行快照",
    icon: "01",
    color: "from-slate-500 to-slate-700",
    action: "查看总览",
  },
  {
    id: "candidates",
    title: "候选管理",
    description: "生成、查看、筛选候选Alpha",
    icon: "02",
    color: "from-brand-500 to-brand-700",
    action: "管理候选",
  },
  {
    id: "official_backtests",
    title: "回测监控",
    description: "官方回测槽位状态监控",
    icon: "03",
    color: "from-blue-500 to-blue-700",
    action: "监控回测",
  },
  {
    id: "scoring",
    title: "科学评分",
    description: "官方指标、归因与门禁评分",
    icon: "04",
    color: "from-violet-500 to-violet-700",
    action: "查看评分",
  },
  {
    id: "quality_check",
    title: "质量门禁",
    description: "达标检查与质量评估",
    icon: "05",
    color: "from-success to-emerald-700",
    action: "检查质量",
  },
  {
    id: "submission_confirm",
    title: "阻断复核",
    description: "提交前阻断原因与候选审计",
    icon: "06",
    color: "from-warning to-amber-700",
    action: "查看阻断",
  },
  {
    id: "checkpoint_status",
    title: "续跑记录",
    description: "上次进度与运行历史回溯",
    icon: "08",
    color: "from-teal-500 to-emerald-700",
    action: "查看历史",
  },
  {
    id: "config",
    title: "系统配置",
    description: "参数、阈值与运行预算",
    icon: "09",
    color: "from-indigo-500 to-indigo-700",
    action: "系统设置",
  },
  {
    id: "cloud",
    title: "云端快照",
    description: "云端Alpha缓存与同步状态",
    icon: "10",
    color: "from-cyan-500 to-blue-700",
    action: "查看快照",
  },
];

export default function StateCards({ onNavigate, notify }: Props) {
  const { candidates: candidatesGlobal, slots: slotsGlobal, config: configGlobal, cloud: cloudGlobal, refreshAll } = useGlobalData();
  const checkpointApi = useApi<CheckpointStatusSummary>();

  const loadStateSnapshots = useCallback(() => {
    refreshAll();
    void checkpointApi.call("/api/checkpoint_status");
  }, [refreshAll, checkpointApi.call]);

  // 加载数据
  useEffect(() => {
    loadStateSnapshots();
  }, [loadStateSnapshots]);

  // 错误处理
  const stateErrors = useMemo(
    () => [
      labeledError("候选", candidatesGlobal.error),
      labeledError("回测", slotsGlobal.error),
      labeledError("配置", configGlobal.error),
      labeledError("历史", checkpointApi.error),
      labeledError("云端", cloudGlobal.error),
    ].filter(Boolean),
    [candidatesGlobal.error, slotsGlobal.error, configGlobal.error, checkpointApi.error, cloudGlobal.error],
  );

  useEffect(() => {
    if (stateErrors.length) notify("warning", `状态快照加载不完整: ${stateErrors.join("；")}`);
  }, [notify, stateErrors]);

  // 计算核心指标
  const candidates = candidatesGlobal.data?.candidates || candidatesGlobal.data?.items || [];
  const metrics = useMemo(() => {
    const slotLimit = backtestSlotLimit(slotsGlobal.data);
    const activeSlots = backtestActiveCount(slotsGlobal.data);
    const qualityCount = candidatesGlobal.data?.ready_count ?? candidates.filter(isSubmissionReadyCandidate).length;
    const cloudCount = cloudTotal(cloudGlobal.data);

    return {
      candidates: {
        total: candidatesGlobal.data?.total ?? candidates.length,
        label: "候选总数",
      },
      official_backtests: `${activeSlots}/${slotLimit}`,
      quality_check: {
        ready: qualityCount,
        label: "达标数量",
      },
      submission_confirm: {
        eligible: "打开",
        caption: "提交审计",
        label: "提交审计",
      },
      checkpoint_status: {
        history: checkpointApi.data?.history_count ?? 0,
        label: "历史记录",
      },
      config: {
        environment: configGlobal.data?.config?.environment || "-",
        label: "运行环境",
      },
      cloud: {
        total: cloudCount,
        label: "云端缓存",
      },
    };
  }, [candidates, candidatesGlobal.data?.ready_count, candidatesGlobal.data?.total, configGlobal.data, checkpointApi.data, cloudGlobal.data, slotsGlobal.data]);

  // 加载状态
  const loading = [
    candidatesGlobal,
    slotsGlobal,
    configGlobal,
    checkpointApi,
    cloudGlobal,
  ].some((api) => api.loading && !api.data);
  const loadError = stateErrors.length ? stateErrors.join("；") : "";

  // 获取指标值
  const getMetricValue = (id: CardViewId): string => {
    switch (id) {
      case "official_operations":
        return "Web";
      case "candidates":
        return String(metrics.candidates.total);
      case "dashboard":
        return "本地";
      case "official_backtests":
        return metrics.official_backtests;
      case "scoring":
        return String(metrics.quality_check.ready);
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
      case "official_operations":
        return "用户入口";
      case "candidates":
        return metrics.candidates.label;
      case "dashboard":
        return "本地服务";
      case "official_backtests":
        return "回测槽位";
      case "scoring":
        return "可评分候选";
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
    <div className="w-full min-w-0 max-w-full animate-fade-in">
      {/* 加载状态 */}
      {loading && (
        <div className="mb-8 w-full max-w-full overflow-hidden">
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
      <div className="grid w-full max-w-full grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5">
        {CARD_CONFIGS.map((config) => (
          <button
            key={config.id}
            type="button"
            onClick={() => onNavigate(config.id)}
            className="group relative min-w-0 overflow-hidden rounded-lg border border-slate-200 bg-white p-5 text-left shadow-sm transition-all duration-200 hover:border-brand-200 hover:bg-brand-50/40 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-brand-500/50 focus:ring-offset-2 focus:ring-offset-slate-50"
          >
            {/* 背景渐变 */}
            <div className={`absolute inset-x-0 top-0 h-1 bg-gradient-to-r ${config.color} opacity-80`} />
            
            {/* 图标 */}
            <div className="relative mb-4">
              <span className="font-mono text-xs font-semibold tracking-wide text-brand-700" aria-hidden="true">{config.icon}</span>
            </div>
            
            {/* 标题和描述 */}
            <div className="relative">
              <h3 className="text-lg font-bold text-slate-950 tracking-tight">
                {config.title}
              </h3>
              <p className="mt-2 text-sm text-slate-600 leading-6">
                {config.description}
              </p>
            </div>
            
            {/* 指标显示 */}
            <div className="relative mt-6 pt-4 border-t border-slate-200">
              <div className="grid min-w-0 gap-2">
                <span className="min-w-0 text-sm font-medium leading-tight text-slate-600">
                  {getMetricLabel(config.id)}
                </span>
                <span className="min-w-0 max-w-full break-words text-right text-2xl font-bold leading-tight tabular-nums text-slate-950 xl:text-xl 2xl:text-2xl">
                  {getMetricValue(config.id)}
                </span>
              </div>
            </div>
            
            {/* 操作提示 */}
            <div className="relative mt-4">
              <span className="inline-flex items-center gap-2 text-sm font-medium text-brand-700 group-hover:text-brand-800 transition-colors">
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
      <div className="mt-8 max-w-full rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex items-center gap-3">
          <span className="h-2 w-2 rounded-full bg-brand-600" aria-hidden="true" />
          <p className="text-sm text-slate-600">
            点击状态卡进入对应功能模块，完成从候选生成到提交前阻断复核的可视化管理；真实提交保持关闭
          </p>
        </div>
      </div>
    </div>
  );
}

// 辅助函数
function isSubmissionReadyCandidate(candidate: Candidate) {
  const status = String(candidate.lifecycle_status || "").toLowerCase();
  return (
    status === "submission_ready" ||
    candidate.quality_diagnosis?.submission_ready === true ||
    (candidate.gate as { submission_ready?: unknown } | undefined)?.submission_ready === true
  );
}

function cloudTotal(payload: (CloudAlphaSummary & { summary?: Record<string, unknown>; total?: number }) | null) {
  const summary = payload?.summary || {};
  const value = payload?.count ?? payload?.total ?? summary.count ?? summary.total ?? summary.total_count;
  return value == null ? "-" : String(value);
}

function labeledError(label: string, error: string | null) {
  if (!error) return "";
  return `${label}: ${userFacingError(error)}`;
}

function userFacingError(error: string) {
  return safeDisplayErrorMessage(error, "状态读取失败，请重试或检查服务状态。");
}
