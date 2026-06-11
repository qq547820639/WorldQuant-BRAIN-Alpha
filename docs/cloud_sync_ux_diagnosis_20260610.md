# 云端同步模块 — 体验诊断与修改方案

> **诊断者**：UI Designer  
> **诊断日期**：2026-06-10  
> **诊断范围**：`web_sync_job.py`、`web_cloud_snapshot.py`、`pipeline_context_sync.py`、`OfficialOperationsPanel.tsx`、`Dashboard.tsx`、`ProgressFeedback.tsx`、`App.tsx`、`ConfigPanel.tsx`  
> **诊断方法**：全量代码审查 + E2E 测试数据交叉验证 + 既有 UX 评估报告对照  
> **不执行任何更改**：本文是纯诊断方案，所有修改项均需人工确认后再实施。

---

## 1. 执行摘要

云端同步模块是用户完成"连接 BRAIN → 同步云端 → 开始验证"三步流程的关键中间环节。当前实现**功能完整但体验粗糙**——同步本身可靠，但进度反馈、状态语义、语言一致性、错误恢复和导航衔接等体验维度存在系统性问题。

本次诊断共识别出 **14 项体验问题**（P0 × 3、P1 × 6、P2 × 5），覆盖后端状态消息、前端进度渲染、导航衔接和配置透明性四个维度。

---

## 2. 问题清单

### P0 — 最高优先级（立即导致用户困惑/流失）

| # | 问题 | 位置 | 影响 |
|---|------|------|------|
| P0-1 | **扫描进度消息中英混杂** | `web_sync_job.py:L126-148`, `OfficialOperationsPanel.tsx` | 用户在同一条进度流中看到英文扫描消息和中文停止/完成消息，认知负荷高 |
| P0-2 | **Dashboard CTA 双重点击** | `Dashboard.tsx:L416`, `OfficialOperationsPanel.tsx:L191` | 用户点击"开始云端同步"后跳到官方操作页，还需再点"开始刷新"才能启动，等于每次都要点两下 |
| P0-3 | **同步后 Dashboard 状态刷新延迟最长 10 秒** | `App.tsx:L256-261`, `OfficialOperationsPanel.tsx:L321-337` | 同步完成后，Dashboard 的 `contextFresh` 要等下一轮 phase_state 轮询才更新，用户在此期间看到的是过时的 Step 2 待同步状态 |

### P1 — 高优先级（显著影响效率和信心）

| # | 问题 | 位置 | 影响 |
|---|------|------|------|
| P1-1 | **无法选择同步范围** | `OfficialOperationsPanel.tsx:L191-194` | `syncRange` 硬编码为 `"all"`，有 15,000+ 条记录的用户每次同步耗时 2-5 分钟，无法只同步近期数据 |
| P1-2 | **停止按钮非即时生效** | `web_sync_job.py:L271-274`, `OfficialOperationsPanel.tsx:L267-300` | 停止只在分页边界检查，用户点击停止后可能等 15+ 秒才有反应，体验类似"按钮失灵" |
| P1-3 | **上下文摘要信息被埋没** | `OfficialOperationsPanel.tsx:L573-583` | 字段/算子/数据集数量在页面最右侧栏的下半部分，用户需滚动才能看到上下文健康状态 |
| P1-4 | **同步失败后无局部重试** | `web_sync_job.py:L426-449`, `OfficialOperationsPanel.tsx` | 上下文刷新失败后只能重启整个同步，不能仅重试失败的阶段 |
| P1-5 | **云端缓存过期提示太弱** | `Dashboard.tsx:L196` | "已过期"仅有文字标记，无颜色/图标差异，无操作入口 |
| P1-6 | **open-ended 扫描无 ETA** | `ProgressFeedback.tsx:L69` | 当 `api_reported_total > 0` 时其实可以计算 ETA，但代码显式屏蔽了 |

### P2 — 中优先级（改善后显著提升体验）

