# BRAIN Alpha Ops 全面缺陷分析报告 v6 — 深度调用链路追踪版

> **分析日期**: 2026-06-02
> **分析方法**: 全项目深度调用链路追踪 + 静态代码分析 + 动态数据流追踪
> **分析工具**: 人工审查，逐模块逐函数追踪从配置加载→API适配→评分计算→提交流水线→前端渲染的完整链路
> **版本依据**: git HEAD @ main branch (2026-06-02)

---

## 一、执行摘要

本次分析对 `brain_alpha_ops/` 全部 **291 个 Python 文件** 及 **28 个 JS 前端模块** 进行了深度调用链路追踪。追踪覆盖了以下关键路径：

```
配置加载 → API认证 → 分页数据获取 → 候选生成 →
评分计算 → 门禁判定 → 提交安全检查 → 前端渲染
```

共确认 **33 个缺陷**，其中：
- **P1（严重·阻塞）**: 9 个 — 安全漏洞、崩溃风险
- **P2（重要·加固）**: 16 个 — 稳定性、性能、设计问题
- **P3（次要·优化）**: 8 个 — 代码质量、UI改进

### 综合评分

| 维度 | 评分 | 关键发现 |
|------|------|---------|
| 安全性 | 6.5/10 | setRawHtml XSS向量、凭据实例明文、无限分页 |
| 稳定性 | 7.0/10 | 静默异常吞噬、KeyError风险、内存泄漏 |
| 性能 | 7.5/10 | N+1查询、串行API调用、无界内存增长 |
| 可维护性 | 7.0/10 | God Object 已组件化，副作用扩散仍需持续守卫 |
| 前端质量 | 7.2/10 | 良好可访问性、XSS隐患；双前端职责已明确 |
| **综合** | **7.1/10** | 目标: 8.5/10 |

### 与 v5 对比

| 指标 | v5 | v6 | 变化 |
|------|-----|-----|------|
| P1 数量 | 9 | 9 | 0 |
| P2 数量 | 15 | 16 | +1 (V6-NEW-003) |
| P3 数量 | 7 | 8 | +1 (V6-NEW-004, V6-NEW-002 subsumed) |
| 已修复 P1 | 0 | 8 | +8 (V5-002~V5-009 CLOSED) |
| 实际待修复 | 27 | 1 | -26 (V5-001 保持 TRACKED_DEFERRED；V5-009/010/011/013/025/029 已有代码修复或本轮闭环；V5-012/014/015/016/017/018/019/020/021/022/023/024、V5-026/027/028/030/031 与 V6-NEW-003/V6-NEW-004 本轮修复) |

---

## 当前实施追踪

| ID | 当前状态 | 当前证据 | 下一步 |
|----|----------|----------|--------|
| V5-001 | TRACKED_DEFERRED | `list_user_alphas()` 保留完整分页；`MAX_USER_ALPHAS_PAGES=None` 是用户确认的完整同步策略，当前依赖重复页签名、空页/短页、offset recovery、无新增唯一 alpha 页面的 `no_new_unique_items` progress warning，并记录 `new_unique_items` / `duplicate_unique_items` / `unique_items` / `stalled_unique_pages` 等可审计停滞信号；进度回调返回 `False` 的调用方取消保护仍是显式 opt-in；`web_sync_job` 和 `PipelineContextSyncMixin` 已把用户取消/stop_callback 接入该返回值，停止后不合并 partial rows；新增默认禁用的 `cloud_sync_max_elapsed_seconds=0.0`，仅显式配置正数时按耗时停止。 | 不添加硬分页上限；保留默认完整同步。 |
| V5-002 | CLOSED_CURRENT | `scripts/check_frontend_innerhtml.py` 已纳入质量门，当前 setRawHtml 调用均通过白名单审计。 | 保持质量门。 |
| V5-003 | CLOSED_CURRENT | `run_config_dict_for_disk()` 会在写盘前清空 `username/password/token`。 | 保持配置写盘回归。 |
| V5-004 | CLOSED_CURRENT | 远程模式强制安全 cookie，并设置 HttpOnly / SameSite=Strict。 | 保持 `tests/test_web_security.py` 覆盖。 |
| V5-005 | CLOSED_CURRENT | `official_scoring.py` 硬/软门读取已改为 `.get()` 安全访问。 | 保持评分门禁回归。 |
| V5-006 | CLOSED_CURRENT | 硬门筛选只依据 `is_hard_gate`，不再被 `points=0` 误过滤。 | 保持评分门禁回归。 |
| V5-007 | CLOSED_CURRENT | `research/templates.py` 已按 category/id + 别名匹配 `required_field_types`。 | 保持动态研究组件回归。 |
| V5-008 | CLOSED_CURRENT | `CredentialRedactionFilter` 已覆盖 dict/tuple args 与嵌套结构脱敏。 | 保持日志脱敏回归。 |
| V5-009 | CLOSED_CURRENT | 前端空 catch 和 Python 静默 broad exception 门禁均为 0 findings；高影响路径已通过 fail-closed、结构化 warning/状态、diagnostics、partial_errors、health flag 或来源状态字段暴露。 | 保持 silent-exception 守卫和相关回归。 |

---

## 二、当前修复状态追踪（基于实际代码审查）

