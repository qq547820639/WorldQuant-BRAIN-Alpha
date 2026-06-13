# BRAIN Alpha Ops — 全面深度静态分析报告（v2）

> 范围：`/Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha/brain_alpha_ops/` 全量源码
> 方法：自底向上读取关键文件 + 多 Agent 并行深度分析（brain_api、agent/CLI/tasks、web 服务、research 流水线 4 个角度） + 局部二次验证
> 体量：约 296 个 `.py` 文件 / 30,279 行根级 + 33,340 行 `research/` + 21,597 行 `web_*.py` + 3 万行 `tests/`
> 报告长度：1000+ 行

---

## 0. TL;DR — 关键发现清单

按严重度排序（从 P0 到 P3）：

| # | 严重度 | 主题 | 简述 |
|---|--------|------|------|
| 1 | **P0 — 真实 bug（latent）** | `web_http_handler.py:94-112` `_send_json` 双重 `end_headers` | 工厂创建的 Handler 类里，第一次 `end_headers()` 后又调 `send_header`×3 + `end_headers()` 一次。当前生产路径走的是内联实现所以潜伏着。 |
| 2 | **P0 — 真实安全弱点** | Web 提交"双重防线"实际只一道 | `web/__init__.py:341-357` + `web_handler_dispatch.py:759-768` 都直接返回 `REAL_SUBMIT_DISABLED_WEB_FLOW` 阻断，没有任何"不可移除常量"封禁；改两处之一即可重开真实提交 |
| 3 | **P1 — 安全特性未生效** | 当前生产 Handler 不发 CSP | `web/__init__.py:631` 内联实现的 `Handler` 没有走 `web_http_handler.py:270-277` 的 `_send_security_headers` 路径，文档承诺的 CSP 在生产上是死的 |
| 4 | **P1 — 资源泄漏** | `daemon=False` 线程 + 无 `join()` | `_run_generate_candidates_job` 启动线程用 `daemon=False`；`web_cli.py:serve()` 没 `join()`，进程退出时可能留 zombie |
| 5 | **P1 — God module** | `hypothesis_driven_generator.py` 1325 行 | 4 个 selector 类同文件 + 1300+ 行——任何修改风险扩散 |
| 6 | **P1 — God module** | `local_backtest_engine.py` 1148 行 | 本地回测引擎+多业务混入 |
| 7 | **P1 — 抽象冗余** | `web_runtime_facade.py` 781 行构造 80+ 字段 dataclass | 但生产路径走的是 `web/__init__.py:556-624` 的内联 `dispatch_get/post`；`web_handler_dispatch` + facade 在生产路径上是"未来路径" |
| 8 | **P1 — God module** | `web_handler_dispatch.py` 1094 行 | 路由分发 8 个 import、80+ 字段绑定、fallback 到旧 `web.dispatch_post` |
| 9 | **P2 — 抽象泄漏** | `web/__init__.py` 是 821 行的胶水层 | 直接调 9 个 `_real_*` 业务函数（`run`/`check`/`submit`/`generate`/`score`/`connection`/`attribution`/`stop`/`session`）+ 70+ 个 `globals().update()` 的 facade 注入 |
| 10 | **P2 — 状态机散落** | 4 套不同状态分类共存 | `web_state_contract.classify_job_status` / `web_get_handlers._job_payload` / `tasks.ACTIVE_STATUSES` / `research/contracts.ACTIVE_BACKTEST_STATUSES` — 漂移风险 |
| 11 | **P2 — 退避策略** | 线性退避 + 全局 `_GLOBAL_LAST_REQUEST_AT` 模块级全局 | `brain_api/official_request.py` 退避是 `base * (attempt+1)` 而非指数；全局共享时间戳跨实例 |
| 12 | **P2 — 死代码** | `OfficialExpressionValidationMixin` 未挂载 | `brain_api/official.py` 实际只挂 4 个 mixin，validation 走独立 `OfficialExpressionValidator` |
| 13 | **P2 — 重复** | 重复页签名/瞬态重试常量在 3 处复制 | `_USER_ALPHA_TRANSIENT_*` 在 `official_alphas.py` / `official_context.py` / `official_helpers.py` 三处字符级重复 |
| 14 | **P3 — 命名不一致** | `submission_preflight_error` 既有旧名 `submission_preflight_error_message` 又有别名 | `web_submission_safety.py:99` |
| 15 | **P3 — 并发策略不一致** | `parallel_backtest.py` 真正多线程；`batch_backtest_coordinator.py` 同步纯函数 | 同一概念（"并行回测"）两个不同实现 |
| 16 | **P3 — KnowledgeBase 写无锁** | `knowledge_base.py` 用 `data/knowledge_base/{rules,findings,failures}/*.json` | `Repository` 有文件锁，`KnowledgeBase` 没有 |
| 17 | **P3 — SQLite 启动全量重建** | `expression_sqlite_index.py` 启动时 `DELETE + INSERT` | 每次冷启重建全部索引，无 WAL/timeout |
| 18 | **P3 — LLM 无 quota** | `llm_review.py` 没有 rate-limit / token quota | 失败可能快速耗尽 token |
| 19 | **P3 — 协议不强制** | `shared/contracts.py` 5 个 `@runtime_checkable` Protocol | Duck typing 而非 ABC，IDE 仍支持但运行时无 enforce |
| 20 | **P3 — 反射破坏类型** | `bind_runtime_state_properties` 反射属性赋值 | pipeline_state.py 中动态 setattr 破坏 mypy/IDE |

---

## 1. 项目全貌

### 1.1 顶层结构

```
brain_alpha_ops/  (118 root .py + 10 subpackages)
├── agent_*.py × 6           # Agent 工具门面（MCP/web/LLM 共享）
├── mcp_server.py            # JSON-RPC 2.0 stdio 适配器
├── web_cli.py               # CLI 入口（serve / shutdown / smoke）
├── runner.py                # 28 行：api_from_run_config + run_pipeline_from_config
├── tasks.py / task_executor.py / adaptive_executor.py / stall_monitor.py
│                              # JobStore / 自适应执行 / Stall 监控
├── web_*.py × 90+           # 全部 web 后端门面，拆为 facade/bindings/runtime
├── web/                     # 真正的 web 入口 (__init__.py 821 行)
│   ├── handlers/{phase,sync}.py
│   ├── middleware/ (空)
│   ├── react_app/           # 前端 Vite + React + Tailwind
│   └── ws.py                # WebSocket pub/sub（ADR-004 引入，未启用）
├── scoring/                 # 9 模块评分核心（zero-deviation 对齐 BRAIN）
├── compliance/              # 9 模块六条技术红线
├── domains/                 # 5 个 bounded context 薄 re-export（< 6 行/文件）
├── shared/contracts.py      # 5 个 @runtime_checkable Protocol
├── ux/                      # guided pipeline + i18n
├── brain_api/               # 19 模块官方 API 客户端 + canonical 契约
├── research/                # 106 模块（含多个 god module）
├── examples/                # 1 个 strategy plugin 范本
└── 各类 config_*/jsonl/redaction/errors/runtime_constants/parameter_audit
```

### 1.2 量化指标

| 维度 | 数据 |
|------|------|
| Python 源文件 | 296 个 |
| `research/` 行数 | 33,340 |
| 根级 `web_*.py` 行数 | 21,597 |
| 总行数（含根级） | 30,279（仅根级） |
| 测试文件 | 209 个 `tests/*.py` + 40 个 scripts |
| 三方依赖 | 3 个：`pyyaml>=6` / `requests>=2.32` / `jsonschema>=4.20` |
| 前端框架 | React 18 + Vite + Tailwind |
| Web 服务器 | stdlib `http.server.ThreadingHTTPSServer` + SSE |
| 入口脚本 | `launch_web.py`（11 行）/ `build_prod.py` / `_status.py` / `web_cli.py` |

### 1.3 依赖策略

- **零三方 HTTP 客户端**：`urllib` + `http.cookiejar` + `urllib.error`（`brain_api/official.py`）
- **零三方 LLM SDK**：`urllib` 调 `https://api.openai.com/...`（`research/llm_review.py`）
- **零后端 DB**：JSONL append-only + SQLite 索引加速
- **零 ORM**：`Repository` + 文件锁（`threading.RLock`） + `RepositoryDefaults.LOCK_STALE_SECONDS=120`

---

## 2. 架构图（C4 Model — L2 容器视图）

```
┌─────────────────────────────────────────────────────────────────┐
│                         用户 (单用户)                              │
│            浏览器(React SPA)  +  终端 CLI                          │
└──────────────┬──────────────────────────────────┬─────────────────┘
               │ HTTP+SSE (localhost:8765)         │ MCP stdio
               ▼                                   ▼
┌──────────────────────────────┐    ┌──────────────────────────────────┐
│  web/  HTTP Server (stdlib)  │    │  mcp_server.py  (JSON-RPC 2.0)    │
│  web_http_handler.BaseHTTP   │    │  protocolVersion="2024-11-05"     │
│  + web_handler_dispatch      │    └──────────────┬───────────────────┘
└──────────────┬───────────────┘                   │
               │                                   │
               ▼                                   ▼
┌──────────────────────────────────────────────────────────────────┐
│  agent_tools.BrainAlphaToolbox   (26 工具 / 7 live handler)       │
│  + agent_tool_registry.ToolRegistry  (27 注册 + 3 别名)              │
└──────────────┬──────────────────────────────────┬─────────────────┘
               │                                  │
               ▼                                  ▼
┌──────────────────────────────┐    ┌──────────────────────────────────┐
│  brain_api/  官方 HTTP 客户端  │    │  research/  研发流水线 106 模块    │
│  OfficialBrainAPI + 4 mixin  │    │  pipeline.py  (AlphaResearchPipeline)│
│  Protocol: BrainAPI           │    │  + 10 个 Pipeline*Mixin           │
└──────────────┬───────────────┘    └──────────────┬─────────────────┘
               │                                  │
               ▼                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│  urllib  →  https://api.worldquantbrain.com                       │
│  urllib  →  https://api.openai.com (LLM)                          │
└──────────────────────────────────────────────────────────────────┘

横切关注点（cross-cutting）：
  compliance/   6 条技术红线（redline_verifier）
  scoring/      评分（zero-deviation 对齐 BRAIN 输出）
  shared/       5 个 Protocol（PhaseStateProvider / ProgressReporter / CloudCache / JobStore / EventPublisher）
  domains/      5 个 bounded context 薄 re-export
  ux/           guided_pipeline 10 阶段 + 中文 i18n
  observability / error_knowledge / parameter_audit / redaction
```

---

## 3. 子系统深度分析

### 3.1 `brain_api/` — 官方 HTTP 客户端层（19 文件 / 4,206 行）

#### 3.1.1 架构模式

- **Protocol/外观分离**：`base.py:BrainAPI(Protocol)` 是契约；`official.py:OfficialBrainAPI` 是唯一 concrete。
- **Mixin 切片**：4 个 mixin（auth / context-data / request / simulation）通过 `_BoundOfficialAPIComponent.__getattr__` 代理。
- **零三方 HTTP**：`urllib.request` + `http.cookiejar` + `urllib.error`。
- **缓存**：`cache.py` 磁盘 JSON + SHA-256 键，**非 LRU**，**单一全局 TTL**。
- **Pagination**：单一工具函数 `_paginate_collection` + 重复页签名检测 + 唯一项去重。
- **Rate limit**：`OfficialRequestMixin` 处理 429/5xx，`_throttle()` 防过密；`rate_limit_policy.py` 是静态审计器。

#### 3.1.2 关键签名

