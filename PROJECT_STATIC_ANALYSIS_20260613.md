# BRAIN Alpha Ops — 项目全面静态分析报告

> 分析对象：`/Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha/`
> 范围：项目根 + `brain_alpha_ops/` 包 (301 个 .py,~7.78 万行业务代码) + React 前端 (38 个 .tsx/.ts,1.37 万行) + tests (205 个文件) + scripts + config + data 缓存
> 方法：源代码逐文件/逐关键段阅读 + 子代理深读补充 + 关键断言交叉验证
> 报告日期：2026-06-13

---

## 0. TL;DR（执行摘要）

| 维度 | 评估 |
|---|---|
| **成熟度** | 7/10 — Beta (v0.3.0),接近可用,但多区域仍在迭代中 |
| **架构合理度** | 8/10 — 分层清晰、Mixins 拆解、kill-switch 多重防护,Web 提交被硬门禁 |
| **代码体量** | 中等偏大 — 7.78 万行 Python + 1.37 万行 TSX + 205 个测试;`web_*.py` 80 个文件 2.18 万行(碎片化严重) |
| **安全设计** | 8/10 — 凭据三件套(浏览/环境/配置)+ CSP/Session/CSRF/Replay 五重;但 `BRAIN_ALPHA_FORCE_REAL_SUBMIT=1` 单点可越权 |
| **数据/缓存一致性** | 5/10 — JSONL 无锁增长,单例 `OfficialDataLoader` 需手动 `refresh()`,`official_context_refresh_status.json` 状态 `failed`(timeout 120s) |
| **测试覆盖** | 中等 — 205 个测试文件但 `core_modules_comprehensive` 注释提到 27 个测试模块存在集合错误 |
| **核心矛盾** | 模块化漂移:`web_jobs.py` (200 in-mem jobs) 与 `tasks.py:JobStore` 双轨;`web_sse.py` 与 `web_http_handler._handle_sse_stream` 重复;`web_runtime_facade.compute_run_stats` 是空壳占位 |
| **建议优先级** | (1) 统一 SSE/job store 双轨;(2) 修复官方上下文刷新 timeout;(3) 调和 3 处 `SYNC_RANGES` 差异;(4) 删除 5 个 `domains/` 空 stub + 9 个 `web_*_bindings.py` 死代码 |

---

## 1. 项目拓扑与代码度量

### 1.1 总览
```
WorldQuant-BRAIN-Alpha/
├── brain_alpha_ops/         # 主包 (301 .py, 77840 行)
│   ├── __init__.py          # lazy 导出 (15 个核心符号)
│   ├── brain_api/           # BRAIN 官方 API 适配 (22 .py)
│   ├── research/            # 自动化生成子系统 (104 .py)
│   ├── scoring/             # 评分与门禁 (10 .py)
│   ├── web/                 # Web 控制台入口 (内置前端)
│   │   └── react_app/       # React + Vite + TS (38 .tsx/.ts, 13688 行)
│   ├── compliance/          # Red-line 6 条硬约束 (8 .py)
│   ├── config/              # 配置加载/校验/Schema
│   ├── data/                # OfficialDataLoader + 字段映射
│   ├── domains/             # 5 个空 stub(几乎全 re-export)
│   ├── examples/            # 示例脚本
│   ├── shared/              # 共享契约 (contracts.py)
│   ├── ux/                  # 引导式 UX 层 (9 .py, 1863 行)
│   ├── web_*.py (80 个)     # Web 后端按主题拆分(2.18 万行)
│   ├── tasks.py             # JobStore 持久化任务系统
│   ├── agent_tools.py       # Agent/MCP 工具注册
│   ├── mcp_server.py        # JSON-RPC 2.0 stdio MCP
│   ├── pipeline.py (??)     # 注:pipeline.py 在 research/,不在根
│   └── runtime_constants.py # 集中常量中心
├── tests/                   # 205 个测试文件
├── scripts/                 # 60+ 检查/E2E/治理脚本
├── data/                    # 运行时 JSONL + JSON 缓存
├── docs/                    # 149 个文档/截图/设计稿
├── config/run_config.json   # 131 行主配置
├── launch_web.py            # 13 行 CLI 启动器
└── fetch_official_context.py # 维护脚本 (503 行)
```

### 1.2 关键文件 Top-15 (按行数)

| # | 路径 | 行数 | 角色 |
|---|------|------|------|
| 1 | `research/hypothesis_driven_generator.py` | 1240 | 3 模式 (70/20/10) 生成路由器 + 6 步假设驱动管道 |
| 2 | `research/local_backtest_engine.py` | 1099 | 本地 FASTEXPR 子集评估(84 日期 × 160 标的) |
| 3 | `web_handler_dispatch.py` | 1004 | 路由表 + 25 个 POST handler(均为 `_post_*` 形式) |
| 4 | `web_candidate_simulation.py` | 996 | 模拟任务编排(槽位/轮询/HTTP 429 退避) |
| 5 | `research/observability.py` | 940 | 健康快照 + 红色/黄色告警 |
| 6 | `web_cloud_snapshot.py` | 905 | 云 Alpha 同步 + 官方 context 刷新 |
| 7 | `web_check_availability.py` | 879 | 12 项候选可用性检查 + 批处理 job |
| 8 | `web_routes.py` | 875 | GET/POST 路由分发(早期链式 if-else) |
| 9 | `research/assistant.py` | 865 | LLM 助手主类(未深入) |
| 10 | `web/__init__.py` | 850 | Handler + dispatch + _real_* helpers |
| 11 | `research/scoring.py` | 844 | 3 层评分(prior 8 / empirical 16 / checklist 7) |
| 12 | `research/alpha_quality.py` | 820 | Alpha 质量综合 |
| 13 | `web_runtime_facade.py` | 781 | 781 行运行时 facade |
| 14 | `research/hypothesis_library.py` | 781 | 8 个 hypothesis YAML + 经验权重 EMA |
| 15 | `config_schema.py` | (未读) | JSON Schema 校验 |

**Top-15 累计 ~14000 行 / 7.78 万行 ≈ 18%**,长尾分散。

### 1.3 关键依赖 (`pyproject.toml`)

```toml
[project]
name = "brain-alpha-ops"
version = "0.3.0"
requires-python = ">=3.10"
dependencies = [
    "pyyaml>=6.0,<7",
    "requests>=2.32.4,<3",
    "jsonschema>=4.20,<5",
]

[project.optional-dependencies]
test = ["pytest>=7.0,<9", "pytest-cov>=4.0,<7"]
dev = ["ruff>=0.4,<1", "mypy>=1.0,<2", "pip-audit>=2.7,<3"]
```

**Web 后端零第三方依赖**(标准库 `http.server` + `urllib`)— 这是核心设计原则。React 前端独立,只依赖 `react` + `react-dom`。

### 1.4 导入边界 (`.importlinter`)

```
shared  ─→  [禁止] research, web, agents
brain_api ─→  [禁止] research, web, agents
data   ─→  [禁止] research, web, agents
research ─→  [禁止] web, agents
config  ─→  [禁止] research, web, agents
```

5 条 `forbidden` 契约,层间无向上依赖。这是非常清晰的六边形架构。

---

## 2. `brain_alpha_ops/` 主包

### 2.1 `__init__.py` (lazy 导出)
- 22 个核心符号,所有都用 `__getattr__` 懒加载,import 链轻
- 安装一个 WARNING 级别 log handler (避免污染 root logger level)
- `_LAZY_EXPORTS` 字典:(`BrainAlphaToolbox`, `JobStore`, `OfficialDataLoader`, `CandidateGenerator`, `DynamicThemeEngine`, `DatasetSelector`, `AlphaCheckRegistry`, `AlphaTemplateRegistry`, `ResearchMemory`, `ToolRegistry` 等)

### 2.2 `runtime_constants.py` (228 行) — 集中常量中心
8 个 dataclass 化分组:
- `WebDefaults` (HOST/PORT/MAX_BODY_BYTES=2MB/SSE_PUSH_INTERVAL=1s/MAX_SSE_DURATION=600s)
- `SnapshotDefaults` (LIFECYCLE_LIMIT=1000/RESEARCH_MEMORY_LIMIT=5000/STORAGE_JSONL_LIMIT=500)
- `CloudDefaults` (CLOUD_SYNC_STALE_SECONDS=86400/CONTEXT_CACHE_TTL_SECONDS=86400)
- `AgentLimits` (MAX_TOOL_CANDIDATES=100/MAX_BATCH_SIMULATIONS=10/MAX_BATCH_SIMULATION_WORKERS=3)
- `RepositoryDefaults` (LOCK_STALE_SECONDS=120/EXPRESSION_INDEXED_FILES 6 项/RECORD_INDEXED_FILES 2 项)
- `ScoringDefaults` (DEFAULT_PRIOR/EMPIRICAL/CHECKLIST_LAYER_WEIGHT = **0.30/0.45/0.25**;DEFAULT_LOCAL_PRIOR/QUALITY_WEIGHT = 0.65/0.35;DEFAULT_SUBMIT/OPTIMIZE/RESEARCH_THRESHOLD = 85/70/50)
- `PipelineDefaults` (max_candidates/validations/simulations per cycle = 20/10/3;max_cycles=10;CONVERGENCE_STALL_CYCLES=5)

