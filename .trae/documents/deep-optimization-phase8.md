# 深挖优化 Phase 8 - 实施计划

## Summary

Phase 6/7 完成了前端全量文件拆分（≤400行）和后端 research/web 模块拆分。但仍遗留 11 个 Python 文件超过 500 行（违反 Phase 7 自己提出的规范）、前端 tsconfig 严格模式关闭、集成测试失败、孤儿测试未运行等问题。本轮聚焦 P0 高价值项：拆分剩余后端大文件 + 修复前端测试问题 + 提升类型安全。

## Current State Analysis

### 已完成（Phase 5-7）
- 前端：所有 .ts/.tsx 文件 ≤ 400 行（最大 App.tsx 394行）
- 后端：research/ 6个文件、web/misc/ 2个文件、web/candidates/ 1个文件、web_cloud/snapshot.py 已拆分
- 可访问性组件库、性能优化组件/Hooks、测试覆盖已建立

### 未完成（本轮目标）
1. **11 个 Python 文件 > 500 行**（Phase 7 未覆盖 web_candidates/、data/、ux/、web_cloud/、根目录）
2. **tsconfig strict 模式关闭** — `strict: false`、`noImplicitAny: false`、`strictNullChecks: false`
3. **孤儿测试** — `src/__tests__/` 下 2 个测试文件未被 vitest 执行
4. **vite manualChunks 粗粒度** — 所有 node_modules 合并为单个 vendor chunk

## Proposed Changes

### Task 1: 拆分 11 个 Python 后端大文件（>500行 → ≤350行子包）

按模块分组，使用 Phase 6/7 验证过的 re-export 子包模式：

**web_candidates/ 模块（4个文件，最集中）：**
- `web_candidates/optimization.py` (730行) → `optimization/` 子包
- `web_candidates/bindings.py` (581行) → `bindings/` 子包
- `web_candidates/decisions.py` (520行) → `decisions/` 子包
- `web_candidates/audit.py` (510行) → `audit/` 子包

**data/ 模块（2个文件）：**
- `data/ashare_adapter.py` (770行) → `ashare_adapter/` 子包
- `data/loader.py` (521行) → `loader/` 子包

**web_cloud/ 模块（1个文件）：**
- `web_cloud/sync_job.py` (630行) → `sync_job/` 子包

**根目录（3个文件）：**
- `tasks.py` (567行) → `tasks/` 子包
- `production_diagnostics.py` (548行) → `production_diagnostics/` 子包
- `agent_tools.py` (540行) → `agent_tools/` 子包

**ux/ 模块（1个文件）：**
- `ux/guided_pipeline.py` (517行) → `guided_pipeline/` 子包

**模式**（已验证 5 次）：
1. 创建同名子目录
2. 按功能拆分为 3-5 个子模块（≤350行/文件）
3. `__init__.py` 统一导出所有公共 API + 被外部引用的私有符号
4. 原 .py 文件改为 re-export shim（≤100行）
5. 验证 `from module import *` 正常工作

### Task 2: 修复前端测试配置

**2a. 迁移孤儿测试：**
- 将 `src/__tests__/components_v3.test.tsx` 迁移到 `tests/components_v3.test.tsx`
- 将 `src/__tests__/usePhaseState.test.ts` 迁移到 `tests/usePhaseState_v3.test.ts`（避免与已有 tests/usePhaseState.test.ts 冲突）
- 删除 `src/__tests__/` 目录
- 或替代方案：修改 `vite.config.ts` 的 `test.include` 添加 `"src/**/__tests__/**/*.test.{ts,tsx}"`

**2b. vite.config.ts manualChunks 优化：**
- 将单一 `vendor` chunk 拆分为：
  - `react-vendor`: react, react-dom, react/jsx-runtime
  - `tanstack-vendor`: @tanstack/react-virtual, @tanstack/react-table
  - `vendor`: 其他第三方依赖
- 改善浏览器长缓存命中率

### Task 3: tsconfig 类型安全提升（渐进式）

分步启用，避免一次性破坏：
1. 启用 `noUnusedLocals: true` — 自动发现未使用导入/变量
2. 启用 `noUnusedParameters: true` — 发现未使用函数参数
3. 清理所有发现的未使用导入/变量
4. **暂不启用 strict/strictNullChecks**（影响面太大，需单独评估）

### Task 4: 回填过期规格文档

- 更新 `deep-optimization-final/checklist.md` — 将已在 Phase 6/7 完成的 stale 项标记为 `[x]`
- 更新 `deep-optimization-phase2/checklist.md` — 同上

### Task 5: 最终验证与提交

- 确认所有 Python 文件 ≤ 500 行
- 确认前端文件仍 ≤ 400 行
- 运行 Python 测试套件
- 提交并推送到 origin/main

## Assumptions & Decisions

1. **Node.js 不可用**：环境中无 node/npx，前端类型检查和测试运行需通过代码审查验证，不能执行 `npx tsc --noEmit` 或 `npx vitest run`
2. **Python 3.9 可用**：可运行 `python3 -m pytest` 验证后端
3. **向后兼容优先**：所有拆分保持 100% 向后兼容，原文件保留为 re-export 入口
4. **strict 模式分步推进**：本轮只启用 noUnusedLocals/noUnusedParameters，不碰 strictNullChecks（影响面太大需单独评估）
5. **manualChunks 优化为低风险**：仅影响构建产物的 chunk 分割，不影响运行时行为

## Verification Steps

1. `find brain_alpha_ops -name "*.py" -not -path "*/__pycache__/*" | xargs wc -l | sort -rn | awk '$1 > 500'` → 应为空
2. `python3 -m pytest tests/test_anti_overfit.py tests/test_web_routes_handlers.py -v` → 无新增失败
3. `python3 -c "from brain_alpha_ops.web_candidates.optimization import *; print('OK')"` → 每个拆分模块验证
4. `git status --short` → 工作区干净（除数据文件外）
5. `git push origin main` → 推送成功