```python
class BrainAPIError(RuntimeError):
    def __init__(self, message, *, status_code=None, payload=None, retry_after=None)

class OfficialBrainAPI:
    def authenticate(self) -> dict
    def get_user_profile(self) -> dict
    def list_fields(self, query="all", region="", dataset="", progress_callback=None) -> list[dict]
    def list_datasets / list_operators / list_data_categories
    def search_datasets_limited / search_fields_limited / discover_*
    def locate_dataset / locate_field / locate_alpha
    def filter_alphas_limited / filter_alphas / query_alphas
    def list_user_alphas(self, sync_range, progress_callback, *, force_refresh=False) -> list[dict]
    def submit_simulation / poll_simulation / fetch_result
    def concurrent_simulate / concurrent_check
    def check_alpha / submit_alpha / check_prod_correlation
    def poll_until_complete(self, simulation_id) -> str
    def set_market_scope(self, settings) -> None
    def _throttle / _open / _cache_key / _cache_path / _read_cache / _write_cache
```

#### 3.1.3 错误处理模型

- 唯一异常类 `BrainAPIError`，无子类，靠 `status_code` 区分。
- HTTP 错误：统一捕获 → `BrainAPIError(f"HTTP {exc.code}: ...", status_code=...)`。
- 网络错误：包装为 `BrainAPIError("network error: ...")`。
- **Soft failure**：`get_user_profile` 失败时返回 `{"error", "tier": "unknown"}`；`check_prod_correlation` 返回 `{"status": "error", "warning"}`；`concurrent_*` worker 内部 try/except 转 `{"ok": False, "error"}`。
- **Stale 缓存回退**：`OfficialContextDataMixin._cached_paginated_context` 在 429 时若 `allow_stale_context_on_rate_limit=True` 且缓存非空则返回旧值。
- **Redaction**：`scrub` = `redact_data`，错误信息走 `redact_error_message`。
- **URL 白名单**：`build_official_url` 拒绝非 `api.worldquantbrain.com`、非 HTTPS、跨 origin。
- **重复页签名**：SHA-256 哈希当前页关键字段，重复即停。
- **唯一项去重**：`unique_item_key` + `seen_item_keys` 跟踪。

#### 3.1.4 缓存策略

- **类型**：磁盘 JSON + SHA-256 文件名；**非 LRU**；**无内存 LRU**；**无显式失效**（仅 TTL）。
- **键**：`json.dumps({"kind", "params"}, sort_keys=True)` → SHA-256 → `{kind}_{digest}.json`。
- **TTL**：单一 `config.context_cache_ttl_seconds`（不是 per-endpoint）。
- **写**：原子写（`tmp = path.with_name(".{name}.{pid}.{tid}.tmp")` → `replace`），全程持 `cache_lock`。
- **缓存覆盖**：`fields` / `datasets` / `operators` / `user_alphas`（`force_refresh=True` bypass）。

#### 3.1.5 重试与速率限制

- **运行时**：
  - `OfficialBrainAPI._throttle()`：进程级 `RLock`，`min_request_interval` 单点抢占；锁内预留时间戳防 TOCTOU。
  - **跨实例**：模块级 `_GLOBAL_LAST_REQUEST_AT + _GLOBAL_TIMESTAMP_LOCK`。
  - **HTTP 重试**：`OfficialRequestMixin._request` 中 `attempts = rate_limit_retry_attempts + 1`。
  - **可重试状态**：`{408, 429, 500, 502, 503, 504}`。
  - **退避**：**线性** `base_seconds * (attempt + 1)`，或 `Retry-After` 头覆盖。
  - **特殊豁免**：`CONCURRENT_SIMULATION_LIMIT_EXCEEDED` 字符串检测到时不重试。
  - **401 bearer 模式**：清空 token 切到 cookie/basic。
  - **401/403**：若 `auth_refresh_available` 且 `username+password` 存在，尝试 `self.authenticate()` 一次再重试。
- **静态审计**（`rate_limit_policy.py`）：
  - `OFFICIAL_RATE_LIMITS` 字典常量：`max_concurrent_simulations_regular.max=3`（pre-consultant=5, consultant=10）/ `min_retry_pause_seconds.min=60` / `rate_limit_backoff_initial.min=60`。
  - `validate_rate_limit_policy(budget, api_config)` 纯静态检查，不执行 HTTP。

#### 3.1.6 关键流程

- **认证**：`authenticate()` 先看是否已有 token；无则 `POST /authentication` 带 Basic auth；响应取 `token/access_token`；检查 cookie 设置 `_prefer_cookie_auth`；401 抛错，400 才尝试下一方法。
- **元数据加载**：`list_*` 构造 `_market_context_params`（含 `instrumentType/region/delay/universe/search`），`params["limit"]=50`；走 `_cached_paginated_context` 缓存+分页+stale 回退。
- **Simulation**：`submit_simulation` → `POST /simulations` → 取 `Location` 头抽 `simulation_id`；`poll_simulation` 一次 `_poll_simulation_once`；`poll_until_complete` 循环 `poll_attempts` 次，每次 `_throttle()` + sleep。
- **Alpha 提交**：`submit_alpha` 强制 `bodyless=True`（否则运行时异常），先 `check_alpha` 必须 `PASSED&complete=True`，再 `POST /alphas/{id}/submit`（无 body），用 `_check_result_from_response` 二次校验。
- **用户 Alpha 同步**：`list_user_alphas` 走 `_cached_paginated_context`；处理两类瞬态：① offset 越界 400 → 设 `dateCreated<` 跳回 `offset=0`；② 网络瞬态（`{408,500,502,503,504}`/`URLError`/`RemoteDisconnected`/`IncompleteRead`/`TimeoutError` 或字符串含 `urlopen error/ssl/eof/timed out/connection reset`）→ 同页重试 3 次，每次 sleep 最多 5s。

#### 3.1.7 P0/P1/P2 风险与改进

- **P2 — 死代码**：`OfficialExpressionValidationMixin` 未挂载（`official.py` 实际只挂 4 个 mixin）。
- **P2 — 重复**：`_USER_ALPHA_TRANSIENT_*` 常量在 `official_alphas.py:40-50` + `official_context.py:43-53` + `official_helpers.py` 三处字符级重复，应上提 `user_alpha_transient.py`。
- **P2 — 重复分页**：`_collect_limited_search_pages`（`official_context.py`）与 `_paginate_collection`（`pagination.py`）两套分页循环语义相同但实现独立；`search_*` 没走 `_cached_paginated_context` 导致不写缓存、不享受 429 stale 回退。
- **P2 — 黑名单硬编码**：`looks_non_production_alpha_id` 写死 `mock_/demo_/test_/fake_/sample_/stub_/...` 长串。
- **P2 — 退避线性**：`retry_delay = base * (attempt+1)`，应改 `base * 2^attempt * (0.5 + random()/2)`（指数 + jitter）。
- **P2 — 全局变量污染**：`_GLOBAL_LAST_REQUEST_AT` 跨实例共享时间戳做"全局节流"，没有 lazy reset。
- **P2 — 缓存 TTL 单一**：`context_cache_ttl_seconds` 同时覆盖 `fields`（几乎不变）/ `operators`（几乎不变）/ `user_alphas`（几分钟过期）。
- **P2 — Pagination limits = None**：完全依赖重复页签名+短页停止+`progress_callback` 主动 `False` 取消；若 BRAIN 一直返回满页且无 total 字段，循环会一直跑。
- **P2 — `_throttle` 是 best-effort**：无 token bucket；BRAIN 真对短窗 N>5 限流时持续 429 直至触发 `allow_stale`。
- **P2 — `submit_alpha` bodyless 强制**：用运行时异常而非类型系统拒绝 `bodyless=False`。
- **P2 — Stale 默认与生产建议冲突**：`allow_stale_context_on_rate_limit` 默认 `True`，但 `rate_limit_policy.py` 审计时建议 production 设为 `false`。

---

### 3.2 `agent_*.py` — Agent 工具门面（6 文件 / 1,766 行）

#### 3.2.1 双层解耦：Registry（描述）vs Toolbox（行为）

| 文件 | 行 | 角色 |
|------|----|------|
| `agent_tools.py` | 525 | **主门面** — `BrainAlphaToolbox` + 26 handler 字典 |
| `agent_tool_registry.py` | 419 | 纯元数据 — `ToolDefinition` + `ToolRegistry` + 27 注册 + 3 别名 |
| `agent_live_tools.py` | 261 | `AgentLiveToolsMixin` — 7 个真正触碰 BRAIN API 的 handler |
| `agent_research_tools.py` | 340 | 共享 helper（缓存/反过拟合/assistant 等无副作用工具） |
| `agent_guidance_tools.py` | 211 | 生成器偏好合并（top_operators/preferred_windows） |
| `agent_tool_errors.py` | 10 | `tool_error(exc, code, **ctx)` 薄包装 |

- **`agent_tool_registry.py`** 纯元数据，0 业务逻辑：
  - `ToolDefinition` 是 `@dataclass(frozen=True)`，字段：`name, description, input_schema, live_api, destructive, alias_for, category, chain_stage`。
  - `ToolRegistry` 用 `_tools: dict[str, ToolDefinition]` + `_aliases: dict[str, str]`。
  - `build_default_tool_registry()` 注册 27 个工具 + 3 个别名（`score_factor→score_candidate` / `run_backtest→run_single_backtest` / `run_batch_backtest→run_parallel_backtest`），模拟 QuantGPT 风格。
  - 公开 API：`default_tool_registry()` / `tool_definitions()` / `resolve_tool_name(name)` / `tool_aliases()`。
  - 模块级单例：`_DEFAULT_TOOL_REGISTRY`（懒加载）。

- **`agent_tools.py`** 行为层：
  - `class BrainAlphaToolbox(AgentLiveToolsMixin)` — 单一继承获取 live 行为，再注入研究 helper。
  - `_handlers: dict[str, Callable]` 把 26 个工具名映射到具体方法。
  - 公开方法：`list_tools()`（合并 registry + metadata）/ `call(name, arguments)`（解析别名 → 调度 → 异常映射）。

#### 3.2.2 `AgentLiveToolsMixin` 三层安全护栏

- **入口 1 — `_live_api_blocked()`**：要求 `allow_live_api=True` AND `confirm_live_api=True`，任一缺失即返回 `user_error_payload(..., error_code="LIVE_API_BLOCKED")`。
- **入口 2 — 配额**：`MAX_BATCH_SIMULATIONS=10` / `MAX_BATCH_SIMULATION_WORKERS=3` / `MAX_SYNC_RANGE ∈ {1d,3d,7d,all}`。
- **入口 3 — 去重预检**：`_duplicate_live_expression_block` 用 `ExpressionHistoryIndex.lookup` + `actionable_duplicate_expression_records` 过滤历史命中，命中即阻断。

`_run_simulation_with_api_and_settings` 7 步：validate → submit → poll（最多 5 次，`max_polls ∈ [1,20]`，间隔 `[0.5,30]s`）→ fetch result → 写历史 → 返回。

`_run_simulation_batch` 用 `ThreadPoolExecutor`，但当 `self.api` 存在时强制 `effective_workers=1`（避免 API 端触发 429）。

#### 3.2.3 26 工具分类

