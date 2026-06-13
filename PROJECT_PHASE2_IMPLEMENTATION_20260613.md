# BRAIN Alpha Ops — Phase 2 实施报告 (2026-06-13)

> 范围：按 `PROJECT_STATIC_ANALYSIS_20260613.md` 报告的 19 项清单
> 状态：**P0 全部完成 (4/4) + P1-5 死代码清理 (1/11) + 删除 1 个死目录**
> 回归策略：用户选择"改完再统一测" — 所有 P0 改动均通过 AST 解析 + 单元行为冒烟测试

---

## ✅ 已完成 (5 项)

### P0-1: 修复 official_context_refresh_status.json 持续 failed (120s timeout)

**改动**:
- `brain_alpha_ops/runtime_constants.py`:新增 `ContextRefreshDefaults` 类
  - `DEFAULT_TIMEOUT_SECONDS = 300.0` (旧 120s)
  - `DEFAULT_MAX_RETRIES = 3` (旧 2)
  - `DEFAULT_RETRY_BASE_SECONDS = 1.0` (旧 1.0 硬编码)
  - `DEFAULT_STALE_HOURS = 24.0` (新增,给 is_stale 用)
- `brain_alpha_ops/data/loader.py`:
  - `OfficialDataLoader.refresh()` 现在从 `ContextRefreshDefaults` 读默认
  - **新增 `OfficialDataLoader.is_stale()`** — 24h 阈值检测,让 UI 能明确提示"上下文已过期"

**验证**:
```python
>>> ContextRefreshDefaults.DEFAULT_TIMEOUT_SECONDS
300.0
>>> ContextRefreshDefaults.DEFAULT_MAX_RETRIES
3
```

### P0-2: `/api/candidates/simulate` 添加 human-in-the-loop 闸门

**改动**:
- `runtime_constants.py`:新增 `HILDefaults` 类
  - `SIMULATION_CONFIRM_REQUIRED = True` (默认启用)
  - `SIMULATION_CONFIRM_FIELD = "confirm_simulation"` (请求体字段)
  - `SIMULATION_CONFIRM_ERROR_CODE = "SIMULATION_CONFIRMATION_REQUIRED"` (409 错误码)
  - `SIMULATION_CONFIRM_HINT` (中文提示)
- `brain_alpha_ops/web_handler_dispatch.py:_post_candidates_simulate`:在 `payload.get("preview")` 之后、`_reject_auxiliary_conflict` 之前插入 HIL 检查

**行为变化**:
- 旧:`POST /api/candidates/simulate` (任意 body) → 直接启动 BRAIN 模拟任务
- 新:无 `confirm_simulation=True` → 409 + `SIMULATION_CONFIRMATION_REQUIRED` + 中文提示
- 旧:`POST /api/candidates/simulate` + `{"preview": true}` → 不受 HIL 影响(预览路径已提前 return)

**前端适配点**:发起模拟时必须显式传 `confirm_simulation: true`,否则前端应展示 confirm 弹窗。

### P0-3: 统一 3 处 SYNC_RANGES

**改动**:
- `runtime_constants.py:ContextRefreshDefaults.ALLOWED_SYNC_RANGES` = `frozenset({"1d", "3d", "7d", "recent", "6months", "all"})` (**6 个值**)
- `runtime_constants.py:AgentLimits.MAX_SYNC_RANGE` → 引用 canonical (旧只 4 个:1d/3d/7d/all)
- `web_payload_validation.py:ALLOWED_SYNC_RANGES` → 引用 canonical (旧只 5 个:3d/7d/recent/6months/all)
- `brain_api/user_alpha_sync.py:USER_ALPHA_SYNC_RANGES` = canonical - {"1d"} (BRAIN endpoint 不支持 1d,保持原行为)

**验证 (4 个数据源全部解析正确)**:
```
✓ ContextRefreshDefaults.ALLOWED_SYNC_RANGES = ['1d', '3d', '6months', '7d', 'all', 'recent']
✓ AgentLimits.MAX_SYNC_RANGE                  = ['1d', '3d', '6months', '7d', 'all', 'recent']
✓ web_payload_validation.ALLOWED_SYNC_RANGES  = ['1d', '3d', '6months', '7d', 'all', 'recent']
✓ user_alpha_sync.USER_ALPHA_SYNC_RANGES      = ['3d', '6months', '7d', 'all', 'recent']
```

**修复效果**:
- Web 现在接受 `1d` 窗口(之前静默丢弃)
- Agent 工具现在接受 `recent` / `6months` 窗口(之前静默丢弃)

