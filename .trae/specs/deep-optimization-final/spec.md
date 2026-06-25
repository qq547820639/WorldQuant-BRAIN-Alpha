# BRAIN Alpha Ops 深挖优化（最终阶段）- 产品需求文档

## Overview
- **Summary**: 针对 BRAIN Alpha Ops 前后端项目进行最终阶段深度优化，聚焦于测试修复、代码质量标准化、构建性能优化和大型工具模块拆分四个核心维度，确保项目达到生产级质量标准后合并到 main 分支。
- **Purpose**: 解决当前代码库中存在的 94 个前端测试失败、6907 个 ESLint 错误、构建时间过长（4.89s）和大型工具模块维护困难等问题，将项目质量提升到可交付的生产标准。
- **Target Users**: 前端开发团队、后端开发团队、QA 团队、DevOps 团队

## Goals
- 修复所有前端测试失败，测试通过率达到 100%
- 消除所有 ESLint error 级错误，代码风格统一
- 前端构建时间优化至 3 秒以内
- 所有组件/hooks 单文件行数控制在 400 行以内，工具模块控制在 500 行以内
- 修复 TypeScript baseUrl 弃用警告
- 所有修改向后兼容，不破坏现有功能

## Non-Goals (Out of Scope)
- 不引入新的业务功能
- 不进行视觉设计改版
- 不修改核心业务逻辑
- 不替换现有技术栈
- 不进行后端性能深度优化（仅修复影响前端的问题）
- 不重构 Python 后端架构

## Background & Context
- 项目已完成前三阶段深挖优化，组件拆分和基础性能优化已基本完成
- 当前存在 94 个前端测试失败（614 个测试中），涉及快照不匹配、集成测试失败等
- ESLint 报告 6907 个错误，其中大部分为 Prettier 格式问题
- 前端构建时间 4.89 秒，超出 3 秒目标
- 存在多个超大型工具模块：OfficialOperations/utils.ts (1021行)、CandidateTableUtils.ts (613行)、useOfficialOperations.ts (685行)
- TypeScript 配置存在 baseUrl 弃用警告

## Functional Requirements

### FR-1: 前端测试失败修复
- 修复所有 94 个失败的前端单元测试和集成测试
- 更新过期的快照测试（snapshot tests）
- 修复集成测试中的 DOM 查询问题
- 确保所有测试在 CI 环境中稳定通过

### FR-2: ESLint/Prettier 代码质量标准化
- 修复所有 ESLint error 级错误
- 统一代码格式化风格（Prettier）
- 修复 no-undef、no-console 等规则违规
- 确保代码风格一致，提高可维护性

### FR-3: 构建性能优化
- 优化 Vite 构建配置，将构建时间降至 3 秒以内
- 优化依赖预构建和代码分割策略
- 确保构建产物的体积不增加

### FR-4: 大型工具模块拆分
- 拆分 OfficialOperations/utils.ts (1021行) 为更小的功能模块
- 拆分 CandidateTableUtils.ts (613行) 为更小的工具模块
- 拆分 useOfficialOperations.ts (685行) 为更细粒度的 hooks
- 保持所有现有 API 向后兼容

### FR-5: TypeScript 配置现代化
- 修复 baseUrl 弃用警告，迁移至 paths 配置
- 确保 TypeScript 严格模式零错误
- 更新相关构建配置以适配新的路径配置

## Non-Functional Requirements

### NFR-1: 质量保证
- 前端测试通过率 100%
- TypeScript 严格模式零错误
- ESLint 无 error 级警告
- Prettier 格式化 100% 通过

### NFR-2: 性能
- 前端构建时间 ≤ 3 秒
- 构建产物体积保持不变（gzip 主包 ≤ 80KB，总体积 ≤ 200KB）
- 运行时性能不下降

### NFR-3: 可维护性
- 组件文件 ≤ 400 行
- 自定义 hooks ≤ 400 行
- 工具模块 ≤ 500 行
- 单个函数 ≤ 50 行

### NFR-4: 兼容性
- 所有 API 向后兼容
- 不引入破坏性变更
- 现有功能 100% 可用

## Constraints
- **Technical**: React 18 + TypeScript + Vite 技术栈，Python 3.10+ 后端
- **Business**: 不得影响现有功能正常使用，所有优化必须向后兼容
- **Dependencies**: 优先使用项目已有依赖，谨慎添加新依赖
- **Timeline**: 一次性完成，完成后直接提交到 origin/main

## Assumptions
- 测试失败主要是快照过期和 DOM 查询选择器不匹配，而非逻辑错误
- ESLint 错误大部分为格式问题，可通过 --fix 自动修复
- 大型工具模块可以按功能边界自然拆分而不影响运行时
- 构建时间优化可以通过调整 Vite 配置和依赖策略实现

## Acceptance Criteria

### AC-1: 前端测试 100% 通过
- **Given**: 所有前端单元测试和集成测试
- **When**: 运行 `npx vitest run`
- **Then**: 所有测试通过，失败数为 0
- **Verification**: `programmatic`

### AC-2: ESLint 无 error 级错误
- **Given**: 所有前端源代码
- **When**: 运行 `npx eslint src`
- **Then**: error 级错误数为 0
- **Verification**: `programmatic`

### AC-3: Prettier 格式化通过
- **Given**: 所有前端源代码
- **When**: 运行 `npx prettier --check src`
- **Then**: 所有文件格式符合规范
- **Verification**: `programmatic`

### AC-4: 构建时间 ≤ 3 秒
- **Given**: 生产构建
- **When**: 运行 `npm run build`
- **Then**: 构建完成时间 ≤ 3 秒
- **Verification**: `programmatic`

### AC-5: 构建体积保持
- **Given**: 生产构建产物
- **When**: 检查构建产物体积
- **Then**: gzip 后主包 ≤ 80KB，总体积 ≤ 200KB
- **Verification**: `programmatic`

### AC-6: TypeScript 零错误
- **Given**: TypeScript 严格模式
- **When**: 运行 `npx tsc --noEmit`
- **Then**: 零类型错误，无弃用警告
- **Verification**: `programmatic`

### AC-7: 大型模块拆分完成
- **Given**: 拆分后的工具模块和 hooks
- **When**: 检查文件行数
- **Then**: 组件 ≤ 400 行，hooks ≤ 400 行，工具模块 ≤ 500 行
- **Verification**: `programmatic`

### AC-8: 向后兼容
- **Given**: 所有现有导入路径
- **When**: 构建和运行测试
- **Then**: 所有现有导入路径仍然有效，功能正常
- **Verification**: `programmatic`

### AC-9: 后端测试通过
- **Given**: 所有后端 Python 测试
- **When**: 运行 `pytest tests/`
- **Then**: 所有现有测试继续通过
- **Verification**: `programmatic`

## Open Questions
- [ ] 构建时间优化是否允许调整 sourcemap 配置？
- [ ] 大型工具模块拆分是否需要调整导入路径，还是全部通过 index.ts 重新导出？
