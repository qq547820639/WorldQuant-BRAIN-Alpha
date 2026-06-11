# 云端同步模块全面诊断分析报告

> **诊断日期**: 2026-06-10  
> **诊断范围**: 全栈——后端 Python（6 个核心模块）、前端 React TypeScript（3 个组件）、Web API 路由层、Pipeline 集成层、历史 E2E 测试报告  
> **方法论**: 静态代码审查 + 数据流追踪 + 历史缺陷/测试报告交叉验证 + 真实 sync job 日志分析

---

## 0. 执行摘要

云端同步模块是 BRAIN Alpha Ops 的核心数据入口——它从官方 BRAIN API 拉取用户 Alpha 快照、刷新官方字段/算子/Dataset 上下文，是所有后续生产操作（候选生成、评分、提交）的数据基础。

当前模块已具备完整的**功能骨架**（多路径同步、分页扫描、取消支持、进度反馈、兜底降级），但用户体验层面存在 **7 个关键问题**：进度反馈在长扫描期间用户焦虑、错误恢复路径不完整、前后端阈值不同步、代码重复维护风险、同步范围选项不匹配、以及首次同步等待期间无引导。本报告逐项分析根因并给出具体修改方案。

---

## 1. 架构概览

### 1.1 模块调用拓扑

```
                          ┌─────────────────────────────┐
                          │    OfficialOperationsPanel   │
                          │  (React TSX — 用户操作入口)    │
                          └──────────────┬──────────────┘
                                         │
              ┌──────────────────────────┼──────────────────────────┐
              │                          │                          │
     POST /api/sync_alphas     GET /api/sync_status      POST /api/sync_cancel
     POST /api/sync_context_only                              │
              │                          │                          │
    ┌─────────▼──────────┐    ┌─────────▼──────────┐    ┌─────────▼──────────┐
    │ web_sync_job.py    │    │   web_routes.py    │    │   web_jobs.py      │
    │ run_sync_job_      │    │  _status_payload() │    │  cancel flag       │
    │ service()          │    │   (async 作业状态)   │    │  management        │
    └─────────┬──────────┘    └────────────────────┘    └────────────────────┘
              │
    ┌─────────▼──────────────────────────────────────────────┐
    │            brain_api/user_alpha_sync.py                │
    │  list_user_alphas_for_sync() — 官方 API 分页拉取        │
    │  分页回调 → on_page() → store.update() 进度推送         │
    └─────────┬──────────────────────────────────────────────┘
              │
    ┌─────────▼──────────┐    ┌────────────────────────────┐
    │ ResearchRepository │    │  official_context_datasets │
    │ merge_cloud_alphas │    │  list_official_datasets_   │
    │ (本地持久化合并)     │    │  or_derive()               │
    └────────────────────┘    └────────────────────────────┘
              │                          │
    ┌─────────▼──────────────────────────▼──────────────────┐
    │            Pipeline 集成（后端自动化路径）                │
    │  pipeline_context_sync.py::_sync_cloud_alphas()        │
    │  pipeline_submission_gate.py — cloud_sync 门禁检查      │
    └────────────────────────────────────────────────────────┘
```

### 1.2 三条同步路径

| 路径 | 触发方式 | 进度机制 | 文件 |
|------|---------|---------|------|
| **Web 异步作业** | 用户点击"开始刷新"→ POST `/api/sync_alphas` | 前端每 2s 轮询 `GET /api/sync_status` | `web_sync_job.py` + `OfficialOperationsPanel.tsx` |
| **Web 同步内联** | 编程调用（agent tools） | 直接返回结果 dict | `web_sync_payload.py::sync_cloud_alphas_payload()` |
| **Pipeline 自动** | `AlphaResearchPipeline.run()` 启动时 | SSE/WSSE 事件 `cloud_sync` phase | `pipeline_context_sync.py::_sync_cloud_alphas()` |

### 1.3 核心数据流

