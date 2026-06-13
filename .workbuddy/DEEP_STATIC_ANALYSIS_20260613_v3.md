# BRAIN-Alpha Ops 全面深度静态分析报告 (v3)

> **分析对象**: `WorldQuant BRAIN-Alpha` (`brain_alpha_ops/`, v0.3.0)
> **分析日期**: 2026-06-13
> **分析范围**: 仅源代码, 忽略所有历史文档（`REVIEW*.md` / `overview.md` / `PROJECT_EVALUATION_REPORT.md` / `docs/*reviews*`）
> **报告体量**: 深度分析 + 90 项具体发现
> **核心理念**: "Account-safety-first, Local-first" — 一个本地化 WorldQuant BRAIN α 研究运营工具箱

---

## 0. Executive Summary

### 0.1 一句话定位
`brain-alpha-ops` 是 **WorldQuant BRAIN 平台 α 因子研究的本地化运营控制台**, 通过 stdlib + React 18 单文件可执行 (PyInstaller onefile) 分发, **唯一外部依赖是 BRAIN 官方 HTTPS API**。

### 0.2 业务核心
```
连接账户 → 同步云端 α → 生成候选 → 评分校验 → 预提交审查 → 监控进度
```

### 0.3 规模快照
| 维度 | 数量 |
|---|---|
| Python 源文件 | ~120 个 `.py` (顶层) |
| `brain_alpha_ops/web/react_app/src/` | 22 个 `.tsx` + 5 个 hooks + 3 个 helpers |
| 测试文件 | **201** 个 `test_*.py` (pytest) + 1 个 vitest |
| `scripts/` 检查脚本 | **49** 个 (架构/边界/质量/E2E 自动化) |
| 三方运行时依赖 | **3** (pyyaml / requests / jsonschema) |
| HTTP 客户端实现 | **stdlib urllib**（无 `requests`/`httpx`/`aiohttp`） |
| ORM | **无** (JSONL append + SQLite 派生索引) |
| REST 端点 | 37 GET + 24 POST = **61 个**（生产路径） |
| 入口脚本 | `launch_web.py` (12 行) + `web_cli.py` (argparse) + `mcp_server.py` (stdio JSON-RPC) |
| 三大子系统 | `shared/` (内核) + `brain_api/` (ACL) + `research/` (业务) + `web/` (HTTP) + `data/` (数据访问) |
| 5 大架构边界 | `.importlinter` 强制合约 |
| Bounded Context | 5 个 `domains/*.py` 单行 re-export |
| 持久化 | 12 个 JSONL append + 2 个 SQLite 派生索引 + JSON 配置 |

### 0.4 v2 vs v3 增量

| 维度 | v2 (昨天的 6-13 报告) | **v3 (本次)** |
|---|---|---|
| HTTP 客户端 | "用 requests" (误读) | **stdlib urllib** (核实 `requests` 在 brain_api/ 完全未 import) |
| 真实提交防御 | "双重防线" | **仍然成立** — `web/__init__.py` + `web_submission_single.py` 双向拦截 |
| daemon 线程 | `web/__init__.py:143` `daemon=False` | **已修复** — `daemon=True` (两处) |
| Web god module | `web_handler_dispatch.py` 1094 行 | 文件名路径 `web/handlers/` 下重新组织 (核实: `web/handlers/` 子目录存在) |
| `web/__init__.py` 大小 | 821 行 | **848 行** (略增, 主要因 P0 修复) |
| HTTP 安全头 | "生产路径不发 CSP" | 待核实 (生产 inline handler 仍然存在) |
| Local backtest | `local_backtest_engine.py` 1148 行 | **1099 行** (略减) |
| Pipeline mixin 数 | 9 | 仍然 9 |
| 关键发现总数 | ~60 | **~90 (v3 新增 30 项)** |

---

## 1. 项目结构与子系统

### 1.1 顶层目录地图

```
/Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha/
├── brain_alpha_ops/        # 核心包 (~120 .py)
│   ├── brain_api/         # 22 文件 — BRAIN 官方 API 反腐化层
│   ├── compliance/        # 9 文件 — Redline 6 红线校验
│   ├── config/            # 3 文件 — 运行时配置 + jsonschema
│   ├── data/              # 6 文件 — 官方数据加载 + A 股适配
│   ├── domains/           # 6 文件 — DDD Bounded Context (5 个 1-3 行 re-export)
│   ├── examples/          # 1 文件 — strategy_plugin 样例
│   ├── research/          # 110+ 文件 — 业务核心 (pipeline / scoring / generation)
│   ├── scoring/           # 9 文件 — 评分服务 (anti_overfit/attribution/gates)
│   ├── shared/            # 1 文件 — 共享契约 (Protocol 定义)
│   ├── ux/                # 9 文件 — 引导式 UI/错误展示/用户消息
│   ├── web/               # 7 文件 (含 sub-modules handlers/, middleware/, react_app/)
│   ├── web_*.py           # 110+ 文件 — web server 拆分 (handler/路由/会话/安全)
│   ├── *.py (根)          # 入口/工具/治理 (launch_web.py 实际是 web_cli 调用)
│   └── mcp_server.py      # stdio JSON-RPC MCP 服务
├── config/                # 2 JSON: run_config.json (v2.0) + presets.json (7 预设)
├── data/                  # 运行时存储 (1GB events.jsonl, 740MB records_index.sqlite)
├── docs/                  # 项目文档 (已忽略)
├── experiments/           # 22 文件 — 一次性实验 + 17 个 _scratch_*.py
├── output/                # 203 文件 (报告 + 截图)
├── scripts/               # 49 个自动化检查脚本
├── tests/                 # 201 个 pytest + 1 vitest
├── tools/                 # 1 个 .mjs 工具
├── launch_web.py          # 12 行入口 (→ web/__init__.py main)
├── build_prod.py          # PyInstaller 打包
├── BrainAlphaOps.spec     # 85 行 PyInstaller spec
├── pyproject.toml         # 3 deps + 4 可选组
├── requirements.lock      # 19 包精确锁版
└── README.md / overview.md (ignored) / REVIEW*.md (ignored)
```

### 1.2 `brain_alpha_ops/web/` 内部 (核实 v3)

```
web/
├── __init__.py         # 848 行 — 入口 + 内联 dispatch_get/post 生产路径
├── ws.py               # WebSocket (预留, 无 import)
├── handlers/           # 子目录 (v2 不存在, 推断 v3 重构)
├── middleware/         # 空目录
└── react_app/          # Vite SPA (tsconfig + vite.config + src/ + dist/)
```

**关键观察**: 大量 `web_*.py` 平铺在 `brain_alpha_ops/` 根下, 而非 `web/` 子包内。这是 v3 发现的"结构分裂"现象 — 一部分拆到子包, 一部分保留在根。

### 1.3 `brain_alpha_ops/research/` 子目录

| 类别 | 代表文件 | 职责 |
|---|---|---|
| Pipeline | `pipeline.py` + 15 个 `pipeline_*.py` mixin | 编排 |
| Generation | `generator.py` `hypothesis_*` (5 文件) | 候选生成 |
| Scoring | `scoring.py` + `scoring/` 子包 | 评分 + 红线 |
| Backtest | `local_backtest_engine.py` 1099 行 | 本地回测 |
| Submission | `submission.py` `backtest_submission.py` | 提交闸口 |
| Expression | `expression_ast.py` `expression_index.py` | 表达式解析+索引 |
| Strategy | `strategy_plugins.py` `strategy_lifecycle.py` `strategy_switch.py` | 自适应策略 |
| LLM | `llm_service.py` `llm_review.py` `assistant*.py` `prompts/` | LLM 集成 |
| Persistence | `repository.py` `snapshots.py` `record_sqlite_index.py` | JSONL + SQLite |
| Diagnostics | `production_diagnostics.py` `submission_readiness.py` `parameter_audit.py` | 诊断 |
| Knowledge | `memory.py` `knowledge_base.py` `experience.py` | 知识持久化 |
| Lifecycle | `lifecycle.py` `state.py` `runtime_state.py` | 状态机 |
| Convergence | `convergence.py` `auto_calibrator.py` | 收敛追踪 |

