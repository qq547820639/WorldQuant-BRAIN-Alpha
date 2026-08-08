# Tasks

> 目标：`npm run test`（vitest run）全量通过、0 失败、0 错误、不挂起。约束：不关 strict、不削弱 ErrorBoundary "boom" 断言、最小低风险改动、快照仅当渲染确属正确才更新、不改 vite.config.ts 测试配置。

## [ ] Task 1: 修复候选流程无限渲染循环（挂起根因）
**Depends On**: None（最高优先级，先做）
- 复现 `tests/integration/candidate-flow.test.tsx` 分页测试的 "Maximum update depth exceeded"。
- 根因：`src/hooks/useCandidateTableData.ts` 中 `useEffect(() => { void loadCandidates(); }, [loadCandidates])`，而 `loadCandidates` 依赖 `globalCandidatesData`/`refreshAll`，每次 fetch 后其身份变化导致 effect 反复重跑、无限重取。
- 修复：稳定数据加载 effect 依赖（如仅在挂载/关键参数变化时触发、或将 `globalCandidatesData` 移出回调依赖、或加数据已加载守卫），消除无限循环。
- 验证：`npx vitest run tests/integration/candidate-flow.test.tsx` 通过且无 "Maximum update depth exceeded" 风暴。

## [ ] Task 2: 补齐缺失 hooks（useLoadingState / useThrottle / useMemoCompare / useNetworkError）
**Depends On**: None
- 依据 `tests/hooks/useLoadingState.test.ts`、`useThrottle.test.ts`、`useMemoCompare.test.ts`、`useNetworkError.test.ts` 的调用契约实现：
  - `src/hooks/useLoadingState.ts`：`{ isLoading, error, hasError, setLoading, setError, runWithLoading, reset }`，支持 `minDuration`（默认 300）、`initialLoading`。
  - `src/hooks/useThrottle.ts`：`useThrottle(value, delay=300)`、`useThrottledCallback(cb, delay=300)`，含卸载清理。
  - `src/hooks/useMemoCompare.ts`：`useMemoCompare(factory, deps, compare)`、`useDeepMemo(factory, deps)`。
  - `src/hooks/useNetworkError.ts`：监听 `online`/`offline`，`{ isOnline, isReconnecting, retryCount, lastError, retry, reset }`，`enableAutoRetry` 选项。
- 验证：4 个 hook 测试文件全部通过，`npm run typecheck` 无错误。

## [ ] Task 3: 补齐缺失组件（A11y/* 与 SubmissionPanel）
**Depends On**: None
- 依据 `tests/components/A11y/{FocusTrap,LiveRegion,SkipLink,VisuallyHidden}.test.tsx` 与 `tests/components.test.tsx` 中 `SubmissionPanel` 的用法实现：
  - `src/components/A11y/SkipLink.tsx`、`LiveRegion.tsx`、`VisuallyHidden.tsx`、`FocusTrap.tsx`。
  - `src/components/SubmissionPanel.tsx`（配合 `notify` prop 等）。
- 可参照 `tests/components.test.tsx` 中 `SubmissionPanel` describe 块的期望。
- 验证：相关测试文件通过，`npm run typecheck` 无错误。

## [ ] Task 4: 修复组件断言失败（ScoringPanel / PageLoader / ButtonLoader / RetryButton）
**Depends On**: None
- `ScoringPanel`：`/alpha_test_001/` 重复文本 → 使测试查询唯一或在组件内消除重复，保持展示正确。
- `PageLoader` / `ButtonLoader`：重复 `role="status"` → 移除重复 role，保留可访问性语义。
- `RetryButton`：可访问名 `重试中...` 无法匹配 → 调整实现或测试查询，保留 aria-busy 与 loading 行为。
- 相关测试：`tests/components/ScoringPanel.test.tsx`、`tests/components/LoadingState/PageLoader.test.tsx`、`tests/components/ErrorState/RetryButton.test.tsx` 等。
- 验证：相关组件测试通过。

## [ ] Task 5: 修复 Hook 失败（useSorting 解构 / useGlobalData timer）
**Depends On**: None
- `useSorting`：`options` 为 undefined 时解构崩溃 → 提供默认值或修正测试调用。
- `useGlobalData`：timer / global mock 相关失败 → 修正测试或实现以通过。
- 相关测试：`tests/hooks/useSorting.test.ts`、`tests/hooks/useGlobalData.test.tsx`。
- 验证：相关 hook 测试通过。

## [ ] Task 6: 修复 ErrorBoundary 测试失败
**Depends On**: None
- `ErrorBoundary.test.tsx` 找不到预期错误文本：`ActionableError` 对错误分类后展示标准化消息 → 让测试断言与 `ActionableError` 实际输出对齐，或按渲染实际展示正确更新期望；**不得削弱 "boom" 断言**。
- 验证：`tests/ErrorBoundary.test.tsx`（及 `src/__tests__/ErrorBoundary.test.tsx` 若存在）通过。

## [ ] Task 7: 修复快照失败
**Depends On**: Task 4/5 之后
- dashboard、ScoringPanel、过期快照：仅当渲染输出确属正确时更新快照；否则先修根因。
- 验证：`tests/__snapshots__/*.snap` 对应测试通过。

## [ ] Task 8: 修复 ConfigPanel 重复导入解析错误（若仍存在）
**Depends On**: None
- `tests/components/ConfigPanel.test.tsx` 等文件若存在 `describe/expect/it` 重复导入 → 合并为单一导入。
- 验证：相关测试可正常收集。

## [ ] Task 9: 全量验证
**Depends On**: Task 1-8
- 运行 `timeout 300 npx vitest run --reporter=dot 2>&1 | tail`，确认完整跑完、0 failures、0 errors、无 "Maximum update depth exceeded" 风暴。
- 运行 `npx vitest run`（无 timeout gmnd）确认不再挂起。
- 运行 `npm run typecheck` 确认无类型错误。

# Task Dependencies
- [Task 1] 独立，先行（消除挂起）。
- [Task 2]、[Task 3]、[Task 4]、[Task 5]、[Task 6]、[Task 8] 相互独立，可并行。
- [Task 7] 依赖 [Task 4]/[Task 5] 的根因修复。
- [Task 9] 依赖全部 [Task 1-8]。