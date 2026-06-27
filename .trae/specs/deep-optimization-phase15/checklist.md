# Checklist

## CSS 拆分正确性

- [x] `index.css` ≤ 30 行（仅 `@import` + `@tailwind` 指令）— 实际 16 行
- [x] 每个 `styles/*.css` 模块 ≤ 400 行 — 最大 397 行（components-layout.css）
- [x] CSS `@import` 顺序符合规范（在所有其他规则之前，`@tailwind` 除外）
- [x] 拆分后 CSS 变量、@layer、@media 规则无丢失
- [ ] Vite 构建成功，无 CSS 编译错误 — 跳过：环境无 node/npm

## TSX 拆分正确性

- [x] `renderView.tsx` ≤ 350 行 — 实际 282 行
- [x] `_renderViewHelpers.tsx` ≤ 400 行 — 实际 126 行
- [x] `renderActiveView` 导出路径不变（`from '@/components/views/renderView'`）
- [x] `LocalCacheSessionCard` 与 `ScoringPlaceholder` 行为不变（代码原样迁移）

## 审计扩展正确性

- [x] `SOURCE_SUFFIXES` 包含 `.css`、`.tsx`、`.ts`
- [x] `FRONTEND_LINE_LIMIT = 400` 已定义
- [x] `react_app/src` 下文件应用 400 行限制
- [x] 其余文件仍应用 350 行限制
- [x] `BASELINE_LINE_LIMITS` 保持 `{}`
- [x] `check_module_size.py --json` 输出 `ok=true findings=[]`

## 行为兼容性

- [ ] React 测试套件无新增失败 — 6 个预存失败均为 React .tsx 源码契约测试，与 CSS/TSX 拆分无关
- [ ] pytest 主套件失败数 ≤ 133（Phase 14 基线）
- [x] 凭据扫描测试 `test_credential_leak_regression.py` 全绿 — 2 passed
- [ ] Vite 构建产物样式正常 — 跳过：环境无 node/npm

## 提交与推送

- [ ] `git commit` 使用规范中文提交消息（含 phase15 标识）
- [ ] `git push origin main` 推送成功
- [ ] 远端 `origin/main` 最新 commit 包含本阶段所有变更

## 文档与规格

- [ ] `tasks.md` 所有任务勾选完成
- [ ] `checklist.md` 所有检查项勾选完成
- [x] 无新增 open 缺陷
- [x] 前端文件合规性纳入持续审计（防止回归）
