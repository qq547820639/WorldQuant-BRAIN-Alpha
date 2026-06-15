# REVIEW_20260615_VERIFICATION — 5 P0 修复独立验证

> **结论先给：宣称"106/106 通过"与实际不符。**
> 实际：`4 failed, 2645 passed, 3 skipped`（317.36s）。
> 更严重的是，4 个被断言"已修复"的 P0 里有 **2 个** 走的是"改测试让它消失"路线，导致 **2 个全新生产 bug 处于潜伏状态**，1 个是真·生产安全回归（real submit 守门被绕过）。

---

## 0. 用户原文与本次工作范围

### 用户原文
> "全 5 个 P0 缺陷修复完毕。106/106 测试通过。"

### 工作范围
1. 独立运行完整 pytest 套件核对数字
2. 对 5 个宣称修复用 `git diff HEAD` 验证落点
3. 找出 4 个**仍失败**测试的根因
4. 找出用户在"修复"过程中**新引入**的生产 bug

---

## 1. 数字核验

| 指标 | 宣称 | 实际（本次 09:12 重跑） | 差异 |
|---|---|---|---|
| Passed | 106 | **2645** | 口径不一致（用户把"5 P0 相关子集"当全量） |
| Failed | 0 | **4** | 漏报 4 个 |
| Skipped | 0 | 3 | — |
| 总耗时 | — | 317.36s | — |
| 全量测试总数 | 106 | 2649 + 3 = 2652 | 宣称值连数量级都不对 |

> **判定**：用户的"106/106"是仅针对 5 个 P0 所涉及测试文件的子集计数（5+33+46+2+1+12+2+1=102，约为 106），**不能与全量测试通过率混用**。

---

## 2. 5 P0 修复落地核验

逐项 `git diff HEAD` 检查，结论：**5 个 P0 修复文件均存在，但 2 个生产代码修复有副作用**。

| P0 | 根因 | 修复落点 | 修复判定 |
|---|---|---|---|
| P0-1 | `validate_run_config` 在写配置前要求 cache 已存在 | `config/_loader.py` `_is_dataset_id_in_official_cache` cache 不存在时返回 True | ✅ 安全（"首次安装友好"合理） |
| P0-2 | `_clean_state_tracker_text` fixture 与 checker 契约漂移 | `tests/test_review_gap_closure_tracker.py`（1115 行变更）+ fixture 重写 | ✅ 测试侧，无生产副作用 |
| P0-3 | `fake_run` monkeypatch 缺 `actionable_ok` 字段 | `tests/test_quality_gate.py`（line 152-154）`fake_run` 失败时加 `actionable_ok: False` | ✅ 测试侧，无生产副作用 |
| P0-4 | 测试 Loader 用 `get_fields` 但生产代码调 `list_fields` | `tests/test_generation.py` 给 3 个测试 Loader 加 `list_fields = get_fields` 别名 | 🔴 **P0-4 修复方向错误**（见 §4.1） |
| P0-5 | `max_generation_attempts=3` 导致多一次生成调用 | `tests/test_generation_phase.py` line 60 断言改为接受重试 | ✅ 测试侧（但回避了生产 bug） |

---

## 3. 4 个仍失败测试（含根因分析）

### 3.1 🔴 `test_web_candidate_generation.py::test_web_local_check_and_submit_routes_do_not_claim_official_actions`

```
tests/test_web_candidate_generation.py:750: in test_web_local_check_and_submit_routes_do_not_claim_official_actions
    assert submit["ok"] is False
E   assert True is False
```

**根因（生产代码回归）**：`web/__init__.py:_real_submit` 被重写为
- 原：返回 `_submit_disabled_payload()`（`ok=False`, `error_code=REAL_SUBMIT_DISABLED_WEB_FLOW`）
- 现：函数顶部**强制设置** `os.environ["BRAIN_ALPHA_FORCE_REAL_SUBMIT"] = "1"` + `BRAIN_ALPHA_ENABLE_REAL_SUBMIT_TESTS = "1"`，再启动线程执行 `_run_submit_alpha_job`，**真实**调用 BRAIN `submit_simulation / poll_simulation / check_alpha / submit_alpha`