```
用户点击 → POST /api/sync_alphas → 创建作业 → 启动后台线程
                                              │
  ┌─ AUTH phase ──────────────────────────────┤
  │  authenticate() → 验证 BRAIN 凭证          │
  ├─ SCAN phase ──────────────────────────────┤
  │  list_user_alphas_for_sync(api, range)     │
  │  ├─ 每页 progress_callback → store.update  │
  │  ├─ stop_callback 检查取消                  │
  │  └─ 分页结束 → 返回 rows                   │
  ├─ MERGE phase ─────────────────────────────┤
  │  repo.merge_cloud_alphas(rows)             │
  │  → 新增/更新/跳过 统计                     │
  ├─ CONTEXT phase (3 步) ────────────────────┤
  │  ① CONTEXT_FIELDS: list_fields()          │
  │  ② CONTEXT_OPERATORS: list_operators()    │
  │  ③ persist_official_context()              │
  └─ COMPLETED / COMPLETED_WITH_WARNINGS ─────┘
```

---

## 2. 关键问题诊断

### 2.1 P0 级——体验阻断问题

#### 🔴 P0-1: 超时/停滞恢复路径不完整

**表现**（E2E 测试已证实）：
> "云端同步失败：云端同步超时，后台任务仍未完成 | 0% | 0/0 | 新增 0"  
> 消息可见且不崩溃，但缺乏取消/重试/日志操作，也未解释下一步最佳操作。

**根因分析**：

`OfficialOperationsPanel.tsx` 的 stall 检测机制（30s 警告 → 90s 自动停止）确实存在，但：
1. **停止后的 UI 状态**：自动停止后进度条显示"已自动停止"→ 进度组件进入 `idle` 状态 → 按钮恢复为"开始刷新"，与第一次点击时完全相同。用户不知道上一次失败的原因（网络？凭证？数据量？），也没有差异化的恢复建议。
2. **重试按钮的行为**：ProgressFeedback 的 `onRetry` 在 context_refresh 模式下直接调用 `startOfficialContextRefresh()`，这意味着重新跑完整流程，而不是有针对性的重试（如仅重试上下文）。
3. **停止等待超时重试**：当 `stopping` 状态超过 60s，前端确实会重发 cancel 请求——但用户看到的是"已等待 60s"而没有进度，体验焦虑。

**影响范围**：`OfficialOperationsPanel.tsx` L136-171 (stall 监控)、L293-395 (开始同步)、L397-398 (上下文仅重试)

---

#### 🔴 P0-2: 前端/后端 Stale 阈值硬编码不同步

**现状**：

| 位置 | 值 | 形式 |
|------|-----|------|
| 后端 `runtime_constants.py::CloudDefaults.CLOUD_SYNC_STALE_SECONDS` | `86400` (24h) | Python 类常量 |
| 前端 `Dashboard.tsx` 缓存年龄判断 | `86400` | 硬编码数字 `if (ageSeconds < 86400)` |

**风险**：后端修改 stale 策略后（如改为 12 小时），前端 Dashboard 仍按 24 小时显示"有效"，用户看到的缓存状态与后端 pipeline 门禁不一致，导致：
- Dashboard 显示"有效"但 pipeline 拒绝提交（`SUBMIT_CLOUD_SYNC_STALE`）
- 用户体验断裂：明明显示"有效"却不能提交

**影响范围**：`Dashboard.tsx` 缓存状态显示、`runtime_constants.py` 常量定义

---

#### 🔴 P0-3: 会话失效后缺乏恢复引导

**表现**：当 sync job 运行时间超过本地 session 有效期时，前端调用 `applySyncRecoveryFailure()` 设置 `status: "missing"` + `phase: "session_invalid"`。进度组件显示：
> "本地会话已失效，无法读取正在运行的官方同步状态。请刷新页面或重新测试连接后恢复监控。"

**问题**：
1. 提示要求"刷新页面"——但用户正在等待长时间同步，刷新页面可能丢失进度
2. 没有提供"重新连接"的快捷按钮——用户必须手动导航到 Dashboard 测试连接
3. 错误状态下 `retryLabel` 绑定到 `startOfficialContextRefresh`——但会话已失效，retry 也会失败

**影响范围**：`OfficialOperationsPanel.tsx` L173-199 (applySyncRecoveryFailure)

---

### 2.2 P1 级——高用户体验影响

#### 🟠 P1-1: 进度反馈在首段等待期间焦虑高

**表现**：用户点击"开始刷新"后，如果官方 API 响应慢（第一页数据返回前），进度显示：
> "正在扫描云端 Alpha，等待官方接口返回第一页和过滤窗口数量。"  
> 进度条 indeterminate，无 ETA，无百分比。

**根因**：`list_user_alphas_for_sync()` 在第一页返回前不会调用 `progress_callback`。这期间用户看到的始终是：
- 进度条：无限滚动的 indeterminate 条
- 状态：`phase: "auth"` 或 `phase: "queued"`
- 耗时：从 00:00 开始递增