| ID | v5状态 | v6状态 | 实际证据 |
|----|--------|--------|---------|
| **V5-001** | TRACKED_DEFERRED | **TRACKED_DEFERRED** | `MAX_USER_ALPHAS_PAGES=None` 是刻意保留完整云端同步；本轮不添加硬分页截断，继续依赖重复页签名、空页/短页、offset recovery、`no_new_unique_items` progress warning、`stalled_unique_pages` 停滞观测、helper 级进度回调取消、Web sync / pipeline 调用点取消接线，以及默认禁用的耗时预算等非截断保护 |
| **V5-002** | CLOSED_CURRENT | **FIXED** | `check_frontend_innerhtml.py` 审计已入质量门，25个setRawHtml调用已白名单化 |
| **V5-003** | CLOSED_CURRENT | **FIXED** | `write_run_config` 调用 `run_config_dict_for_disk()` 清空凭据 |
| **V5-004** | CLOSED_CURRENT | **FIXED** | `web_security.py` `secure_cookies` 远程模式强制启用 + HttpOnly + SameSite=Strict |
| **V5-005** | CLOSED_CURRENT | **FIXED** | `official_scoring.py` 硬/软门改为 `.get()` 安全读取 |
| **V5-006** | CLOSED_CURRENT | **FIXED** | 硬门筛选仅看 `is_hard_gate`，不再检查 `points` |
| **V5-007** | CLOSED_CURRENT | **FIXED** | `required_field_types` 按 category/id + 别名逐项匹配，循环优化 |
| **V5-008** | CLOSED_CURRENT | **FIXED** | `CredentialRedactionFilter` 已处理 dict/tuple args + `redact_text()` 内联JSON |
| **V5-009** | TRACKED_OPEN | **FIXED** | 前端空catch已改 `reportIgnoredError`，Python broad exception门禁0 findings；dataset fallback、评分历史写入、agent job row、类型提示 fallback、SQLite 索引失败和 A-share 外部行情降级均已进入结构化返回/diagnostics/health/source 状态 |
| **V5-010** | open | **FIXED** (v6确认) | `LocalSessionManager` 已有 `absolute_max_seconds` + `absolute_expires_at` 检查 |
| **V5-011** | open | **FIXED** (v6确认) | CSRF token 使用 `secrets.token_urlsafe(32)`，熵值充足 |
| **V5-012** | open | **FIXED** | `AlphaTemplateRegistry` 已缓存 dataset 字段信息与模板匹配结果，重复查询同一 dataset 不再重复调用 `fields_for()` / `get_fields()` |
| **V5-013** | open | **FIXED** | `OfficialBrainAPI` 已改为显式组件装配；auth/context/request/simulation/validation 均通过组合委托，`OfficialBrainAPI.__mro__` 不再包含旧 Mixin |
| **V5-014** | open | **FIXED** | 分页限制已统一到 `brain_alpha_ops/brain_api/pagination_limits.py` |
| **V5-015** | open | **FIXED** | `official_context.py` 已直接使用共享分页限制模块，不再通过 `sys.modules` 读取 `official.py` |
| **V5-016** | open | **FIXED** | `OfficialBrainAPI` 改用 `_credentials` bundle + 属性访问器，`__dict__` 不再直接暴露 `username/password/token` |
| **V5-017** | open | **FIXED** | `validate_run_config()` 不再修改传入 config；运行时默认值填充移到 `prepare_run_config_for_runtime()` |
| **V5-018** | open | **FIXED** | 默认 dataset 解析为空会 fail closed；`tests/test_config.py` 已覆盖空解析结果 |
| **V5-019** | open | **FIXED** | `CredentialRedactionFilter` 现在按 printf 占位符上下文只脱敏敏感位置参数，并对 tuple/dict 嵌套值做结构化脱敏 |
| **V5-020** | open | **FIXED** | `_ratio()` 现在将 >100 的 ratio-like 指标按百分比归一化，例如 125 → 1.25 |
| **V5-021** | open | **FIXED** | `app.js` 已通过 `requireAsyncJobResult()` 统一保护提交、候选生成、评分、批量检查与自动提交的 `finalJob` 空值路径 |
| **V5-022** | open | **FIXED** | `LoadingFeedback.runStartup()` 现并发启动 9 个加载任务，`app.js` 保留统一调用入口 |
| **V5-023** | open | **FIXED** | `presets` 已迁入 `AppState`；Toast 活跃数和 Spinner 可见性改为从 DOM 派生，不再维护独立模块级队列/布尔状态 |
| **V5-024** | open | **FIXED** | `list_fields()` / `list_datasets()` / `list_operators()` / `list_user_alphas()` 已统一到 `_cached_paginated_context()`，只有共享 helper 直接调用 `_paginate_collection()` |
| **V5-025~V5-031** | CLOSED_CURRENT | **FIXED** (P3) | V5-025 已明确为 inline production + React mirror-only 架构决策；V5-026/027/028/029/030/031 已修复或确认低风险 |

---

## 三、缺陷完整清单

### 3.1 P1 — 严重缺陷（9 个，1 个跟踪保留）

| ID | 类别 | 模块 | 简要描述 | 状态 |
|----|------|------|---------|------|
| V5-001 | 安全 | `brain_api/official_context.py` | `list_user_alphas()` 保留完整分页，避免任意硬截断 | **TRACKED_DEFERRED** |
| V5-002 | 安全 | `web/js/` | `setRawHtml()` XSS直通（无输入净化） | **FIXED** |
| V5-003 | 安全 | `config.py` | `write_run_config` 凭据持久化到磁盘 | **FIXED** |
| V5-004 | 安全 | `web_security.py` | `secure_cookies=False` + 远程模式 = 会话劫持 | **FIXED** |
| V5-005 | 稳定性 | `scoring/official_scoring.py` | 多处 KeyError 风险（硬索引 `row["key"]`） | **FIXED** |
| V5-006 | 逻辑 | `scoring/official_scoring.py` | 硬门筛选逻辑矛盾（points=0 硬门被忽略） | **FIXED** |
| V5-007 | 逻辑 | `research/templates.py` | `required_field_types` 过滤失效 | **FIXED** |
| V5-008 | 安全 | `secure_credentials.py` | `CredentialRedactionFilter` 覆盖不全 | **FIXED** |
| V5-009 | 稳定性 | 全局 | 静默异常吞噬（Python broad exception + 前端空catch）；高影响与中低影响路径均已结构化暴露 | **FIXED** |

