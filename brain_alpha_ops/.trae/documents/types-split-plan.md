# TypeScript 类型文件拆分计划

## 概述
将 `src/types/index.ts`（1223 行）拆分为 6 个模块文件，每个文件 ≤ 300 行，保持 100% 向后兼容。

## 文件拆分方案

### 1. src/types/api.ts (~280 行)
**包含类型：**
- ApiResponse, ApiUserError
- JobStatus, SyncHistoryItem, JobProgress
- ProgressLifecycle, UnifiedProgress
- SSEEvent, SSECandidateEventData
- ProductionResultSummary
- TrendApiResponse

**跨模块导入：**
- 从 `./cloud` 导入 `OfficialContextCache`（JobStatus 引用）

### 2. src/types/candidate.ts (~260 行)
**包含类型：**
- Candidate, AlphaLifecycleRecord, AlphaLifecycleTrace, AlphaLifecycleHistoryResponse
- CandidateExtraFields, CandidateOptimizationExplanation, CandidateScientificAudit
- CandidateProductionDecision, CandidateDecisionEvidence
- LocalQuality, AlphaOutputConfig, AlphaQualityReason, QualityDiagnosis
- OfficialMetrics, QualityGate, GateCheck
- CandidateCheckResult, CandidateWorkflowPlan
- CandidateListMeta, CandidateQueueView

**跨模块导入：**
- 从 `./scoring` 导入 `Scorecard, ScoreAttribution, ScoreLayerDetail, ScoreConfidence, HardGateResult, AttributionNode, FailureItem`

### 3. src/types/scoring.ts (~220 行)
**包含类型：**
- Scorecard, ScoreLayerDetail, ScoreConfidence, HardGateResult, ScoreAttribution
- ScoringResult, ScoreLayer, ScoreLayerItem
- OfficialGateResult, OfficialGateCheckItem
- AttributionNode, ScoringAttributionResponse, FailureItem

**跨模块导入：** 无

### 4. src/types/config.ts (~70 行)
**包含类型：**
- RunConfig, BrainSettings, BudgetConfig, ThresholdConfig, ScoringConfig
- BrainCredentials

**跨模块导入：** 无

### 5. src/types/cloud.ts (~180 行)
**包含类型：**
- OfficialContextCache, CloudAlphaCache
- PhaseData, CloudAlphaSummary, CloudAlphaWithMetrics
- BacktestSlot, BacktestSlotsResponse, BacktestStatusBoard, BacktestQueueSummary
- SubmitReadinessResponse, SubmitReadinessCandidate, SubmitReadinessFinding, ReadinessReasonCount
- CloudAlpha, ResearchMemorySummary, FamilyStat, FieldStat, OperatorStat, FailurePattern

**跨模块导入：**
- 从 `./candidate` 导入 `OfficialMetrics, QualityGate`

### 6. src/types/ui.ts (~130 行)
**包含类型：**
- TabId, Toast
- PhaseId, PhaseStatus, PhaseGroup, PhaseNavItem, PhaseState, StepGuideItem
- CardViewId, PhaseApiStatus
- LifecycleMetric, LifecycleMetricProps, LifecycleReplayPanelProps
- QualitySummaryData

**跨模块导入：** 无

### 7. src/types/index.ts (更新后 ~30 行)
**内容：**
- 使用 `export * from` 重新导出所有 6 个模块
- 保留类型守卫函数 `isRecord` 和 `isSSECandidateData`
- 确保所有现有 import 路径不变

## 依赖关系图（无循环依赖）
```
api.ts → cloud.ts → candidate.ts → scoring.ts
              ↘ config.ts
              ↘ ui.ts
```

## 验证步骤
1. 创建所有 6 个新模块文件
2. 更新 index.ts
3. 运行 `npx tsc --noEmit` 验证类型正确性
4. 检查每个文件行数 ≤ 300

## 向后兼容性保证
- 所有类型仍可通过 `@/types` 或 `../types` 路径导入
- index.ts 作为统一出口，使用 `export *` 重新导出
- 类型守卫函数保留在 index.ts 中