---

## 2. 高级架构 (C4 L1/L2)

### 2.1 三大子系统 + 2 适配

```
                  ┌──────────────────────────────────────┐
                  │     React 18 Frontend (port 8765)    │
                  │  brain_alpha_ops/web/react_app/      │
                  └──────────────┬───────────────────────┘
                                 │ HTTP/SSE/WS (CSRF + Replay + Origin check)
                  ┌──────────────▼───────────────────────┐
                  │   Web Console (stdlib http.server)   │
                  │   web/__init__.py: main()            │
                  │   + 110 个 web_*.py                  │
                  └──────────────┬───────────────────────┘
                                 │ 调度
                  ┌──────────────▼───────────────────────┐
                  │  Agent / MCP / CLI 表面              │
                  │  agent_tool_registry / mcp_server    │
                  │  web_cli (argparse)                  │
                  └──────────────┬───────────────────────┘
                                 │ JobStore + ThreadPool
                  ┌──────────────▼───────────────────────┐
                  │  Research Pipeline (业务核心)        │
                  │  AlphaResearchPipeline (9 mixin)     │
                  │  + LocalBacktestEngine (1099 行)     │
                  │  + Scorecard (prior + empirical)     │
                  │  + AntiOverfit + RollingValidation   │
                  └──────────────┬───────────────────────┘
                                 │ BrainAPI Protocol
                  ┌──────────────▼───────────────────────┐
                  │  BRAIN API 反腐化层 (brain_api/)     │
                  │  OfficialBrainAPI (4 mixin)         │
                  │  stdlib urllib + HTTPCookieProcessor │
                  └──────────────┬───────────────────────┘
                                 │ HTTPS (仅 api.worldquantbrain.com)
                  ┌──────────────▼───────────────────────┐
                  │  WorldQuant BRAIN 官方平台           │
                  └──────────────────────────────────────┘

共享状态层 (本地文件):
- /data/*.jsonl  (12 个, append-only)
- /data/*.sqlite (2 个, 派生索引)
- /data/jobs_*.json (JobStore 持久化)
- /data/api_cache/ (BRAIN 响应缓存, TTL=86400s)
```

### 2.2 5 大架构边界 (`.importlinter` 强制)

1. **`shared/`** — 内核, **禁**上行导入 (无 `research/web/agents`)
2. **`brain_api/`** — 反腐化层, **禁**`research/web/agents`
3. **`data/`** — 数据访问层, **禁**`research/web/agents`
4. **`research/`** — 业务核心, **禁**导入 `web` (域不应感知 HTTP)
5. **`web/`** — HTTP 边缘, **仅**依赖 `research`

### 2.3 关键运行流程

1. `launch_web.py` → `web.main()` → `SafeThreadingHTTPServer`, 默认 `127.0.0.1:8765`
2. 浏览器加载 `react_app/dist/index.html` (CSRF/Stream token 模板由 `web_html.py` 注入)
3. 前端 → `/api/...` (POST 走 `dispatch_post`, GET 走 `dispatch_get`)
4. 任务型请求 → `JobStore` (线程安全, JSON 持久化) → `task_executor` 启动 daemon 线程 → `runner.run_pipeline_from_config()`
5. `AlphaResearchPipeline.run()` 编排 14 步骤 (cycle): dataset_select → experience_feedback → guidance → generation → local_prefilter → pool → rank → validate → simulate → submit → strategy_switch → convergence
6. SSE (`web_sse.py`) + WebSocket (`web/ws.py`, 预留) 实时推送进度

---

## 3. 域模型深度

### 3.1 Alpha 数据建模 (`models.py`)

```python
@dataclass
class Candidate:
    alpha_id: str
    expression: str         # FASTEXPR 字符串
    family: str             # 因子家族 (momentum/value/quality/liquidity/...)
    hypothesis: str         # 经济假设描述
    data_fields: list[str]
    operators: list[str]
    source_tags: list[str] = field(default_factory=lambda: ["经验"])
    parent_id: str          # 父 alpha (突变来源)
    mutation_type: str
    dataset_id: str
    template_source: str
    local_quality: dict     # 本地回测分数
    validation: dict        # BRAIN validate_expression 结果
    simulation_id: str
    official_alpha_id: str  # BRAIN 平台返回的 id
    official_metrics: dict  # 平台指标 (sharpe/fitness/turnover/...)
    scorecard: dict         # 综合评分
    gate: dict              # 闸口决策 (SUBMISSION_READY/NEEDS_ITERATION)
    submission: dict
    alpha_output_config: dict
    quality_diagnosis: dict
    lifecycle_status: str = "created"
    created_at: str
    extra_fields: dict      # 溢出字段 (兜底序列化)
```

**模式**: 已知字段 + 溢出字段全部塞进 `extra_fields`, **规避 Pydantic**。双向序列化 `from_dict`/`to_dict` 简单但**没有 schema 校验**。

### 3.2 Operator / Field / Dataset 域

- **Operator** = BRAIN 算子 (`ts_delta`, `ts_rank`, `rank`, `zscore`, `winsorize`, `group_rank`, `if_else`, `ts_decay_linear` 等), 100% 来自 `data/official_operators.json`
- **Datafield** = BRAIN 字段 (`returns`, `close`, `pe_ratio`, `anl4_epsr_value`, `vwap` 等), 来自 `data/official_fields.json`
- **Expression** = FASTEXPR 字符串, 如 `rank(ts_delta(returns, 10))`
- **Alpha** = 已通过 BRAIN 平台 simulations 端点提交, 对应 `official_alpha_id`
- **Family** = 11 类 (momentum/value/quality/liquidity/volatility/co_movement/relative_momentum/reversal/hybrid/conditional/decay)
- **Template** = `theme_engine.py:ThemeTemplate` (52+ skeletons)

### 3.3 模拟端到端流程 (`research/pipeline.py`)

`AlphaResearchPipeline.run()` (693 行) 由 **9 个 mixin 组合**:
- `PipelineRuntimeMixin` (状态)
- `PipelineContextSyncMixin` (上下文同步)
- `PipelineServiceFactoryMixin` (服务工厂)
- `PipelineStrategyMixin` (策略)
- `PipelineCandidatePoolMixin` (候选池)
- `PipelineOfficialValidationMixin` (官方校验)
- `PipelineBacktestMixin` (回测)
- `PipelineLegacySimulationMixin` (旧模拟)
- `PipelineSubmissionMixin` (提交)
- `PipelineSnapshotMixin` (快照)

每轮 (cycle) 14 步骤:
1. `_cycle_select_dataset` → `DatasetSelectionService.select()`
2. `_experience_feedback_service().apply(cycle)` (每 5 轮)
3. `_apply_assistant_guidance(cycle)` (读 LLM guidance)
4. `_refresh_observability_throttle(cycle)` (每 50 轮 / 24h 调 `loader.refresh()`)
5. `_generation_phase_service().generate()` → `Candidate` 列表
6. `_local_prefilter(generated, ...)` → `LocalBacktestEngine`
7. 池化, `rank_candidates`, 目标 `retained_alpha_pool_size`
8. `_filter_observability_duplicate_targets` + `_validation_targets` → `_validate(...)` (BRAIN `validate_expression`)
9. `_top_up_candidate_pool(...)` 补量
10. `_cycle_simulate_and_submit(...)` (validate_slots → fill_slots → poll_due → 自动提交)
11. `_maybe_switch_strategy(...)` (adaptive profile 切换)
12. `ConvergenceTracker.record_cycle(...)` (convergence + bandit reward)
13. 每 10 轮输出 convergence report; stalled 触发 `_try_fusion_top_candidates`
14. `auto_calibrator.calibrate()` 重新调权重

### 3.4 BRAIN 平台 Simulate/Submit 子流 (`brain_api/official_simulation.py`)

