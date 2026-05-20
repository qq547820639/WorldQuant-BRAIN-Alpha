# UI/UX 深度评审：BRAIN Alpha Ops 前端

**评审标准**：UI/UX Pro Max 框架 + WCAG 2.1 AA + UX 准则（99 项）+ Web 界面模式（31 项）  
**日期**：2026-05-15  
**上下文**：基于 design-critique、accessibility-audit 及用户业务场景审计的交叉扩展

---

## 0. 设计系统对齐度评估

UI/UX Pro Max 对"金融 Dashboard + 量化研究"场景推荐 **Dark Mode (OLED)**，但当前系统采用 **Light Mode (Teal + White)**。

| 维度 | 推荐（Dark Mode OLED） | 当前实现（Light Teal） | 对齐度 |
|------|----------------------|----------------------|--------|
| 主色调 | #0F172A (深蓝黑) | #0f766e (teal) | 异向 |
| 背景 | #020617 (深黑) | #eef3f8 (浅蓝灰) | 异向 |
| CTA | #22C55E (绿) | #0f766e (teal) | 可接受 |
| 正/负指标 | 绿涨红跌 | 绿好红坏 | ✅ |
| 字体 | Fira Code + Fira Sans | Microsoft YaHei + Segoe UI | 可接受 |
| 暗色模式 | Primary | 无暗色切换 | ❌ |

**判断**：当前 Light 方案对内部工具场景 **功能上可用**，但缺失 Dark Mode 在长时间盯盘场景中是重大 UX 缺陷。建议增加暗色模式切换。

---

## 1. 完整 UX 准则对照审计（99 项中选取相关项）

### 1.1 导航与布局（#1-#6, #16-#21）

| 准则 | 现状 | 判定 |
|------|------|------|
| #1 平滑滚动 | 未设置 `scroll-behavior: smooth` | ❌ Minor |
| #2 固定导航补偿 | header 高度 66px，main 有 `calc(100vh - 66px)` | ✅ |
| #3 Active State | 状态卡 `.insight-item.active` 有 teal 边框+背景 | ✅ |
| #4 返回按钮 | SPA 无多页面导航，不适用 | N/A |
| #5 深度链接 | 视图状态仅存内存，URL 不变 | ❌ High |
| #19 内容跳变 | 表格异步加载时无骨架屏 | ❌ Medium |
| #20 Viewport 单位 | 使用 `100vh` 在移动端可能溢出 | ⚠ Medium |

**关键发现**：**#5 深度链接缺失**意味着用户无法分享/书签特定视图（如"可提交"Tab），刷新后丢失全部页面状态。对于需要协作的内部工具，这是显著体验缺陷。

### 1.2 交互动画（#7-#14）

| 准则 | 现状 | 判定 |
|------|------|------|
| #7 动画过载 | Toast/按钮/spinner 各有动画，总量可控 | ✅ |
| #8 动画时长 | 按钮 `160ms`、模态 `260ms`，在 150-300ms 范围内 | ✅ |
| #9 prefers-reduced-motion | **未设置媒体查询** | ❌ High |
| #10 加载状态 | Spinner overlay + 进度条 + Toast，完整 | ✅ |
| #11 Hover vs Tap | 按钮主要依赖 `onclick`，hover 仅为增强 | ✅ |

