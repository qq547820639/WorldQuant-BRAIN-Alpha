# 1.2 前端业务逻辑地图

> **审计日期**：2026-05-15  
> **审计方法**：逐模块剖析 `brain_alpha_ops/web/index.html` 中 55+ JS 函数，标注状态管理、条件分支、数据转换逻辑及与后端实际行为的冲突点

---

## 一、全局状态拓扑

```
currentResult               (核心数据容器)
├── summary: {}             # 流水线摘要
├── candidates: []          # 当前批次候选数组
├── pending_backtest_candidates: []  # 等待回测
├── passed_candidates: []   # 达标候选
├── cloud_alphas: []        # 云端同步数据
├── lifecycle_records: []   # 生命周期记录
└── backtests: []           # 回测槽位状态

liveProgress                (实时进度快照)
selected                    (当前选中行: {kind, id})
activeView                  (当前视图: candidates/waiting/backtesting/passed/submittable/submitted/failed/cloud/lifecycle/stats)
activeJobId                 (当前运行任务ID)

Check/Polling 状态:
├── checkResults: {}        # alpha_id → check_result
├── selectedSubmitIds: Set  # 勾选提交ID集合
├── batchCheckJobId: ""     # 批量检查job
├── syncJobId: ""           # 云端同步job
├── syncInFlight: false
├── submitInFlight: false
├── isRunning: false

提交失败追踪:
├── lastSubmitResults: []   # 上次批量提交结果
├── lastSubmitPayload: {}   # 上次提交payload

进度/ETA:
├── progressEtaState: {}
├── backtestSnapshotUpdatedAt: 0
├── cloudSyncCountdownUntil: 0
├── jobStatusCountdownUntil: 0
├── checkCountdownUntil: 0

本地配置缓存:
├── configAutoSubmit: false
├── configRunForever: false
├── configuredBudget: {}

渲染缓存:
├── rowCache: Map<string, row>
├── MAX_RENDERED_ROWS: 300
├── CHECK_STALE_MS: 86400000 (24h)
```

**问题诊断**：

| # | 问题 | 详情 | 严重度 |
|---|------|------|--------|
| S1 | **全局可变状态无封装** | 54 个全局 `let` 变量散布在 4400 行文件中，无 namespace/对象包裹。任何函数可修改任何状态，调试极其困难。 | P2 |
| S2 | **数据源不唯一** | `currentResult.summary`、`liveProgress.data`、`data.result.summary` 三处保存"同一份"摘要数据，`updateLiveView()` 和 SSE `onmessage` 各自写入不同路径。 | **P1** |
| S3 | **`checkResults` 无持久化恢复映射** | 刷新页面后 `loadCheckResults()` 读取 `checks.jsonl`，但恢复的检查结果中 `timestamp` 字段缺失 → `isFreshCheck()` 判老逻辑失效。 | **P1** |

---

## 二、API 调用链路映射

### 2.1 页面初始化流程

```
Page Load
├── loadConfig()          → GET /api/config → applyConfig()
├── loadCloudSnapshot()   → GET /api/cloud_alphas → applyCloudSnapshot()
├── loadCheckResults()    → GET /api/check_results → 恢复 checkResults
├── renderInsight()       → 纯本地渲染状态卡
├── renderOpsMonitor()    → 纯本地渲染监控瓦片
├── refreshUserProfile()  → GET /api/profile → 渲染用户等级/积分
├── restoreActiveJob()    → GET /api/active_job → 重连运行中任务
└── setInterval(refreshUserProfile, 30000)  # 每30s刷新
```

### 2.2 生产运行流程

```
用户点击 "开始生产搜索" (toggleRun → startRun)
├── collectPayload()      → 组装 settings/credentials/syncRange
├── POST /api/run         → 获得 job_id
├── waitForJob(jobId)
│   ├── SSE优先: EventSource → /api/stream?job_id=xxx
│   │   └─ onmessage: updateProgress() → updateLiveView()
│   │                  renderBacktests() → renderInsight() → renderCharts() → renderCurrentView()
│   │                  await loadLifecycle()  ← BUG: 非async回调中使用await
│   └── Polling fallback: setInterval → GET /api/status?job_id=xxx
│       └─ 同上，但调用 renderResult(data.result)
└── finally: isRunning=false, 重置UI
```

### 2.3 提交流程

