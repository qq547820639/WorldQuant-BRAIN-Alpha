# BRAIN Alpha Ops — UX 架构重设计 v3.0

> **架构师**：ArchitectUX  
> **日期**：2026-06-08  
> **基准**：Terminal Precision v2.0（10 模块侧边栏）  
> **目标**：任务导向的渐进式导航，消除 7 个已知流程断点

---

## 目录

1. [当前架构诊断](#1-当前架构诊断)
2. [新信息架构](#2-新信息架构)
3. [导航系统重设计](#3-导航系统重设计)
4. [模块状态机](#4-模块状态机)
5. [组件层级与边界](#5-组件层级与边界)
6. [响应式策略](#6-响应式策略)
7. [断点修复映射](#7-断点修复映射)
8. [实施路线](#8-实施路线)

---

## 1. 当前架构诊断

### 1.1 导航结构问题

```
当前（扁平）
═══════════════════════════════════════════
工作流程                                     工具
───────────────────────────────────────────
官方操作 (web)  运行总览                   续跑记录
候选管理        回测监控                   云端快照
科学评分        质量门禁                   系统配置
阻断复核
───────────────────────────────────────────
              状态栏 (BRAIN API · v2.0)
```

**问题**：
- 7 个工作流项 + 3 个工具项，10 项平铺 — 新用户认知负荷高
- "官方操作" 排在第一位但内部是按钮驱动 — 语义不一致
- "运行总览" 才是真正的入口，却被放在第二位
- 工作流中没有 "连接/认证" 入口 — 凭据埋在 Dashboard 顶部的 CredentialQuickStart
- 工具区混杂：配置（使用前设置）和快照（日常查看）混合

### 1.2 用户流程断点

```
用户旅程           当前体验                断点等级
──────────────────────────────────────────────────
🔌 首次进入        Dashboard + 凭据面板    ⚠️  没有 onboarding，配置裸暴露
🔗 测试连接        按钮反馈明确            ✅  OK
🔄 云端同步        进度停在 0%，无重试     ❌ P0 无恢复路径
📊 查看结果        16 张状态卡            ⚠️  信息密度过高
🔍 候选发现        导航到 Candidates      ✅  OK
📈 评分            需先选候选              ⚠️  空态不够友好
✅ 批量检查        聚合失败无逐项修复      ❌ P1 无单项修复
📤 提交审核        概念断层                ⚠️  "达标 ≠ 可提交" 不清晰
```

### 1.3 状态缺失清单

| 状态类型 | 已覆盖 | 缺失 |
|----------|--------|------|
| 加载中 (loading) | spinner + 文字 | ✅ |
| 空态 (empty) | 表格空态 | ⚠️ 缺少引导行动 |
| 错误 (error) | toast 通知 | ❌ 无恢复引导 |
| 成功 (success) | toast + 数据刷新 | ✅ |
| 进行中 (in-progress) | 进度条 + ETA | ⚠️ 不确定进度缺提示 |
| 超时 (timeout) | 显示错误消息 | ❌ 无重试/取消/日志 |

---

## 2. 新信息架构

### 2.1 三层导航体系

```
第 1 层：阶段导航（Phase Navigation）
  用户当前所在工作阶段，一次只激活一个阶段

第 2 层：阶段内视图（Stage View）
  当前阶段内的具体操作面板

第 3 层：全局工具（Global Tools）
  跨阶段可用的辅助功能
```

### 2.2 阶段定义

```
Phase 0 — 连接与就绪 (Connect & Ready)
├── 凭据管理
├── 连接测试
├── 云端同步（字段/算子/Alpha）
└── 就绪确认
    出口条件：connected=true, context_fresh=true

Phase 1 — 候选发现 (Discover)
├── 生产搜索
├── 候选表（筛选/排序/查看）
├── 本地预筛
└── 池管理
    出口条件：pool_size > 0

Phase 2 — 评估与验证 (Evaluate)
├── 评分仪表盘
├── 门禁检查
├── 回测监控（slots）
├── 收敛追踪
└── 候选详情
    出口条件：scored_count > 0

Phase 3 — 提交就绪 (Ready)
├── 批量检查
├── 阻断复核
├── 逐项修复
└── 提交确认（仅审核，不实际提交）
    出口条件：readiness_passed=true
```

### 2.3 全局工具层

```
始终可访问（与当前阶段无关）
├── 运行总览 / 仪表盘
├── 云端快照
├── 续跑记录
└── 系统配置
```

---

## 3. 导航系统重设计

### 3.1 新侧边栏结构

```
┌─────────────────────┐
│  B  Alpha Ops        │  ← Brand
├─────────────────────┤
│                      │
│  ▼ 连接与就绪        │  ← Phase 0 (collapse)
│    凭据与认证        │
│    云端同步          │
│                      │
│  ▼ 候选发现          │  ← Phase 1
│    生产搜索          │
│    候选管理          │
│                      │
│  ▼ 评估与验证        │  ← Phase 2
│    科学评分          │
│    回测监控  [2/8]   │  ← 动态徽章
│    质量门禁          │
│                      │
│  ▶ 提交就绪          │  ← Phase 3 (collapse until ready)
│                      │
├─────────────────────┤
│  — 工具 —            │
│  运行总览            │
│  云端快照   25.5k    │
│  续跑记录            │
│  系统配置            │
│                      │
├─────────────────────┤
│  U  operator         │
│  本地非提交          │
└─────────────────────┘
```

### 3.2 导航行为规范

#### 阶段折叠规则
- **Phase 0**：始终展开（直到首次连接+同步完成）
- **Phase 1**：Phase 0 完成后自动展开
- **Phase 2**：有候选进入池后自动展开
- **Phase 3**：有候选通过质量门禁后展开，否则折叠

#### 阶段间导航
- 阶段按顺序解锁，不禁止回退
- 跳转到未解锁阶段：显示空态引导，提示前置步骤
- 顶栏始终显示当前阶段名称

#### 徽章系统
| 徽章位置 | 内容 | 更新频率 |
|----------|------|----------|
| 候选管理 | 池中候选数 | 每次搜索/筛选后 |
| 回测监控 | 活跃/总 slot | 每 5s 轮询 |
| 评分 | 已评分候选数 | 每次评分后 |
| 云端快照 | 云端 Alpha 总数 | 每次同步后 |

### 3.3 顶栏重新设计

```
当前:
  BRAIN Alpha Ops / 运行总览    [43% 2:15]  [PRODUCTION]  ● 已连接

改为:
  ● 已连接  ·  BRAIN Alpha Ops  阶段: 评估与验证  [43% 2:15]  PRODUCTION
  ─────────────────────────────────────────────────────────────────
  ↑ 状态明确       ↑ 当前阶段清晰             ↑ 后台任务 mini
```

- **连接状态**：字符级显示（已连接 / 同步中 / 已断开），不再依赖点色区分
- **阶段标签**：见名知义，点击可快速跳转阶段总览
- **任务 mini**：只在有运行中任务时显示，点击回到任务所在阶段

### 3.4 移动端导航

```
桌面端（≥1024px）                    移动端（<1024px）
┌────┬──────────────────┐           ┌──────────────────┐
│    │                  │           │  BRAIN Alpha Ops  │
│ 侧 │   主内容区        │           │  阶段: 评估与验证  │
│ 栏 │                  │           ├──────────────────┤
│    │                  │           │                  │
│ 240│                  │           │   主内容区        │
│ px │                  │           │                  │
│    │                  │           │                  │
└────┴──────────────────┘           ├──────────────────┤
                                    │ ■ 连接  ■ 候选  │  ← 底部 Tab
                                    │ ■ 评估  ■ 工具  │
                                    └──────────────────┘
```

移动端底部 4 Tab：
1. **连接** — 凭据 + 同步状态
2. **候选** — 搜索 + 候选表
3. **评估** — 评分 + 门禁（合并 Phase 2+3）
4. **工具** — 仪表盘 + 快照 + 配置

---

## 4. 模块状态机

### 4.1 通用状态模板

每个可操作模块遵循统一状态模型：

```
                    ┌─────────────────┐
         ┌─────────→│     idle        │←─────────┐
         │          │  (初始/就绪)     │          │
         │          └────────┬────────┘          │
         │                   │ 用户触发操作       │
         │          ┌────────▼────────┐          │
         │          │    loading      │          │
         │          │  (处理中...)    │          │
         │          └───┬───────┬─────┘          │
         │   ┌──────────┘       └──────────┐     │
         │   │ 操作成功                    │ 失败│
         │   ▼                             ▼     │
         │ ┌──────────┐            ┌──────────┐  │
         │ │ success  │            │  error   │  │
         │ │ (已完成)  │            │ (含恢复)  │──┘
         │ └────┬─────┘            └────┬─────┘  "重试"
         │      │ 新操作                  │
         └──────┘                 ┌──────┘ "取消"
                                  │
                                  ▼
                            ┌──────────┐
                            │  idle     │
                            │ (回退就绪) │
                            └──────────┘
```

### 4.2 各模块状态定义

#### Phase 0 — 连接与就绪

```
凭据与认证 (Credentials)
┌──────────────────────────────────────────────────┐
│ idle        │ 显示凭据表单，测试连接按钮          │
│ loading     │ "测试中..." 按钮 loading            │
│ success     │ toast "连接成功" + 解锁 Phase 1     │
│ error       │ toast "连接失败: {reason}"          │
│             │ + "检查账户/密码" 提示              │
│             │ + "重试" 按钮                       │
│             │ token 模式下额外提示 "Token 可能过期"│
│ empty       │ 无凭据：显示 "也可留空使用托管凭证" │
└──────────────────────────────────────────────────┘

云端同步 (Cloud Sync)
┌──────────────────────────────────────────────────┐
│ idle        │ "开始同步" 按钮 + 上次同步时间      │
│ loading     │ 分阶段进度 ([AUTH]→[SCAN]→[MERGE]) │
│             │ + scanned/total 实时计数            │
│             │ + elapsed 计时器                    │
│             │ + ETA 估算（total > 0 时）          │
│             │ + "停止" 按钮                       │
│ stall       │ SCAN 阶段 >10s 无进度 → 追加提示    │
│             │ "BRAIN 服务器仍在响应中..."         │
│ success     │ 完成摘要: scanned/added/updated     │
│             │ + 字段/算子/数据集计数              │
│ error       │ 错误消息 + "重试" + "缩小范围(1d)" │
│             │ + "查看日志" + "联系维护者"          │
│ timeout     │ "同步超时 (≥{elapsed}s)"            │
│             │ + "重试" + "缩小范围(1d)"          │
│             │ + "离线使用默认上下文" 选项         │
│ cancelled   │ "同步已停止" + "重试"               │
└──────────────────────────────────────────────────┘
```

#### Phase 1 — 候选发现

```
候选管理 (Candidates)
┌──────────────────────────────────────────────────┐
│ idle        │ 候选表 + 筛选栏 + "生产搜索" 按钮   │
│ empty       │ 图标 + "暂无候选" + "开始生产搜索"  │
│             │ CTA 按钮（引导首次使用）            │
│ loading     │ "正在生成..." + 进度条              │
│ error       │ "生成失败: {reason}" + "重试"       │
│ success     │ 候选表刷新 + 徽章计数更新           │
└──────────────────────────────────────────────────┘
```

#### Phase 2 — 评估与验证

```
科学评分 (Scoring)
┌──────────────────────────────────────────────────┐
│ no-selection│ 候选表 picker + "请先选择候选" 提示  │
│ loading     │ "加载评分..." spinner              │
│ success     │ 评分仪表盘 (Sharpe/Fitness/...)     │
│ error       │ "评分加载失败" + "重试"             │
│ no-data     │ 候选存在但无评分数据 → "运行检查"    │
└──────────────────────────────────────────────────┘

回测监控 (Backtest Slots)
┌──────────────────────────────────────────────────┐
│ idle        │ Slot 网格 + 状态标记               │
│ empty       │ "无活跃回测" + "empty/complete 状态"│
│ error       │ "回测状态加载失败" + "重试"         │
└──────────────────────────────────────────────────┘

质量门禁 (Quality Gate)
┌──────────────────────────────────────────────────┐
│ empty       │ "先运行批量检查" 引导               │
│ loading     │ "检查中..." + 逐项进度              │
│ success     │ 通过/阻断 列表 + 逐项修复建议       │
│ error       │ "检查失败: {reason}" + "逐项重试"   │
│ partial     │ 部分通过: "X 项通过, Y 项阻断"      │
└──────────────────────────────────────────────────┘
```

#### Phase 3 — 提交就绪

```
阻断复核 (Submission Review)
┌──────────────────────────────────────────────────┐
│ blocked     │ 阻断项列表 + 逐项修复引导           │
│ reviewing   │ "正在加载阻断复核..."               │
│ ready       │ 候选列表 + "进入提交审核" 引导       │
│             │ 明确标注 "此页面不执行真实提交"      │
└──────────────────────────────────────────────────┘
```

---

## 5. 组件层级与边界

### 5.1 布局网格

```
app-shell
├── app-topbar            (固定 44px, z-200)
│   ├── ConnectionStatus   (左)
│   ├── PhaseIndicator     (中)
│   └── RunningJobMini     (右, 条件渲染)
│
├── app-body              (flex row, min-h calc(100vh-44px-28px))
│   ├── app-sidebar        (固定 240px, overflow-y auto)
│   │   ├── SidebarBrand
│   │   ├── SidebarPhase   (可折叠阶段组)
│   │   │   ├── PhaseGroup × 4
│   │   │   └── NavItem × N
│   │   ├── SidebarDivider
│   │   ├── SidebarTools   (全局工具组)
│   │   └── SidebarUser    (底部固定)
│   │
│   └── app-main           (flex-1, min-w-0, overflow-y auto)
│       ├── PageHeader     (当前阶段标题 + 面包屑)
│       ├── PhaseShell     (阶段包装器)
│       │   ├── PhaseProgress   (条件: phase<3)
│       │   └── RouteContent    (react-router / switch)
│       └── ToastArea      (fixed, top-right)
│
└── app-statusbar         (固定 28px, z-100)
    ├── ApiStatus
    └── VersionInfo
```

### 5.2 模块间契约

每个页面组件对外暴露统一接口：

```typescript
interface PageModuleProps {
  // 通用通知
  notify: (type: ToastType, message: string, action?: ToastAction) => void;
  
  // 凭据上下文（可选，需要 API 调用的模块使用）
  credentials?: BrainCredentials;
  
  // 阶段导航
  onNavigateToPhase?: (phase: PhaseId) => void;
  onExport?: (data: ExportPayload) => void;
  
  // 数据依赖（可选注入）
  selectedCandidate?: Candidate;
  jobState?: JobState;
}
```

### 5.3 状态共享

```
AppState (useReducer at App level)
├── phase: PhaseId           // 当前激活阶段
├── connection: {
│     status: 'idle' | 'testing' | 'connected' | 'failed'
│     lastTestedAt: number | null
│   }
├── sync: {
│     status: SyncStatus
│     lastSyncAt: number | null
│     progress: SyncProgress | null
│     error: string | null
│   }
├── candidates: {
│     pool: Candidate[]
│     selectedId: string | null
│     lastSearchAt: number | null
│   }
├── scoring: {
│     scoredIds: Set<string>
│     activeScoreId: string | null
│   }
├── checks: {
│     results: CheckResult[]
│     lastCheckAt: number | null
│   }
└── readiness: {
      eligibleCount: number
      blockers: Blocker[]
      lastReviewAt: number | null
    }
```

---

## 6. 响应式策略

### 6.1 断点定义

| 断点 | 宽度 | 布局 | 侧边栏 | 表格列 |
|------|------|------|--------|--------|
| **mobile** | <640px | 单栏 + 底部 Tab | 隐藏（汉堡菜单） | 精简至 3 列 |
| **tablet** | 640-1023px | 单栏 + 可折叠侧栏 | 覆盖式抽屉 | 4-5 列 |
| **desktop** | 1024-1439px | 侧栏(220px) + 主区域 | 固定 | 全列 |
| **wide** | ≥1440px | 侧栏(240px) + 主区域 | 固定 | 全列 + 侧面板 |

### 6.2 移动端优化原则

1. **首屏优先显示当前阶段的核心操作**，配置/工具下沉
2. **表格**：移动端使用卡片视图替代完整表格（`< 640px`）
3. **按钮最小触控 44px**（当前 34px → 提升）
4. **底部 Tab 固定**，不随滚动消失
5. **长表单折叠**：凭据区在连接成功后自动折叠

### 6.3 关键断点处理

```
Phase 0 (连接页面) 移动端布局：
┌────────────────────┐
│  ● 连接状态         │
│                    │
│  [账户邮箱]        │
│  [密码]            │
│  [Token (可选)]    │
│                    │
│  [测试连接] ← 44px │
│                    │
│  凭证仅保留在页面   │
└────────────────────┘

工具页 移动端底部 Tab：
┌────────────────────┐
│   (主内容)          │
│                    │
├────────────────────┤
│ ■连接 ■候选 ■评估 ■工具│
└────────────────────┘
```

---

## 7. 断点修复映射

### 7.1 修复清单

| ID | 问题 | 修复方案 | 文件 | 行数 |
|----|------|----------|------|------|
| **F-01** | 同步超时无恢复 | `context_refresh` error 绑定 `onRetry` → `startOfficialContextRefresh` | OfficialOperationsPanel.tsx | +3 |
| **F-02** | SCAN 阶段停滞无提示 | 追加超时检测：`elapsed > 10s && scanned == 0` → 显示 "BRAIN 服务器响应中" | OfficialOperationsPanel.tsx | +8 |
| **F-03** | 连接状态不明确 | 顶栏区分认证状态 + 同步状态 | App.tsx | +15 |
| **F-04** | 16 张状态卡过多 | 移至仪表盘底部 collapsed section | Dashboard.tsx | +5 |
| **F-05** | 达标/可提交概念模糊 | 阻断复核页增加状态流转图 | SubmissionConfirmPanel.tsx | +30 |
| **F-06** | 批量失败无逐项修复 | 检查结果增加行级重试按钮 | QualityCheckPanel.tsx | +20 |
| **F-07** | 新用户配置负担重 | Dashboard 顶部增加分步引导 | App.tsx + Dashboard | +40 |
| **F-08** | 移动端首屏核心结果被埋 | 移动端 bottom tab 导航 | App.tsx (新增 MobileNav) | +50 |
| **F-09** | 图表空态显示技术信息 | 替换为用户友好 fallback | CandidateTable.tsx | +5 |

### 7.2 修复优先级

```
本周 (P0 → 阻断任务)
  F-01: 同步超时恢复       ← 1 行 onRetry 绑定
  F-02: SCAN 停滞提示       ← 8 行超时检测
  F-03: 连接状态分离        ← 15 行 topbar

下周 (P1 → 严重摩擦)
  F-07: 分步引导             ← 40 行 onboarding
  F-05: 状态流转图           ← 30 行 SVG/HTML
  F-06: 逐项修复             ← 20 行 row action

本月 (P1-P2 → 体验优化)
  F-04: 状态卡精简           ← 5 行折叠
  F-09: 图标空态文案         ← 5 行文字替换
  F-08: 移动端导航           ← 50 行 bottom nav
```

---

## 8. 实施路线

### Phase A：致命断点修复（预计 2 天）

```
Day 1: F-01 + F-02 + F-03
  → OfficialOperationsPanel.tsx: onRetry + stall detection
  → App.tsx: topbar state separation
  → 验证: 模拟同步超时场景

Day 2: 回归测试
  → 全部 2155 测试保持通过
  → 手动验证 3 个修复点
```

### Phase B：导航重构（预计 5 天）

```
Day 3-4: 新侧边栏 Phase 分组
  → Sidebar.tsx 重构: PhaseGroup 组件
  → 阶段折叠/展开逻辑
  → 徽章系统更新

Day 5-7: Dashboard 重构
  → 分步引导组件 (F-07)
  → StatusCards 折叠 (F-04)
  → 状态流转图 (F-05)
```

### Phase C：移动端响应式（预计 3 天）

```
Day 8-9: MobileNav 底部 Tab
  → useMediaQuery hook
  → MobileTabBar 组件
  → 表格 → 卡片视图适配

Day 10: 触控目标统一 44px
  → CSS token 更新
  → 全站按钮/输入框审查
```

---

## 附录 A：命名规范

| 概念 | 旧名 | 新名 |
|------|------|------|
| 工作流程 | workflow | workflow / phases |
| 工具 | tools | tools |
| 运行总览 | dashboard | overview / dashboard |
| 官方操作 | official_operations | （拆分到各阶段） |
| 候选管理 | candidates | candidates |
| 科学评分 | scoring | scoring |
| 质量门禁 | quality_check | quality-gate |
| 阻断复核 | submission_confirm | readiness-review |
| 系统配置 | config | settings |

## 附录 B：文件变更范围

```
修改文件:
  src/App.tsx                          ~100 行变更
  src/components/Sidebar.tsx           ~80 行变更
  src/components/Dashboard.tsx         ~30 行变更
  src/components/OfficialOperationsPanel.tsx  ~15 行变更
  src/components/CandidateTable.tsx    ~10 行变更
  src/components/QualityCheckPanel.tsx ~25 行变更
  src/components/SubmissionConfirmPanel.tsx   ~35 行变更

新增文件:
  src/components/MobileTabBar.tsx      ~50 行
  src/components/PhaseShell.tsx        ~40 行
  src/components/StepGuide.tsx         ~60 行
  src/components/StatusFlowDiagram.tsx ~50 行

总计: ~495 行变更，~200 行新增
```