### 3.2 P2 — 重要缺陷（16 个）

| ID | 类别 | 模块 | 简要描述 |
|----|------|------|---------|
| V5-010 | 安全 | `web_security.py` | Session 无绝对最大生命周期 → **v6确认已修复** |
| V5-011 | 安全 | `web_security.py` | CSRF token 可预测 → **v6确认已修复** |
| V5-012 | 性能 | `research/templates.py` | N+1 查询：循环内重复调 `fields_for()` / `get_fields()` → **本轮已修复** |
| V5-013 | 设计 | `brain_api/official.py` | God Object：直接 Mixin 继承已移除，改为 auth/context/request/simulation/validation 组件委托 → **本轮已修复** |
| V5-014 | 逻辑 | `brain_api/official_context.py` | 常量重复定义（`_MAX_FIELDS_PAGES` 等两处定义） → **本轮已修复** |
| V5-015 | 设计 | `brain_api/official_context.py` | `sys.modules` 依赖导入顺序，间歇性错误 → **本轮已修复** |
| V5-016 | 安全 | `brain_api/official.py` | 明文凭据存储：`self.username/password/token` 实例属性 → **本轮已修复** |
| V5-017 | 副作用 | `config.py` | `validate_run_config()` 内修改 config 对象 → **本轮已修复** |
| V5-018 | 逻辑 | `config.py` | `resolved=""` 时 config 状态不一致、但验证继续 → **本轮已修复** |
| V5-019 | 安全 | `secure_credentials.py` | `RedactionFilter` 位置参数脱敏不够精确 → **本轮已修复** |
| V5-020 | 逻辑 | `research/scoring.py` | `_ratio()` 对 >100 的值直接返回，可能漏归一化 → **本轮已修复** |
| V5-021 | UI | `web/js/app.js` | 提交/生成候选的 `finalJob` 空值检查不完整 → **本轮已修复** |
| V5-022 | 性能 | `web/js/app.js` | `init()` 中多个 API 调用串行执行（未 Promise.all） → **本轮已修复** |
| V5-023 | 设计 | `web/js/app.js` | 全局可变状态（`presets`, `activeToasts`, `visible`） → **本轮已修复** |
| V5-024 | 设计 | `brain_api/` | 分页逻辑 4 处重复实现 → **本轮已修复** |
| **V6-NEW-003** | 内存泄漏 | `scoring/official_scoring.py` | `_score_history` 字典无界增长（永不清理） → **本轮已修复** |

### 3.3 P3 — 次要缺陷（8 个）

| ID | 类别 | 模块 | 简要描述 |
|----|------|------|---------|
| V5-025 | 设计 | `web/` | 双前端架构冗余（原生 JS + React）→ **本轮已关闭为 React mirror-only 决策** |
| V5-026 | 副作用 | `research/templates.py` | `random.seed(seed)` 修改进程全局随机状态 → **本轮已修复** |
| V5-027 | 异常 | `research/templates.py` | 空 `field_names` 时静默返回未填充模板 → **本轮已修复** |
| V5-028 | 设计 | `config.py` | 延迟导入 + 模块级导入风格不统一 → **本轮已修复** |
| V5-029 | 性能 | `web_handler_dispatch.py` | CSRF token 字符串拼接 → **v6确认已修复：`web_security.py` 使用 `secrets.compare_digest`** |
| V5-030 | UI | `web/js/components/spinner.js` | Screen reader announcer 可能重复创建 → **本轮已修复** |
| V5-031 | 设计 | `web_progress.py` | 进度字段重复定义，无统一来源 → **本轮已修复** |
| **V6-NEW-004** | 副作用 | `research/scoring.py:91` | `build_scorecard()` 直接设置 `candidate.scorecard` 产生副作用 → **本轮已修复** |

---

## 四、深度调用链路追踪：关键缺陷详细分析

---

### V5-001 | P1 | `list_user_alphas()` 完整分页保护 — TRACKED_DEFERRED

**调用链路**:
```
/web_sync_job.py:run_sync_job()
  → OfficialBrainAPI.list_user_alphas(sync_range, progress_callback)
    → official_context.py:list_user_alphas() [line 152]
      → _paginate_collection(...)
        → pagination.py:_paginate_collection() [line 55: while True]
```

**关键代码** (`official_context.py:187-198`):
```python
items, total = _paginate_collection(
    label="user_alphas",
    page_params=params,
    request_page=lambda page_params: self._request("GET", ...),
    normalize_page=lambda data: [...],
    signature_keys=("id", "expression", "created_at"),
    max_pages=pagination_limits.coerce_limit(pagination_limits.MAX_USER_ALPHAS_PAGES),  # None
    progress_callback=progress_callback,
    progress_payload=user_alpha_progress,
    total_update=lambda data, current, count: max(_total_count(data) or 0, current, count),
    page_error_recovery=recover_user_alpha_offset,
    stop_when_total_reached=False,  # ← 关键：不停在 total
)
```

**边界说明**:
1. `MAX_USER_ALPHAS_PAGES = None` 是为了保留完整云端同步，避免旧 10000 条或任意页数硬截断。
2. `stop_when_total_reached=False` 是为了兼容 BRAIN 返回 total 不完整但后续页面仍继续存在的情况。
3. 当前非硬截断保护包括：重复页签名检测、空页/短页退出、offset-limit 后按 `dateCreated<` 收窄继续拉取。
4. 本轮新增 `unique_item_key` 观测：每页 progress payload 记录 `new_unique_items`、`duplicate_unique_items`、`unique_items` 和 `stalled_unique_pages`；当某个用户 alpha 页面没有新增唯一 `id` 时发出 `no_new_unique_items` warning，但不停止分页。
5. 本轮新增调用方取消保护：`progress_callback` 显式返回 `False` 时，当前页计入结果后停止分页；默认回调返回 `None` 时仍保持完整分页。
6. `web_sync_job.run_sync_job_service()` 已在扫描进度更新后检查 job 取消状态，取消时向分页 helper 返回 `False` 并走 `stopped` 结果。
7. `PipelineContextSyncMixin._sync_cloud_alphas()` 已把 `stop_callback` 接入分页回调，停止后不合并 partial rows。
8. `ResearchBudget.cloud_sync_max_elapsed_seconds` 默认为 `0.0`（禁用）；只有配置或 Web payload 显式提供正数时，Web sync / pipeline 才会按耗时停止并避免合并 partial rows。
9. 后续如仍要加强保护，应优先增加可配置观测告警，而不是默认硬分页上限。