| # | 问题 | 位置 | 影响 |
|---|------|------|------|
| P2-1 | **requireCloudSync 配置项无说明** | `ConfigPanel.tsx:L360` | "需要云端同步"复选框无 tooltip 或 help text，新用户不理解含义 |
| P2-2 | **Dashboard 缺少"上次同步时间"** | `Dashboard.tsx:L148-149` | KPI 卡片只显示数量，用户无法判断数据新鲜度 |
| P2-3 | **进度条在 open-ended 扫描中完全不确定** | `ProgressFeedback.tsx:L110-119` | 进度条显示 indeterminate 动画，但实际上可以用 `scanned / api_reported_total` 提供有意义的百分比 |
| P2-4 | **日志与进度区域割裂** | `OfficialOperationsPanel.tsx:L506-529` | 操作事件日志在左栏，进度在顶部独立面板，用户需要在两个区域间来回切换才能理解完整状态 |
| P2-5 | **凭证未填写时的同步启动提示不够** | `OfficialOperationsPanel.tsx` | 如果用户在 Dashboard 未测试连接就直接进官方操作页点同步，缺少前置凭证检查，会直接 API 报错 |

---

## 3. 根因分析

### 3.1 后端状态消息生成缺乏本地化层

`web_sync_job.py` 的 `_cloud_scan_status_message()` 函数（L126-148）和 `pipeline_context_sync.py` 的 `_sync_cloud_alphas()` 内联消息使用硬编码英文字符串。而停止/取消消息（L173-174）使用中文。整个模块没有统一的消息语言策略。

**根因**：同步模块最初为英文环境开发，后续 stop 功能加入时使用了中文消息，但扫描阶段的英文消息未被同步改造。

### 3.2 前端两阶段启动设计的意图与实现的断层

`Dashboard.tsx` 中的 `SyncCloudCTA` (L388-431) 设计意图是"把用户引导到同步入口"。但 `OfficialOperationsPanel` 的"开始刷新"按钮是一个独立操作，不是自动触发的。这意味着：

```
用户意图：一键同步
实际流程：Dashboard CTA → 官方操作页 → 找到按钮 → 点击 → 等待
```

**根因**：`onNavigateToSync` 只做视图切换（`App.tsx:L355`），不传递操作意图。同步页没有接收"自动开始"的 URL 参数或状态。

### 3.3 轮询架构导致的反馈延迟

`App.tsx` 每 10 秒轮询 `/api/phase_state`（L256-261），而 `OfficialOperationsPanel` 每 2 秒轮询 `/api/sync_status`（L339-346）。两个轮询完全独立，同步完成后的 `contextFresh` 状态变更最多延迟 10 秒才反映到 Dashboard。

**根因**：没有事件总线或回调机制将 sync 完成事件主动推送给 Dashboard 的状态刷新逻辑。

### 3.4 分页扫描的"停止"语义歧义

`web_sync_job.py` 的 `cancel_requested()` 检查（L177-179, L271）只在 `on_page` 回调中触发，这意味着在每次 API 调用之间才会检查。对于返回 100 条/页的 API，单次调用可能耗时数秒，用户在此期间看到的是"正在停止"的假状态。

**根因**：停止机制依赖轮询式检查而非中断式信号。这在使用 HTTP 分页 API 时是合理的工程实现，但对用户来说是反直觉的——他们期望"停止=立即停止"。

---

## 4. 修改方案

### P0-1：统一扫描进度消息语言为中文

**涉及文件**：`brain_alpha_ops/web_sync_job.py`、`brain_alpha_ops/research/pipeline_context_sync.py`

**方案**：

1. 在 `web_sync_job.py` 中重写 `_cloud_scan_status_message()`，全部使用中文：
   ```python
   def _cloud_scan_status_message(stats: dict[str, Any]) -> str:
       """所有消息统一使用中文，与停止/完成消息保持一致。"""
       scanned = max(0, int(stats.get("scanned", 0) or 0))
       filter_window_count = max(0, int(stats.get("api_reported_total") or stats.get("filter_window_count") or 0))
       page = max(0, int(stats.get("pages_fetched") or stats.get("page_number") or 0))
       
       if scanned <= 0:
           return "正在扫描云端 Alpha，等待官方接口返回第一页和过滤窗口数量。"
       
       page_text = f"当前第 {page} 页" if page else ""
       if filter_window_count > 0:
           return f"正在扫描云端 Alpha{':' + page_text if page_text else ''}；已拉取 {scanned:,} 条；API 窗口返回 {filter_window_count:,} 条。"
       return f"正在扫描云端 Alpha{':' + page_text if page_text else ''}；已拉取 {scanned:,} 条；继续直到 API 返回空页或短页。"
   ```