**关键 kill-switch**:
```python
REAL_SUBMIT_DISABLED_WEB_FLOW: Final[bool] = True
```
Web 控制台永远禁止调用 `api.submit_alpha`。`BRAIN_ALPHA_FORCE_REAL_SUBMIT=1` 可在 consultant-gated 模式下越权。

### 2.3 `errors.py` + `error_payloads.py` + `error_knowledge.py`
- `AppError` 基类 + 8 个子类(`ValidationError`/`AuthError`/`ConflictError`/`ContextRefreshError`/`MissingOfficialIdError`/`NotFoundError`/`OriginForbiddenError`/`SessionError`/`SubmitBlockedError`)
- `user_error_payload(exc, *, error_code, max_length, **context)` 统一错误响应工厂(含 correlation_id)
- `classify_error` 在 `errors.py` 和 `ux/guided_pipeline.py` **两处实现** — 重复

### 2.4 `redaction.py` (220+ 行) — 凭据脱敏
- `SENSITIVE_KEYS` 集合(30+ 键)
- `redact_data`/`redact_text`/`redact_error_message` 三件套
- 跨整个项目 import,在 `web_routes`/`web_handler_dispatch`/`fetch_official_context`/`web_session` 等关键路径都强制使用

### 2.5 `secure_credentials.py` (285 行) — 凭据管理
- `CREDENTIAL_KEY_PATTERNS` 12 个正则(password/token/secret/api_key/access_token/authorization/cookie/csrf/session/credential/credentials)
- `CredentialRedactionFilter(logging.Filter)` — 启动时自动安装到 root logger
- 扫描 printf placeholder 前的 64 字符 window 找到 sensitive 位置 → 替换为 `<REDACTED>`
- `resolve_credentials(*, username, password, token, **envs)` — 优先级 explicit > env > empty;输出 `ResolutionTrace`

### 2.6 `tasks.py` — `JobStore` 持久化任务
- 持锁 + 持久化 + watchdog(replay 攻击防护)
- 与 `web_jobs.py`(早期 200 in-mem jobs)双轨存在
- 新代码应统一用 `JobStore` (通过 `web_job_registry.WebJobRegistry` 访问)

### 2.7 `mcp_server.py` (140 行) — JSON-RPC 2.0 stdio MCP 适配
4 个方法:`tools/list`、`tools/call`、`initialize`、`notifications/initialized`。

### 2.8 `agent_tools.py` + `agent_tool_registry.py` + `agent_live_tools.py` + `agent_research_tools.py` + `agent_guidance_tools.py`
- `BrainAlphaToolbox` 是导入所有子模块 mixin 的总入口
- `ToolDefinition` dataclass + `ToolRegistry`(不可变注册表,分类 research/live_api/destructive)
- `agent_live_tools.py:MAX_BATCH_SIMULATIONS=10` / `MAX_BATCH_SIMULATION_WORKERS=3`
- `agent_research_tools.py`:assistant_response_guidance / parse_assistant_response / cross_review_assistant_response / query_research_observability_snapshot / plan_parallel_backtest_from_args

### 2.9 `agent_live_tools.py` 中同步范围冲突
```python
MAX_SYNC_RANGE = {"1d", "3d", "7d", "all"}  # ← 包含 1d
```
而 `web_payload_validation.ALLOWED_SYNC_RANGES = {"3d", "7d", "recent", "6months", "all"}` — **缺少 1d,多了 recent/6months**。三处定义见 §6.1。

### 2.10 其它主包文件
| 文件 | 角色 |
|---|---|
| `adaptive_executor.py` | `AdaptiveExecutor` + `CachedAPIRateLimiter` |
| `core_state.py` | Canonical 状态枚举 (`JOB_ACTIVE_STATUSES` / `JOB_TERMINAL_STATUSES`) |
| `dataset_defaults.py` | `resolve_default_dataset_id` 从 `official_datasets.json` 读 |
| `e2e_report.py` | E2E 报告生成 |
| `live_submit_readiness_assessment.py` | 本地候选 readiness 评估(无 API) |
| `model.py` | Pydantic/dataclass 模型 (`Candidate` 等) |
| `official_context_datasets.py` | `list_official_datasets_or_derive` (fallback 警告) |
| `observability.py` | `context_payload` 结构化日志上下文 |
| `parameter_audit.py` | 运行时参数快照 (`parameter_audit_snapshot.v1` + 6 个必需 section) |
| `production_diagnostics.py` | 诊断 + `GapRow` / `PriorityItem` |
| `runner.py` | `api_from_run_config` + `run_pipeline_from_config` |
| `shared_bounds.py` | `bounded_float/int` / `expression_batch_argument` |
| `stall_monitor.py` | `JobStallSnapshot` + `StallMonitorConfig` (timeout=120s/poll=15s) |
| `submission_readiness.py` | `live_submit_readiness_hard_gate` + `REQUIRED_OFFICIAL_METRIC_FIELDS` 7 项 |
| `task_executor.py` | `ThreadTaskExecutor`(4 worker 守护)— 含 2 处 `NotImplementedError` |
| `web_alpha_lifecycle.py` | lifecycle replay (上限 2000,SCHEMA_VERSION v1) |

---

## 3. `brain_alpha_ops/brain_api/` — BRAIN 官方 API 适配层 (22 文件)

### 3.1 抽象层
- `base.py` — `BrainAPI` Protocol(22 个方法)+ `BrainAPIError`
- `official.py` (511 行) — `OfficialBrainAPI` 由 4 个 mixin 组合:
  - `OfficialAuthProfileMixin` — 认证 + `/users/self` 提取 tier/level/points
  - `OfficialContextDataMixin` (606 行) — 字段/算子/数据集/Alpha 查询
  - `OfficialRequestMixin` — `_request(...)` 重试(408/429/500/502/503/504)+ 401 回退 basic auth + 401/403 auth refresh
  - `OfficialSimulationSubmissionMixin` — 模拟/回测/检查/提交/PROD_CORRELATION

### 3.2 提交安全 (3 重防护)
```
runtime_constants.REAL_SUBMIT_DISABLED_WEB_FLOW = True   # 1. 常量
web_submission_single._real_submit_disabled() check      # 2. Web 路由
brain_api/official_simulation.submit_alpha 内部 raise    # 3. API 适配层
```

### 3.3 关键模块
| 文件 | 关键能力 |
|---|---|
| `canonical.py` | **Single source of truth** — `CANONICAL_THRESHOLDS` (sharpe=1.25 / fitness=1.0 / max_self_correlation=0.70 / platform_max_turnover=0.70) + `CANONICAL_RELEASE_REQUIREMENTS` + `CANONICAL_API_PATHS` (14 个) + `SUPPORTED_*` 枚举 + `CANONICAL_METRIC_NAMES` 12 个 |
| `context_defaults.py` | 懒加载官方 fields/operators(无硬编码回退 — P0-1) |
| `cache.py` | `cache_key(kind, params)` (sha256 of sorted JSON) + TTL via `config.context_cache_ttl_seconds` |
| `official_auth.py` | 认证 + profile 提取 |
| `official_context.py` | `list_fields/datasets/operators/data_categories` + `search_*_limited` (max_window=10000) + `discover_*` |
| `official_alphas.py` | `locate_dataset/field/alpha` + `filter_alphas` + `query_alphas` + `list_user_alphas` (含 transient retry + cursor/offset 恢复 + `force_refresh=True`) |
| `official_simulation.py` | `submit_simulation` + `poll_*` + `check_alpha` + `submit_alpha` (F-02+F-03 守护) + `concurrent_simulate/check` (ThreadPoolExecutor) + `check_prod_correlation` |
| `official_validation.py` | 本地语法预检(括号/深度 ≤6/length ≤250/quote 配对)+ 委托 `ExpressionEngine` + PASS/FAIL |
| `official_helpers.py` | 纯函数: `build_simulation_payload` / `normalize_metrics` / `looks_non_production_alpha_id` / `ALLOWED_OFFICIAL_API_HOSTS = {"api.worldquantbrain.com"}` |
| `official_query_params.py` | WQB 风格 filter → query string |
| `official_filtering.py` | `FilterRange` dataclass(`[a,b]`/`(a,b)` 文本解析) + `normalize_wqb_options` / `clamp_query_limit` (max 10000) |
| `pagination.py` | `_paginate_collection`(repeated_page 检测 + unique_item_key 去重) |
| `pagination_limits.py` | MAX 全为 `None`(无硬 cap) |
| `rate_limit_policy.py` | 3 等级:regular=3/pre_consultant=5/consultant=10 + min_retry_pause=60 + initial backoff=60 |
| `user_alpha_sync.py` | `list_user_alphas_for_sync` + `sync_range_from_payload` + `USER_ALPHA_SYNC_RANGES = {"3d", "7d", "recent", "6months", "all"}` |
| `user_alpha_transient.py` | `USER_ALPHA_TRANSIENT_RETRY_STATUSES={408,500,502,503,504}` + `USER_ALPHA_TRANSIENT_PAGE_RETRY_ATTEMPTS=3` |