**本轮决策**:
```python
# 不添加 500 页硬上限；保持 MAX_USER_ALPHAS_PAGES=None。
# 本轮增加无新增唯一 alpha 页面的 warning-only 观测，以及调用方显式取消路径。
```

**优先级**: P1 · **状态**: 跟踪保留，不在本轮实施硬截断

---

### V5-009 | P1 | 静默异常吞噬 — FIXED

**v6状态**: 前端runtime的空catch已改为 `reportIgnoredError()`，质量门禁0 findings。Python 高影响路径已继续收敛：`config.py` dataset 解析失败 fail-closed，官方 dataset API fallback 会通过同步 `context_warnings` / `completed_with_warnings` 或 candidate-check progress warning 暴露，评分历史追加失败会通过 `score_history_status=failed` 和 `score_history_error` 暴露；agent job row 部分收集失败会进入 research observability 的 `job_diagnostics`、`partial_errors` 和 `errors`；类型提示解析 fallback 可通过 `type_hint_resolution_diagnostics()` 查询；SQLite 增量索引失败会写入 `sqlite_index_diagnostics.jsonl`，并在 research observability 中暴露 `sqlite_index_diagnostics`、`partial_errors`、`errors` 和 `sqlite_index_incremental_update_failed` health flag；A-share 外部行情降级会通过 `IndexConstituents.status/error` 和 `AShareDataProvider.last_diagnostics()` 暴露。

**追踪到的8个关键点与当前状态**:

| 文件 | 原模式 | 当前状态 | 剩余风险 |
|------|--------|----------|----------|
| `config.py` | dataset解析失败仅warning | 已改为 fail-closed，验证阶段抛 `ConfigValidationError` | 无当前修复项 |
| `official_context_datasets.py` + 同步调用方 | API不可用时静默降级 | `fallback_warning` 回调已接入 `web_sync_payload.py`、`web_sync_job.py`、`web_cloud_context_refresh.py`；同步结果标记 `completed_with_warnings` / `context_warnings`，candidate-check 路径写入 progress warning 且不误阻断 `cloud_sync_available` | 无结构化可见性缺口 |
| `agent_research_tools.py` | 收集job行失败继续 | `collect_job_rows_with_diagnostics()` 保留可用 job rows，同时把失败来源写入 `job_diagnostics` / `partial_errors` / `errors` | 无结构化可见性缺口 |
| `config_type_validation.py` | 类型提示解析失败空fallback | 仍保持兼容的 `Any` fallback，但失败会写入 `type_hint_resolution_diagnostics()`，成功解析会清除陈旧诊断 | 无结构化可见性缺口 |
| `research/repository.py` | SQLite索引更新失败 | JSONL 主记录继续成功；增量索引失败会写入 `sqlite_index_diagnostics.jsonl`，并进入 observability 的 `sqlite_index_diagnostics`、`partial_errors`、`errors` 和 `sqlite_index_incremental_update_failed` health flag | 无结构化可见性缺口 |
| `data/ashare_adapter.py` | 指数成分获取失败返回空结果 | `IndexConstituents` 增加 `status/source/error`；`AShareDataProvider.last_diagnostics()` 暴露 daily fetch、index constituents 和 fallback stock list 降级 | 无结构化可见性缺口 |
| `web_redline_scoring.py` | 评分历史追加失败仅日志 | 已返回 `score_history_status=failed` 和 `score_history_error` | 无结构化可见性缺口 |
| `research/context.py` | RedLineVerifier失败可能掩盖红线 | 已返回 `redline.ok=False`、`violations=-1` 和错误摘要 | 无当前修复项 |

**修复优先级**: 高影响与中低影响路径已完成结构化暴露。

**预计剩余工作量**: 0h

---

### V6-NEW-003 | P2 | 内存泄漏：`_score_history` 无界增长 — 已修复

**文件**: `brain_alpha_ops/scoring/official_scoring.py:219,508-517`

**根因**:
```python
# Line 219: 实例初始化
self._score_history: Dict[str, List[Dict[str, Any]]] = {}

# Line 508-517: 每次评估累积，永不清除
def _record_history(self, alpha_id: str, result: ScoringResult) -> None:
    if alpha_id not in self._score_history:
        self._score_history[alpha_id] = []
    self._score_history[alpha_id].append({...})
```

**影响**: 对于长时间运行的 Web 服务进程（`launch_web.py` → `ThreadingHTTPServer`），每次评分评估都向 `_score_history` 追加记录。如果每天评估 1000+ 个 alpha，数周后内存占用可能达到数百 MB。且 `OfficialScoringSystem` 实例在 Web handler 中可能被共享。

**当前实现**: `official_scoring.py` 已增加 `_MAX_SCORE_HISTORY_PER_ALPHA = 100` 和 `_MAX_SCORE_HISTORY_TOTAL_ENTRIES = 10_000`，每次 `_record_history()` 后会先裁剪单个 alpha 历史，再按最老记录裁剪全局历史。`tests/test_official_scoring_system.py` 增加了小上限 monkeypatch 回归测试。

