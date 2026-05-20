# 2.1 接口契约重定义

> **版本**: v2.0  
> **日期**: 2026-05-15  
> **依据**: 阶段一差异清单 + 全栈开发三层架构规范  
> **格式**: OpenAPI 3.0 风格字段表

---

## 一、通用约定

### 1.1 响应结构

所有 API 统一返回：

```json
{
  "ok": true | false,
  "error": "human-readable error message (仅 ok=false)",
  "error_code": "MACHINE_READABLE_CODE (仅 ok=false)",
  "error_id": "uuid (仅 ok=false, 用于日志关联)",
  "... 业务字段"
}
```

### 1.2 错误码枚举

| error_code | HTTP Status | 含义 |
|-----------|-------------|------|
| `SESSION_INVALID` | 403 | 本地会话无效或过期 |
| `ORIGIN_FORBIDDEN` | 403 | 非本地请求来源 |
| `JOB_NOT_FOUND` | 404 | 任务ID不存在 |
| `CONFLICT_RUNNING` | 409 | 已有同类任务在运行 |
| `CONFLICT_AUX_OP` | 409 | 被其他辅助操作阻塞 |
| `VALIDATION_ERROR` | 400 | 请求参数校验失败 |
| `AUTH_FAILED` | 400 | BRAIN API 认证失败 |
| `SUBMIT_BLOCKED` | 400 | 提交被安全门禁阻断 |
| `MISSING_OFFICIAL_ID` | 400 | 缺少官方 Alpha ID |
| `INTERNAL_ERROR` | 500 | 内部未预期错误 |

### 1.3 透传约定

- 后端在非脱敏模式下，`error` 字段可包含简短原因（如 "candidate not found"）。
- `error_code` 是**机器可读**的，前端用此字段路由到用户可读提示。
- `error_id` 唯一标识本次错误，可用于日志回溯。

---

## 二、GET 路由

### `GET /`

| 属性 | 值 |
|------|-----|
| 用途 | 返回前端 HTML 页面 |
| 鉴权 | 创建或复用本地 Session |
| 响应 Content-Type | `text/html; charset=utf-8` |
| 响应 Headers | `Set-Cookie: brain_alpha_ops_session=<id>; HttpOnly; SameSite=Strict` |

---

### `GET /api/health`

| 属性 | 值 |
|------|-----|
| 用途 | 服务存活检查 |
| 鉴权 | 无需 |
| 响应 | `{"ok":true,"status":"ready"}` |

**注意**：当前前端未调用此 API（P2 Gap），建议在 Header 增加服务状态指示器调用。

---

### `GET /api/config`

| 属性 | 值 |
|------|-----|
| 用途 | 返回脱敏后的运行配置 |
| 鉴权 | Session 必需 |
| 响应字段 | `ok:bool`, `config:dict` |

**`config` 结构**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `environment` | `"production"` \| `"mock"` | 运行环境 |
| `auto_submit` | `bool` | 是否自动提交 |
| `web.port` | `int` | Web 服务端口 |
| `web.session_ttl_seconds` | `int` | 会话有效期 |
| `ops.settings` | `object` | BRAIN simulation settings |
| `ops.budget` | `object` | 资源预算 |
| `ops.thresholds` | `object` | 质量门禁阈值 |
| `ops.submission_policy` | `object` | 提交策略 |
| `credentials` | `object` | **脱敏** — 仅返回 env 变量名 |