这在以下场景下尤其糟糕：
- 网络延迟高（跨国访问 BRAIN API）
- 同步范围大（"all" 可能涉及数万条记录）
- 第一次使用（用户不知道"正常"的等待时间）

**对比**：`ProgressFeedback.tsx` 已有 10s stall 检测（`isStalled = isBusy && !isDeterminate && !openEndedCloudScan && elapsed > 10`），但显示的是"BRAIN 服务器仍在响应中，请耐心等待。"——信息量不足。

**影响范围**：`ProgressFeedback.tsx` L72、`web_sync_job.py` L260-303 (on_page 回调)、`brain_api/user_alpha_sync.py` 分页逻辑

---

#### 🟠 P1-2: 同步范围前后端不匹配

**前端选项**（`OfficialOperationsPanel.tsx` L691-704）：
```tsx
<option value="all">全部</option>
<option value="recent">近期 30 天</option>
<option value="6months">近 6 个月</option>
```

**后端支持**（`web_sync_payload.py` L153-160）：
```python
{"3d": "近 3 天", "7d": "近 7 天", "recent": "近期 30 天", "6months": "近 6 个月", "all": "全部"}
```

"3d" 和 "7d" 选项后端支持但前端不暴露——对于只想快速检查最近变化的用户，这两个快速范围非常有用。

**影响范围**：`OfficialOperationsPanel.tsx` 下拉选项定义

---

#### 🟠 P1-3: `context_only` 模式的进度反馈不清晰

当用户点击"仅重试上下文"时，`run_sync_job_service` 以 `context_only=True` 运行，跳过 SCAN 和 MERGE 阶段。但前端进度组件无法区分：
- 完整同步 vs 仅重试上下文的区别
- 进度显示为 `phase: "context"` 但用户可能以为还在做完整同步

**根因**：`startContextOnlyRefresh()` 调用 `startOfficialContextRefresh({ contextOnly: true })`，但 `contextOnly` 没有透传到进度显示中。

**影响范围**：`OfficialOperationsPanel.tsx` L293-398 (startOfficialContextRefresh)

---

#### 🟠 P1-4: 代码严重重复——`web_sync_payload.py` 文件结构异常

**发现**：`web_sync_payload.py` 文件包含两段几乎相同的内容：

1. 第 1-564 行：`run_sync_job_service()` + 辅助函数（正确的异步作业版本）
2. 第 566-659 行：`sync_cloud_alphas_payload()` + 重复的 type alias 和 import（同步版本）

此外，`web_sync_job.py` 包含与 `web_sync_payload.py` 完全相同的代码（`_timing_payload`、`_scan_observability`、`_cloud_scan_status_message`、`_sync_range_label`、协议类型、`run_sync_job_service`），唯一的区别是 `web_sync_job.py` 多了 `api_reported_total`/`filter_window_count` 的字段填充逻辑（L262-275）。

**风险**：
- 修复 bug 需要同时改两个文件
- `web_sync_payload.py` 中 `sync_cloud_alphas_payload()` 的 import 重复声明导致 Python 解释器可能忽略重复 import，但实际运行时可能产生混淆
- 新增功能（如 `retry_exhausted`）只加到一个文件会被遗忘在另一个

**影响范围**：`web_sync_job.py` 全文（660 行）、`web_sync_payload.py` 全文（659 行）

---

#### 🟠 P1-5: Dashboard 同步 CTA 与操作面板状态不同步

**表现**：Dashboard 有一个 `SyncCloudCTA` 组件，当云端缓存 stale 时显示"立即同步"按钮，点击后导航到 OfficialOperationsPanel。但：
1. Dashboard 的 stale 判断（`age_seconds < 86400`）是纯前端逻辑，与后端恒定值一致是巧合
2. 导航到同步面板后，用户可能看到"已刷新"状态（如果后端 job 刚完成），但 Dashboard 不知道——因为不共享状态
3. 缺少从 Dashboard 直接触发同步的能力——用户必须离开 Dashboard 页面

**影响范围**：`Dashboard.tsx` SyncCloudCTA 部分

---

### 2.3 P2 级——中等用户体验影响

#### 🟡 P2-1: 取消流程在极端网络条件下体验差

**流程**：点击"停止" → 状态变为 `stopping` → 等待当前 API 调用返回 → 变为 `stopped`

