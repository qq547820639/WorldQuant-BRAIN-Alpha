# BRAIN Alpha Ops 用户体验评估与优化方案

> 评估日期：2026-05-21  
> 评估对象：本地 Web 控制台 `brain_alpha_ops/web/index_template.html`、模块化前端 `brain_alpha_ops/web/js/*`、Web API 状态流与本地运行首屏  
> 交付目标：定位交互流程、视觉层级、信息架构与无障碍问题，并给出可执行优化方案与体验指标。

---

## 0. 执行摘要

当前产品已经从早期的阻断型前端问题进入“可用但仍有摩擦”的阶段。核心生产链路、云端同步、批量检查、可提交、提交失败明细、生命周期追踪等入口都已存在，前端语法检查通过，本地服务 smoke test 通过，`/api/health` 返回 ready。

主要 UX 风险不再是页面完全不可用，而是：

1. **核心路径在移动端被配置面板拖长**：390px 宽度下，结果区位于约 3147px 之后，用户必须穿过完整生产控制侧栏才看到候选、状态卡和表格。
2. **无障碍语义缺口仍明显**：首屏检测到 `aria-live=0`、`role=dialog=0`、表格无 `caption/aria-label`、表格行无 `tabindex/role`，进度条也缺少 `progressbar` 语义。
3. **结果状态架构过于“全量暴露”**：生产流程 + 辅助追踪共有 16 个状态卡，信息覆盖完整，但新用户和移动端用户难以判断下一步最重要动作。
4. **提交前后可恢复性有改善但仍可再闭环**：批量提交失败已有明细面板和全部重试入口，但失败项尚未提供逐项修复建议、单项重试、错误类型筛选。
5. **视觉与触控密度偏桌面工具化**：首屏可见按钮多为 28-34px 高，低于 44px 触控目标；移动端虽无横向溢出，但可点区域偏小。

综合判断：桌面端内部工具可用性约 **3.7/5**；移动端只达到 **2.8/5**；无障碍约 **2.4/5**。优先级应从“再加功能”转向“让核心生产路径更短、状态更可解释、长任务更可感知、键盘/读屏可完整操作”。

---

## 1. 本次验证证据

### 1.1 运行与构建

| 验证项 | 结果 | 证据 |
|---|---:|---|
| 前端 inline JS 语法检查 | 通过 | `scripts/check_frontend_syntax.py --json`：`ok=true`，检查 13 个 script block |
| 前端内联构建同步 | 通过 | `brain_alpha_ops/web/build_inline.py --check --json`：13 个模块已内联，输出同步 |
| Web 服务 smoke test | 通过 | `python -m brain_alpha_ops.web --no-browser --port 8765 --smoke-test`：`web ready` |
| 本地 health | 通过 | `GET http://127.0.0.1:8765/api/health`：`{"ok": true, "status": "ready"}` |
| 桌面首屏 | 可打开 | `docs/ux_audit_20260521_desktop.png` |
| 移动首屏 | 可打开，无横向溢出 | `docs/ux_audit_20260521_mobile.png` |

### 1.2 已修复或已改善的历史问题

| 历史问题 | 当前状态 | 代码证据 |
|---|---|---|
| SSE 进度反馈阻断 | 已使用 `EventSource`，并有轮询降级 | `brain_alpha_ops/web/js/views/production.js:27`, `:34`, `:76` |
| 后端 phase 中文标签 | 后端已有 `_PHASE_LABELS` 和 `_enrich_progress()` | `brain_alpha_ops/web.py:324`, `:349` |
| `/api/health` | 已存在 | `brain_alpha_ops/web_get_handlers.py:50` |
| 批量提交失败明细 | 已存在失败面板与重试入口 | `brain_alpha_ops/web/js/app.js:3017` |
| `checks.jsonl` 刷新后恢复 | 前端启动会加载 `/api/check_results` | `brain_alpha_ops/web/js/app.js:3950` |
| 检查项标签和建议 | 后端 check 结果包含 `label_cn`、`suggestion` | `brain_alpha_ops/web_check_availability.py:18`, `:46`, `:49`, `:52` |
| 非 REGULAR Alpha 类型入口 | UI 已提供 `REGULAR/POWER_POOL/ATOM/PYRAMID` | `brain_alpha_ops/web/index_template.html:1105` |

---

## 2. 用户流程诊断

### 2.1 当前主流程

```text
打开本地控制台
→ 选择环境 / 登录凭据 / 回测参数
→ 同步云端 Alpha
→ 开始生产搜索
→ 查看候选池、回测槽、状态卡和图表
→ 达标 Alpha 批量检查
→ 可提交 Alpha 勾选或自动提交
→ 查看提交成功/失败、云端状态和生命周期
```

