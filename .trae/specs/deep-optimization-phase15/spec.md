# 前端文件合规与审计覆盖 Spec (Phase 15)

## Why

Phase 14 完成了 Python 后端的行数收敛（`BASELINE_LINE_LIMITS = {}`，880 个源文件全部 ≤ 350 行）。
但审计脚本 `check_module_size.py` 仅覆盖 `.py/.js/.html`，未审计 `.css/.tsx/.ts`，导致前端文件
合规性存在盲区。当前 `brain_alpha_ops/web/react_app/src/index.css` 已达 1765 行（超过前端 400 行
限制 4.4 倍），`renderView.tsx` 正好 400 行（边缘状态），且无任何审计机制防止进一步劣化。

## What Changes

- 拆分 `brain_alpha_ops/web/react_app/src/index.css`（1765 行）为多个 ≤ 400 行的 CSS 模块，
  原 `index.css` 改为 thin shim（仅 `@import` + `@tailwind` 指令）
- 拆分 `brain_alpha_ops/web/react_app/src/components/views/renderView.tsx`（400 行）至 ≤ 350 行，
  抽取 `LocalCacheSessionCard` + `ScoringPlaceholder` 至同级子模块
- 扩展 `scripts/check_module_size.py`：`SOURCE_SUFFIXES` 增加 `.css/.tsx/.ts`；
  新增 `FRONTEND_LINE_LIMIT = 400`；对 `react_app/src` 下的文件应用 400 行限制
- 验证 Vite 构建正常、React 测试套件无新增失败、模块大小审计全绿

## Impact

- Affected specs: deep-optimization-phase14（BASELINE_LINE_LIMITS 保持 `{}`）
- Affected code:
  - `brain_alpha_ops/web/react_app/src/index.css`（拆分为 thin shim + 多个 CSS 模块）
  - `brain_alpha_ops/web/react_app/src/styles/`（新增 CSS 模块目录）
  - `brain_alpha_ops/web/react_app/src/components/views/renderView.tsx`（拆分）
  - `brain_alpha_ops/web/react_app/src/components/views/_renderViewHelpers.tsx`（新增）
  - `scripts/check_module_size.py`（扩展审计范围）

## ADDED Requirements

### Requirement: 前端文件大小审计

系统 SHALL 在 `check_module_size.py` 中审计 `brain_alpha_ops/web/react_app/src` 下的
`.css/.tsx/.ts` 文件，限制为 400 行。

#### Scenario: CSS 文件超过 400 行
- **WHEN** `react_app/src/styles/foo.css` 有 401 行
- **THEN** `check_module_size.py --json` 的 `findings` 包含该文件，`ok=false`

#### Scenario: 前端审计全绿
- **WHEN** 所有前端文件 ≤ 400 行
- **THEN** `check_module_size.py --json` 输出 `ok=true findings=[]`

### Requirement: index.css 拆分为 thin shim

系统 SHALL 将 `index.css`（1765 行）拆分为多个 ≤ 400 行的语义化 CSS 模块，
原 `index.css` 仅保留 `@tailwind` 指令与 `@import` 语句（≤ 30 行）。

#### Scenario: CSS 拆分后导入正常
- **WHEN** Vite 构建运行
- **THEN** 所有 CSS 样式正常应用，无样式丢失或重复

### Requirement: renderView.tsx 拆分至 ≤ 350 行

系统 SHALL 将 `renderView.tsx`（400 行）中的 `LocalCacheSessionCard` 与
`ScoringPlaceholder` 抽取至同级 helper 文件，使主文件 ≤ 350 行。

#### Scenario: 拆分后渲染正常
- **WHEN** React 组件树渲染 activeView
- **THEN** `renderActiveView` 行为不变，所有视图正常显示

## MODIFIED Requirements

### Requirement: check_module_size.py 审计范围

原审计仅覆盖 `brain_alpha_ops` 与 `scripts` 下的 `.py/.js/.html` 文件，限制 350 行。
现扩展为：同时审计 `.css/.tsx/.ts` 文件；`react_app/src` 路径下的文件限制 400 行，
其余文件仍限制 350 行。`BASELINE_LINE_LIMITS` 保持 `{}`。
