# BRAIN Alpha Ops 深挖优化（补充修复）- 验证检查清单

## React.memo 覆盖
- [x] 80% 以上展示型组件使用 React.memo
- [x] OfficialOperations/OverviewCard 使用 React.memo
- [x] OfficialOperations/ActionPanel 使用 React.memo
- [x] OfficialOperations/SummaryMetric 使用 React.memo
- [x] memo 包装后 TypeScript 类型正确

## 测试覆盖
- [x] useCandidateActions 行覆盖率 ≥ 70%
- [x] useCandidateActions 测试文件已创建
- [x] useApi 分支覆盖率 ≥ 70%
- [x] 所有单元测试 100% 通过
- [x] useCandidateActions 测试覆盖 buildCredentialOverrides
- [x] useCandidateActions 测试覆盖 SSE 事件处理

## 代码质量
- [x] CandidateTableToolbar.tsx ≤ 400 行
- [x] CandidateTableToolbar 拆分为多个子组件
- [x] RunConfigSection.tsx ≤ 400 行
- [x] RunConfigSection 拆分为多个子组件
- [x] FIELD_HELP 常量提取到独立模块
- [x] TypeScript 类型检查零错误
- [x] ESLint 无 error 级警告

## 错误边界
- [x] OfficialBacktestSlots 被 ErrorBoundary 包裹
- [x] SubmissionConfirmPanel 被 ErrorBoundary 包裹
- [x] 错误边界使用 section 级别
- [x] 错误提示文案友好且与其他模块一致

## 构建性能
- [x] 构建时间 ≤ 3 秒
- [x] gzip 后主包体积 ≤ 80KB
- [x] gzip 后总体积 ≤ 200KB
- [x] 构建无警告
- [x] 构建配置合理，不影响调试体验
