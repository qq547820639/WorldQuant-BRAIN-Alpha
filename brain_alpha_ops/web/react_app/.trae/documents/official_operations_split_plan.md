# OfficialOperationsPanel 组件拆分计划

## 背景

- **当前状态**: `OfficialOperationsPanel.tsx` 共 770 行，包含状态管理、业务逻辑和渲染代码
- **目标**: 将业务逻辑提取到 `useOfficialOperations` hook 中，主组件只保留渲染逻辑（≤ 300 行）
- **已有子组件**: `OfficialOperations/` 目录下已有 ActionButtons、MetricsDisplay、OperationsLog 等子组件
- **工具函数**: `OfficialOperations/utils.ts` 已有 1021 行工具函数，继续使用

## 拆分策略

### 1. 创建 useOfficialOperations hook

**文件位置**: `src/components/OfficialOperations/useOfficialOperations.ts`

**提取内容**:

#### 1.1 状态管理 (useState)
- `mode: OperationMode` - 当前操作模式
- `syncJobId: string` - 同步任务 ID
- `syncStatus: JobStatus | null` - 同步状态
- `syncRunning: boolean` - 是否正在同步
- `syncRange: SyncRange` - 同步范围
- `contextOnlyMode: boolean` - 是否仅上下文模式
- `stoppingSinceMs: number` - 停止开始时间
- `stoppingNowMs: number` - 停止当前时间
- `logs: OperationLogEntry[]` - 日志列表

#### 1.2 Refs (useRef)
- `syncPollInFlightRef` - 轮询是否进行中
- `activeSyncJobIdRef` - 当前活跃任务 ID
- `syncPollGenerationRef` - 轮询世代号
- `syncPollFailureCountRef` - 轮询失败计数
- `syncProgressMonitorRef` - 同步进度监控状态
- `syncRecoveryAttemptedRef` - 恢复是否已尝试
- `autoStartConsumedRef` - 自动启动是否已消耗
- `stopRetryStartedAtRef` - 停止重试开始时间

#### 1.3 API hooks
- `syncStartApi` - 启动同步 API
- `syncStatusApi` - 同步状态 API
- `syncCancelApi` - 取消同步 API
- `readinessApi` - 就绪检查 API
- `checkResultsApi` - 检查结果 API

#### 1.4 业务逻辑函数 (useCallback)
- `updateSyncJobId` - 更新同步任务 ID
- `appendLog` - 追加日志
- `resetSyncProgressMonitor` - 重置进度监控
- `inspectSyncProgressMonitor` - 检查进度监控（停滞检测）
- `applySyncRecoveryFailure` - 应用同步恢复失败
- `applyRecoveredSyncStatus` - 应用已恢复的同步状态
- `loadReadiness` - 加载就绪状态
- `loadChecks` - 加载检查结果
- `startOfficialContextRefresh` - 启动官方上下文刷新
- `startContextOnlyRefresh` - 仅启动上下文刷新
- `interruptOfficialContextRefresh` - 中断官方上下文刷新
- `pollSyncStatus` - 轮询同步状态
- `stopOfficialContextRefresh` - 停止官方上下文刷新

#### 1.5 Effects (useEffect)
- **恢复效果**: 组件挂载时恢复之前的同步状态
- **自动启动效果**: 处理 autoStart 属性
- **轮询效果**: 同步运行时定期轮询状态
- **停止计时效果**: 停止状态下更新计时器
- **停止重试效果**: 停止超时后自动重试停止请求