```
批量检查 → 勾选 → 提交
├── checkBatch(mode)
│   ├── POST /api/check_batch → jobId
│   └── waitForCheckBatch → GET /api/check_status
│       └── 收集 checkResults
├── 用户勾选 → selectedSubmitIds.add(alphaId)
├── submitSelectedCandidates()
│   ├── POST /api/submit_batch → {ok, submitted, failed, results[]}
│   └── lastSubmitResults = data.results  # 失败详情仅保存不渲染!
└── 单条提交
    ├── POST /api/submit → {ok, submission{}}
    └── toast 显示简单消息
```

---

## 三、前端业务逻辑冲突点（与后端行为对照）

### 3.1 硬编码阈值 vs 后端配置

| 前端硬编码值 | 位置 | 后端实际值来源 | 冲突 |
|-------------|------|-------------|------|
| `CHECK_STALE_MS = 86400000` (24h) | 全局常量 | `CLOUD_SYNC_STALE_SECONDS = 86400` (web.py L32) | **前端独立硬编码**，后端修改后前端不同步 |
| `MAX_RENDERED_ROWS = 300` | 全局常量 | 后端无对应限制 | 前端可能截断后端返回的长列表 |
| 预设市场参数 `map` (7个预设) | `applyPreset()` | 配置文件 `config/run_config.json` | **完全独立于后端**，预设在前端重复定义 |
| `toast(msg, type, 4000)` | toast 函数 | 后端无 toast 时长控制 | 一致性问题：4000ms 在提交确认等场景可能偏短 |

### 3.2 前端承担的本该是后端逻辑

| 逻辑 | 当前位置 | 应该在哪 | 问题 |
|------|---------|---------|------|
| **`isStaleCheck(timestamp)`** — 判断24小时过期 | 前端 `isFreshCheck()` | 后端应返回 `is_stale` 布尔值 | 时区问题、时钟偏差 |
| **`phaseName()`** — 25个阶段名中文化 | 前端硬编码映射表 | 后端应返回 `phase_label` | 后端新增 phase 前端不可见 |
| **`humanCheckName()`** — 检查名中文化 | 前端硬编码8项映射 | 后端应返回 `label_cn` | 17+ 检查项无映射 |
| **`convergenceLabel()`** — Sharpe趋势判断 | 前端 value→label 映射 | 后端应直接返回 `convergence.label` | 重复逻辑 |
| **`banditLabel()`** — 策略表现格式化 | 前端字符串拼接 | 后端应返回格式化字符串 | 格式脆弱 |
| **`submittableCandidates()`** | 前端过滤逻辑 | 后端应维护 `submittable` 状态 | **业务判断在前端！** 刷新后状态丢失 |
| **`isSubmittable(checkResult)`** | 前端判 `passed` + `submittable` + `!stale` | 后端应直接返回布尔值 | 状态机不一致风险 |
| **`failedRows()` 正则过滤** | 前端用 `/failed\|rejected\|fail/i` 匹配 lifecycle | 后端应返回 `status_category` | BLOCKED 被遗漏 |
| **`activeBacktestCount()`** | 前端遍历计算 | 后端应在 progress 中直接返回 | 每次渲染都重新计算 |
| **`needsCheckCount()`** | 前端遍历 `passedCandidates()` 并比较 `checkResults` | 后端应维护 | 检查状态在前端无持久化 |

### 3.3 条件分支与后端不一致

| 分支 | 前端逻辑 | 后端行为 | 冲突 |
|------|---------|---------|------|
| 环境切换 | `toggleEnvironment()` 只切换 CSS class | 后端 `environment` 值不影响路由 | 前端隐藏凭据表单但后端仍接受凭据 |
| 生产环境无凭据提示 | `startRun()` 检查 `username && password` 为空时弹确认框 | 后端环境变量中可能有凭据 | 弹框可能误导用户 |
| 自动提交开关 | `handleAutoSubmitToggle()` 开启后检查通过自动 `submitCandidate()` | 后端 `auto_submit` 来自 `payload.autoSubmit` | 前端 `autoSubmitToggle` 和后端 `auto_submit` 是两套独立机制 |

---

## 四、视图状态机