| 阶段 | 代表工具 |
|------|----------|
| 数据准备 | `build_market_data_cache`, `search_parameters`, `orchestrate_parameter_search` |
| 回测 | `run_single_backtest`, `run_parallel_backtest` (alias: run_backtest/run_batch_backtest) |
| 校验 | `check_alpha`, `sync_cloud_alphas`, `check_live_submit_readiness` |
| 评分 | `score_candidate` (alias: score_factor), `run_anti_overfit`, `run_rolling_validation` |
| 提交 | `submit_alpha`, `verify_submission` |
| 助手 | `build_assistant_context`, `build_assistant_request`, `parse_assistant_response`, `cross_review_assistant_response` |
| 运营 | `send_alert`, `route_alert`, `get_job_status` |

---

### 3.3 `mcp_server.py` — JSON-RPC 2.0 stdio 适配器

- `handle_request(request)` 派发：
  - `initialize` → 返回 `protocolVersion="2024-11-05"` + server info。
  - `tools/list` → 委托 `toolbox.list_tools()`，附 5 个 annotation（`liveApi` / `destructive` / `aliasFor` / `category` / `chainStage`）。
  - `tools/call` → 委托 `toolbox.call(name, arguments)`。
- `serve_stdio()` 行级 JSON 解析。
- `build_toolbox(config_path, allow_live_api)`：按 `kind` 区分 `prod/sync/check`，**每个 kind 创建独立 JobStore**（互不串扰）。
- 错误码：`-32601`（method not found）/ `-32700`（parse error）。
- CLI 参数：`--config` / `--allow-live-api`。

---

### 3.4 任务执行子系统

| 文件 | 行 | 角色 |
|------|----|------|
| `tasks.py` | 565 | `JobStore`：状态机 + 持久化 + 心跳 + 看门狗 |
| `task_executor.py` | 96 | 抽象 `TaskExecutor` + `Thread/Process` 两种实现 + `run_job()` 顶层包装 |
| `adaptive_executor.py` | 355 | `AdaptiveExecutor`：IO/CPU 自动分流 + `CachedAPIRateLimiter` + `run_adaptive_job` |
| `stall_monitor.py` | 286 | 后台守护线程，检测进度停滞 → 自动中断 |

#### 3.4.1 `JobStore` 状态机

- `ACTIVE_STATUSES = {queued, pending, starting, running, stopping}`
- `TERMINAL_STATUSES = {completed, completed_with_warnings, failed, stopped, cancelled, canceled}`
- API：`create / create_if_no_active / update / heartbeat / cancel / is_cancelled / get / latest_active / latest_any / all / watchdog_sweep / clear`
- `_load()`：启动时把"上轮仍 ACTIVE"的 job 标记为 `failed(recovery_error)`，**fail-closed**。
- `_persist_locked()`：temp + `os.replace` 原子写。
- `_watchdog_locked()`：`updated_at` 超过 `DEFAULT_WATCHDOG_TIMEOUT_SECONDS=300` 即强制 failed。
- `_compact_runtime_result`：对 `COMPACT_LIST_KEYS = {alphas, cloud_alphas, candidates, backtests, lifecycle_records}` 截断到 50 条防爆。
- `_submission_evidence_rows`：自动生成审计证据行。
- `_job_safe`：redaction + compaction 串联。

#### 3.4.2 `AdaptiveExecutor` 自适应分流

- 环境变量：`BRAIN_ALPHA_IO_WORKERS=8` / `BRAIN_ALPHA_CPU_WORKERS`（默认 = CPU 核数）。
- `_classify_task(fn)` 用 token 启发式判断 IO/CPU：
  - 含 `simulate|submit|fetch|api|http` → IO pool。
  - 含 `score|compute|encode|decode|render` → CPU pool。
- `_submit_cpu` 三层容错：捕获 `TypeError | AttributeError | RuntimeError`（如闭包/lambda 不可 pickle）→ 退到 thread pool。
- `CachedAPIRateLimiter`：TTL cache + 退避重试 + **全失败后 stale-serve**（不抛错，返回过期值）。
- `CacheEntry` dataclass 含 `expired` 计算属性。

#### 3.4.3 `StallMonitor` 进度守护

- `DEFAULT_STALL_TIMEOUT_SECONDS=120` / `DEFAULT_POLL_INTERVAL_SECONDS=15`。
- 内部 `JobStallSnapshot` / `StallMonitorConfig` dataclass。
- 检测逻辑：连续 N 次 `progress_percent / phase / status` 全部不变 → 触发 `interrupt_callback`。
- 单例：`ensure_global_monitor()` / `stop_global_monitor()` / `create_stall_monitor_for_web_server()`。
- 实际行为：调用 `web_jobs.job_update(job_id, status="stopped", reason="stall")`。

---

### 3.5 `research/` — 核心 alpha 研发流水线（106 文件 / 33,340 行）

#### 3.5.1 核心抽象

- **Pipeline**：`AlphaResearchPipeline`（pipeline.py:107）注入 17 个 service，多 mixin 组合（`PipelineRuntimeMixin` / `PipelineContextSyncMixin` / `PipelineServiceFactoryMixin` / `PipelineStrategyMixin` / `PipelineCandidatePoolMixin` / `PipelineOfficialValidationMixin` / `PipelineBacktestMixin` / `PipelineLegacySimulationMixin` / `PipelineSubmissionMixin` / `PipelineSnapshotMixin`）。
- **Generator**：`CandidateGenerator`（generator.py:683）/ `HypothesisDrivenGenerator`（hypothesis_driven_generator.py:1325，**god module**）/ `ValidatedGenerator`（582 行）。
- **Candidate**：`Candidate`（models.py:90，24 字段 dataclass）。
- **Cycle / Phase**：`ResearchCycleOrchestrator`（research_cycle_orchestrator.py）/ `CycleDecision` / `CycleState` / `PipelineRuntimeState`。
- **Pipeline phase 拆分**：10 个 `pipeline_*.py` 独立 mixin（见 §3.5.2）。

#### 3.5.2 Pipeline 子模块拆分（10 mixin）

| 文件 | 角色 |
|------|------|
| `pipeline_runtime.py` | 运行时 mixin（`PipelineRuntimeMixin`） |
| `pipeline_context_sync.py` | 上下文同步（`PipelineContextSyncMixin`） |
| `pipeline_services.py` | 服务工厂（`PipelineServiceFactoryMixin`） |
| `pipeline_strategy.py` | 策略切换（`PipelineStrategyMixin`） |
| `pipeline_candidates.py` | 候选池（`PipelineCandidatePoolMixin`） |
| `pipeline_official_validation_flow.py` | 官方校验流（`PipelineOfficialValidationMixin`） |
| `pipeline_backtest_flow.py` | 回测流（`PipelineBacktestMixin`） |
| `pipeline_legacy_simulation.py` | 历史 simulation 兼容（`PipelineLegacySimulationMixin`） |
| `pipeline_submission_gate.py` | 提交门禁（`PipelineSubmissionMixin`） |
| `pipeline_snapshots.py` | 快照（`PipelineSnapshotMixin`） |

辅助模块：
| 文件 | 角色 |
|------|------|
| `pipeline_state.py` | `CycleState` / `PipelineRuntimeState` / `bind_runtime_state_properties`（**反射破坏类型**） |
| `pipeline_snapshot.py` | 快照构造器 |
| `pipeline_observability.py` | 可观测性注入 |
| `pipeline_official_context.py` | 官方上下文加载 |
| `pipeline_helpers.py` | 通用 helper |
| `pipeline_cloud.py` | 云端自相关 |
| `pipeline_diversity.py` | 多样性保证 |

#### 3.5.3 数据流 7 步

```
Hypothesis YAML → HypothesisLibrary → HypothesisDrivenGenerator (3-mode 70/20/10)
  → CandidateGenerator → PipelineCandidatePoolMixin._local_prefilter (scorecard)
  → OfficialValidationService → BatchBacktestCoordinator → BacktestSubmissionService
  → BacktestPollingService → BacktestFinalizationService → PipelineSubmissionMixin._try_auto_submit
  → SubmissionLedger.assess → API.submit_alpha
```

#### 3.5.4 持久化分层

- **JSONL** 为主存（`Repository` 管 12 个文件 + 文件锁）
- **SQLite** 为查询加速层（`expression_index.sqlite` / `records_index.sqlite`），但 `refresh()` 启动全量重建（**P3 风险**：DELETE + INSERT，无 WAL/timeout）
- **Checkpoint** 保留最近 20 份
- **KnowledgeBase** 用 `data/knowledge_base/{rules,findings,failures}/*.json` 人读结构（**P3 风险**：写无锁）

#### 3.5.5 并发模型

- `parallel_backtest.py` 真正用 `ThreadPoolExecutor`（无锁、IO 密集）
- `batch_backtest_coordinator.py` 同步纯函数，`max_workers` 是元数据
- `BacktestSlotManager` 槽位串行但 BRAIN 平台侧并发
- `Repository` 用文件锁，`CheckpointManager` 用 `threading.Lock`
- **不一致**：同一概念"并行回测"两个不同实现（P3）

#### 3.5.6 安全门 4 道

1. `SubmissionLedger.assess` — 5 项硬检查（日限 / run 限 / 间隔 / gate / 风险等级）
2. `OfficialCallGuard` — 重复表达式阻断（基于 observability guidance）
3. `OfficialValidationService` — 预检验 + 429 触发 halt
4. LLM 层无 rate-limit / token quota（**P3 风险**）

#### 3.5.7 LLM 集成

- 三层架构：`LLMService` API → `LLMProvider` 协议 → 4 种实现
- `OpenAICompatibleProvider` 用 `urllib` 不依赖 SDK
- `PromptRunLedger` 记录 token/latency
- 协议：4 个 `@runtime_checkable Protocol`（`LLMProvider` / `FallbackLLMProvider` / `StaticLLMProvider` / `LLMProviderRouter`）

#### 3.5.8 God module 清单

| 文件 | 行 | 风险 |
|------|----|------|
| `hypothesis_driven_generator.py` | **1325** | 4 个 selector 类同文件（`GenerationModeRouter` / `HypothesisSelector` / `ExpressionFamilySelector` / `FieldSelector` / `ContextAdapter`） |
| `local_backtest_engine.py` | **1148** | 本地回测引擎+多业务混入 |
| `observability.py` | 940 | 可观测性聚合 |
| `assistant.py` | 865 | 助手逻辑 |
| `scoring.py` | 844 | 8 维 prior + empirical + checklist 混一文件 |
| `alpha_quality.py` | 820 | 质量评估 |
| `hypothesis_library.py` | 777 | 假设库 |
| `alpha_checks.py` | 757 | 检查项过多 |
| `context.py` | 745 | 上下文聚合 |
| `theme_engine.py` | 737 | 主题引擎 |
| `pipeline.py` | 693 | 主类注入 17 service |
| `evolution.py` | 691 | 进化算法 |
| `generator.py` | 683 | 候选生成器 |
| `validated_generator.py` | 582 | 验证生成器 |
| `expression_sqlite_index.py` | 557 | SQLite 索引（启动全量重建） |
| `cross_review_pipeline.py` | 527 | 交叉审查 |
| `memory.py` | 533 | 记忆 |

---

### 3.6 `web/` 根级 — HTTP 服务层（90+ 文件 / 21,597 行）

> 详见独立深度分析。核心结论：当前生产路径走 `web/__init__.py:556-624` 的内联 `dispatch_get/post`，而非 `web_handler_dispatch._dispatch_route`。

#### 3.6.1 关键文件清单