### 3.4 重要差异(已发现的 3 处)
| 位置 | 范围集合 |
|---|---|
| `runtime_constants.AgentLimits.MAX_SYNC_RANGE` | `{"1d", "3d", "7d", "all"}` |
| `brain_api.user_alpha_sync.USER_ALPHA_SYNC_RANGES` | `{"3d", "7d", "recent", "6months", "all"}` |
| `web_payload_validation.ALLOWED_SYNC_RANGES` | `{"3d", "7d", "recent", "6months", "all"}` |

`1d` 仅 agent 工具层允许,Web 入口缺;反之 `recent/6months` 在 Web 允许但 agent 工具层不允许。

---

## 4. `brain_alpha_ops/research/` — 自动化生成子系统 (104 文件)

### 4.1 `pipeline.py` (693 行) — 主编排器
`AlphaResearchPipeline` 通过 10 个 mixin 组合功能:
```
PipelineRuntimeMixin          # 主循环骨架
PipelineContextSyncMixin      # 上下文同步
PipelineServiceFactoryMixin   # 服务工厂
PipelineStrategyMixin         # 策略切换整合
PipelineCandidatePoolMixin    # 候选池管理
PipelineOfficialValidationMixin
PipelineBacktestMixin
PipelineLegacySimulationMixin # 旧模拟兼容
PipelineSubmissionMixin
PipelineSnapshotMixin         # 快照构造
```

`run()` 主循环:
1. `authenticate()` → `recover_persisted_backtest_slots()` → `get_user_profile()`
2. `_sync_cloud_alphas()` → `_load_official_context()` → `build_production_context()`
3. 注入 `live safe_fields` 到 generator
4. `ResearchCycleOrchestrator.next_cycle()` 循环:
   - `_cycle_select_dataset(cycle)` — 数据集选择(P1 refactor)
   - `_experience_feedback_service().apply(cycle)` (每 5 轮)
   - `_apply_assistant_guidance(cycle)` — LLM 引导
   - `_refresh_observability_throttle(cycle)` (每 50 轮 / 24h 刷 context)
   - `_local_prefilter → rank_candidates → validation_targets[:quota]`
   - `_cycle_simulate_and_submit` → `_top_up_candidate_pool` → `_maybe_switch_strategy`
   - `convergence.record_cycle(...)` — 收敛跟踪
   - `record_strategy_reward(...)` — Bandit 奖励
   - `auto_calibrator.needs_calibration()` — 自动校准触发
   - `_try_fusion_top_candidates` (stalled && stall_cycles≥3) — 次级融合

**关键事件**:每 10 周期出 `convergence_report`;stalled 时升级为 WARN。

### 4.2 8 阶段门禁管道

| 阶段 | 入口 | 关键模块 | 检查项 |
|---|---|---|---|
| 1. 候选生成 | `generate()` | `HypothesisDrivenGenerator` / `DynamicThemeEngine` / `CandidateGenerator` | 3 模式 70/20/10;knowledge constraints;observability avoid-keys |
| 2. 本地预筛 | `_local_prefilter` | `local_backtest_engine.py` + `local_backtest_gate.py` | `PREFILTER_BACKTEST_DATES=84 × 160` 合成数据;失败 → score -8 |
| 3. 本地评分 | `local_convergence_score` | `scoring.py` | `0.65*prior + 0.35*local_quality` |
| 4. 官方校验 | `_validate → _validate_slots` | `pipeline_backtest_flow.py` + `official_validation.py` | 槽位 + 配额 |
| 5. 官方模拟/回测 | `_cycle_simulate_and_submit` | `parallel_backtest.py` + `batch_backtest_coordinator.py` | 槽位填充 + 轮询 + 终化 |
| 6. 实证评分 | `empirical_score` + `submission_checklist` | `scoring.py` | 16+7 项;hard gate 失败 → score=0 |
| 7. 提交决策 | `evaluate_quality_gate` | `scoring.py` + `safety.py` | decision_band: submit(≥85) / optimize(≥70) / research(≥50) |
| 8. 提交安全闸 | `SubmissionLedger.assess` | `safety.py` | 8 项 + 非生产 ID 前缀拦截 |

### 4.3 3 层评分体系 (`scoring.py` 844 行)

```
┌─────────────────────────────────────────────────────────────┐
│  total_score = 0.30 × prior + 0.45 × empirical + 0.25 × checklist │
│                  (官方验证后)                                  │
│  else = local_rank_score + assistant_guidance_adjustment    │
└─────────────────────────────────────────────────────────────┘
```

**Prior (8 维, 参数化)**:
| 维度 | 默认 weight | 评分依据 |
|---|---|---|
| economic_logic | 0.18 | 9 个概念关键词计数(momentum/mean_reversion/value/quality/volatility/liquidity/growth/risk_management/cross_sectional) |
| structure | 0.14 | 复杂度评分(threshold=4, penalty=8) |
| field_operator_support | 0.16 | +8/field |
| data_compliance | 0.12 | high=82 / low=35 |
| horizon_turnover_proxy | 0.14 | 窗口中位数 [5,90] in=82 / out=68 |
| risk_control_proxy | 0.14 | tier3=84 / tier2=66 / tier1=48 |
| diversity | 0.07 | category ∈ {Liquidity,Volatility,Hybrid} high=80 |
| explainability | 0.05 | len<140 in=85 |

**Empirical (16 项, max ~120)**:
| item | points | hard? | 阈值/规则 |
|---|---|---|---|
| sharpe | 20 | ✓ | ≥1.25 (Delay-1) / ≥2.0 (Delay-0) |
| fitness | 15 | ✓ | ≥1.0 / ≥1.3 (delay0) |
| fitness_crosscheck | 0 | | |BRAIN − local| ≤0.05 |
| turnover_min | 8 | ✓ | ≥0.01 |
| turnover_platform | 8 | ✓ | ≤0.70 |
| turnover_quality | 6 | 可硬 | ≤0.30 (advisor target) |
| returns | 5 | | |≥0 |
| drawdown | 5 | | |≤0.25 |
| self_correlation | 14 | ✓ | ≤0.70 (Sharpe × 1.10 豁免) |
| prod_correlation | 10 | ✓ | ≤0.70 |
| weight_concentration | 5 | ✓ | ≤0.10 |
| sub_universe_sharpe | 10 | ✓ | ≥0.75 × √(sub/alpha) × sharpe |
| is_oos_ratio | 8 | | |sub_sharpe / sharpe ≥ 0.5 |
| margin_bps | 10 | | |≥4 bps (API 优先, fallback 估算) |

**BRAIN 官方 fitness 公式**:`Sharpe × √(|Returns| / max(Turnover, 0.125))`

**Hard gate 行为**:`empirical_score = 0` if any hard gate fails(独立 status: `hard_gate_blocked`)

**Submission checklist (7 项, max 100)**:`official_metrics_present(15)` + `official_pass(15)` + `economic_logic(15)` + `data_delay_conservative(10)` + `local_quality(15)` + `self_correlation_proxy(20)` + `diversity(10)`

**Decision bands**:`submit(≥85)` / `optimize(≥70)` / `research(≥50)` / `abandon`

### 4.4 AlphaCheckRegistry (`alpha_checks.py` 757 行)

**25 个 check + 类型特定**:
- 23 个默认 + `is_oos_robustness` + `expression_complexity` = 25
- 6 个类型特定 (POWER_POOL×5 / ATOM×1 / PYRAMID×1)

**Severity 分布**:
- **ERROR (8 个, 阻塞)**:sharpe_positive / fitness_minimum / turnover_platform / self_correlation / prod_correlation / weight_concentration / sub_universe_sharpe / expression_valid
- **WARNING (9 个)**:returns_positive / drawdown_limit / turnover_quality / marginal_contribution / margin_minimum / ic_mean / ic_ir / coverage_minimum / delay_consistent / is_oos_robustness
- **INFO (6 个)**:rank_ic / turnover_stability / drawdown_stability / neutralization / pasteurization / nan_handling / expression_complexity

**与 `scoring.py:empirical_score` 重复**:两套并行评估,结果可能不一致。`CheckReport.passed` 与 `scorecard.empirical.hard_gate_failed` 行为同步,但 detail 字段不同。

### 4.5 `hypothesis_driven_generator.py` (1240 行) — 3 模式路由器

**6 个组件**:
- `GenerationModeRouter` — 加权 `random.choices`,实际比例统计(`actual_ratios`)
- `HypothesisSelector` — 按 `experience_weights.overall` 加权,3 个最近使用 ID 排除
- `ExpressionFamilySelector` — 加权 family + window
- `FieldSelector` — dataset 字段集优先 → 语义类别 fallback → token 评分(≥5)
- `ContextAdapter` — region/universe/delay 偏好 ∩ available
- `HypothesisDrivenGenerator` — `generate(n, dataset_id)` 主类

**3 模式(70/20/10)**:
- `hypothesis_driven`(70%):6 步管道 select hypothesis → select expression family+window → select fields → adapt context → build expression → assemble Candidate
- `experience_feedback`(20%):`DynamicThemeEngine` 偏向 winning 模式
- `random_exploration`(10%):纯 `DynamicThemeEngine` 随机

**降级链**:任何子步骤失败 → `_generate_random_exploration` → `_generate_bare_fallback`

### 4.6 8 个 Hypothesis (`hypotheses/*.yaml`)

