# BRAIN Alpha Ops 深挖优化（第三阶段）- 实施计划

## 仓库调研结论

### 当前状态（第二阶段完成后）

**已完成的优化：**
- React.memo 全面覆盖（22 个组件）
- CandidateTable 虚拟滚动（桌面端 + 移动端）
- 核心 Hooks 测试（56 个测试用例）
- CandidateTable 拆分：784 行 → 357 行
- ConfigPanel 拆分：611 行 → 235 行
- 防抖/节流全面覆盖（11 个防抖处理）
- 核心组件测试增强（新增 66 个测试用例）
- 可复用逻辑抽取（usePagination, useSorting, useFormValidation, useMediaQuery）
- 错误边界粒度优化（7 个模块独立错误边界）
- 构建和体积优化（主包 gzip 69KB，构建 2.64s）

### 待优化问题（第三阶段重点）

**1. 仍存在的大型组件（> 400 行）：**
- [OfficialOperationsPanel.tsx](file:///workspace/brain_alpha_ops/web/react_app/src/components/OfficialOperationsPanel.tsx) - 770 行
- [useCandidateActions.ts](file:///workspace/brain_alpha_ops/web/react_app/src/hooks/useCandidateActions.ts) - 540 行
- [App.tsx](file:///workspace/brain_alpha_ops/web/react_app/src/App.tsx) - 510 行
- [Dashboard.tsx](file:///workspace/brain_alpha_ops/web/react_app/src/components/Dashboard.tsx) - 493 行
- [CandidateTableToolbar.tsx](file:///workspace/brain_alpha_ops/web/react_app/src/components/CandidateTableToolbar.tsx) - 471 行
- [SubmissionGates.tsx](file:///workspace/brain_alpha_ops/web/react_app/src/components/SubmissionGates.tsx) - 443 行
- [ProgressFeedback.tsx](file:///workspace/brain_alpha_ops/web/react_app/src/components/ProgressFeedback.tsx) - 443 行
- [JobMonitor.tsx](file:///workspace/brain_alpha_ops/web/react_app/src/components/JobMonitor.tsx) - 433 行
- [useJobState.ts](file:///workspace/brain_alpha_ops/web/react_app/src/hooks/useJobState.ts) - 401 行

**2. 类型定义臃肿：**
- [types/index.ts](file:///workspace/brain_alpha_ops/web/react_app/src/types/index.ts) - 1223 行，需要模块化拆分

**3. 代码质量工具不完善：**
- 已有 ESLint 配置，但缺少 Prettier 配置
- 缺少 pre-commit hooks 和 CI 集成

**4. 测试覆盖仍有提升空间：**
- 大型业务组件（OfficialOperationsPanel、Dashboard、JobMonitor 等）缺少测试
- 缺少集成测试
- 缺少 E2E 测试基础

**5. 可访问性需要加强：**
- 键盘导航和 ARIA 标签需要全面审查

## 待编辑的文件和模块

### 新创建的文件
- `src/types/candidate.ts` - 候选相关类型
- `src/types/job.ts` - 任务相关类型
- `src/types/config.ts` - 配置相关类型
- `src/types/api.ts` - API 相关类型
- `src/hooks/useOfficialOperations.ts` - 官方操作逻辑
- `src/hooks/useAppState.ts` - App 状态管理
- `src/components/OfficialOperationsPanel/Header.tsx`
- `src/components/OfficialOperationsPanel/Body.tsx`
- `src/components/Dashboard/DashboardOverview.tsx`
- `src/components/Dashboard/DashboardCharts.tsx`
- `src/components/JobMonitor/JobMonitorHeader.tsx`
- `src/components/JobMonitor/JobMonitorContent.tsx`
- `tests/integration/candidate-flow.test.tsx`
- `.prettierrc`
- `.prettierignore`

### 需要修改的文件
- `src/types/index.ts` - 重新导出拆分后的类型
- `src/components/OfficialOperationsPanel.tsx` - 拆分精简
- `src/App.tsx` - 抽取状态逻辑
- `src/components/Dashboard.tsx` - 拆分子组件
- `src/components/JobMonitor.tsx` - 拆分子组件
- `src/hooks/useCandidateActions.ts` - 拆分逻辑
- `src/hooks/useJobState.ts` - 拆分逻辑
- `.eslintrc.js` - 完善规则
- `vite.config.ts` - 添加测试配置
- `package.json` - 添加脚本命令

## 修改步骤

### Task 1: 类型定义模块化拆分
- 将 1223 行的 `types/index.ts` 拆分为多个模块
- 按领域划分：candidate、job、config、api、ui 等
- 保持 `index.ts` 作为统一出口，确保向后兼容
- 目标：单个类型文件 ≤ 300 行

### Task 2: OfficialOperationsPanel 拆分
- 将 770 行的 OfficialOperationsPanel 拆分为子组件
- 抽取 `useOfficialOperations` hook 管理业务逻辑
- 拆分为 Header、Body、ActionPanel、SyncHistory 等子组件
- 目标：主组件 ≤ 300 行

### Task 3: App.tsx 状态逻辑抽取
- 将 510 行的 App.tsx 中的状态管理逻辑抽取为 hooks
- 创建 `useAppState` hook 统一管理应用级状态
- 抽取视图切换、连接状态、阶段管理等逻辑
- 目标：App.tsx ≤ 350 行

### Task 4: Dashboard 组件拆分
- 将 493 行的 Dashboard 拆分为子组件
- 拆分为 DashboardOverview、DashboardCharts、DashboardReports 等
- 抽取 Dashboard 数据处理逻辑为 hook
- 目标：主组件 ≤ 300 行

### Task 5: 大型 Hooks 拆分
- 拆分 useCandidateActions（540 行）为多个专项 hooks
- 拆分 useJobState（401 行）为更细粒度的 hooks
- 每个 hook 职责单一，便于测试和复用
- 目标：单个 hook ≤ 300 行

### Task 6: JobMonitor 和 ProgressFeedback 拆分
- 拆分 JobMonitor（433 行）为子组件
- 拆分 ProgressFeedback（443 行）为子组件
- 抽取进度计算逻辑为工具函数
- 目标：主组件 ≤ 300 行

### Task 7: 代码质量工具完善
- 添加 Prettier 配置和忽略文件
- 完善 ESLint 规则
- 添加 lint-staged 和 husky（可选）
- 添加 `lint`、`format`、`format:check` 脚本命令
- 运行 ESLint 检查并修复问题

### Task 8: 集成测试增强
- 添加候选管理流程集成测试
- 添加配置保存流程集成测试
- 添加官方操作流程集成测试
- 使用 Testing Library 的集成测试模式
- 目标：新增 3+ 个集成测试文件

### Task 9: 可访问性全面优化
- 全面审查 ARIA 标签使用
- 确保所有交互元素可键盘操作
- 添加焦点管理和焦点可见性
- 优化屏幕阅读器体验
- 验证颜色对比度

### Task 10: 构建和开发体验优化
- 优化 Vite 开发服务器配置
- 添加环境变量类型定义
- 优化 HMR 热更新速度
- 添加 ESLint 插件到 Vite
- 进一步优化产物体积

## 潜在依赖和注意事项

1. **向后兼容**：所有拆分和重构必须保持现有 API 不变
2. **TypeScript 类型**：确保所有拆分后的类型正确导出
3. **测试更新**：重构后需要更新相关测试文件
4. **依赖顺序**：类型拆分必须先完成，后续任务依赖新的类型结构
5. **性能影响**：拆分不应引入额外的运行时开销

## 风险处理

1. **功能回归风险**：每个任务完成后运行所有测试，确保功能正常
2. **类型错误风险**：每次重构后运行 `tsc --noEmit` 验证
3. **性能退化风险**：构建优化前后对比体积和构建时间
4. **测试失败风险**：重构前确保有足够的测试覆盖，重构后及时更新测试

## 验收标准

- 无 > 400 行的组件或 hooks
- 类型定义模块化，单个类型文件 ≤ 300 行
- TypeScript 零错误
- ESLint 无 error 级警告
- Prettier 格式化统一
- 新增 3+ 个集成测试文件
- 所有测试 100% 通过
- 可访问性符合 WCAG 2.1 AA 标准
- 构建体积和时间保持在第二阶段水平或更优
