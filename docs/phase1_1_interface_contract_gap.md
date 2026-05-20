# 1.1 前后端接口契约差异清单

> **审计日期**：2026-05-15  
> **审计方法**：逐 API 交叉比对前端 call site（`index.html` JS 函数）↔ 后端 handler（`web.py`）↔ 后端 models（`models.py`）↔ pipeline 产出物  
> **差异判定**：入参名不匹配、出参字段未消费/未定义、状态码含义分歧、异常结构不一致、前端假设与后端行为矛盾

---

## 一、入参契约差异（前端发送 vs 后端期望）

| # | API 路由 | 前端发送字段 | 后端期望字段 | 差异 | 严重度 |
|---|---------|-------------|-------------|------|--------|
| 1 | `POST /api/run` | `settings.type` (from `alphaType` select) | `settings.type` | 一致 — 但后端 BrainSettings `type` 字段名在 `to_platform_dict()` 中被 pop 并放在顶层 | P2 |
| 2 | `POST /api/run` | `settings.pasteurization` | `settings.pasteurization` → 后端传给 BRAIN API 时会被 pop 并改名为 `pasteurize` | 前端字段名与 BRAIN API 实际 key 不同但后端有映射 | P2 |
| 3 | `POST /api/run` | `continuousMode` (boolean) | `run_config.ops.budget.run_forever` | **前端传 `continuousMode`，但 `run_config_from_payload` 未消费此字段** — 后端始终用配置文件默认值 `run_forever` | **P1** |
| 4 | `POST /api/run` | `autoSubmit` (boolean) | `run_config.auto_submit` | 前端从 `autoSubmitToggle.checked` 取，后端从 `payload.autoSubmit` 取 — 匹配 | ✅ |
| 5 | `POST /api/submit` | `payload.job_id` | `run_config_from_payload(payload)` 不过滤 `job_id`，传入 settings 解析时可能被当数字 | `job_id` 是字符串但 `run_config_from_payload` 不处理它，不会有副作用 | P2 |
| 6 | `POST /api/check` | `payload.alpha_id` + `payload.candidate` + `payload.mode` | `check_candidate` (未定义) 或 `check_candidate_availability` | 前端 `checkCandidate()` 调用 `/api/check`，但后端 web.py 第 411-421 行调用的是 `check_candidate(payload)` — **该函数不存在于当前 web.py！** | **P0** |
| 7 | `POST /api/submit_batch` | `payload.submit_candidates` (数组) | `submit_candidates` 被读取用于 `by_id` 映射 | 一致，但 `submit_candidates` 是前端自建的本地 candidate 列表 | ✅ |

---

## 二、出参契约差异（后端返回 vs 前端消费）

| # | API 路由 | 后端返回字段 | 前端消费情况 | 差异 | 严重度 |
|---|---------|-------------|-------------|------|--------|
| 8 | `POST /api/submit_batch` | `results[].error` (每条失败原因) | **仅消费 `submitted` 和 `failed` 计数** | `results[]` 数组完全不渲染，全部失败时 `ok: true` → 前端仍切到"已提交"视图 | **P0** |
| 9 | `GET /api/lifecycle` | BLOCKED 状态记录 | `failedRows()` 正则 `/failed\|rejected\|fail/i` — 不包含 `blocked` | BLOCKED Alpha 在任何视图中都不可见 | **P0** |
| 10 | `POST /api/check` | `checks[].detail` 字段 (25+ 检查项的详细原因) | `humanCheckName()` 仅覆盖 8/25+ 检查名，其余显示原始英文名 | 用户无法理解失败原因 | **P0** |
| 11 | `POST /api/check` | `requires_official_check` (boolean) | 前端 `isOfficialPassedCheck()` 使用但 UI 不单独标示 | 用户看不到"待官方检查"状态 | **P1** |
| 12 | `POST /api/check` | `cloud_correlation_risk.max_similarity` / `matched_alpha_id` / `matched_status` | 仅用 `level` 判断风险 | 数字精度完全丢失 | **P1** |
| 13 | `POST /api/check` | `cloud_status.match` (匹配方式) | 完全不渲染 | 用户不知道云端是用 ID 还是表达式匹配的 | **P1** |
| 14 | `POST /api/submit` | `submission` (dict) | 仅 JSON.stringify 原样展示 | 不解析 `status/message/alpha_id`，用户看不懂提交结果 | **P1** |
| 15 | `GET /api/profile` | `profile.username` | 未显示 | 用户看不到当前登录账号名 | P2 |
| 16 | `GET /api/check_results` | `results[]` 持久化检查结果 | `loadCheckResults()` 调用但渲染逻辑不完备 | 刷新后检查结果恢复存在但部分字段丢失 | **P1** |
| 17 | `GET /api/status` (job完成时) | `result.summary` / `result.candidates` / `result.events` | SSE 路径走 `progress.data`，polling 路径走 `data.result` | **两条路径数据结构不同**，迁移可能存在重复渲染 | **P1** |