### 2.2 主要流失节点

| 流失节点 | 表现 | 用户影响 | 严重度 |
|---|---|---|---|
| 首次进入配置负担重 | 侧栏默认展开官方回测设置、云端数据、系统策略 | 新用户需要理解大量参数后才看到结果区 | P1 |
| 移动端核心结果区过深 | 390px 下 `aside` 高约 2955px，`section` 从 y=3147 开始 | 手机或窄屏下几乎无法快速监控生产状态 | P1 |
| 状态卡过多但缺少任务优先级 | 生产流程 8 张 + 辅助追踪 8 张 | 用户知道“有很多状态”，但不一定知道“下一步做什么” | P1 |
| 达标到可提交之间概念断层 | “达标”“可提交”“检查通过”“过期”混合依赖检查状态 | 用户可能误以为达标即可提交 | P1 |
| 失败恢复仍偏聚合 | 批量提交失败有列表，但缺单项修复、单项重试、错误分类 | 用户需要自己判断失败项如何处理 | P2 |
| 键盘用户无法完整操作表格 | 行仅点击打开详情，没有行级 `tabindex` / `role` | 无鼠标或辅助设备用户无法高效查看详情 | P0 for accessibility |
| 读屏用户无法感知长任务变化 | 进度与 toast 无 `aria-live` | 长任务完成、失败、阻断不会主动播报 | P0 for accessibility |

---

## 3. 视觉层级与信息架构评估

### 3.1 做得好的部分

| 维度 | 现状优势 |
|---|---|
| 业务覆盖 | 候选、等待回测、回测中、失败/二次融合、达标、可提交、已提交、云端、生命周期均有入口 |
| 长任务反馈 | 云端同步和批量检查有进度条、已处理数量、预计剩余 |
| 结果可解释性 | 候选详情包含 scorecard、门禁、校验、本地质量、官方指标和 scoring attribution |
| 风险控制 | 生产环境提示、云端同步风险、重复提交、观测风险确认都有防护 |
| 工程结构 | 前端已拆分 `utils/api-client/state/components/views/app`，不再完全依赖巨型 inline 脚本 |

### 3.2 主要结构问题

| 问题 | 具体位置 | 诊断 |
|---|---|---|
| 主操作与次级配置同权 | `aside` 中登录、回测设置、云端同步、策略全部默认堆叠 | 首屏没有“当前最重要任务”与“高级设置”的明显分层 |
| 结果区首屏优先级不足 | `section` 位于右侧，但移动端排在配置后面 | 响应式布局只做了单列适配，没有重排核心任务顺序 |
| 状态卡分组虽清楚但数量偏多 | `renderInsight()` 生成生产流程和辅助追踪 16 张卡 | 专家可扫读，新用户认知成本高 |
| 表格空态可读，但可行动性弱 | 空态提示“点击开始生产后显示候选” | 可以增加“开始生产”“同步云端”的上下文快捷动作 |
| 图表作为辅助分析，但默认隐藏 | `chartsPanel` 默认 display none | 对结果理解有帮助，但入口不明显，易被忽略 |

---

## 4. 可用性与无障碍问题清单

### P0：无障碍操作闭环

| ID | 问题 | 证据 | 改进方案 | 预期提升 |
|---|---|---|---|---|
| A11Y-1 | 表格行不可键盘聚焦 | 首屏检测：`firstRowsTabindex=[null]`，行 HTML 无 `tabindex`；`candidateRowHtml()` 只生成 `onclick` | 给数据行添加 `tabindex="0" role="button"` 或将 Alpha 单元格中的“查看”作为主要可聚焦入口；Enter/Space 打开详情 | 键盘完成候选详情查看率从不可用提升到 100% |
| A11Y-2 | 弹窗缺少 dialog 语义 | 首屏检测：`dialogs=0`、`ariaModal=0`；`detailModal` 和 `confirmOverlay` 未标注 | `#detailModal .modal-panel`、`.confirm-dialog` 添加 `role="dialog" aria-modal="true" aria-labelledby`；打开时 focus close/primary button | 读屏用户可识别上下文，降低迷失 |
| A11Y-3 | 长任务进度与 toast 不播报 | 首屏检测：`liveRegions=0`；`cloudSyncMeta`、`checkProgressMeta` 无 `aria-live` | toast 容器加 `aria-live="polite"`；error toast 加 `role="alert"`；进度 meta 加 `aria-live="polite"` | 长任务完成/失败可被辅助技术感知 |
| A11Y-4 | 进度条缺少语义 | `.track/.fill` 仅视觉宽度 | 给 track 加 `role="progressbar"`、`aria-valuemin/max/now`，更新时同步 aria 值 | 读屏可理解百分比 |

### P1：核心路径压缩