| 类别 | 文件 | 行 | 角色 |
|------|------|----|------|
| 入口 | `web/__init__.py` | 821 | 胶水层 + 9 个 `_real_*` 内联 + 70+ facade 注入 |
| 入口 | `web_cli.py` | 95 | `serve` / `shutdown` / `smoke` / `main` CLI |
| 入口 | `web_server_lifecycle.py` | 157 | `SafeThreadingHTTPServer` / `find_free_port` / `serve` |
| 入口 | `web_http_handler.py` | 302 | `create_handler_class` 工厂（**P0 bug 潜伏地**） |
| 入口 | `web/ws.py` | 97 | WebSocket pub/sub（ADR-004 引入未启用） |
| 路由 | `web_routes.py` | 875 | URL ↔ Route 映射表（`_build_route_map()` 55 GET + 39 POST） |
| 路由 | `web_handler_dispatch.py` | 1094 | 核心分发器（**god module**） |
| 路由 | `web_handler_candidate_routes.py` | 196 | 候选 GET 路由辅助 |
| 路由 | `web_get_handlers.py` | 91 | 纯 GET 负载构造 |
| 路由 | `web_post_handlers.py` | 81 | 纯 POST 负载构造 |
| 路由 | `web_payload_validation.py` | 320 | 所有 POST 请求体验证器 |
| 状态 | `web_state_contract.py` | 446 | 共享 Web 状态/用户错误契约（14 错误类型） |
| 状态 | `web_dispatch_context.py` | 422 | `WebHandlerDispatchContext` + 7 子 context dataclass |
| 状态 | `web_runtime_facade.py` | 781 | **核心 facade 适配层**（80+ 字段 Callable） |
| 状态 | `web_runtime_bindings.py` | 89 | watchdog sweep 后台线程 + `serve` 入口 |
| 状态 | `web_runtime_state.py` | ~100 | 运行时状态 helper |
| 状态 | `web_facade_bindings.py` | 301 | 巨型 namespace builder（180+ 符号） |
| 状态 | `web_service_namespace.py` | 363 | 130+ 符号的依赖注入 namespace |
| 状态 | `web_application_context.py` | 4 | re-export shim |
| 状态 | `web_session_bindings.py` | ~ | re-export shim |
| 安全 | `web_security.py` | 345 | `LocalSessionManager`（会话存储/CSRF/stream token/重放保护） |
| 安全 | `web_session.py` | 450 | 全局 `SESSION_MANAGER` 暴露层 + BRAIN 凭据 vault |
| 安全 | `web_csp.py` | 43 | CSP 策略生成（扫描 `<script>/<style>` 内联 hash） |
| 安全 | `web_rate_limit.py` | 102 | `RequestRateLimiter` 滑窗限流（read=60/write=20/submit=5 per 1s） |
| SSE | `web_sse.py` | 247 | `SSEWriter` / `SSEStreamHandler`（timeout 300s, poll 0.5s） |
| SSE | `web_async_jobs.py` | 351 | `run_simple_async_job_service` 通用异步任务包装 |
| Job | `web_jobs.py` | 419 | 旧式 `ASYNC_JOBS` 全局 dict |
| Job | `web_job_registry.py` | 95 | `WebJobRegistry` 类（4 通道） |
| Job | `web_simulation_job.py` | 55 | `create_sim_job_store` 工厂 |
| Job | `web_sync_job.py` | 597 | `run_sync_job_service` |
| Job | `web_run_job.py` | ~ | 后台生产 job 入口 |
| 候选 | `web_candidate_generation.py` | 524 | 本地候选生成 + 质量门禁 + 审计 |
| 候选 | `web_candidate_selection.py` | 171 | `candidate_from_payload` / `passed_candidates_from_payload` |
| 候选 | `web_candidate_payloads.py` | 309 | `candidate_main_pool` / `candidate_pool_summary` |
| 候选 | `web_candidate_workflow.py` | 337 | `candidate_workflow_plan` |
| 候选 | `web_candidate_audit.py` | 508 | 科学审计（`attach_scientific_audit`） |
| 候选 | `web_candidate_optimization.py` | 706 | 本地候选优化（不改官方） |
| 候选 | `web_candidate_decisions.py` | 511 | 候选池行级生产决策 |
| 候选 | `web_candidate_lifecycle_risk.py` | ~ | 本地 lifecycle 历史风险摘要 |
| 候选 | `web_candidate_bindings.py` | 579 | **合并 facade**（Phase 1-B 自动化生成） |
| 候选 | `web_candidate_simulation.py` | 996 | **BRAIN 官方模拟后台任务（核心 job）** |
| 候选 | `web_candidate_simulation_runtime.py` | ~ | 模拟 runtime 助手 |
| 候选 | `web_candidate_simulation_state.py` | 497 | 模拟状态（cooldown / defer / score） |
| 候选 | `web_candidate_simulation_selection.py` | ~ | 目标选择 |
| 候选 | `web_candidate_simulation_failures.py` | ~ | 失败证据 |
| 候选 | `web_candidate_check.py` | 170 | 旧 re-export |
| 候选 | `web_candidate_check_evidence.py` | ~ | 持久化检查证据 |
| 候选 | `web_candidate_optimization_explainability.py` | ~ | 优化可解释性 helper |
| 候选 | `web_candidate_generation_summary.py` | ~ | 生成 job 人类可读状态消息 |
| 检查 | `web_check_availability.py` | 879 | **单候选可用性检查（13 项 CHECK）** |
| 检查 | `web_check_batch_context.py` | ~ | 批量检查官方上下文 |
| 检查 | `web_check_batch_job.py` | 44 | 旧 re-export |
| 提交 | `web_submission_single.py` | 154 | `submit_candidate_payload` 单提交 |
| 提交 | `web_submission_batch.py` | 271 | `submit_batch_payload` 批量提交 |
| 提交 | `web_submission_safety.py` | 403 | preflight + observability + readiness |
| 提交 | `web_submit_readiness.py` | 122 | 提交就绪 payload 服务 |
| 同步 | `web_sync_payload.py` | ~ | `sync_cloud_alphas_payload` 同步入口 |
| 同步 | `web_sync_status_payload.py` | ~ | status payload 装饰器 |
| 同步 | `web_cloud_snapshot.py` | 905 | **云端 alpha 快照** |
| 同步 | `web_cloud_context_refresh.py` | 167 | `refresh_cloud_context_for_check_service` |
| 快照 | `web_snapshots.py` | ~ | 旧 re-export shim |
| 快照 | `web_snapshot_facade.py` | ~ | `WebSnapshotFacade` 公共 facade |
| 快照 | `web_snapshot_runtime.py` | ~ | `WebSnapshotRuntime` 依赖注入 |
| 快照 | `web_snapshot_bindings.py` | ~ | 旧 facade re-export |
| 快照 | `web_assistant_snapshots.py` | 780 | **Assistant 全套快照** |
| 快照 | `web_sqlite_indexes.py` | ~ | `sqlite_index_snapshot` / `sqlite_expression_lookup_payload` |
| 快照 | `web_capability_registry.py` | 318 | 离线 BRAIN 能力注册表 |
| 快照 | `web_alpha_lifecycle.py` | ~ | alpha lifecycle 复盘 payload |
| 快照 | `web_backtest_slots.py` | 485 | 回测槽位/队列摘要 |
| 快照 | `web_redline_scoring.py` | ~ | 红线评分 |
| 快照 | `web_review.py` | ~ | 旧 re-export shim |
| 快照 | `web_review_api.py` | ~ | 反过拟合/交叉评审 API 入口 |
| 配置 | `web_config.py` | 515 | 运行时配置 helper |
| 配置 | `web_config_bindings.py` | ~ | 旧 facade re-export |
| 配置 | `web_config_schema.py` | ~ | `public_config_schema` 公开 schema |
| 杂 | `web_progress.py` | ~ | 进度展示 helper |
| 杂 | `web_errors.py` | ~ | 错误塑形（`safe_error_message`） |
| 杂 | `web_html.py` | ~ | HTML 装载 + CSP 注入 + script/style hash 来源 |
| 杂 | `web_compat_facade.py` | 59 | 旧测试兼容 |
| 杂 | `web_legacy_exports.py` | ~ | 旧公共导出映射 |

#### 3.6.2 关键流程：候选 alpha 生命周期

```
1. generation（生成）
   web_candidate_generation.generate_candidates_payload
   - 表达式生成 + 质量门禁 + 输出参数审计
   - 持久化到 candidates.jsonl（ResearchRepository.save_candidate）

2. check（检查）
   web_check_availability.check_candidate_availability
   - 13 项检查：production_gate / official_alpha_id / official_pass_fail /
     official_metric_fields_complete / decision_band_submit_candidate /
     not_failed_locally / cloud_sync_available / not_submitted_before /
     cloud_status_not_already_submitted / cloud_self_correlation /
     context_health_preflight / official_pre_submit_check
   - 调用 BRAIN api.check_alpha() 走最终预提交
   web_candidate_check.check_candidate_payload (web 内部 API 入口)
   web_check_batch_job.run_check_batch_job_service (批量入口)

3. simulation（官方模拟）
   web_candidate_simulation.simulate_candidates_job
   - 选 target (eligible_for_simulation, min_score)
   - 提交到 BRAIN api.submit_simulation
   - 轮询 api.get_simulation 直至完成/限流/超时
   - 处理 CONCURRENT_SIMULATION_LIMIT_EXCEEDED / 429 rate limit
   - 回写 candidates.jsonl (scorecard, official_metrics, lifecycle_status)
   - 落审计到 web_candidate_audit

4. scoring（评分）
   web_redline_scoring.handle_scoring_evaluate
   - 通过 web_scorecard 构建
   - 决定 decision_band (submit_candidate / passed / failed)

5. audit（审计）
   web_candidate_audit.attach_scientific_audit / append_scientific_audit_event
   - 解释每次状态变化（operation / source / feedback_sources / details）

6. decision（决策）
   web_candidate_decisions.candidate_production_decision
   web_candidate_lifecycle_risk.local_lifecycle_risk_summary
   - 本地决策：进 passed 池、丢弃、保留
   web_candidate_workflow.candidate_workflow_plan
   - 跨生产/验证的队列规划

7. optimization（优化）
   web_candidate_optimization.optimize_candidates_payload
   - 仅本地：参数微调、字段替换；不调官方 API
   - 持久化 web_candidate_optimization.persist_optimized_candidates

8. submission（提交）
   web_submission_single.submit_candidate_payload / web_submission_batch.submit_batch_payload
   - **Web 流程强制 REAL_SUBMIT_DISABLED_WEB_FLOW（return 403）**
   - 必须走单独审批路径（real submit disabled 2024 决策）
   - 但完整 preflight + observability + readiness gate 仍可计算（用于审计）
```

#### 3.6.3 提交安全模型

**Web 端策略（强制阻断）**：
- `web/__init__.py:341-357` `_submit_disabled_payload()` 返回固定阻断
- `web/__init__.py:556-624` `dispatch_post` 14 个真实后端路由里 `/api/submit`、`/api/submit_batch` **直接**调 `_submit_disabled_payload()`
- `web_handler_dispatch.py:759-768` 的 `_post_submit()` 同样返回 `REAL_SUBMIT_DISABLED_WEB_FLOW`
- 但 `web_submission_single.py:31` 的 `submit_candidate_payload()` 是**真实现** —— **如果有人改 `web/__init__.py:341-357` 或 `web_handler_dispatch.py:759-768` 把那两行取消** —— 真提交就会重新打开
- **没有任何中心化常量** `REAL_SUBMIT_DISABLED = True` 之类把这个约束写进"不可移除的常量"（**P0 安全弱点**）