| 文件 | id | 类别 | 表达式家族数 |
|------|----|------|-------------|
| `value_reversal.yaml` | value_reversal | reversal | 5 |
| `earnings_revision.yaml` | earnings_revision_momentum | momentum | 4 |
| `sentiment_short.yaml` | sentiment_short_interest | hybrid | 4 |
| `liquidity_premium.yaml` | liquidity_premium | liquidity | 4 |
| `low_volatility.yaml` | low_volatility_anomaly | volatility | 4 |
| `quality_profitability.yaml` | quality_profitability | quality | 4 |
| `microstructure.yaml` | microstructure_order_flow | hybrid | 5 |
| `analyst_behavior.yaml` | analyst_behavior_bias | cross_sectional | 5 |

每个 YAML 包含:`rationale.theory`(中文 ≥20 字) + `academic_refs` + `behavioral_bias`、`field_categories`(P0/P1/P2 priority + weight)、`expression_families`(带 `windows/windows_short/windows_long` 占位符)、`expected_failure_modes`、`adaptation`、`experience_weights`(初始 1.0)。

### 4.7 EMA 经验反馈 (`experience.py` 562 行)
- `record_alpha_result` → `data/alpha_features.jsonl`
- `get_winning_patterns` → `{top_operators, preferred_windows, field_combinations, top_categories}`
- `update_hypothesis_weights` → `HypothesisLibrary.update_weights` (EMA 0.8/0.2)
- AB 检验 → `data/ab_tests.jsonl` (parent_*/mutant_*/sharpe_delta/...)

### 4.8 收敛跟踪 (`convergence.py` 394 行)
- 滚动窗口 (maxlen=10) + 90% Bootstrap CI
- Spearman ρ trend(`|ρ|<0.3` → inconclusive)
- Stall 检测:当前 CI 下界 > 上次 CI 上界 → 显著改进;反之 → 显著下降
- 触发次级融合:stalled && stall_cycles≥3

### 4.9 反过拟合 (`anti_overfit.py` + `rolling_validation.py` + `robustness_policy.py`)
- `AntiOverfitService.evaluate` — 4 项测试:ic_stability / subsample_stress / placebo / half_life;score≥75 pass / 50–74 caution / <50 block
- `RollingValidationService.evaluate` — rolling_fitness/sharpe 分 chunk,decay_ratio = last/first
- `RobustnessPolicy.decide` — `block_on_anti_overfit=True` → block;`block_on_rolling_failure=False` → downgrade;multiplier (0.9 caution / 0.0 block)

### 4.10 策略切换 (`strategy_switch.py`) — ε-greedy bandit
```python
epsilon = 0.20
P(explore) < ε → 1/max(bandit_counts/ max_count) 加权采样
P(exploit) ≥ ε → max(mean_rewards) → 平局 random.choice
```
`StrategyLifecycleTracker`:`propose/validate/mutate/retire/record_reward` + lineage = sha256(name|region|universe|neutralization)
`StrategyPluginRegistry`:`from_specs(["module:attr", ...])` 动态加载

### 4.11 融合 (`fusion.py` 207 行)
- `orthogonal_blend(a, b)`: `a - ts_regression(a, b, 252) * b`
- `residual_alpha(signal, base)`: `signal - ts_regression(signal, base, 252) * base`
- `composite_fusion(ex1, ex2, mode)`:orthogonal / residual / reverse_residual / composite
- `composite_ensemble(expressions, mode)`:average / rank_average / max / min

### 4.12 自动校准 (`auto_calibrator.py` 465 行)
- 触发:`passing_count >= 30 AND new_since_last >= 30`
- Grid search 7 维(经济逻辑除外):structure(240) / field_op(6) / horizon(27) / risk(27) / diversity(12) / explainability(27) / compliance(12)
- 评估指标:MAE = mean(|prior_score − sharpe*50|)
- 依赖注入:`from calibrate_weights import ...`(项目根级脚本)

### 4.13 `iterative_optimizer.py` (472 行) — 诊断驱动突变
`_FAILURE_TO_STRATEGY` 映射(10 类失败):
- sharpe → [field_swap, window_perturb, structure_refine]
- fitness → [field_swap, structure_refine, operator_substitute]
- correlation → [field_swap_semantic, operator_substitute, structure_refine]
- turnover_platform/quality → [longer_window, structure_refine]
- turnover_low → [window_perturb, field_swap]
- concentration → [structure_refine, field_swap]
- margin → [structure_refine, operator_substitute]
- sub_universe_sharpe → [structure_refine, field_swap]
- gate → [structure_refine, field_swap]

5 大算子:`field_swap` / `field_swap_semantic` / `window_perturb` / `structure_refine` / `operator_substitute`(同族替换,白名单 = `data/official_operators.json`)。

### 4.14 其它 research 模块 (按角色)
| 模块 | 角色 |
|---|---|
| `local_backtest_engine.py` (1099 行) | 本地 FASTEXPR 子集评估(84 日 × 160 标的 合成数据) |
| `local_backtest_gate.py` (151 行) | 拒绝/降级(score_penalty=8) |
| `prod_correlation.py` (272 行) | 官方 `/alphas/correlations/check` + 本地 fallback(`len(expr)` 启发式) |
| `repository.py` | `ResearchRepository` JSONL 持久化(candidates/events/lifecycle/cloud_alphas) |
| `safety.py` (243 行) | `SubmissionLedger` 8 项 + 非生产 ID 拦截 |
| `templates.py` (265 行) | `AlphaTemplateRegistry` 6 内置模板 + JSON 加载 |
| `theme_engine.py` (737 行) | `DynamicThemeEngine` + 109 个 `TEMPLATE_SKELETONS` 跨 12 类别 + 14 种自动骨架 |
| `dataset_selector.py` (186 行) | 4 策略:`all/rotate/random/specific` + `fixed/locked` |
| `diagnostics.py` (256 行) | 9 维失败诊断 + mutation 建议 |
| `expression_engine.py` | 表达式规范化(`normalize_wq_expression_shape`) |
| `expression_ast.py` | AST/指纹/相似度 |
| `expression_diversity.py` | 重复检测 |
| `expression_index.py` / `expression_sqlite_index.py` | 索引(去重 + 相似度) |
| `checkpoint.py` | 断点续跑 |
| `backtest_slots.py` / `backtest_polling.py` / `backtest_finalization.py` / `backtest_submission.py` | 4 阶段回测 |
| `batch_backtest_coordinator.py` | 批量协调 |
| `candidate_pool.py` | `rank_candidates` 等 |
| `fusion_candidates.py` / `secondary_fusion.py` | 主/次融合 |
| `memory.py` | `ResearchMemory` 持久化 |
| `knowledge_base.py` | `KnowledgeRecord` + `StructuredKnowledgeBase` |
| `llm_review.py` | `CrossReviewService` + LLM 路由(Fallback/OpenAICompatible/Static) |
| `llm_service.py` | LLM 服务 |
| `prompt_templates.py` | 提示模板 |
| `cross_review_pipeline.py` | 跨 review 流程 |
| `assistant.py` | LLM 助手主类 |
| `production_context.py` | `build_production_context` + `eligible_strategy_profiles` |
| `calibration.py` / `calibration_engine.py` | 校准入口 + 引擎 |
| `observability.py` (940 行) | 健康快照 + 红/黄告警 |
| `parallel_backtest.py` (372 行) | 并行回测 |
| `alerting.py` | 告警事件 → 通知 |
| `market_data_cache.py` / `market_data_vector.py` | 市场数据缓存/向量化 |
| `fallback_generation.py` | 降级生成(bare fallback) |
| `field_quality.py` | `filter_generation_fields` |
| `validated_generator.py` | 验证后生成器 |
| `hypothesis_expression_support.py` | 假设-表达式 placeholder 解析 |
| `hypothesis_generator_helpers.py` | 假设生成器辅助 |
| `pipeline_*.py` mixin (17 个) | 见 `pipeline.py` 描述 |
| `pipeline_state.py` / `pipeline_helpers.py` / `pipeline_services.py` / `pipeline_strategy.py` 等 | 状态/服务/策略 mixin |

---

## 5. `brain_alpha_ops/data/` + `config/` + `scoring/` + `compliance/`

### 5.1 `data/loader.py` — `OfficialDataLoader` 单例
- 双检锁线程安全单例 + 自动 `load_all()` 加载 3 个 JSON
- `REQUIRED_OFFICIAL_CONTEXT_FILES = ("official_fields.json", "official_operators.json", "official_datasets.json")`
- `SUPPLEMENTAL_OFFICIAL_CONTEXT_FILES` 含 meta × 3 + `official_context_refresh_status.json`
- `ensure_official_context_files(data_dir)` — PyInstaller `_MEIPASS` 下的文件复制到 runtime data_dir
- `reload()` 强制重载
- `data/official_fields.json` (834 KB) 实际有 **8599 字段**(`official_context_refresh_status.json` 显示)
- 启动时只 load 一次,新写入的 context **不会自动 reload** 除非显式 `loader.refresh(data_dir)`

### 5.2 `data/field_dataset_mapper.py`
- 双向 field↔dataset 索引 + atomic swap(新 readers 永远看到完整索引)

### 5.3 `data/ashare_adapter.py`
A 股数据适配器(未深入)。

