# 1.3 后端逻辑缺陷识别清单

> **审计日期**：2026-05-15  
> **审计方法**：审查 `web.py`、`pipeline.py`、`brain_api/official.py`、`research/safety.py`、`research/scoring.py`、`research/alpha_checks.py` 及配置层 `config.py`

---

## 一、缺失校验 (Missing Validation)

| # | 位置 | 缺失项 | 当前行为 | 风险 | 严重度 |
|---|------|--------|---------|------|--------|
| B1 | `web.py:run_config_from_payload()` | **settings 字段类型校验** | `BrainSettings(delay=int(...), decay=int(...))` 等直接类型转换，不传值时 `int(None)` 抛 TypeError | 恶意/错误 payload 导致 500 | **P1** |
| B2 | `web.py:run_config_from_payload()` | **settings 枚举值范围校验** | `region="XYZ"` 直接透传 — BRAIN API 可能返回 cryptic error | 错误难以诊断 | **P1** |
| B3 | `web.py:submit_candidate()` | **重复提交检测（云端实时）** | 只检查 `SubmissionLedger` 本地记录和 `check_candidate_availability` 中的历史检测，不实时查询 BRAIN API 当前状态 | 可能在 BRAIN 侧已存在的 Alpha 被重复提交 | P2 |
| B4 | `web.py:run_job()` | **认证失败不中断** | `run_pipeline_from_config` 内部认证可能失败但 pipeline 继续运行 | 生产环境下静默降级为无认证运行 | **P1** |
| B5 | `research/pipeline.py` | **fields/operators 刷新失败静默忽略** | `_refresh_context()` 中异常被 `pass` 吞掉 | 字段缓存过期后生成表达式的字段可能不可用 | **P1** |
| B6 | `config.py` | **配置值范围校验** | `_update_dataclass` 直接写入 JSON 值，不校验类型/范围/枚举 | 配置文件中负数或字符串可能导致运行时崩溃 | P2 |

---

## 二、未处理的边界条件

| # | 位置 | 边界条件 | 当前行为 | 影响 | 严重度 |
|---|------|---------|---------|------|--------|
| B7 | `web.py:submit_candidate()` | **candidate 无 `official_alpha_id`** | 返回 "Missing official Alpha ID" 错误，但 `record_submit_blocked()` 因 try/except pass 可能静默失败 | 阻断记录丢失 | P2 |
| B8 | `web.py:submit_batch()` | **`alpha_ids` 列表为空** | 返回 `submitted=0, failed=0, results=[]`，但 `ok: true` | 前端收到 `ok:true` 但实际什么都没做 | P2 |
| B9 | `web.py:_user_profile_snapshot()` | **无 active job 且无 `/api/profile` 缓存** | 返回 `tier: "offline"` 等硬编码默认值 | 前端显示"离线"但实际可能只是未运行流水线 | P2 |
| B10 | `brain_api/official.py` | **分页循环无最大页数** | `list_fields/list_operators/list_user_alphas` 依赖返回数量判断结束，无 `max_pages` 保护 | 上游异常返回固定满页时可能死循环 | P2 |
| B11 | `web.py:lifecycle_from_job()` | **`lifecycle.jsonl` 文件过大** | 每次读取 `limit=1000` 但 `merged[-1000:]` 依赖内存中全量合并 | 文件持续增长（2026-05-14 已有 28MB）将导致 OOM | P2 |
| B12 | `web.py:cloud_alpha_snapshot()` | **`cloud_alphas.jsonl` 为空且无 API 缓存** | `_cloud_alpha_summary([])` 正常返回但不设置 `is_empty` 标志 | 前端误以为"已同步过但是0条" | P2 |

---

## 三、状态机漏洞

| # | 状态转换 | 漏洞 | 影响 | 严重度 |
|---|---------|------|------|--------|
| B13 | `candidate → submitted` | **提交成功后不更新客户端的 candidate 数据** | `submit_candidate()` 返回 `submission` 结果但 pipeline 中的 `Candidate` 对象未标记为 `lifecycle_status="submitted"` | 同一 Alpha 可能被反复提交 | **P1** |
| B14 | `job: running → stopped` | **`JOBS.cancel()` 设置 `cancel=True` 但 `run_job()` 中的 `stop_callback` 只检查一次** | 如果 `run_pipeline_from_config` 在长时间运行的阶段（如官方 simulation）中，cancel 可能延迟生效 | 用户点"停止"后任务可能继续运行数分钟 | P2 |
| B15 | `job: completed → (无后续)` | **`JOBS.jobs` 无自动清理** | completed/failed jobs 永久保留在内存中 | 长时间运行后内存泄漏 | P2 |
| B16 | `check: 未持久化 timestamp` | `check_candidate_availability()` 返回结果中**没有 `checked_at` 时间戳** | 前端 `isFreshCheck()` 无法判断检查是否过期 | 用户无法知道检查何时做的 | **P1** |
| B17 | `submission: BLOCKED → (无路径)` | submission_blocked 后无"解除阻断"或"重新检查"机制 | 被阻断的 Alpha 永久滞留在 blocked 状态 | 用户无法恢复 | P2 |

---

## 四、幂等性与并发问题