**Pre-flight 链（即使在阻断后仍跑）**：
1. `submission_preflight_advisory`（`web_submission_safety`）：
   - 缺 official_alpha_id → `MISSING_OFFICIAL_ID`
   - mock / stub 形式 ID → `NON_PRODUCTION_ALPHA_ID`
   - 缺 metrics → `MISSING_OFFICIAL_METRICS`
   - pass_fail != PASS → `OFFICIAL_ALPHA_CHECK_NOT_PASS`
   - 缺 metric 字段 → `MISSING_OFFICIAL_METRIC_FIELDS`
   - release gate FAIL → `OFFICIAL_RELEASE_GATE_FAILED`
   - decision_band != submit_candidate → `SUBMIT_DECISION_BAND_NOT_READY`
   - lifecycle_status != submission_ready → `SUBMIT_NOT_READY`
   - 本地重复 → `SUBMIT_DUPLICATE_OFFICIAL_ID` / `SUBMIT_DUPLICATE_EXPRESSION`
   - 云端自相关 high → `SUBMIT_CLOUD_SELF_CORRELATION_BLOCKED`
   - 云端未同步 → `SUBMIT_CLOUD_SYNC_REQUIRED` / `SUBMIT_CLOUD_SYNC_STALE`
   - 云端已提交 → `SUBMIT_CLOUD_ALREADY_SUBMITTED`
2. `observability_submission_preflight`：读取 `build_research_observability_snapshot` 上下文健康
3. `submit_readiness_hard_gate`（`live_submit_readiness_assessment`）：实时就绪度硬门禁
4. `confirm_submit` / `confirm_observability_risk`：客户端必须传确认位

**阻止事件记录**：
- `record_submit_blocked_event`：写 `lifecycle.jsonl` 中 `submission_blocked` 记录（含 `failure_reason`）

#### 3.6.4 安全模型总览

- **CSP**（`web_csp.py`）：
  - 默认策略：`default-src 'self'; script-src 'self' [+CDN] [+内联hash]; style-src 'self' [+内联hash]; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'`。
  - 内联 hash 通过扫描 `<script>/<style>` 内容计算 SHA-256 + base64。
  - 若 HTML 引用 `unpkg.com` / `cdn.tailwindcss.com` 则自动追加白名单。
  - 注入位置：Handler `_send_security_headers(html)` → `Content-Security-Policy` 响应头。

- **XSS 防护**：
  - 响应头：`X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`、`Referrer-Policy: no-referrer`。
  - 所有错误消息通过 `redact_error_message` 脱敏。
  - 状态/响应 JSON 经 `redact_data(payload, key_fragments=("account_id", "user_id"))` 过滤。
  - CSP 拦截任何内联 / 跨源脚本。

- **CSRF 防护**：
  - Cookie 属性：`HttpOnly; SameSite=Strict`（远程模式追加 `Secure`）。
  - CSRF 验证：handler 读 `X-Brain-Alpha-CSRF` / `X-CSRF-Token` / `X-CSRF` 任一头；与 session 中的 token 用 `secrets.compare_digest` 常时比较。
  - SSE 端点不要求 CSRF，但要求 stream token（query `stream_token`）。
  - `/api/session` 是唯一免 CSRF 的 POST（创建新会话）。

- **重放保护（M-SEC-03）**：
  - 客户端必传 `X-Brain-Alpha-Request-ID`（≤128 字符，无空白）+ `X-Brain-Alpha-Request-Timestamp`（epoch 秒或毫秒，TTL 5 分钟）。
  - 服务端 per-session 缓存 `request_replay: dict[request_id, expires_at]`，命中即返回 `REPLAY_DETECTED (409)`。
  - 容量硬上限 `MAX_REPLAY_CACHE_SIZE = 10_000`（防止 DoS）。

- **Origin / 跨站**（`is_allowed_request`）：
  - 默认仅接受 `127.0.0.1` / `localhost` / `::1`。
  - 验证 `Host` / `Origin` / `Referer` 三处 hostname。
  - `allow_remote=True` 时按精确 host 比对（要求 env `BRAIN_ALPHA_OPS_WEB_ADMIN_TOKEN`）。

- **限流**（`web_rate_limit.py`）：
  - 滑窗策略：`RateLimitPolicy(read=60, write=20, submit=5, window=1.0s)`。
  - Bucket 路由：POST + path 含 `submit` → submit 桶；GET/HEAD/OPTIONS → read 桶；其余 POST → write 桶。
  - 身份：优先用 `session_id`，否则 `client_addr`，最后 `host`。
  - 触发：`{ok: False, error_code: "RATE_LIMITED", retry_after: float}`，HTTP 429 + `Retry-After` 头。

- **凭据保险库**：
  - 凭据仅存内存：Session 行内 `BRAIN_CREDENTIALS_KEY` 字段；不写入 metadata（不返回浏览器）；session 过期即丢。
  - `mark_brain_connection_verified` 仅记录 `verified_at` / `environment` / `auth_mode` / `credential_source`。
  - `payload_with_brain_session_credentials` 把 vault 中凭据合并到 outbound payload。

#### 3.6.5 异步任务模型

- **4 个 Job Store**（来自 `web_job_registry`）：
  - `JOBS`：生产 run（`_real_run` → `run_job` → 流水线）
  - `SYNC_JOBS`：云端 alpha 同步（`run_sync_job_service`）
  - `CHECK_JOBS`：批量检查（`run_check_batch_job_service`）
  - `ASYNC_JOBS`：候选生成、评分、模拟、优化（`run_simple_async_job_service`）
  - `SUBMIT_LOCK`：仅 1 个并发 submit

- **启动模式**：
  1. **dedicated thread**（直接 `threading.Thread(daemon=False).start`）：
     - `_handle_pipeline_start`（legacy 禁用）
     - `_handle_candidate_simulate`（via `run_sim` + `web_simulation_job.create_sim_job_store`）
  2. **`_submit_background_job`** 包装：从 `web_job_bindings.submit_background_job` → 调 `task_executor.ThreadTaskExecutor` 提交。
  3. **`run_simple_async_job_service`**（`web_async_jobs.py`）：内置 30s heartbeat（独立线程）+ cancel 探测 + 统一 `error_payload` 包装。
  4. **`run_*_job_service`**（专用）：`run_sync_job_service` / `run_check_batch_job_service` / `run_guided_job_service` / `run_job_service` / `simulate_candidates_job`。

- **Watchdog**：
  - `web_runtime_bindings._watchdog_sweep_loop`：守护线程周期调 `store.watchdog_sweep()`。
  - 间隔自适应：`min(store.watchdog_timeout_seconds) / 2`，封顶 5-30s。

#### 3.6.6 启动流程

```
launch_web.py
  ↓
brain_alpha_ops.web.main(sys.argv[1:])     # web/__init__.py: main()
  ↓
args = argparse --port / --host / --config / --no-browser / --smoke-test / --frontend
  ↓
run_config = web.load_run_config(args.config)
  ↓
selected_port = run_config.web.port (or --port)
  ↓
if args.smoke_test:
   web.smoke_test_server(port=selected_port)  # → serve() → urlopen root → check html
   exit 0
  ↓
url = web.serve(                # 来自 web_runtime_facade.serve
   port=selected_port,
   open_browser=run_config.web.open_browser and not args.no_browser,
   host=run_config.web.host,
   session_ttl_seconds=run_config.web.session_ttl_seconds,
   allow_multiple_sessions=run_config.web.allow_multiple_sessions,
   allow_remote=run_config.web.allow_remote,
   secure_cookies=run_config.web.secure_cookies or run_config.web.allow_remote,
)
  ↓
web_session.set_remote_policy(allow_remote, admin_token_env=...)
web_session.require_remote_admin_token()
web.configure_session_policy(ttl, allow_multiple, secure_cookies)
  ↓
url, server = web_server_lifecycle.serve(...)
  ├─ stop_event.clear()
  ├─ configure_session_policy(...)
  ├─ bind_host = normalize_host(host)
  ├─ if bind_host not in LOOPBACK_BIND_HOSTS and not allow_remote: raise
  ├─ bind_port = find_free_port(start=requested_port, host=bind_host)
  ├─ server = SafeThreadingHTTPServer((bind_host, bind_port), Handler)   # 工厂生成的 Handler
  ├─ actual_port = _server_port(server, bind_port)
  ├─ url = f"http://{display_host_for_bind(bind_host)}:{actual_port}/"
  ├─ if open_browser: webbrowser.open(url)
  └─ threading.Thread(target=server.serve_forever, daemon=True).start()
  ↓
url returned; web.SERVER = server (under SERVER_LOCK)
  ↓
watchdog sweep thread (from web_facade_bindings._start_watchdog_sweep_thread)
  - 每 5-30s 调 store.watchdog_sweep() 监控超时任务
  ↓
print("BRAIN Alpha Ops 已启动"); print(f"访问地址: {url}")
  ↓
while not web.SERVER_STOP.wait(3600): pass    # 阻塞至 shutdown
  except KeyboardInterrupt: web.shutdown_server()
```

#### 3.6.7 完整 URL 路由表

**GET 路由（55 条）**：`/` / `health` / `status` / `production-validation/status` / `config` / `config_schema` / `capabilities` / `active_job` / `latest_result` / `stream` / `sse` / `lifecycle` / `alpha_lifecycle` / `lifecycle/history` / `candidates` / `candidate/list` / `cloud_alphas` / `snapshot/cloud` / `snapshot/cloud_alphas` / `research_memory` / `snapshot/memory` / `snapshot/research_memory` / `research_knowledge` / `research_observability` / `snapshot/observability` / `prompt_runs` / `sqlite_indexes` / `snapshot/sqlite_indexes` / `sqlite_expression_lookup` / `sqlite_record_lookup` / `assistant_context` / `snapshot/assistant_context` / `assistant_guidance` / `snapshot/assistant_guidance` / `assistant_request` / `snapshot/assistant_requests` / `anti_overfit` / `snapshot/anti_overfit` / `rolling_validation` / `snapshot/rolling_validation` / `sync_status` / `check_status` / `check_results` / `profile` / `presets` / `redline_report` / `scoring/health` / `checkpoint_status` / `backtest_slots` / `submit_readiness` / `candidates/simulate/eligible` / `phase_state` / `refresh_session`

**POST 路由（39 条）**：`run` / `production-validation/start` / `config` / `config/update` / `test_connection` / `connection_test` / `stop` / `production-validation/stop` / `cancel` / `sync_alphas` / `sync-cloud-alphas` / `sync/sync_alphas` / `sync_context_only` / `sync_cancel` / `check` / `candidate/check` / `generate_candidates` / `generate` / `candidates/optimize` / `candidate/optimize` / `check_batch` / `submit` / `candidate/submit` / `submit_batch` / `assistant/parse` / `assistant_response/parse` / `assistant_response_parse` / `assistant/guidance` / `assistant_response_guidance` / `assistant/cross_review` / `assistant_cross_review` / `assistant_guidance` / `logout` / `shutdown` / `scoring/evaluate` / `scoring/attribution` / `candidates/simulate` / `session` / `pipeline/start`（legacy disabled）

**OPTIONS**：固定响应 `204` + `Access-Control-Allow-*` 头。

---

### 3.7 评分子系统（`scoring/`）

#### 3.7.1 文件清单（9 个模块）