**`ops.budget` 关键字段**：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_candidates_per_cycle` | `int` | 20 | 每轮生成候选数 |
| `max_official_validations_per_cycle` | `int` | 10 | 每轮回测前预检数 |
| `max_official_simulations_per_cycle` | `int` | 3 | 每轮官方模拟数 |
| `max_official_concurrent_simulations` | `int` | 3 | 并发模拟上限 |
| `retained_alpha_pool_size` | `int` | 10 | 候选池容量 |
| `run_forever` | `bool` | false | 是否连续运行 |
| `require_cloud_sync` | `bool` | true | 是否要求云端同步 |
| `cloud_sync_range` | `string` | "3d" | 云端同步时间范围 |
| `cycle_pause_seconds` | `float` | 2.0 | 轮次间暂停 |
| `dataset_strategy` | `string` | "rotate" | 数据集选择策略 |
| `generation_mode_ratio` | `string` | "70/20/10" | 生成模式比例 |

**`ops.thresholds` 关键字段**：

| 字段 | 类型 | 默认值 | BRAIN 官方对应 |
|------|------|--------|---------------|
| `min_sharpe` | `float` | 1.25 | LOW_SHARPE (Delay-1) |
| `min_fitness` | `float` | 1.0 | LOW_FITNESS (Delay-1) |
| `min_sharpe_delay0` | `float` | 2.0 | LOW_SHARPE (Delay-0) |
| `min_fitness_delay0` | `float` | 1.3 | LOW_FITNESS (Delay-0) |
| `min_turnover` | `float` | 0.01 | LOW_TURNOVER (< 1%) |
| `platform_max_turnover` | `float` | 0.70 | HIGH_TURNOVER (> 70%) |
| `max_self_correlation` | `float` | 0.70 | SELF_CORRELATION |
| `max_prod_correlation` | `float` | 0.70 | 衍生自 SELF_CORRELATION |
| `max_weight_concentration` | `float` | 0.10 | CONCENTRATED_WEIGHT |
| `sub_universe_sharpe_min_ratio` | `float` | 0.75 | LOW_SUB_UNIVERSE_SHARPE |
| `target_max_turnover` | `float` | 0.30 | 顾问标准 (非BRAIN硬门槛) |
| `min_margin_bps` | `float` | 4.0 | 最低保证金(bps) |
| `max_drawdown` | `float` | 0.25 | 参考值 (非硬门槛) |
| `enforce_target_turnover_as_hard_gate` | `bool` | false | 是否将30%也作硬门禁 |

---

### `GET /api/status`

| 属性 | 值 |
|------|-----|
| 用途 | 查询后台任务状态（轮询用） |
| 鉴权 | Session 必需 |
| 查询参数 | `job_id` (必需) |
| 响应 Status | 200 (job存在) / 404 (job不存在) |

**响应字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `ok` | `bool` | |
| `status` | `"queued"` \| `"running"` \| `"completed"` \| `"stopped"` \| `"stopping"` \| `"failed"` | 任务状态 |
| `progress` | `object` | 进度对象 |
| `result` | `object` \| `null` | 完成时的结果（仅 completed/stopped） |
| `error` | `string` | 失败原因（仅 failed） |

**`progress` 对象**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `phase` | `string` | 当前阶段（如 "startup", "production_loop", "official_validation"） |
| `current` | `int` | 当前进度 |
| `total` | `int` | 总进度 |
| `percent` | `int` | 进度百分比 0-100 |
| `message` | `string` | 阶段描述 |
| `alpha_id` | `string` | 当前处理的 Alpha ID |
| `continuous` | `bool` | 是否连续运行模式 |
| `data` | `object` | 运行时数据快照（见下方） |

**`progress.data` 对象**（仅列出前后端都使用的关键字段）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `candidates` | `array` | 当前候选列表 |
| `backtests` | `array` | 回测槽位状态 |
| `lifecycle_records` | `array` | 生命周期记录 |
| `summary` | `object` | 流水线摘要 |
| `summary.produced_count` | `int` | 已生产数 |
| `summary.ready_results_count` | `int` | 达标数 |
| `summary.strategy_profile` | `object` | 当前策略配置 |
| `summary.convergence` | `object` | 收敛状态 |
| `summary.bandit` | `object` | 策略表现 |
| `summary.active_dataset_id` | `string` | 当前数据集 |
| `summary.official_retry_remaining_seconds` | `float` | 官方限流剩余时间 |
| `user_profile` | `object` | 用户等级/积分快照 |

---

### `GET /api/active_job`

| 属性 | 值 |
|------|-----|
| 用途 | 获取当前活跃任务（页面恢复用） |
| 鉴权 | Session 必需 |
| 响应 | 与 `GET /api/status` 相同结构，或 `{"ok":true,"job_id":"","status":"idle"}` |

---

### `GET /api/stream`

| 属性 | 值 |
|------|-----|
| 用途 | SSE 实时推送任务状态 |
| 鉴权 | Session 必需（通过 CSRF token） |
| 查询参数 | `job_id` (必需) |
| Content-Type | `text/event-stream` |

**SSE data 字段**：

```
data: {"ok":true,"job_id":"...","status":"...","progress":{...},"error":""}
```

每 1 秒推送一次。遇到 `status` 为 `"completed"` / `"stopped"` / `"failed"` 后关闭连接。

---

### `GET /api/lifecycle`

| 属性 | 值 |
|------|-----|
| 用途 | 获取 Alpha 生命周期记录 |
| 鉴权 | Session 必需 |
| 查询参数 | `job_id` (可选) |

**响应字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `ok` | `bool` | |
| `records` | `array` | 生命周期记录列表 |

**`records[*]` 结构**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `run_id` | `string` | 所属运行 |
| `timestamp` | `string` | ISO 8601 UTC |
| `alpha_id` | `string` | Alpha ID |
| `official_alpha_id` | `string` | 官方 Alpha ID（如有） |
| `stage` | `string` | 阶段：generated/validated/simulated/scored/submitted/submission_blocked |
| `status` | `string` | 状态：SUBMITTED/FAILED/BLOCKED/PASSED/... |
| `family` | `string` | Alpha 家族 |
| `score` | `float` | 总分 |
| `simulation_id` | `string` | 模拟 ID |
| `expression` | `string` | Alpha 表达式 |
| `note` | `string` | 备注（如阻断原因） |

---

### `GET /api/cloud_alphas`

| 属性 | 值 |
|------|-----|
| 用途 | 获取本地缓存的云端 Alpha 数据 |
| 鉴权 | Session 必需 |

**响应字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `ok` | `bool` | |
| `alphas` | `array` | 云端 Alpha 列表 |
| `summary` | `object` | 汇总信息 |

**`summary` 字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `source` | `"storage"` \| `"api_cache"` \| `"empty"` | 数据来源 |
| `loaded_at` | `string` | 加载时间 ISO 8601 |
| `age_seconds` | `int` \| `null` | 数据年龄（秒） |
| `is_stale` | `bool` | 是否超过24小时（需同步） |
| `total` | `int` | 总数 |
| `submitted_count` | `int` | 已提交数 |
| `passed_unsubmitted` | `int` | 达标未提交数 |
| `failed_unsubmitted` | `int` | 不达标未提交数 |

---

### `GET /api/sync_status`

| 属性 | 值 |
|------|-----|
| 用途 | 查询云端同步任务状态 |
| 鉴权 | Session 必需 |
| 查询参数 | `job_id` (必需) |

**响应字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `ok` | `bool` | |
| `status` | `"running"` \| `"completed"` \| `"failed"` | |
| `progress` | `object` | 包含 `phase`, `range`, `scanned`, `total`, `added`, `skipped`, `failed` |

---

### `GET /api/check_status`

| 属性 | 值 |
|------|-----|
| 用途 | 查询批量检查任务状态 |
| 鉴权 | Session 必需 |
| 查询参数 | `job_id` (必需) |

**响应字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `ok` | `bool` | |
| `status` | `"running"` \| `"completed"` \| `"failed"` | |
| `progress` | `object` | 包含 `mode`, `total`, `checked`, `submittable`, `blocked`, `failed`, `items[]` |

**`progress.items[*]`** 结构与 `POST /api/check` 响应相同。

---

### `GET /api/check_results`

| 属性 | 值 |
|------|-----|
| 用途 | 获取持久化检查结果（页面恢复用） |
| 鉴权 | Session 必需 |

**响应字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `ok` | `bool` | |
| `results` | `array` | 检查结果列表 |

**`results[*]` 结构**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `alpha_id` | `string` | Alpha ID |
| `official_alpha_id` | `string` | 官方 Alpha ID |
| `passed` | `bool` | 全部检查通过 |
| `submittable` | `bool` | 可提交 |
| `requires_official_check` | `bool` | 需要官方预提交检查 |
| `checked_at` | `string` | **【新增】** ISO 8601 检查时间 |
| `is_stale` | `bool` | **【新增】** 是否已过期（>24h） |
| `score` | `float` | 调整后分数 |
| `checks` | `array` | 逐项检查结果 |
| `cloud_correlation_risk` | `object` | 云端相关性风险 |
| `cloud_status` | `object` | 云端匹配状态 |

**`checks[*]` 结构**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | `string` | 检查标识 (e.g. "production_gate") |
| `label_cn` | `string` | **【新增】** 中文标签 |
| `passed` | `bool` | 是否通过 |
| `detail` | `string` | 详情/失败原因 |
| `suggestion` | `string` | **【新增】** 操作建议 |

**`cloud_correlation_risk` 结构**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `level` | `"low"` \| `"medium"` \| `"high"` | 风险等级 |
| `max_similarity` | `float` | 最大相似度 |
| `matched_alpha_id` | `string` | 匹配的云端 Alpha ID |
| `matched_status` | `string` | 匹配 Alpha 的状态 |

**`cloud_status` 结构**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `string` | 云端 Alpha ID |
| `status` | `string` | 云端状态 |
| `match` | `"official_id"` \| `"expression"` \| `"none"` | 匹配方式 |

---

### `GET /api/profile`

| 属性 | 值 |
|------|-----|
| 用途 | 获取 BRAIN 用户等级/积分 |
| 鉴权 | Session 必需 |

**响应字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `ok` | `bool` | |
| `profile` | `object` | |

**`profile` 结构**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `tier` | `string` | 用户等级 (e.g. "Consultant") |
| `level` | `int` \| `null` | 等级数值 |
| `points` | `float` \| `null` | 积分 |
| `username` | `string` | 用户名/邮箱 |

---

## 三、POST 路由

### `POST /api/run`

| 属性 | 值 |
|------|-----|
| 用途 | 启动后台生产流水线 |
| 鉴权 | Session 必需 |
| Content-Type | `application/json` |

**请求 body**：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `environment` | `"production"` \| `"mock"` | 是 | |
| `username` | `string` | 否 | BRAIN 账号 |
| `password` | `string` | 否 | BRAIN 密码 |
| `token` | `string` | 否 | Bearer Token |
| `baseUrl` | `string` | 否 | API 地址 |
| `syncRange` | `"3d"` \| `"7d"` \| `"all"` | 否 | |
| `continuousMode` | `bool` | 否 | **【修复】** 后端需消费此字段 |
| `autoSubmit` | `bool` | 否 | 自动提交开关 |
| `settings` | `object` | 是 | BRAIN simulation settings |

**`settings` 结构**：

| 字段 | 类型 | 必需 | 枚举值 |
|------|------|------|--------|
| `instrumentType` | `string` | 是 | `EQUITY` |
| `region` | `string` | 是 | `USA`, `CHN`, `EUR`, `GLB` |
| `universe` | `string` | 是 | `TOP3000`, `TOP1000`, `TOP500` |
| `delay` | `int` | 是 | `0`, `1` |
| `decay` | `int` | 是 | 1-20 |
| `neutralization` | `string` | 是 | `SUBINDUSTRY`, `INDUSTRY`, `SECTOR`, `MARKET`, `NONE` |
| `truncation` | `float` | 是 | 0.0-1.0 |
| `pasteurization` | `string` | 是 | `ON`, `OFF` |
| `unitHandling` | `string` | 是 | `VERIFY`, `RAW` |
| `nanHandling` | `string` | 是 | `ON`, `OFF` |
| `language` | `string` | 是 | `FASTEXPR` |
| `type` | `string` | 是 | `REGULAR`, `POWER_POOL`, `ATOM`, `PYRAMID` |

**成功响应 (200)**：

```json
{"ok": true, "job_id": "job_0001"}
```

**冲突响应 (409)**：

```json
{"ok": false, "error": "已有生产任务正在运行，请先停止当前任务。", "error_code": "CONFLICT_RUNNING", "job_id": "job_0000"}
```

---

### `POST /api/test_connection`

| 属性 | 值 |
|------|-----|
| 用途 | 测试 BRAIN API 连接 |
| 鉴权 | Session 必需 |
| Body | 与 `POST /api/run` 相同 |

**响应**：

```json
{"ok": true, "environment": "production", "auth": "token"}
```

或：

```json
{"ok": false, "error": "production mode requires BRAIN_USERNAME/BRAIN_PASSWORD or BRAIN_TOKEN", "error_code": "AUTH_FAILED"}
```

---

### `POST /api/stop`

| 属性 | 值 |
|------|-----|
| 用途 | 停止当前运行中的任务 |
| 鉴权 | Session 必需 |

**请求 body**：

| 字段 | 类型 | 必需 |
|------|------|------|
| `job_id` | `string` | 是 |

**响应**：

```json
{"ok": true}   // cancel 成功
{"ok": false}  // job 不存在
```

---

### `POST /api/sync_alphas`

| 属性 | 值 |
|------|-----|
| 用途 | 从 BRAIN API 同步云端 Alpha 数据 |
| 鉴权 | Session 必需 |

**请求 body**：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `environment` | `string` | 是 | |
| `username` / `password` / `token` | 见 `/api/run` | |
| `baseUrl` | `string` | 否 | |
| `syncRange` | `"3d"` \| `"7d"` \| `"all"` | 是 | |

**成功响应**：

```json
{"ok": true, "job_id": "sync_0001"}
```

---

### `POST /api/check`

| 属性 | 值 |
|------|-----|
| 用途 | 单条 Alpha 提交前检查 |
| 鉴权 | Session 必需 |
| 注意 | **当前缺失函数定义 (P0)** |

**请求 body**：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `environment` | `string` | 是 | |
| `username` / `password` / `token` | 见 `/api/run` | |
| `alpha_id` | `string` | 是 | |
| `candidate` | `object` | 是 | 候选对象（含 expression, official_alpha_id 等） |
| `mode` | `"quick"` \| `"all"` | 是 | |
| `syncRange` | `string` | 否 | |

**响应**（与 `GET /api/check_results` 中 `results[*]` 结构相同）：

```json
{
  "ok": true,
  "alpha_id": "...",
  "official_alpha_id": "...",
  "mode": "all",
  "passed": true,
  "submittable": true,
  "requires_official_check": false,
  "checked_at": "2026-05-15T01:42:30Z",
  "is_stale": false,
  "score": 85.5,
  "checks": [...],
  "cloud_correlation_risk": {...},
  "cloud_status": {...}
}
```

**checks 完整枚举**（25项，每项含 label_cn）：

| name | label_cn | 说明 |
|------|----------|------|
| `production_gate` | 生产门禁 | `gate.submission_ready` 检查 |
| `official_alpha_id` | 官方 Alpha ID | 是否存在 |
| `not_failed_locally` | 未本地失败 | 非 failed/rejected/不达标/blocked |
| `cloud_sync_available` | 云端同步可用 | 云端数据是否可访问 |
| `not_submitted_before` | 未提交过 | 本地提交历史检查 |
| `cloud_status_not_already_submitted` | 云端未提交 | 云端状态检查 |
| `cloud_self_correlation` | 云端自相关 | 与云端 Alpha 相似度 |
| `official_pre_submit_check` | 官方预提交检查 | BRAIN API check_alpha() |
| *(其余17项由 BRAIN API check 返回)* | → | 后端需补全 label_cn 映射 |

---

### `POST /api/check_batch`

| 属性 | 值 |
|------|-----|
| 用途 | 批量 Alpha 提交前检查 |
| 鉴权 | Session 必需 |

**请求 body** (在 `/api/check` 基础上增加)：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `mode` | `"quick"` \| `"all"` | 是 | |
| `check_candidates` | `array` | 是 | 待检查候选列表 |

**成功响应**：

```json
{"ok": true, "job_id": "check_0001"}
```

---

### `POST /api/submit`

| 属性 | 值 |
|------|-----|
| 用途 | 提交单条 Alpha 到 BRAIN |
| 鉴权 | Session 必需 |

**请求 body**：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `environment` / `username` / `password` / `token` / `baseUrl` | | 是 | |
| `alpha_id` | `string` | 是 | |
| `candidate` | `object` | 是 | 完整候选对象 |
| `job_id` | `string` | 否 | 关联任务 ID |
| `submit_mode` | `"manual"` \| `"auto"` | 否 | |

**成功响应**：

```json
{
  "ok": true,
  "submission": {
    "status": "SUBMITTED",
    "message": "Alpha submitted successfully",
    "alpha_id": "official_alpha_id"
  }
}
```

**阻断响应**：

```json
{
  "ok": false,
  "error": "Missing official Alpha ID; run an official simulation before production submit.",
  "error_code": "MISSING_OFFICIAL_ID"
}
```

---

### `POST /api/submit_batch`

| 属性 | 值 |
|------|-----|
| 用途 | 批量提交 Alpha |
| 鉴权 | Session 必需 |

**请求 body**（在 `/api/submit` 基础上增加）：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `alpha_ids` | `array` | 是 | Alpha ID 列表 |
| `submit_candidates` | `array` | 是 | 候选对象列表 |

**响应**（**修复后** — 当前缺失 results 渲染）：

```json
{
  "ok": true,
  "submitted": 2,
  "failed": 1,
  "results": [
    {
      "alpha_id": "A001",
      "ok": true,
      "submission": {"status": "SUBMITTED", "message": "..."}
    },
    {
      "alpha_id": "A002",
      "ok": false,
      "error": "Alpha already submitted via another session",
      "error_code": "SUBMIT_BLOCKED"
    }
  ]
}
```

---

### `POST /api/logout`

| 属性 | 值 |
|------|-----|
| 用途 | 销毁本地 Session |
| 鉴权 | Session 必需 |
| 响应 | `{"ok": true}` + `Set-Cookie` 过期头 |

---

### `POST /api/shutdown`

| 属性 | 值 |
|------|-----|
| 用途 | 关闭本地服务 |
| 鉴权 | Session 必需 |
| 响应 | `{"ok": true}` → 线程关闭服务器 |

---

## 四、前端类型定义（建议）

```typescript
// api-types.ts — 与后端契约对齐的类型定义

