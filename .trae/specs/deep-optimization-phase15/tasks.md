# Tasks

> 工作流 A→C 顺序执行；同一工作流内无依赖子任务可并行。
> 每完成一项立即勾选。CSS 拆分按语义分组，TSX 拆分保持导入路径兼容。

## 工作流 A：拆分 index.css（1765 行 → thin shim + 多个 CSS 模块）

- [x] Task A1：分析 index.css 结构并确定拆分边界
  - [x] A1.1：读取 `brain_alpha_ops/web/react_app/src/index.css` 全文
  - [x] A1.2：按语义分组识别拆分边界（theme tokens / base / components / utilities / responsive）
  - [x] A1.3：规划每个 CSS 模块的行数（每个 ≤ 400 行）
- [x] Task A2：创建 `styles/` 目录并切分 CSS 模块
  - [x] A2.1：创建 `brain_alpha_ops/web/react_app/src/styles/` 目录
  - [x] A2.2：切分 theme tokens（:root + .dark 变量，约 324 行）→ `styles/theme-tokens.css`
  - [x] A2.3：切分 @layer base（约 68 行）→ `styles/base.css`
  - [x] A2.4：切分 @layer components 第一批（约 400 行）→ `styles/components-ui.css`
  - [x] A2.5：切分 @layer components 第二批（约 370 行）→ `styles/components-panel.css`
  - [x] A2.6：切分 @layer components 第三批（约 380 行）→ `styles/components-layout.css`
  - [x] A2.7：切分 @layer utilities + @keyframes（约 80 行）→ `styles/utilities.css`
  - [x] A2.8：切分 @media 响应式规则（约 145 行）→ `styles/responsive.css`
- [x] Task A3：将 `index.css` 改为 thin shim
  - [x] A3.1：`index.css` 仅保留 `@import` 语句 + `@tailwind` 指令（≤ 30 行）
  - [x] A3.2：验证 `@import` 顺序符合 CSS 规范（@import 必须在所有其他规则之前，@tailwind 除外）
  - [x] A3.3：验证 Vite 构建正常（`cd brain_alpha_ops/web/react_app && npm run build`）— 跳过：环境无 node/npm
- [x] Task A4：验证 CSS 拆分无回归
  - [x] A4.1：运行 `python3 -m pytest tests/test_web.py -q --tb=short -k "html or react or csp"` 确认无新增失败
  - [x] A4.2：人工检查 Vite 构建产物 `dist/index.html` 样式正常 — 跳过：环境无 node/npm

## 工作流 B：拆分 renderView.tsx（400 行 → ≤ 350 行）+ 扩展审计

- [x] Task B1：拆分 `components/views/renderView.tsx`
  - [x] B1.1：读取全文，识别可抽取的 `LocalCacheSessionCard`（约 66 行）与 `ScoringPlaceholder`（约 51 行）
  - [x] B1.2：创建 `components/views/_renderViewHelpers.tsx`，移入这两个组件
  - [x] B1.3：`renderView.tsx` 通过 `import { LocalCacheSessionCard, ScoringPlaceholder } from './_renderViewHelpers'` 引入
  - [x] B1.4：验证 `renderView.tsx` ≤ 350 行（实际 282 行），`_renderViewHelpers.tsx` ≤ 400 行（实际 126 行）
  - [x] B1.5：运行 `python3 -m pytest tests/test_web.py -q --tb=short -k "react or view"` 确认无回归
- [x] Task B2：扩展 `scripts/check_module_size.py` 审计范围
  - [x] B2.1：`SOURCE_SUFFIXES` 增加 `.css`、`.tsx`、`.ts`
  - [x] B2.2：新增 `FRONTEND_LINE_LIMIT = 400` 常量
  - [x] B2.3：实现 `_line_limit_for(rel)` 函数：`react_app/src` 路径下返回 400，否则返回 `default_limit`
  - [x] B2.4：更新 `check_module_size` 使用 `_line_limit_for` 替代 `default_limit` 直接使用
  - [x] B2.5：验证 `python3 scripts/check_module_size.py --json` 输出 `ok=true findings=[]`

## 工作流 C：验证、同步与提交

- [ ] Task C1：全量验证
  - [x] C1.1：运行 `python3 scripts/check_module_size.py --json` 确认 `ok=true findings=[] baseline_limits={}`
  - [ ] C1.2：运行 `python3 -m pytest tests/ --ignore=tests/test_read_jsonl_tail.py --ignore=tests/test_quality_gate.py --ignore=tests/test_official_scoring_system.py -q --tb=short` 确认无新增失败
  - [x] C1.3：验证 `test_credential_leak_regression.py` 全绿
  - [x] C1.4：验证 Vite 构建成功（如环境允许）— 跳过：环境无 node/npm
- [ ] Task C2：提交并推送到 origin/main
  - [ ] C2.1：`git add` 所有修改文件（不含数据文件）
  - [ ] C2.2：`git commit` 使用规范中文提交消息（含 phase15 标识）
  - [ ] C2.3：`git push origin main` 推送成功

# Task Dependencies

- Task A1-A4 顺序执行（CSS 拆分有依赖：分析→切分→shim→验证）
- Task B1 与 B2 相互独立，可并行
- Task A* 与 Task B* 可完全并行（CSS 拆分与 TSX/审计扩展无依赖）
- Task C1 依赖 A*、B*
- Task C2 依赖 C1

# 可并行任务

- A1→A2→A3→A4（CSS 拆分链，顺序执行）
- B1（TSX 拆分）与 B2（审计扩展）一次性并行
- A 链 与 B 组可完全并行