2. 同理改造 `run_sync_job_service()` 中 auth/merge/context 各阶段的 message 字段（L234, L298, L316, L378 等），如 `"Preparing cloud sync for ..."` → `"准备 {sync_range} 云端同步…"`。

3. `pipeline_context_sync.py` 的 `_sync_cloud_alphas()` 使用的进度消息已为中文（L94），确认无改动需求。

**风险**：低。仅改消息字符串，不影响数据结构或 API 契约。

---

### P0-2：Dashboard CTA 一键启动同步

**涉及文件**：`Dashboard.tsx`、`OfficialOperationsPanel.tsx`、`App.tsx`

**方案 A（推荐——轻量改动）**：

在 `OfficialOperationsPanel` 增加 `autoStart` prop，当为 `true` 时组件 mount 后自动调用 `startOfficialContextRefresh()`：

```tsx
// OfficialOperationsPanel.tsx
interface Props {
  // ... existing props
  autoStart?: boolean;
}

useEffect(() => {
  if (autoStart && !syncRunning && !syncJobId) {
    void startOfficialContextRefresh();
  }
}, [autoStart]);
```

在 `App.tsx` 中传递参数：

```tsx
case "official_operations":
  return <OfficialOperationsPanel notify={notify} credentials={credentials} autoStart={true} />;
```

**方案 B（更彻底的体验改造——纳入后续迭代）**：

将同步操作从 `OfficialOperationsPanel` 中独立出来为一个单独的 `SyncWizard` 组件，Dashboard CTA 直接跳转到该向导，自动开始同步。官方操作页的其他功能（阻断复核、质量检查等）保持独立。

**推荐**：方案 A 作为 P0 快速修复，方案 B 纳入 P1 后续优化。

**风险**：方案 A 低。仅增加一个 boolean prop，不影响独立使用场景（用户从侧边栏手动导航进入时不传 `autoStart`）。

---

### P0-3：同步完成后主动刷新 Dashboard 阶段状态

**涉及文件**：`App.tsx`、`OfficialOperationsPanel.tsx`

**方案**：

在 `OfficialOperationsPanel` 的 `pollSyncStatus` 回调中，当检测到同步完成时（`completed` / `completed_with_warnings`），通过一个回调通知父组件刷新 phase state。

1. 增加 prop `onSyncCompleted?: () => void`
2. 在 `pollSyncStatus` 的完成分支（L321-326）中调用 `onSyncCompleted?.()`
3. `App.tsx` 传入 `onSyncCompleted={() => void phaseApi.call("/api/phase_state")}`

```tsx
// OfficialOperationsPanel.tsx
interface Props {
  // ... existing
  onSyncCompleted?: () => void;
}

// In pollSyncStatus, after detecting completion:
if (["completed", "completed_with_warnings"].includes(statusText)) {
  clearStoredSyncJobId();
  setSyncRunning(false);
  syncPollFailureCountRef.current = 0;
  appendLog(statusText === "completed" ? "success" : "warning", operationStatusMessage(result));
  notify(statusText === "completed" ? "success" : "warning", "官方上下文刷新完成");
  onSyncCompleted?.();  // <-- NEW
}
```

```tsx
// App.tsx
<OfficialOperationsPanel 
  notify={notify} 
  credentials={credentials} 
  onSyncCompleted={() => void phaseApi.call("/api/phase_state")} 
/>
```

**风险**：低。仅增加回调，不影响现有逻辑。

---

### P1-1：支持选择同步范围

**涉及文件**：`OfficialOperationsPanel.tsx`、`web_sync_job.py`（payload 校验）

**方案**：

1. 在 `OfficialOperationsPanel.tsx` 的"刷新官方能力集" ActionPanel 区域增加一个范围选择器（下拉框），选项：

   | 值 | 标签 | 说明 |
   |----|------|------|
   | `recent` | 近期（30 天） | 仅同步最近 30 天有活动的 Alpha，速度快 |
   | `6months` | 半年 | 同步最近 6 个月的数据 |
   | `all` | 全部（默认） | 完整同步，时间较长 |

