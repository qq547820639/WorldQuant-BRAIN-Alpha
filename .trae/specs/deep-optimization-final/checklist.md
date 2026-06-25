# BRAIN Alpha Ops 深挖优化（最终阶段）- 验证清单

## 代码质量
- [ ] ESLint 检查：`npx eslint src` 无 error 级错误
- [ ] Prettier 检查：`npx prettier --check src` 全部通过
- [ ] 所有文件代码风格统一

## TypeScript
- [ ] `npx tsc --noEmit` 零类型错误
- [ ] 无 baseUrl 弃用警告
- [ ] 路径别名正常工作

## 大型模块拆分
- [ ] OfficialOperations/utils.ts 已拆分，单文件 ≤ 500 行
- [ ] useOfficialOperations.ts 已拆分，单文件 ≤ 400 行
- [ ] CandidateTableUtils.ts 已拆分，单文件 ≤ 500 行
- [ ] 所有组件文件 ≤ 400 行
- [ ] 所有 hooks 文件 ≤ 400 行
- [ ] 向后兼容：所有现有导入路径仍然有效

## 构建性能
- [ ] `npm run build` 构建时间 ≤ 3 秒
- [ ] gzip 后主包体积 ≤ 80KB
- [ ] gzip 后总体积 ≤ 200KB
- [ ] 构建产物完整无缺失

## 测试
- [ ] 前端单元测试：`npx vitest run` 100% 通过（0 失败）
- [ ] 快照测试全部通过
- [ ] 集成测试全部通过
- [ ] hooks 测试全部通过
- [ ] 组件测试全部通过

## 功能验证
- [ ] 应用可以正常启动
- [ ] 主要页面可以正常渲染
- [ ] 核心交互功能正常

## 提交
- [ ] 所有变更已提交
- [ ] 已成功推送到 origin/main
- [ ] git status 显示工作区干净