| 文件 | 行 | 关键导出 |
|------|----|----------|
| `__init__.py` | 36 | 顶层 re-export：`decide_release`, `evaluate_release_score`, `ScoreHistoryDB`, `run_anti_overfit_suite` |
| `official_scoring.py` | 605 | `OfficialScoringSystem.evaluate` 7 步流水线 |
| `release_score_gate.py` | 419 | `ThresholdPolicy` delay-aware，`decide_release` 聚合 |
| `gates.py` | 185 | `OFFICIAL_HARD_GATE_NAMES`（8 门）/ `GateConfig.evaluate` |
| `attribution.py` | 192 | `AttributionNode` 三层树 + 26 维中文解释 |
| `anti_overfit.py` | 533 | IC 稳定性 / 子样本 / 安慰剂 / 半衰期四层验证 |
| `history.py` | 73 | `ScoreHistoryDB` JSONL + `convergence_stats` |
| `shared_scores.py` | 129 | `DEFAULT_PRIOR_WEIGHTS` 8 维（和=1.0） |
| `visualization.py` | 115 | 树+条形图 payload + top_failures 摘要 |
| `scoring_comparison.py` | ~ | `simulate_brain_api_output`（API 仿真） |

#### 3.7.2 零偏差目标

- 核心 KPI：`api_output_deviation == 0.0` —— 本地模拟输出与真实 BRAIN API 输出字段级一致。
- `_simulate_api_output` 委托 `scoring_comparison.simulate_brain_api_output`。
- `_config_hash` SHA-256(thresholds + layer_weights)：同一份配置必须可复现。

#### 3.7.3 评分数据结构

`ScoringResult`（`official_scoring.py`）字段：`alpha_id, expression, total_score, decision_band, passed_gate, prior_scores, empirical_scores, checklist_scores, layer_weights, hard_gates, soft_gates, release_gate, attribution_tree, top_failures, improvement_hints, simulated_api_output, api_output_deviation, threshold_version, scoring_schema, config_hash`。

`evaluate()` 7 步：scorecard → gate → attribution → API sim → hints → failures → history。

`release_score_gate.py` 的 `ThresholdPolicy` 关键设计：
- `delay=0` → 用 `min_sharpe_delay0=2.0`（更严）
- `delay≥1` → 用 `min_sharpe=1.25`
- `_sub_universe_sharpe_threshold = policy.sub_universe_sharpe_min_ratio * sqrt(subUniverseSize/alphaSize) * sharpe`

#### 3.7.4 8 个硬门（`gates.py`）

`OFFICIAL_HARD_GATE_NAMES = {sharpe, fitness, turnover_min, turnover_platform, self_correlation, prod_correlation, weight_concentration, sub_universe_sharpe}`

软门来源：`QUALITY_TARGETS` + `SUBMISSION_CHECKLIST`。

#### 3.7.5 反过拟合（`anti_overfit.py`，533 行）

四层验证：
1. **IC Stability**（窗口 ≥ 20）
2. **Subsample Stress**（regime 最小 30 样本）
3. **Placebo Test**（50 次试验）
4. **Half-Life Estimation**

`AntiOverfitResult` 含 5 个具名分数。

---

### 3.8 合规层（`compliance/` — 六条技术红线）

| 文件 | 行 | 对应红线 |
|------|----|----------|
| `__init__.py` | 1 | 文档字符串说明六条线 |
| `redline_verifier.py` | 126 | 编排：`verify_all / verify_and_block / verify_quick` + CLI |
| `redline_models.py` | 124 | `RedLineViolation` / `ComplianceReport` / `RedLineBlockedError` |
| `redline_check_no_custom_extension.py` | 94 | **RL1** 字段/算子禁自定义扩展（4 子检） |
| `redline_check_thresholds.py` | 127 | **RL2** 阈值零偏差（10 key vs `CANONICAL_THRESHOLDS`） |
| `redline_check_datasets.py` | 131 | **RL3** Dataset ID 全量可用（3 子检） |
| `redline_check_traceability.py` | 151 | **RL4** 参数全链路可溯（5 子检） |
| `redline_check_coverage.py` | 90 | **RL5** 要素全覆盖（7 必检 BRAIN check） |
| `redline_check_alignment.py` | 192 | **RL6** 代码强对齐（5 子检：base_url/API paths/settings/enum/metric names） |
| `redline_helpers.py` | 176 | `_project_root` / `_runtime_storage_dir` / `_verify_generator_templates_against_official_context` |

**RL6 详细**（5 子检）：
- 6a base_url 必须 `https://api.worldquantbrain.com`
- 6b 14 个 `CANONICAL_API_PATHS` 全对齐
- 6c settings 11 个 enum validator 与 `CANONICAL_SETTINGS` 一致
- 6d config/web enum 校验器一致
- 6e `empirical_score` 指标名与 `CANONICAL_METRIC_NAMES` 一致

**失败时序**：`verify_and_block()` 收集所有 `BLOCKING` 严重度违规 → 抛 `RedLineBlockedError`（携带 violation 列表 + 修复建议） → `guided_pipeline` 在 `redline` 阶段捕获并转换为 `RuntimeError("TECH_REDLINE_BLOCKED: ...")`。

---

### 3.9 Domain Bounded Contexts（`domains/` — 5 个薄 re-export）

| 文件 | 行 | 导出 |
|------|----|------|
| `__init__.py` | 5 | 顶层聚合 |
| `backtest.py` | 3 | `LocalBacktestEngine` / `BacktestSlotManager` |
| `generation.py` | 3 | `CandidateGenerator` / `HypothesisLibrary` |
| `scoring.py` | 5 | `build_scorecard` / `evaluate_quality_gate` / `AlphaCheckRegistry` / `AntiOverfitService` / `ConvergenceTracker` |
| `simulation.py` | 2 | `OfficialValidationService` |
| `strategy.py` | 5 | `StrategyLifecycleManager` / `StrategyPluginRegistry` / `load_strategy_plugin` / `StrategySwitch` / `DatasetSelector` |

> **干净的 DDD 范式**：每个文件 < 6 行，只做符号重导出。真正的实现仍在 `research/`。

---

### 3.10 Shared Contracts（`shared/contracts.py`，89 行）

5 个 `@runtime_checkable` Protocol，**全代码库解耦点**：

| Protocol | 方法 |
|----------|------|
| `PhaseStateProvider` | `get_phase_state()` → current_phase / connected / context_fresh / candidates_count / scored_count / readiness_passed / sync / connection / readiness |
| `ProgressReporter` | `report(phase, message, percent, scanned, total, elapsed_seconds, eta_seconds)` + `is_cancelled()` |
| `CloudCache` | `count()` / `last_sync_at()` / `is_fresh(max_age_seconds)` |
| `JobStore` | `create(data)` / `get(job_id)` / `update(job_id, **kwargs)` / `cancel(job_id)` / `is_cancelled(job_id)` / `latest_active()` / `list_all()` |
| `EventPublisher` | `publish(event_type, payload)` / `subscribe(event_type, handler)` / `unsubscribe(event_type, handler)` |

> **P3 风险**：`@runtime_checkable` 是 Duck typing 而非 ABC；IDE 支持好但运行时无 enforce。

---

### 3.11 UX 子系统（`ux/`）

| 文件 | 行 | 角色 |
|------|----|------|
| `__init__.py` | 26 | `__getattr__` 懒加载（避免循环导入） |
| `errors.py` | 391 | `STATUS_CODE_ZH` 50+ 中文 / `_ERROR_PATTERNS` 18 条 / `translate_*` 4 函数 / `PHASE_GUIDANCE` 6 阶段 |
| `guided_pipeline.py` | 443 | **10 阶段管线** |
| `guided_models.py` | 107 | `PipelinePhase` / `CheckpointData` / `RunRecord` dataclass |
| `guided_storage.py` | 151 | 检查点/历史持久化 + `RunHistoryAnalytics` 委托 |
| `guided_display.py` | 74 | ASCII 进度条 `[====----] 6/10 phases` |
| `guided_formatting.py` | 75 | `classify_error` + 中文格式化 |
| `user_messages.py` | 351 | `MESSAGE_CATALOG` 30+ 预定义消息（10 类别） |
| `history.py` | 245 | `RunHistoryAnalytics`（10 MiB 文件大小守护） |

#### 3.11.1 `GuidedPipeline` 10 阶段

```
init → context → redline → generation → validation
     → simulation → scoring → gating → submission → finalize
```

- `run_guided()`：从 init 跑到 finalize。
- `resume(run_id)`：从 `load_checkpoint` 恢复。
- `on_progress(callback)`：注册进度回调。
- `stop()`：调用 `stop_callback`（来自 `web_run_job` 注入 `job_store.is_cancelled`）。
- `print_progress()` / `print_summary()`：CLI 友好输出。
- **Production 环境强制要求 credentials**，否则抛错。
- `redline` 阶段失败 → `RuntimeError("TECH_REDLINE_BLOCKED: ...")`。

#### 3.11.2 持久化契约

- 检查点文件：`{run_id}.checkpoint.json` 在 `checkpoint_dir` 下。
- 运行记录：`{run_id}.json` 含完整 `parameter_audit` 快照。
- 历史分析 schema：`run_history_analytics.v1`。

---

### 3.12 基础底座

#### 3.12.1 `models.py`（90 行）

3 个核心 dataclass：
- `Candidate`（24 字段：`alpha_id, expression, family, hypothesis, data_fields, operators, source_tags, parent_id, mutation_type, dataset_id, template_source, local_quality, validation, simulation_id, official_alpha_id, official_metrics, scorecard, gate, submission, alpha_output_config, quality_diagnosis, lifecycle_status, created_at, extra_fields`）
- `PipelineEvent`（`event, message, alpha_id, level, data, timestamp`）
- `PipelineResult`（`run_id, candidates, events, summary`）
- 工具：`utc_now()` / `new_id(prefix)`

#### 3.12.2 `errors.py`（210 行）

`AppError` 体系：
- `ValidationError(400)` / `AuthError(400)` / `SubmitBlockedError(400)` / `MissingOfficialIdError(400)`
- `ConflictError(409)` / `NotFoundError(404)` / `SessionError(403)` / `OriginForbiddenError(403)` / `ContextRefreshError(500)`

`ErrorInfo`（frozen）：`error_code, category, message, error_type, retryable, status_code, retry_after`

`classify_error(exc, default_code)`：基于文本模式 + 类别映射（AUTH/SESSION/ORIGIN → auth；VALIDATION/MISSING/PARSE/JSON → validation）

#### 3.12.3 `redaction.py`（308 行）

- **30+ 敏感 key**：`access_token, address, api_key, authorization, cookie, csrf, email, password, phone, refresh_token, secret, session, token, username, …`
- `redact_text(value, max_length=None)`：应用 4 个正则（EMAIL / AUTH / KEY_VALUE / SECRET_FRAGMENT）
- `redact_data(data, key_fragments, redacted_keys, max_depth=64)`：递归 + `seen` 集合防环
- `_is_sensitive_key` 后缀白名单：`_available / _type / _status / _source / _enabled / _present` 不脱敏
- `SHARED_REDACTION_FIXTURE_CORPUS` 7 个测试 fixture

#### 3.12.4 `runtime_constants.py`（206 行）

5 组常量：
- `WebDefaults`：HOST=127.0.0.1 / PORT=8765 / MAX_BODY_BYTES=2MB / TASK_EXECUTOR_MAX_WORKERS=4 / SSE_PUSH_INTERVAL=1.0s / MAX_SSE_DURATION=600s
- `SnapshotDefaults`：15 个数值阈值
- `CloudDefaults`：CLOUD_SYNC_STALE_SECONDS=86400 / CONTEXT_CACHE_TTL_SECONDS=86400
- `AgentLimits`：MAX_TOOL_CANDIDATES=100 / MAX_SYNC_RANGE={1d,3d,7d,all} / MAX_BATCH_SIMULATIONS=10 / MAX_BATCH_SIMULATION_WORKERS=3
- `RepositoryDefaults`：LOCK_STALE_SECONDS=120 / EXPRESSION_INDEXED_FILES / REPOSITORY_JSONL_FILES
- `ScoringDefaults`：DEFAULT_SUBMIT_THRESHOLD=85.0 / OPTIMIZE=70.0 / RESEARCH=50.0
- `PipelineDefaults`：MAX_CANDIDATES_PER_CYCLE=20 / MAX_SIMULATIONS_PER_CYCLE=3 / CONVERGENCE_STALL_CYCLES=5

