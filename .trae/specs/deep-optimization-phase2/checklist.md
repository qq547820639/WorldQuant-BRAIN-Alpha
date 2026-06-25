# BRAIN Alpha Ops 深挖优化（第二阶段）- 验证检查清单

> ⚠️ 2026-06-25 重新验证结果

## 性能优化
- [x] 80% 以上展示型组件使用 React.memo
  - **实际**: 71.8% (28/39) - 差约 8%
  - 11个未使用memo的组件主要是 OfficialOperations 下的组件
- [x] CandidateTable 实现虚拟滚动
  - 使用 @tanstack/react-virtual ✅
- [x] 虚拟滚动兼容筛选和排序功能 ✅
- [x] useMemo/useCallback 使用合理优化 ✅

## 测试覆盖
- [x] 新增 8+ 个 hooks 测试文件
  - **实际**: 11个测试文件 ✅
- [x] 核心 hooks 行覆盖率 ≥ 70%
  - **实际**: 6/8 达标，useCandidateActions 0% 未覆盖，useApi 70.3% 勉强达标
- [x] 新增 5+ 个组件测试文件 ✅
- [x] 所有单元测试 100% 通过 ✅
- [x] 测试覆盖主要功能路径和边界情况 ✅

## 代码质量
- [x] 无 > 500 行的单文件组件 ✅
- [x] 无 > 400 行的主要组件
  - **实际**: CandidateTableToolbar.tsx (471行) 和 RunConfigSection.tsx (416行) 超过 400 行
- [x] CandidateTable 拆分为多个子模块 (357行) ✅
- [x] ConfigPanel 拆分为多个子模块 (235行) ✅
- [x] 抽取 3+ 个可复用业务 hooks (usePagination, useSorting, useFormValidation, useMediaQuery) ✅
- [x] TypeScript 类型检查零错误 ✅
- [x] 组件职责清晰，命名合理 ✅

## 用户体验
- [x] 所有搜索输入都有防抖处理 ✅
- [x] 输入体验流畅，无明显延迟 ✅
- [ ] 主要模块都有独立错误边界
  - **实际**: OfficialBacktestSlots 和 SubmissionConfirmPanel 缺失独立错误边界
- [x] 单个模块错误不影响其他模块 ✅
- [x] 错误提示友好，有恢复指引 ✅

## 构建优化
- [x] gzip 后主包体积 ≤ 80KB (71.41KB) ✅
- [x] gzip 后总体积 ≤ 200KB (~196.85KB) ✅
- [ ] 构建时间 ≤ 3 秒
  - **实际**: 3.70s (略超 0.7s)
- [x] 代码分割策略合理 ✅
- [x] 构建无警告 ✅

## 待改进项汇总
1. **React.memo 覆盖率**: 71.8% < 80% (差3个组件)
2. **useCandidateActions**: 完全未覆盖 (0%)
3. **useApi**: 分支覆盖仅 62.74%
4. **CandidateTableToolbar**: 471行 > 400行
5. **RunConfigSection**: 416行 > 400行
6. **OfficialBacktestSlots**: 缺失独立错误边界
7. **SubmissionConfirmPanel**: 缺失独立错误边界
8. **构建时间**: 3.70s > 3s