| ID | 问题 | 改进方案 | 预期提升 |
|---|---|---|---|
| FLOW-1 | 首次进入先看到大量参数 | 把“生产控制”拆为紧凑模式：环境、凭据、开始生产、同步云端默认显示；官方设置和系统策略默认折叠，并显示当前 preset 摘要 | 首屏关键操作数量减少 40-60% |
| FLOW-2 | 移动端结果区过深 | 在 `<720px` 下把结果状态摘要置于控制区之前；或增加 sticky 底部操作条：同步、开始/停止、跳到结果 | 移动端到达候选区滚动距离从约 3147px 降到 < 900px |
| FLOW-3 | “达标”与“可提交”关系不够直观 | 在达标卡下展示“需检查 N / 检查通过 M / 过期 K”；点击达标后顶部固定显示检查动作 | 达标后下一步识别时间降低 50% |
| FLOW-4 | 失败恢复偏聚合 | 提交失败列表增加错误类型、建议动作、单项重试、复制错误、按可重试筛选 | 批量提交失败后的平均恢复时间降低 30-50% |

### P2：视觉和响应反馈

| ID | 问题 | 改进方案 | 预期提升 |
|---|---|---|---|
| UI-1 | 可点目标偏小 | 将主要按钮和表格操作按钮最小高度提升到 40-44px；header 小按钮保留图标但扩大 hit area | 移动误触率下降 |
| UI-2 | 辅助追踪卡与生产流程卡视觉同权 | 生产流程卡保留强视觉，辅助追踪卡改为更轻的状态条或折叠组 | 首屏扫描效率提升 |
| UI-3 | 图表入口弱 | 在候选池标题区增加“表格/图表”分段控件；图表卡不默认完全隐藏，而在有数据时显示摘要 | 指标趋势更容易被发现 |
| UI-4 | 警告信息与行动建议分离 | 把 `suggestion` 展示在检查详情和失败面板首层，而非只藏在详情 JSON/检查数组中 | 阻断原因可解释性提升 |

---

## 5. 可执行优化方案

### 5.1 简化核心操作路径

1. **新增“运行准备卡”作为侧栏顶部唯一主任务区**
   - 显示：环境、连接状态、云端同步状态、当前 preset、开始/停止按钮。
   - 折叠：凭据高级设置、完整 official settings、策略插件参数。
   - 文件：`brain_alpha_ops/web/index_template.html`、`brain_alpha_ops/web/js/app.js`。

2. **移动端重排信息架构**
   - 在 `@media (max-width: 720px)` 下，使用 CSS grid/order 或复制轻量状态摘要，使“状态卡 + 开始/停止 + 同步”进入首屏。
   - 增加“跳到结果”按钮，锚点到 `section` 或 `#candidateTable`。

3. **将达标检查变成明确步骤**
   - 当进入 `passed` 视图时，模块操作区固定展示：“快速检查”“全部检查”“自动提交”。
   - 如果 `checks.jsonl` 已恢复检查结果，顶部显示“有效通过/阻断/过期”并提供一键复检过期项。

### 5.2 提升界面响应反馈

1. **进度反馈语义化**
   - `cloudSyncMeta` 和 `checkProgressMeta` 添加 `aria-live="polite"`。
   - `.track` 添加 `role="progressbar"`，动态写入 `aria-valuenow`。
   - 长时间停滞时，把“等待接口返回”升级为 warning 文案，并给出“查看日志/继续等待/停止任务”的动作。

2. **错误反馈从 toast 升级为任务内反馈**
   - toast 仅承担短提示。
   - 任务面板保留可持久查看的错误块，包含错误码、用户文案、技术详情折叠、建议动作。
   - 批量失败项提供 per-alpha 操作：查看详情、重试、复制错误、标记忽略。

3. **状态卡增加下一步提示**
   - 例如“达标 3，待检查 2”卡点击后，模块区直接出现检查 CTA。
   - “可提交 1，检查通过”卡点击后，直接展示勾选与提交 CTA。

### 5.3 无障碍访问设计

1. **语义地标**
   - `<header role="banner">`
   - `<main role="main">`
   - `<aside role="complementary" aria-label="生产控制">`
   - `<section aria-labelledby="tableTitle">`

2. **表格与行操作**
   - `<table id="candidateTable" aria-label="Alpha 候选与生命周期记录">`
   - 数据行添加 `tabindex="0"`，监听 Enter/Space 打开详情。
   - 更稳妥的方案：每行第一列或最后一列保留真实 `<button>` 作为主详情入口，行点击仅作为增强。

3. **弹窗焦点管理**
   - 打开详情时记录 `previousFocus`，关闭后恢复。
   - 弹窗内 trap focus，Esc 关闭已有全局监听，可继续保留。
   - confirm dialog 首次聚焦“取消”或风险较低操作，避免误确认。

