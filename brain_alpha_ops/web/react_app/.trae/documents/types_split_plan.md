# TypeScript 类型文件拆分计划

## 概述
将 `src/types/index.ts`（1223 行）拆分为 5 个模块文件，每个文件 ≤ 300 行，保持 100% 向后兼容。

## 文件结构

### 1. src/types/scoring.ts — 评分相关类型
**预计行数：约 130 行**

包含类型：
- `Scorecard`
- `ScoreLayerDetail`
- `ScoreConfidence`
- `HardGateResult`
- `ScoreAttribution`
- `ScoringResult`
- `ScoreLayer`
- `ScoreLayerItem`
- `OfficialGateResult`
- `OfficialGateCheckItem`
- `AttributionNode`
- `ScoringAttributionResponse`
- `FailureItem`

**依赖：无（最底层模块）**

---

### 2. src/types/candidate.ts — 候选核心类型
**预计行数：约 260 行**

包含类型：
- `Candidate`
- `AlphaLifecycleRecord`
- `AlphaLifecycleTrace`
- `AlphaLifecycleHistoryResponse`
- `CandidateExtraFields`
- `CandidateOptimizationExplanation`
- `CandidateScientificAudit`
- `CandidateProductionDecision`
- `CandidateDecisionEvidence`
- `LocalQuality`
- `AlphaOutputConfig`
- `AlphaQualityReason`
- `QualityDiagnosis`
- `OfficialMetrics`
- `QualityGate`
- `GateCheck`
- `CandidateCheckResult`
- `CandidateWorkflowPlan`
- `CandidateListMeta`
- `CandidateQueueView`

**依赖：** `import type * as ScoringTypes from './scoring'`（Scorecard 等评分类型）

---

### 3. src/types/api.ts — API 响应和任务相关类型
**预计行数：约 430 行（超出 300 行限制 ⚠️）**

包含类型：
- `ApiResponse`
- `ApiUserError`
- `JobStatus`
- `SyncHistoryItem`
- `JobProgress`
- `OfficialContextCache`
- `CloudAlphaCache`
- `ProgressLifecycle`
- `UnifiedProgress`
- `SSEEvent`
- `SSECandidateEventData`
- `PhaseData`
- `ProductionResultSummary`
- `CloudAlphaSummary`
- `CloudAlphaWithMetrics`
- `TrendApiResponse`
- `BacktestSlot`
- `BacktestSlotsResponse`
- `BacktestStatusBoard`
- `BacktestQueueSummary`
- `SubmitReadinessResponse`
- `SubmitReadinessCandidate`
- `SubmitReadinessFinding`
- `ReadinessReasonCount`
- `CloudAlpha`
- `ResearchMemorySummary`
- `FamilyStat`
- `FieldStat`
- `OperatorStat`
- `FailurePattern`

**依赖：** `import type * as CandidateTypes from './candidate'`（OfficialMetrics, QualityGate）

**⚠️ 问题：** api.ts 约 430 行，超出 300 行限制。

**调整方案（二选一）：**
- **方案 A：** 将 `BacktestSlot / BacktestSlotsResponse / BacktestStatusBoard / BacktestQueueSummary` 移至 `candidate.ts`（因 BacktestSlot 引用 OfficialMetrics 和 QualityGate，逻辑上属于候选相关）
- **方案 B：** 将 `CloudAlpha / CloudAlphaWithMetrics / CloudAlphaSummary / ResearchMemorySummary / FamilyStat / FieldStat / OperatorStat / FailurePattern` 移至 `candidate.ts`
- **方案 C：** 新增第 6 个文件 `src/types/cloud.ts` 存放云 Alpha 和回测槽相关类型

---

### 4. src/types/config.ts — 配置相关类型
**预计行数：约 70 行**

包含类型：
- `RunConfig`
- `BrainSettings`
- `BudgetConfig`
- `ThresholdConfig`
- `ScoringConfig`
- `BrainCredentials`

**依赖：无**

---

### 5. src/types/ui.ts — UI 状态和导航类型
**预计行数：约 120 行**

包含类型：
- `TabId`
- `Toast`
- `PhaseId`
- `PhaseStatus`
- `PhaseGroup`
- `PhaseNavItem`
- `PhaseState`
- `StepGuideItem`
- `CardViewId`
- `PhaseApiStatus`
- `LifecycleMetric`
- `LifecycleMetricProps`
- `LifecycleReplayPanelProps`
- `QualitySummaryData`

**依赖：无**

---

### 6. src/types/index.ts — 统一出口
**预计行数：约 20 行**

内容：
- 使用 `export * from './xxx'` 重新导出所有 5 个模块
- 保留类型守卫函数 `isRecord` 和 `isSSECandidateData`

---

## 依赖关系图
```
scoring.ts (无依赖)
    ↑
candidate.ts (依赖 scoring)
    ↑
api.ts (依赖 candidate)

config.ts (无依赖)
ui.ts (无依赖)

index.ts (统一 re-export 所有模块 + 类型守卫)
```

## 验证步骤
1. 创建 5 个新类型文件
2. 更新 index.ts
3. 运行 `npx tsc --noEmit` 验证类型正确性
4. 确认每个文件行数 ≤ 300
5. 确认现有 import 路径无需修改