**关键发现**：**#9 reduced-motion 缺失**——动画敏感用户会受 Toast 弹入、按钮 lift、进度条渐变的影响。修复成本低，应在 `<style>` 中添加：

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
}
```

### 1.3 触控与移动（#22-#26）

| 准则 | 现状 | 判定 |
|------|------|------|
| #22 触控目标 | 按钮 34px，低于 44px 建议 | ❌ Major |
| #23 触控间距 | 按钮 `gap: 8-10px`，满足 8px 最低要求 | ✅ |
| #25 Tap 延迟 | 未设置 `touch-action: manipulation` | ❌ Medium |

### 1.4 反馈系统（#32-#35, #78-#84）

| 准则 | 现状 | 判定 |
|------|------|------|
| #32 加载按钮防重复 | `submitInFlight` 标志 + `setSubmitBusy()` | ✅ |
| #33 错误反馈 | Toast error + 状态栏更新，但部分场景静默 | ⚠ Medium |
| #34 成功反馈 | Toast success + 视图切换 | ✅ |
| #35 确认弹窗 | `confirmAction()` 对删除/提交显示确认 | ✅ |
| #78 加载指示器 | Spinner overlay + 进度条 覆盖同步/检查场景 | ✅ |
| #79 空状态 | 各组 `emptyText()` 提供上下文提示 | ✅ |
| #80 错误恢复 | 提交失败仅 Toast，无"重试"按钮 | ❌ Medium |
| #81 进度指示器 | 云端同步/批量检查均有进度条 + ETA | ✅ |
| #82 Toast 通知 | 4 种类型，3-5 秒自动消失 | ✅ |

### 1.5 表单与输入（#54-#63）

| 准则 | 现状 | 判定 |
|------|------|------|
| #54 输入标签 | 所有 input/select 均有 `<label>` | ✅ |
| #57 输入类型 | `type="number"` 用于 decay/truncation | ✅ |
| #58 自动填充 | 未设置 `autocomplete` 属性 | ❌ Medium |

### 1.6 可访问性（#36-#45）

| 准则 | 现状 | 判定 |
|------|------|------|
| #36 色彩对比度 | 4 处未达标（见无障碍审计） | ⚠ Medium |
| #37 非仅颜色传递信息 | 状态使用 颜色+图标+文字 三重编码 | ✅ |
| #39 标题层级 | h1(header) → h2(section title) → 无 h3 表格标题 | ⚠ Medium |
| #40 ARIA 标签 | 图标按钮/状态卡缺失 `aria-label` | ❌ High |
| #41 键盘导航 | 表格行不可 Tab | ❌ Critical |
| #43 表单标签 | 所有 input 有 `for` 关联 label | ✅ |
| #44 错误播报 | Toast 无 `role="alert"` | ❌ High |

---

## 2. Web 界面模式审计（31 项中选取相关项）

| 模式 | 现状 | 判定 |
|------|------|------|
| #1 图标按钮标签 | 关闭按钮无 `aria-label` | ❌ Critical |
| #3 键盘处理 | 表格行仅 `onclick`，无 `onkeydown` | ❌ High |
| #4 语义 HTML | 使用 `<button>`/`<table>`/`<header>`/`<main>` | ✅ |
| #5 Aria Live | 进度更新无 `aria-live` | ❌ Medium |
| #7 可见焦点态 | `input:focus`/`select:focus` 有 ring，但按钮无 | ⚠ Medium |
| #8 不移除 outline | 未使用 `outline: none`（好） | ✅ |
| #11 语义输入类型 | `type="email"` 等未使用 | ❌ Low |
| #14 提交按钮 | `submitInFlight` 控制，但按钮可能 disable | ⚠ Medium |
| #15 内联错误 | 表单验证依赖 Toast，非字段内联 | ❌ Medium |
| #21 URL 反映状态 | 视图切换不更新 URL | ❌ High |
| #27 不禁用缩放 | viewport 未包含 `maximum-scale` | ✅ |

---

## 3. 图表选型审计

当前使用 Chart.js 4.4.0 渲染 4 张图表：

| 图表 | 当前类型 | 推荐类型 | 对齐度 |
|------|---------|---------|--------|
| 评分趋势 | 折线图 | ✅ 折线图（Trend Over Time） | ✅ |
| Sharpe 分布 | 折线图? | ❌ 应使用 直方图/Box Plot | ❌ |
| 门禁通过率 | 饼图? | ⚠ 饼图可接受，堆叠柱状图更好 | ⚠ |
| Turnover 质量目标 | 折线图? | ✅ 折线图/散点图 | ✅ |

**关键发现**：Sharpe 分布图使用折线图不符合统计学最佳实践。分布数据应用直方图或箱线图展示。

---

## 4. 用户旅程映射

### 4.1 Happy Path（当前覆盖良好）

```
登录 → 同步云端 → 开始生产 → 候选池 → 等待回测 → 回测中 → 达标 → 检查 → 可提交 → 提交 → 已提交
```

每一步都有对应的视图卡、进度条、状态状态。

### 4.2 Unhappy Path（当前缺口）

| 旅程阶段 | 异常场景 | 用户当前体验 | 理想体验 |
|---------|---------|------------|---------|
| 批量提交 | 部分失败 | "成功 X，失败 Y"，无明细 | 展开失败列表 + 每项原因 + 单条重试 |
| 提交 | BLOCKED | 生命周期有记录，视图找不到 | 失败 Tab 下可见，附阻断原因 + 处理指引 |
| 检查 | 刷新后 | 检查结果丢失，需重新检查 | 自动恢复上次检查结果 |
| 配置 | Alpha Type | 只有 REGULAR | 下拉包含所有 PRD 要求的类型 |
| 诊断 | 检查失败 | `production_gate` 等技术名 | 中文名称 + 含义 + 建议操作 |

### 4.3 状态流转视觉化

```
            ┌──────────┐
            │  候选池   │ ← 生产自动填充
            └────┬─────┘
                 │ 本地预筛通过
            ┌────▼─────┐
            │ 等待回测  │
            └────┬─────┘
                 │ 排序分 Top N
            ┌────▼─────┐
            │  回测中   │ → 并发限流/失败 → 回到等待回测
            └────┬─────┘
                 │ 官方回测完成
          ┌──────┴──────┐
     ┌────▼────┐  ┌─────▼─────┐
     │  达标   │  │  不达标   │ ← 回溯优化
     └────┬────┘  └───────────┘
          │ 检查通过
     ┌────▼────┐
     │ 可提交  │ → 检查过期 → 需复检
     └────┬────┘
          │ 提交成功/被阻断
     ┌────▼────┐  ┌──────────┐
     │ 已提交  │  │ BLOCKED  │ ← 当前不在失败视图！❌
     └─────────┘  └──────────┘