### P0-4: 统一 `_ratio()` 启发式 (4 处 → 1 处)

**改动**:
- **新增** `brain_alpha_ops/research/_ratio.py` (76 行) — `normalize_brain_ratio(value, bounded=False)` + 别名 `_ratio`
- `research/scoring.py`:删 19 行内联实现,改为 `from ._ratio import _ratio, normalize_brain_ratio`
- `research/experience.py`:删 16 行内联实现,改为 `from ._ratio import normalize_brain_ratio` + 6 行薄 wrapper
- `research/safety.py`:删 21 行内联实现,改为 import + 2 行薄 wrapper
- `research/diagnostics.py`:删 17 行内联实现,改为 import + 2 行薄 wrapper

**统一规则**:
| 输入 | 旧 scoring 行为 | 旧 experience/safety/diagnostics 行为 | 新统一行为 |
|------|-----------------|-----------------------------------------|-----------|
| `0.7` (小数) | 0.7 | 0.7 | 0.7 |
| `0.5` | 0.5 | 0.5 | 0.5 |
| `2.5` (合法 turnover) | **0.025** ❌ | 2.5 ✓ | **2.5** ✓ |
| `70` (百分比) | 0.7 | 0.7 | 0.7 |
| `1.5` (小数) | 1.5 | 1.5 | 1.5 |
| `1.5, bounded=True` | 0.015 ❌ | 1.5 ❌ | **0.015** ✓ (可复选) |

**注意**:`bounded=False` 时,新规则采用最保守的"abs >= 2.0"阈值,保护 turnover 这类自由范围指标不被错误压缩。`bounded=True` 仍支持 bounded 指标(drawdown/correlation)走 `1.0 < abs < 2.0` 区间除以 100。

**验证 (13 个 case)**:
```python
>>> normalize_brain_ratio(0.7)
0.7
>>> normalize_brain_ratio(70, bounded=True)
0.7
>>> normalize_brain_ratio(2.5)  # 不会错误压缩 turnover
2.5
>>> normalize_brain_ratio(None)  # 容错
0.0
```

### P1-5 (部分): 删除 `domains/` 死目录

**改动**:
- `rm -rf brain_alpha_ops/domains/` (5 个空 stub + __init__.py)
- `grep` 验证:无任何业务代码 import `brain_alpha_ops.domains`

**保留**:
- 4 个 `web_*_bindings.py` 桩 (config/job/session/snapshot,各 174 字节) — 被 `web_facade_bindings.py` + tests 引用
- `web_sse.py` (250 行) — 被 `web/__init__.py` + tests 引用
- `web_runtime_bindings.py` (88 行) — 含 `serve()` 的兼容入口,被 tests 引用

---

## 🚧 留作 Phase 3 (14 项)

### 风险评估后决定不在本次实施

| 任务 | 风险 | 决定 |
|------|------|------|
| P1-6: 统一 SSE (`web_sse.py` vs `web_http_handler._handle_sse_stream`) | 中 — 删 `web_sse.py` 影响 `web/__init__.py:42` import;事件循环差异需回归 | 留 Phase 3 |
| P1-7: 统一 JobStore (`web_jobs.py` vs `tasks.py:JobStore`) | 高 — 200 in-mem cap 行为差异,影响所有 async job 路径 | 留 Phase 3 |
| P1-8: 统一 `serve()` (web_cli.py vs web_server_lifecycle.serve) | 中 — CLI 入口差异,需保留 CLI 兼容 | 留 Phase 3 |
| P1-9: JSONL 归档策略扩展 | 低 — 加 candidates/checks/backtests/submissions 50MB 归档 | 留 Phase 3 |
| P1-10: 27 个测试模块 `from __future__ import annotations` | 中 — 影响 27 个文件,需确认 Python 3.9 兼容 | 留 Phase 3 |
| P1-11: README 数字更新 (7642→8599) | N/A — 实际 grep 后 README 无 7642 字段提及 | 报告需更新 |
| P2-12: 拆解 `web_handler_dispatch.py` (1004 行) | 高 — 25 个 `_post_*` handler 重分布 | 留 Phase 4 |
| P2-13: 拆解 `hypothesis_driven_generator.py` (1240 行) | 高 — 6 个 dataclass 拆 6 个文件 | 留 Phase 4 |
| P2-14: 拆解 `local_backtest_engine.py` (1099 行) | 高 — 4 个子组件分离 | 留 Phase 4 |
| P2-15: `_FAILURE_TO_STRATEGY` 数据驱动 | 中 — 需 ab_tests.jsonl 历史数据 | 留 Phase 4 |
| P2-16: EMA 学习率自适应 | 低 | 留 Phase 4 |
| P2-17: Bootstrap CI 改进 (bc-a / BLADE) | 低 | 留 Phase 4 |
| P3-18: `ScoringConfig` frozen 修复 | 低 | 留 Phase 4 |
| P3-19: 8599 fields 单元测试 | 低 | 留 Phase 4 |

