# BRAIN Alpha Ops 深挖优化（第二阶段）- 实施计划

## [x] Task 1: React.memo 全面覆盖
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 对 20+ 个高频渲染的展示型组件添加 React.memo 包装
  - 优先处理列表项、卡片、状态指示器等频繁重渲染的组件
  - 确保 props 比较正确，避免误判导致的性能问题
- **Acceptance Criteria Addressed**: AC-2
- **Test Requirements**:
  - `programmatic` TR-1.1: 展示型组件 memo 覆盖率达到 80% 以上
  - `programmatic` TR-1.2: TypeScript 类型检查零错误
  - `human-judgement` TR-1.3: 代码 review 确认 memo 使用合理
- **Notes**: 优先处理 CandidateTable 相关子组件、Dashboard 卡片组件、状态展示组件

## [x] Task 2: 候选表格虚拟滚动
- **Priority**: high
- **Depends On**: Task 1
- **Description**:
  - 为 CandidateTable 实现虚拟滚动（Virtual Scrolling）
  - 仅渲染可视区域内的行，大幅减少 DOM 节点数量
  - 保持现有筛选、排序、选择等功能不受影响
  - 预估高度动态计算，支持不同行高
- **Acceptance Criteria Addressed**: AC-1, AC-6
- **Test Requirements**:
  - `programmatic` TR-2.1: 500 条数据滚动帧率 ≥ 50fps
  - `programmatic` TR-2.2: 虚拟滚动不影响筛选和排序功能
  - `programmatic` TR-2.3: 内存使用量降低 50% 以上
  - `human-judgement` TR-2.4: 滚动体验流畅，无明显白屏
- **Notes**: 考虑使用 react-window 或自定义实现，需评估依赖体积

## [x] Task 3: 核心 Hooks 测试
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 为核心业务 hooks 添加单元测试
  - 覆盖 useApi, useGlobalData, useCandidateActions, useDebounce 等关键 hooks
  - 每个 hook 测试覆盖主要功能路径和边界情况
  - 使用 vitest + @testing-library/react-hooks
- **Acceptance Criteria Addressed**: AC-3, AC-8
- **Test Requirements**:
  - `programmatic` TR-3.1: 新增 8+ 个 hooks 测试文件
  - `programmatic` TR-3.2: 核心 hooks 行覆盖率 ≥ 70%
  - `programmatic` TR-3.3: 所有测试 100% 通过
- **Notes**: 重点测试数据获取、状态管理、错误处理相关 hooks

## [x] Task 4: 大型组件拆分 - CandidateTable
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 将 CandidateTable.tsx（770 行）拆分为更小的模块
  - 拆分为：表头组件、表体组件、分页组件、行操作组件等
  - 保持现有 API 和功能完全兼容
  - 提取通用逻辑到自定义 hooks
- **Acceptance Criteria Addressed**: AC-4
- **Test Requirements**:
  - `programmatic` TR-4.1: 拆分后无 > 400 行的单文件组件
  - `programmatic` TR-4.2: 所有现有测试通过
  - `programmatic` TR-4.3: TypeScript 类型检查零错误
  - `human-judgement` TR-4.4: 组件职责清晰，命名合理
- **Notes**: 渐进式拆分，每步都要确保功能正常

## [x] Task 5: 大型组件拆分 - ConfigPanel
- **Priority**: medium
- **Depends On**: None
- **Description**:
  - 将 ConfigPanel.tsx（611 行）拆分为更小的模块
  - 按配置区域拆分：凭证配置、参数配置、高级配置等
  - 提取表单验证逻辑到独立模块
  - 保持现有功能完全兼容
- **Acceptance Criteria Addressed**: AC-4
- **Test Requirements**:
  - `programmatic` TR-5.1: 拆分后无 > 400 行的单文件组件
  - `programmatic` TR-5.2: 所有现有测试通过
  - `programmatic` TR-5.3: TypeScript 类型检查零错误