**问题**：如果当前 API 调用本身已挂起（网络超时未设置），`stopping` 可能持续数分钟。前端有 60s 重试机制（`STOP_RETRY_AFTER_MS`），但：
1. 用户不知道后台是否真的在处理停止请求
2. `stoppingSinceMs` 显示增加但无实际效果

**影响范围**：`OfficialOperationsPanel.tsx` L507-564 (stopOfficialContextRefresh)、L566-585 (stopping 重试 useEffect)

---

#### 🟡 P2-2: 重复同步的反馈无差异化

**表现**：当 sync 数据无变化时（例如刚同步完立即再次同步），结果显示：
> "云端同步完成：已扫描 40,226 条，新增 0 条，更新 0 条，跳过 40,226 条，失败 0 条。"

**问题**：
1. 用户不知道"跳过 40,226 条"是因为数据完全一致还是因为 dedup 逻辑
2. 没有提示"数据已是最新，无需重复同步"——用户可能怀疑同步是否真的执行了
3. 操作日志只有一条完成消息，没有说明"没有新数据"

**优化方向**：当 `added=0 && updated=0` 时，明确告知"云端数据无变化，本地缓存已是最新。"

**影响范围**：`web_sync_job.py` L504-538 (完成状态消息)

---

#### 🟡 P2-3: 错误消息映射不完整

`OfficialOperationsPanel.tsx` 的 `readableBackendText()` 函数（L1003-1021）映射了约 8 种错误消息，但以下常见错误未覆盖：

1. HTTP 状态码错误（如 `HTTP_503`、`HTTP_429`）→ 直接显示原始英文
2. 网络超时错误 → 可能显示堆栈信息
3. `BrainAPIError` 的特定子类错误 → 未映射

**影响范围**：`OfficialOperationsPanel.tsx` L1003-1021

---

### 2.4 P3 级——轻微问题

#### 🟢 P3-1: 缺少首次同步时间预估

"all" 范围同步时进度条始终 indeterminate——没有"通常需要 3-5 分钟"之类的引导性提示。

#### 🟢 P3-2: 同步历史不可见

`data/jobs_sync.json` 存储了完整的作业历史（包含 `job_0001` 到当前的 16+ 次记录），但前端不展示——用户无法了解过去的同步模式和成功率。

#### 🟢 P3-3: Dashboard 和操作面板的缓存年龄显示不一致

Dashboard 用 "X 小时前" / "X 天前"，操作面板用 "最后更新 HH:MM:SS"——两个页面的时间格式不统一。

---

## 3. 详细修改方案

### 3.1 P0-1: 超时恢复路径增强

**目标**：让停止/失败状态有差异化的恢复路径

**文件**: `brain_alpha_ops/web/react_app/src/components/OfficialOperationsPanel.tsx`

**方案 A**：在 `syncStatus?.status === "stopped"` 时，将操作面板的 primaryLabel 从"开始刷新"改为"重新刷新"，并附加一段失败原因说明：

```tsx
// 在 ActionPanel 的 status 和 primaryLabel 附近（约 L679-684）
const isRecovery = syncStatus?.status === "stopped" || syncStatus?.status === "failed";
const primaryLabel = syncRunning 
  ? "刷新中..." 
  : isRecovery 
    ? "重新刷新" 
    : "开始刷新";
```

**方案 B**：在停止状态下的进度卡片中，增加上下文操作建议：

```tsx
{syncStatus?.status === "stopped" && (
  <div className="mt-3 p-3 rounded-md border border-warning-subtle bg-warning-subtle text-sm">
    <p className="font-medium text-warning">同步未完成</p>
    <p className="mt-1 text-text-secondary">
      {syncStatus?.progress?.stop_reason || syncStatus?.error || "同步在扫描阶段被停止，部分数据未拉取。"}
    </p>
    <div className="mt-2 flex gap-2">
      <button className="btn btn-secondary text-sm" onClick={() => void startOfficialContextRefresh()}>
        使用相同范围重试
      </button>
      <button className="btn btn-secondary text-sm" onClick={() => { setSyncRange("recent"); void startOfficialContextRefresh(); }}>
        缩小为近期 30 天重试
      </button>
    </div>
  </div>
)}
```

**方案 C**：在 `ProgressFeedback` 的 error 状态中（L149-156），为 sync 操作增加"查看日志"按钮：