interface ApiResponse<T = void> {
  ok: true;
} & T;

interface ApiError {
  ok: false;
  error: string;
  error_code: string;
  error_id?: string;
}

type ApiResult<T = void> = ApiResponse<T> | ApiError;

// 核心类型
interface Candidate {
  alpha_id: string;
  expression: string;
  family: string;
  hypothesis: string;
  data_fields: string[];
  operators: string[];
  source_tags: string[];
  parent_id: string;
  mutation_type: string;
  local_quality: Record<string, unknown>;
  validation: Record<string, unknown>;
  simulation_id: string;
  official_alpha_id: string;
  official_metrics: Record<string, unknown>;
  scorecard: Scorecard;
  gate: Gate;
  submission: Record<string, unknown>;
  lifecycle_status: AlphaStatus;
  created_at: string;
}

type AlphaStatus = 
  | "created" 
  | "validated" 
  | "simulated" 
  | "passed" 
  | "submittable"
  | "submitted" 
  | "failed" 
  | "blocked";

interface Scorecard {
  total_score: number;
  prior_score: number;
  empirical_score: number;
  checklist_score: number;
}

interface ProgressData {
  candidates: Candidate[];
  backtests: BacktestSlot[];
  lifecycle_records: LifecycleRecord[];
  summary: PipelineSummary;
  user_profile: UserProfile;
}

interface CheckResult {
  alpha_id: string;
  official_alpha_id: string;
  passed: boolean;
  submittable: boolean;
  requires_official_check: boolean;
  checked_at: string;
  is_stale: boolean;
  score: number;
  checks: CheckItem[];
  cloud_correlation_risk: CloudCorrelationRisk;
  cloud_status: CloudMatchStatus;
}

type ViewKind = "candidates" | "waiting" | "backtesting" | "passed" 
  | "submittable" | "submitted" | "failed" | "cloud" | "lifecycle" | "stats";
```

---

## 五、变更记录

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-05-14 | 初版（隐式契约，散落在代码中） |
| v2.0 | 2026-05-15 | 基于阶段一审计的完整重定义 |
| | | + 新增 error_code 枚举 |
| | | + 新增 checked_at / is_stale 字段 |
| | | + 新增 label_cn / suggestion 字段 |
| | | + 补全 settings 枚举值约束 |
| | | + 补全 submit_batch.results 结构 |
| | | + 新增 TypeScript 类型定义建议 |