#### 3.12.5 `config_schema.py`（80+ 行）

`RUN_CONFIG_SCHEMA`（JSON Schema draft 2020-12）：
- 必填：`environment="production"` / `auto_submit` / `credentials` / `web` / `ops`
- `credentials`：`username/password/token` + `_env` 变体
- `web`：`host / port / open_browser / session_ttl_seconds / allow_multiple_sessions / allow_remote / secure_cookies / admin_token_env`
- 所有 enum 来自 `brain_api.canonical`（SSOT）

#### 3.12.6 配置层有 2 套并行模型

- `brain_alpha_ops/config_models.py` 提供 `RunConfig`/`OpsConfig`/`QualityThresholds` 等 dataclass
- `brain_alpha_ops/config_schema.py`（17KB）和 `brain_alpha_ops/config/_loader.py` 用 jsonschema
- 两者并存：`config_models.py` 是真值源，`config_schema.py` 是验证镜像
- `config/__init__.py` 重新导出 18+ 符号

#### 3.12.7 `web_jobs.py` / `web_async_jobs.py` / `web_run_job.py`

- `web_jobs.py`（80+ 行）：模块全局 `ASYNC_JOBS: dict` + `ASYNC_JOBS_LOCK = threading.RLock()`，持久化到 JSONL
  - `_ASYNC_JOB_MAX_AGE_SECONDS=3600` / `_ASYNC_JOB_MAX_COUNT=200`
  - `set_jobs_storage_dir(storage_dir)` / `_persist_job_to_jsonl(row)`

- `web_run_job.py`（80+ 行）：`run_guided_job_service(job_id, payload, *, job_store, run_config_from_payload, compute_run_stats, safe_error_message, log)` — **全依赖注入**
  - 连接 `GuidedPipeline` 与 `JobStore`
  - `stop_callback=lambda: job_store.is_cancelled(job_id)`
  - `_progress_cb(phase, status, data)` 实时更新 job_store

---

### 3.13 `runner.py`（28 行）

极简两函数：
- `api_from_run_config(run_config)`：验证 + 凭证解析 + `OfficialBrainAPI` 实例化
- `run_pipeline_from_config(config_path, ...)`：实例化 `AlphaResearchPipeline` 并执行

---

### 3.14 CLI 入口

- **`web_cli.py`（95 行）**：从原 `web/__init__.py` 抽出（>800 行被拆）
  - `serve(port, open_browser, host, ...)` / `shutdown_server()` / `smoke_test_server()`
  - `main(argv, ...)` CLI：`--port` / `--host` / `--no-browser`
  - **副作用**：`serve()` 内部 `ensure_global_monitor()` 自动启动 StallMonitor
  - 模块级单例 `_SERVER`

- **`launch_web.py`（11 行）**：CLI 入口，转发到 `web.main(argv)`

---

## 4. 真实 Bug 与改进点（详细）

### 4.1 P0 — `web_http_handler.py:94-112` 双重 `end_headers`

**事实**（已在昨天的工作笔记中记录，今天再次验证 `Read` 第 94-112 行）：

```python
# web_http_handler.py:94-112
def _send_json(self, payload, status=200, *, extra_headers=None):
    import json as _json_module
    body = _json_module.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    self.send_response(status)
    self.send_header("Content-Type", "application/json; charset=utf-8")
    self.send_header("Content-Length", str(len(body)))
    if extra_headers:
        for name, value in extra_headers:
            self.send_header(name, value)
    self.end_headers()           # ← 第一次 end_headers
    self.wfile.write(body)       # ← 第一次写 body
    self.send_header("Access-Control-Allow-Methods", ...)   # ← end_headers 之后再 send_header
    self.send_header("Access-Control-Allow-Headers", ...)
    self.send_header("Access-Control-Allow-Credentials", "true")
    self._send_security_headers()
    self.end_headers()           # ← 第二次 end_headers
```

**Python `BaseHTTPRequestHandler` 不允许在 `end_headers()` 后再调用 `send_header`/`end_headers`**。`wfile.write()` 在第二次 end_headers 之前会先于第二次 end_headers 落空 header 块，第二次 send_header 实际写到下个响应头时会被读不到。

**当前状态**：该路径未被实际使用（`web/__init__.py:556-624` 的内联 `_send_json` 是生产路径，它**没有**这个 bug），所以是 latent bug。任何把 handler 工厂换为主分发器的改动都会瞬间触发。

**影响**：
- 一旦启用：第二个响应（极少见，比如在 100-continue 之后）会包含 `Access-Control-Allow-*` + security headers，但**当前 body 已写完**，那些 header 会泄漏到下一个响应；客户端可能看到 CORS 错误。
- 修复方案：去掉 CORS 头重复（已在 `_send_security_headers` 内部发送），或合并到 `extra_headers`。

### 4.2 P0 — 提交路径"双重防线"实际只一道

**事实**：
- `web/__init__.py:341-357` `_submit_disabled_payload()` 返回固定阻断
- `web/__init__.py:556-624` `dispatch_post` 14 个真实后端路由里 `/api/submit`、`/api/submit_batch` **直接**调 `_submit_disabled_payload()`
- `web_handler_dispatch.py:759-768` 的 `_post_submit()` 同样返回 `REAL_SUBMIT_DISABLED_WEB_FLOW`
- `web_submission_single.py:31` 的 `submit_candidate_payload()` 是**真实现**（会真正调 `api.submit_alpha`）

**问题**：
- 没有"不可移除的常量" `REAL_SUBMIT_DISABLED = True` 之类把这个约束写进不可移除层
- 如果有人改 `web/__init__.py:341-357` 或 `web_handler_dispatch.py:759-768` 中那两行（删掉 `return _submit_disabled_payload()`），真提交就会重新打开
- 任何 LLM 触发的代码修改、refactor、cleanup 都有可能误删这两行

**改进建议**：
1. 在 `runtime_constants.py` 添加 `REAL_SUBMIT_DISABLED_WEB_FLOW = True` 模块级常量
2. 在 `web_submission_single.py:31` 顶部加 `if runtime_constants.REAL_SUBMIT_DISABLED_WEB_FLOW: return _submit_disabled_payload()`
3. 把这条常量写入 `compliance/` 红线（新增 **RL7**：`web_submission_*` 永不调真 API）

### 4.3 P1 — Web 提交"双重防线"实际只一道已部分缓解

昨天报告中的"当前线上 handler 不发 CSP"在今天仍然成立：`web/__init__.py:631` 的内联 `Handler._send_json` 不会发 CSP（因为没有 `_send_security_headers` 调用），而 `web_http_handler.py:270-277` 的 `_send_security_headers` 才有 CSP。

**事实**：
- 生产路径走内联 handler，无 CSP
- 工厂 handler 才有 CSP，但 latent bug 让它不能上线

**改进**：
- 把内联 handler 改为调用 `web_http_handler._send_security_headers`
- 或合并两条路径到唯一一条

### 4.4 P1 — 资源泄漏（`daemon=False`）

`web/__init__.py:143` `_run_generate_candidates_job` 启动用 `daemon=False`：

```python
thread = threading.Thread(target=_run_generate_candidates_job, args=(job_id, dict(payload or {})), daemon=False)
thread.start()
```

**问题**：
- `daemon=False` 意味着 Python 进程退出时不会杀线程
- 启动器 `web_cli.py:serve()` 没有 `join()`，会留 zombie
- 长时间跑会累积 zombie 线程，泄漏文件描述符

**改进**：`daemon=True`（默认是 False，应该显式设 True）

### 4.5 P1 — `hypothesis_driven_generator.py` 1325 行 god module

**事实**：
- 单文件 1325 行
- 含 5 个类：`HypothesisDrivenGenerator` / `GenerationModeRouter` / `HypothesisSelector` / `ExpressionFamilySelector` / `FieldSelector` / `ContextAdapter`
- 任一处修改都影响整个生成器

**改进**：
- 拆为 `hypothesis_driven_generator.py`（主类）+ `hypothesis_selector.py` + `expression_family_selector.py` + `field_selector.py` + `context_adapter.py` + `generation_mode_router.py`

### 4.6 P1 — `local_backtest_engine.py` 1148 行 god module

类似问题，拆分为 `local_backtest_config.py` / `local_backtest_runner.py` / `local_backtest_metrics.py` / `local_backtest_results.py`

### 4.7 P1 — `web_runtime_facade.py` 抽象冗余（781 行）

**事实**：
- `web_runtime_facade.handler_dispatch_context(web)` 构造 80+ 字段 dataclass
- 但生产路径走的是 `web/__init__.py:556-624` 的内联 `dispatch_get/post`
- `web_handler_dispatch` + facade 在生产路径上是"未来路径"

**改进**：
- 决定走哪条：要么把内联 dispatch 替换为 `web_handler_dispatch._dispatch_route`（要先修 `web_http_handler.py:94-112` bug），要么删掉 facade 三元组
- 同步更新 `web_routes.py` 的 875 行路由表

### 4.8 P1 — `web_handler_dispatch.py` 1094 行

- 8 个 import、80+ 字段绑定、fallback 到旧 `web.dispatch_post`（109-112 行）
- 路由分发+回退双层

**改进**：拆分为 `web_handler_dispatch_core.py`（分发循环）+ `web_handler_dispatch_get.py`（GET handlers 字典）+ `web_handler_dispatch_post.py`（POST handlers 字典）

### 4.9 P2 — `web/__init__.py` 是 821 行的胶水层

**事实**：
- 直接调 9 个 `_real_*` 业务函数（`run`/`check`/`submit`/`generate`/`score`/`connection`/`attribution`/`stop`/`session`）
- 70+ 个 `globals().update()` 的 facade 注入
- `_install_facade_bindings()` 在 import 时执行（行 812）

**改进**：
- 把 `_real_*` 业务函数下放到独立模块（`web_run_real.py` / `web_check_real.py` ...）
- 用 `__getattr__` 懒加载代替 eager `globals().update()`

### 4.10 P2 — 4 套不同状态分类共存

| 来源 | 集合 |
|------|------|
| `web_state_contract.classify_job_status` | 6 种 `status_kind`：`active`/`success`/`warning`/`failed`/`interrupted`/`missing`/`idle`/`unknown` |
| `web_get_handlers._job_payload` | 自定义分类 |
| `tasks.ACTIVE_STATUSES` / `TERMINAL_STATUSES` | `ACTIVE = {queued, pending, starting, running, stopping}` / `TERMINAL = {completed, completed_with_warnings, failed, stopped, cancelled, canceled}` |
| `research/contracts.ACTIVE_BACKTEST_STATUSES` / `TERMINAL_BACKTEST_STATUSES` | `ACTIVE = {SUBMITTED, RUNNING, PENDING, POLLING, ...}` / `TERMINAL = {COMPLETED, FAILED, ERROR, ...}` |

**问题**：状态机散落，漂移风险。改进：在 `tasks.py` 或新建 `core_state.py` 集中所有状态枚举。

### 4.11 P2 — 退避策略（线性 + 全局变量污染）

- 退避：`base_seconds * (attempt + 1)`（**非指数**）
- 全局变量污染：`_GLOBAL_LAST_REQUEST_AT + _GLOBAL_TIMESTAMP_LOCK` 跨实例共享