```tsx
{state === "error" && (
  <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
    {onRetry && (
      <button type="button" className="btn btn-primary" onClick={onRetry}>
        {retryLabel}
      </button>
    )}
    {progress?.operation === "sync_alphas" && (
      <button type="button" className="btn btn-secondary" onClick={onViewLogs}>
        查看日志
      </button>
    )}
  </div>
)}
```

---

### 3.2 P0-2: Stale 阈值前后端同步

**目标**：让前端从后端获取 stale 阈值，而非硬编码

**文件**: 
- `brain_alpha_ops/web_get_handlers.py`（新增 API）
- `brain_alpha_ops/web/react_app/src/components/Dashboard.tsx`
- `brain_alpha_ops/web/react_app/src/hooks/useApi.ts`

**方案**：在 `/api/health` 响应中增加 `cloud_sync_stale_seconds` 字段

```python
# web_get_handlers.py 的 health_payload() 中增加：
from brain_alpha_ops.runtime_constants import CloudDefaults

def health_payload() -> dict:
    return {
        "ok": True,
        "status": "ready",
        "cloud_sync_stale_seconds": CloudDefaults.CLOUD_SYNC_STALE_SECONDS,
        # ... 其他字段
    }
```

前端 Dashboard 从 health API 获取阈值：

```tsx
// Dashboard.tsx 中
const staleThresholdSeconds = healthData?.cloud_sync_stale_seconds ?? 86400;
const isStale = cloudSummary.age_seconds > staleThresholdSeconds;
```

---

### 3.3 P0-3: 会话失效恢复引导

**目标**：在会话失效状态下提供可操作的恢复路径

**文件**: `OfficialOperationsPanel.tsx` L173-199

**方案**：在 `applySyncRecoveryFailure` 中增加"重新连接"快捷操作：

```tsx
const applySyncRecoveryFailure = useCallback((jobId: string, result: JobStatus | null) => {
  // ... 现有逻辑 ...
  // 在 setSyncStatus 之后，增加操作按钮状态
  setStoredRecoveryAction("reconnect"); // 新增状态
  // ...
}, [appendLog, notify]);
```

在 UI 中根据 `storedRecoveryAction` 渲染不同的恢复按钮：

```tsx
{syncStatus?.phase === "session_invalid" && (
  <div className="mt-3 p-3 rounded-md border border-negative-subtle bg-negative-subtle">
    <p className="text-sm text-negative">{syncStatus?.error}</p>
    <div className="mt-2 flex gap-2">
      <button className="btn btn-primary text-sm" onClick={onNavigateToDashboard}>
        前往 Dashboard 重新连接
      </button>
    </div>
  </div>
)}
```

---

### 3.4 P1-1: 首段等待优化

**目标**：减少同步启动阶段的用户焦虑

**文件**: `web_sync_job.py` + `ProgressFeedback.tsx`

**方案 A**（后端）：在 `run_sync_job_service` 的初始阶段增加更明确的状态：

```python
# L236-250 的初始 store.update 中
status_message = (
    "正在连接 BRAIN 服务器并验证身份..." if not context_only 
    else "正在连接 BRAIN 服务器准备刷新上下文..."
)
```

**方案 B**（前端）：在 `ProgressFeedback` 的 `isStalled` 逻辑中（L72），将 stalled 阈值从 10s 改为可配置，并增加更友好的提示：

```tsx
{isStalled && (
  <div style={{ fontSize: 12, color: "oklch(0.75 0.10 88)", padding: "4px 0" }}>
    {openEndedCloudScan 
      ? "云端 Alpha 数据量较大，首次响应可能需要 1-3 分钟。"
      : "BRAIN 服务器仍在响应中，请耐心等待。"}
  </div>
)}
```

**方案 C**（前端）：在 `startOfficialContextRefresh` 启动后立即在日志中显示提示：

```tsx
appendLog("info", "已连接到 BRAIN 服务器，正在等待第一页数据返回。首次完整同步通常需要 3-5 分钟，近期范围同步约 1 分钟。");
```

---

### 3.5 P1-2: 同步范围选项补全

**目标**：前端暴露所有后端支持的同步范围

**文件**: `OfficialOperationsPanel.tsx` L35, L691-704

**方案**：

