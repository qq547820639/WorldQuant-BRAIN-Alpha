# 1.4 前端重复/冗余逻辑识别与重构候选清单

> **审计日期**：2026-05-15  
> **审计方法**：遍历 `index.html` 中全部 JS 函数，标记重复代码、跨模块相似逻辑、本该后端承担的前端计算

---

## 一、重复代码 (Duplicate Code)

### 1.1 API 调用样板代码复读

**模式**：`fetch → .json() → .ok 检查 → toast(error)` 在 15+ 处出现。

| 函数 | 代码行数 | 重复模式 |
|------|---------|---------|
| `testConnection()` | 20行 | POST → json → ok check → error toast |
| `startRun()` | 25行 | POST → json → ok check → error throw |
| `stopRun()` | 8行 | POST → (无 ok 检查) |
| `syncCloud()` | 20行 | POST → json → ok check → error throw |
| `checkBatch()` | 25行 | POST → json → ok check → error toast |
| `submitCandidate()` | 25行 | POST → json → ok check → error toast |
| `submitSelectedCandidates()` | 30行 | POST → json → ok check → error toast |
| `retryAllFailedSubmit()` | 20行 | POST → json → (无统一处理) |
| `refreshUserProfile()` | 15行 | GET → json → 手动渲染 |
| `loadConfig()` | 5行 | GET → json → apply |
| `loadLifecycle()` | 8行 | GET → json → 更新 currentResult |
| `loadCloudSnapshot()` | 5行 | GET → json → apply |

**重构建议**：抽取统一的 `apiClient.post<T>(url, body)` 和 `apiClient.get<T>(url)` 包装，内置 ok 检查和错误 toast。

**节省代码量**：约 200 行。

---

### 1.2 轮询/等待模式复读

| 函数 | 行数 | 模式 |
|------|------|------|
| `waitForJobPolling()` | 18行 | `while(true) → sleep → fetch status → 检查完成/失败` |
| `waitForSync()` | 15行 | 同上，但轮询 `/api/sync_status` |
| `waitForCheckBatch()` | 15行 | 同上，但轮询 `/api/check_status` |
| `waitForJobSSE()` | 30行 | EventSource → onmessage → 检查完成/失败 |

**重构建议**：抽取通用 `async function pollUntilDone(jobId, statusUrl, getProgressFn, options)` 函数，参数化轮询间隔和完成条件。

**节省代码量**：约 80 行。

---

### 1.3 进度条/ETA 更新逻辑复读

| 位置 | 行数 | 模式 |
|------|------|------|
| `updateProgress()` 云端同步分支 | 10行 | 从 `data.cloud_sync` 提取进度字段 |
| `updateProgress()` 上下文加载分支 | 10行 | 从 `data.context_load` 提取进度字段 |
| `updateSyncProgress()` | 25行 | DOM 更新：进度条宽度 + 元数据显示 |
| `updateCheckProgress()` | 15行 | DOM 更新：进度条宽度 + 元数据显示 |

**重构建议**：统一进度数据结构 `{phase, current, total, percent, message}`，抽取 `renderProgressBar(elementId, progress)` 通用函数。

---

### 1.4 表格行渲染逻辑重复

| 函数 | 行数 | 用途 |
|------|------|------|
| `candidateRow(item, idx)` | 45行 | 渲染候选行 |
| `cloudRow(item, idx)` | 30行 | 渲染云端 Alpha 行 |
| `lifecycleRow(item, idx)` | 20行 | 渲染生命周期行 |
| `backtestSlotRow(slot, idx)` | 25行 | 渲染回测槽行 |
| `passedRow(item, idx)` | 40行 | 渲染达标行（与 candidateRow 高度相似） |
| `submittableRow(item, idx)` | 40行 | 渲染可提交行（与 passedRow 高度相似） |

**重构建议**：合并为 `renderTableRow(template, item, idx)` 使用列定义配置驱动渲染。`passedRow` 和 `submittableRow` 差异仅在于操作按钮列，可共用核心模板。

**节省代码量**：约 130 行。

---

### 1.5 详情弹窗渲染重复

| 函数 | 行数 |
|------|------|
| `renderCandidateDetail(candidate)` | 200+ 行 |
| `renderCloudDetail(row)` | 80+ 行 |
| `renderLifecycleDetail(row)` | 60+ 行 |
| `renderBacktestDetail(row)` | 60+ 行 |
| `renderCheckDetail(result)` | 80+ 行 |