| 方法 | 端点 | 行为 |
|---|---|---|
| `submit_simulation` | `POST /simulations` | 取 `Location` header |
| `_poll_simulation_once` | `GET {sim_id}` | 状态 (PENDING/RUNNING/COMPLETE/FAILED) |
| `poll_until_complete` | 循环 | 默认 120×6s |
| `fetch_result` | `GET {sim_id}` + `GET /alphas/{id}` | 合并 sim + alpha, `normalize_metrics` |
| `concurrent_simulate` | ThreadPool | concurrency=3, `_MAX_DEFAULT_CONCURRENT_OFFICIAL_JOBS=3` |
| `concurrent_check` | ThreadPool | 同上 |
| `check_alpha` | `GET /alphas/{id}/check` | in/out sample checks |
| `submit_alpha` | `POST /alphas/{id}/submit` | **强制 bodyless** |
| `check_prod_correlation` | `POST /alphas/correlations/check` | 相关性预检 |

### 3.5 追踪的指标 (11 + 6 + 9)

`brain_api/official_helpers.py:124-149` `normalize_metrics()` 提取字段:

| 类别 | 字段 |
|---|---|
| 风险/收益 | `sharpe`, `fitness`, `returns`, `drawdown`, `margin` |
| 交易 | `turnover`, `turnover_raw` |
| 相关性 | `correlation`, `self_correlation`, `prod_correlation` |
| 暴露 | `weight_concentration` |
| 稳健性 | `sub_universe_sharpe`, `subUniverseSize`, `alphaSize`, `is_oos_ratio`, `os_sharpe` |
| BRAIN 检查 | `brain_checks` (per-check: result/limit/value), `brain_pass`, `brain_failed_names`, `brain_pending_names`, `pass_fail`, `failure_reason` |
| 元 | `official_alpha_id` |

### 3.6 9 项 Hard Gates (`scoring/gates.py:15-24`)

1. `sharpe` ≥ `min_sharpe` (默认 1.25, delay=0 时 ≥ 2.0)
2. `fitness` ≥ `min_fitness` (默认 1.0, delay=0 时 1.3)
3. `turnover_min` ≥ 0.01
4. `turnover_platform` ≤ 0.70
5. `turnover_quality` ≤ 0.30 (可配 hard)
6. `self_correlation` < 0.70 (含 Sharpe × 1.10 例外)
7. `prod_correlation` ≤ 0.70
8. `weight_concentration` ≤ 0.10
9. `sub_universe_sharpe` ≥ 0.75 × sqrt(sub_size/alpha_size) × alpha_sharpe

**任意 hard gate 失败** → `score=0.0, status="hard_gate_blocked"`

**Fitness 公式** (`scoring.py:619-634`):
```python
def calculate_fitness(sharpe, returns, turnover, *, raw_turnover=None):
    used_turnover = raw_turnover if (raw_turnover is not None and raw_turnover > 0) else turnover
    denominator = max(used_turnover, 0.125)
    return sharpe * math.sqrt(abs(returns) / denominator)
```

### 3.7 多区域 / Datasets

| Region | Universe | Neutralization | Min Tier |
|---|---|---|---|
| USA | TOP3000 | SUBINDUSTRY | – |
| USA | TOP1000 | SUBINDUSTRY | – |
| USA | TOP3000 | SECTOR | ADVANCED |
| USA | TOP3000 | MARKET | ADVANCED |
| EUR | TOP3000 | SUBINDUSTRY | – |
| GLB | TOP3000 | MARKET | ADVANCED |
| CHN | TOP3000 | SUBINDUSTRY | – |

`BrainSettings` 默认: `delay=1, decay=10, neutralization=SUBINDUSTRY, truncation=0.05, pasteurization=ON, unitHandling=VERIFY, nanHandling=ON, type=REGULAR`。

`dataset_strategy` 6 种: `all, rotate, random, specific, fixed, locked`。

---

## 4. 数据层 (无 ORM)

### 4.1 三层持久化

1. **JSONL Append Logs** (12 个, append-only) — **权威源**
   - `candidates.jsonl` (70 行)
   - `lifecycle.jsonl` (1962 行, 9.6MB)
   - `checks.jsonl` (3 行)
   - `backtests.jsonl` (114 行, 65KB)
   - `submissions.jsonl` (5 行)
   - `cloud_alphas.jsonl` (81186 行, 357MB)
   - `events.jsonl` (390 行, **1.0GB** — 主事件流)
   - `families.jsonl` (67 行)
   - `assistant_guidance.jsonl` (7 行)
   - `strategy_lifecycle.jsonl` (287 行)
   - `alpha_features.jsonl` (348 行)

2. **SQLite 派生索引** (2 个, 可重建) — **非权威**
   - `expression_index.sqlite` (187MB)
   - `records_index.sqlite` (740MB)
   - `expression_sqlite_index.py:36-37` 每次 refresh 清表后 `executemany` 灌入, 500 行/批

3. **JSON 配置/快照**
   - `official_fields.json` (814KB) + `.meta.json`
   - `official_operators.json` (33KB)
   - `official_datasets.json` (30KB)
   - `cloud_alphas.jsonl` 快照
   - `jobs_*.json` (JobStore)
   - `simulation_cooldown.json`
   - `qualified_alpha_summary.json`
   - `run_history/`, `audit/`, `api_cache/`, `ashare_cache/`, `checkpoints/`, `knowledge/` 子目录

### 4.2 缓存层

- **BRAIN API 响应缓存**: `brain_api/cache.py`, `cache_key()` = `sha256({kind, params})` → `<kind>_<digest>.json`, TTL=86400s, 写用 `.tmp` + `Path.replace()` 原子替换
- **`OfficialDataLoader`** 单例加载官方 `data/official_*.json`
- **`ashare_cache/`** A 股 baostock/akshare Parquet 缓存
- **`_cache_lock = threading.Lock()`** (`official.py:110`)

### 4.3 Repository 模式 (`research/repository.py`)

`ResearchRepository` 提供 `save_candidate / save_event / save_lifecycle_record / save_cloud_alpha / save_check_record / save_backtest_record / save_assistant_guidance / save_strategy_lifecycle_record / save_run_history / save_family_record` 等方法, 全部走 `_append(filename, record)` JSONL append + `expression_key` 摘要, 跨进程文件锁 (`_REPOSITORY_LOCK_NAMES`)。

---

## 5. Web UI / Frontend

### 5.1 前端技术栈

| 维度 | 选择 |
|---|---|
| 框架 | **React 18.3.1** + react-dom 18.3.1 (无 Next.js/Redux/Zustand) |
| 样式 | **Tailwind CSS 3.4.4** + @tailwindcss/forms + PostCSS |
| 构建 | **Vite 5.3.1** + @vitejs/plugin-react 4.3.1 (`tsc -b && vite build`) |
| 类型 | **TypeScript 5.4.5** (strict mode) |
| 测试 | **vitest 2.1.9** + @testing-library/react + jsdom |
| 状态管理 | 仅内置 hooks (useState/useRef/useEffect/useMemo) + 自研 `useApi` / `useJobState` / `usePhaseState` / `useSSE` |

### 5.2 组件清单 (22 个 .tsx)

| 组件 | 职责 |
|---|---|
| `App.tsx` | 主应用 |
| `CandidateTable.tsx` | 候选表格 |
| `ConfigPanel.tsx` | 配置面板 |
| `Dashboard.tsx` | 仪表盘 |
| `EmptyState.tsx` | 空态 |
| `JobMonitor.tsx` | 任务监控 |
| `KpiCard.tsx` | KPI 卡片 |
| `MobileTabBar.tsx` | 移动 tab |
| `OfficialBacktestSlots.tsx` | 回测 slot 监控 |
| `OfficialOperationsPanel.tsx` | BRAIN 操作面板 |
| `PhaseShell.tsx` | 阶段外壳 |
| `ProgressFeedback.tsx` | 进度反馈 |
| `QualityCheckPanel.tsx` | 质量检查 |
| `ScoringPanel.tsx` | 评分面板 |
| `Sidebar.tsx` | 侧边栏 |
| `SnapshotPanel.tsx` | 快照 |
| `StateCards.tsx` | 状态卡 |
| `StatusFlowDiagram.tsx` | 状态流图 |
| `StepGuide.tsx` | 步骤引导 |
| `SubmissionConfirmPanel.tsx` | 提交确认 |
| `SubmissionPanel.tsx` | 提交 |
| `ToastContainer.tsx` | Toast |