```tsx
// L35: 扩展 SyncRange 类型
type SyncRange = "3d" | "7d" | "recent" | "6months" | "all";

// L691-704: 补全下拉选项
<select
  className="input w-full text-sm"
  value={syncRange}
  disabled={syncRunning || syncStartApi.loading}
  onChange={(event) => setSyncRange(event.target.value as SyncRange)}
  aria-label="同步范围"
>
  <option value="3d">近 3 天（快速检查）</option>
  <option value="7d">近 7 天</option>
  <option value="recent">近期 30 天</option>
  <option value="6months">近 6 个月</option>
  <option value="all">全部（推荐）</option>
</select>
```

同步范围 hint 也需更新：

```tsx
<span className="mt-1 block text-text-tertiary">
  小范围同步更快，适合快速检查；首次使用建议"全部"。
</span>
```

---

### 3.6 P1-3: context_only 模式进度区分

**目标**：让用户明确知道当前是"仅重试上下文"而非完整同步

**文件**: `OfficialOperationsPanel.tsx`

**方案**：在 `startOfficialContextRefresh` 调用中增加 `contextOnly` 状态追踪，并在 UI 中反映：

```tsx
const [contextOnlyMode, setContextOnlyMode] = useState(false);

const startOfficialContextRefresh = useCallback(async (options?: { contextOnly?: boolean }) => {
  const contextOnly = Boolean(options?.contextOnly);
  setContextOnlyMode(contextOnly);
  // ... 现有逻辑 ...
}, [...]);

// 在 ActionPanel 标题中区分
<ActionPanel
  title={contextOnlyMode ? "刷新官方能力集（仅上下文）" : "刷新官方能力集"}
  description={contextOnlyMode 
    ? "仅刷新官方字段、算子与 Dataset 上下文，不拉取 Alpha 数据。" 
    : "同步云端 Alpha 快照，并刷新官方字段、算子与 Dataset 上下文。"}
  // ...
/>
```

---

### 3.7 P1-4: 消除代码重复

**目标**：将 `web_sync_payload.py` 和 `web_sync_job.py` 的共享代码提取为公共模块

**方案**：

1. **新建** `brain_alpha_ops/web_sync_shared.py`，移入：
   - `_timing_payload()`
   - `_scan_observability()` + 相关常量
   - `_cloud_scan_status_message()`
   - `_sync_range_label()`
   - 所有 Protocol 类型定义（`JobStoreLike`、`RunConfigFromPayload` 等）
   - `SyncJobCancelled`

2. **修改** `web_sync_job.py`：删除共享代码，从 `web_sync_shared` 导入

3. **修改** `web_sync_payload.py`：
   - 删除 L566-659 的重复 `sync_cloud_alphas_payload()` 代码块
   - 保留 L1-564 的 `run_sync_job_service()`
   - 从 `web_sync_shared` 导入共享辅助函数

4. **验证**：
```bash
python -m pytest tests/test_pipeline.py -v -k "cloud_sync"
python -m pytest tests/test_web_sync_job.py tests/test_web_sync_payload.py -v
```

---

### 3.8 P2-1: 取消流程体验改善

**目标**：停止操作提供更及时的反馈

**文件**: `OfficialOperationsPanel.tsx` L507-564

**方案**：在 `stopping` 状态下，每 5 秒更新进度描述：

```tsx
// 在 stopping 的 useEffect (L566-570) 中
useEffect(() => {
  if (syncStatus?.status !== "stopping") return;
  const timer = window.setInterval(() => {
    setStoppingNowMs(Date.now());
    // 更新状态消息显示已等待时间
  }, 1000);
  return () => window.clearInterval(timer);
}, [syncStatus?.status]);

// 在 stopping 提示区（L743-747）优化：
{syncStatus?.status === "stopping" && (
  <div className="rounded-md border border-[oklch(0.65_0.06_85/0.25)] bg-warning-subtle p-3 text-sm">
    <p className="font-medium text-warning">正在停止同步</p>
    <p className="mt-1 text-text-secondary">
      停止请求已发送，等待当前 API 调用返回。已等待 {formatDuration(stoppingElapsedSeconds)}。
    </p>
    <p className="mt-1 text-xs text-text-tertiary">
      通常在 15 秒内生效。如超过 60 秒仍在等待，系统会自动重发停止请求。
      {stoppingElapsedSeconds > 30 && " 当前请求可能阻塞，请耐心等待或刷新页面。"}
    </p>
  </div>
)}
```

---

### 3.9 P2-2: 无变化同步的差异化反馈