```

---

## 5. 组件级审计

### 5.1 状态卡 (InsightCard)

```
✅ 做得好：
  - 激活态视觉反馈清晰（teal 边框+背景）
  - 数字 + 标签 + 备注 三层信息架构
  - cursor: pointer + hover lift

❌ 需改进：
  - 无 aria-label / role="button" 明确声明
  - 无键盘 Enter/Space 触发
```

### 5.2 表格 (CandidateTable)

```
✅ 做得好：
  - 粘性表头（position: sticky）
  - 斑马纹交替行
  - hover 高亮
  - 排序分可视化（score-badge）

❌ 需改进：
  - 行无 tabindex，键盘不可操作 ← Critical
  - 无 aria-label / caption
  - 无虚拟滚动，候选超过 300 行时性能下降
```

### 5.3 弹窗 (DetailModal)

```
✅ 做得好：
  - 遮罩层 + 面板 两层结构
  - 滚动内容 + 粘性标题
  - close 按钮视觉清晰

❌ 需改进：
  - 无 role="dialog" aria-modal="true"
  - 关闭后焦点不回到触发元素
  - 无 Esc 关闭
  - 背景内容仍可 Tab
```

### 5.4 进度条 (Progress Track)

```
✅ 做得好：
  - 百分比填充 + 文字元数据
  - 不同状态不同颜色（warn/bad）
  - ETA 预估

❌ 需改进：
  - 无 aria-valuenow/aria-valuemin/aria-valuemax
  - warn/bad 填充纯色，色觉障碍用户依赖颜色
  - 无 aria-live 更新播报
```

### 5.5 Toast 通知

```
✅ 做得好：
  - 4 种状态（success/error/warning/info）
  - 动画进入/退出（260ms/200ms）
  - 点击关闭
  - 堆叠布局（新消息在上）

❌ 需改进：
  - 无 role="alert"（error）或 aria-live="polite"（info）
  - warning Toast 对比度 4.42:1 差 0.08