**重构建议**：抽取 `renderFieldTable(title, fields)` 通用函数 (`fields = [{label, value, format}]`)，各详情弹窗只需定义字段列表。

**节省代码量**：约 200 行。

---

## 二、跨模块相似逻辑 (Similar Logic Across Modules)

### 2.1 三个独立进度倒计时

| 变量 | 用途 | 更新方式 |
|------|------|---------|
| `cloudSyncCountdownUntil` | 云端同步轮询倒计时 | `setInterval(updateProgressCountdowns, 250)` |
| `jobStatusCountdownUntil` | 任务状态轮询倒计时 | 同上 |
| `checkCountdownUntil` | 检查任务轮询倒计时 | 同上 |

**重构建议**：合并为 `countdowns = {cloud: {until, label}, job: {until, label}, check: {until, label}}` 字典。

---

### 2.2 多处字符串拼接生成表格 HTML

分布在 8+ 函数中：
- `rowsForView()` 各视图
- `renderOpsMonitor()` 统计瓦片
- `renderCloudStatsPanel()` 统计面板
- `renderScorecard()` 评分表格
- `renderGate()` 门禁表格
- `renderCheckDetail()` 检查详情表格

**重构建议**：统一使用 `buildTable(columns, rows)` / `buildCardGrid(items)` 模板函数。

---

### 2.3 "达标/可提交/已提交/不达标" 状态判断重复

| 函数 | 判断逻辑 |
|------|---------|
| `isPassed(candidate)` | lifecycle_status 检查 |
| `isSubmittable(candidate)` | passed + check 通过 + 不过期 |
| `isSubmitted(candidate)` | submission 状态检查 |
| `isFailed(candidate)` | lifecycle_status 正则匹配 |
| `isBlocked(candidate)` | **不存在！** |

**重构建议**：统一为 `alphaStatus(candidate, checkResult)` → 返回枚举值 `{CREATED, VALIDATED, SIMULATED, PASSED, SUBMITTABLE, SUBMITTED, FAILED, BLOCKED}`，避免各函数独立判断导致遗漏（如 BLOCKED）。

---

## 三、本该后端承担的前端计算 (Backend-Should-Be Logic)

### 3.1 业务判断逻辑

| 前端函数 | 行数 | 应由后端维护 | 原因 |
|---------|------|-------------|------|
| `submittableCandidates()` | 15行 | 后端 `candidate.submittable` 字段 | 刷新后丢失 |
| `isFreshCheck(result)` | 5行 | 后端 `result.is_stale` 字段 | 时钟偏差风险 |
| `isOfficialPassedCheck(result)` | 3行 | 后端 `result.requires_official_check` | 已经有此字段！前端额外计算 |
| `needsCheckCount()` | 10行 | 后端 `stats.needs_check_count` | 遍历所有候选效率低 |
| `staleCheckCount()` | 8行 | 后端 `stats.stale_check_count` | 同上 |
| `activeBacktestCount()` | 5行 | 后端 `progress.active_backtest_count` | 每次渲染都重复计算 |
| `softDeferredBacktestCandidates()` | 10行 | 后端 `stats.deferred_count` | 不必要的客户端计算 |

### 3.2 数据格式化

| 前端函数 | 行数 | 应由后端维护 | 原因 |
|---------|------|-------------|------|
| `phaseName(phase)` | 25项 | 后端 `progress.phase_label` | 新增 phase 时前端遗漏 |
| `humanCheckName(name)` | 8项(25+) | 后端 `check.label_cn` | 17+ 项不可读 |
| `convergenceLabel(data)` | 10行 | 后端 `convergence.label` | 与后端阈值逻辑重复 |
| `banditLabel(data)` | 5行 | 后端 `bandit.label` | 格式风险 |
| `validationTileValue(data)` | 10行 | 后端 `stats.validation_tile` | 无端增加客户端复杂度 |
| `localProductionNote(data)` | 12行 | 后端 `stats.production_note` | 同上 |

### 3.3 预设参数定义

| 前端代码 | 行数 | 应由后端配置 | 原因 |
|---------|------|-------------|------|
| `applyPreset()` 中的 `map` 对象 (7个预设) | 8行 | 配置文件 `config/presets.json` | 前后端预设不同步 |
| `syncPresetFromSettings()` 的逆向映射 `map` | 6行 | 后端预设 ID 应随 settings 返回 | 双重维护 |

---

## 四、魔法值清单 (Magic Numbers/Strings)