4. **触控目标**
   - 主要按钮最小 44px。
   - 表格内小按钮移动端改为 40px。
   - header 图标按钮视觉可小，但 hit area 用 padding 扩大。

### 5.4 多端适配

1. **桌面端**
   - 保持 360px 控制侧栏 + 结果主面板。
   - 优化侧栏折叠默认状态，减少首屏高度。

2. **平板端**
   - 单列后将“运行准备卡”和“状态摘要”置顶。
   - 详情弹窗宽度 92vw，表格可横向滚动但保留关键列 sticky。

3. **手机端**
   - 默认展示：状态、同步/开始按钮、核心流程卡。
   - 高级设置通过 bottom sheet 或折叠面板进入。
   - 表格改为卡片列表：Alpha ID、状态、排序分、官方 ID、风险、操作。

---

## 6. 预期体验提升指标

| 指标 | 当前基线 | 目标 | 验收方式 |
|---|---:|---:|---|
| 首屏关键操作数量 | 侧栏可见控件约 30+ | 首屏主操作 <= 8 | DOM 统计 + 人工检查 |
| 移动端到结果区滚动距离 | 约 3147px | < 900px | 390x844 viewport 截图/DOM rect |
| 前端无障碍 live region | 0 | >= 3 | DOM 检查 |
| dialog 语义覆盖 | 0 | 详情、确认弹窗 100% | DOM 检查 |
| 表格键盘可操作 | 行不可聚焦 | 所有数据行或详情按钮可 Enter/Space 操作 | 键盘测试 |
| 触控目标 | 可见按钮多为 28-34px | 主操作 >= 44px，次要 >= 40px | DOM rect |
| 批量失败恢复 | 聚合重试 | 单项重试 + 错误分类 + 建议 | 人工流程测试 |
| 达标到检查路径 | 需要理解状态卡和模块区 | 点击达标后直接出现检查 CTA | 任务流测试 |
| 任务反馈可理解性 | toast + 状态文本 | 状态文本 + 持久错误块 + 建议动作 | 失败模拟测试 |

---

## 7. 实施路线图

### Phase 1：无障碍与低风险修复（0.5-1 天）

| 任务 | 文件 | 验收 |
|---|---|---|
| 添加 landmarks、table aria-label、dialog role、aria-modal | `index_template.html` | DOM 检测通过 |
| 进度文本与 toast 添加 live region | `index_template.html`, `components/toast.js` | `aria-live >= 3` |
| 表格行键盘打开详情 | `app.js` | Tab + Enter 可打开详情 |
| 弹窗焦点恢复 | `views/detail.js`, `components/modal.js` | 关闭后焦点回到触发按钮 |

### Phase 2：核心路径压缩（1-2 天）

| 任务 | 文件 | 验收 |
|---|---|---|
| 侧栏改为“运行准备卡 + 默认折叠高级设置” | `index_template.html` | 首屏主操作 <= 8 |
| 移动端状态摘要置顶或增加跳转按钮 | `index_template.html`, CSS | 390px 下结果区进入 < 900px |
| 达标/可提交模块动作固定化 | `app.js` | passed/submittable 视图 CTA 清晰 |

### Phase 3：恢复性与可解释性（2-3 天）

| 任务 | 文件 | 验收 |
|---|---|---|
| 提交失败明细增加错误类型、建议、单项重试 | `app.js`, `web_submission_batch.py` | 每个失败项有 action |
| 检查详情首层展示 suggestion | `views/detail.js` | 阻断项直接可读 |
| 状态卡增加下一步描述 | `app.js` | 用户可从状态卡判断动作 |

### Phase 4：移动端专用展示（3-5 天）

| 任务 | 文件 | 验收 |
|---|---|---|
| 手机端表格改卡片列表 | `app.js`, CSS | 390px 无横向滚动且信息完整 |
| 主操作 sticky bottom bar | `index_template.html`, CSS | 手机端可随时开始/停止/同步 |
| 图表入口改为分段控件 | `app.js`, `views/charts.js` | 有数据时图表可发现 |

---

## 8. 结论

BRAIN Alpha Ops 的业务功能面已经比较完整，且关键阻断问题已经修复：SSE/轮询反馈、检查结果恢复、失败提交明细、phase 标签、health 路由都具备基础闭环。下一阶段的最大收益来自 UX 收敛，而不是继续堆功能。

建议优先投入 **Phase 1 + Phase 2**：它们改动范围小、风险低，但能显著提升可达性、移动端可用性和核心路径清晰度。完成后，再把批量失败恢复和检查建议做深，产品会从“专家能用”进一步变成“长时间运行时也稳、出错时知道怎么救”的生产工具。