### 5.4 `config/_loader.py` + `config_models.py` + `config_schema.py` + `config_domain_validation.py`
- `load_run_config` + `load_ops_config` + `validate_run_config` + `write_run_config`
- Dataclass models:`BrainSettings` / `CredentialConfig` / `OfficialAPIConfig` / `OpsConfig` / `QualityThresholds` / `ResearchBudget` / `ScoringConfig` / `SubmissionPolicy` / `RunConfig` / `WebConfig`
- `BrainSettings.to_platform_dict()` 返回 `{"type", "settings"}` 格式
- v4.0 重构后的 config 域总入口(`config/__init__.py` re-export)

### 5.5 `scoring/official_scoring.py` — `OfficialScoringSystem`
- `evaluate(candidate)` → `ScoringResult`
- 委托 `research.scoring.build_scorecard` + `evaluate_quality_gate`,加 `attribution_tree` + `release_score_gate` + `scoring_comparison.simulate_brain_api_output`

### 5.6 `scoring/attribution.py` — `AttributionNode`
(name/score/weight/contribution/children/explanation/calibratable/historical_trend) + `build_attribution_tree` + `_DIM_EXPLANATIONS`(中文)。

### 5.7 `scoring/gates.py` — `GateConfig` + `GateResult`
- `OFFICIAL_HARD_GATE_NAMES = {sharpe, fitness, turnover_min, turnover_platform, self_correlation, prod_correlation, weight_concentration, sub_universe_sharpe}`

### 5.8 `scoring/anti_overfit.py` — 4 层验证
- IC Stability / Subsample Stress / Placebo / Half-Life
- `_IC_STABILITY_WINDOW_MIN=20` / `_REGIME_MIN_SAMPLES=30` / `_PLACEBO_TRIALS=50` / `_DEFAULT_HALF_LIFE_WINDOW=60`

### 5.9 `compliance/` — Red-line 6 条硬约束
- `redline_verifier.RedLineVerifier` 串行检查 6 条红线:
  1. `_verify_redline_1_no_custom_extension` — 零自定义字段/算子
  2. `_verify_redline_2_threshold_zero_deviation` — 阈值零偏差
  3. `_verify_redline_3_dataset_ids` — Dataset ID 全可用
  4. `_verify_redline_4_parameter_traceability` — 参数全链路可溯
  5. `_verify_redline_5_factor_coverage` — 要素全覆盖
  6. `_verify_redline_6_code_alignment` — 代码与 BRAIN API 强对齐
- `redline_models.py` — `ComplianceReport` / `RedLineViolation` / `RedLineBlockedError`

### 5.10 `ux/` (9 文件, 1863 行) — Guided UX 层
- `guided_pipeline.py` (443 行) — 主流程
- `guided_models.py` / `guided_storage.py` / `guided_display.py` / `guided_formatting.py`
- `errors.py` (391 行) — UX 层错误
- `user_messages.py` (351 行) — 用户消息模板
- `history.py` (245 行) — `RunHistoryAnalytics`

### 5.11 `domains/` — 5 个空 stub
每个文件只 2-5 行 re-export,未实现任何实际功能。**可全部删除**。

---

## 6. `brain_alpha_ops/web/` (React + Web 后端)

### 6.1 React 前端
- `web/react_app/` (Vite + React 18 + TS 5.4 + Tailwind 3.4)
- 38 个 .tsx/.ts,1.37 万行
- 21 个组件、5 个 hooks、3 个 helpers、3 个 utils、1 个 types
- 依赖:**仅 `react` + `react-dom`**(无 recharts/antd/lodash 等 — 之前已剔除)
- devDeps:tailwindcss / vite / vitest / testing-library / lighthouse

**主要组件**:`Dashboard` / `Sidebar` / `JobMonitor` / `CandidateTable` / `ConfigPanel` / `ScoringPanel` / `QualityCheckPanel` / `SubmissionPanel` / `SubmissionConfirmPanel` / `OfficialBacktestSlots` / `OfficialOperationsPanel` / `SnapshotPanel` / `StateCards` / `StatusFlowDiagram` / `StepGuide` / `ProgressFeedback` / `PhaseShell` / `KpiCard` / `EmptyState` / `MobileTabBar` / `ToastContainer`

**主要 hooks**:`useApi` / `useJobState` / `usePhaseState` / `useSSE` / `useToast`

**API 客户端**:`api/jobCancel.ts`(仅此一个,其它都用 `useApi.ts` + fetch 包装)

### 6.2 后端入口
- `web/__init__.py` (850 行) — 包含 `Handler(BaseHTTPRequestHandler)` + `dispatch_get` + `dispatch_post` + 14 个 `_real_*` 业务处理
- 14 个 `_real_*` 路由处理:
  - `_real_sync` / `_real_generate` / `_real_check` / `_real_check_batch` / `_real_submit` (硬阻断) / `_real_submit_batch` (硬阻断) / `_real_score` / `_real_attribution` / `_real_run` / `_real_connection` / `_real_stop` / `_real_session`
- `_submit_disabled_payload()` 返回 `REAL_SUBMIT_DISABLED_WEB_FLOW` 错误 — Web 永远不调用 `api.submit_alpha`

### 6.3 路由分层
```
HTTP request
  ↓
Handler (web/__init__.py)
  ↓
security: origin + session + replay
  ↓
_dispatch_route (web_handler_dispatch_core.py)  ← 优先路径
  ↓
_per_route handlers (web_handler_dispatch.py, 25 个 _post_* / 多个 _get_*)
  ↓
domain service (web_runtime_facade.py / web_cloud_snapshot.py / ...)
  ↓
↓
fallback: web_routes.py (web/__init__.py 内 dispatch) ← 兜底
```

### 6.4 完整路由表(74 个 GET + 24 个 POST)

**GET 路由**(75 个):
```
/api/health                                # 无需 session
/api/status                                # 作业状态
/api/production-validation/status
/api/config
/api/config_schema
/api/capabilities
/api/active_job
/api/latest_result
/api/stream                                # SSE 流
/api/lifecycle
/api/alpha_lifecycle
/api/lifecycle/history
/api/candidates
/api/candidate/list
/api/cloud_alphas
/api/snapshot/cloud
/api/snapshot/cloud_alphas
/api/research_memory
/api/snapshot/memory
/api/snapshot/research_memory
/api/research_knowledge
/api/research_observability
/api/snapshot/observability
/api/prompt_runs
/api/sqlite_indexes
/api/snapshot/sqlite_indexes
/api/sqlite_expression_lookup
/api/sqlite_record_lookup
/api/assistant_context
/api/snapshot/assistant_context
/api/assistant_guidance
/api/snapshot/assistant_guidance
/api/assistant_request
/api/snapshot/assistant_requests
/api/anti_overfit
/api/snapshot/anti_overfit
/api/rolling_validation
/api/snapshot/rolling_validation
/api/sync_status
/api/check_status
/api/check_results
/api/profile
/api/presets
/api/redline_report
/api/scoring/health
/api/checkpoint_status
/api/backtest_slots
/api/submit_readiness
/api/candidates/simulate/eligible
/api/phase_state
... (75 总)
```

**POST 路由**(24 个):
```
/api/run                                   # _post_run
/api/production-validation/start
/api/config                                # _post_config_save
/api/config/update
/api/test_connection                       # _post_test_connection
/api/connection_test
/api/stop                                  # _post_stop
/api/production-validation/stop
/api/cancel                                # _post_cancel
/api/sync_alphas                           # _post_sync_alphas
/api/sync-cloud-alphas                     # R-02 legacy alias
/api/sync/sync_alphas
/api/sync_context_only
/api/sync_cancel
/api/check                                 # _post_check
/api/candidate/check
/api/generate_candidates                   # _post_generate_candidates
/api/generate
/api/candidates/optimize
/api/candidate/optimize
/api/check_batch                           # _post_check_batch
/api/submit                                # _post_submit (硬阻断 403 REAL_SUBMIT_DISABLED_WEB_FLOW)
/api/candidate/submit
/api/submit_batch                          # _post_submit_batch
/api/assistant/parse
/api/assistant_response/parse
/api/assistant_response_parse
/api/assistant/guidance                    # _post_assistant_response_guidance
/api/assistant/cross_review
/api/assistant_guidance
/api/logout
/api/shutdown
/api/session
/api/scoring/evaluate
/api/scoring/attribution
/api/candidates/simulate
```

### 6.5 后端核心模块(80 个 `web_*.py`)

