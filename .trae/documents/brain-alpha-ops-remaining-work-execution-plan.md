# BRAIN Alpha Ops 剩余工作执行计划（续）

> 承接 `brain-alpha-ops-remaining-fixes-execution-plan.md`。
> 前序计划 18 项工作中，**A2/A3/A4 共 5 项已完成**（F-005、F-006、F-007、W-001、U-015）。
> 本计划聚焦**剩余 13 项**：C2 线程安全收尾（3 项，import 已加，待实现锁）+ C4 数值正确性（4 项）+ B Code Wiki 文档（6 类）+ 最终验证。
> 验证日期：2026-07-07（Phase 1 只读探索确认所有缺陷仍存在）。

---

## 计划摘要 (Summary)

前序综合改进计划已批准并完成阶段 A2/A3/A4。本计划是同一批准计划的**收尾部分**，不引入新范围，仅完成原计划中尚未实施的 C2/C4/B/验证。所有文件路径与行号已通过 Phase 1 只读探索二次确认。

**已完成（不再触碰）**：F-005（runtime_constants.py 调用栈检查）、F-006（Dockerfile 非 root USER）、F-007（docker-compose 127.0.0.1 绑定 + cap_drop + no-new-privileges）、W-001（PhaseShell inert）、U-015（CredentialQuickStart timer ref cleanup）。

**C2 当前状态**：`import threading` 已添加至 `metrics.py:23` 与 `backend_registration.py:13`（经 Phase 1 确认），但**锁实现尚未落地**。本计划完成锁实现。

---

## 当前状态分析 (Current State Analysis)

### C2 线程安全（3 项，进行中）

| 缺陷 | 文件:行 | 当前状态（Phase 1 确认） |
|------|---------|--------------------------|
| F-020 | `brain_alpha_ops/metrics.py` `MetricsCollector` | `import threading` 已在 L23；`__init__`（L43-47）无 `self._lock`；`counter`/`gauge`/`histogram`/`timer`/`summary`/`reset` 均无 `with self._lock` |
| F-028 | `brain_alpha_ops/backend_registration.py:64-75` | `import threading` 已在 L13；`_api_instance=None`（L64）；`_get_brain_api()`（L67-75）仅单次检查 `if _api_instance is not None`，无锁无双检 |
| F-053 | `brain_alpha_ops/research/record_sqlite_index.py` | `append_record`（L30-51）与 `refresh`（L53-78）用默认 deferred 隔离 + `conn.commit()`；`_connect`（L150-153）未设 `isolation_level` |

### C4 数值正确性（4 项，Phase 1 全部确认仍存在）

| 缺陷 | 文件:行 | 当前代码 | 缺陷 |
|------|---------|----------|------|
| F-051 | `scoring/release_score_gate/release_score_gate.py:411` | `effective_settings = settings if settings is not None else metrics` | settings 为 None 时回退到 metrics 字典，把指标当 settings 传给 `ThresholdPolicy.from_thresholds` |
| F-052 | `research/prod_correlation.py:235-268` `_local_fallback` | complexity≥50 时 `estimated_corr=0.40/0.25`，`passed=estimated_corr < self._max_correlation` → `passed=True` | 官方 API 不可用且 `allow_local_fallback=True` 时，高复杂度表达式被本地估算放行（fail-open），违反提交门禁语义 |
| F-055 | `research/fusion.py:152-156` `composite_ensemble` max 分支 | `return result`（未校验） | 同函数 average/rank_average/min 分支均调用 `_validate_fusion_expr`，唯独 max 跳过，可能产出超长/超深表达式 |
| F-056 | `research/backtest_flow_service/_slot_submission.py:87` | `for slot in open_slots:` 内 `if not outcome.submitted: ... return` | 单槽提交失败时 `return` 退出整个函数，放弃后续槽位；应为 `continue`（同函数 L52 去重场景已用 `continue`） |

### B Code Wiki 文档（6 类，全部待补充）

`docs/CODE_WIKI.md` 现有 8 章（项目概览/架构/目录/数据模型/模块详解/依赖/运行方式/安全模型），缺：HTTP API 参考、React 前端架构、测试策略、CI/CD、缺陷索引、贡献者指南。

---

## 提议的改动 (Proposed Changes)