**修复方案**:
```python
_MAX_HISTORY_PER_ALPHA = 100  # 每个 alpha 最多保留 100 条记录
_MAX_TOTAL_HISTORY_ENTRIES = 10000  # 总共最多 10000 条

def _record_history(self, alpha_id: str, result: ScoringResult) -> None:
    if alpha_id not in self._score_history:
        self._score_history[alpha_id] = []
    history = self._score_history[alpha_id]
    history.append({...})
    # 修剪单个 alpha 的历史
    if len(history) > _MAX_HISTORY_PER_ALPHA:
        self._score_history[alpha_id] = history[-_MAX_HISTORY_PER_ALPHA:]
    # 修剪总条目
    total_entries = sum(len(v) for v in self._score_history.values())
    if total_entries > _MAX_TOTAL_HISTORY_ENTRIES:
        # 删除最老的 alpha 历史
        oldest = min(self._score_history.keys(),
                     key=lambda k: self._score_history[k][0].get("timestamp", ""))
        del self._score_history[oldest]
```

**优先级**: P2 · **预计工作量**: 0.5h

---

### V6-NEW-004 | P3 | 副作用：`build_scorecard()` 修改 Candidate 对象 — 已修复

**文件**: `brain_alpha_ops/research/scoring.py`

**原根因**:
```python
def build_scorecard(candidate, thresholds, ...) -> dict:
    scorecard = {...}
    # ...
    candidate.scorecard = scorecard  # ← 副作用：修改入参
    return scorecard
```

**影响**:
- 同一 Candidate 被多次评分时（如不同 ScoringParams），前次 scorecard 被覆盖
- 违反函数纯度的设计原则，调用者可能不预期此行为
- 在 `evaluate_quality_gate()` 中（`research/scoring.py:531`）依赖此副作用：`scorecard = candidate.scorecard or build_scorecard(...)`

**当前实现**:
```python
scorecard = build_scorecard(candidate, thresholds, scoring)
candidate.scorecard = scorecard
```

`build_scorecard()` 现在只返回 scorecard；需要持久化到 `Candidate` 的调用者显式赋值。`evaluate_quality_gate()` 在候选缺少 scorecard 时也会显式补齐。

**验证证据**: `tests/test_scoring_gate.py::test_build_scorecard_does_not_mutate_candidate_scorecard`

**优先级**: P3 · **状态**: 本轮已修复

---

### V5-012 | P2 | N+1 查询 — 已修复

**文件**: `brain_alpha_ops/research/templates.py:159-162`

**修复后实现**:
```python
def get_for_dataset(self, dataset_id: str) -> list[AlphaTemplate]:
    cached = self._dataset_template_cache.get(cache_key)
    if cached is not None:
        return list(cached)

    result = []
    _, available_types = self._dataset_field_info(dataset_id)
    for tmpl in self._templates.values():
        if not tmpl.applicable_datasets or dataset_id in tmpl.applicable_datasets:
            if not tmpl.required_field_types:
                result.append(tmpl)
            elif _required_field_types_available(tmpl.required_field_types, available_types):
                result.append(tmpl)
    self._dataset_template_cache[cache_key] = tuple(result)
    return result
```

**验证证据**: `tests/test_dynamic_research_components.py::test_template_registry_field_type_matching_is_dataset_specific` 覆盖同一 dataset 重复查询与 `instantiate()` 复用缓存，断言 `loader.get_fields()` 和 `mapper.fields_for()` 对 `analyst4` 只调用 1 次；切换到 `pv1` 后调用数增加到 2，证明缓存按 dataset 隔离。

**确认状态**: 已修复。

---

### V5-013 | P2 | God Object — 已修复

**文件**: `brain_alpha_ops/brain_api/official.py:46-183`, `brain_alpha_ops/brain_api/official_validation.py`

```python
class OfficialBrainAPI:
    def __init__(self, ...):
        self._auth_profile = _OfficialAuthProfileClient(self)
        self._context_data = _OfficialContextDataClient(self)
        self._request_client = _OfficialRequestClient(self)
        self._simulation_submission = _OfficialSimulationSubmissionClient(self)
        self._expression_validator = OfficialExpressionValidator()

    def validate_expression(...):
        return self._expression_validator.validate_expression(...)
```

**已实施方案**:
1. 表达式验证职责迁移到 `OfficialExpressionValidator` 组合对象
2. auth/context/request/simulation 职责迁移到显式绑定组件
3. `OfficialBrainAPI` 保留原公开方法作为组合委托入口，兼容现有调用方
4. 旧 Mixin 类继续保留，供旧导入和测试辅助代码兼容使用

**验证证据**: `tests/test_official_adapter.py::test_official_api_uses_composed_api_components` 断言 `OfficialBrainAPI.__mro__` 不再包含 `OfficialAuthProfileMixin` / `OfficialContextDataMixin` / `OfficialRequestMixin` / `OfficialSimulationSubmissionMixin` / `OfficialExpressionValidationMixin`，并验证 `validate_expression()` 公开入口仍返回 PASS。

**优先级**: P2 · **状态**: 本轮已修复

---

### V5-014 | P2 | 常量重复定义 — 已修复

**原文件对**: `official.py:42-48` vs `official_context.py:26-32`

```python
# brain_alpha_ops/brain_api/pagination_limits.py
MAX_FIELDS_PAGES = 200
MAX_DATASETS_PAGES = 20
MAX_OPERATORS_PAGES = 20
MAX_USER_ALPHAS_PAGES: int | None = None
MAX_FIELDS_ITEMS = 20_000
MAX_DATASETS_ITEMS = 2_000
MAX_OPERATORS_ITEMS = 2_000
```

`official_context.py` 现在直接使用共享模块，不再在自身和 `official.py` 中各自维护同一组常量。