**目标**：当同步无新数据时给出明确反馈

**文件**: `web_sync_job.py` L504-538

**方案**：修改完成状态消息：

```python
# 在 run_sync_job_service 的最终 store.update 中
if stats["added"] == 0 and stats.get("updated", 0) == 0 and stats["scanned"] > 0:
    status_message = (
        f"云端同步完成：已扫描 {stats['scanned']:,} 条，无新增或更新。"
        f"本地缓存已是最新，无需重复同步。"
    )
elif stats["added"] > 0 or stats.get("updated", 0) > 0:
    status_message = (
        f"云端同步完成：已扫描 {stats['scanned']:,} 条，新增 {stats['added']:,} 条，"
        f"更新 {stats.get('updated', 0):,} 条，跳过 {stats['skipped']:,} 条，失败 {stats['failed']:,} 条。"
    )
```

---

### 3.10 P2-3: 错误消息映射扩展

**目标**：覆盖更多常见错误

**文件**: `OfficialOperationsPanel.tsx` L1003-1021

**方案**：

```tsx
function readableBackendText(raw: unknown) {
  const value = String(raw || "").trim();
  // ... 现有映射 ...
  const labels: Record<string, string> = {
    // 现有映射保持不变
    // 新增：
    "HTTP_401": "BRAIN 认证失败，请检查凭据是否有效。",
    "HTTP_403": "BRAIN 访问被拒绝，请检查账号权限。",
    "HTTP_429": "BRAIN API 访问频率过高，请稍后重试。",
    "HTTP_500": "BRAIN 服务器内部错误，请稍后重试。",
    "HTTP_502": "BRAIN 网关错误，请稍后重试。",
    "HTTP_503": "BRAIN 服务暂时不可用，请稍后重试。",
    "Connection timed out": "连接 BRAIN 超时，请检查网络或稍后重试。",
    "Connection refused": "无法连接到 BRAIN 服务器，请检查网络。",
    "DNS lookup failed": "无法解析 BRAIN 服务器地址，请检查 DNS 设置。",
    "SSL certificate verify failed": "BRAIN SSL 证书验证失败，请检查系统时间或网络代理。",
    "Read timed out": "BRAIN 响应超时，请缩小同步范围或稍后重试。",
    "Process restarted before this task completed": "同步在后台进程重启时中断，请重新启动同步。",
    // ... 保留原有映射
  };
  // 尝试部分匹配
  for (const [key, mapped] of Object.entries(labels)) {
    if (value === key || value.includes(key)) return mapped;
  }
  return value;
}
```

---

## 4. 修改优先级排序

| 优先级 | ID | 问题 | 修改文件数 | 预估工时 | 用户体验改善 |
|--------|-----|------|-----------|---------|------------|
| **P0** | P0-1 | 超时恢复路径增强 | 1 (TSX) | 2h | 用户可自主恢复 |
| **P0** | P0-2 | Stale 阈值前后端同步 | 2 (Python + TSX) | 1h | 消除状态不一致 |
| **P0** | P0-3 | 会话失效恢复引导 | 1 (TSX) | 1.5h | 失效后可操作 |
| **P1** | P1-1 | 首段等待优化 | 2 (Python + TSX) | 2h | 减少焦虑 |
| **P1** | P1-2 | 同步范围补全 | 1 (TSX) | 0.5h | 快速同步可用 |
| **P1** | P1-4 | 消除代码重复 | 3 (Python) | 3h | 维护性提升 |
| **P1** | P1-3 | context_only 进度区分 | 1 (TSX) | 1h | 操作可见性 |
| **P1** | P1-5 | Dashboard CTA 同步 | 2 (TSX) | 1.5h | 跨页面一致性 |
| **P2** | P2-1 | 取消流程体验 | 1 (TSX) | 1h | 等待可理解 |
| **P2** | P2-2 | 无变化同步反馈 | 1 (Python) | 0.5h | 减少困惑 |
| **P2** | P2-3 | 错误消息映射 | 1 (TSX) | 1h | 错误可理解 |

**总计**: 约 15 小时，分 2-3 个迭代窗口完成

---

## 5. 验证方案

### 5.1 单元测试

```bash
# 后端
python -m pytest tests/test_pipeline.py -v -k "cloud_sync"
python -m pytest tests/test_web_sync_job.py -v
python -m pytest tests/test_web_sync_payload.py -v
python -m pytest tests/test_web_submission_safety.py -v -k "cloud_sync"

# 前端（需 React Testing Library）
cd brain_alpha_ops/web/react_app && npx vitest run tests/
```