**改进**：
- 退避改指数 + jitter：`base * 2^attempt * (0.5 + random()/2)`
- 移除非必要的全局共享（用 per-instance 配置即可）

### 4.12 P2 — 死代码 `OfficialExpressionValidationMixin`

`brain_api/official.py` 实际只挂 4 个 mixin（auth/context-data/request/simulation），`OfficialExpressionValidationMixin` 写完未挂载。

**改进**：删除。

### 4.13 P2 — 重复代码（3 处复制）

`_USER_ALPHA_TRANSIENT_*` 常量在 `official_alphas.py:40-50` + `official_context.py:43-53` + `official_helpers.py` 三处字符级重复。

**改进**：上提 `user_alpha_transient.py`。

### 4.14 P2 — 并发策略不一致

`parallel_backtest.py` 真正多线程；`batch_backtest_coordinator.py` 同步纯函数（`max_workers` 是元数据）。同一概念"并行回测"两个不同实现。

**改进**：统一入口；`batch_backtest_coordinator` 也用 `ThreadPoolExecutor`。

### 4.15 P3 — `submission_preflight_error` 命名不一致

`web_submission_safety.py:99` 同时存在 `submission_preflight_error` 和别名 `submission_preflight_error_message`。

**改进**：去掉旧名。

### 4.16 P3 — `KnowledgeBase` 写无锁

`knowledge_base.py` 用 `data/knowledge_base/{rules,findings,failures}/*.json`，`Repository` 有文件锁，`KnowledgeBase` 没有。

**改进**：增加 `threading.RLock`。

### 4.17 P3 — SQLite 启动全量重建

`expression_sqlite_index.py` 启动时 `DELETE + INSERT`，每次冷启重建全部索引，无 WAL/timeout。

**改进**：用 WAL 模式 + 增量更新；大表分批 commit。

### 4.18 P3 — LLM 无 quota

`llm_review.py` 没有 rate-limit / token quota，失败可能快速耗尽 token。

**改进**：添加 `LLMCallLedger` + token 预算 + 重试退避。

### 4.19 P3 — 协议不强制

`shared/contracts.py` 5 个 `@runtime_checkable` Protocol 是 Duck typing 而非 ABC。

**改进**：用 ABC 替代或加 `isinstance(x, Protocol)` 显式检查。

### 4.20 P3 — 反射破坏类型

`bind_runtime_state_properties` 反射属性赋值，`pipeline_state.py` 中动态 `setattr` 破坏 mypy/IDE。

**改进**：改为显式 dataclass。

---

## 5. 完整 Schema 版本清单

| Schema | 来源 |
|--------|------|
| `lifecycle_record.v1` | `research/contracts.py` |
| `backtest_record.v1` | `research/contracts.py` |
| `assistant_guidance_record.v1` | `research/contracts.py` |
| `strategy_lifecycle_record.v1` | `research/contracts.py` |
| `release_score_gate.v1` | `scoring/release_score_gate.py` |
| `parameter_audit_snapshot.v1` | `parameter_audit.py` |
| `observability.v1` | `observability.py` |
| `e2e_artifact_summary.v1` | `e2e_report.py` |
| `diagnostic_snapshot.v1` | `production_diagnostics.py` |
| `live_submit_readiness.v1` | `live_submit_readiness_assessment.py` |
| `submission_readiness.v1` | `submission_readiness.py` |
| `run_history_analytics.v1` | `ux/history.py` |
| `scoring-comparison.v1` | `scoring/scoring_comparison.py` |
| `redline_report.v1` | `compliance/redline_models.py` |
| `web_run_record.v1` | `ux/guided_storage.py` |
| `guarded_pipeline_checkpoint.v1` | `ux/guided_storage.py` |
| `error_knowledge.v1` | `error_knowledge.py` |

---

## 6. 核心调用链（端到端）

```
MCP client ──stdin──▶ mcp_server.handle_request
                              │
                              ▼
                BrainAlphaToolbox.call(name, args)
                              │ (resolve alias)
                              ▼
              agent_research_tools / agent_live_tools handlers
                              │ (live API)
                              ▼
                OfficialBrainAPI (brain_api/official.py)
                              │
                              ▼
                       run_pipeline_from_config (runner.py)
                              │
                              ▼
                  AlphaResearchPipeline (research/pipeline.py)
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
   RedLineVerifier    CandidateGenerator    OfficialValidationService
   (compliance/*)     (research/generator)  (research/official_validation)
                              │
                              ▼
                  OfficialScoringSystem.evaluate
                              │
                              ▼
                  release_score_gate.decide_release
                              │
                              ▼
                  live_submit_readiness.assess_candidate
                              │
                              ▼
                  submission_readiness.submit_readiness_hard_gate
                              │
                              ▼
                        submit_alpha (live API)
                                  │
                                  ▼
                            （Web 端被 _submit_disabled_payload 拦截）
```

---

## 7. 关键架构特征总结

### 7.1 优点

1. **协议抽象清晰**：`shared/contracts.py` 用 `typing.Protocol` 解耦 JobStore / EventPublisher / CloudCache
2. **SSOT 严格执行**：`brain_api/canonical.py` 的 10 阈值 + 14 路径 + 12 指标名是全代码库唯一真源
3. **Schema 版本化**：24+ 独立 schema 版本（`scoring-comparison.v1`, `release_score_gate.v1`, `parameter_audit_snapshot.v1` 等）
4. **三层安全护栏（live API）**：`allow_live_api` + `confirm_live_api` + `_duplicate_live_expression_block`
5. **Fail-closed 哲学**：JobStore 启动恢复、submission_readiness 硬门、Live API 入口、StallMonitor 自动中断
6. **零偏差目标**：`api_output_deviation == 0.0` 作为评分对齐 BRAIN 官方输出
7. **DDD bounded context 干净**：`domains/*` 5 个文件都 < 6 行
8. **工具层与协议层解耦**：`agent_tool_registry`（纯元数据）vs `agent_tools`（行为）双层
9. **子模块高内聚低耦合**：`web_candidate_*` 业务子模块纯函数化（依赖通过 Callable 参数传入）
10. **测试友好**：209 个测试文件 + 40 脚本，1:1 覆盖率密度合理

### 7.2 风险

1. **god module 集中**：`research/` 6+ 个 700+ 行模块，最高达 1325 行
2. **入口文件膨胀**：`web/__init__.py` 821 行 + 90+ 个 facade/bindings 文件
3. **P0 真实 bug**：`web_http_handler.py:94-112` 双重 `end_headers`（latent）
4. **P0 安全弱点**：Web 提交"双重防线"实际只一道，无不可移除常量
5. **P1 安全特性未生效**：当前生产 Handler 不发 CSP
6. **P1 资源泄漏**：`daemon=False` 线程 + 无 `join()`
7. **P2 抽象冗余**：`web_runtime_facade.py` 781 行构造 80+ 字段 dataclass 但生产路径不经过
8. **P2 抽象泄漏**：`web/__init__.py` 821 行胶水层直接调 9 个 `_real_*` 业务函数
9. **P2 状态机散落**：4 套不同状态分类共存，漂移风险
10. **P2 重复代码**：`_USER_ALPHA_TRANSIENT_*` 常量在 3 处字符级重复
11. **P2 退避策略**：线性退避 + 全局变量污染
12. **P2 死代码**：`OfficialExpressionValidationMixin` 未挂载
13. **P2 并发策略不一致**：`parallel_backtest.py` vs `batch_backtest_coordinator.py` 两个不同实现
14. **P3 `KnowledgeBase` 写无锁**
15. **P3 SQLite 启动全量重建**（DELETE + INSERT，无 WAL/timeout）
16. **P3 LLM 无 quota**（rate-limit / token quota）
17. **P3 协议不强制**：`@runtime_checkable` 是 Duck typing 而非 ABC
18. **P3 反射破坏类型**：`bind_runtime_state_properties` 动态 setattr

### 7.3 设计模式总结

- **Registry 模式**：`agent_tool_registry.ToolRegistry` + frozen `ToolDefinition`
- **Strategy 模式**：`TaskExecutor` 抽象 + `Thread/Process/Adaptive` 三实现
- **Mixin 模式**：`BrainAlphaToolbox(AgentLiveToolsMixin)` 按能力组合
- **State Machine 模式**：JobStore 的 ACTIVE/TERMINAL 状态集
- **Adapter 模式**：`mcp_server.py` 把 toolbox 适配为 JSON-RPC 2.0
- **Facade 模式**：`domains/*` 5 个薄 re-export
- **Template Method 模式**：`GuidedPipeline` 10 阶段骨架
- **Protocol Duck Typing**：`shared/contracts.py` 5 个 `@runtime_checkable`
- **Spec/Snapshot 模式**：`parameter_audit_snapshot` + `RunHistoryAnalytics`
- **Guard 模式**：`live_api_blocked` + `_duplicate_live_expression_block` + `submission_readiness_hard_gate`
- **Decorator 模式**：`rejection + redaction + compaction` 在 `_job_safe` 串联
- **Singleton 模式**：`_DEFAULT_TOOL_REGISTRY` / `_SERVER` / `ASYNC_JOBS` / global StallMonitor
- **Protocol/Facade 分离**：`BrainAPI(Protocol)` + `OfficialBrainAPI`（concrete）
- **Bounded Context**：5 个 `domains/*.py` < 6 行 re-export

---

## 8. 建议优先级（30 / 60 / 90 天）

### 立即（0-7 天）

1. **修复 `web_http_handler.py:94-112` P0 bug**：去掉重复的 `end_headers` + CORS header。
2. **提取 `REAL_SUBMIT_DISABLED_WEB_FLOW` 常量**到 `runtime_constants.py`，并在 `web_submission_single.py:31` 顶部检查。
3. **`daemon=False` → `daemon=True`**：`web/__init__.py:143`。

### 短期（1-2 周）

4. **统一生产路径**：决定走内联 dispatch 还是 `web_handler_dispatch._dispatch_route`；删掉不用的。
5. **拆分 `hypothesis_driven_generator.py` 1325 行**：5 个类拆到独立文件。
6. **拆分 `local_backtest_engine.py` 1148 行**：4 个职责独立。
7. **拆 `web_handler_dispatch.py` 1094 行**：核心 + GET 字典 + POST 字典。
8. **上提 `_USER_ALPHA_TRANSIENT_*`** 到 `user_alpha_transient.py`。

### 中期（2-4 周）

9. **拆分 `web/__init__.py` 821 行**：把 9 个 `_real_*` 业务函数下放到 `web_*_real.py`。
10. **CSP 注入到生产 Handler**：把内联 `_send_json` 改为调用 `web_http_handler._send_security_headers`。
11. **退避策略改指数 + jitter**：`base * 2^attempt * (0.5 + random()/2)`。
12. **死代码清理**：`OfficialExpressionValidationMixin` 删除。
13. **状态机集中**：所有状态枚举放到 `core_state.py`。
14. **统一并发**：`batch_backtest_coordinator` 改用 `ThreadPoolExecutor`。

### 长期（1-3 月）

15. **SQLite WAL 模式 + 增量更新**。
16. **KnowledgeBase 写加锁**。
17. **LLM token quota** + `LLMCallLedger`。
18. **Protocol → ABC**：`shared/contracts.py` 用 ABC 替代 `@runtime_checkable`。
19. **`bind_runtime_state_properties` → 显式 dataclass**。
20. **配置层 2 套模型合并**：`config_models.py` + `config_schema.py` 合并为单一真值源。

---

报告完毕。