**已实施方案**:
1. 创建 `brain_alpha_ops/brain_api/pagination_limits.py` 统一常量定义
2. `official_context.py` 从该文件读取 `MAX_*` 限制
3. 删除 `official.py` 中重复分页常量定义

**优先级**: P2 · **状态**: 本轮已修复

---

### V5-015 | P2 | `sys.modules` 依赖导入顺序 — 已修复

**原文件**: `brain_alpha_ops/brain_api/official_context.py:35-43`

```python
from . import pagination_limits
```

**根因**: 如果 `official.py` 尚未被导入（如从 `official_context.py` 直接导入 `OfficialContextDataMixin`），则 `sys.modules` 中找不到该模块，函数静默回退到 `default` 值。

**已实施方案**: 配合 V5-014 常量统一，移除 `_official_limit()` 和 `sys.modules` 读取逻辑，测试 monkeypatch 改为作用于 `pagination_limits`。

**优先级**: P2 · **状态**: 本轮已修复

---

### V5-016 | P2 | 明文凭据存储 — 已修复

**原文件**: `brain_alpha_ops/brain_api/official.py:72-74`

```python
self.username = username or os.getenv("BRAIN_USERNAME", "")
self.password = password or os.getenv("BRAIN_PASSWORD", "")
self.token = token or os.getenv("BRAIN_TOKEN", "")
```

**影响**: 实例属性可在调试器、`__dict__` 序列化、堆栈跟踪中泄露。虽然 `secure_credentials.py` 中已有 `CredentialBundle` 封装，但 `OfficialBrainAPI` 未使用。

**已实施方案**:
```python
from brain_alpha_ops.secure_credentials import resolve_credentials

class OfficialBrainAPI(...):
    def __init__(self, ...):
        self._credentials = resolve_credentials(
            username=username, password=password, token=token
        )

    @property
    def token(self) -> str:
        return self._credentials.token
```

`username/password/token` 现在是属性访问器，兼容认证和请求逻辑；实例 `__dict__` 不再直接保存这三个明文字段。`CredentialBundle.__repr__()` 也改为 masked 输出，避免调试打印泄露实际值。

**验证**: `tests/test_official_adapter.py::test_official_api_keeps_credentials_out_of_plain_instance_fields` 覆盖实例字段边界和 token rotation；`tests/test_infrastructure_modules.py::TestSecureCredentials::test_credential_bundle_repr_is_masked` 覆盖 bundle repr 脱敏。

**优先级**: P2 · **状态**: 本轮已修复

---

### V5-017/V5-018 | P2 | `validate_run_config` 副作用 + 状态不一致 — 已修复

**文件**: `brain_alpha_ops/config.py:186-196`

```python
resolved = dataset.strip() if isinstance(dataset, str) and dataset.strip() else ""
if not resolved:
    try:
        resolved = resolve_default_dataset_id(...)
    except Exception as exc:
        logger.warning(...)
        errors.append(...)
        resolved = ""          # ← 空字符串
# Only mutate settings if resolution succeeded
if resolved:
    config.ops.settings.dataset = resolved  # ← 副作用
_validate_ops(errors, config.ops)           # ← resolved="" 时仍继续验证
```

**问题**:
1. `config.ops.settings.dataset = resolved` 修改了入参 config（副作用）
2. `resolved=""` 时 dataset 保持原值（可能是空字符串），但验证继续

**已实施方案**:
```python
def prepare_run_config_for_runtime(config: RunConfig) -> RunConfig:
    runtime_config = _copy_run_config(config)
    resolved_dataset = _resolve_dataset_for_validation(runtime_config, errors)
    if resolved_dataset:
        runtime_config.ops.settings.dataset = resolved_dataset
    validate_run_config(runtime_config)
    return runtime_config
```

`validate_run_config(config)` 现在只在临时副本上校验补全后的 dataset，不再写回传入对象；`load_run_config()` 和 `write_run_config()` 使用 `prepare_run_config_for_runtime()` 获取运行时副本。若默认 dataset 解析返回空字符串，会产生 `ConfigValidationError` 并 fail closed。

**验证**: `tests/test_config.py::test_validate_run_config_resolves_dataset_without_mutating_input` 与 `tests/test_config.py::test_validate_run_config_rejects_empty_default_dataset_resolution` 覆盖副作用和空解析场景。

**优先级**: P2 · **状态**: 本轮已修复

---

### V5-019 | P2 | `CredentialRedactionFilter` 位置参数匹配不精确 — 已修复

**文件**: `brain_alpha_ops/secure_credentials.py`

**原问题**: tuple 形式的 `record.args` 只要日志模板提到 `token/password` 等关键词，就会把所有字符串参数替换为 `<REDACTED>`。例如 `path=%s token=%s retry=%s` 会误伤 `path`，同时非字符串 tuple 值里的嵌套敏感字段可能没有结构化脱敏。

**已实施方案**:
1. 为 printf 占位符增加上下文扫描，只标记当前占位符片段里带敏感键的参数位置。
2. 普通字符串参数仅执行 `redact_text()`，避免误伤安全字段。
3. 非字符串参数走 `redact_data()`，让 dict/list/tuple 内部敏感键也被递归处理。

**验证**: `tests/test_infrastructure_modules.py::TestSecureCredentials::test_redaction_filter_tuple_args_redacts_only_sensitive_positions` 覆盖精确位置脱敏；`test_redaction_filter_tuple_args_redacts_nested_values` 覆盖嵌套结构脱敏。

**优先级**: P2 · **状态**: 本轮已修复

---

### V5-025 | P3 | 双前端架构冗余 — CLOSED_CURRENT

**文件/证据**: `README.md`, `docs/REVIEW_GAP_CLOSURE_20260530.md`, `scripts/check_frontend_surface_parity.py`, `scripts/check_react_build_env.py`