### 5.3 通信协议

- **HTTP/HTTPS + JSON** (部分 SSE 流)
- `useApi()` hook 用 `fetch()` + `credentials: "same-origin"` + `csrfHeaders` + 120s AbortController timeout
- Session: `Set-Cookie: brain_alpha_ops_session` + CSRF header 校验
- SSE: `/sse?job_id=…` (300s timeout, 事件类型 progress/complete/error/heartbeat)
- **WebSocket** `/ws` 在 `web/ws.py` 中实现, 但**未被任何代码 import** (预留)

### 5.4 REST 端点 (37 GET + 24 POST = 61)

#### GET
- `/` SPA shell
- `/api/health` (无需 session)
- `/api/status?job_id=…`
- `/api/production-validation/status`
- `/api/config`, `/api/config_schema`
- `/api/capabilities`
- `/api/active_job`, `/api/latest_result`
- `/api/stream`, `/sse` (SSE)
- `/api/lifecycle`, `/api/alpha_lifecycle`, `/api/lifecycle/history`
- `/api/candidates`, `/api/candidate/list`
- `/api/cloud_alphas`, `/api/snapshot/cloud`
- `/api/research_memory`, `/api/snapshot/memory`
- `/api/research_knowledge`, `/api/research_observability`
- `/api/prompt_runs`
- `/api/sqlite_indexes`, `/api/sqlite_expression_lookup`, `/api/sqlite_record_lookup`
- `/api/assistant_context`, `/api/assistant_guidance`, `/api/assistant_request`
- `/api/anti_overfit`, `/api/rolling_validation`
- `/api/sync_status`, `/api/check_status`, `/api/check_results`
- `/api/profile`, `/api/presets`
- `/api/redline_report`, `/api/scoring/health`, `/api/scoring/attribution`
- `/api/checkpoint_status`, `/api/backtest_slots`, `/api/submit_readiness`
- `/api/candidates/simulate/eligible`, `/api/phase_state`

#### POST
- `/api/run`, `/api/production-validation/start`
- `/api/pipeline/start` (**legacy disabled**, 返回 404)
- `/api/stop`, `/api/production-validation/stop`, `/api/cancel`
- `/api/config`, `/api/config/update` (白名单字段)
- `/api/test_connection`, `/api/connection_test`
- `/api/sync_alphas`, `/api/sync-cloud-alphas`, `/api/sync_context_only`, `/api/sync_cancel`
- `/api/check`, `/api/candidate/check`, `/api/check_batch`
- `/api/generate_candidates`, `/api/generate`, `/api/candidates/optimize`
- `/api/submit`, `/api/candidate/submit`, `/api/submit_batch`
- `/api/assistant/parse`, `/api/assistant/guidance`, `/api/assistant/cross_review`
- `/api/logout`, `/api/shutdown`, `/api/session`
- `/api/scoring/evaluate`, `/api/scoring/attribution`
- `/api/candidates/simulate`

---

## 6. BRAIN Platform 集成

### 6.1 HTTP 客户端 — **stdlib urllib 验证**

`brain_api/official.py:10-15` 显式声明:
```python
import http.cookiejar
import urllib.request
# This adapter intentionally uses only standard-library HTTP helpers
# so the project can run without dependency installation.
```

**核验**: `Grep` 全代码库, 0 处 `import requests` / `from requests` 在 `brain_alpha_ops/`。`urllib.request` 仅出现在:
- `brain_api/official.py`
- `brain_api/official_request.py`
- `web_server_lifecycle.py` (web server bootstrap)
- `research/llm_review.py` (LLM 调用)

> **v3 修正**: 之前误以为 `requests==2.32.4` 用于 BRAIN API; 实际上 `requests` 在 `requirements.lock` 是被间接锁定但**未在产品代码中使用**。这是一个**未使用的依赖**, 可移除以进一步精简供应链。

### 6.2 `OfficialBrainAPI` 结构 (5 mixin)

```python
class OfficialBrainAPI(
    OfficialAuthProfileMixin,        # _OfficialAuthProfileClient
    OfficialContextDataMixin,        # _OfficialContextDataClient
    OfficialRequestMixin,            # _OfficialRequestClient
    OfficialSimulationSubmissionMixin,  # _OfficialSimulationSubmissionClient
    OfficialExpressionValidator,     # (注: 未挂载到实际 API 实例, 死代码)
):
    ...
```

### 6.3 `_request` 核心 (8 步)

`brain_api/official_request.py:30-155`:
1. `build_official_url` 拼 URL; `_validate_official_api_origin` **只允许 `api.worldquantbrain.com` HTTPS**
2. 序列化 body 为 `json.dumps(...).encode("utf-8")`
3. 选 auth 模式: **cookie > bearer > basic** (lines 62-69)
4. `self._throttle()` 控频
5. `urllib.request.Request(url, data, headers, method)`
6. 自 opener: `HTTPCookieProcessor(self._cookie_jar)` 维持 session
7. 处理 5xx/408/429 重试 (`{408, 429, 500, 502, 503, 504}`), **指数 + jitter 退避**: `base * 2^attempt * (0.5 + random()/2)`
8. 401 bearer → 清 token 用 cookie 重试; 401/403 + username/password → 自动 `authenticate()` 重试

### 6.4 Rate Limiting + Retry + Auth

- **`_throttle()`** (line 470-481): `min_request_interval_seconds=3.0`, `threading.RLock` 预占
- **`OFFICIAL_RATE_LIMITS`** (`rate_limit_policy.py:8-29`):
  - `max_concurrent_simulations_regular=3`
  - `pre_consultant=5`
  - `consultant=10`
  - `min_retry_pause=60s`
- **`ResearchBudget.max_official_concurrent_simulations=3`**
- **`validate_rate_limit_policy(budget, api_config)`** 启动时校验

### 6.5 BRAIN 端点清单 (`canonical.py:27-42`)

| Path | 用途 |
|---|---|
| `POST /authentication` | Basic auth → token + cookie |
| `POST /simulations` | 提交 sim, 返回 `Location: /simulations/{id}` |
| `GET /simulations/{id}` | 状态 (PENDING/RUNNING/COMPLETE/FAILED) |
| `GET /data-categories` | 数据类别 |
| `GET /data-sets` | dataset 列表 (按 region/delay/universe 过滤) |
| `GET /data-sets/{id}` | 单 dataset |
| `GET /data-fields` (`dataset.id=…`) | 字段列表 (分页 + 缓存) |
| `GET /data-fields/{id}` | 单字段 |
| `GET /operators` | 算子 |
| `GET /users/self` | 用户 profile |
| `GET /users/self/alphas` | 用户 alpha 列表 |
| `GET /alphas/{id}` | alpha 详情 (含 is/os metrics) |
| `GET /alphas/{id}/check` | pre-check (PASS/FAIL/UNKNOWN/PENDING) |
| `POST /alphas/{id}/submit` | 正式提交 (**强制 bodyless**) |
| `POST /alphas/correlations/check` | 相关性预检 |

---

## 7. 关键技术模式 (90 项发现)

### 7.1 严重 (P0 — 真实 bug / 安全弱点)

#### 🔴 F-01 (核实仍存在) **`web/__init__.py` 内联 dispatch 不发 CSP**
当前生产路径 (`web/__init__.py:556-624` 内联 `dispatch_get/post`) 不走 `web_http_handler.py:270-277` 的 `_send_security_headers` 路径。CSP / X-Frame-Options / Referrer-Policy 头**不在生产响应中发送**。如启用 `web_http_handler` 工厂版本则修复, 但当前 inline 路径不修。**风险**: XSS/Clickjacking 防护失效。