- **Notes**: 确保配置状态管理逻辑清晰

## [x] Task 6: 防抖/节流全面覆盖
- **Priority**: medium
- **Depends On**: None
- **Description**:
  - 审查所有高频输入场景，添加防抖/节流处理
  - ConfigPanel 中的配置输入添加防抖
  - 滚动事件添加节流
  - window resize 事件添加防抖
  - 统一使用项目的 debounce/throttle 工具函数
- **Acceptance Criteria Addressed**: AC-5
- **Test Requirements**:
  - `programmatic` TR-6.1: 所有搜索输入都有防抖
  - `programmatic` TR-6.2: 所有滚动事件都有节流
  - `human-judgement` TR-6.3: 输入体验流畅，无延迟感
- **Notes**: 防抖延迟建议 300ms，节流间隔建议 100ms

## [x] Task 7: 核心组件测试增强
- **Priority**: medium
- **Depends On**: None
- **Description**:
  - 为核心业务组件添加更多测试用例
  - 覆盖 Dashboard, ConfigPanel, ScoringPanel, SnapshotPanel 等
  - 测试组件渲染、用户交互、状态变化
  - 使用 Testing Library 的用户事件模拟
- **Acceptance Criteria Addressed**: AC-8
- **Test Requirements**:
  - `programmatic` TR-7.1: 新增 5+ 个组件测试文件
  - `programmatic` TR-7.2: 核心组件行覆盖率 ≥ 60%
  - `programmatic` TR-7.3: 所有测试 100% 通过
- **Notes**: 重点测试用户交互路径和边界情况

## [x] Task 8: 可复用逻辑抽取
- **Priority**: medium
- **Depends On**: Task 4, Task 5
- **Description**:
  - 从大型组件中抽取可复用的业务逻辑
  - 创建 usePagination hook 处理分页逻辑
  - 创建 useSorting hook 处理排序逻辑
  - 创建 useFormValidation hook 处理表单验证
  - 抽取通用的表格操作逻辑
- **Acceptance Criteria Addressed**: AC-4
- **Test Requirements**:
  - `programmatic` TR-8.1: 新增 3+ 个可复用 hooks
  - `programmatic` TR-8.2: 重复代码率降低 20%
  - `programmatic` TR-8.3: 所有新 hooks 有单元测试
- **Notes**: 确保抽取的 hooks 有良好的类型定义

## [x] Task 9: 错误边界粒度优化
- **Priority**: medium
- **Depends On**: None
- **Description**:
  - 在主要功能模块级别添加错误边界
  - Dashboard 模块独立错误边界
  - CandidateTable 模块独立错误边界
  - ConfigPanel 模块独立错误边界
  - 每个错误边界都有重试和恢复机制
- **Acceptance Criteria Addressed**: AC-10
- **Test Requirements**:
  - `programmatic` TR-9.1: 主要模块都有独立错误边界
  - `programmatic` TR-9.2: 单个模块错误不影响其他模块
  - `human-judgement` TR-9.3: 错误提示友好，有恢复指引
- **Notes**: 保持顶层错误边界作为最终兜底

## [x] Task 10: 构建和体积优化
- **Priority**: low
- **Depends On**: None
- **Description**:
  - 进一步优化构建配置，减少产物体积
  - 分析 bundle 组成，识别可优化的依赖
  - 实现更细粒度的代码分割
  - 优化图片和静态资源
  - 添加构建体积监控
- **Acceptance Criteria Addressed**: AC-6
- **Test Requirements**:
  - `programmatic` TR-10.1: gzip 后主包 ≤ 80KB
  - `programmatic` TR-10.2: gzip 后总体积 ≤ 200KB
  - `programmatic` TR-10.3: 构建时间 ≤ 3 秒
  - `human-judgement` TR-10.4: 代码分割策略合理
- **Notes**: 使用 rollup-plugin-visualizer 分析 bundle