2. 将选择的值传递给 `startOfficialContextRefresh` 的 POST body。

3. 在 `OfficialOperationsPanel.tsx` 中增加状态：
   ```tsx
   const [syncRange, setSyncRange] = useState<"recent" | "6months" | "all">("all");
   ```

4. POST body 改为：
   ```json
   { "syncRange": "recent", "refreshOfficialContext": true, ... }
   ```

**风险**：低。后端 `sync_range_from_payload()` 已支持多种 range 格式，只需在 payload 中传递。

---

### P1-2：改善停止按钮反馈

**涉及文件**：`OfficialOperationsPanel.tsx`、`web_sync_job.py`

**方案**：

1. **前端**：点击停止后立即将状态设为 `"stopping"`（已实现），同时增加一个倒计时指示器：
   ```tsx
   {syncStatus?.status === "stopping" && (
     <span className="text-xs text-text-tertiary">
       等待当前 API 调用完成…（通常在 15 秒内生效）
     </span>
   )}
   ```

2. **后端**：在 `_timing_payload` 中增加 `stopping_since_ms` 字段，让前端知道停止请求已发出多久。

3. **超时保护**：如果 `stopping` 状态持续超过 60 秒，前端自动再次发送停止请求，并显示"停止超时，正在重试…"。

**风险**：低。前端改动为主。

---

### P1-3：上下文摘要前置到同步进度区域

**涉及文件**：`OfficialOperationsPanel.tsx`

**方案**：

将"官方上下文摘要"（当前在 L573-583 的右侧栏中）的内容提取为一个内联的紧凑行，放在同步操作面板的下方进度反馈之前：

```tsx
{/* Context summary — moved above progress feedback */}
{syncJobId && (
  <div className="grid grid-cols-3 gap-2 text-xs" style={{...}}>
    <span>字段: {fieldFromProgress(syncStatus, "fields_count")}</span>
    <span>算子: {fieldFromProgress(syncStatus, "operators_count")}</span>
    <span>数据集: {fieldFromProgress(syncStatus, "datasets_count")}</span>
  </div>
)}
```

右侧栏保留详细摘要，但主操作区增加一个紧凑预览。

**风险**：低。仅为布局调整。

---

### P1-4：支持上下文刷新失败后局部重试

**涉及文件**：`web_sync_job.py`、`OfficialOperationsPanel.tsx`

**方案**：

1. 在后端增加一个轻量 API：`POST /api/sync_context_only`，仅刷新 fields/operators/datasets 而不重新拉取 cloud alphas。
2. 当同步完成后 `context_status === "failed"` 时，前端显示"上下文刷新失败，点击仅重试上下文"按钮。
3. 该 API 复用 `run_sync_job_service` 的逻辑，但跳过 alpha 扫描和合并阶段。

```python
# web_sync_job.py 新增
def run_context_only_sync(payload, ...):
    """仅刷新官方上下文，不重新拉取 alpha。"""
    # skip alpha scan/merge, go directly to context phase
```

**风险**：中。需要新增 API 路由，但逻辑复用现有代码，不影响现有同步流程。

---

### P1-5：云端缓存过期视觉强化

**涉及文件**：`Dashboard.tsx`

**方案**：

1. 当 `cloudSummary.is_stale === true` 时，KPI 卡片的"缓存状态"行使用警告色：
   ```tsx
   <span className={`${cloudSummary.is_stale ? "text-warning font-medium" : "text-text-secondary"}`}>
     {cloudSummary.is_stale ? "⚠ 已过期" : "有效"}
   </span>
   ```

2. 增加一个可点击的"立即同步"链接：
   ```tsx
   {cloudSummary.is_stale && (
     <button onClick={onNavigateToSync} className="text-xs text-accent underline ml-2">
       立即同步 →
     </button>
   )}
   ```

**风险**：低。纯 UI 改动。

---

### P1-6：open-ended 扫描显示 ETA

**涉及文件**：`ProgressFeedback.tsx`

**方案**：