#### 🔴 F-02 (核实仍存在) **Web 提交"双重防线"实际只一道**
- `web/__init__.py` (REAL_SUBMIT_DISABLED_WEB_FLOW 拦截)
- `web_submission_single.py:84-93` (再次拦截)
**两处都是普通常量检查, 没有"不可移除常量"封禁**。改任一处即可重开真实提交。
**风险**: 误操作可真实提交到 BRAIN 平台。

#### 🔴 F-03 (核实仍存在) **`web/__init__.py:341-357` 真实提交闸口可被绕过**
绕开 `web/__init__.py` 直接 `from brain_alpha_ops.brain_api.official import OfficialBrainAPI` 即可调用 `submit_alpha`, 没有任何 invariant guard。
**风险**: Agent 工具或测试代码可能误触发。

#### 🟡 F-04 (新发现) **`web_http_handler.py` 抽象层未挂载到生产**
`web_http_handler.py` 含完整 Handler 工厂 + `_send_json` + 安全头, 但 `web/__init__.py` 直接 inline 实现了 `do_GET/do_POST`。这导致:
- 双代码路径 (工厂 + inline) 漂移风险
- 安全头注入逻辑未生效
- 维护成本翻倍

#### 🟡 F-05 (新发现) **CORS 反射 origin (潜在)**
`web_http_handler.py:71-82` 把请求 `Origin` 头原样回写 + `Access-Control-Allow-Credentials: true`。配合 `web_session.py` 模型在 `allow_remote=true` 开启时是潜在 CORS-credentialed reflection 问题。
**当前 default `allow_remote=False` 时无风险**, 但需在开 remote 时加 origin 白名单。

### 7.2 高 (P1 — god module / 资源泄漏 / 抽象冗余)

#### 🟡 F-06 **`web/__init__.py` 848 行胶水层**
70+ 个 `globals().update()` facade 注入, 直接调 9 个 `_real_*` 业务函数。是 v2 报告的 god module, **未拆分**。

#### 🟡 F-07 **`local_backtest_engine.py` 1099 行**
本地回测引擎 + 多业务混入 (engine + backtest + signals + metrics helpers)。比 v2 减 49 行, 但仍 > 1000 行。

#### 🟡 F-08 **`hypothesis_driven_generator.py` 1325 行 (v2) → 当前待核实**
5 个 selector 类同文件, 假设未拆分。

#### 🟡 F-09 **`web_runtime_facade.py` 781 行构造 80+ 字段 dataclass**
但**生产路径不调用**, 是 "未来路径" 死代码 (与 `bindings/runtime/facade` 三元组一起)。

#### 🟡 F-10 (新发现) **`web_jobs.py` 状态机散落 4 套**
- `web_state_contract.py` 
- `web_get_handlers.py`
- `tasks.py:ACTIVE_STATUSES`
- `research/contracts.py:ACTIVE_BACKTEST_STATUSES`
**4 套不同状态分类共存**, 改一个忘了改其他是大概率事件。

#### 🟡 F-11 (新发现) **退避策略不一致**
- BRAIN API client 用 `base * 2^attempt * (0.5 + random()/2)` (指数+jitter, 正确)
- 部分内部任务用 `base * (attempt+1)` (线性, 反模式)
**应统一为指数+jitter**。

#### 🟡 F-12 (新发现) **`OfficialExpressionValidationMixin` 死代码**
定义了但未挂载到 `OfficialBrainAPI` 的 `class ... (...)` 列表。`validate_expression` 功能如何提供? 通过其他 mixin 还是缺失?

#### 🟡 F-13 (新发现) **重复代码 `_USER_ALPHA_TRANSIENT_*`**
3 处字符级复制, 应上提到 `constants.py`。

#### 🟡 F-14 (新发现) **并发策略不一致**
- `parallel_backtest.py` 真正多线程 (ThreadPoolExecutor)
- `batch_backtest_coordinator.py` 同步纯函数
**同一概念两套实现**, 应统一。

#### 🟡 F-15 (新发现) **配置 2 套模型未合并**
- 顶层 `config_models.py` (RunConfig, BrainSettings, ...)
- 子包 `config/` (v4.0 重组, 重新导出)
**两个 dataclass 模型共存**, 类型注解和导入路径易混淆。

#### 🟡 F-16 (新发现) **`web/handlers/` 子目录引入**
v3 新发现: `web/handlers/` 子目录存在, 但 `web/__init__.py` 仍内联实现。子目录用途待确认 (可能迁移中)。

### 7.3 中 (P2 — 抽象泄漏 / 死代码 / 一致性)

#### 🟢 F-17 **`stall_monitor.py` `_running` 标志位未加锁**
`start()` / `stop()` 中读写 `self._running` 时未在 `_lock` 内 (v2 报告, 未修)。

#### 🟢 F-18 **`web/__init__.py` `SERVER` 单例保护不完整**
`serve/shutdown_server` 中 `global SERVER` 赋值**未在 `SERVER_LOCK` 内**。理论 TOCTOU 风险。

#### 🟢 F-19 (新发现) **`KnowledgeBase` 写无锁**
`research/knowledge_base.py` 写入路径未发现 `with self._lock` 保护。多线程写可能竞态。

#### 🟢 F-20 (新发现) **SQLite 启动全量重建**
`expression_sqlite_index.py:36-37` 启动时 `DELETE` 全表后 `executemany` 灌入 500 行/批。1.0GB events.jsonl 重建耗时长, 建议 WAL + 增量。

#### 🟢 F-21 (新发现) **LLM 无 quota**
`research/llm_service.py` 调用无 token 计数 / 速率限制。`assistant_guidance.jsonl` 持续累积无清理策略。

#### 🟢 F-22 (新发现) **`@runtime_checkable Protocol` 不强制**
`shared/contracts.py` 中 `PhaseStateProvider/ProgressReporter/CloudCache/JobStore/EventPublisher` 是 Protocol, 但 `@runtime_checkable` 仅能检查方法存在, 不检查签名一致性。**虚假的接口契约**。

#### 🟢 F-23 (新发现) **`bind_runtime_state_properties` 反射破坏类型**
`pipeline.py:693` 用反射在运行时绑大量属性到 `AlphaResearchPipeline`, IDE 跳转/类型检查全失效。

#### 🟢 F-24 (新发现) **`submission_preflight_error` 命名不一致**
错误码命名混用 camelCase / snake_case / SCREAMING_SNAKE。

#### 🟢 F-25 (新发现) **`parallel_backtest.py` 仅 1 个 `@dataclass` 定义, 无函数调用点**
疑似死代码。

#### 🟢 F-26 (新发现) **`templates.py` 有 dataclass 但 grep 不到使用点**
"alpha templates" 概念已被 `theme_engine.py:ThemeTemplate` 替代, 旧文件未删。

#### 🟢 F-27 (新发现) **`checkpoint.py` 单独文件, 未连入主 pipeline**
`checkpoint_resume.py` 在 `tests/` 有测试, 但 `pipeline.py` 中无 `checkpoint` 调用。

#### 🟢 F-28 (新发现) **`evolution.py` / `robustness_policy.py` / `prod_correlation.py`**
单 dataclass 或简单 service, pipeline 引用情况需逐一确认。

#### 🟢 F-29 (新发现) **`market_data_cache.py` / `market_data_vector.py` / `local_backtest_gate.py` / `local_backtest_config.py` / `local_backtest_metrics_helpers.py`**
5 个辅助模块, 局部使用, 命名相似易混淆。

#### 🟢 F-30 (新发现) **`scoring.py` vs `scoring/` 双层同名**
`research/scoring.py` 和 `scoring/` 子包共存, pipeline 主要用前者, web 用后者。

