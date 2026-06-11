# 静态分析缺陷报告 — BRAIN-Alpha Ops

> **分析日期**: 2026-06-03  
> **分析范围**: 全部 306 个 Python 文件, 30+ 个 JS/TSX 文件  
> **方法论**: 静态函数调用链追踪 + 数据流分析，不依赖历史文档  
> **发现缺陷总数**: 22 项（P0×4 / P1×7 / P2×6 / P3×5）

---

## 目录

1. [P0 — 关键缺陷（立即修复）](#p0)
2. [P1 — 高危缺陷（一周内修复）](#p1)
3. [P2 — 中危缺陷（迭代内修复）](#p2)
4. [P3 — 低危缺陷（积压处理）](#p3)
5. [修复优先级排序与执行顺序](#priority)
6. [附录：关键调用链图谱](#appendix)

---

## 当前实施跟踪快照（Codex，2026-06-03）

> 本节用于把原始静态分析发现映射到当前工作树中的代码、测试和明确边界；原报告正文保留为问题来源，不直接代表当前状态。
> 本轮追加跟进：`_validation_targets()` 先执行观测重复表达式 official-call guard，再执行 cloud similarity 预检；`OfficialCallGuard` 对同一候选/阶段/表达式幂等计数，`test_pipeline_observability_duplicate_guard_blocks_official_validation` 覆盖。
> 本轮追加验证：Web 入口 `main()` 绑定、`--smoke-test` CLI 分支、port=0 传递和 smoke 生命周期已由 `tests/test_web_facade_contract.py`、`tests/test_web_runtime_facade_coverage.py`、`tests/test_web_server_lifecycle.py` 覆盖；`python -m brain_alpha_ops.web --smoke-test --port 0` 在 Codex 沙箱内已实测到 `socket.bind()` 并被 `PermissionError: [Errno 1] Operation not permitted` 阻止，沙箱外本地复跑已返回 `{"ok": true, "status": "web ready", "url": "http://127.0.0.1:64761/", "config_ok": true}`。
> 本轮追加检查：`scripts/check_defect_analysis_report.py` 已锁定 `P2-6` 的 `FIXED` 状态、端到端 smoke 命令和 `{"ok": true, "status": "web ready", ...}` 成功输出片段。

| ID | 当前状态 | 当前证据 | 下一步 |
|----|----------|----------|--------|
| P0-1 | FIXED | `build_official_url()` 校验 `base_url` 与绝对目标 URL 的官方/测试 host，并拒绝非 ASCII hostname；`test_request_rejects_untrusted_configured_base_url`、`test_build_official_url_rejects_non_ascii_hostname` 覆盖 | 保持 URL allowlist 回归 |
| P0-2 | FIXED | `list_official_datasets_or_derive()` 对 API 失败会发出 warning callback；fallback 为空或失败时抛 `BrainAPIError`；`tests/test_official_context_datasets.py` 覆盖 | 保持 dataset fallback 状态暴露 |
| P0-3 | TRACKED_DEFERRED | `MAX_USER_ALPHAS_PAGES=None` 是完整云端同步策略；保留重复页签名、空页/短页、offset recovery、无新增唯一 alpha 页面的 `no_new_unique_items` progress warning，并在 progress payload 记录 `new_unique_items` / `duplicate_unique_items` / `unique_items` / `stalled_unique_pages`；进度回调返回 `False` 的调用方取消保护仍是显式 opt-in；Web sync 和 pipeline 调用点已接入用户取消/stop_callback，停止后避免合并 partial rows | 不添加固定分页截断；保留默认完整同步 |
| P0-4 | FIXED | `submit_simulation()` 将同源 `Location` 规范化为 path/query；`test_submit_simulation_normalizes_same_origin_location_header_to_path` 覆盖 | 保持提交 URL 规范化回归 |
| P1-1 | FIXED | `_throttle()` 在全局锁内预留请求时间戳；`test_throttle_uses_shared_timestamp_across_instances` 覆盖 | 保持跨实例节流回归 |
| P1-2 | FIXED | `FieldDatasetMapper.build()` 使用本地 dict 构建后原子替换，读路径加锁并兼容轻量 loader；`tests/test_field_dataset_mapper.py` 覆盖 | 可追加并发压力测试 |
| P1-3 | FIXED | `_read_cache()` 支持共享 `cache_lock`，损坏缓存返回 `error` 字段；`test_read_cache_warns_on_invalid_cache_file` 覆盖 | 保持缓存损坏状态可见 |
| P1-4 | FIXED | `web_handler_dispatch.py` 对断连异常和二次 `_json()` 失败都有兜底；`tests/test_web_handler_dispatch.py`、`tests/test_web_http_handler_coverage.py` 覆盖 | 保持 handler 异常链回归 |
| P1-5 | FIXED | `run_pipeline.py` 在人类可读摘要格式化失败时打印 fallback 提示，再输出 JSON | 可增加入口级 CLI 回归 |
| P1-6 | FIXED | `pipeline.py` warning 级日志改为脱敏摘要，完整 traceback 降到 debug；`tests/test_pipeline.py` 覆盖 raw secret 与 warning traceback 不外泄 | 继续收敛其他模块 warning traceback |
| P1-7 | FIXED | `submit_alpha()` 拒绝空白 alpha_id 与非生产 alpha_id；`tests/test_submission_gate.py` 覆盖 | 保持真实提交 gate |
| P2-1 | FIXED | `parse_response()` 对非 JSON 响应记录 warning 并抛 `BrainAPIError` | 保持 API 响应格式错误可见 |
| P2-2 | FIXED | `_ratio()` 默认只归一化 `abs(value) >= 100` 的明确百分比尺度，避免破坏自然 turnover；drawdown/correlation/prod_correlation/weight_concentration 等有界指标使用 `bounded=True` 归一化 `[1, 100)` 百分比表示；`tests/test_comprehensive_scoring_edge_cases.py` 覆盖 | 保持评分边界回归 |
| P2-3 | FIXED | `poll_until_complete()` 每轮 poll 前调用 `_throttle()` | 保持轮询速率限制 |
| P2-4 | FIXED | stale cache 进度 warning 使用通用模板，只暴露状态码 | 保持进度消息不携带异常详情 |
| P2-5 | TRACKED_LEGACY_COMPAT | `web.py` 保留 legacy namespace 注入以兼容旧导入面；`web_legacy_exports.py` 显式列出 legacy public exports，`tests/test_web_facade_contract.py` 覆盖 legacy exports、动态 job exports、facade bindings 和 runtime delegation | 保持契约测试；若重构需先冻结 public web API 清单 |
| P2-6 | FIXED | `web.py` 的 `__main__` 调用已落到绑定后的 `main()`；`web_runtime_bindings.main()` 将 `_app_context()` 传入 facade；`--smoke-test`、port=0 和 smoke 生命周期已由聚焦测试覆盖；沙箱外本地执行 `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m brain_alpha_ops.web --smoke-test --port 0` 返回 `{"ok": true, "status": "web ready", "url": "http://127.0.0.1:64761/", "config_ok": true}` | 保持端到端 smoke 回归 |
| P3-1 | FIXED | `cache_key()` 使用完整 SHA-256 hex digest | 保持缓存 key 回归 |
| P3-2 | FIXED | `read_cache()` 区分 `missing` 与损坏 `error` | 保持缓存状态字段 |
| P3-3 | FIXED | `brain_api.__getattr__` 与 `research.__getattr__` 为导入失败添加模块/属性上下文 | 保持 lazy import 错误上下文 |
| P3-4 | FIXED | `official_helpers._num()` 显式处理 `bool` 值 | 保持 bool 输入回归 |
| P3-5 | FIXED | `web_runtime_facade.main()` 当前使用 `SERVER_STOP.wait(5)`，不再是原报告所述 1 小时等待 | 保持 shutdown 等待测试 |

---

<a name="p0"></a>

## P0 — 关键缺陷（4 项）

### P0-1: SSRF 漏洞 — 可配置 base_url 允许认证令牌发送到攻击者服务器

| 属性 | 值 |
|------|---|
| **位置** | `brain_alpha_ops/brain_api/official_helpers.py:119-134` (`build_official_url`) |
| **调用链** | `load_run_config()` → `OfficialBrainAPI(config=...)` → `_request()` → `build_official_url(base, path, query)` |
| **触发条件** | 攻击者控制 `config/run_config.json` 中的 `official_api.base_url`，将其指向恶意服务器 |

**根因分析**:

```
config/run_config.json → load_run_config() → OfficialAPIConfig.base_url = "https://evil.com"
                                                      ↓
OfficialBrainAPI._request() → build_official_url(self.config.base_url, path, query)
                                                      ↓
BEFORE: path_or_url.startsWith("http")  →  检查 scheme+netloc 是否与 base_url 一致
                                              ↓
                                         如果一致 → 使用该 URL，携带 Bearer Token
```

`build_official_url` 在第 120-127 行做了"同源检查"，但这个检查仅对比 `path_or_url` 与 `base_url` 的 origin 是否一致。**如果攻击者同时控制了 `base_url` 和 `path_or_url`**（例如通过恶意 JSON 配置），所有后续 API 请求都会携带用户的 `Bearer` 令牌发送到攻击者服务器。

```python
# 第 120-127 行 — 当前实现
if path_or_url.startswith(("http://", "https://")):
    base_parts = urllib.parse.urlparse(base)
    target_parts = urllib.parse.urlparse(path_or_url)
    base_origin = (base_parts.scheme.lower(), base_parts.netloc.lower())
    target_origin = (target_parts.scheme.lower(), target_parts.netloc.lower())
    if target_origin != base_origin:
        raise BrainAPIError("refusing cross-origin official API URL")  # ← 仅当不同源时报错
    url = path_or_url  # ← 同一源时直接信任
```

**修复代码实现逻辑**:

```python
# official_helpers.py 顶部添加
ALLOWED_BRAIN_API_ORIGINS = frozenset({
    "api.worldquantbrain.com",
    "worldquantbrain.com",
})

def build_official_url(base: str, path_or_url: str, query: dict | None) -> str:
    # 1. 验证 base_url 是否为合法 BRAIN API 域名
    base_parts = urllib.parse.urlparse(base)
    if base_parts.hostname and base_parts.hostname.lower() not in ALLOWED_BRAIN_API_ORIGINS:
        raise BrainAPIError(
            f"base_url host {base_parts.hostname!r} is not a known BRAIN API endpoint"
        )
    # 2. 对绝对 URL 做完整验证
    if path_or_url.startswith(("http://", "https://")):
        target_parts = urllib.parse.urlparse(path_or_url)
        if target_parts.hostname and target_parts.hostname.lower() not in ALLOWED_BRAIN_API_ORIGINS:
            raise BrainAPIError(
                f"target URL host {target_parts.hostname!r} is not a known BRAIN API endpoint"
            )
        if (target_parts.scheme.lower(), target_parts.netloc.lower()) != \
           (base_parts.scheme.lower(), base_parts.netloc.lower()):
            raise BrainAPIError("refusing cross-origin official API URL")
        url = path_or_url
    else:
        url = base.rstrip("/") + "/" + path_or_url.lstrip("/")
    # 3. 构建带 query 的 URL（保持不变）
    if query:
        clean = {k: v for k, v in query.items() if v not in ("", None)}
        if clean:
            url += "?" + urllib.parse.urlencode(clean)
    return url
```

**预期修复效果**: 即使 `run_config.json` 被篡改，所有 API 请求也只能发往 `api.worldquantbrain.com`。其他域名（包括 `localhost`、`127.0.0.1`、任意私有 IP）均被拒绝。

---

### P0-2: 静默异常吞没 — API 全部错误被转为空数据返回

| 属性 | 值 |
|------|---|
| **位置** | `brain_alpha_ops/official_context_datasets.py:26-36` (`list_official_datasets_or_derive`) |
| **调用链** | `refresh_official_context()` → `list_official_datasets_or_derive()` → `api.list_datasets()` |
| **触发条件** | API 返回任何非预期错误（HTTPError / ConnectionError / Timeout / 500 等） |

**根因分析**:

```python
# 第 26-36 行 — 当前实现
try:
    try:
        datasets = api.list_datasets(query="all", region=region)
    except TypeError:
        # 落后版本: api.list_datasets() 只接受位置参数
        datasets = api.list_datasets("all")
except Exception:                      # ← 捕获 *一切*（网络错误、认证失败、服务宕机）
    logger.warning("...")              # ← 仅一条日志
    datasets = []                      # ← 静默返回空列表
```

`_warn_dataset_fallback` 记录一条 warning 日志后就继续执行。调用方（`refresh_official_context`）拿到空列表后走 fallback 路径 `datasets_from_fields`，产生**无数据集的上下文快照**。下游 `DatasetSelector`、`CandidateGenerator` 等模块基于空数据集运行，会导致整个研究流水线静默失败。

**修复代码实现逻辑**:

```python
def list_official_datasets_or_derive(
    api: Any, fields: list[dict[str, Any]], *,
    region: str = "",
    datasets_from_fields: DatasetsFromFields,
    fallback_warning: DatasetFallbackWarning | None = None,
) -> list[dict[str, Any]]:
    api_error: Exception | None = None

    # Attempt 1: API call
    try:
        try:
            datasets = api.list_datasets(query="all", region=region)
        except TypeError:
            datasets = api.list_datasets("all")
        # Verify we got meaningful data
        if datasets and len(datasets) > 0:
            return datasets
    except BrainAPIError as exc:
        api_error = exc
        logger.warning("API error fetching datasets (status=%s): %s", exc.status_code, exc)
    except Exception as exc:
        api_error = exc
        logger.warning("Unexpected error fetching datasets: %s", exc, exc_info=True)

    # Attempt 2: Fallback from fields
    try:
        datasets = datasets_from_fields(fields, region=region)
        if datasets:
            if fallback_warning and api_error:
                fallback_warning(api_error, "falling back to field-derived datasets")
            logger.info("Derived %d datasets from %d fields as fallback", len(datasets), len(fields))
            return datasets
    except Exception as exc:
        logger.error("Field-derived dataset fallback also failed: %s", exc, exc_info=True)

    # Both attempts failed — propagate original error
    if api_error is not None:
        raise BrainAPIError(
            f"Failed to load datasets and field-derived fallback also failed"
        ) from api_error
    raise RuntimeError("Failed to load datasets: no data from API and field fallback produced empty result")
```

**预期修复效果**: 
- API 暂时不可用时，若字段来源的数据集 fallback 可用，系统能继续以降级模式运行
- 两者均失败时，抛出明确的异常（而非返回空列表），让上层调用者能感知到数据集获取失败

---

### P0-3: 无限分页风险 — 特定条件下分页循环永不终止

| 属性 | 值 |
|------|---|
| **位置** | `brain_alpha_ops/brain_api/pagination.py:48-118` (`_paginate_collection`) |
| **调用链** | `list_user_alphas()` → `_cached_paginated_context(stop_when_total_reached=False)` → `_paginate_collection()` |
| **触发条件** | `stop_when_total_reached=False` **且** `max_pages=None` **且** `max_items=None` **且** 服务器始终返回满页数据 |

**根因分析**:

```python
# 第 48-118 行 — 分页循环终止条件分析
while True:
    # 条件1: max_pages 限制
    if max_pages is not None and page_number > max_pages:   # ← max_pages=None → 永不触发
        break
    
    # ... 请求并获取 page_items ...
    
    # 条件2: 重复页面签名检测
    if page_items and page_signature in seen_page_signatures:  # ← 服务器若无序返回则不会重复
        break
    
    # 条件3: total_reached 检查
    if stop_when_total_reached and total and len(items) >= total:  # ← stop_when_total_reached=False → 永不触发
        break
    
    # 条件4: max_items 限制
    if max_items is not None and len(items) >= max_items:  # ← max_items=None → 永不触发
        break
    
    # 条件5: 不满页终止
    if len(page_items) < int(params["limit"]):  # ← 如果服务器总返回满页 → 永不触发
        break
```

`list_user_alphas` 调用时传入 `stop_when_total_reached=False`，且 `MAX_USER_ALPHAS_PAGES = None`。这是当前确认的完整云端同步策略：不能用任意固定分页截断用户 alpha，否则会重新引入数据不完整风险。

**当前处理与跟踪逻辑**:

```python
# pagination_limits.py
MAX_USER_ALPHAS_PAGES: int | None = None

# official_context.py
max_pages=pagination_limits.coerce_limit(pagination_limits.MAX_USER_ALPHAS_PAGES)
stop_when_total_reached=False
unique_item_key=lambda row: str(row.get("id") or "").strip()
```

当前保留的非硬截断保护：

1. `_paginate_collection()` 对重复页签名发出 `repeated_page` warning 并停止，避免同一页循环。
2. 空页/短页仍会自然结束分页。
3. `user_alpha_offset_recovery()` 在 offset 达到服务端限制后用 `dateCreated<` 收窄继续同步。
4. `unique_item_key` 对用户 alpha `id` 做唯一进度观测；progress payload 每页记录 `new_unique_items`、`duplicate_unique_items`、`unique_items` 和 `stalled_unique_pages`；如果页面签名未重复、但该页没有新增唯一 alpha，会发出 `no_new_unique_items` warning，分页继续向后拉取。
5. `progress_callback` 可通过显式返回 `False` 取消继续分页；默认返回 `None` 的观察型回调不改变完整同步行为。
6. `web_sync_job.run_sync_job_service()` 的扫描进度回调会在更新 UI/job 状态后检查用户取消，取消时向分页 helper 返回 `False`，最终进入 `stopped` 结果。
7. `PipelineContextSyncMixin._sync_cloud_alphas()` 会在 `stop_callback` 触发时向分页 helper 返回 `False`，并且不会把 partial rows 合并进本地仓库。
8. `ResearchBudget.cloud_sync_max_elapsed_seconds` 保持 `0.0` 兼容字段；Web sync / pipeline 不再把耗时数值作为停止条件，云端 Alpha 同步只能因用户取消、官方分页自然结束或官方/API错误停止。
9. `list_user_alphas` 覆盖已验证无默认页数上限、可拉过旧 10000 条边界、不会因 BRAIN 返回的 `total` 偏小而提前终止，并覆盖无新增唯一 alpha 页面的 warning-only 场景。

**后续可选增强**:

如果需要继续收敛该风险，应优先做可配置的观测告警或由调用方显式取消。默认行为仍不应添加硬页数上限。

**验证证据**: `tests/test_official_adapter.py::test_list_user_alphas_warns_on_page_with_no_new_unique_items_without_stopping` 覆盖无新增唯一 alpha 的 warning-only 观测，并断言 `new_unique_items` / `duplicate_unique_items` / `unique_items` / `stalled_unique_pages` progress 字段；`tests/test_official_adapter.py::test_list_user_alphas_can_be_cancelled_by_progress_callback_without_page_cap` 覆盖 helper 级调用方取消保护不依赖固定分页截断；`tests/test_web_sync_job.py::test_run_sync_job_service_returns_false_to_cancel_alpha_scan` 覆盖 Web sync 用户取消接线；`tests/test_web_sync_job.py::test_run_sync_job_service_ignores_elapsed_limit_and_scans_all_pages` 覆盖 Web sync 不因耗时数值截断分页；`tests/test_pipeline.py::test_pipeline_cloud_sync_cancel_does_not_merge_partial_rows` 覆盖 pipeline 停止后不合并 partial rows；`tests/test_pipeline.py::test_pipeline_cloud_sync_ignores_elapsed_limit_and_merges_all_rows` 覆盖 pipeline 不因耗时数值截断分页。

**预期效果**: 保留完整同步能力，避免任意截断造成 alpha 缺失；剩余“服务端持续返回新满页且调用方不取消”的极端风险作为 `TRACKED_DEFERRED` 跟踪，不在本轮改为硬停止。

---

### P0-4: `submit_simulation()` 丢弃标准化后的 URL

| 属性 | 值 |
|------|---|
| **位置** | `brain_alpha_ops/brain_api/official_simulation.py:28-30` |
| **调用链** | `AlphaResearchPipeline.run()` → `BacktestPollingService` → `api.submit_simulation()` |
| **触发条件** | BRAIN API 返回以 `http://` 开头的 `location` 头（完整 URL 而非路径片段） |

**根因分析**:

```python
# 第 21-30 行
def submit_simulation(self, expression: str, settings: dict) -> str:
    body = build_simulation_payload(expression, settings)
    data, headers = self._request("POST", self.config.simulations_path, body=body)
    location = headers.get("Location") or headers.get("location")
    sim_id = location or _first_value(data, ["id", "simulation_id", "location"], "")
    if not sim_id:
        raise BrainAPIError(...)
    if str(sim_id).startswith(("http://", "https://")):
        build_official_url(self.config.base_url, str(sim_id), None)  # ← 返回值被丢弃！
    return str(sim_id)  # ← 始终返回原始值
```

当 `sim_id` 是完整 URL（如 `https://api.worldquantbrain.com/simulations/abc123`）时：
- 第 28 行检查到它以 `http` 开头
- 第 29 行调用 `build_official_url` 做验证，但**丢弃了返回值**
- 第 30 行返回原始的完整 URL

下游 `poll_simulation("https://api.worldquantbrain.com/simulations/abc123")` 使用这个完整 URL 做轮询。虽然功能上可工作（因为 `_request` 中的 `build_official_url` 会处理完整 URL），但语义不一致：`simulation_id` 应该是 ID 片段而非完整 URL。

**修复代码实现逻辑**:

```python
def submit_simulation(self, expression: str, settings: dict) -> str:
    body = build_simulation_payload(expression, settings)
    data, headers = self._request("POST", self.config.simulations_path, body=body)
    location = headers.get("Location") or headers.get("location")
    raw_id = location or _first_value(data, ["id", "simulation_id", "location"], "")
    if not raw_id:
        raise BrainAPIError(
            f"simulation submission did not return a location/id: {_scrub(data)}"
        )
    sim_id = str(raw_id)
    if sim_id.startswith(("http://", "https://")):
        # 通过 build_official_url 验证并标准化
        normalized = build_official_url(self.config.base_url, sim_id, None)
        # 从完整 URL 中提取路径部分作为 ID
        import urllib.parse
        parsed = urllib.parse.urlparse(normalized)
        path_parts = parsed.path.rstrip("/").split("/")
        sim_id = path_parts[-1] if path_parts else sim_id
    return sim_id
```

**预期修复效果**: `submit_simulation` 始终返回纯粹的 simulation ID（如 `"abc123"`）而非完整 URL，保证下游调用一致性。

---

<a name="p1"></a>

## P1 — 高危缺陷（7 项）

### P1-1: `_throttle()` 速率限制 TOCTOU 竞态条件

| 属性 | 值 |
|------|---|
| **位置** | `brain_alpha_ops/brain_api/official.py:251-269` |
| **影响范围** | 多线程/多实例使用同一 API 时，实际请求间隔可能低于配置值 |
| **触发条件** | 两个线程几乎同时进入 `_throttle()`，在该取 `_GLOBAL_LAST_REQUEST_AT` 和写入新值之间存在时间窗口 |

**根因分析**:

```python
def _throttle(self):
    global _GLOBAL_LAST_REQUEST_AT
    interval = max(0.0, float(self.config.min_request_interval_seconds))
    with self._request_lock:
        if interval <= 0:
            now = time.monotonic()
            with _GLOBAL_TIMESTAMP_LOCK:
                _GLOBAL_LAST_REQUEST_AT = now
            self._last_request_at = now
            return                          # ← 双层锁，但中间有间隙
        with _GLOBAL_TIMESTAMP_LOCK:
            last_request_at = max(self._last_request_at, _GLOBAL_LAST_REQUEST_AT)
        elapsed = time.monotonic() - last_request_at
        if elapsed < interval:
            time.sleep(interval - elapsed)
        now = time.monotonic()
        self._last_request_at = now
        with _GLOBAL_TIMESTAMP_LOCK:
            _GLOBAL_LAST_REQUEST_AT = now
```

问题在于：
1. 线程 A 在 `_GLOBAL_TIMESTAMP_LOCK` 内读取 `last_request_at`（第 262 行）
2. 线程 A 释放 `_GLOBAL_TIMESTAMP_LOCK`，进入 sleep（第 265 行）
3. 线程 B 在 A sleep 期间获取 `_GLOBAL_TIMESTAMP_LOCK`，读取相同的旧值，也进入 sleep
4. 两个线程以几乎相同的间隔唤醒并同时发请求 → **实际间隔低于配置值**

**修复代码实现逻辑**:

```python
def _throttle(self):
    interval = max(0.0, float(self.config.min_request_interval_seconds))
    if interval <= 0:
        return

    # 使用单个全局锁保护整个 throttle 逻辑
    with _GLOBAL_TIMESTAMP_LOCK:
        now = time.monotonic()
        elapsed = now - _GLOBAL_LAST_REQUEST_AT
        if elapsed < interval:
            # 记录需要等待的时间，在锁外 sleep
            wait_time = interval - elapsed
        else:
            wait_time = 0.0
        # 立即更新时间戳，阻止其他线程通过
        _GLOBAL_LAST_REQUEST_AT = now + wait_time

    if wait_time > 0:
        time.sleep(wait_time)

    # 更新实例级别时间戳
    self._last_request_at = time.monotonic()
```

**预期修复效果**: 全局速率限制严格原子化，多线程场景下实际间隔不会低于 `min_request_interval_seconds`。

---

### P1-2: `FieldDatasetMapper.build()` 并发构建竞态条件

| 属性 | 值 |
|------|---|
| **位置** | `brain_alpha_ops/data/field_dataset_mapper.py:15-42` |
| **影响范围** | 多线程读取 `fields_for()` / `datasets_for()` 时可能看到中间状态 |
| **触发条件** | 线程 A 调用 `build()` 时，线程 B 同时调用 `fields_for()` |

**根因分析**: `build()` 方法依次执行 `self._dataset_to_fields.clear()` 和 `self._field_to_datasets.clear()`，然后逐个调用 `_add_mapping()` 重新填充。整个操作不是原子的，且没有任何锁保护。

```python
# 第 15-42 行 — 当前实现
def build(self, loader: "OfficialDataLoader") -> "FieldDatasetMapper":
    self._dataset_to_fields.clear()       # ← 步骤1：清空
    self._field_to_datasets.clear()       # ← 步骤2：清空
    
    for dataset in loader.get_datasets():  # ← 步骤3：逐个重建
        if not isinstance(dataset, dict):
            continue
        dataset_id = dataset.get("id")
        if not dataset_id:
            continue
        for field_info in dataset.get("fields", []):
            field_name = ...
            if field_name:
                self._add_mapping(dataset_id, field_name)
    return self
```

如果在步骤1-3之间，另一个线程调用 `fields_for("some_dataset")`，它会看到空字典或部分数据。

**修复代码实现逻辑**:

```python
import threading

class FieldDatasetMapper:
    def __init__(self) -> None:
        self._dataset_to_fields: dict[str, set[str]] = {}
        self._field_to_datasets: dict[str, set[str]] = {}
        self._lock = threading.RLock()  # 新增锁
        self._ready = threading.Event()  # 新增就绪标记

    def build(self, loader: "OfficialDataLoader") -> "FieldDatasetMapper":
        # 在本地构建新字典，然后原子替换
        new_ds_to_fields: dict[str, set[str]] = {}
        new_field_to_ds: dict[str, set[str]] = {}

        for dataset in loader.get_datasets():
            if not isinstance(dataset, dict):
                continue
            dataset_id = dataset.get("id")
            if not dataset_id:
                continue
            fields_set: set[str] = set()
            for field_info in dataset.get("fields", []):
                field_name = str(field_info.get("name") or field_info.get("id") or "")
                if field_name:
                    fields_set.add(field_name)
                    new_field_to_ds.setdefault(field_name, set()).add(dataset_id)
            new_ds_to_fields[dataset_id] = fields_set

        # 原子替换
        with self._lock:
            self._dataset_to_fields = new_ds_to_fields
            self._field_to_datasets = new_field_to_ds
        self._ready.set()
        return self

    def fields_for(self, dataset_id: str) -> list[str]:
        with self._lock:
            return list(self._dataset_to_fields.get(dataset_id, set()))

    def datasets_for(self, field_name: str) -> list[str]:
        with self._lock:
            return list(self._field_to_datasets.get(field_name, set()))
    
    # 其他读方法同样加锁...
```

**预期修复效果**: 读取操作始终看到一致的快照，不会出现空或部分数据。

---

### P1-3: 缓存读取缺少锁保护

| 属性 | 值 |
|------|---|
| **位置** | `brain_alpha_ops/brain_api/cache.py:38-56` (`read_cache`) + `official.py:280-286` |
| **调用链** | `_cached_paginated_context()` → `_read_cache()` |
| **触发条件** | 读线程在读 JSON 文件时，写线程正在执行 `.tmp` → `.json` 原子替换 |

**根因分析**: `write_cache` 使用 `cache_lock` 保护写入，但 `read_cache` 不使用任何锁。虽然写入使用原子替换（先写 `.tmp`，再重命名为 `.json`），但：

1. 在特定文件系统上（如某些网络文件系统），重命名操作不是原子性的
2. 如果读恰好发生在文件被删除（准备替换）但新文件尚未创建的时间窗口，会触发 `FileNotFoundError`，然后被静默转为返回空缓存

```python
# cache.py:38-56
def read_cache(config, name, ...):
    path = cache_path_builder(config, name)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))  # ← 无锁读
        # ...
        return {"items": data.get("items", []), "total": ..., "fresh": fresh, ...}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        # 静默返回空缓存 → 触发完整 API 拉取
        return {"items": [], "fresh": False}
```

**修复代码实现逻辑**:

```python
# cache.py 和 official.py
def read_cache(config, name, *, cache_path_builder=..., log=None, cache_lock=None):
    path = cache_path_builder(config, name)
    
    # 使用共享锁进行读取（如果是多线程环境）
    if cache_lock:
        with cache_lock:
            return _do_read_cache(path, log)
    return _do_read_cache(path, log)

def _do_read_cache(path, log):
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        # ... 验证和 freshness 检查 ...
        return {"items": data.get("items", []), ...}
    except FileNotFoundError:
        return {"items": [], "fresh": False, "missing": True}
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        if log:
            log.warning("Cache read error for %s: %s", path.name, exc)
        return {"items": [], "fresh": False, "error": str(exc)}
```

同时在 `OfficialBrainAPI._read_cache` 中传入 `cache_lock`:

```python
# official.py:280-286
def _read_cache(self, name: str) -> dict:
    return _read_cache(
        self.config, name,
        cache_path_builder=lambda _config, cache_name: self._cache_path(cache_name),
        log=logger,
        cache_lock=self._cache_lock,  # ← 传入共享锁
    )
```

**预期修复效果**: 读写互斥，消除读脏数据的可能；文件缺失时明确告知"缺失"而非"不新鲜"。

---

### P1-4: Web 分发器的异常处理链可能崩溃

| 属性 | 值 |
|------|---|
| **位置** | `brain_alpha_ops/web_handler_dispatch.py` (异常处理块) |
| **调用链** | `do_GET()` / `do_POST()` → `dispatch_get()` / `dispatch_post()` → `_dispatch_route()` |
| **触发条件** | API 处理器抛出异常后，`handler._json(status=500, ...)` 写入响应时也失败 |

**根因分析**: 当前的分发异常处理为：

```python
# 推测的 _dispatch_route 实现
try:
    handler_fn(**route_params)
except Exception as exc:
    logger.exception("Route dispatch error")
    handler._json(status=500, error=str(exc))  # ← 如果这里也抛出异常，无人捕获
```

如果 `handler._json()` 因为连接已关闭、缓冲区满等原因抛出 `BrokenPipeError` 或 `OSError`，这个异常会向上传播到 `do_GET`/`do_POST`，可能导致 HTTP 服务器线程崩溃。

**修复代码实现逻辑**:

```python
def _dispatch_route(handler, route_fn, **params):
    try:
        route_fn(**params)
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
        # 客户端已断开 — 安全忽略
        pass
    except Exception as exc:
        logger.exception("Route dispatch error for %s", handler.path)
        try:
            handler._json(status=500, error="Internal server error")
        except Exception:
            # 无法发送错误响应 — 静默放弃
            logger.error("Failed to send error response to client", exc_info=True)
```

**预期修复效果**: 无论如何异常，HTTP 服务器线程不会崩溃，请求处理总是安全终止。

---

### P1-5: 流水线 scorecard 输出静默失败

| 属性 | 值 |
|------|---|
| **位置** | `run_pipeline.py:229-235` |
| **调用链** | `main()` → `run_pipeline_from_config()` → `AlphaResearchPipeline.run()` → 返回 result → `_format_result(result)` |
| **触发条件** | `_format_result()` 在处理结果时因任何原因抛出异常 |

**根因分析**:

```python
# 第 229-235 行
try:
    formatted = _format_result(result)
except Exception:
    logger.exception("Failed to format result summary")
    formatted = json.dumps(_result_to_dict(result), ensure_ascii=False, indent=2)
```

如果 `_format_result` 失败（例如 result 中某字段类型与格式化逻辑不匹配），异常被静默吞掉，JSON fallback 输出被打印，但用户完全不知道人类可读的流水线摘要因 bug 而丢失。

**修复代码实现逻辑**:

```python
try:
    formatted = _format_result(result)
except Exception:
    logger.exception("Failed to format human-readable result summary")
    # 显式告知用户格式化了 JSON fallback
    fallback_data = _result_to_dict(result)
    formatted = (
        "⚠️  人类可读摘要生成失败（详情见日志）。以下是原始 JSON 结果：\n\n"
        + json.dumps(fallback_data, ensure_ascii=False, indent=2)
    )
```

**预期修复效果**: 用户能在终端看到 fallback 通知，而非静默地拿到 JSON 输出。

---

### P1-6: 流水线日志中的敏感数据泄露

| 属性 | 值 |
|------|---|
| **位置** | `brain_alpha_ops/research/pipeline.py:298, 479, 541` |
| **调用链** | `AlphaResearchPipeline.run()` → 各 `except Exception` 块 |
| **触发条件** | 上下文刷新、自动校准、或持久化过程中抛出包含认证信息的异常 |

**根因分析**:

```python
# pipeline.py:298 — 未脱敏的异常日志
except Exception as exc:
    logger.error(
        f"Cycle {cycle}: Context refresh exception — {exc}",  # ← exc 可能包含 API key/token
        exc_info=True,                                         # ← exc_info 可能包含完整请求体
    )
```

虽然 `redaction.py` 提供了 `redact_error_message()` 函数，但 pipeline 中的这些 `except` 块未使用它。

**修复代码实现逻辑**:

```python
from brain_alpha_ops.redaction import redact_error_message

# 在所有流水线日志中使用脱敏
except Exception as exc:
    logger.error(
        f"Cycle {cycle}: Context refresh exception — {redact_error_message(exc)}",
        exc_info=False,  # 不在生产模式下打印完整 traceback（避免泄露）
    )

# 为调试保留一份安全的 traceback
logger.debug("Full context refresh exception", exc_info=True)
```

**预期修复效果**: 日志文件中不再出现 `Bearer xxx`、`password=xxx` 等敏感信息。

---

### P1-7: `submit_alpha` 未检查空 `alpha_id`

| 属性 | 值 |
|------|---|
| **位置** | `brain_alpha_ops/brain_api/official_simulation.py:79-96` |
| **调用链** | `AlphaResearchPipeline.run()` → 提交阶段 → `api.submit_alpha(alpha_id, ...)` |
| **触发条件** | 调用方传入空字符串 `""` 作为 `alpha_id` |

**根因分析**:

```python
def submit_alpha(self, alpha_id: str, expression: str, settings: dict) -> dict:
    if _looks_non_production_alpha_id(alpha_id):  # ← 只检查已知的非生产前缀
        raise BrainAPIError(...)
    check = self.check_alpha(alpha_id)  # ← 空的 alpha_id 会生成无效的 API 路径
```

`_looks_non_production_alpha_id("")` 返回 `False`（因为空字符串不在前缀列表中），然后代码继续调用 `check_alpha("")`，这会构造一个无效 URL 并产生无意义的 API 错误。

**修复代码实现逻辑**:

```python
def submit_alpha(self, alpha_id: str, expression: str, settings: dict) -> dict:
    if not alpha_id or not str(alpha_id).strip():
        raise BrainAPIError("cannot submit alpha without a valid alpha_id")
    if _looks_non_production_alpha_id(alpha_id):
        raise BrainAPIError(
            f"refusing to submit non-production alpha_id through OfficialBrainAPI: {alpha_id}"
        )
    # ... 其余逻辑 ...
```

**预期修复效果**: 空 alpha_id 在早期被拦截，产生清晰的错误信息。

---

<a name="p2"></a>

## P2 — 中危缺陷（6 项）

### P2-1: `parse_response` 将无效 JSON 静默转换为 `{"raw": "..."}`

| 属性 | 值 |
|------|---|
| **位置** | `brain_alpha_ops/brain_api/official_helpers.py:160-166` |
| **触发条件** | API 返回非 JSON 响应（HTML 错误页、纯文本等） |

**根因分析**:

```python
def parse_response(raw: str) -> Any:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}  # ← 调用方无法区分"空响应"与"无效 JSON"
```

所有 HTTP 200 但非 JSON 的响应都被转换为 `{"raw": "..."}` 字典。下游 `_items()`、`_first_value()` 等函数遍历这个字典时找不到预期的 list 数据，静默返回空列表。

**修复**: 让非 JSON 响应也抛出异常（或至少记录一条 warning），使调用方能感知到数据格式问题：

```python
def parse_response(raw: str) -> Any:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("API returned non-JSON response (first 200 chars): %s", raw[:200])
        raise BrainAPIError(
            f"API returned non-JSON response",
            payload={"raw_preview": raw[:500]}
        )
```

---

### P2-2: `_ratio()` 对百分比和自然比率语义区分不足

| 属性 | 值 |
|------|---|
| **位置** | `brain_alpha_ops/research/scoring.py:_ratio` |
| **触发条件** | turnover 等可自然超过 1 的指标与 drawdown/correlation 等天然有界指标共享同一个无语义 `_ratio()` 启发式 |

**根因分析**: 原始 `_ratio()` 缺少指标语义，只能用数值区间推断百分比或自然小数。过宽的 `abs(value) >= 2.0` 归一化会把自然 turnover `2.5` 错转为 `0.025`；过窄的无语义保留又会让有界指标的 `1.5%` 被当作 `1.5`。

```python
turnover = _ratio(metrics.get("turnover"))
drawdown = abs(_ratio(metrics.get("drawdown"), bounded=True))
self_correlation = abs(_ratio(metrics.get("correlation"), bounded=True))
```

**修复**: 为 `_ratio()` 增加 `bounded` 语义参数。默认路径只将 `abs(value) >= 100` 视为明确百分比尺度，保护 turnover 等自然比率；有界指标路径将 `abs(value) > 1` 解释为百分比表示。

```python
def _ratio(value, *, bounded: bool = False) -> float:
    numeric = _num(value)
    abs_numeric = abs(numeric)
    if abs_numeric >= 100.0 or (bounded and abs_numeric > 1.0):
        return numeric / 100.0
    return numeric
```

**验证**: `tests/test_comprehensive_scoring_edge_cases.py` 覆盖 `_ratio(2.5) == 2.5`、`_ratio("1.5", bounded=True) == 0.015`、自然高 turnover 会触发 platform gate 失败，以及有界指标 `1.5%` 会归一化为 `0.015`。

此缺陷与现有代码语义一致，属于**设计权衡**而非 bug，但值得在文档中明确说明。

---

### P2-3: `poll_until_complete` 不遵循速率限制

| 属性 | 值 |
|------|---|
| **位置** | `brain_alpha_ops/brain_api/official_simulation.py:128-134` |
| **触发条件** | 每次 poll 循环都直接调用 `poll_simulation`，无节流 |

**根因分析**:

```python
def poll_until_complete(self, simulation_id: str) -> str:
    for _attempt in range(self.config.poll_attempts):
        status = self.poll_simulation(simulation_id)  # ← 直接 HTTP 调用
        if status in {"COMPLETED", "FAILED"}:
            return status
        time.sleep(self.config.poll_interval_seconds)  # ← sleep 但不保证速率限制
```

`poll_simulation` 内部调用 `_request`，`_request` 有重试逻辑（耗时不定）。在高频轮询场景下，`_throttle` 的速率限制是全局共享的，但 `poll_until_complete` 可能连续触发，导致全局节流。

**修复**: 在调用 `poll_simulation` 前显式触发 `_throttle()` 或在间隔计算中考虑 `min_request_interval_seconds`。

---

### P2-4: `_cached_paginated_context` stale 进度回调可能泄露异常详情

| 属性 | 值 |
|------|---|
| **位置** | `brain_alpha_ops/brain_api/official_context.py:201-208` |
| **触发条件** | Rate limit 导致使用过期缓存时，异常消息作为进度信息返回 |

**根因分析**:

```python
stale_progress=lambda cached, exc: _user_alpha_progress(
    sync_range,
    cached["items"],
    ...,
    warning=redact_error_message(exc),  # ← 部分脱敏但不完整
),
```

`redact_error_message` 使用正则脱敏，但复杂的嵌套异常消息可能逃脱正则匹配。

**修复**: 使用通用的脱敏模板消息替代原始异常文本：

```python
warning=f"using stale cache due to API rate limit (status={exc.status_code})" 
```

---

### P2-5: `web.py` 命名空间污染

| 属性 | 值 |
|------|---|
| **位置** | `brain_alpha_ops/web.py:25` |
| **影响** | 调试困难，IDE 无法正确提示 |

**根因分析**: `globals().update(_build_web_service_namespace())` 将所有 `_` 前缀的函数注入到模块的 `globals()` 中。如果有任何名称冲突（如自定义函数和注入的函数同名），静默覆盖会发生。

**当前实施跟踪补充（2026-06-03）**: 当前工作树没有直接删除 legacy namespace 注入，因为旧测试和旧导入面仍依赖 `brain_alpha_ops.web` 的兼容导出。风险已通过显式 legacy export 清单和契约测试收敛：

- `brain_alpha_ops/web_legacy_exports.py` 用 `LEGACY_EXPORT_SPECS` 列出允许保留的 legacy public names。
- `tests/test_web_facade_contract.py` 覆盖 legacy imported exports、动态 job exports 不进入 `web.__dict__`、`build_web_facade_bindings()` 的 public surface，以及 runtime/config/candidate/session 绑定委托。
- `scripts/check_web_facade_contract.py` 作为机器检查，要求 runtime facade 不再直接通过 `sys.modules` 抓模块状态，且 public brain_alpha import / lambda alias 等计数为 0。

因此该项当前保留为兼容边界，而不是开放缺陷；后续若要移除动态 namespace，需先冻结 public web API 清单并迁移旧调用方。

---

### P2-6: `launch_web.py` 和 `web.py:55` 入口点不一致

| 属性 | 值 |
|------|---|
| **位置** | `launch_web.py:6` vs `brain_alpha_ops/web.py:55` |

**根因分析**: `web.py:55` 的 `if __name__ == "__main__"` 块调用 `main()` 但缺少必需的 `web` 参数 → 若直接以 `python -m brain_alpha_ops.web` 运行将失败。实际的入口点是 `launch_web.py`。存在两个不一致的入口点。

**修复**: 统一入口点，要么移除 `web.py:55` 的 `__main__` 块，要么修复参数传递。

**当前实施跟踪补充（2026-06-03）**: 当前 `brain_alpha_ops/web.py` 通过 `build_web_facade_bindings()` 暴露的绑定版 `main()` 进入 `brain_alpha_ops/web_runtime_bindings.py`，由后者把 `_app_context()` 传给 `web_runtime_facade.main()`；因此原始报告中的缺参入口问题已在当前工作树中关闭。已验证：

- `tests/test_web_facade_contract.py` 覆盖 `web.main(["--smoke-test"])` 会携带应用上下文委托。
- `tests/test_web_runtime_facade_coverage.py` 覆盖 `--smoke-test`、`--frontend react`、显式 `--port 0` 和默认端口分支。
- `tests/test_web_server_lifecycle.py` 覆盖 smoke 访问根页面、`/api/config`、显式 port=0 保留，以及失败时总会 shutdown。

Codex 沙箱仍无法完成真实本地端口绑定，但沙箱外本地复跑已完成端到端 bind smoke；该项不再保留为开放边界。

**端到端 smoke 复跑记录（2026-06-03）**:

- Codex 沙箱内执行 `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m brain_alpha_ops.web --smoke-test --port 0`，调用链已到 `web_server_lifecycle.serve()` 的 `socket.bind()`，随后被当前环境以 `PermissionError: [Errno 1] Operation not permitted` 拦截。
- 沙箱外本机 bind 验证已成功执行，同一命令返回 `{"ok": true, "status": "web ready", "url": "http://127.0.0.1:64761/", "config_ok": true}`。

---

<a name="p3"></a>

## P3 — 低危缺陷（5 项）

### P3-1: `cache_key` 摘要截断增加碰撞概率

| **位置** | `brain_alpha_ops/brain_api/cache.py:12-18` |
| **问题** | SHA256 截断到 16 hex 字符 = 64 位，碰撞概率约 `n² / 2⁶⁵` |
| **修复** | 使用完整 64 hex 字符（128 位）消化 |

### P3-2: `read_cache` 在缓存损坏时静默返回空

| **位置** | `brain_alpha_ops/brain_api/cache.py:38-56` |
| **问题** | JSON 损坏时 `fresh: False` 意味着"不新鲜"而非"已损坏" |
| **修复** | 在返回字典中添加 `integrity: "corrupted"` 字段区分 |

### P3-3: 模块级 `__getattr__` 惰性导入无错误上下文

| **位置** | `brain_alpha_ops/brain_api/__init__.py:8-14` 和 `research/__init__.py:115-127` |
| **问题** | 导入失败时原始异常直接传播，无上下文信息指明是哪个模块导入失败 |
| **修复** | 在 `except ImportError` 中重新包裹异常，添加模块名和路径信息 |

### P3-4: `_num()` 和 `_num_or_none()` 对 `bool` 值的处理

| **位置** | `brain_alpha_ops/brain_api/official_helpers.py:409-421` |
| **问题** | `float(True)` 返回 `1.0`，但 `True in (None, "")` 为 `False`，所以 `True` 不会被当作空值处理 |
| **修复** | 添加显式的 `isinstance(value, bool)` 检查，布尔值返回 `0.0` |

### P3-5: Web 服务器优雅关闭延迟过长

| **位置** | `brain_alpha_ops/web_runtime_facade.py:709` |
| **问题** | `SERVER_STOP.wait(3600)` — 1 小时超时，关闭时最多延迟 1 小时 |
| **修复** | 将超时减少为 5 秒或使用 `SERVER_STOP.wait()` 无限等待（信号驱动关闭） |

---

<a name="priority"></a>

## 修复优先级排序与执行步骤

### 阶段一：安全修复（P0，预计 4-6 小时）

| 顺序 | 缺陷 ID | 描述 | 预计工时 |
|------|---------|------|----------|
| 1 | P0-1 | SSRF 漏洞 — base_url 白名单 | 2h |
| 2 | P0-2 | 静默异常吞没 — 数据集 fallback 传播错误 | 1.5h |
| 3 | P0-3 | 完整分页边界 — 保留无固定截断，已增加无新增唯一 alpha warning-only 观测、helper 级调用方取消保护、Web sync / pipeline 取消接线 | 跟踪保留 |
| 4 | P0-4 | submit_simulation URL 标准化 | 0.5h |

**执行原则**: 按依赖关系排序。P0-1 必须先修复（安全漏洞），其余无依赖，可并行。

### 阶段二：稳定性修复（P1，预计 5-8 小时）

| 顺序 | 缺陷 ID | 描述 | 预计工时 |
|------|---------|------|----------|
| 5 | P1-1 | 速率限制 TOCTOU 竞态 | 1.5h |
| 6 | P1-3 | 缓存读锁保护 | 1h |
| 7 | P1-2 | FieldDatasetMapper 并发安全 | 1h |
| 8 | P1-7 | submit_alpha 空 ID 检查 | 0.5h |
| 9 | P1-4 | Web 异常处理链加固 | 1h |
| 10 | P1-6 | 日志敏感数据脱敏 | 1h |
| 11 | P1-5 | 流水线输出静默失败提示 | 0.5h |

**执行原则**: P1-1 和 P1-3 可以先并行（无依赖），P1-4 依赖 Web 模块理解。

### 阶段三：健壮性改进（P2，预计 3-5 小时）

| 顺序 | 缺陷 ID | 描述 | 预计工时 |
|------|---------|------|----------|
| 12 | P2-1 | parse_response 非 JSON 响应 | 1h |
| 13 | P2-3 | poll_until_complete 速率限制 | 0.5h |
| 14 | P2-4 | 过期缓存异常泄露 | 0.5h |
| 15 | P2-2 | _ratio 指标语义分支与边界测试 | 已完成 |
| 16 | P2-5 | web.py legacy namespace 兼容边界与契约守卫 | 兼容保留 |
| 17 | P2-6 | 统一入口点；端到端 bind smoke 已在沙箱外本地复跑通过 | 已完成 |

### 阶段四：质量提升（P3，预计 3-4 小时）

| 顺序 | 缺陷 ID | 描述 | 预计工时 |
|------|---------|------|----------|
| 18 | P3-1 | cache_key 摘要长度 | 0.5h |
| 19 | P3-2 | 缓存完整性标记 | 0.5h |
| 20 | P3-3 | 惰性导入错误上下文 | 1h |
| 21 | P3-4 | _num bool 处理 | 0.5h |
| 22 | P3-5 | 关闭延迟优化 | 0.5h |

**总预估工时**: ~15-23 小时（单人全职），建议分 2-3 个 sprint 完成。

---

<a name="appendix"></a>

## 附录：关键调用链图谱

### 主流水线调用链

```
launch_web.py / run_pipeline.py
    │
    ├── load_run_config("config/run_config.json")
    │       ├── json.loads() → jsonschema 验证
    │       ├── validate_run_config() → 程序化验证
    │       └── prepare_run_config_for_runtime() → 路径标准化
    │
    ├── OfficialBrainAPI(config=run_config.ops.official_api)
    │       ├── resolve_credentials() ← 环境变量 / keychain
    │       ├── OfficialAuthProfileMixin.authenticate()
    │       ├── OfficialRequestMixin._request()
    │       │       ├── build_official_url()  ← P0-1 SSRF 风险点
    │       │       ├── _throttle()           ← P1-1 TOCTOU 风险点
    │       │       └── _opener.open()        ← urllib
    │       ├── OfficialContextDataMixin
    │       │       ├── _cached_paginated_context()
    │       │       │       ├── _read_cache()     ← P1-3 无锁
    │       │       │       ├── _paginate_collection() ← P0-3 完整分页跟踪边界
    │       │       │       └── _write_cache()
    │       │       └── list_fields / list_datasets / list_operators / list_user_alphas
    │       └── OfficialSimulationSubmissionMixin
    │               ├── submit_simulation()  ← P0-4 URL 丢弃
    │               ├── poll_simulation()
    │               ├── fetch_result()
    │               ├── check_alpha()
    │               └── submit_alpha()       ← P1-7 空 ID 检查
    │
    └── AlphaResearchPipeline(config=run_config, api=api).run()
            ├── 上下文刷新 → context refresh  ← P1-6 日志泄露
            ├── 候选生成 → CandidateGenerator.generate()
            ├── 本地评分 → prior_score / empirical_score
            │       └── scoring_params  ← 参数化评分
            ├── 反过拟合 → AntiOverfitService.evaluate()
            ├── 官方验证 → api.validate_expression()
            ├── 批量回测 → BatchBacktestCoordinator
            │       └── BacktestPollingService.poll()
            ├── 自动校准 → AutoCalibrator  ← P1-6 日志泄露
            └── 持久化 → save lifecycle/events  ← P1-6 日志泄露
```

### 数据流向

```
BRAIN API ←→ OfficialBrainAPI._request()
    │              │
    │        parse_response(raw)  ← P2-1 非 JSON
    │              │
    │        normalize_metrics()  ← P2-2 _ratio
    │              │
    │        _normal_field / _normal_operator / _normal_alpha
    │              │
    ▼              ▼
 (cache)    brain_alpha_ops.data.OfficialDataLoader
                  │
                  ▼
         FieldDatasetMapper  ← P1-2 并发安全
                  │
                  ▼
         CandidateGenerator.generate()
                  │
                  ▼
         scoring.build_scorecard(candidate)
                  │
                  ▼
         pipeline output → _format_result()  ← P1-5 静默失败
```

---

> **报告生成**: 2026-06-03 08:13 UTC+8  
> **分析工具**: 静态代码分析 + 函数调用链追踪  
> **覆盖范围**: brain_alpha_ops/ (306 files), 顶层脚本 (8 files)