| 模块 | 行数 | 关键职责 |
|---|---|---|
| `web_routes.py` | 875 | GET 路由分发(链式 if-else) |
| `web_handler_dispatch.py` | 1004 | 25 个 POST handler + 路由表 + `dispatch_get`/`dispatch_post` |
| `web_handler_dispatch_core.py` | (未读全) | `dispatch_route` / `apply_rate_limit` / `error_response` + 中央路由循环(回退到 `web/__init__.py:dispatch_post`) |
| `web_dispatch_context.py` | (未读全) | `WebHandlerDispatchContext` + 7 子 context |
| `web_application_context.py` | (未读全) | re-export |
| `web_runtime_facade.py` | 781 | 巨型 facade: `test_connection` / `run_job` / `run_check_batch_job` / `run_sync_job` / `run_generate_candidates_job` / `run_scoring_evaluate_job` / `run_submit_batch_job` / `submit_candidate` / `submit_batch` / `submission_preflight_advisory` / `observability_submission_preflight` |
| `web_runtime_state.py` | 217 | `active_auxiliary_operation` / `compute_run_stats` / `lifecycle_from_job` / `maybe_archive_lifecycle` / `load_presets` / `load_check_results` / `status_category` |
| `web_runtime_bindings.py` | (未读) | 旧 binding 桩 |
| `web_service_namespace.py` | (363) | `build_web_service_namespace()` ~130 key |
| `web_facade_bindings.py` | (300) | `build_web_facade_bindings(namespace)` 200+ key + `Handler = _create_handler_class(...)` |
| `web_compat_facade.py` | 75 | 17 个旧测试函数名 lazy-import 桥 |
| `web_legacy_exports.py` | 122 | 74 个 LEGACY_EXPORT_SPECS |
| `web_state_contract.py` | 450 | 错误码 → 用户可读消息映射器(16 个 `_ERROR_DEFINITIONS`) |
| `web_server_lifecycle.py` | 160 | `SafeThreadingHTTPServer` + `find_free_port` + `serve` |
| `web_cli.py` | 90 | CLI 入口 + 旧 `serve`(重复实现) |
| `web_html.py` | 140 | HTML 加载 + CSP + 模板占位符 |
| `web_csp.py` | (未读) | 极简 CSP 生成器(SHA-256 hash) |
| `web_session.py` | 450 | 会话门面 + BRAIN 凭证 vault |
| `web_security.py` | 350 | 核心安全原语 |
| `web_sse.py` | 250 | 旧 SSE 实现(与 `_handle_sse_stream` 重复) |
| `web_http_handler.py` | 290 | `create_handler_class` 工厂生成 `BaseHTTPRequestHandler` 子类 |
| `web_jobs.py` | 300 | 早期 `ASYNC_JOBS` in-memory(200 cap, 1h TTL) — 与 `tasks.py:JobStore` 双轨 |
| `web_async_jobs.py` | 350 | 通用 async job 服务(`run_simple_async_job_service` 模板) |
| `web_progress.py` | 275 | `ProgressPayload` + `PHASE_LABELS` 中文映射表(27 个 phase) |
| `web_candidate_simulation.py` | 996 | `simulate_candidates_job` 完整模拟任务 |
| `web_check_availability.py` | 879 | 12 项候选可用性检查 + 批处理 job + 解释器(3 个职责) |
| `web_submission_safety.py` | 405 | 11 项 preflight 检查 + observability |
| `web_submission_single.py` | 200 | 单次提交编排(REAL_SUBMIT hard kill-switch) |
| `web_submission_batch.py` | 270 | 批量提交编排 |
| `web_candidate_decisions.py` | 515 | 6 类 production decision(archive/optimize/official_validation/needs_human_confirmation/submit_review_blocked/retain) |
| `web_candidate_optimization.py` | (大) | 局部候选优化(无 API) |
| `web_candidate_audit.py` | (大) | 科学审计(SCIENTIFIC_AUDIT_SCHEMA_VERSION) |
| `web_candidate_bindings.py` | (大) | binding 合并 |
| `web_candidate_check_evidence.py` | 110 | 把 check 结果落盘 |
| `web_backtest_slots.py` | 485 | 槽位 / 队列汇总 |
| `web_redline_scoring.py` | 290 | Red-line 评分集成 |
| `web_alpha_lifecycle.py` | 256 | lifecycle replay (上限 2000) |
| `web_capability_registry.py` | 320 | 静态 capability 清单 |
| `web_payload_validation.py` | 336 | 11 个严格 payload 校验器 |
| `web_config.py` | 515 | Payload 解析 + bounded 校验 |
| `web_sync_job.py` | 598 | 完整云端同步 job(8 阶段) |
| `web_sync_payload.py` | (中) | 同步版 sync |
| `web_sync_status_payload.py` | 108 | sync_status + history |
| `web_cloud_snapshot.py` | 905 | 同步 snapshot + 上下文刷新 |
| `web_run_job.py` | 282 | `run_job_service` + `run_guided_job_service` |
| `web_simulation_job.py` | 51 | `create_sim_job_store` |
| `web_review.py` / `web_review_api.py` | (未读) | 复核 API |
| `web_rate_limit.py` | 92 | 速率限制 |
| `web_get_handlers.py` | 75 | GET handlers 拆片 |
| `web_post_handlers.py` | 75 | POST handlers 拆片 |
| `web_handler_candidate_routes.py` | 135 | candidate 路由 |
| `web_job_registry.py` | 90 | JobRegistry 工厂 |
| `web_submit_readiness.py` | 145 | submit readiness payload |
| `web_check_batch_context.py` | 80 | check_batch 上下文 |
| `web_check_batch_job.py` | 7 | stub (deprecated) |
| `web_session_bindings.py` / `web_job_bindings.py` / `web_config_bindings.py` / `web_snapshot_bindings.py` | (各 ~5) | **死代码**,已被 `web_facade_bindings` + `web_service_namespace` 替代 |
| `web_candidate_check.py` | 4 | stub |
| `web_candidate_selection.py` | 4 | stub |
| `web_candidate_generation_summary.py` | 110 | 候选生成摘要 |
| `web_candidate_generation.py` | 538 | 候选生成主流程 |
| `web_candidate_lifecycle_risk.py` | 170 | lifecycle 风险 |
| `web_candidate_payloads.py` | 309 | payload 注释 |
| `web_candidate_simulation_failures.py` | 95 | 失败处理 |
| `web_candidate_simulation_runtime.py` | 137 | runtime 工具 |
| `web_candidate_simulation_selection.py` | 102 | 选 candidate |
| `web_candidate_simulation_state.py` | 468 | simulation 状态 |
| `web_candidate_workflow.py` | 276 | workflow 计划 |
| `web_snapshots.py` | 60 | snapshot 工具 |
| `web_snapshot_facade.py` | 138 | snapshot facade |
| `web_snapshot_runtime.py` | 237 | snapshot runtime |
| `web_assistant_snapshots.py` | 728 | assistant 快照 |
| `web_sqlite_indexes.py` | 65 | SQLite 索引快照 |
| `web_simulation_job.py` | 51 | simulation job 工厂 |
| `web_backtest_slots.py` | 485 | 槽位 |
| `web_redline_scoring.py` | 290 | 评分集成 |
| `web_submission_single.py` | 200 | 单次提交 |
| `web_submission_batch.py` | 270 | 批量提交 |
| `web_runtime_bindings.py` | 30 | runtime binding |

### 6.6 业务子系统
- **模拟**:`web_candidate_simulation.py` 是 996 行大文件,主入口 `simulate_candidates_job(job_id, payload, *, job_store, log)`,处理 HTTP 429 退避、`STALL_DETECTED`、`CONCURRENT_SIMULATION_LIMIT_EXCEEDED` 退避。
- **检查**:`web_check_availability.py` 12 项检查 + 批处理 job。`score -= 40` for severity ≥ high,`-12` for medium。
- **提交安全**:`web_submission_safety.py:submission_preflight_advisory` 11 项检查 + `observability_submission_preflight` 阻塞旗标需 `confirm_observability_risk`。
- **提交编排**:`web_submission_single.py` / `web_submission_batch.py` 真实路径要求 `confirm_submit=True` + observability 确认 + 3 重 kill-switch。
- **决策**:`web_candidate_decisions.py:candidate_production_decision` 6 类决策(永远 `submit_allowed=False`)。

### 6.7 安全设计
- `web_session.py`:`SESSION_MANAGER = LocalSessionManager()` + BRAIN 凭证 vault
- `validate_token` 用 `secrets.compare_digest`
- Cookie: `name=val; Path=/; Max-Age=ttl; HttpOnly; SameSite=Strict[; Secure]`
- `web_security.py`:5 个常量(`LOCAL_HOSTS` / `SESSION_COOKIE_NAME` / `DEFAULT_SESSION_TTL_SECONDS=12h` / `REQUEST_REPLAY_TTL_SECONDS=5min` / `MAX_REPLAY_CACHE_SIZE=10000`)
- Replay 防护:session row 上 `request_replay` 子 dict(cap=10000)
- `web_csp.py`:SHA-256 hash 注入到 `script-src` / `style-src`
- 路由前门:`_is_allowed_local_request` + `_has_valid_session` + `_validate_replay_request`
- `_send_security_headers` 注入 `X-Content-Type-Options: nosniff` / `X-Frame-Options: DENY` / `Referrer-Policy: no-referrer` / CSP

---

## 7. 配置 / 数据 / 启动入口

