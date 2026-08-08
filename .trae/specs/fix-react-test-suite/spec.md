# 修复 React 前端测试套件（vitest run 全绿）Spec

## Why
`npm run test`（vitest run）当前存在**测试失败**与**测试挂起/无限渲染循环**，导致无法判定项目质量。目标：在 `npm run test` 下**0 失败、0 错误、不挂起**完整跑通。

## What Changes
- 修复 `tests/integration/candidate-flow.test.tsx` 分页测试触发的**无限渲染循环**（根因：`useCandidateTableData` 的 `loadCandidates` effect 依赖中 `globalCandidatesData` 在每次 fetch 后变化，导致 effect 反复重跑、无限重取）。
- 补齐缺失的源模块（测试引用了但 `src/` 中不存在）：
  - `src/hooks/useLoadingState.ts`、`src/hooks/useThrottle.ts`、`src/hooks/useMemoCompare.ts`、`src/hooks/useNetworkError.ts`
  - `src/components/A11y/{FocusTrap,LiveRegion,SkipLink,VisuallyHidden}`、`src/components/SubmissionPanel.tsx`
- 修复组件/Hook 断言失败：`ScoringPanel`（重复文本）、`PageLoader`/`ButtonLoader`（重复 `role="status"`）、`RetryButton`（可访问名）、`useSorting`（`options` undefined 解构）、`useGlobalData`（timer）、`ErrorBoundary`（错误消息分类后与断言不匹配）。
- 修复快照失败（dashboard、ScoringPanel、过期快照）。
- 修复 `tests/components/ConfigPanel.test.tsx` 重复导入解析错误（若仍存在）。
- 确保确定性清理（`setup.ts` mock 不泄漏全局状态）。

## Impact
- Affected specs: 前端测试质量、组件可访问性、Hook 契约
- Affected code:
  - `src/hooks/useCandidateTableData.ts`（无限循环）
  - `src/hooks/useSorting.ts`、`src/components/ScoringPanel/ScoringPanel.tsx`、`src/components/LoadingState/*`、`src/components/ErrorState/RetryButton.tsx`、`src/components/ErrorBoundary.tsx`、`src/hooks/useGlobalData.ts`
  - 新增缺失模块（见 What Changes）
  - 相应测试文件与快照

## Constraints
- 不关闭 TypeScript strict 模式；不削弱 ErrorBoundary "boom" 断言。
- 采用最小、低风险的修复；快照仅在渲染输出确属正确时更新。
- 不修改 `vite.config.ts` 测试配置以排除测试或拉高 timeout。

## ADDED Requirements
### Requirement: 缺失源模块可按测试契约实现
系统 SHALL 提供 `useLoadingState`、`useThrottle`/`useThrottledCallback`、`useMemoCompare`/`useDeepMemo`、`useNetworkError` 及 A11y 组件（FocusTrap/LiveRegion/SkipLink/VisuallyHidden）与 `SubmissionPanel`，API 与对应测试文件的使用方式一致。

#### Scenario: 测试通过
- **WHEN** 运行 `npx vitest run`
- **THEN** 这些测试文件全部通过，无模块解析错误。

### Requirement: 测试套件确定性收敛
系统 SHALL 保证 `npm run test`（vitest run）在合理时间内结束，不因无限渲染/重取循环挂起。

#### Scenario: 全量跑通
- **WHEN** 运行 `timeout 300 npx vitest run`
- **THEN** 完成且 0 failures、0 errors，无 "Maximum update depth exceeded" 风暴。

## MODIFIED Requirements
### Requirement: 现有组件/Hook 测试断言对齐
修复 `ScoringPanel`、`PageLoader`/`ButtonLoader`、`RetryButton`、`useSorting`、`useGlobalData`、`ErrorBoundary`、ConfigPanel 的断言失败，确保对应测试通过，同时保持组件/Hook 原有行为与可访问性语义。

## REMOVED Requirements
### Requirement: 无限渲染循环
**Reason**: 导致测试挂起并刷屏，无法判定质量。
**Migration**: 通过稳定 `loadCandidates`/数据加载 effect 依赖修复，恢复正常数据获取行为。