| # | 位置 | 问题 | 当前保护 | 风险 | 严重度 |
|---|------|------|---------|------|--------|
| B18 | `web.py:submit_candidate()` | **无分布式幂等保护** | `SUBMIT_LOCK` 只保护同一进程 | 多标签页/多进程可能重复提交 | P2 |
| B19 | `web.py:submit_batch()` | **批量提交中部分失败的幂等** | 失败项在 `results[]` 中返回但已成功的项不回滚 | 重试时会重复提交已成功的项 | **P1** |
| B20 | `web.py:check_candidate()` | **函数不存在** | 详见差异清单 #6 | 单条检查功能完全不可用 | **P0** |
| B21 | `web.py:JOBS/SYNC_JOBS/CHECK_JOBS` | **三个独立的 JobStore 实例** | 各自独立，但 `active_auxiliary_operation()` 通过检查 `latest_active()` 实现互斥 | 并发安全但耦合松散 | P2 |

---

## 五、异常处理缺陷

| # | 位置 | 问题 | 当前处理 | 影响 | 严重度 |
|---|------|------|---------|------|--------|
| B22 | `web.py:run_job()` L615-622 | **只有 `except Exception` 一个分支** | 所有异常归为 "failed"，错误消息经 `safe_error_message()` 脱敏 | 无法区分认证失败 vs 参数错误 vs 官方限流 | P2 |
| B23 | `web.py:submit_candidate()` | **`SubmissionLedger.record()` 和 `repo.save_lifecycle_record()` 失败被 `pass`** | 静默吞异常 | 提交审计日志可能不完整 | P2 |
| B24 | `research/pipeline.py` | **多处 `except: pass` 静默吞异常** | REVIEW.md M-11 记录 5 处 | 安全检查降级无感知 | **P1** |
| B25 | `web.py:_handle_sse_stream()` | **`BrokenPipeError/ConnectionResetError/OSError` 仅捕获不通知** | 客户端断开时服务端静默退出，不记录日志 | 无法追踪 SSE 连接质量 | P2 |

---

## 六、数据一致性问题

| # | 问题 | 详情 | 严重度 |
|---|------|------|--------|
| B26 | **progress.data 结构无 schema 约束** | `run_pipeline_from_config` 通过 `progress_callback` 传递任意 dict — 前端假设的字段（如 `data.candidates`, `data.summary.strategy_profile`）可能缺失 | P2 |
| B27 | **backtests 数据源不唯一** | `run_job()` 在 L598-599 和 L615-622 分别从 `result_data.summary.backtest_slots` 和 `last_data.backtests` 获取 — 两处可能不同 | **P1** |
| B28 | **cloud_alphas 多源合并逻辑复杂** | `cloud_alpha_snapshot()` 优先 `cloud_alphas.jsonl`，fallback `api_cache/user_alphas_*.json`，两处数据格式可能不同 | P2 |

---

## 七、性能与资源问题

| # | 问题 | 详情 | 严重度 |
|---|------|------|--------|
| B29 | **`lifecycle.jsonl` 无归档/清理策略** | 文件截至 2026-05-14 已达 28MB，每次请求读取并合并到内存 | **P1** |
| B30 | **`cloud_alphas.jsonl` 无保留策略** | 348MB events + 42MB cloud alphas + 28MB lifecycle — 每次 `_read_storage_jsonl` 全量加载 | **P1** |
| B31 | **`job.progress` 对象在 SSE 推送中每次序列化整个 data 字典** | `run_job()` 在 L595-596 将整个 `result_data.summary` + `candidates` + `backtests` 合并后塞入 progress，SSE 每 1s 推送此完整副本 | P2 |

---

## 八、与前端契约的断层（重复差异清单中的关键项）

| # | 问题 | 关联差异项 |
|---|------|----------|
| B32 | **`check_candidate()` 函数不存在** → 单条检查不可用 | Gap #6 (P0) |
| B33 | **check 结果无 `timestamp` 字段** | Gap #25 (P1) |
| B34 | **`submit_batch` 不标记已成功项** | Gap #8 (P0) |
| B35 | **pipeline 不生成 `phase_label` / `check_label_cn`** | 前端硬编码映射 |

---

## 九、汇总

| 类别 | P0 | P1 | P2 | 总计 |
|------|-----|-----|-----|------|
| 缺失校验 | 0 | 3 | 3 | 6 |
| 边界条件 | 0 | 0 | 6 | 6 |
| 状态机漏洞 | 0 | 2 | 3 | 5 |
| 幂等/并发 | 1 | 1 | 2 | 4 |
| 异常处理 | 0 | 1 | 4 | 5 |
| 数据一致性 | 0 | 1 | 2 | 3 |
| 性能/资源 | 0 | 2 | 1 | 3 |
| 契约断层 | 2 | 1 | 0 | 3 |
| **总计** | **3** | **11** | **21** | **35** |

---

## 十、TOP 5 关键缺陷

1. **B20** — `check_candidate()` 函数不存在，单条 Alpha 检查完全不可用
2. **B5** — Fields/Operators 刷新失败静默忽略，表达式生成可能使用过期上下文
3. **B16** — Check 结果缺少 `timestamp`，前端无法判断检查是否过期
4. **B19** — 批量提交中已成功项无幂等保护，重试会重复提交
5. **B29/B30** — lifecycle.jsonl (28MB)、cloud_alphas.jsonl (42MB)、events.jsonl (348MB) 无归档策略
