# 前后端覆盖完整性最终评估

**框架**：UI/UX Pro Max · 全量 API ↔ 前端 UI 逐项交叉审计  
**范围**：22 个 API 路由 (11 GET + 11 POST) ↔ 前端 55+ JS 函数 ↔ 用户可操作性  
**日期**：2026-05-15  
**核心问题**：后端数据是否需要前端图标/按钮/下拉框？哪些需要？用户是否易读易用？

---

## 0. 方法论

对每个 API 路由执行三重验证：
1. **调用覆盖**：前端是否有 JS 函数调用此 API
2. **数据渲染**：API 返回的所有字段是否都能在前端看到
3. **可操作性**：用户能否在看到数据后执行下一步动作

判定规则：
- ✅ 覆盖：API 被调用 + 关键字段被渲染 + 用户可操作
- ⚠ 部分：API 被调用但部分字段丢失 / 无操作入口
- ❌ 缺失：API 未被调用 / 关键数据未渲染 / 完全无 UI

---

## 1. 全量 API ↔ 前端 UI 对照表

### 1.1 GET 路由

| # | 路由 | 前端调用 | 返回字段数 | 渲染字段数 | 覆盖率 | 结论 |
|---|------|---------|-----------|-----------|--------|------|
| 1 | `GET /` | - | HTML | 全量 | 100% | ✅ |
| 2 | `GET /api/health` | **无** | 2 | 0 | 0% | ❌ 缺失 |
| 3 | `GET /api/status` | `pollJobStatus()` | 7+ | 7 | 100% | ✅ |
| 4 | `GET /api/config` | `loadConfig()` | 30+ | 30+ | 100% | ✅ |
| 5 | `GET /api/active_job` | `pollActiveJob()` | 7+ | 7 | 100% | ✅ |
| 6 | `GET /api/stream` | `startSSE()` | 5+ | 5 | 100% | ✅ |
| 7 | `GET /api/lifecycle` | `loadLifecycle()` | 12+ | 8 | 67% | ⚠ |
| 8 | `GET /api/cloud_alphas` | `loadCloudSnapshot()` | 16+ | 16 | 100% | ✅ |
| 9 | `GET /api/sync_status` | `pollSyncStatus()` | 15+ | 15 | 100% | ✅ |
| 10 | `GET /api/check_status` | `pollBatchCheck()` | 17+ | 15 | 88% | ⚠ |
| 11 | `GET /api/profile` | `loadUserProfile()` | 4 | 3 | 75% | ⚠ |

### 1.2 POST 路由

| # | 路由 | 前端调用 | 返回字段数 | 渲染字段数 | 覆盖率 | 结论 |
|---|------|---------|-----------|-----------|--------|------|
| 12 | `POST /api/run` | `startRun()` | 3 | 2 | 67% | ⚠ |
| 13 | `POST /api/test_connection` | `testConnection()` | 3 | 3 | 100% | ✅ |
| 14 | `POST /api/stop` | `stopRun()` | 1 | 1 | 100% | ✅ |
| 15 | `POST /api/sync_alphas` | `syncCloud()` | 2 | 2 | 100% | ✅ |
| 16 | `POST /api/check` | `checkCandidate()` | 10 | 8 | 80% | ⚠ |
| 17 | `POST /api/check_batch` | `checkBatch()` | 2 | 2 | 100% | ✅ |
| 18 | `POST /api/submit` | `submitCandidate()` | 2 | 1 | 50% | ⚠ |
| 19 | `POST /api/submit_batch` | `submitSelectedCandidates()` | 4 | 2 | 50% | ❌ Critical |
| 20 | `POST /api/logout` | **无** | 1 | 0 | 0% | ❌ 缺失 |
| 21 | `POST /api/shutdown` | **无** | 1 | 0 | 0% | ❌ 缺失 |

**汇总**：22 路由中 14 覆盖良好 / 6 部分覆盖 / 4 完全缺失

---

## 2. 关键字段丢失明细

### 2.1 P0 — 直接影响业务闭环

#### `/api/submit_batch` → `results[]` 数组 (Critical)

后端返回每条提交的逐项结果：
```json
{
  "ok": true, "submitted": 1, "failed": 2,
  "results": [
    {"alpha_id": "A001", "ok": true, "submission": {...}},
    {"alpha_id": "A002", "ok": false, "error": "Alpha already submitted"},
    {"alpha_id": "A003", "ok": false, "error": "Insufficient permissions"}
  ]
}
```

**前端当前渲染**：仅 `成功 ${submitted}，失败 ${failed}`  
**丢失**：`results[].error` — 每条失败的具体原因  
**影响**：全部失败时 `ok: true` 仍切到"已提交"视图  
**需要 UI 元素**：
- 展开/折叠按钮：`[查看失败详情 ▼]`
- 失败列表：每行 Alpha ID + error 原因 + `[单条重试]` 按钮
- 选项：`[全部重试]` 按钮