**影响范围**：
1. 该测试断言的"web 端不声称为 official action"契约被打破
2. **生产安全回归**：`runtime_constants.REAL_SUBMIT_DISABLED_WEB_FLOW: Final[bool] = True` 守门
   - `brain_api/official_simulation.py:209-210` 读取 `BRAIN_ALPHA_FORCE_REAL_SUBMIT` 决定是否绕过
   - 而 conftest 默认 `os.environ.setdefault("BRAIN_ALPHA_FORCE_REAL_SUBMIT", "1")`（`tests/conftest.py:16`）
   - **生产 web 端一旦被请求 `/api/submit` 即会**：(a) 强制设置 env，(b) 走线程真提交到 BRAIN，`REAL_SUBMIT_DISABLED_WEB_FLOW` 完全失守

**为什么这个测试"必须失败"**：
原 P0 列表（REVIEW_20260615.md P0-3 即"web 端不声称为 official action"）就是用这个测试做守门；用户新加的 `_run_submit_alpha_job` 恰恰是让这个守门失效。

**修复建议**（不要让测试消失）：
- 选项 A：恢复 `return _submit_disabled_payload()`，把真提交逻辑封装为可选 `_real_submit_live()`，用 `BRAIN_ALPHA_ENABLE_REAL_SUBMIT_TESTS=1` + 显式 `?force_live=1` 双重开关
- 选项 B：在 `_real_submit` 顶部加守门：
  ```python
  if REAL_SUBMIT_DISABLED_WEB_FLOW and not os.environ.get("BRAIN_ALPHA_FORCE_REAL_SUBMIT") == "1":
      return _submit_disabled_payload()
  ```
  并把 `os.environ.set(...)` 删掉（不要让 web 端自己开锁）

### 3.2 🔴 `test_data_loader.py::test_refresh_replaces_existing_data_after_successful_fresh_load`

```
tests/test_data_loader.py:45: in test_refresh_replaces_existing_data_after_successful_fresh_load
    assert result["status"] == "refreshed"
E   AssertionError: assert 'no_change' == 'refreshed'
```

**根因**：`data/loader.py:335-349` P3-29 patch 写反了 delta 计算顺序：

```python
# 当前错误顺序
self._loaded_root = fresh._loaded_root
_f_delta = self.field_count - old_fields        # old_fields 是 self 改之前的快照
# 但 self._fields 已在更早处被 self._fields = dict(fresh._fields) 覆盖
# self.field_count 现在等于 fresh.field_count, 而 old_fields 来自修改前
# 当测试 monkey-patch 把 fresh 设成 self 时, old_fields == self.field_count, delta = 0
```

**生产影响**：
- 测试场景下 `_f_delta = 0` → status=`no_change`（测试失败）
- 生产场景下，`_f_delta` 偶然为 0 时（数据集/字段都没变）应返回 `no_change`（这是合理的）
- 但**生产场景下字段真变了也会判 no_change**，因为 `old_fields` 的快照是来自 `self.field_count` 改前，改后 self 已等于 fresh

**为什么测试失败**：
- 测试 fixture 把 fresh == self（monkey-patch），所以 `self._fields = dict(fresh._fields)` 之后 `self.field_count == old_fields`，永远 0
- 即 P3-29 patch 永远返回 `no_change`

**修复建议**：
```python
# 正确顺序：先取 old, 再覆盖 self
old_fields = self.field_count
old_operators = self.operator_count
old_datasets = self.dataset_count
# ... 覆盖 self._fields 等 ...
self._loaded_root = fresh._loaded_root
_f_delta = self.field_count - old_fields
```

### 3.3 🔴 `test_log_redaction_guard.py::test_log_redaction_guard_accepts_current_package`

```
tests/test_log_redaction_guard.py:15: in test_log_redaction_guard_accepts_current_package
    assert result["ok"] is True
E   assert False is True
```

**根因**：`brain_alpha_ops/research/pipeline_candidates.py:75` 的 P1-15 patch
```python
logger.warning("build_scorecard failed for %s: %s", candidate.alpha_id, _score_msg)
```
触发 redaction 规则 `raw_user_value_log_arg`（候选 ID 视为"raw user value"）。**且** `pipeline_candidates.py` 整个文件**没有任何 logger 定义**（已用 grep 确认：无 `import logging`、无 `logger = logging.getLogger(...)`、无任何模块级 logger 变量）。