#### 1.6 派生状态计算
- `currentProgress` - 当前进度
- `currentError` - 当前错误
- `currentState` - 当前状态
- `readiness` - 就绪数据
- `checkRows` - 检查结果行
- `displaySyncStatus` - 显示用同步状态
- `syncOverview` - 同步概览
- `syncHistory` - 同步历史
- `syncHistoryError` - 同步历史错误
- `syncHistoryErrorTitle` - 同步历史错误标题
- `canRetryContext` - 是否可重试上下文
- `syncState` - 同步状态分类
- `displaySyncState` - 显示用同步状态分类
- `syncNeedsRetry` - 同步是否需要重试
- `refreshPanelTitle` - 刷新面板标题
- `refreshPanelDescription` - 刷新面板描述
- `stoppingElapsedSeconds` - 停止已用秒数

### 2. 精简 OfficialOperationsPanel.tsx 主组件

**保留内容**:
- Props 接口定义
- CheckResultsResponse 内部接口（或移至 hook 中）
- 调用 `useOfficialOperations` hook
- JSX 渲染逻辑

**目标行数**: ≤ 300 行

### 3. 更新 barrel export

在 `OfficialOperations/index.ts` 中导出 `useOfficialOperations` hook。

## Hook 接口设计

```typescript
interface UseOfficialOperationsInput {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
  credentials?: BrainCredentials;
  autoStart?: boolean;
  connectionReady?: boolean;
  officialContextCache?: OfficialContextCache;
  cloudAlphaCache?: CloudAlphaCache;
  onAutoStartConsumed?: () => void;
  onSyncCompleted?: () => void;
  onReconnectRequested?: () => void;
  onNavigateToCandidates?: () => void;
}

interface UseOfficialOperationsResult {
  // 状态
  mode: OperationMode;
  syncJobId: string;
  syncStatus: JobStatus | null;
  syncRunning: boolean;
  syncRange: SyncRange;
  contextOnlyMode: boolean;
  stoppingSinceMs: number;
  stoppingNowMs: number;
  logs: OperationLogEntry[];
  setLogs: React.Dispatch<React.SetStateAction<OperationLogEntry[]>>;
  
  // API 状态
  syncStartLoading: boolean;
  syncStatusLoading: boolean;
  readinessLoading: boolean;
  checkResultsLoading: boolean;
  readiness: SubmitReadinessResponse | null;
  checkRows: Array<Record<string, unknown>>;
  
  // 派生状态
  currentProgress: UnifiedProgress;
  currentError: string | null;
  currentState: string;
  displaySyncStatus: JobStatus | null;
  syncOverview: ReturnType<typeof syncDataOverview>;
  syncHistory: Array<Record<string, unknown>>;
  syncHistoryError: string;
  syncHistoryErrorTitle: string;
  canRetryContext: boolean;
  syncNeedsRetry: boolean;
  refreshPanelTitle: string;
  refreshPanelDescription: string;
  stoppingElapsedSeconds: number;
  
  // 操作函数
  setSyncRange: (range: SyncRange) => void;
  startOfficialContextRefresh: (options?: { contextOnly?: boolean }) => Promise<void>;
  startContextOnlyRefresh: () => void;
  stopOfficialContextRefresh: () => Promise<void>;
  loadReadiness: () => Promise<void>;
  loadChecks: () => Promise<void>;
  setLogs: React.Dispatch<React.SetStateAction<OperationLogEntry[]>>;
}
```

## 文件改动清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/components/OfficialOperations/useOfficialOperations.ts` | 新建 | 核心业务逻辑 hook |
| `src/components/OfficialOperationsPanel.tsx` | 修改 | 精简为纯渲染组件 |
| `src/components/OfficialOperations/index.ts` | 修改 | 导出新 hook |

## 验证步骤

1. **TypeScript 检查**: `cd /workspace/brain_alpha_ops/web/react_app && npx tsc --noEmit`
2. **测试运行**: `cd /workspace/brain_alpha_ops/web/react_app && npx vitest run`
3. **行数验证**: 主组件 ≤ 300 行

## 注意事项

- 保持所有现有功能完全兼容
- 保持 Props 接口不变
- 保持所有外部行为不变
- 使用 utils.ts 中已有的工具函数
- 遵循项目现有的代码风格和命名约定