| 魔法值 | 出现次数 | 位置 | 应替换为 |
|--------|---------|------|---------|
| `4000` (toast 时长) | 5+ | `toast(msg, type, 4000)` | `TOAST_DURATION_MS` |
| `900` (轮询间隔) | 5+ | `sleep(900)`, `countdown + 900` | `POLL_INTERVAL_MS` |
| `700` (同步轮询) | 2 | `sleep(700)` | `SYNC_POLL_INTERVAL_MS` |
| `250` (倒计时更新) | 1 | `setInterval(..., 250)` | `COUNTDOWN_UPDATE_MS` |
| `30000` (profile刷新) | 1 | `setInterval(refreshUserProfile, 30000)` | `PROFILE_REFRESH_MS` |
| `500` (重连延迟) | 1 | `setTimeout(restoreActiveJob, 500)` | `RESTORE_JOB_DELAY_MS` |
| `86400000` (检查过期) | 1 | `CHECK_STALE_MS` | 已有常量名但应来自后端 |
| `300` (最大渲染行) | 1 | `MAX_RENDERED_ROWS` | 已有常量名 ✅ |
| `5000` (SSE超时) | 1 | SSE timeout | `SSE_TIMEOUT_MS` |
| `"candidates"` / `"waiting"` 等视图名 | 30+ | 散落各处 | 应使用 `VIEW` 枚举 |
| `/failed\|rejected\|fail/i` 正则 | 3 | `failedRows()`, `findAnyRow()` | `BLOCKED_STATUS_PATTERN` |

---

## 五、重构候选汇总

### 按优先级排序

| 优先级 | 重构项 | 预计节省行数 | 收益 |
|--------|--------|-------------|------|
| **P0** | 抽取 API 客户端层 (`apiClient.get/post`) | -200 | 统一错误处理、CSRF、base URL |
| **P0** | 合并状态判断逻辑 → `alphaStatus()` 单函数 | -60 | 消除 BLOCKED 遗漏风险 |
| **P1** | 后端计算下沉 (phase_label, check_label_cn, 统计计数) | -150 | 前端减负 + 数据一致性 |
| **P1** | 表格行渲染通用化 (列定义驱动) | -130 | 6个函数合并为1个 |
| **P1** | 详情弹窗通用化 (`renderFieldTable()`) | -200 | 5个函数共用核心 |
| **P1** | 轮询模式统一 (`pollUntilDone()`) | -80 | 消除 3 段重复 while(true) |
| **P1** | 进度条渲染统一 (`renderProgressBar()`) | -40 | 消除 2 段重复 DOM 操作 |
| **P2** | 魔法值常量化 | 0 | 可维护性 |
| **P2** | 预设参数删除 → 迁移到后端配置 | -14 | 消除双重维护 |
| **P2** | 全局状态封装为 `AppState` 对象 | 0 | 可调试性 |
| **P2** | 进度倒计时合并为字典 | -10 | 代码整洁 |

**总计预计节省**：约 **884 行**（当前 JS 约 3200 行 → 目标 2300 行，减少 ~28%）

---

## 六、模块拆分建议

### 当前结构

```
index.html (4432 行)
├── CSS (970 行)
├── HTML (200 行)
└── JS `<script>` (3200 行)
    └── 55+ 函数，全在全局作用域
```

### 建议拆分为

```
web/
├── index.html              # HTML 框架 + CSS
├── js/
│   ├── app.js              # 初始化、事件绑定、全局状态 AppState
│   ├── api-client.js       # apiClient.get/post 统一封装
│   ├── views/
│   │   ├── candidates.js   # 候选池视图
│   │   ├── backtest.js     # 回测槽视图
│   │   ├── cloud.js        # 云端 Alpha 视图
│   │   ├── lifecycle.js    # 生命周期视图
│   │   └── detail.js       # 详情弹窗 (renderFieldTable)
│   ├── components/
│   │   ├── toast.js        # Toast 通知
│   │   ├── spinner.js      # 加载动画
│   │   ├── modal.js        # 确认弹窗
│   │   ├── progress.js     # 进度条
│   │   └── monitor.js      # 监控瓦片
│   ├── state.js            # AppState 管理
│   └── utils.js            # escapeHtml, phaseName → 迁移到后端
```

> **注意**：由于打包为 `.exe` 时 `web/index.html` 是单文件，需要构建步骤将 JS 文件内联回 HTML。可使用 `<!-- inline:js/app.js -->` 标记 + 简单 Python 构建脚本。