**生产影响**：
- 测试场景下：try 块不触发，日志函数不被调用，但 `from . import ...` 链上 `pipeline_candidates` 的导入本身会让 P1-15 代码被 lint/扫描器静态分析命中（`redaction` 工具是基于 AST 的）
- 生产场景下：**任何一次 `build_scorecard` 失败都会导致 `NameError: name 'logger' is not defined`**，把单次评分失败扩大成整个 prefilter 循环崩溃

**修复建议**（两件事，必须都做）：
1. 在 `pipeline_candidates.py` 顶部加：
   ```python
   import logging
   logger = logging.getLogger(__name__)
   ```
2. 把 `logger.warning` 的第一参数改写，避免传 `candidate.alpha_id`（用 `id(candidate)` 或 truncate）：
   ```python
   logger.warning("build_scorecard failed: %s", _score_msg)
   ```

### 3.4 🟡 `test_backtest_submission.py::test_backtest_submission_service_records_request_failure_event`

```
E   AssertionError: assert True is False
E    +  where True = BacktestSubmitOutcome(submitted=False, halted=True,
E        error=BrainAPIError('HTTP 500: upstream failed'),
E        error_code='SIMULATION_SUBMIT_ERROR',
E        note='official simulation request failed (status=500); deferring official calls for 30.0s').halted
```

**根因**：`brain_alpha_ops/research/backtest_submission.py` P0-6 patch 把非 rate-limit 的 5xx 错误也视为"transient"，触发 30s 暂停。测试仍用旧期望"非 rate-limit 失败不应 halt"。

**生产影响**：
- 真线上 BRAIN 5xx 一来就会自动暂停 30s，不区分瞬时错误和持续错误 → 在持续故障期间 pipeline 会反复暂停
- 测试应当更新（5xx 是合理的"暂停"），但**生产逻辑需要加"持续 5xx 后升级报警"**，否则 pipeline 会安静地慢死

**修复建议**：
- 选项 A：测试期望更新为 `outcome.halted is True`（接受"5xx 触发 halt"）
- 选项 B：生产逻辑加指数退避 + 连续 N 次失败后停止整个 pipeline

---

## 4. 用户"修复"过程中新引入的生产 bug

### 4.1 🔴 P0-4 修复方向错误：测试补全不能替代生产修复

| 项 | 详情 |
|---|---|
| **症状** | `OfficialDataLoader` 没有 `list_fields()` 方法，但 `generator.py:151` 调 `self._loader.list_fields(ds_id or "all")` |
| **原报告 P0-4 根因** | 测试 Loader 用 `get_fields` 但生产代码调 `list_fields` |
| **用户"修复"** | 给 3 个测试 Loader 类加 `list_fields = get_fields` 别名（`tests/test_generation.py`） |
| **真实问题** | **生产代码调用的就是 `OfficialDataLoader`，没有这个别名**。测试加别名让测试绿，但生产 AttributeError 一旦触发即崩 |
| **正确修复** | 二选一：(a) 在 `OfficialDataLoader` 加 `list_fields = get_fields` 别名（生产侧），(b) 把 `generator.py:151` 改回 `self._loader.get_fields(ds_id or "all")`（同义） |

**生产激活路径**：pipeline 启动 → `_load_official_context()` → `generator.generate()` → `list_fields()` → **AttributeError**。整条 production pipeline 在 `OfficialDataLoader` 是单例时是必触发。

**严重度**：🔴 Blocker。pipeline 启动 1 次必崩。

### 4.2 🔴 `pipeline_candidates.py:74` NameError 风险

详见 §3.3。`logger` 完全没定义。**任何一次** `build_scorecard` 失败即触发，try/except 自身不能捕 NameError（它确实能，但任何更宽的 try/except 之上没有 logger 初始化的话仍崩）。

**严重度**：🔴 Blocker。`build_scorecard` 失败概率 > 0（异常路径已被显式打开）。

### 4.3 🔴 `data/loader.py:338-340` P3-29 delta 计算顺序错误

详见 §3.2。

**严重度**：🟡 P1。`refresh` 路径在生产几乎不被频繁调用（仅 web 端"刷新官方上下文"按钮），但若调用则永远返回 `no_change`（即便字段真变了）→ 上层 `_local_prefilter` 误判"无新数据可用" → pipeline 跳过新字段。

### 4.4 🔴 `web/__init__.py:_real_submit` 守门被绕过的生产安全回归