### 阶段 C2：线程安全修复收尾（F-020, F-028, F-053）

#### C2-1. F-020：`metrics.py` MetricsCollector 加锁

**文件**：[brain_alpha_ops/metrics.py](file:///workspace/brain_alpha_ops/metrics.py)（`import threading` 已在 L23）

- **What**：在 `MetricsCollector.__init__`（L43-47）末尾添加 `self._lock = threading.Lock()`；所有写方法（`counter` L49-52、`gauge` L54-57、`histogram` L59-62）方法体用 `with self._lock:` 包裹；`timer`（L64-72）的 finally 块内 `self.histogram(...)` 调用已在锁内（因 histogram 已加锁，无需重复）；读方法 `summary`（L74-88）用 `with self._lock:` 拷贝字典后计算；`reset`（L90-95）用 `with self._lock:` 包裹。
- **Why**：Web 控制台用 `ThreadPoolExecutor`（`WebDefaults.TASK_EXECUTOR_MAX_WORKERS=4`）并发跑任务，多线程同时 `self._counters[key] += value` 会丢更新；`histogram.append` 非原子。
- **How**：
  ```python
  def __init__(self) -> None:
      self._counters: dict[str, int] = defaultdict(int)
      self._gauges: dict[str, float] = {}
      self._timers: dict[str, list[float]] = defaultdict(list)
      self._histograms: dict[str, list[float]] = defaultdict(list)
      self._lock = threading.Lock()  # F-020: guard all reads/writes

  def counter(self, name, value=1, **tags):
      key = self._make_key(name, tags)
      with self._lock:
          self._counters[key] += value

  def gauge(self, name, value, **tags):
      key = self._make_key(name, tags)
      with self._lock:
          self._gauges[key] = value

  def histogram(self, name, value, **tags):
      key = self._make_key(name, tags)
      with self._lock:
          self._histograms[key].append(value)

  def summary(self):
      with self._lock:
          counters = dict(self._counters)
          gauges = dict(self._gauges)
          histograms = {name: list(v) for name, v in self._histograms.items()}
      # 计算在锁外（基于快照）
      return {"counters": counters, "gauges": gauges,
              "histograms": {n: {"count": len(v), "min": min(v) if v else 0,
                                 "max": max(v) if v else 0,
                                 "avg": sum(v)/len(v) if v else 0} for n, v in histograms.items()}}

  def reset(self):
      with self._lock:
          self._counters.clear()
          self._gauges.clear()
          self._timers.clear()
          self._histograms.clear()
  ```
  `timer` 的 finally 块调用 `self.histogram(...)` 已被锁保护，无需改 timer 本身。
- **注意**：`summary` 在锁内只做浅拷贝，统计计算移到锁外，减少锁持有时间。

#### C2-2. F-028：`backend_registration.py` 双检锁

**文件**：[brain_alpha_ops/backend_registration.py](file:///workspace/brain_alpha_ops/backend_registration.py)（`import threading` 已在 L13）

- **What**：添加模块级 `_api_lock = threading.Lock()`；重写 `_get_brain_api()`（L67-75）为双检锁。
- **Why**：当前单次检查 `_api_instance is not None`，两线程同时通过检查会各自 `OfficialBrainAPI()` 创建实例并相互覆盖，可能使用半初始化实例。
- **How**：
  ```python
  # Lazy BrainAPI singleton — only created when the api backend is first used.
  _api_instance = None
  _api_lock = threading.Lock()  # F-028: guard singleton creation

  def _get_brain_api():
      """Lazily create the API backend's BrainAPI instance (thread-safe)."""
      global _api_instance
      if _api_instance is not None:  # fast path, no lock
          return _api_instance
      with _api_lock:
          if _api_instance is not None:  # double-check under lock
              return _api_instance
          from brain_alpha_ops.brain_api.official import OfficialBrainAPI
          _api_instance = OfficialBrainAPI()
          return _api_instance
  ```

#### C2-3. F-053：`record_sqlite_index.py` BEGIN IMMEDIATE

**文件**：[brain_alpha_ops/research/record_sqlite_index.py](file:///workspace/brain_alpha_ops/research/record_sqlite_index.py)

- **What**：在 `append_record`（L30-51）与 `refresh`（L53-78）的写事务中显式 `conn.execute("BEGIN IMMEDIATE")` 包裹 read+write，完成 `conn.commit()`。读方法（`summary` L80-119、`lookup_alpha` L121-148）保持默认。
- **Why**：当前 `_ensure_schema` + `_next_record_index`（读）+ `INSERT`（写）用默认 deferred 隔离，多线程同时写时 SQLite 在升级锁时可能抛 `database is locked` 死锁；`BEGIN IMMEDIATE` 在事务开始即获写锁，失败快速返回。
- **How**：在 `_connect` 设 `conn.isolation_level = None`（autocommit 模式，禁用 Python sqlite3 的隐式事务管理），然后写方法手动控制事务：
  ```python
  def _connect(self) -> sqlite3.Connection:
      conn = sqlite3.connect(self.db_path)
      conn.row_factory = sqlite3.Row
      conn.isolation_level = None  # F-053: manual BEGIN IMMEDIATE/COMMIT
      return conn

  # append_record 内（L36-48 改为）:
  conn = self._connect()
  try:
      conn.execute("BEGIN IMMEDIATE")  # F-053: acquire write lock up-front
      _ensure_schema(conn)             # CREATE TABLE/INDEX (DDL, idempotent)
      record_index = _next_record_index(conn, source_file)
      conn.execute("INSERT OR REPLACE INTO records ...", ...)
      conn.commit()
  except Exception:
      conn.rollback()
      raise
  finally:
      conn.close()

  # refresh 内同理：BEGIN IMMEDIATE → _ensure_schema → DELETE → INSERTs → commit
  ```
  `_ensure_schema` 的 `CREATE TABLE IF NOT EXISTS` 在 IMMEDIATE 事务内安全（DDL 幂等）。注意 `BEGIN IMMEDIATE` 后必须保证 commit/rollback，故加 `except: rollback; raise`。
- **注意**：`_next_record_index` 的 `SELECT MAX(...)` 必须在 `BEGIN IMMEDIATE` 之后执行，才能保证读到的 max_index 不被并发插入打破（写锁已持，无新并发写）。

---

### 阶段 C4：数值正确性修复（F-051, F-052, F-055, F-056）

#### C4-1. F-051：`release_score_gate.py` 默认 `{}` 而非 `metrics`

**文件**：[brain_alpha_ops/scoring/release_score_gate/release_score_gate.py:411](file:///workspace/brain_alpha_ops/scoring/release_score_gate/release_score_gate.py)

- **What**：第 411 行 `effective_settings = settings if settings is not None else metrics` 改为 `effective_settings = settings if settings is not None else {}`。
- **Why**：settings 为 None 时回退到 metrics，把 sharpe/returns 等指标误当作 region/universe/delay 传给 `ThresholdPolicy.from_thresholds`，导致阈值策略基于错误字段计算。
- **How**：单行修改。执行时确认 `ThresholdPolicy.from_thresholds(thresholds, settings={})` 能处理空 dict（应有默认值，如默认 region/universe）。

#### C4-2. F-052：`prod_correlation.py` `_local_fallback` fail-closed

**文件**：[brain_alpha_ops/research/prod_correlation.py:235-268](file:///workspace/brain_alpha_ops/research/prod_correlation.py) `_local_fallback`

- **What**：`_local_fallback` 返回值改为强制 `passed=False`（fail-closed），保留 `correlation=estimated_corr` 与 `source="local_estimate"` 供下游区分原因，但不再因估算值低于阈值而放行。
- **Why**：当前 complexity≥50 时 `estimated_corr=0.40/0.25 < max_correlation(0.7)` → `passed=True`，即官方 API 不可用时仍放行高复杂度 alpha，违反提交门禁 fail-closed 语义。与同文件 L124-129 的 `allow_local_fallback=False` 路径（`correlation=1.0, passed=False`）保持一致的保守取向。
- **How**：
  ```python
  return ProdCorrelationResult(
      correlation=estimated_corr,
      passed=False,  # F-052: local estimate must never auto-pass a submission gate
      max_threshold=self._max_correlation,
      source="local_estimate",
      error=reason or "official API unavailable, using local estimate (fail-closed)",
  )
  ```
  保留 `allow_local_fallback` 开关（仍控制是否返回本地估算结果 vs 抛错），但本地估算结果一律 `passed=False`，强制人工复核。
- **影响面检查**：`test_prod_correlation.py` 中依赖 `_local_fallback` 返回 `passed=True` 的用例需同步调整为期望 `passed=False`。执行时跑 `pytest tests/test_prod_correlation.py -v` 定位并修正。
- **次要观察（不在本次范围）**：`release_score_gate.py:250-251` `_cmp_required_max` 在 `actual is None and not policy.require_official_metrics` 时返回 `passed=True`。这是受 `require_official_metrics` 策略开关控制的故意设计（本地预览模式），非明显 bug，本次不改。若后续需提交门禁强制 fail-closed，再评估该开关语义。

#### C4-3. F-055：`fusion.py` max 分支补校验

**文件**：[brain_alpha_ops/research/fusion.py:152-156](file:///workspace/brain_alpha_ops/research/fusion.py)

- **What**：`composite_ensemble` 的 max 分支末尾 `return result`（L156）改为 `return _validate_fusion_expr(result, "ensemble_max")`。
- **Why**：同函数 average（L147）、rank_average（L150）、min（L161）分支均调用 `_validate_fusion_expr` 校验长度（≤512）与括号深度（≤12），唯独 max 跳过，可能产出超 BRAIN 平台限制的非法表达式。
- **How**：单行修改 `return _validate_fusion_expr(result, "ensemble_max")`。

#### C4-4. F-056：`_slot_submission.py` `return`→`continue`

**文件**：[brain_alpha_ops/research/backtest_flow_service/_slot_submission.py:87](file:///workspace/brain_alpha_ops/research/backtest_flow_service/_slot_submission.py)

- **What**：第 87 行 `return` 改为 `continue`。
- **Why**：`for slot in open_slots:` 循环内，单槽提交失败（`if not outcome.submitted:`）后 `return` 退出整个 `_fill_backtest_slots` 函数，3-slot 循环中第 1 槽失败则第 2、3 槽永不尝试；应为 `continue` 跳过当前失败槽继续下一槽（同函数 L52 去重场景已正确用 `continue`）。
- **How**：单行修改 `return` → `continue`。注意 L47 的 `return`（无候选可用）保持不变——池空时后续槽也无候选，提前退出合理。

---

### 阶段 B：Code Wiki 文档补充（仅编辑 `docs/CODE_WIKI.md`）

在现有第 8 章（安全模型）后追加第 9-14 章。每章以现有文档风格（中文 + 表格 + `file:///` 链接）撰写，引用真实文件路径。

- **B1. 第 9 章 HTTP API 端点参考**：列主要 POST 处理器与 GET 路由，含路径/请求体/响应体/鉴权/HIL 确认门。来源 [web/dispatch/web_post_routes.py](file:///workspace/brain_alpha_ops/web/dispatch/web_post_routes.py)、[web/dispatch/web_routes.py](file:///workspace/brain_alpha_ops/web/dispatch/web_routes.py)。重点 `/api/candidates/simulate`（HIL gate）、`/api/submit_*`（REAL_SUBMIT_DISABLED）、`/api/health`、`/api/snapshot/*`。

- **B2. 第 10 章 React 前端架构**：组件树（App → PhaseShell → views）、状态管理（AppStateContext composition root，[hooks/useAppState](file:///workspace/brain_alpha_ops/web/react_app/src/hooks/useAppState)）、SSE/轮询通信、activeView 路由、Vite 构建。说明 VirtualList 已拆为 CandidateTableDesktop/Mobile。

- **B3. 第 11 章 测试策略与结构**：测试标记（slow/integration/e2e/browser/live/readonly/mock，[tests/conftest.py](file:///workspace/tests/conftest.py)）、覆盖率门槛 80%（[pyproject.toml](file:///workspace/pyproject.toml)）、夹具工厂、E2E 框架（Playwright）。

- **B4. 第 12 章 CI/CD 流程**：[.github/workflows/](file:///workspace/.github/workflows/) 下 workflow 的触发条件、阶段、产物。

- **B5. 第 13 章 已知缺陷索引**：汇总评估报告 85 条缺陷编号/文件/严重度/状态。标注本系列修复的 17 项（前序 5 + 本轮 12）+ 已修复 15 项，其余 backlog。

- **B6. 第 14 章 贡献者指南**：代码规范（ruff/mypy，[pyproject.toml](file:///workspace/pyproject.toml)）、提交规范、分支策略、质量门禁脚本（[scripts/check_*.py](file:///workspace/scripts/)）。

---

## 假设与决策 (Assumptions & Decisions)

### 假设
1. 行号基于 2026-07-07 代码状态，执行时可能偏移，以缺陷 ID + 函数名为准定位。
2. `ThresholdPolicy.from_thresholds(thresholds, settings={})` 能处理空 dict（F-051），执行时确认；若不能则改为 `BrainSettings()` 默认实例。
3. `test_prod_correlation.py` 中依赖 `_local_fallback passed=True` 的用例需同步修正（F-052）。
4. C2 线程安全改动可能无直接并发测试，需人工复核锁覆盖完整性。
5. `docs/CODE_WIKI.md` 追加章节不破坏现有目录锚点（新增 9-14 章在末尾）。

### 决策
1. **优先级**：C2（P1 线程安全，收尾）→ C4（P1 数值正确性）→ B（文档）→ 最终验证。
2. **最小改动**：每个修复点只改必要行，不顺带重构；F-051/F-055/F-056 均单行修改。
3. **F-052 保守取向**：`_local_fallback` 一律 `passed=False`，保留 `allow_local_fallback` 开关控制"返回估算结果 vs 抛错"，但估算结果永不放行。
4. **F-052 次要观察不动**：`release_score_gate.py:_cmp_required_max` 的 `require_official_metrics` 开关语义为故意设计，本次不改，仅在文档标注。
5. **C2-3 锁粒度**：`_connect` 设 `isolation_level=None` + 写方法手动 `BEGIN IMMEDIATE`/`COMMIT`/`ROLLBACK`；读方法不动。
6. **验证方式**：每阶段跑相关 pytest 子集，失败即修。

---

## 验证步骤 (Verification Steps)

### C2 验证
1. `pytest tests/test_record_sqlite_index.py -v`（已存在）
2. `pytest -k "metrics or backend_registration or sqlite" -v`
3. 人工复核：metrics.py 所有读写方法均有 `with self._lock`；backend_registration 双检锁；record_sqlite_index 写事务 BEGIN IMMEDIATE + rollback。

### C4 验证
1. `pytest tests/test_prod_correlation.py -v`（已存在，F-052 可能需同步改测试）
2. `pytest tests/test_fusion_candidates.py -v`（已存在）
3. `pytest -k "release_score or fusion or prod_correlation or slot_submission or backtest_flow" -v`
4. 人工复核 4 处单行/小改。

### B 验证
1. 人工审阅 `docs/CODE_WIKI.md` 新增 6 章完整性与准确性。
2. 验证所有 `file:///` 链接指向真实文件（抽查 5+ 个）。

### 最终验证
1. `pytest -k "metrics or backend_registration or sqlite or release_score or fusion or prod_correlation or slot_submission" -v`（合并子集）
2. `pytest --cov=brain_alpha_ops --cov-fail-under=80`（若环境缺依赖，跑可运行子集并记录）
3. `python scripts/check_python_silent_broad_exceptions.py`（确认 C1 仍 OK）
4. `python scripts/check_architecture.py`（若存在）
5. 若有红线验证器：`python -m brain_alpha_ops.compliance.redline_verifier --block`（确认 zero_deviation 未破坏）

---

## 实施顺序

1. **C2-1** F-020：metrics.py 加锁（`__init__` + 6 方法）
2. **C2-2** F-028：backend_registration.py 双检锁
3. **C2-3** F-053：record_sqlite_index.py BEGIN IMMEDIATE
4. **C2 验证**：pytest 子集
5. **C4-1** F-051：release_score_gate.py 单行 `else {}`
6. **C4-2** F-052：prod_correlation.py `_local_fallback` fail-closed + 同步测试
7. **C4-3** F-055：fusion.py max 分支补校验
8. **C4-4** F-056：_slot_submission.py `return`→`continue`
9. **C4 验证**：pytest 子集
10. **B1-B6**：CODE_WIKI.md 追加 6 章
11. **最终验证**：合并 pytest + 质量门禁脚本

每步完成立即跑相关测试，失败即修，不累积。