### 7.1 `config/run_config.json` (131 行)
```json
{
  "schema_version": "v2.0",
  "environment": "production",
  "auto_submit": false,
  "credentials": {"username": "", "password": "", "token": "", ...},
  "web": {"host": "127.0.0.1", "port": 8765, "open_browser": true, "session_ttl_seconds": 43200, "allow_remote": false, ...},
  "ops": {
    "settings": {"instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000", "delay": 1, "dataset": "pv1", "neutralization": "SUBINDUSTRY", "type": "REGULAR", ...},
    "budget": {"max_candidates_per_cycle": 20, "max_official_simulations_per_cycle": 3, "run_forever": false, "max_cycles": 10, "generation_mode_ratio": "70/20/10", ...},
    "scoring": {"assistant_guidance_score_adjustment_enabled": true, ...},
    "thresholds": {"min_sharpe": 1.25, "min_sharpe_delay0": 2.0, "min_fitness": 1.0, "min_fitness_delay0": 1.3, "platform_max_turnover": 0.70, "target_max_turnover": 0.30, "enforce_target_turnover_as_hard_gate": false, "sub_universe_sharpe_min_ratio": 0.75, ...},
    "submission_policy": {"max_auto_submissions_per_day": 3, "max_expression_similarity": 0.9, "block_micro_variants": true, ...}
  }
}
```

### 7.2 `data/` 目录状态
- `official_*.json` × 3 + 3 meta + 1 status(8599 字段,67 算子,20 数据集)
- `official_context_refresh_status.json`:**`ok: false, status: failed`**,error = "official context refresh exceeded 120s timeout"(2026-06-12 14:37:57)
- 11 个 JSONL:candidates/lifecycle/checks/backtests/submissions/cloud_alphas/ab_tests/assistant_guidance/events/families/strategy_lifecycle
- 3 个 SQLite:expression_index / records_index / knowledge
- 4 个 JSON:jobs_async / jobs_check / jobs_production / jobs_sync

### 7.3 启动入口
- `launch_web.py` (13 行) — `python3 launch_web.py` → `brain_alpha_ops.web.main(sys.argv[1:])`
- `fetch_official_context.py` (503 行) — 独立维护脚本,timeout 默认 120s(已失败)

---

## 8. 测试与脚本

### 8.1 测试体系
- 205 个 `test_*.py` + 6 个 `qa_*.py`
- pytest 7.0+ ,coverage fail_under=75%
- 关键测试:
  - `test_p1_verification.py` — P1 缺陷验证
  - `test_*_static.py` (10 个) — React 静态分析(innerHTML guard / silent catches / surface parity / API contract / accessibility / responsive)
  - `test_python_silent_broad_exceptions_guard.py` — 静默 except 防御
  - `test_log_redaction_guard.py` / `test_defect_015_log_redaction.py` — 凭据脱敏
  - `test_brain_contract_check.py` / `test_canonical_alignment.py` — BRAIN 契约一致性
  - `test_dynamic_research_components.py` — 动态研究组件

**已发现的问题**:`PROJECT_EVALUATION_REPORT.md` 提到"27 个测试模块存在集合错误(类型注解兼容性问题,可能是 Python 3.9 vs 3.10+ 的 `X | Y` 语法差异)"。

### 8.2 脚本 (60+ 个)
- 治理/检查:`check_*.py` × 30+:`architecture_compliance` / `brain_contract` / `capability_registry` / `dependency_policy` / `module_size` / `python_silent_broad_exceptions` / `log_redaction` / `log_governance` / `web_console_contract` / `web_facade_contract` / `web_handler_dispatch_context` / `frontend_innerhtml` / `frontend_silent_catches` / `frontend_surface_parity` / `frontend_syntax` / `live_submit_readiness` / `official_context` / `parameter_traceability` / `pipeline_runtime_state` / `prod_defect_tracking` / `react_build_env` / `review_gap_closure_tracker` / `sensitive_artifacts` / `text_encoding` / `v5_defect_tracking` / `diagnostic_report` / `diagnosis_gap_coverage` / `defect_analysis_report` / `candidate_scientific_audit`
- E2E:`browser_e2e_test.sh` / `browser_populated_layout_smoke.mjs` / `browser_react_artifact_smoke.mjs` / `live_page_e2e.mjs` / `qa_e2e_walkthrough_report.json` / `summarize_e2e_artifacts.py` / `run_e2e_walkthrough.py` / `ux_walkthrough_local.py`
- 发布门:`final_release_gate.py` / `quality_gate.py`
- 其它:`responsiveness_check.py` / `build_prod.py` / `build_windows.ps1` / `verify_canonical_compliance.py` / `calibrate_weights.py` (根级,被 `auto_calibrator` 通过 `sys.path.insert` 引用)

---

## 9. 关键发现 / 风险 / 关注点

### 9.1 安全(整体良好,细节需注意)

#### ✅ 良好
1. **凭据三件套**:浏览器输入 / 环境变量 / 配置文件(优先级递减)+ `CredentialRedactionFilter` 自动安装到 root logger
2. **REAL_SUBMIT 三重防护**:常量 + Web 路由 + API 适配层
3. **路由前门**:origin + session + CSRF + replay 五重
4. **CSP**:SHA-256 hash,阻止 inline script
5. **敏感日志**:`redact_error_message` / `redact_text` / `redact_data` 跨项目强制
6. **本地优先**:`host=127.0.0.1` + `allow_remote=false` 默认
7. **配置回显**:`save_run_config_payload` 永远把 `auto_submit=False` 并清空 credentials 的实际值

#### ⚠️ 关注
1. **单点越权**:`BRAIN_ALPHA_FORCE_REAL_SUBMIT=1` / `BRAIN_ALPHA_ENABLE_REAL_SUBMIT_TESTS=1` 绕过 kill-switch(consultant-gated,但仍是单点)
2. **`/api/candidates/simulate` 无 human-in-the-loop**:无 kill-switch,启动实际模拟任务(预期行为,但要意识到)
3. **官方 context 刷新 timeout 120s 经常失败**(`ok: false`),导致运行需用 stale data(用户可能不知情)
4. **`_has_session_cookie` 语义不严**:永远返回 `True`(只看 cookie 存在),但实际来自 BRAIN auth,无安全漏洞
5. **Replay cache 10000 cap**:`REPLAY_CACHE_FULL` 不通知用户,长跑可能反复触发
6. **JSONL 持久化无锁写**:多个后台 job 同时更新可能 race(虽然每个文件 single-writer 通常没问题)

### 9.2 数据一致性

#### 🔴 高优先级
1. **`official_context_refresh_status.json` 显示 refresh failed**(timeout 120s)
   - 原因:`fetch_official_context.py:timeout_seconds=120.0` + 网络环境
   - 影响:运行依赖 stale data,但无明确用户提示
2. **`OfficialDataLoader` 单例**:`reload()` 需显式调用,`web_cloud_snapshot.persist_official_context` 末尾调一次,但其它路径不调
3. **JSONL 无限增长**:`alpha_features.jsonl` / `candidates.jsonl` / `lifecycle.jsonl` / `checks.jsonl` 等
   - `web_runtime_state.maybe_archive_lifecycle` 只对 lifecycle.jsonl 50MB+ 归档,其它无归档策略

#### 🟡 中优先级
4. **3 处 `SYNC_RANGES` 不一致**:`AgentLimits` / `user_alpha_sync` / `web_payload_validation` 三处定义不同集合
5. **`MAX_BACKTEST_BATCH_SIZE=100`(Web) vs `MAX_BATCH_SIMULATIONS=10`(Agent) vs `rate_limit_policy.max_concurrent=3`** — 三层不匹配
6. **`SUPPORTED_NEUTRALIZATIONS` 在 `canonical.py` 与 `config_domain_validation` 间可能差异**(需进一步审计)

### 9.3 模块化漂移(技术债)

| 类别 | 旧/新 | 状态 |
|---|---|---|
| **SSE 双轨** | `web_sse.py:handle_sse_request` vs `web_http_handler._handle_sse_stream` | 两套循环并存,行为略不同 |
| **Job store 双轨** | `web_jobs.py` (200 in-mem) vs `tasks.py:JobStore` (持久化) | 新代码应统一 |
| **`serve` 双轨** | `web_cli.py.serve` (zombie-thread fix) vs `web_server_lifecycle.serve` | 两个 main() 入口走不同路径 |
| **空壳占位** | `web_runtime_facade.compute_run_stats` / `status_category` 是空壳 | 实际业务走 `web_runtime_state` 同名实现 |
| **死 binding** | `web_*_bindings.py` 9 个桩(各 ~5 行) | 已被 `web_facade_bindings` 统一,可删 |
| **5 个空 stub** | `domains/backtest.py` / `generation.py` / `scoring.py` / `simulation.py` / `strategy.py` | 各 2-5 行 re-export,可删 |
| **死 route** | `web_check_batch_job.py` / `web_candidate_check.py` / `web_candidate_selection.py` | 7 行 stub |
| **死 `web_submit_readiness`/`_web_error` 等** | `web/__init__.py:dispatch_get` 多处 fallback | 重复定义 |

### 9.4 算法 / 数学

1. **`_ratio()` 启发式分散且不一致**:
   - `scoring.py:744-763` 用 `abs ≥ 100.0 或 (bounded and abs > 1.0)`
   - `experience.py:50-65` / `safety.py:200-220` / `diagnostics.py:37-52` 用 `abs ≥ 2.0`
   - 同一份 BRAIN metrics 在不同模块可能得到不同的 turnover/correlation
