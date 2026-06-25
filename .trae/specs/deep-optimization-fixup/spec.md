# BRAIN Alpha Ops 深挖优化（补充修复）- 产品需求文档

## Overview
- **Summary**: 针对 deep-optimization-phase2 验证中发现的 8 项未达标问题进行集中修复，补齐 React.memo 覆盖、useCandidateActions 测试、大型组件进一步拆分、错误边界缺失模块和构建时间优化，将项目质量标准真正落地。
- **Purpose**: phase2 的 checklist 虽然标记为全绿，但实际验证发现多项未达标。本阶段聚焦于真正补齐所有质量缺口，确保验收标准名副其实。
- **Target Users**: 前端开发团队、QA 团队

## Goals
- React.memo 展示型组件覆盖率达到 80% 以上
- useCandidateActions Hook 单元测试覆盖率达到 70% 以上
- useApi Hook 分支覆盖率提升到 70% 以上
- 所有主要组件文件行数控制在 400 行以内
- 所有主要功能模块都有独立错误边界保护
- 构建时间控制在 3 秒以内

## Non-Goals (Out of Scope)
- 不引入新的业务功能
- 不进行视觉设计改版
- 不修改核心业务逻辑
- 不替换现有技术栈
- 不进行后端优化

## Background & Context
- deep-optimization-phase2 已完成主体工作，但实际验证发现 8 项未达标
- 当前 React.memo 覆盖率 71.8%（28/39），差 8% 达标
- useCandidateActions 核心 Hook 完全无测试（0% 覆盖率）
- CandidateTableToolbar.tsx (471行) 和 RunConfigSection.tsx (416行) 超过 400 行限制
- OfficialBacktestSlots 和 SubmissionConfirmPanel 缺少独立错误边界
- 构建时间 3.70s，略超 3s 标准

## Functional Requirements

### FR-1: React.memo 覆盖补全
- 为 OfficialOperations 下的展示型组件添加 React.memo 包装
- 重点组件：OverviewCard、ActionPanel、SummaryMetric 等
- 确保 props 比较逻辑正确

### FR-2: useCandidateActions 单元测试
- 为 useCandidateActions Hook 添加完整的单元测试
- 覆盖 generateCandidates、startSimulation、startOptimization 等核心方法
- 覆盖 SSE 事件处理路径
- 覆盖 buildCredentialOverrides 工具方法

### FR-3: useApi 测试增强
- 补充 useApi 的分支覆盖测试
- 覆盖错误处理、重试、loading 状态等边界场景
- 提升分支覆盖率到 70% 以上

### FR-4: CandidateTableToolbar 拆分
- 将 CandidateTableToolbar.tsx (471行) 拆分为更小的组件
- 按功能区域拆分：标题统计区、批量操作栏、生产控制区、质量摘要区、过滤工具栏
- 保持现有 API 和功能完全兼容

### FR-5: RunConfigSection 拆分
- 将 RunConfigSection.tsx (416行) 拆分为更小的组件
- 按配置类别拆分：基础配置区、评分配置区、高级配置区
- 提取 FIELD_HELP 等常量到独立模块
- 保持现有功能完全兼容

### FR-6: 错误边界补全
- 为 OfficialBacktestSlots 添加独立错误边界
- 为 SubmissionConfirmPanel 添加独立错误边界
- 保持与其他模块一致的错误提示风格

## Non-Functional Requirements

### NFR-1: 性能
- 构建时间 ≤ 3 秒
- 构建产物体积保持不变（gzip 主包 ≤ 80KB，总体积 ≤ 200KB）

### NFR-2: 可维护性
- 单个组件文件 ≤ 400 行
- 单个函数 ≤ 50 行

### NFR-3: 质量保证
- TypeScript 严格模式零错误
- 单元测试通过率 100%
- ESLint 无 error 级警告

### NFR-4: 测试覆盖
- 核心 Hooks 行覆盖率 ≥ 70%
- 核心 Hooks 分支覆盖率 ≥ 70%

## Constraints
- **Technical**: React 18 + TypeScript + Vite 技术栈，不引入大型新依赖
- **Business**: 不得影响现有功能正常使用，所有修改必须向后兼容
- **Dependencies**: 优先使用项目已有依赖

## Assumptions
- useCandidateActions 的子 hooks（useCandidateGeneration 等）已有独立测试，可以进行 mock
- CandidateTableToolbar 的拆分可以按 UI 区域自然划分
- 构建时间优化可以通过调整 Vite 配置或优化依赖实现

## Acceptance Criteria

### AC-1: React.memo 覆盖率达标
- **Given**: 所有展示型组件
- **When**: 检查组件定义
- **Then**: 80% 以上的展示型组件使用了 React.memo
- **Verification**: `programmatic`

### AC-2: useCandidateActions 测试覆盖
- **Given**: useCandidateActions Hook
- **When**: 运行测试覆盖率检查
- **Then**: 行覆盖率达到 70% 以上
- **Verification**: `programmatic`

### AC-3: useApi 分支覆盖
- **Given**: useApi Hook
- **When**: 运行测试覆盖率检查
- **Then**: 分支覆盖率达到 70% 以上
- **Verification**: `programmatic`

### AC-4: CandidateTableToolbar 拆分完成
- **Given**: CandidateTableToolbar 及其子组件
- **When**: 检查文件行数
- **Then**: 没有超过 400 行的组件文件
- **Verification**: `programmatic`

### AC-5: RunConfigSection 拆分完成
- **Given**: RunConfigSection 及其子组件
- **When**: 检查文件行数
- **Then**: 没有超过 400 行的组件文件
- **Verification**: `programmatic`

### AC-6: 错误边界全覆盖
- **Given**: 所有主要功能模块
- **When**: 检查 renderView.tsx
- **Then**: 每个主要模块都被 ErrorBoundary 包裹
- **Verification**: `programmatic`

### AC-7: 构建时间达标
- **Given**: 生产构建
- **When**: 运行 npm run build
- **Then**: 构建时间 ≤ 3 秒
- **Verification**: `programmatic`

### AC-8: 构建体积保持
- **Given**: 生产构建产物
- **When**: 检查构建产物体积
- **Then**: gzip 后主包 ≤ 80KB，总体积 ≤ 200KB
- **Verification**: `programmatic`

### AC-9: 所有测试通过
- **Given**: 所有单元测试
- **When**: 运行 vitest run
- **Then**: 所有测试 100% 通过
- **Verification**: `programmatic`

### AC-10: TypeScript 零错误
- **Given**: TypeScript 严格模式
- **When**: 运行 tsc --noEmit
- **Then**: 零类型错误
- **Verification**: `programmatic`

## Open Questions
- [ ] 构建时间优化是否允许调整 sourcemap 配置？
- [ ] useCandidateActions 测试是否需要集成测试其子 hooks？