```

---

## 6. 信息架构审计

| 层级 | 当前结构 | 建议 |
|------|---------|------|
| L1 全局 | Header（标题 + 用户信息）+ Sidebar + Main | ✅ 合理 |
| L2 监控 | Insight 卡 → 图表 → Monitor（统计+槽位） | ✅ 合理 |
| L3 操作 | Toolbar（搜索+排序）→ FilterBar → ModuleActions → 表格 | ✅ 合理 |
| L4 详情 | Modal（详情 / 云端 / 生命周期 / 槽位） | ✅ 合理 |
| **缺失** | **事件日志 Tab**（策略切换/刷新失败/收敛停滞） | ❌ 需要新增 |
| **缺失** | **批量操作面板**（提交失败明细展开） | ❌ 需要新增 |

---

## 7. 设计系统 Token 补全建议

当前系统使用 CSS 自定义属性，结构良好但 Token 粒度可细化：

```css
:root {
  /* ── 当前已有 ── */
  --bg, --panel, --soft, --text, --muted, --line,
  --accent, --accent-soft, --good, --warn, --bad,
  --blue, --blue-soft, --amber-soft, --red-soft,
  --shadow, --shadow-soft

  /* ── 建议新增 ── */
  --radius-sm: 4px;
  --radius-md: 6px;
  --radius-lg: 8px;
  --radius-xl: 12px;
  --radius-full: 999px;

  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 12px;
  --space-lg: 16px;
  --space-xl: 24px;

  --text-xs: 11px;
  --text-sm: 12px;
  --text-base: 13px;
  --text-md: 14px;
  --text-lg: 16px;
  --text-xl: 20px;

  /* ── Dark Mode ── */
  @media (prefers-color-scheme: dark) {
    --bg: #0f172a;
    --panel: #1e293b;
    --soft: #1e293b;
    --text: #f1f5f9;
    --muted: #94a3b8;
    --line: #334155;
    /* ... 完整映射 ... */
  }
}
```

---

## 8. 综合发现汇总

### P0 — Critical（4 项，跨审计汇总）

| # | 问题 | 来源 |
|---|------|------|
| 1 | 表格行无键盘访问 | A11y #6, UI/UX #41, Web #3 |
| 2 | 批量提交失败无明细 | 用户审计, Design #1 |
| 3 | BLOCKED 不入失败视图 | 用户审计, Design #2 |
| 4 | 检查结果刷新丢失 | 用户审计, Design #4 |

### P1 — High（10 项）

| # | 问题 | 来源 |
|---|------|------|
| 5 | 状态码映射不完整 | 用户审计, Design #3 |
| 6 | 检查失败原因偏技术化 | 用户审计, Design #6 |
| 7 | 特殊 Alpha Type 入口缺失 | 用户审计, Design #5 |
| 8 | 无 Dark Mode | UI/UX 设计系统 |
| 9 | 无 prefer-reduced-motion | UI/UX #9 |
| 10 | URL 不反映状态 | UI/UX #5, Web #21 |
| 11 | 弹窗缺 role/focus trap | A11y #7/8/13, UI/UX #41 |
| 12 | 缺 ARIA 地标 | A11y #14, Web #5 |
| 13 | Toast 缺 aria-live/role | A11y #11, Web #5 |
| 14 | 触控目标 34px → 44px | A11y #9, UI/UX #22 |

### P2 — Medium（7 项）

| # | 问题 | 来源 |
|---|------|------|
| 15 | warning 对比度 4.42:1 | A11y #1 |
| 16 | muted on bg 对比度 4.26:1 | A11y #2 |
| 17 | border 对比度 1.35:1 | A11y #3 |
| 18 | 无骨架屏/加载占位 | UI/UX #19 |
| 19 | 文档互斥 vs 代码并行矛盾 | 用户审计, Design P2 |
| 20 | 事件日志无前端视图 | 用户审计, Design P2 |
| 21 | Chart.js CDN 依赖 | 用户审计, Design P2 |

---

## 9. 修复路线图

```
Phase 1：提交前（上线阻断）
  ├─ #1 表格行键盘访问
  ├─ #2 批量提交失败明细
  ├─ #3 BLOCKED 入失败视图
  └─ #4 检查结果持久化恢复

Phase 2：QA 阶段
  ├─ #5 状态码全量中文化
  ├─ #6 检查失败原因人性化
  ├─ #7 特殊 Alpha Type 入口
  ├─ #12 ARIA 地标 + #11 弹窗角色
  └─ #13 Toast aria-live

Phase 3：正式版前
  ├─ #8 Dark Mode
  ├─ #9 prefer-reduced-motion
  ├─ #10 URL 状态同步
  ├─ #14 触控目标扩大
  ├─ #15-17 对比度修正
  └─ #18-21 骨架屏/事件中心/离线图表
```

---

## 10. 结论

三份评审（用户业务审计 + 设计评审 + 无障碍审计）交叉验证后，**结论一致**：

- **主路径（Happy Path）** 覆盖良好，视觉设计成熟
- **非主路径（Unhappy Path）** 在 4 个 Critical 维度未闭环：失败反馈、阻断诊断、键盘可用性、状态持久化
- **行业对齐**：针对金融量化 Dashboard 场景，推荐 Dark Mode 但当前缺失
- **上线建议**：Phase 1（4 项 Critical）修复后进入 QA，Phase 2（6 项 High）修复后正式上线