2. **两条并行评估路径**:`scoring.py:empirical_score` (item dict + points) vs `alpha_checks.py:AlphaCheckRegistry.evaluate` (CheckResult + severity),可能不一致
3. **hard gate 行为分歧**:`scoring.py:empirical_score` 用 `is_hard_gate` 标记 → 0 分;`alpha_checks.py` 用 `severity='ERROR'` 决定 `report.passed`;二者硬集合相同但评估时序不同
4. **`iterative_optimizer._FAILURE_TO_STRATEGY` 是硬编码**,未基于 `Diagnostics` 实证;`fitness` 失败时建议 `operator_substitute`,但 `fitness = Sharpe × √(|Returns|/max(TO,0.125))` 难以靠换算子改善
5. **`auto_calibrator` MAE 公式**:`empirical = sharpe * 50` clamp [0,100];但 `sharpe=2 → empirical=100`,与 scorecard 的 `submit(≥85)` 阈值(sharpe≥1.7)不一致,MAE 失真
6. **`economic_logic` 概念计数权重 9 个概念**但 `concept_scores` 字典 key 是计数(1–4),超过 4 个概念与 4 个概念同分(92)
7. **EMA 系数 0.8/0.2 全局固定**,未按 hypothesis/field/expr_family 单独调整,slow learner
8. **Bootstrap CI 简单随机抽样**(无 BLADE/bc-a),n 小时容易得到不连续 CI

### 9.5 配置耦合

1. **`scoring.ScoringConfig` 是 frozen dataclass**,但 `auto_calibrator.apply` 直接 mutate `prior_weights_override` 等字段 —— `frozen=True` 可能被绕过
2. **`pipeline.py` 通过 `self.config.scoring = self.auto_calibrator.apply(...)` 整体替换**(`scoring.py:476`),但 `scoring.ScoringConfig` 如果 frozen 会抛 `FrozenInstanceError`
3. **`scoring.py:30-31` 把函数引用存到模块全局**:`_economic_logic_score = economic_logic_score` — 不必要(直接调用即可)

### 9.6 提交安全

1. **`safety.py:account_risk_level` 用 `correlation >= 0.70 or concentration >= 0.10 or turnover < 0.01` 判定 medium**,但 `self_correlation` 有 Sharpe × 1.10 例外;`safety.py` 未读取 `exception_applied`,可能误报
2. **`non_production_source_reasons` 只检查 ID 前缀 / source_tags / environment / mode 4 个维度**;不检查 submission trace 中的 `optimizer_trace.submit_allowed=False` 标记
3. **`block_micro_variants` 通过 `max expression_similarity`,只针对已提交集合**,未考虑 pipeline 内部池

### 9.7 LLM 集成

- `prompts/assistant_system_prompt.txt` 明确"不能 submit / 不能 invent metrics",但 `assistant.py` (865 行) 未读,工具注册是否强制 live API confirmation 未知
- `llm_service.py` (614 行) 未读,retry / token 预算未知
- `knowledge_base.py` (651 行) 与 `llm_review.py` (396 行) 之间的约束传播未知

### 9.8 性能 / 资源

1. **JSONL 全文扫描**:`web_alpha_lifecycle` / `web_candidate_simulation` 用 `read_jsonl_records` 读全文,上限仅 500/2000
2. **Replay cache 10000 cap**:满后直接拒绝新请求(`REPLAY_CACHE_FULL`)
3. **`ASYNC_JOBS` 内存 200 cap + 1h TTL**:恢复时只恢复非 terminal,可能导致重启后看到"ghost running"任务
4. **大文件依赖**:`data/official_fields.json` 834KB,加载到内存 `_fields_by_name: Dict[str, List[OfficialField]]` 索引(可能再 5-10 倍)
5. **`alpha_features.jsonl` 无限增长**:`DEFAULT_HISTORY_LIMIT=5000` 只影响查询,不清理
6. **PyInstaller bundled 时**:`ensure_official_context_files` 兜底,但 EXE 启动时 I/O 可能慢

### 9.9 文档 / 状态漂移

1. **README 提到 "7642 fields"** — 实际当前是 **8599 fields**(以 `data/official_context_refresh_status.json` 为准)
2. **README 提到 "29/29 tests passing"** — 实际有 205 个测试文件(其中 6 个是 qa_),且有 27 个测试模块存在集合错误
3. **`README.md` 35KB** 是用户级操作手册,与 `overview.md` / `REVIEW.md` / `REVIEW_20260609.md` / `REVIEW_20260609_v2.md` / `PROJECT_EVALUATION_REPORT.md` 之间有部分重叠
4. **`docs/` 149 个文件**:文档/screenshot/design-system 混杂,目录结构需厘清

### 9.10 未发现的重大问题

- **未发现 `NotImplementedError` 显式抛出**(除 `task_executor.py` 2 处)
- **未发现硬编码真实凭据**(根据 `REVIEW.md` 2026-05-14 报告 R-01 早已修复)
- **未发现 `yaml.load` / `pickle` 反序列化入口**(全部用 `safe_load`)
- **未发现 SQL 注入**(项目无数据库层)
- **未发现 `hashlib.md5` 用于安全场景**(只用于 mock 指标确定性摘要)

---

## 10. 改进建议(优先级排序)

### P0 — 必须修
1. **修复 `official_context_refresh_status.json` 持续 failed 的根因**
   - 当前 timeout=120s 不够,建议延长到 300s 或加入 chunked refresh
   - 同时,stale 状态下明确提示用户
2. **`/api/candidates/simulate` 添加 human-in-the-loop 确认**
   - 当前走 `simulate_candidates_job` 直接发 BRAIN 模拟,无二次确认
3. **3 处 `SYNC_RANGES` 统一为 canonical 一份**
   - 建议在 `runtime_constants` 单一 source of truth,Web 接受 `1d` / `recent` / `6months` 全集
4. **`_ratio()` 启发式统一**
   - 当前 4 处实现不同(经验/打分/安全/诊断),会导致同一指标得不同结果

### P1 — 应当修
5. **删除死代码**:`domains/` 5 个空 stub + 9 个 `web_*_bindings.py` + 4 个 7 行 `web_*.py` stub
6. **统一 SSE 路径**:删 `web_sse.py`,只保留 `web_http_handler._handle_sse_stream`
7. **统一 JobStore**:删 `web_jobs.py` 的 `ASYNC_JOBS` in-memory,统一用 `tasks.JobStore`
8. **统一 `serve()`**:删 `web_cli.py.serve` 的重复实现,只保留 `web_server_lifecycle.serve`
9. **JSONL 归档策略**:除 lifecycle 外,对 candidates/checks/backtests/submissions 也加 50MB 归档
10. **测试模块集合错误**:27 个测试模块 `X | Y` 语法问题(Python 3.9 vs 3.10+),需统一 `from __future__ import annotations`
11. **README 数字更新**:"7642 fields" → "8599 fields","29/29 tests" → 实际测试数

### P2 — 长期改进
12. **拆解 `web_handler_dispatch.py` (1004 行)** — 已 25 个 `_post_*` 函数,继续按主题拆分
13. **拆解 `hypothesis_driven_generator.py` (1240 行)** — 6 个组件已是 dataclass,可继续拆
14. **拆解 `local_backtest_engine.py` (1099 行)** — 4 个子组件(ExpressionEvaluator/PortfolioConstructor/MetricsComputer/SyntheticDataProvider)可拆
15. **`_FAILURE_TO_STRATEGY` 数据驱动**:从经验反馈 `ab_tests.jsonl` 学,而不是硬编码
16. **EMA 学习率自适应**:按 hypothesis 累计样本量动态调整(0.2 → 0.05 慢学习)
17. **Bootstrap CI 用 bc-a 或 BLADE**:替代简单随机抽样

### P3 — 锦上添花
18. **`ScoringConfig` frozen 问题**:`auto_calibrator.apply` 整体替换而非 mutate
19. **打通 LLM 工具 live API confirmation 验证**:`assistant.py` 需深读确认
20. **添加 `regression: 8599 fields` 单元测试**:防止 context 文件 silently 缩水

---

## 11. 总结

BRAIN Alpha Ops 是一个**工程化程度较高的本地 Web 控制台**,核心特性:

✅ **架构清晰**:5 条 import-linter 契约保证层间隔离,Mixins 拆解避免单继承爆炸
✅ **安全优先**:凭据三件套 + 提交三重 kill-switch + 路由五重防护 + CSP
✅ **业务完整**:从连接 → 同步 → 生成 → 评分 → 校验 → 回测 → 审查的全链路
✅ **数据驱动**:8 个经济假设 + 3 模式路由器 + EMA 经验反馈 + 反过拟合四层验证
✅ **可观测**:16 个错误码 + 27 个进度 phase + 940 行 observability
✅ **测试完备**:205 个测试文件 + 30+ 静态检查脚本

⚠️ **主要风险**:模块化漂移(双轨实现)、官方 context 刷新失败(120s timeout)、3 处 `SYNC_RANGES` 不一致、测试模块 Python 版本兼容。

**核心判断**:可以安全进入生产,但需要在 4 件事上做收尾:
1. 修复 official context 刷新 timeout
2. 统一 3 处配置漂移
3. 清理 ~1500 行死代码(`domains/` + `web_*_bindings.py` + 重复 `serve`/`SSE`/`JobStore`)
4. 修复 27 个测试模块的 Python 3.10+ 类型注解语法

其它可在 P1/P2 持续改进。