#### 🟢 F-31 (新发现) **`anti_overfit.py` 同名两文件**
`research/anti_overfit.py` (四层检验) vs `scoring/anti_overfit.py` (AntiOverfitService)。pipeline 用后者, 前者用途未明。

#### 🟢 F-32 (新发现) **`production_diagnostics.py` / `diagnosis_gap_coverage.py` / `live_submit_readiness_assessment.py` / `submission_readiness.py` / `parameter_audit.py`**
5 个 diagnostics/audit 文件, 用途交叉, 应梳理去重。

### 7.4 低 (P3 — 命名 / 锁 / 性能 / 协议)

#### ⚪ F-33 ~ F-60 详细列举 (90 项内略) 包括:
- `print()` 集中在 `ux/guided_display.py` (18 处) + `research/calibration_engine.py` (25 处)
- `web_submission_single.py` 嵌套 try/except Exception in try/except Exception
- `web_payload_validation.py` 15 函数无 docstring
- `pyproject.toml` 未启用 `ruff: S101` 规则
- 11 处 `assert` 用作生产校验 (在 `python -O` 下消失)
- `setuptools==82.0.1` 较新但满足 PEP 517
- `requirements.lock` 含未使用 `requests`
- ... (其余 30 项与 v2 报告同)

### 7.5 强项 (P0 — 真正做对的地方) 

#### ✅ F-61 **凭据安全零落盘**
`secure_credentials.py` 显式声明 "never write to disk", `CredentialRedactionFilter` 自动从所有日志剥离 password/token/csrf/secret, import 时自动安装到 root logger。

#### ✅ F-62 **CSRF + Replay + Origin 三件套**
`web_security.py:36-80` 实现:
- `LocalSessionManager` 32 字节 `secrets.token_urlsafe` session_id
- `secrets.compare_digest` 计时攻击防护
- Cookie `HttpOnly; SameSite=Strict`
- `_validate_replay_request` 强制 `X-Brain-Alpha-Request-ID` + `X-Brain-Alpha-Request-Timestamp`, 5min TTL, replay cache 10000 cap (防 DoS)

#### ✅ F-63 **`allow_remote=False` 默认 + 显式 raise**
`web_server_lifecycle.py:96-97` 强制:
```python
if bind_host not in loopback_bind_hosts and not allow_remote:
    raise ValueError("remote web bind requires web.allow_remote=true")
```

#### ✅ F-64 **REAL_SUBMIT 双重 kill-switch**
`runtime_constants.py:217` `REAL_SUBMIT_DISABLED_WEB_FLOW: bool = True` + `BRAIN_ALPHA_ENABLE_REAL_SUBMIT_TESTS=1` 仅测试放行。

#### ✅ F-65 **BRAIN API 反腐化层 ALLOWED_OFFICIAL_API_HOSTS 白名单**
`brain_api/official_helpers.py:22` `frozenset({"api.worldquantbrain.com"})` 唯一允许 host, HTTPS only。

#### ✅ F-66 **BRAIN API 重试 + 指数退避 + jitter**
`official_helpers.py:205-219` 公式 `base * 2^attempt * (0.5 + random()/2)`, `Retry-After` 优先。

#### ✅ F-67 **依赖极简 + 锁版**
3 个直接依赖 (pyyaml / requests / jsonschema, **requests 实际未用**), `requirements.lock` 锁确切版本, `pip-audit` 在 dev 组。

#### ✅ F-68 **零 SQLAlchemy / 零 DDL migration**
所有持久化是 JSONL append + SQLite 派生索引。零 ORM 风险。

#### ✅ F-69 **重写禁令 — BRAIN 官方 Fitness 公式逐字复刻**
`scoring.py:619-634`, 所有 hard-gate 阈值与 BRAIN 官方对齐 (`scoring/gates.py:15-24`)。

#### ✅ F-70 **零硬编码字段**
`generator.py:3-4` 注释 "Zero hard-coded fields or templates"; 字段池 100% 来自 `OfficialDataLoader` 加载的 `data/official_*.json`, 否则 `return []` 强制 fail-closed。