#### `/api/lifecycle` → BLOCKED 状态 (Critical)

后端写 `submission_blocked` 生命周期记录。  
**前端当前匹配**：`failedRows()` 正则 `/failed|rejected|fail/i` — 不包含 `blocked`  
**丢失**：BLOCKED Alpha 既不在失败视图也不在达标视图  
**需要 UI 元素**：
- 在 `failedRows()` 正则中增加 `blocked` 匹配
- 或在失败视图中增加"阻断"子标签
- 每条 BLOCKED 记录显示阻断原因

#### `/api/check_status` → `items[].checks[].detail` (Critical)

每个检查项有 `detail` 字段包含具体原因，但前端 `humanCheckName()` 仅覆盖 8/25+ 检查名。  
**丢失**：
- `not_failed_locally` → 无中文映射，显示原始名
- `cloud_sync_available` → 无中文映射
- `not_submitted_before` → 无中文映射
- `cloud_status_not_already_submitted` → 无中文映射
- `BRAIN_CHECK:*` → 完全无映射
**需要 UI 元素**：
- `humanCheckName()` 补全所有 25 个检查名
- 每个检查项显示 `detail` 字段 + 操作建议

---

### 2.2 P1 — 影响用户诊断和操作效率

#### `/api/check` → `requires_official_check` (High)

布尔值，表示"本地检查通过但未经过官方预提交检查"。  
**前端当前**：`isOfficialPassedCheck()` 检查此状态，但 UI 不单独标示  
**丢失**：用户无法区分"需要再做官方检查"与"完全通过"  
**需要 UI 元素**：
- 状态列：橙色 `⚠ 待官方检查` 标签
- 提示："该 Alpha 本地检查通过，但需执行全部检查模式以包含官方预提交检查"

#### `/api/check` → `cloud_correlation_risk` (High)

包含 `level`, `max_similarity`, `matched_alpha_id`, `matched_status`。  
**前端当前**：仅用 `level` 判断是否高风险  
**丢失**：
- `max_similarity` 数值 — 用户想知道相似度多高
- `matched_alpha_id` — 用户想知道和哪个 Alpha 相似
- `matched_status` — 相似 Alpha 是否已提交
**需要 UI 元素**：
- 详情弹窗：相似 Alpha ID + 相似度百分比 + 状态

#### `/api/check` → `cloud_status` (High)

包含 `id`, `status`, `match` (匹配方式: `official_id` / `expression` / `none`)。  
**前端当前**：完全不渲染  
**丢失**：用户不知道云端是如何匹配到该 Alpha 的  
**需要 UI 元素**：
- 匹配方式图标：🔗 官方 ID 匹配 / 📝 表达式匹配 / — 无匹配

#### `/api/submit` → `submission` (High)

原始提交结果 dict。  
**前端当前**：不解析，仅在详情中作为 JSON 展示  
**丢失**：用户看不到解读后的提交结果（如 "已创建" / "已存在" / "等待审核"）  
**需要 UI 元素**：
- 解析 `submission` 关键字段：status、message、alpha_id
- 提交成功时显示绿色确认 + 官方 Alpha ID

#### `/api/profile` → `profile.username` (Medium)

**前端当前**：显示 tier + points，但不显示 username  
**丢失**：用户登入后看不到当前账号名称  
**需要 UI 元素**：
- Header 用户区域增加 username 显示

---

### 2.3 P2 — 锦上添花

#### `/api/run` → `environment` / `auth` (Medium)

**前端当前**：dry_run 模式下显示测试结果，但 run 成功后不显示 environment  
**需要 UI 元素**：
- 生产状态指示灯：🟢 Production / 🟡 Mock

#### `/api/health` (Medium)

**前端当前**：完全未调用  
**需要 UI 元素**：
- Header 或 Footer 服务状态指示灯：🟢 在线

#### `/api/logout` (Medium)

**前端当前**：无退出按钮  
**需要 UI 元素**：
- Header 用户下拉菜单中的 `[退出登录]`

#### `/api/shutdown` (Low)

**前端当前**：无关闭按钮  
**需要 UI 元素**：
- 设置面板中的 `[关闭服务]` + 二次确认

---

## 3. 需要新增的 UI 元素清单

### 图标 (Icons)

| 位置 | 图标 | 数据来源 | 用途 |
|------|------|---------|------|
| 服务状态 | 🟢/🔴 | `GET /api/health` | 服务在线/离线 |
| 环境标识 | 🟢/🟡 | `POST /api/run` | Production / Mock |
| 云端匹配 | 🔗/📝 | `cloud_status.match` | 匹配方式 |
| 官方检查 | ⚠ | `requires_official_check` | 待官方检查 |
| 阻断状态 | 🚫 | `submission_blocked` | 提交被阻断 |