修改 `ProgressFeedback.tsx` 的 `eta` 计算逻辑（L69）：

```tsx
// 当前：完全屏蔽 open-ended 扫描的 ETA
const eta = !openEndedCloudScan && !cloudScanWithApiTotal && remaining > 0 ? fmtDuration(remaining) : "";

// 改为：如果 api_reported_total > 0 且有 scanned 和 elapsed，则可以估算 ETA
const scannableTotal = positiveNumber(progress?.api_reported_total ?? progress?.filter_window_count);
const scanned = positiveNumber(progress?.scanned);
const canEstimate = scannableTotal > 0 && scanned > 0 && elapsed > 0 && scanned < scannableTotal;
const estimatedEta = canEstimate 
  ? Math.ceil((scannableTotal - scanned) / (scanned / elapsed))
  : remaining;

const eta = estimatedEta > 0 ? fmtDuration(estimatedEta) : "";
```

**风险**：低。纯计算逻辑改动，因为 `api_reported_total` 是官方 API 返回的窗口数据，在扫描过程中通常已知。

---

### P2-1：requireCloudSync 配置增加帮助文本

**涉及文件**：`ConfigPanel.tsx`

**方案**：

在"需要云端同步"复选框下方增加说明文本：

```tsx
<CheckboxField label="需要云端同步" checked={form.requireCloudSync} onChange={...} />
<p className="text-xs text-text-tertiary mt-1">
  开启后，每次运行前自动拉取云端 Alpha 列表和官方能力集。
  关闭时使用本地缓存，可手动在"官方操作"页触发同步。
</p>
```

**风险**：无。

---

### P2-2：Dashboard KPI 增加上次同步时间

**涉及文件**：`Dashboard.tsx`

**方案**：

从 `cloudApi.data?.summary?.loaded_at` 或 `age_seconds` 中提取上次同步时间，在 KPI 卡片的 subtitle 中显示：

```tsx
<KpiCard
  label="云端 Alpha"
  value={cloudSummary.count ?? "--"}
  subtitle={cloud 
    ? `${cloudSummary.submitted_count ?? 0} 已提交 · ${formatSyncAge(cloudSummary.age_seconds)}`
    : "等待刷新"}
  trend={...}
/>
```

其中 `formatSyncAge` 将秒数转为人类可读格式（"2 分钟前"、"3 小时前"、"2 天前"）。

**风险**：低。需要确认 `age_seconds` 字段在 API 响应中可用（`web_cloud_snapshot.py:L88` 已返回）。

---

### P2-3：open-ended 扫描进度条保持开放状态

**涉及文件**：`ProgressFeedback.tsx`

**方案**：

`api_reported_total` / `filter_window_count` 只表示当前接口过滤窗口返回的参考数量，不是账户云端 Alpha 全局真实数量，也不是完成分母。扫描阶段应保持开放式/动态分页状态，只展示“已拉取 N 条、接口窗口返回 M 条、继续按分页和日期窗口拉取”，不要用 `scanned / api_reported_total` 计算完成百分比或 ETA。

```tsx
const displayPercent = openEndedCloudScan ? null : percent;
const scanReference = progress.api_reported_total ?? progress.filter_window_count;
```

**风险**：低。用户看到的进度不再误以为接口窗口数量就是云端总量，且不会因为已拉取数量超过窗口参考值而出现假 100% 或倒退。

---

### P2-4：日志与进度区域整合

**涉及文件**：`OfficialOperationsPanel.tsx`

**方案**：

将操作事件日志区域缩小为可折叠的内联时间线，放在 ProgressFeedback 下方而非独立的左右布局列中：

```tsx
{/* Collapsible log — inline under progress */}
<details className="mt-3">
  <summary className="text-xs text-text-tertiary cursor-pointer">
    操作日志（{logs.length} 条）
  </summary>
  <div className="mt-2 max-h-40 overflow-y-auto ...">
    {/* log entries */}
  </div>
</details>
```

这样用户无需跨区域扫视即可在进度反馈下方看到最近的日志。

**风险**：低。布局调整，日志内容不变。

---

### P2-5：同步启动前检查凭证

**涉及文件**：`OfficialOperationsPanel.tsx`

