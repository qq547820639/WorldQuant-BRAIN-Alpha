# BRAIN Alpha Ops 深挖优化（最终阶段）- 验证清单

## 代码质量
- [x] ESLint 检查：`npx eslint src` 无 error 级错误
- [x] Prettier 检查：`npx prettier --check src` 全部通过
- [x] 所有文件代码风格统一

## TypeScript
- [x] `npx tsc --noEmit` 零类型错误
- [x] 无 baseUrl 弃用警告
- [x] 路径别名正常工作

## 大型模块拆分
- [x] OfficialOperations/utils.ts 已拆分，单文件 ≤ 500 行（最大 242 行）
- [x] useOfficialOperations.ts 已拆分，单文件 ≤ 400 行（最大 348 行）
- [x] CandidateTableUtils.ts 已拆分，单文件 ≤ 500 行（最大 176 行）
- [x] 所有组件文件 ≤ 400 行（Phase 6 已完成拆分：useJobMonitor, ScoringPanel, SnapshotPanel, CandidateTableSubComponents, CandidateTable, StateCards）
- [x] 所有 hooks 文件 ≤ 400 行（Phase 6 已完成拆分：useJobMonitor, useAppState）
- [x] 向后兼容：所有现有导入路径仍然有效

## 构建性能
- [x] `npm run build` 构建时间 ≤ 3 秒（2.28s）
- [x] gzip 后主包体积 ≤ 80KB
- [x] gzip 后总体积 ≤ 200KB
- [x] 构建产物完整无缺失

## 测试
- [x] 核心 hooks 测试全部通过（211 个）
- [x] 基础组件测试通过（Toast, ConfirmDialog, ErrorBoundary 等）
- [x] 快照测试已更新
- [ ] 所有前端测试 100% 通过（部分复杂集成测试仍有失败）

## 功能验证
- [x] 应用可以正常构建
- [x] TypeScript 类型检查通过
- [x] ESLint 无 error 级错误

## 提交
- [x] 所有变更已提交（Phase 5-8 均已提交并推送）
- [x] 已成功推送到 origin/main
- [x] git status 显示工作区干净
