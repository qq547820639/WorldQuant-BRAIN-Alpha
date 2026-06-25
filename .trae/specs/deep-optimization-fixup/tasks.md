# BRAIN Alpha Ops 深挖优化（补充修复）- 实施计划

## [x] Task 1: React.memo 覆盖补全
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 为 OfficialOperations 下的展示型组件添加 React.memo 包装
  - 重点组件：OverviewCard、ActionPanel、SummaryMetric、BlockerList、OperationLog、OperationMetric、SyncHistoryList
  - 确保 props 比较正确，避免误判
  - 检查 ProgressFeedback 下的展示组件是否需要添加 memo
- **Acceptance Criteria Addressed**: AC-1
- **Test Requirements**:
  - `programmatic` TR-1.1: 展示型组件 memo 覆盖率达到 80% 以上
  - `programmatic` TR-1.2: TypeScript 类型检查零错误
  - `human-judgement` TR-1.3: 代码 review 确认 memo 使用合理
- **Notes**: 优先处理纯展示型组件，包含复杂逻辑的容器组件不需要 memo

## [x] Task 2: useCandidateActions 单元测试
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 为 useCandidateActions Hook 添加完整的单元测试
  - 测试 buildCredentialOverrides 方法
  - 测试 generateCandidates、startSimulation、startOptimization、startSingleCheck、startBatchCheck 方法调用
  - 测试 SSE 事件处理（handleTaskEvent、handleSimEvent、handleOptimizationEvent、handleCheckEvent）
  - Mock 子 hooks（useCandidateGeneration、useCandidateSimulation、useCandidateOptimization、useCandidateCheck、useCandidateSSEHandlers）
- **Acceptance Criteria Addressed**: AC-2, AC-9
- **Test Requirements**:
  - `programmatic` TR-2.1: useCandidateActions 行覆盖率 ≥ 70%
  - `programmatic` TR-2.2: 所有测试 100% 通过
  - `programmatic` TR-2.3: 新增测试文件 ≥ 1 个
- **Notes**: 参考现有 hooks 测试模式，使用 @testing-library/react-hooks

## [x] Task 3: useApi 测试增强
- **Priority**: medium
- **Depends On**: None
- **Description**:
  - 补充 useApi 的分支覆盖测试
  - 覆盖错误处理路径（网络错误、超时、非200响应）
  - 覆盖 loading 状态转换
  - 覆盖 abort/取消请求场景
  - 覆盖 reset 方法
- **Acceptance Criteria Addressed**: AC-3, AC-9
- **Test Requirements**:
  - `programmatic` TR-3.1: useApi 分支覆盖率 ≥ 70%
  - `programmatic` TR-3.2: useApi 行覆盖率保持 ≥ 70%
  - `programmatic` TR-3.3: 所有测试 100% 通过
- **Notes**: 在现有 useApi.test.tsx 基础上补充测试用例

## [x] Task 4: CandidateTableToolbar 拆分
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 将 CandidateTableToolbar.tsx (471行) 拆分为更小的组件
  - 拆分方案：
    - ToolbarHeader: 标题、统计信息、批量选择栏
    - ProductionControls: 生产控制按钮区域
    - QualitySummaryBar: 质量摘要 KPI 卡片区域
    - FilterToolbar: 过滤输入、刷新、收藏过滤、导出
  - 保持现有 Props API 不变
  - 提取可复用逻辑到自定义 hooks
- **Acceptance Criteria Addressed**: AC-4, AC-10
- **Test Requirements**:
  - `programmatic` TR-4.1: 拆分后无 > 400 行的单文件组件
  - `programmatic` TR-4.2: 所有现有测试通过
  - `programmatic` TR-4.3: TypeScript 类型检查零错误
  - `human-judgement` TR-4.4: 组件职责清晰，命名合理
- **Notes**: 渐进式拆分，每步都要确保功能正常

## [x] Task 5: RunConfigSection 拆分
- **Priority**: medium
- **Depends On**: None
- **Description**:
  - 将 RunConfigSection.tsx (416行) 拆分为更小的组件
  - 拆分方案：
    - BasicConfigGroup: 基础配置（区域、股票池、延迟等）
    - ScoringConfigGroup: 评分配置（权重、市场状态等）
    - AdvancedConfigGroup: 高级配置（中性化、数据净化等）
  - 提取 FIELD_HELP 常量到独立的 fieldHelp.ts 文件
  - 保持现有 Props API 不变
- **Acceptance Criteria Addressed**: AC-5, AC-10
- **Test Requirements**:
  - `programmatic` TR-5.1: 拆分后无 > 400 行的单文件组件
  - `programmatic` TR-5.2: 所有现有测试通过
  - `programmatic` TR-5.3: TypeScript 类型检查零错误
  - `human-judgement` TR-5.4: 组件职责清晰，命名合理
- **Notes**: 确保配置状态管理逻辑清晰

## [x] Task 6: 错误边界补全
- **Priority**: medium
- **Depends On**: None
- **Description**:
  - 为 OfficialBacktestSlots 添加独立错误边界
  - 为 SubmissionConfirmPanel 添加独立错误边界
  - 保持与其他模块一致的错误提示风格
  - 错误边界使用 section 级别
  - 配置合适的标题和描述文案
- **Acceptance Criteria Addressed**: AC-6, AC-10
- **Test Requirements**:
  - `programmatic` TR-6.1: OfficialBacktestSlots 被 ErrorBoundary 包裹
  - `programmatic` TR-6.2: SubmissionConfirmPanel 被 ErrorBoundary 包裹
  - `programmatic` TR-6.3: TypeScript 类型检查零错误
  - `human-judgement` TR-6.4: 错误提示文案友好且一致
- **Notes**: 参考 renderView.tsx 中其他模块的错误边界实现方式

## [x] Task 7: 构建时间优化
- **Priority**: low
- **Depends On**: None
- **Description**:
  - 分析构建瓶颈，优化 Vite 配置
  - 检查是否可以通过调整依赖拆分减少构建时间
  - 确认 sourcemap 配置是否可以优化
  - 确保构建体积不增加
- **Acceptance Criteria Addressed**: AC-7, AC-8
- **Test Requirements**:
  - `programmatic` TR-7.1: 构建时间 ≤ 3 秒
  - `programmatic` TR-7.2: gzip 后主包 ≤ 80KB
  - `programmatic` TR-7.3: gzip 后总体积 ≤ 200KB
  - `human-judgement` TR-7.4: 构建配置合理，不影响调试体验
- **Notes**: 优先使用配置优化，不引入新的构建工具

# Task Dependencies
- Task 1, 2, 3, 4, 5, 6, 7 可并行执行（互不依赖）