详见 §3.1。**这是用户在"P0 修复"过程中主动打开的真提交路径。**

**严重度**：🔴 Blocker / 安全。`REAL_SUBMIT_DISABLED_WEB_FLOW` 守门 + `web_submission_single.py:20` 的 `from brain_alpha_ops.runtime_constants import REAL_SUBMIT_DISABLED_WEB_FLOW` 都还在，但 `_real_submit` 函数顶部强制 `os.environ["BRAIN_ALPHA_FORCE_REAL_SUBMIT"] = "1"`，让守门形同虚设。

**触发链**：
1. 用户在 Web UI 点击"提交"
2. 路由进 `_real_submit(payload)`（`web/__init__.py:344`）
3. 强制 `os.environ["BRAIN_ALPHA_FORCE_REAL_SUBMIT"] = "1"`
4. 强制 `os.environ["BRAIN_ALPHA_ENABLE_REAL_SUBMIT_TESTS"] = "1"`
5. 启动线程跑 `_run_submit_alpha_job`
6. 线程内 `api.authenticate() / submit_simulation / poll_simulation / check_alpha / submit_alpha` **真打 BRAIN**
7. `brain_api/official_simulation.py:209-210` 检查 env 是 1 → 跳过 `REAL_SUBMIT_DISABLED_WEB_FLOW` 守门 → 真提交

---

## 5. 修复优先级建议

| 序 | 项 | 文件 | 风险 | 工作量 |
|---|---|---|---|---|
| 1 | 4.4 守门恢复 | `web/__init__.py:344-376` | 🔴 安全 | 5 行 |
| 2 | 4.1 P0-4 改向 | `data/loader.py` + `research/generator.py` 二选一 | 🔴 启动崩 | 1 行 |
| 3 | 4.2 NameError 风险 | `research/pipeline_candidates.py:1-2` 加 logger + 第 75 行改写 | 🔴 评分路径崩 | 3 行 |
| 4 | 4.3 delta 顺序 | `data/loader.py:335-349` 取 old 后改 self | 🟡 refresh 失效 | 5 行 |
| 5 | 3.4 测试期望更新 | `tests/test_backtest_submission.py:104` | 🟡 一致性 | 1 行 |
| 6 | 3.1 测试回归后通过 | 修完 4.4 后此测试自动恢复 | — | 0 |
| 7 | 3.2 测试回归后通过 | 修完 4.3 后此测试自动恢复 | — | 0 |
| 8 | 3.3 测试回归后通过 | 修完 4.2 后此测试自动恢复 | — | 0 |

> 修完 1-5 后，4 个失败测试预计**全部自动转绿**（它们是 4 个新生产 bug 的下游症状）。

---

## 6. 验证方法学（用户下次"修完"时可参考）

### 6.1 关键校验点
1. **全量跑**：用 `python -m pytest`（不指定文件），不要看子集通过率
2. **每个"修复"都看 diff**：`git diff HEAD path/to/file` 确认改动方向对不对
3. **看测试是否在隐藏 bug**：测试从红变绿时，**也**要看生产代码的对应路径是否真的被修了
4. **守门对称性检查**：每次动 `BRAIN_ALPHA_FORCE_REAL_SUBMIT` 这类环境变量，要 grep 全仓确认"setdefault / setenv"是不是在多个地方同时生效
5. **logger 静态扫描**：每个 `logger.warning(...)` 调用前都要确认 `logger = logging.getLogger(__name__)` 在文件顶部

### 6.2 已加入 MEMORY 长期教训
详见 `.workbuddy/memory/MEMORY.md` "测试反咬回归" 段。

---

## 7. 一句话总结

> 5 个 P0 修复的"形"都到位，但其中 1 个（P0-4）走的是改测试方向（生产没修），1 个"附带优化"（web 真提交路径 + loader status 二分）直接打破了两个已有的安全/正确性守门，2 个 P1 修复（pipeline_candidates NameError / data/loader delta）没做就合入了。
> 真正的"修复完毕"应当是：(a) P0-4 改 `OfficialDataLoader` 而非测试 fixture，(b) `_real_submit` 加守门 + 删 `os.environ.set`，(c) `pipeline_candidates` 加 `import logging` + `logger = logging.getLogger(__name__)`，(d) `data/loader` 改 delta 顺序。
