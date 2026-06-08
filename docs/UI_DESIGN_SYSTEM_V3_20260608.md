# BRAIN Alpha Ops — UI 设计系统 v3.0

> **设计师**：UI Designer
> **日期**：2026-06-08
> **基准**：Terminal Precision v2.0（暗色金融终端）
> **目标**：全面适配 4 阶段渐进式导航 + 新系统架构

---

## 目录

1. [设计令牌更新](#1-设计令牌更新)
2. [布局架构](#2-布局架构)
3. [导航系统](#3-导航系统)
4. [核心组件设计](#4-核心组件设计)
5. [关键页面设计](#5-关键页面设计)
6. [交互模式与状态](#6-交互模式与状态)
7. [响应式策略](#7-响应式策略)
8. [无障碍合规](#8-无障碍合规)
9. [实现规范](#9-实现规范)

---

## 1. 设计令牌更新

### 1.1 新增令牌（基于现有 Terminal Precision 体系）

在现有 Tailwind 配置基础上，新增以下令牌：

```javascript
// 新增: Phase 状态色
phase: {
  connect:   { fill: "oklch(0.65 0.06 265 / 0.12)", stroke: "oklch(0.65 0.10 265)", text: "oklch(0.75 0.08 268)" },
  discover:  { fill: "oklch(0.58 0.06 245 / 0.12)", stroke: "oklch(0.58 0.12 245)", text: "oklch(0.68 0.10 248)" },
  evaluate:  { fill: "oklch(0.52 0.06 155 / 0.12)", stroke: "oklch(0.52 0.10 155)", text: "oklch(0.62 0.10 160)" },
  ready:     { fill: "oklch(0.65 0.06 85 / 0.12)",  stroke: "oklch(0.65 0.10 85)",  text: "oklch(0.75 0.10 88)" },
  locked:    { fill: "oklch(0.38 0.005 45 / 0.08)", stroke: "oklch(0.38 0.006 45)", text: "oklch(0.38 0.006 45)" },
},

// 新增: 状态流转色 (Status Flow)
flow: {
  active:   "oklch(0.52 0.10 155)",   // 当前阶段
  pending:  "oklch(0.58 0.12 245)",   // 待解锁
  complete: "oklch(0.52 0.10 155)",   // 已完成
  blocked:  "oklch(0.48 0.12 22)",    // 阻断
  empty:    "oklch(0.38 0.006 45)",   // 未开始
}

// 新增: 更细粒度的 Surface Elevation（暗色主题需要更多层次）
surface: {
  root:     "oklch(0.085 0.006 45)",   // 页面背景（现有）
  1:        "oklch(0.100 0.007 45)",   // 侧边栏、面板（现有）
  2:        "oklch(0.115 0.007 45)",   // 顶栏、状态栏（现有）
  3:        "oklch(0.135 0.008 45)",   // 卡片、hover（现有）
  hover:    "oklch(0.155 0.008 45)",   // 行 hover（现有）
  active:   "oklch(0.175 0.009 45)",   // 选中（现有）
  elevated: "oklch(0.125 0.007 45)",   // 新增: 阶段卡片
  overlay:  "oklch(0.085 0.006 45 / 0.92)", // 新增: 半透明覆盖
}
```

### 1.2 令牌使用映射

```
旧令牌                    新用途                    模块
─────────────────────────────────────────────────────────
surface.1              →  侧边栏背景              Sidebar
surface.elevated       →  阶段卡片（新）           PhaseShell
phase.connect.*        →  Phase 0 连接阶段色       Sidebar + PhaseShell
phase.discover.*       →  Phase 1 候选发现色       Sidebar + PhaseShell
phase.evaluate.*       →  Phase 2 评估验证色       Sidebar + PhaseShell
phase.ready.*          →  Phase 3 提交就绪色       Sidebar + PhaseShell
phase.locked.*         →  未解锁阶段（灰色）       Sidebar
flow.*                 →  状态流转指示器           StepGuide + StatusFlowDiagram
```

---

## 2. 布局架构

### 2.1 桌面端布局（>= 1024px）

```
┌──────────────────────────────────────────────────────────────┐
│  TopBar (44px fixed)                                        │
│  ● 已连接 · Phase 1 — 候选发现    [0% scan]     PRODUCTION  │
├──────────────┬───────────────────────────────────────────────┤
│ Sidebar      │  Main Content                                │
│ (240px fixed)│                                              │
│              │  ┌──────────────────────────────────────────┐│
│  B Alpha Ops │  │ PhaseShell (当前阶段包装器)               ││
│              │  │  ┌─────────────────────────────────────┐ ││
│ ▼ 连接与就绪 │  │  │ StepGuide (条件: Phase < 3)         │ ││
│  · 凭据认证   │  │  │  □ 连接  □ 同步  □ 搜索  ■ 评分    │ ││
│  · 云端同步   │  │  └─────────────────────────────────────┘ ││
│              │  │                                           ││
│ ▼ 候选发现   │  │  ┌─────────────────────────────────────┐ ││
│  · 生产搜索   │  │  │ PageContent (当前阶段主内容)        │ ││
│  · 候选管理   │  │  │                                     │ ││
│              │  │  │                                     │ ││
│ ▼ 评估与验证 │  │  │                                     │ ││
│  · 科学评分   │  │  │                                     │ ││
│  · 回测监控[2]│  │  └─────────────────────────────────────┘ ││
│  · 质量门禁   │  └──────────────────────────────────────────┘│
│              │                                              │
│ ▶ 提交就绪   │  ToastArea (fixed bottom-right, z-1000)     │
│              │                                              │
│ ─ 工具 ─     │                                              │
│  · 运行总览   │                                              │
│  · 云端快照   │                                              │
│  · 续跑记录   │                                              │
│  · 系统配置   │                                              │
│              │                                              │
│ U operator   │                                              │
├──────────────┴──────────────────────────────────────────────┤
│  StatusBar (28px fixed)                                     │
│  ● BRAIN API · runtime: production · v3.0 · 本地非提交      │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 CSS Grid 更新

```css
/* 旧: 220px sidebar */
.app-shell {
  grid-template-columns: 220px 1fr;
}

/* 新: 240px sidebar（容纳阶段折叠面板） */
@media (min-width: 1024px) {
  .app-shell {
    grid-template-columns: 240px 1fr;
  }
}
```

---

## 3. 导航系统

### 3.1 侧边栏设计

#### 阶段组（PhaseGroup）组件

```
┌──────────────────────┐
│ ▼  连接与就绪         │  ← Phase group header (always visible)
│      ● 已完成          │  ← Phase status indicator
├──────────────────────┤
│    凭据与认证          │  ← NavItem
│    云端同步            │  ← NavItem
│                      │
│ ▼  候选发现           │
│      ● 进行中          │
├──────────────────────┤
│    生产搜索            │
│    候选管理    12      │  ← Badge
│                      │
│ ▶  评估与验证         │  ← Collapsed (not yet reached)
│                      │
│ ▶  提交就绪           │  ← Collapsed (locked)
└──────────────────────┘
```

#### CSS 规范

```css
/* Phase Group */
.phase-group {
  border-bottom: 0.5px solid var(--color-border-subtle);
}
.phase-group:last-of-type { border-bottom: none; }

.phase-group-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px 6px;
  cursor: pointer;
  user-select: none;
  transition: background-color 120ms;
  min-height: 36px;
}
.phase-group-header:hover {
  background-color: oklch(0.155 0.008 45);
}

.phase-group-chevron {
  width: 14px; height: 14px;
  transition: transform 200ms ease;
  opacity: 0.5;
  flex-shrink: 0;
}
.phase-group.is-expanded .phase-group-chevron {
  transform: rotate(90deg);
}

.phase-group-label {
  font-size: 12px;
  font-weight: 500;
  color: oklch(0.72 0.005 45);
  flex: 1;
}
.phase-group.is-locked .phase-group-label {
  color: oklch(0.38 0.006 45);
}

.phase-group-status {
  font-size: 10px;
  font-weight: 500;
  padding: 1px 6px;
  border-radius: 3px;
}
/* Status colors mapped to phase.status tokens */
.phase-group-status.complete { color: oklch(0.62 0.10 160); background: oklch(0.52 0.06 155 / 0.12); }
.phase-group-status.active   { color: oklch(0.75 0.08 268); background: oklch(0.65 0.06 265 / 0.12); }
.phase-group-status.pending  { color: oklch(0.52 0.006 45); background: oklch(0.38 0.005 45 / 0.08); }
.phase-group-status.blocked  { color: oklch(0.58 0.12 25); background: oklch(0.48 0.12 22 / 0.12); }

/* NavItem (unchanged from current, just scoped under phase-group) */
.phase-group .sidebar-nav-item {
  padding-left: 36px; /* indented under group */
}
```

### 3.2 侧边栏数据模型

```typescript
interface PhaseGroup {
  id: PhaseId;                    // 'connect' | 'discover' | 'evaluate' | 'ready'
  label: string;                  // '连接与就绪'
  status: 'locked' | 'pending' | 'active' | 'complete' | 'blocked';
  items: NavItem[];               // 阶段内的导航项
  expanded: boolean;              // 当前是否展开
  icon: string;                   // 阶段图标（SVG path）
}

interface NavItem {
  id: string;                     // 路由 ID
  label: string;                  // 显示名称
  badge?: string | number;        // 徽章
  badgeTone?: 'neutral' | 'positive' | 'warning' | 'info';
}
```

### 3.3 全局工具区

```
┌──────────────────────┐
│ ── 工具 ──            │  ← section divider
│    运行总览            │
│    云端快照   25.5k    │  ← dynamic badge
│    续跑记录            │
│    系统配置            │
└──────────────────────┘
```

不变，但移到阶段组下方，用分隔线隔开。

### 3.4 移动端底部 Tab

```html
<nav class="mobile-tab-bar" role="navigation" aria-label="移动端导航">
  <button class="mobile-tab" data-phase="connect" aria-current="false">
    <svg>...</svg>
    <span>连接</span>
  </button>
  <button class="mobile-tab" data-phase="discover" aria-current="true">
    <svg>...</svg>
    <span>候选</span>
  </button>
  <button class="mobile-tab" data-phase="evaluate" aria-current="false">
    <svg>...</svg>
    <span>评估</span>
  </button>
  <button class="mobile-tab" data-phase="tools" aria-current="false">
    <svg>...</svg>
    <span>工具</span>
  </button>
</nav>
```

```css
.mobile-tab-bar {
  display: none;
  position: fixed;
  bottom: 0;
  left: 0; right: 0;
  height: 56px;
  background: oklch(0.100 0.007 45);
  border-top: 0.5px solid oklch(0.22 0.007 45);
  z-index: 300;
  grid-template-columns: repeat(4, 1fr);
  align-items: center;
  padding: 0 4px 4px;
  /* safe area for notched devices */
  padding-bottom: max(4px, env(safe-area-inset-bottom));
}
@media (max-width: 1023px) {
  .mobile-tab-bar { display: grid; }
  .app-main { padding-bottom: 72px; } /* avoid content hidden behind tab bar */
}

.mobile-tab {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 6px 4px;
  background: transparent;
  border: none;
  color: oklch(0.52 0.006 45);
  font-size: 10px;
  font-weight: 500;
  cursor: pointer;
  min-height: 44px; /* WCAG touch target */
  transition: color 120ms;
}
.mobile-tab svg { width: 20px; height: 20px; opacity: 0.6; }
.mobile-tab[aria-current="true"] { color: oklch(0.65 0.14 80); }
.mobile-tab[aria-current="true"] svg { opacity: 1; }
```

---

## 4. 核心组件设计

### 4.1 PhaseShell（阶段包装器）

```
┌──────────────────────────────────────────────────────────┐
│  Phase 1 — 候选发现                         ● 进行中     │
│  至少发现 1 个候选后解锁下一阶段                          │
├──────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────┐ │
│  │  □ 连接  →  □ 同步  →  ■ 搜索  →  □ 评分  →  □ 提交 │ │
│  │  已完成    已完成     进行中    待解锁    待解锁       │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                          │
│  (page content)                                          │
└──────────────────────────────────────────────────────────┘
```

```css
.phase-shell {
  border-radius: 8px;
  border: 0.5px solid oklch(0.22 0.007 45);
  background: oklch(0.100 0.007 45);
  overflow: hidden;
  margin-bottom: 16px;
}
.phase-shell-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 0.5px solid oklch(0.22 0.007 45);
}
.phase-shell-title {
  font-size: 13px;
  font-weight: 500;
  color: oklch(0.92 0.003 45);
}
.phase-shell-subtitle {
  font-size: 12px;
  color: oklch(0.52 0.006 45);
  margin-top: 2px;
}
.phase-shell-body {
  padding: 16px;
}
```

### 4.2 StepGuide（步骤引导器）

```
□ 连接    ➜    □ 同步    ➜    ■ 搜索    ➜    ○ 评分    ➜    ○ 提交
已完成         已完成          进行中           待解锁          待解锁
```

```css
.step-guide {
  display: flex;
  align-items: flex-start;
  gap: 0;
  padding: 12px 16px;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

.step {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  position: relative;
}

.step-indicator {
  width: 24px; height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 500;
  border: 1.5px solid;
  transition: all 200ms;
}

/* States */
.step.complete .step-indicator {
  background: oklch(0.52 0.06 155 / 0.15);
  border-color: oklch(0.52 0.10 155);
  color: oklch(0.62 0.10 160);
}
.step.active .step-indicator {
  background: oklch(0.65 0.07 80 / 0.15);
  border-color: oklch(0.65 0.14 80);
  color: oklch(0.65 0.14 80);
  animation: pulse-step 2s ease-in-out infinite;
}
.step.pending .step-indicator {
  background: transparent;
  border-color: oklch(0.38 0.006 45);
  color: oklch(0.38 0.006 45);
}

.step-label {
  font-size: 11px;
  color: oklch(0.52 0.006 45);
  white-space: nowrap;
}
.step.complete .step-label { color: oklch(0.62 0.10 160); }
.step.active .step-label   { color: oklch(0.65 0.14 80); font-weight: 500; }

.step-connector {
  width: 28px; height: 1px;
  background: oklch(0.28 0.008 45);
  margin: 0 4px;
  flex-shrink: 0;
  align-self: center;
}
.step-connector.complete { background: oklch(0.52 0.10 155); }

@keyframes pulse-step {
  0%, 100% { box-shadow: 0 0 0 0 oklch(0.65 0.14 80 / 0.3); }
  50%      { box-shadow: 0 0 0 4px oklch(0.65 0.14 80 / 0); }
}
```

### 4.3 TopBar 连接状态

```
旧:
  BRAIN Alpha Ops / 运行总览    [43% 2:15]  PRODUCTION  ● 已连接

新:
  ● 已连接  ·  Phase 2 · 评估与验证    [43%]  PRODUCTION  Alex
  ─────────────────────────────────────────────────────────
  ↑ 独立状态        ↑ 阶段指示器     ↑ 任务mini  ↑ 用户
```

```css
.topbar-connection {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 500;
}
.topbar-connection.connected { color: oklch(0.62 0.10 160); }
.topbar-connection.disconnected { color: oklch(0.58 0.12 25); }
.topbar-connection.syncing { color: oklch(0.75 0.10 88); }
.topbar-connection .status-dot { width: 7px; height: 7px; }

.topbar-phase {
  font-size: 12px;
  color: oklch(0.52 0.006 45);
}
.topbar-phase strong { color: oklch(0.92 0.003 45); font-weight: 500; }
```

### 4.4 ProgressFeedback 增强（stall 检测）

```
当前状态 — SCAN 停滞:
  ┌──────────────────────────────────────────┐
  │  扫描云端 Alpha                          │
  │  0 / — 条  ·  已耗时 12s                 │
  │  ⚡ BRAIN 服务器仍在响应中，请耐心等待     │  ← 新增 stall 提示
  │  ─────────────────────────────────────── │
  │  ░░░░░░░░░░░░░░░░░░░░░░  (不确定进度)    │
  │                                          │
  │  [停止同步]                               │
  └──────────────────────────────────────────┘

错误状态 — 带恢复:
  ┌──────────────────────────────────────────┐
  │  同步失败                                │
  │  官方上下文刷新超时，请稍后重试。          │
  │  ─────────────────────────────────────── │
  │  ████████████████████████  100%          │
  │                                          │
  │  [重试]  [缩小范围(1d)]  [查看日志]        │  ← 多个恢复选项
  └──────────────────────────────────────────┘
```

---

## 5. 关键页面设计

### 5.1 Dashboard（运行总览）

```
┌──────────────────────────────────────────────────────────────┐
│  运行总览                                                    │
│  当前阶段: 评估与验证  ·  上次同步: 12:30  ·  云端: 25,549   │
├──────────────────────────────────────────────────────────────┤
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐│
│  │ 同步状态  │ │ 候选池    │ │ 评分      │ │ 回测             ││
│  │ ● 已更新  │ │  3 活跃   │ │  2 已评分  │ │  2/8 slots      ││
│  │ 25,549    │ │  0 提交   │ │  73.4 均分 │ │  1 pending      ││
│  └──────────┘ └──────────┘ └──────────┘ └──────────────────┘│
│                                                              │
│  ┌──────────────────────────────────────────────────────────┐│
│  │  快速操作                                          [收起] ││
│  │  [同步云端] [生产搜索] [批量检查] [查看阻断]              ││
│  └──────────────────────────────────────────────────────────┘│
│                                                              │
│  ┌──────────────────────────────────────────────────────────┐│
│  │  最近活动                                          [更多] ││
│  │  12:30  云端同步完成 +25,549                            ││
│  │  12:25  候选 C47a3f 评分 73.4                           ││
│  │  12:20  回测 slot #3 完成                               ││
│  └──────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────┘
```

### 5.2 Phase 0 — 连接与就绪（凭据 + 同步）

```
┌──────────────────────────────────────────────────────────────┐
│  Phase 0 — 连接与就绪                         ● 准备中       │
│  连接 BRAIN 账户并同步云端数据                               │
├──────────────────────────────────────────────────────────────┤
│  □ 凭据  →  ■ 连接  →  ○ 同步  →  ○ 就绪                     │
│  已完成      进行中     待解锁     待解锁                     │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─ 凭证与连接 ──────────────────────────────────────────┐  │
│  │  账户邮箱  [________________________]                 │  │
│  │  密码      [________________________]                 │  │
│  │  Token     [________________________]  (可选)         │  │
│  │                                                      │  │
│  │  ℹ️ 凭证仅保留在当前页面                               │  │
│  │                           [测试连接]                  │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌─ 云端同步 ───────────────────────────────────────────┐  │
│  │  ○ 等待连接成功                                       │  │
│  │                                                      │  │
│  │  [开始同步]  (disabled until connected)               │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 5.3 Phase 3 — 提交就绪（阻断复核）

```
┌──────────────────────────────────────────────────────────────┐
│  Phase 3 — 提交就绪                          ● 待审核        │
│  候选通过质量门禁后进入人工审核                              │
├──────────────────────────────────────────────────────────────┤
│  □ 检查  →  ■ 复核  →  ○ 确认                               │
│  已完成      进行中     待审核                               │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─ 阻断项 (2) ──────────────────────────────────────────┐  │
│  │  🔴 云端相似度过高 (0.97)              [修复建议 ▼]     │  │
│  │     → 尝试调整表达式窗口参数                           │  │
│  │     [单项重试]                                        │  │
│  │                                                       │  │
│  │  🟡 换手率偏高 (0.45)                 [修复建议 ▼]     │  │
│  │     → 添加 truncation 参数降低换手                     │  │
│  │     [单项重试]                                        │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌─ 通过候选 (3) ───────────────────────────────────────┐  │
│  │  ✅ C47a3f · score 73.4 · simulate pass              │  │
│  │  ✅ D81b2e · score 68.1 · simulate pass              │  │
│  │  ✅ E92c7a · score 65.0 · simulate pass              │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ⚠️ 本页面不执行真实提交。提交前需人工审核。                 │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 6. 交互模式与状态

### 6.1 通用加载骨架屏（Skeleton）

```css
.skeleton {
  background: linear-gradient(
    90deg,
    oklch(0.135 0.008 45) 25%,
    oklch(0.155 0.008 45) 50%,
    oklch(0.135 0.008 45) 75%
  );
  background-size: 200% 100%;
  animation: skeleton-shimmer 1.5s ease-in-out infinite;
  border-radius: 4px;
}
@keyframes skeleton-shimmer {
  0%   { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.skeleton-text   { height: 14px; width: 60%; margin-bottom: 8px; }
.skeleton-heading { height: 20px; width: 40%; margin-bottom: 12px; }
.skeleton-kpi     { height: 64px; width: 100%; }
.skeleton-row     { height: 36px; width: 100%; margin-bottom: 4px; }
```

### 6.2 空态（Empty State）

```
┌──────────────────────────────────────────┐
│                                          │
│              [empty icon]                │
│                                          │
│           暂无候选 Alpha                  │
│    开始生产搜索以发现新的 Alpha 候选       │
│                                          │
│         [开始生产搜索]                    │
│                                          │
│  提示：请确保已完成云端同步               │
│                                          │
└──────────────────────────────────────────┘
```

```css
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  text-align: center;
}
.empty-state-icon {
  width: 48px; height: 48px;
  margin-bottom: 16px;
  opacity: 0.3;
}
.empty-state-title {
  font-size: 15px;
  font-weight: 500;
  color: oklch(0.72 0.005 45);
  margin-bottom: 8px;
}
.empty-state-description {
  font-size: 13px;
  color: oklch(0.52 0.006 45);
  margin-bottom: 20px;
  max-width: 320px;
  line-height: 1.5;
}
.empty-state-hint {
  font-size: 12px;
  color: oklch(0.38 0.006 45);
  margin-top: 12px;
}
```

### 6.3 错误恢复模式

所有可恢复错误均提供最多 3 个恢复选项，按推荐顺序排列：

```
[重试]  [替代方案]  [查看详情]
primary  secondary   ghost
```

优先级规则：
- 主操作（重试）始终为 primary 按钮
- 降级选项（缩小范围、使用缓存）为 secondary
- 诊断操作（查看日志、联系支持）为 ghost

---

## 7. 响应式策略

### 7.1 断点映射

| 断点 | 宽度 | 侧边栏 | 导航 | 表格 |
|------|------|--------|------|------|
| mobile | < 640px | 隐藏 | 底部 4 Tab | 卡片视图 (3 列) |
| tablet | 640-1023px | 抽屉式覆盖 | 汉堡菜单 | 精简 (5 列) |
| desktop | 1024-1439px | 固定 240px | 全侧栏 | 全列 |
| wide | >= 1440px | 固定 240px | 全侧栏 + 侧面板 | 全列 |

### 7.2 移动端卡片视图

```css
/* 移动端: 表格转为卡片 */
@media (max-width: 639px) {
  .data-table thead { display: none; }
  .data-table, .data-table tbody, .data-table tr, .data-table td {
    display: block;
  }
  .data-table tr {
    margin-bottom: 8px;
    border: 0.5px solid oklch(0.22 0.007 45);
    border-radius: 6px;
    padding: 10px 12px;
    background: oklch(0.100 0.007 45);
  }
  .data-table td {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 4px 0;
    border: none;
    font-size: 13px;
  }
  .data-table td::before {
    content: attr(data-label);
    font-size: 11px;
    color: oklch(0.52 0.006 45);
    text-transform: uppercase;
    font-weight: 500;
    flex-shrink: 0;
    margin-right: 8px;
  }
}
```

---

## 8. 无障碍合规

### 8.1 WCAG 2.1 AA 检查清单

| 要求 | 状态 | 实现 |
|------|------|------|
| 颜色对比度 ≥ 4.5:1 (正文) | ✅ | 正文 #EBEBEB on #1A1A1A = 14.57:1 |
| 颜色对比度 ≥ 3:1 (大文本) | ✅ | 标题满足 |
| 键盘可操作 | ⚠️ | PhaseGroup header + tabindex, NavItem 已支持 |
| 焦点指示器 | ✅ | `:focus-visible` 2px amber 轮廓 |
| ARIA 标签 | ⚠️ | PhaseGroup 需要 `aria-expanded` |
| 跳过导航链接 | ✅ | 已存在 "跳到主内容" |
| 触控目标 ≥ 44px | ❌ | 按钮 32px → 移动端提升至 44px |
| 动画偏好 | ✅ | `prefers-reduced-motion` 已处理 |
| 屏幕阅读器 | ⚠️ | Toast 需要 `role="alert"` |

### 8.2 PhaseGroup ARIA

```html
<button class="phase-group-header"
  role="button"
  aria-expanded="true"
  aria-controls="phase-connect-items">
  <span class="phase-group-chevron" aria-hidden="true">▶</span>
  <span class="phase-group-label">连接与就绪</span>
  <span class="phase-group-status complete" aria-label="已完成">已完成</span>
</button>
<div id="phase-connect-items" role="region" aria-label="连接与就绪 导航项">
  <!-- NavItems -->
</div>
```

---

## 9. 实现规范

### 9.1 文件变更清单

```
新增文件:
  src/components/PhaseShell.tsx         ~60 lines
  src/components/PhaseGroup.tsx         ~80 lines
  src/components/StepGuide.tsx          ~70 lines
  src/components/StatusFlowDiagram.tsx  ~50 lines
  src/components/MobileTabBar.tsx       ~60 lines
  src/components/EmptyState.tsx         ~40 lines
  src/components/SkeletonLoader.tsx     ~30 lines
  src/hooks/usePhaseState.ts            ~50 lines

修改文件:
  src/App.tsx                           ~80 lines (new layout + PhaseShell)
  src/components/Sidebar.tsx            ~120 lines (PhaseGroup accordion)
  src/components/Dashboard.tsx          ~40 lines (simplify)
  src/components/OfficialOperationsPanel.tsx  ~15 lines (retry/stall)
  src/components/ProgressFeedback.tsx   ~20 lines (stall + recovery)
  src/index.css                         ~150 lines (new component styles)
  tailwind.config.js                    ~25 lines (new tokens)

总计: ~890 lines
```

### 9.2 迁移策略

不采用大爆炸式重写。渐进式引入：

1. **Week 1**：Token 更新 + Stall 检测 + 错误恢复（P0 修复）
2. **Week 2**：PhaseGroup + PhaseShell + StepGuide 组件
3. **Week 3**：App.tsx 集成 + Dashboard 精简
4. **Week 4**：MobileTabBar + 响应式卡片视图 + 无障碍 ARIA

每个阶段保持 2155 测试通过，功能不回归。

---

> **设计交付物**：
> - 设计令牌规范（新增 phase/flow/surface.elevated 令牌）
> - 完整 CSS 组件样式（PhaseGroup, StepGuide, EmptyState, Skeleton, MobileTabBar）
> - 5 个关键页面设计（Dashboard, Phase 0, Phase 1, Phase 3, Mobile）
> - 无障碍 ARIA 标注规范
> - 实现优先级和里程碑

---
**UI Designer** | 2026-06-08 | BRAIN Alpha Ops UI Design System v3.0