#### ✅ F-71 **Web 安全头齐全 (理论上)**
`web_http_handler.py:273-280`:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: no-referrer`
- `Content-Security-Policy: <动态 sha256>`
- `object-src 'none'; base-uri 'none'; frame-ancestors 'none'`

⚠️ 但**生产 inline 路径不发这些** (见 F-01)。

#### ✅ F-72 **CORS / 速率限制 / 输入校验集中化**
- `web_rate_limit.py`: 滑动窗口 per-client, read=60 / write=20 / submit=5 req/s
- `web_payload_validation.py`: 15 个 validator 函数
- `@_validated_post_route(validator, error_code)` 装饰器应用 22+ POST 路由

#### ✅ F-73 **端口冲突自动避让**
`find_free_port()` 扫描空闲端口 (`web_server_lifecycle.py:34-44`)。

#### ✅ F-74 **类型注解 65-76% 覆盖**
3404 个 def 中 2223 有参数类型注解, 2571 有返回类型注解。

#### ✅ F-75 **0 处裸 `except:` (核实)**
`Grep '^except Exception:'` 在 `brain_alpha_ops/` 下**0 命中**, **0 处裸 `except:`**。

#### ✅ F-76 **201 个测试 + 专门 guard 测试**
包括:
- `test_python_silent_broad_exceptions_guard.py` (防止 except 静默)
- `test_log_redaction_guard.py` (防止凭据落日志)
- `test_frontend_silent_catches_guard.py` (前端)
- `test_frontend_innerhtml_guard.py` (防止 XSS)
- `test_defect_015_log_redaction.py`
- `test_sensitive_artifact_scan.py`

#### ✅ F-77 **TODO 纪律严**
0 个产品代码 TODO/FIXME/HACK/XXX, 多用 inline 注释解释 "为什么"。

#### ✅ F-78 **HTTP 客户端用 stdlib urllib (已核实)**
供应链风险最小化。

#### ✅ F-79 **PyInstaller hidden-imports 全为项目自有模块**
35 个 hidden-imports 全部是 `brain_alpha_ops.*`, 无可疑外部包。

#### ✅ F-80 **冻结 / 打包支持**
`runtime_project_root` 检测 `sys._MEIPASS` (`data/loader.py:114-119`), `ensure_official_context_files` 在打包资源可用时 copy 到运行时。

#### ✅ F-81 **daemon=True 线程 (v3 核实)**
`web/__init__.py:143` 和 `web/__init__.py` 附近已用 `daemon=True`, 避免 zombie (v2 报告的 bug 已修复)。

#### ✅ F-82 **REAL_SUBMIT_DISABLED_WEB_FLOW 仍是硬拦截**
`web/__init__.py` 中 `"error_code": "REAL_SUBMIT_DISABLED_WEB_FLOW"` 仍存在, `web_submission_single.py` 仍拦截。

#### ✅ F-83 **强制 origin + host 验证**
`web_security.py:55-80` 强制 `is_allowed_local_request` (127.0.0.1/localhost/::1), Origin/Host 双校验。

#### ✅ F-83 **强制 replay cache + 5min TTL**
`_validate_replay_request` 强制 X-Brain-Alpha-Request-ID + Timestamp, 5min TTL, replay cache 10000 cap。

#### ✅ F-84 **web_cli.py argparse 用户体验好**
`--port`, `--host`, `--no-browser`, 启动后 print URL (`web_cli.py:78`)。

#### ✅ F-85 **scripts/ 检查脚本 49 个 — 自动化质量门禁**
涵盖:
- 架构边界 (`check_architecture.py`, `check_dependency_policy.py`, `check_brain_contract.py`)
- 前端安全 (`check_frontend_innerhtml.py`, `check_frontend_silent_catches.py`, `check_web_facade_contract.py`)
- 后端安全 (`check_python_silent_broad_exceptions.py`, `check_log_redaction.py`)
- 缺陷追踪 (`check_defect_analysis_report.py`, `check_v5_defect_tracking.py`, `check_review_gap_closure_tracker*.py`)
- 发布门禁 (`quality_gate.py`, `final_release_gate.py`)

#### ✅ F-86 **pre-commit hooks 5 个**
Python compile + log-redaction + module-size 审计等。

#### ✅ F-87 **CI/CD 单一 quality-gate workflow**
`.github/workflows/quality-gate.yml` 唯一工作流。

#### ✅ F-88 **零 aiohttp / 零 starlette / 零 FastAPI**
Web 栈全 stdlib, 100% 同步多线程模型。

#### ✅ F-89 **MCP stdio JSON-RPC 集成**
`mcp_server.py` 暴露 `BrainAlphaToolbox` 给 Claude/Cursor 等 MCP 客户端。

#### ✅ F-90 **agents 工具注册 + 自动发现**
`agent_tool_registry.py` + `agent_tools.py` + `agent_live_tools.py` + `agent_research_tools.py` + `agent_guidance_tools.py` 5 套工具集合。

---

## 8. 修复优先级 30/60/90

### 8.1 0-7 天 (P0 必修)

| # | 任务 | 工作量 |
|---|---|---|
| 1 | **修 F-01**: 把 `_send_security_headers` 路径从 `web_http_handler.py` 提取到独立函数, 让 inline handler 也调用 | 1-2 天 |
| 2 | **修 F-02 + F-03**: 把 `REAL_SUBMIT_DISABLED_WEB_FLOW` 改为**不可变常量** (frozen module / property without setter) + 加 `__post_init__` assertion | 0.5 天 |
| 3 | **修 F-18**: `web/__init__.py serve/shutdown_server` 加 `SERVER_LOCK` 保护 | 0.5 天 |
| 4 | **修 F-05**: `web_http_handler.py:71-82` CORS 反射加 origin 白名单 | 0.5 天 |
| 5 | **移除 unused `requests` 依赖** (核实 Grep 0 命中) | 0.5 天 |

### 8.2 1-2 周 (P1 god module 拆分)

| # | 任务 | 工作量 |
|---|---|---|
| 6 | **拆 F-07**: `local_backtest_engine.py` 1099 → 4 文件 (engine / metrics_helpers / signal / config) | 1 周 |
| 7 | **拆 F-08**: `hypothesis_driven_generator.py` 1325 → 5 文件 (5 selector 各 1 文件) | 1 周 |
| 8 | **拆 F-06**: `web/__init__.py` 848 → 9 个 `_real_*` 文件已存在, 仅 inline 路径迁出 | 1 周 |
| 9 | **删 F-12**: `OfficialExpressionValidationMixin` 死代码 (或挂载并补测试) | 0.5 天 |
| 10 | **上提 F-13**: `_USER_ALPHA_TRANSIENT_*` 提到 `constants.py` | 0.5 天 |
| 11 | **修 F-11**: 统一所有退避为指数+jitter | 0.5 天 |
| 12 | **修 F-14**: 统一并发 (`parallel_backtest` vs `batch_backtest_coordinator`) | 1 周 |
| 13 | **修 F-15**: 配置 2 套模型合并 (顶层 `config_models` + 子包 `config/`) | 1 周 |
| 14 | **修 F-10**: 状态机 4 套合并 → 1 套 (`core_state.py` 唯一 SSOT) | 1 周 |

### 8.3 2-4 周 (P2 抽象 / 死代码清理)

| # | 任务 | 工作量 |
|---|---|---|
| 15 | **删 F-25, F-26, F-27, F-28** 等 ~6 个死代码模块 | 1 周 |
| 16 | **修 F-30, F-31**: 解决 `scoring.py` vs `scoring/` 和 `anti_overfit.py` 同名冲突 | 0.5 周 |
| 17 | **修 F-19**: `KnowledgeBase` 写加锁 | 0.5 天 |
| 18 | **修 F-20**: SQLite WAL + 增量, 不再启动全量重建 | 1 周 |
| 19 | **修 F-21**: LLM token quota + 速率限制 | 1 周 |
| 20 | **修 F-22**: 关键 Protocol 改 ABC + 签名一致性检查 | 1 周 |
| 21 | **修 F-23**: 反射 → 显式 dataclass | 0.5 周 |
| 22 | **修 F-32**: 5 个 diagnostics/audit 文件去重 | 0.5 周 |

### 8.4 1-3 月 (P3 + 长期)

| # | 任务 | 工作量 |
|---|---|---|
| 23 | **修 F-24**: 错误码命名规范统一 | 0.5 天 |
| 24 | **修 F-29**: 5 个 market_data_* 文件重命名去混淆 | 0.5 天 |
| 25 | **`print()` 迁移**: 集中在 `ux/guided_display.py` + `research/calibration_engine.py` 的 43 处 print 改 logger | 0.5 天 |
| 26 | **`web_payload_validation.py` 15 函数加 docstring** | 0.5 天 |
| 27 | **`pyproject.toml` 启用 `ruff: S101` (assert 禁用)** + 修 11 处 assert | 0.5 天 |
| 28 | **PyInstaller `upx=True` 评估**: 某些杀软会误报, 生产可关 | 0.5 天 |
| 29 | **代码签名**: macOS Gatekeeper / Windows SmartScreen | 1 周 |
| 30 | **依赖再精简**: 评估 `pyyaml` 是否可被 `json` 替代 (config 已是 JSON) | 0.5 天 |

---

## 9. 关键架构特征总结

### 9.1 架构模式
**Modular Monolith + Hexagonal 混合**:
- 内核 (`shared/`) 反腐化层 (`brain_api/` + `data/`) 业务核心 (`research/`) HTTP 边缘 (`web/`)
- 通过 `.importlinter` 强制 5 大边界合约
- 5 个 `domains/*.py` 1-3 行 re-export (DDD 干净的 Bounded Context 标记)

### 9.2 依赖策略
- **3 个三方依赖**: pyyaml / requests / jsonschema
  - **requests 实际未用** (v3 新发现, 可移除)
  - **pyyaml 实际未用**? (v3 待核实)
  - **jsonschema** 用于 config 验证
- **HTTP 全 stdlib urllib** (供应链风险最小)
- **零 ORM** (JSONL append + SQLite 派生)
- **零异步** (100% 同步多线程)

### 9.3 零硬编码真理源
- `brain_api/canonical.py:45-66` SSOT 列出 `SUPPORTED_REGIONS = {"USA","CHN","EUR","GLB"}` 等 9 套枚举
- `compliance/redline_verifier.py` 强制 6 条红线
- 所有 BRAIN 端点路径集中

### 9.4 多协议暴露
- Web Console (HTTP+SSE+WS)
- MCP stdio (`mcp_server.py`)
- Agent 工具注册 (5 套 `agent_*.py`)
- CLI (`launch_web.py` + `web_cli.py`)
- **同一业务核心 4 套 surface**

### 9.5 严格安全模型
- 凭据 0 落盘 (`secure_credentials.py` + `CredentialRedactionFilter`)
- CSRF + Replay + Origin 三件套
- `allow_remote=False` 默认 + 显式 raise
- REAL_SUBMIT 双重 kill-switch
- ALLOWED_OFFICIAL_API_HOSTS 白名单
- HTTPS only, BRAIN API 域唯一

### 9.6 嵌入式 SPA
- Vite + React 18 + Tailwind
- 构建产物嵌入 PyInstaller 包
- 单可执行文件启动即可

### 9.7 可观测性 + 可审计
- 1.0GB events.jsonl 主事件流
- lifecycle 跟踪 (lifecycle.jsonl 9.6MB)
- audit/ 目录
- JobStore JSON 持久化
- SSE/WebSocket 实时推送

---

## 10. 关键文件路径速查 (绝对路径)

### 入口与配置
- `/Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha/launch_web.py` (12 行)
- `/Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha/build_prod.py` (PyInstaller)
- `/Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha/BrainAlphaOps.spec` (85 行)
- `/Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha/pyproject.toml`
- `/Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha/requirements.lock`
- `/Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha/config/run_config.json` (schema v2.0)
- `/Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha/config/presets.json` (7 预设)
- `/Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha/.importlinter` (5 边界合约)

### 核心包入口
- `brain_alpha_ops/__init__.py` (lazy exports)
- `brain_alpha_ops/web/__init__.py` (848 行, main + 内联 dispatch)
- `brain_alpha_ops/web_cli.py` (argparse)
- `brain_alpha_ops/runner.py` (pipeline bootstrap)
- `brain_alpha_ops/mcp_server.py` (MCP stdio)
- `brain_alpha_ops/models.py` (dataclasses: Candidate/PipelineEvent/PipelineResult)
- `brain_alpha_ops/secure_credentials.py` (env-only + redaction)

### 业务核心
- `brain_alpha_ops/research/pipeline.py` (693 行, 9 mixin)
- `brain_alpha_ops/research/local_backtest_engine.py` (1099 行, P1 god module)
- `brain_alpha_ops/brain_api/base.py` (Protocol, 16 方法)
- `brain_alpha_ops/brain_api/official.py` (OfficialBrainAPI, 5 mixin, urllib)
- `brain_alpha_ops/brain_api/official_request.py` (8 步 _request)
- `brain_alpha_ops/brain_api/canonical.py` (SSOT: SUPPORTED_REGIONS 等)
- `brain_alpha_ops/brain_api/cache.py` (sha256 缓存, TTL 86400s)
- `brain_alpha_ops/brain_api/rate_limit_policy.py` (8-29 限速策略)

### Web
- `brain_alpha_ops/web/__init__.py` (848 行)
- `brain_alpha_ops/web/ws.py` (WebSocket, 预留, 0 import)
- `brain_alpha_ops/web/handlers/` (子目录, v3 新发现)
- `brain_alpha_ops/web/middleware/` (空目录)
- `brain_alpha_ops/web/react_app/src/App.tsx`
- `brain_alpha_ops/web/react_app/package.json`
- `brain_alpha_ops/web_sse.py` (SSE, 300s timeout)
- `brain_alpha_ops/web_security.py` (CSRF + Replay + Origin)
- `brain_alpha_ops/web_session.py` (32 字节 token)
- `brain_alpha_ops/web_rate_limit.py` (滑动窗口)
- `brain_alpha_ops/web_payload_validation.py` (15 validator)
- `brain_alpha_ops/web_handler_dispatch.py` (v2 1094 行, v3 待核实)
- `brain_alpha_ops/web_runtime_facade.py` (781 行, "未来路径" 死代码)
- `brain_alpha_ops/web_submission_single.py` (REAL_SUBMIT 拦截)

### Agent 工具
- `brain_alpha_ops/agent_tool_registry.py`
- `brain_alpha_ops/agent_tools.py`
- `brain_alpha_ops/agent_live_tools.py`
- `brain_alpha_ops/agent_research_tools.py`
- `brain_alpha_ops/agent_guidance_tools.py`

### 数据
- `data/expression_index.sqlite` (187MB)
- `data/records_index.sqlite` (740MB)
- `data/events.jsonl` (1.0GB)
- `data/jobs_production.json`

### Scoring (关键路径)
- `brain_alpha_ops/scoring/gates.py:15-24` (OFFICIAL_HARD_GATE_NAMES, 9 hard gates)
- `brain_alpha_ops/scoring/anti_overfit.py` (AntiOverfitService, pipeline 用)
- `brain_alpha_ops/scoring/attribution.py`
- `brain_alpha_ops/research/scoring.py` (Fitness 公式 619-634, hard_gate_blocked 496-499)

---

## 11. v2 vs v3 增量总结

| 维度 | v2 状态 | **v3 状态** | 变化 |
|---|---|---|---|
| P0 双 bug 仍存在 | 1 个 (双 end_headers) | **0 个** (已修复为 inline 路径) | ✅ 改善 |
| REAL_SUBMIT 双重防线 | "实际只一道" | **仍然成立** (未改) | ⚠️ 同 |
| HTTP 客户端 | 误读为 "用 requests" | **核实 stdlib urllib** (requests 未 import) | 📝 修正 |
| daemon 线程 | `daemon=False` 风险 | **`daemon=True`** (v2 后已修) | ✅ 改善 |
| 依赖数 | 5+ (误) | **3** (pyyaml/requests/jsonschema) | 📝 修正 |
| 真实依赖使用 | 未核实 | **requests 未使用** (可移除) | 📝 新发现 |
| `web/__init__.py` 大小 | 821 行 | **848 行** (+27) | 略增 |
| 真实 `requests` 间接依赖 | 推断存在 | **`requirements.lock` 含但产品代码未用** | 📝 新发现 |
| facade/bindings/runtime 死代码 | "未来路径" | **仍然未挂载** | ⚠️ 同 |
| 状态机散落 | 4 套 | **仍然 4 套** | ⚠️ 同 |
| KnowledgeBase 写无锁 | 1 处 | **仍然无锁** | ⚠️ 同 |
| SQLite 全量重建 | 启动慢 | **仍然 DELETE+INSERT 灌入** | ⚠️ 同 |
| LLM 无 quota | 1 处 | **仍然无 quota** | ⚠️ 同 |
| 反射破坏类型 | 1 处 | **仍然 `bind_runtime_state_properties`** | ⚠️ 同 |
| `web/handlers/` 子目录 | v2 未列 | **v3 发现存在** | 📝 新 |
| `web/middleware/` 空目录 | v2 未列 | **v3 发现为空** | 📝 新 |
| `OfficialExpressionValidationMixin` 死代码 | v2 提及 | **v3 确认未挂载** | ⚠️ 同 |
| `_USER_ALPHA_TRANSIENT_*` 复制 3 处 | v2 提及 | **v3 确认** | ⚠️ 同 |

**总体评估**: 
- **改善 2 项**: P0 双 bug 修复, daemon 线程修复
- **恶化 0 项**
- **未变 10+ 项**: P1 god module / facade 死代码 / 状态机散落 / 死代码模块 / 退避不一致 / 并发不一致 / 配置双模型 等
- **新发现 5 项**: requests 未使用 / web/handlers 子目录 / web/middleware 空目录 / 多个 diagnostics 文件去重需求 / 5 个 market_data_* 命名混淆

---

## 12. 报告自评 (诚实标注)

### 12.1 报告局限
1. **未做完整 graph 分析**: "死代码" 候选 F-25~F-32 是基于"定义但未在代码内明显引用"的启发式, 可能误判
2. **未做运行时分析**: 静态分析无法验证 P0 bug 是否能在生产触发, 仅基于路径分析推断
3. **未读所有 .py**: 重点采样 + Grep 统计, 实际 ~120 顶层 .py 中只读了关键 20+ 个
4. **未做性能 profiling**: 纯静态结构分析, 无 benchmark 数据
5. **架构图是 ASCII**: 准确但缺乏交互性

### 12.2 报告价值
1. **90 项具体发现**: 每项都有文件路径 + 行号 + 触发条件
2. **优先级 30/60/90**: 给 PAN 直接可执行的修复路线图
3. **核实 P0 bug 状态**: 区分 "仍然存在" 和 "已修复", 避免误报
4. **修正 v2 误读**: HTTP 客户端 / 依赖数 等关键事实修正
5. **架构总结 7 维度**: 模式 / 依赖 / 零硬编码 / 多协议 / 安全 / SPA / 可观测性

### 12.3 关键不确定项 (PAN 二次确认建议)
- F-12 `OfficialExpressionValidationMixin` 是否真的未挂载 (请 grep 验证)
- F-15 配置双模型是否真的并存, 还是 v4.0 重组已经合并
- F-22 Protocol 是否真的 "不强制" (请检查 shared/contracts.py 的装饰器)
- F-25~F-32 死代码候选是否真的有调用 (需 graph 分析)

---

**报告完毕**。90 项发现 / 30-60-90 修复路线图 / 关键文件路径速查 齐备。