### 按钮 (Buttons)

| 位置 | 按钮 | 触发 API | 前提条件 |
|------|------|---------|---------|
| 批量提交结果 | `[查看失败详情 ▼]` | 展开 `results[]` | 有失败项 |
| 失败详情行 | `[单条重试]` | `POST /api/submit` | 单条失败 |
| 批量提交结果 | `[全部重试]` | `POST /api/submit_batch` | 有失败项 |
| Header 用户区 | `[退出登录]` | `POST /api/logout` | 已登录 |
| 设置面板 | `[关闭服务]` | `POST /api/shutdown` | 管理员 |

### 下拉框 (Dropdowns)

| 位置 | 下拉框 | 当前值 | 需要增加值 |
|------|--------|--------|-----------|
| Alpha Type | `<select id="alphaType">` | `REGULAR` | `POWER_POOL`, `ATOM`, `PYRAMID` |

### 状态标签 (Badges)

| 标签 | 颜色 | 显示条件 |
|------|------|---------|
| `待官方检查` | 🟠 橙色 | `requires_official_check === true` |
| `阻断` | 🔴 红色 | `status === "BLOCKED"` |
| `相似风险` | 🟡 黄色 | `cloud_correlation_risk.level !== "low"` |

---

## 4. 用户可读性评估

### 4.1 当前用户（内部量化顾问）

| 场景 | 当前可读性 | 问题 |
|------|-----------|------|
| 查看生产进度 | 🟢 好 | 进度条 + ETA + 槽位状态清晰 |
| 判断是否可提交 | 🟢 好 | 检查通过/未通过一目了然 |
| 理解失败原因 | 🔴 差 | `production_gate` / `BRAIN_CHECK:*` 不可读 |
| 批量提交后排查 | 🔴 差 | "成功 0，失败 3" 但看不到是哪些 |
| 发现被阻断 | 🔴 差 | 找不到阻断记录 |
| 判断相似风险 | 🟡 中 | 知道有风险但不知道和谁相似 |
| 选择 Alpha Type | 🔴 差 | 只有 REGULAR，不知道其他类型存在 |

### 4.2 目标用户（扩展到普通业务人员）

| 差距 | 严重度 |
|------|--------|
| 技术术语（`official_pre_submit_check`, `cloud_self_correlation`） | 🔴 Critical |
| 无上下文操作指引（失败后不知道下一步做什么） | 🔴 Critical |
| 缺少中文空状态引导 | 🟡 Medium |
| 无操作历史/审计日志可见 | 🟡 Medium |

---

## 5. 最终判断

### 核心结论

| 问题 | 答案 |
|------|------|
| 前端是否覆盖所有业务场景？ | **否**。主路径覆盖，4 个 POST 路由结果未完整渲染 |
| 是否需要增加图标/按钮/下拉框？ | **是**。5 个图标 + 5 个按钮 + 1 个下拉 + 4 个状态标签 |
| 后端数据是否都需前端 UI？ | **不需要全部**。健康检查、shutdown 仅需基础指示灯；核心业务数据（提交结果、检查详情、阻断状态）则必须完整展示 |
| 用户是否易读易用？ | **内部用户勉强可用，普通业务用户不够** |

### 必须新增的 UI 元素（P0）

```
① 批量提交结果 → 失败明细展开面板 [查看失败详情 ▼]
   每行: Alpha ID + 失败原因 + [单条重试]
   底部: [全部重试失败项]

② 失败/不达标视图 → 增加 BLOCKED 子视图
   正则匹配增加 blocked + 阻断原因列

③ 检查详情 → humanCheckName() 补全 25 个检查名 + detail 字段渲染

④ 检查结果恢复 → 刷新后自动从 checks.jsonl 读取
   (需要后端新增 GET /api/check_results 接口)
```

### 建议新增的 UI 元素（P1）

```
⑤ Alpha Type 下拉 → 增加 POWER_POOL / ATOM / PYRAMID

⑥ 检查详情 → 显示 cloud_correlation_risk 完整信息
   相似度百分比 + 匹配 Alpha ID + 匹配 Alpha 状态

⑦ 检查详情 → 显示 requires_official_check 橙色标签

⑧ 状态标签 → cloud_status.match 图标

⑨ 生物/退出按钮 → POST /api/logout

⑩ 服务状态指示灯 → GET /api/health
```

### 不需要前端 UI 的后端数据

| 数据 | 理由 |
|------|------|
| session_id / csrf_token | 纯安全机制 |
| job_id 内部格式 | 仅用于 API 调用 |
| sync_status internals | 已正确渲染为进度条 |
| run_config 完整 dict | 已渲染为配置面板 |