```
activeView 枚举值及其渲染逻辑：

candidates      → rowsForView() 从 currentResult.candidates 取
waiting         → pendingBacktestCandidates()
backtesting     → backtestingRows()
passed          → passedCandidates() + checkResults 过滤
submittable     → submittableCandidates() (passed + check 通过 + 未过期)
submitted       → lifecycle 中 submitted 记录
failed          → lifecycle 中 status 匹配 /failed|rejected|fail/i 的记录
cloud           → currentResult.cloud_alphas
lifecycle       → currentResult.lifecycle_records
stats           → 图表视图
```

**视图切换触发点**：
- `switchView(view)` — 由侧边栏状态卡点击触发
- `renderCurrentView()` — 由数据更新后触发
- 自动切换：提交成功后切 `submitted`，检查通过后切 `submittable`

**问题**：
| # | 问题 | 详情 |
|---|------|------|
| V1 | `submittable` 视图依赖前端 `checkResults` 内存数据，刷新后全部丢失 | 用户刷新页面后"可提交"视图为空 |
| V2 | `failedRows()` 不匹配 `BLOCKED` → 阻断记录在任何视图中不可见 | BLOCKED 成为幽灵状态 |
| V3 | `candidates` 和 `passed_candidates` 是两个独立数组，`findCandidate()` 需要跨数组搜索 | 效率低且状态可能不同步 |

---

## 五、前端数据转换 / 格式化层

| 函数 | 输入 | 输出 | 硬编码风险 |
|------|------|------|-----------|
| `phaseName(phase)` | 英文字符串 | 25项中文明细 | 后端新增 phase 时前端不更新 |
| `humanCheckName(name)` | 检查英文明 | 8项中文明 (其余原文) | 17+ 项无映射 |
| `statusBadge(status)` | lifecycle status | HTML badge | 颜色方案内嵌 |
| `renderScorecard(scorecard)` | 三层评分对象 | HTML table | 权重显示格式固定 |
| `renderGate(gate)` | gate 对象 | HTML detail | 依赖 gate.status 枚举值 |
| `renderCandidateDetail(candidate)` | Candidate dict | HTML 详情弹窗 | 字段名硬编码（如 `candidate.scorecard.total_score`） |
| `renderCloudDetail(row)` | Cloud alpha dict | HTML 详情弹窗 | 假设 `row.metrics.sharpe` 存在 |
| `renderLifecycleDetail(row)` | Lifecycle dict | HTML 详情弹窗 | 假设 `row.status` 字段存在 |

---

## 六、危险区域标注

| 代码段 | 风险 |
|--------|------|
| `collectPayload()` → `settings` 对象 | 前端自由传 `settings`，后端 `run_config_from_payload` 用这些值创建 `BrainSettings`——任何拼写错误都会导致非预期值 |
| `waitForJobPolling()` → `sleep(900)` | 硬编码 900ms 轮询间隔，无自适应 |
| `restoreActiveJob()` 的 finally 块 | 异常静默吞掉，用户不知道重连失败 |
| SSE `onmessage` 中对 `await loadLifecycle()` 的使用 | **已知语法错误 R-05** |
| `renderCurrentView()` → `filteredRows()` | 每 250ms 调用一次（`setInterval(updateProgressCountdowns, 250)`），搜索结果变化时重新渲染，可能频繁触发 DOM 操作 |

---

## 七、模块耦合热图

```
高耦合区域:
├── collectPayload() ← 几乎所有 POST 调用都依赖此函数
├── currentResult ← 几乎所有渲染函数都读取此对象
├── activeView ← renderCurrentView/rowsForView/viewTitle 等 15+ 函数依赖
├── checkResults ← isFreshCheck/isOfficialPassedCheck/needsCheckCount/staleCheckCount/submittableCandidates 依赖

低内聚函数:
├── renderOpsMonitor() — 9 个统计瓦片，每个瓦片的数据来源逻辑独立且重复
├── renderCandidateDetail() — 200+ 行 HTML 拼接，无子函数拆分
└── updateProgress() — 混合了进度更新、云端同步进度同步、上下文加载进度同步
```

---

## 八、汇总

| 类别 | 问题数 |
|------|--------|
| 状态管理问题 | 3 |
| 前端承担后端逻辑 | 10 |
| 条件分支不一致 | 3 |
| 视图状态机问题 | 3 |
| 硬编码阈值 | 6 |
| 函数耦合/内聚问题 | 3 |
| **总问题数** | **28** |