---

## 三、状态机 / 生命周期状态码分歧

| # | 状态 | 后端定义 | 前端认知 | 差异 | 严重度 |
|---|------|---------|---------|------|--------|
| 18 | `submission_blocked` | 提交被安全门禁阻断 (web.py `record_submit_blocked`) | 无此概念，`failedRows()` 不匹配 | BLOCKED α 不可见 | **P0** |
| 19 | `BLOCKED` (gate status) | gate 返回 `BLOCKED` 时 pipeline 写入 lifecycle | 前端不处理此状态码 | 阻断原因不可见 | **P0** |
| 20 | `stopped` (job) | 用户主动停止 | SSE 路径识别为 `"已停止"` | 一致 ✅ | — |
| 21 | `stopping` (job) | 用户请求停止但线程还在跑 | 前端不处理 `state === "stopping"` | 控制按钮在过渡期可能错误显示 | P2 |
| 22 | `production_gate` | `gate.submission_ready` 为 False | `humanCheckName` 未映射 → 显示原始 `production_gate` | 不可读 | **P1** |
| 23 | `cloud_self_correlation` | risk level `high/medium/low` | `humanCheckName` 映射为"云端自相关" | 映射存在但 `detail` 不渲染 | P2 |

---

## 四、字段类型 / 枚举不一致

| # | 字段 | 后端值/类型 | 前端假设 | 差异 | 严重度 |
|---|------|-----------|---------|------|--------|
| 24 | `progress.percent` | `int` 0-100 | `progressEtaState` 期望数值 | 一致 ✅ | — |
| 25 | `checkResults[].timestamp` | 后端未持久化 timestamp | 前端 `isFreshCheck()` 需要时间戳 | **后端 check 结果缺少时间戳字段** | **P1** |
| 26 | `cloud_alphas[].status` | 混合大小写 (`ACTIVE`, `Submitted` 等) | 前端 `.toUpperCase()` 统一比较 | 一致但脆 — 依赖前端归一化 | P2 |
| 27 | `settings.type` | `str` 枚举 (`REGULAR`, `POWER_POOL`, `ATOM`, `PYRAMID`) | 前端 `<select id="alphaType">` 有全部 4 个值 | 一致 ✅ | — |
| 28 | `progress.phase` | 后端自由字符串 | 前端 `phaseName()` 映射 25 个阶段名 | 后端新增 phase 时前端若不更新会显示原始英文 | P2 |

---

## 五、结构性问题

| # | 问题 | 详情 | 严重度 |
|---|------|------|--------|
| 29 | **`check_candidate(payload)` 函数未定义** | `web.py` 第 419 行调用 `check_candidate(payload)`，但该文件内不存在此函数。实际检查函数名为 `check_candidate_availability()`（在 `run_check_batch_job` 中调用）。`/api/check` 单个检查路径可能在运行时抛出 `NameError`。 | **P0** |
| 30 | **`waitForJobSSE` 非 async 函数内使用 `await`** | 第 1353-1377 行：`source.onmessage = (event) => { ... await loadLifecycle(); ... }` 在非 async 回调中使用 `await`，浏览器会抛出 SyntaxError。已知问题（REVIEW.md R-05）。 | **P0** |
| 31 | **SSE 路径 vs Polling 路径数据合并策略不同** | SSE 用 `progress.data` 最终状态，Polling 用 `data.result`。如果 SSE 失败 fallback 到 polling，可能收到不同结构的数据。 | P2 |
| 32 | **`humanCheckName()` 仅覆盖 8/25+ 检查项** | 存在硬编码的 8 个检查名映射表，其余 17+ 检查项（如 `BRAIN_CHECK:*`, `not_failed_locally`, `cloud_sync_available` 等）直接显示原始英文 key。 | **P0** |

---

## 六、汇总统计

| 类别 | 数量 |
|------|------|
| **P0 (阻断级)** | 7 项 |
| **P1 (高优先级)** | 9 项 |
| **P2 (改善级)** | 9 项 |
| ✅ 一致项 | 7 项 |
| **总差异项** | **32 项** |

---

## 七、关键风险

1. **`check_candidate()` 缺失** 意味着单条 Alpha 检查功能**在代码层面不可运行**——任何人点击"检查"按钮都可能得到 500 错误或 `NameError`。
2. **SSE `await` 语法错误** 意味着现代浏览器中 SSE 路径**完全不可用**，且 fallback polling 也因 try-catch 可能被吞。
3. **BLOCKED 状态完全不可见** 意味着被安全门禁阻断的提交记录用户永远看不到——安全机制失效。