### 5.2 E2E 测试

```bash
# 完整用户路径
python scripts/run_e2e_walkthrough.py

# 浏览器端截图验证
bash scripts/browser_e2e_test.sh
```

### 5.3 手动验证清单

| 验证项 | 操作 | 期望结果 |
|--------|------|---------|
| 首次同步 | 清除缓存 → "开始刷新" → 等待完成 | 进度条从 auth→scan→merge→context→completed |
| 停止同步 | 同步中点击"停止" | 状态变为 stopping → stopped，停止原因明确 |
| 重复同步 | 完成后再点"开始刷新" | 显示"无新增或更新" |
| 窄范围同步 | 选择"近 3 天" → 同步 | 快速完成，扫描数量远小于全量 |
| 会话失效 | 手动清除 session → 查看同步状态 | 显示"需要重新连接"及快捷按钮 |
| 仅重试上下文 | 同步完成 → "仅重试上下文" | 跳过 SCAN/MERGE，直接到 CONTEXT |
| Stale 阈值 | 修改后端阈值为 3600 → 等待 1h+ | Dashboard 显示"已过期"，前端与后端一致 |

---

## 6. 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| 代码去重引入回归 | 中 | 高 | 完整运行现有测试套件 + 追加契约测试 |
| 前端状态管理变复杂 | 低 | 中 | 新增状态字段集中管理，不侵入现有逻辑 |
| Stale 阈值 API 变更 | 低 | 低 | 向后兼容，默认值不变 |

---

## 附录 A: 缺陷跟踪引用

| 缺陷报告 | 相关条目 |
|---------|---------|
| `E2E_USER_TEST_REPORT_20260527.md` | P1: cloud sync timeout recovery |
| `STATIC_ANALYSIS_DEFECT_REPORT_20260603.md` | P1-7: Stale cache warning |
| `DEFECT_ANALYSIS_REPORT_20260602_v6.md` | 7, 8: Partial row merge + elapsed limit |
| `UX_EVALUATION_AND_OPTIMIZATION_20260521.md` | A11Y-3: progress aria-live |
| `phase1_2_frontend_logic_map.md` | CHECK_STALE_MS 前后端不同步 |

## 附录 B: 涉及文件清单

| 文件 | 模块 | 行数 | 责任 |
|------|------|------|------|
| `brain_alpha_ops/web_sync_job.py` | 后端异步作业 | 660 | run_sync_job_service() |
| `brain_alpha_ops/web_sync_payload.py` | 后端同步内联 | 659 | sync_cloud_alphas_payload() |
| `brain_alpha_ops/research/pipeline_context_sync.py` | Pipeline 集成 | 251 | _sync_cloud_alphas() |
| `brain_alpha_ops/runtime_constants.py` | 运行时常量 | ~200 | CLOUD_SYNC_STALE_SECONDS |
| `brain_alpha_ops/brain_api/user_alpha_sync.py` | 官方 API 分页 | ~300 | list_user_alphas_for_sync() |
| `brain_alpha_ops/web/react_app/src/components/OfficialOperationsPanel.tsx` | 前端操作面板 | 1736 | 同步按钮/进度/取消 |
| `brain_alpha_ops/web/react_app/src/components/ProgressFeedback.tsx` | 前端进度组件 | 368 | 进度条/状态显示 |
| `brain_alpha_ops/web/react_app/src/components/Dashboard.tsx` | 前端仪表盘 | ~600 | 缓存状态/同步CTA |
| `brain_alpha_ops/web/react_app/src/types/index.ts` | 前端类型定义 | ~200 | UnifiedProgress 等 |
| `brain_alpha_ops/config_models.py` | 配置模型 | ~200 | ResearchBudget |

---

> **UI Designer 诊断结论**: 云端同步模块的基础架构设计合理——多路径同步、分页扫描、取消支持、兜底降级都已有正确实现。主要问题集中在 **进度反馈的精细度**（首次等待、无变化同步、context_only 区分）、**错误恢复的用户自主性**（超时后恢复路径、会话失效引导）和**前后端一致性**（stale 阈值、同步范围选项、代码重复）。建议按 P0→P1→P2 顺序分 2-3 个迭代窗口修复，预计总工时 15 小时。