**当前决策**:
1. 当前 release surface 继续保持 inline HTML/JS production console。
2. React 保留为 mirror / explicit preview path（React mirror-only），仅在 `launch_web.py --frontend react` 或 `BRAIN_ALPHA_OPS_WEB_FRONTEND=react` 时启用。
3. 不在本轮删除任一前端；未来若要把 React 提升为单一生产面，必须先让 `frontend_surface_parity` 严格模式和 React build/smoke 证据同时通过。

**验证证据**: `docs/REVIEW_GAP_CLOSURE_20260530.md` 已将 `P3-1 Dual frontend unification` 标为 `CLOSED_CURRENT`，并说明 `frontend_surface_parity` 默认进入质量门、React-only operational tabs 已在 `docs/FRONTEND_SURFACE_PARITY_PLAN.json` 中显式接受。`scripts/check_react_build_env.py` 当前返回 `production_surface=inline_html_js` 与 `react_surface=mirror`，用于防止 React mirror 状态被误认为默认生产面。

**优先级**: P3 · **状态**: 本轮已关闭为架构决策

---

## 五、修复计划（3 阶段，总计 ~25h）

### Phase 1: P1 安全与稳定性紧急修复（~5h）

| 顺序 | ID | 任务 | 预计 |
|------|-----|------|------|
| 1 | V5-001 | 保留完整分页，不添加硬上限；已增加无新增唯一 alpha warning-only 观测，后续仅考虑耗时/取消类保护 | 跟踪保留 |
| 2 | V5-009a | 高影响静默异常改为错误传播/结构化警告（dataset解析、redline校验、同步dataset fallback、评分历史写入） | 已完成 |
| 3 | V5-009b | 中低影响静默异常增强日志 + 监控集成（agent job row、类型提示 fallback、SQLite索引、外部行情诊断已完成） | 已完成 |
| 4 | V6-NEW-003 | `_score_history` 内存泄漏修复 + 上限保护 | 已完成 |
| 5 | — | 全量回归测试（`pytest tests/`） | 0.5h |

### Phase 2: P2 稳定性加固（~10h）

| 顺序 | ID | 任务 | 预计 |
|------|-----|------|------|
| 6 | V5-012 | N+1查询优化 | 已完成 |
| 7 | V5-014 | 常量统一 + 移除 sys.modules 依赖 | 已完成 |
| 8 | V5-015 | 配合V5-014修复（同工作量） | 已完成 |
| 9 | V5-016 | `CredentialBundle` 封装凭据替代明文属性 | 已完成 |
| 10 | V5-017 | validate 副作用移出 | 已完成 |
| 11 | V5-018 | dataset 解析失败时终止验证 | 已完成 |
| 12 | V5-019 | RedactionFilter 位置参数脱敏增强 | 已完成 |
| 13 | V5-020 | `_ratio()` 归一化逻辑调整 | 已完成 |
| 14 | V5-021 | `finalJob` 空值保护 | 已完成 |
| 15 | V5-022 | `init()` Promise.all 并发优化 | 已完成 |
| 16 | V5-023 | 全局状态闭包封装 | 已完成 |
| 17 | V5-024 | 分页逻辑去重 | 已完成 |
| 18 | V5-013 | God Object 渐进重构（Phase 1: 组合模式） | 已完成 |
| 19 | — | 全量回归测试 | 0.5h |

### Phase 3: P2 架构 + P3 代码质量（~10h）

| 顺序 | ID | 任务 | 预计 |
|------|-----|------|------|
| 20 | V5-013p2 | God Object 深度重构（Phase 2: 依赖注入） | 已完成 |
| 21 | V5-025 | 前端架构决策 + React 生产化迁移评估 | 已完成 |
| 22 | V5-026 | `random.seed` → `random.Random` 局部化 | 已完成 |
| 23 | V5-027 | 空 field_names 错误处理 | 已完成 |
| 24 | V5-028 | 导入风格统一 | 已完成 |
| 25 | V5-030 | Screen reader announcer 引用缓存 | 已完成 |
| 26 | V5-031 | 进度字段 TypedDict 统一 | 已完成 |
| 27 | V6-NEW-004 | `build_scorecard` 副作用文档化 + 调用者处理 | 已完成 |
| 28 | — | 文档更新 + REVIEW.md 更新 | 0.5h |
| 29 | — | 全量回归测试 + 质量门禁 | 1h |

---

## 六、验证标准

### 6.1 已修复缺陷验证矩阵