**方案**：

在 `startOfficialContextRefresh` 函数开头增加凭证检查：

```tsx
const startOfficialContextRefresh = useCallback(async () => {
  const hasCredentials = Boolean(
    credentials?.username?.trim() || 
    credentials?.password || 
    credentials?.token?.trim()
  );
  
  // If no page credentials AND no managed credentials, warn user
  if (!hasCredentials) {
    notify("warning", "未填写凭证。请先在 Dashboard 测试 BRAIN 连接，或在此页面填写账户信息。");
    appendLog("error", "凭证缺失，无法启动云端同步。");
    return;
  }
  // ... rest of function
}, [...]);
```

**风险**：低。增加前置检查，需要将 `credentials` 传递给组件（当前已有 prop `credentials?: BrainCredentials`），或在组件内部读取。

---

## 5. 修改优先级路线图

```
Phase 1（本周 — P0 快速修复）
├─ P0-1  统一扫描消息语言为中文           ≈ 30 min
├─ P0-2  Dashboard CTA 一键启动同步       ≈ 45 min
└─ P0-3  同步完成后主动刷新 Dashboard      ≈ 15 min

Phase 2（下周 — P1 体验提升）
├─ P1-1  支持选择同步范围                 ≈ 1.5 h
├─ P1-3  上下文摘要前置                   ≈ 30 min
├─ P1-5  云端缓存过期视觉强化              ≈ 20 min
└─ P1-6  open-ended 扫描显示 ETA          ≈ 20 min

Phase 3（下下周 — P1 深水区 + P2 收尾）
├─ P1-2  改善停止按钮反馈                 ≈ 1 h
├─ P1-4  支持上下文刷新失败后局部重试      ≈ 2 h（含新增 API）
├─ P2-1  requireCloudSync 配置帮助文本    ≈ 10 min
├─ P2-2  Dashboard KPI 增加同步时间       ≈ 20 min
├─ P2-3  open-ended 进度条 page progress  ≈ 15 min
├─ P2-4  日志与进度区域整合               ≈ 30 min
└─ P2-5  同步启动前凭证检查               ≈ 15 min
```

---

## 6. 验证标准

修改完成后，应执行以下验证：

| 验证项 | 方法 | 通过标准 |
|--------|------|----------|
| 扫描进度消息全中文 | E2E 测试：启动一次完整同步 | 所有进度消息不含英文（除技术标识如 page、offset） |
| 一键同步 | 手动测试：Dashboard → 点击 CTA | 自动跳转并开始同步，无需二次点击 |
| 同步完成即时反馈 | 手动测试：等待同步完成 | Dashboard 在同步完成后 2 秒内从 Step 2 变为 Step 3 |
| 同步范围选择 | 手动测试：选"近期"后启动 | API 请求中 `syncRange` 为 `"recent"`，同步时间明显缩短 |
| 缓存过期视觉 | 手动测试：等待缓存过期 | KPI 卡片显示 ⚠ 图标和黄色文字 |
| ETA 显示 | E2E 测试：监控扫描进度 | `api_reported_total > 0` 时进度反馈显示"预计剩余" |

---

## 7. 已知限制与后续方向

1. **停止按钮的彻底中断**：当前架构依赖 HTTP 分页 API，无法在 API 调用进行中真正中断。如果未来迁移到异步任务队列（如 Celery），可实现真正的即时中断。
2. **增量同步**：当前每次同步都是全量拉取+去重合并。未来可探索基于 `updated_at` 游标的增量同步，进一步缩短同步时间。
3. **WebSocket 进度推送**：当前依赖轮询，2 秒间隔在慢速网络下可能不够实时。未来可考虑 SSE/WebSocket 推送。
4. **同步进度持久化**：页面刷新后同步进度丢失（仅通过 sessionStorage 恢复 jobId）。可考虑服务端持久化进度。

---

**UI Designer** — 诊断日期 2026-06-10  
**状态**：等待审核，未执行任何更改  
**参考文档**：`UX_EVALUATION_AND_OPTIMIZATION_CURRENT_20260521.md`、`UX_RESEARCH_PLAN_20260608.md`、`sync-0032-long-monitor.json`