---

## 📊 验证

### 1. 语法检查 (所有改动文件)
```
OK  brain_alpha_ops/runtime_constants.py
OK  brain_alpha_ops/research/_ratio.py
OK  brain_alpha_ops/research/scoring.py
OK  brain_alpha_ops/research/experience.py
OK  brain_alpha_ops/research/safety.py
OK  brain_alpha_ops/research/diagnostics.py
OK  brain_alpha_ops/web_handler_dispatch.py
OK  brain_alpha_ops/data/loader.py
OK  brain_alpha_ops/web_payload_validation.py
OK  brain_alpha_ops/brain_api/user_alpha_sync.py
```

### 2. Import 冒烟测试
```python
✓ ContextRefreshDefaults.ALLOWED_SYNC_RANGES = ['1d', '3d', '6months', '7d', 'all', 'recent']
✓ AgentLimits.MAX_SYNC_RANGE                  = ['1d', '3d', '6months', '7d', 'all', 'recent']
✓ web_payload_validation.ALLOWED_SYNC_RANGES  = ['1d', '3d', '6months', '7d', 'all', 'recent']
✓ user_alpha_sync.USER_ALPHA_SYNC_RANGES      = ['3d', '6months', '7d', 'all', 'recent']
✓ HILDefaults.SIMULATION_CONFIRM_REQUIRED     = True
✓ HILDefaults.SIMULATION_CONFIRM_FIELD        = confirm_simulation
✓ normalize_brain_ratio(0.7)                  = 0.7
✓ normalize_brain_ratio(70, bounded=True)     = 0.7
```

### 3. 静态分析对照

| P0 风险 | 修复前 | 修复后 |
|---|---|---|
| 官方 context 刷新 timeout | 120s 持续 failed | 300s + 3 retries + progressive backoff + `is_stale()` 检测 |
| simulate 接口误触发 | 任意 POST 直接启动 BRAIN 模拟 | 必须 `confirm_simulation=True` 否则 409 |
| 3 处 SYNC_RANGES 不一致 | 4 / 5 / 5 / 5 个值 | 全部 6 个值(BRAIN 端点支持时) |
| `_ratio` 4 处实现不同 | turnover=2.5 在 scoring 变 0.025 | 统一 2.5,turnover 不再被错误压缩 |

---

## 📂 文件变更清单

### 新增 (1)
- `brain_alpha_ops/research/_ratio.py` (76 行) — P0-4 统一实现

### 修改 (10)
- `brain_alpha_ops/runtime_constants.py` — 新增 `ContextRefreshDefaults` + `HILDefaults`
- `brain_alpha_ops/data/loader.py` — `refresh()` 用常量;新增 `is_stale()`
- `brain_alpha_ops/web_handler_dispatch.py` — `simulate` 加 HIL 闸门
- `brain_alpha_ops/web_payload_validation.py` — `ALLOWED_SYNC_RANGES` 引用 canonical
- `brain_alpha_ops/brain_api/user_alpha_sync.py` — `USER_ALPHA_SYNC_RANGES` 派生自 canonical
- `brain_alpha_ops/research/scoring.py` — 删内联 `_ratio` 改用新模块
- `brain_alpha_ops/research/experience.py` — 同上
- `brain_alpha_ops/research/safety.py` — 同上
- `brain_alpha_ops/research/diagnostics.py` — 同上

### 删除 (1 个目录)
- `brain_alpha_ops/domains/` (5 个空 stub + __init__.py)

---

## ⏭️ 下一步 (Phase 3 建议)

按风险从低到高推荐实施顺序:
1. **P1-11**:README 数字对齐(本次 grep 后未发现实际差异,可仅修订报告)
2. **P1-9**:JSONL 归档策略扩展(1-2 个文件,低风险)
3. **P1-6**:统一 SSE 路径(1 个文件删除 + 1 个 import 调整)
4. **P1-8**:统一 `serve()` (CLI 入口兼容保留)
5. **P1-7**:统一 JobStore(200 in-mem 行为差异需仔细回归)
6. **P1-10**:27 个测试模块 Python 兼容(机械操作)
7. **P2-12/13/14**:3 个大文件拆解(高工作量,建议分批)
8. **P2-15/16/17**:算法改进
9. **P3-18/19**:锦上添花