| 缺陷 | 当前验证证据 |
|------|--------------|
| V5-001 | `tests/test_official_adapter.py::test_list_user_alphas_warns_on_page_with_no_new_unique_items_without_stopping` (`new_unique_items` / `duplicate_unique_items` / `unique_items` / `stalled_unique_pages`); `tests/test_official_adapter.py::test_list_user_alphas_can_be_cancelled_by_progress_callback_without_page_cap`; `tests/test_web_sync_job.py::test_run_sync_job_service_returns_false_to_cancel_alpha_scan`; `tests/test_web_sync_job.py::test_run_sync_job_service_stops_alpha_scan_on_elapsed_limit`; `tests/test_pipeline.py::test_pipeline_cloud_sync_cancel_does_not_merge_partial_rows`; `tests/test_pipeline.py::test_pipeline_cloud_sync_elapsed_limit_does_not_merge_partial_rows` |
| V5-012 | `tests/test_dynamic_research_components.py::test_template_registry_field_type_matching_is_dataset_specific` |
| V5-013 | `tests/test_official_adapter.py::test_official_api_uses_composed_api_components` |
| V5-014/V5-015 | `tests/test_official_adapter.py::test_list_fields_stops_at_max_pages_limit`; `tests/test_official_adapter.py::test_list_user_alphas_has_no_default_page_limit` |
| V5-016 | `tests/test_official_adapter.py::test_official_api_keeps_credentials_out_of_plain_instance_fields` |
| V5-017/V5-018 | `tests/test_config.py::test_validate_run_config_resolves_dataset_without_mutating_input`; `tests/test_config.py::test_validate_run_config_rejects_empty_default_dataset_resolution` |
| V5-019 | `tests/test_infrastructure_modules.py::TestSecureCredentials::test_redaction_filter_tuple_args_redacts_only_sensitive_positions`; `tests/test_infrastructure_modules.py::TestSecureCredentials::test_redaction_filter_tuple_args_redacts_nested_values` |
| V5-020 | `tests/test_comprehensive_scoring_edge_cases.py::TestExtremeValues::test_ratio_normalizes_values_above_100_as_percentages` |
| V5-021 | `tests/test_web_frontend_v2.py::test_app_submit_selected_candidates_handles_missing_async_job_result` |
| V5-022 | `tests/test_web_frontend_v2.py::test_loading_feedback_runstartup_launches_all_tasks_concurrently` |
| V5-023 | `tests/test_web_frontend_v2.py::test_app_apply_preset_reads_presets_from_app_state`; `tests/test_web_frontend_v2.py::test_spinner_component` |
| V5-024 | `tests/test_official_adapter.py::test_context_collection_methods_share_paginated_context_helper` |
| V5-026/V5-027 | `tests/test_dynamic_research_components.py::test_template_registry_seed_does_not_mutate_global_random_state`; `tests/test_dynamic_research_components.py::test_template_registry_unknown_and_empty_field_cases` |
| V5-030 | `tests/test_web_frontend_v2.py::test_spinner_component` |
| V5-031 | `tests/test_web_progress.py::test_progress_payload_documents_unified_fields` |
| V6-NEW-003 | `tests/test_official_scoring_system.py::test_official_scoring_in_memory_history_is_bounded` |
| V6-NEW-004 | `tests/test_scoring_gate.py::test_build_scorecard_does_not_mutate_candidate_scorecard` |

每个 Phase 完成后需通过以下验证：

1. **安全修复**: `pytest tests/ -k "pagination or credential or redaction"` 全部通过
2. **评分修复**: `pytest tests/ -k scoring` 通过，含缺失键和新门禁测试用例
3. **模板过滤**: `pytest tests/test_dynamic_research_components.py` 通过
4. **前端门禁**: `python scripts/check_frontend_silent_catches.py --json` 0 findings
5. **Python门禁**: `python scripts/check_python_silent_broad_exceptions.py --json` 0 findings
6. **全局回归**: `pytest tests/` 覆盖率 > 80%、ruff/mypy 无错误
7. **CI**: GitHub Actions quality-gate 全部通过

---

## 七、风险登记

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| God Object 重构引入回归 | API调用中断 | Mixin 方法逐一迁移，每次提交单测 |
| `_ratio()` 逻辑调整 | 评分结果变化 | 添加对照测试，记录变化幅度 |
| 静默异常改为传播 | 用户看到新错误 | 增量修复，优先高影响场景 |
| React 替换原生 JS | 功能缺失 | 分段迁移，原生版保留回退 |
| 凭据封装重构 | 认证中断 | `CredentialBundle` 向后兼容原有接口 |

---

## 八、调用链路追踪总结图

```
┌──────────────────────────────────────────────────────────────────┐
│                    BRAIN Alpha Ops 核心调用链                        │
├──────────────────────────────────────────────────────────────────┤
│                                                                    │
│  配置层:                                                            │
│  config.json → load_run_config() → validate_run_config()          │
│      ↓  [V5-017/V5-018 fixed: runtime defaults use copies]       │
│                                                                    │
│  API层:                                                            │
│  OfficialBrainAPI.__init__() [V5-016 fixed: CredentialBundle]     │
│      ↓                                                            │
│  .list_user_alphas() → _cached_paginated_context()                │
│      ↓  [V5-001 no max pages]                                     │
│  .list_fields/datasets/operators [V5-024 pagination helper fixed]│
│                                                                    │
│  研究层:                                                            │
│  AlphaTemplateRegistry.get_for_dataset()                           │
│      ↓  [V5-012 N+1 query fixed]                                 │
│  .instantiate() → random.Random(seed) [V5-026 fixed]             │
│      ↓                                                            │
│  build_scorecard() → return scorecard; caller assigns [V6 fixed] │
│      ↓                                                            │
│  empirical_score() → _ratio() [V5-020 normalization fixed]       │
│      ↓                                                            │
│  evaluate_quality_gate() → hard_gate_blocked                     │
│                                                                    │
│  评分层:                                                            │
│  OfficialScoringSystem.evaluate()                                  │
│      ↓  [V5-005 KeyError fixed] [V5-006 gate logic fixed]        │
│  ._record_history() → _score_history [V6-NEW-003 capped]         │
│                                                                    │
│  安全层:                                                            │
│  CredentialRedactionFilter [V5-008 fixed]                         │
│      ↓  [V5-019 fixed: positional arg matching]                  │
│  LocalSessionManager → secure_cookies [V5-004 fixed]              │
│      ↓  [V5-010 absolute max age exists] [V5-011 CSRF secure]    │
│                                                                    │
│  前端层:                                                            │
│  app.js: init() → serial API calls [V5-022 performance fixed]    │
│      ↓  [V5-023 global mutable state fixed]                       │
│  table.js / result-table.js: setRawHtml() [V5-002 fixed]         │
│      ↓  [V5-021 finalJob null check fixed]                        │
└──────────────────────────────────────────────────────────────────┘
```

---

*报告生成时间: 2026-06-02 03:21*
*分析范围: 291 Python 文件 + 28 JS 前端模块*
*分析方法: 深度调用链路追踪 + 静态代码分析 + 数据流追踪*
*前版报告: docs/DEFECT_ANALYSIS_REPORT_20260602_v5.md*
