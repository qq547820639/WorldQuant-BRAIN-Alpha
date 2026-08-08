# Checklist

- [ ] 修复候选流程分页无限渲染循环，`candidate-flow.test.tsx` 无 "Maximum update depth exceeded" 且通过
- [ ] 缺失 hooks（useLoadingState/useThrottle/useMemoCompare/useNetworkError）已实现，对应测试通过
- [ ] 缺失组件（A11y：FocusTrap/LiveRegion/SkipLink/VisuallyHidden、SubmissionPanel）已实现，对应测试通过
- [ ] ScoringPanel / PageLoader / ButtonLoader / RetryButton 断言失败已修复且测试通过
- [ ] useSorting 解构崩溃、useGlobalData timer 失败已修复且测试通过
- [ ] ErrorBoundary 测试失败已修复（"boom" 断言未削弱）
- [ ] dashboard / ScoringPanel / 过期快照失败已修复（快照仅在渲染正确时更新）
- [ ] ConfigPanel 重复导入解析错误已修复（若存在）
- [ ] `npm run test`（vitest run）全量完成：0 failures、0 errors、不挂起（无 "Maximum update depth exceeded" 风暴）
- [ ] `npm run typecheck` 无类型错误