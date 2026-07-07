# BRAIN Alpha Ops — 最终验证执行计划

> 承接 `/workspace/.trae/documents/brain-alpha-ops-remaining-work-execution-plan.md`
> 阶段 C2(线程安全)/ C4(数值正确性)/ B(Code Wiki 文档)均已实施完毕
> 本计划聚焦最后一环:**最终验证** + 1 项文档计数修正
> 验证日期:2026-07-07

---

## 摘要

Phase 1 只读探索已逐项确认:C2 三项(F-020/F-028/F-053)、C4 四项(F-051/F-052/F-055/F-056)、F-052 回归测试、CODE_WIKI.md 6 个新章节(9-14)全部就位。剩余工作仅为:

1. **修正 1 项文档计数偏差** — CODE_WIKI.md 第 13.1 节标题"17 项"但表格实际仅 12 行
2. **执行最终验证**(只读) — 3 个可运行测试文件 + 7 文件 py_compile + 5 个质量门禁脚本 + redline_verifier 阻断模式

无新代码变更(除 1 行文档计数修正)。验证通过即代表本系列工作全部完成。

---

## 当前状态分析(Phase 1 探索结论)

### 已确认就位的修复(全部 PASS)

| 修复 | 文件 | 行号 | 状态 |
|------|------|------|------|
| F-020 | [metrics.py](file:///workspace/brain_alpha_ops/metrics.py) | L51/56/62/68/85/105 | `threading.Lock()` 守护所有读写 ✅ |
| F-028 | [backend_registration.py](file:///workspace/brain_alpha_ops/backend_registration.py) | L70/73-83 | 双检锁 `_api_lock` ✅ |
| F-053 | [record_sqlite_index.py](file:///workspace/brain_alpha_ops/research/record_sqlite_index.py) | L172/41/67 | `isolation_level=None` + `BEGIN IMMEDIATE` ✅ |
| F-051 | [release_score_gate.py](file:///workspace/brain_alpha_ops/scoring/release_score_gate/release_score_gate.py) | L418 | `else {}`(非 `else metrics`) ✅ |
| F-052 | [prod_correlation.py](file:///workspace/brain_alpha_ops/research/prod_correlation.py) | L271 | `passed=False`(fail-closed) ✅ |
| F-055 | [fusion.py](file:///workspace/brain_alpha_ops/research/fusion.py) | L160 | `_validate_fusion_expr(result, "ensemble_max")` ✅ |
| F-056 | [_slot_submission.py](file:///workspace/brain_alpha_ops/research/backtest_flow_service/_slot_submission.py) | L92 | `continue`(非 `return`) ✅ |
| F-052 回归测试 | [test_prod_correlation.py](file:///workspace/tests/test_prod_correlation.py) | L79-91 | `test_fallback_is_fail_closed_even_when_estimate_below_threshold` ✅ |

### CODE_WIKI.md 章节完整性

文件共 1256 行,6 个新章节全部存在且内容充实(非 stub):

| 章节 | 起始行 | 长度 | 状态 |
|------|--------|------|------|
| 第 9 章 HTTP API 端点参考 | L946 | ~73 行 | ✅ 两级字典分派 + GET/POST 路由表 + SSE |
| 第 10 章 React 前端架构 | L1021 | ~82 行 | ✅ 组件树 + 状态管理 + 11 视图 + PhaseShell + 通信 |
| 第 11 章 测试策略与结构 | L1105 | ~41 行 | ✅ 7 markers + 80% 覆盖率 + fixtures + E2E |
| 第 12 章 CI/CD 流程 | L1148 | ~27 行 | ✅ Quality Gate 3 jobs + Build Release 2 jobs |
| 第 13 章 已知缺陷索引 | L1177 | ~33 行 | ⚠️ 13.1 标题"17 项"但表格仅 12 行 |
| 第 14 章 贡献者指南 | L1212 | ~43 行 | ✅ ruff/mypy/eslint/tsc + 20+ 脚本 + 分支策略 |

### 质量门禁脚本清单(全部存在)

| 脚本 | 用途 |
|------|------|
| [check_python_silent_broad_exceptions.py](file:///workspace/scripts/check_python_silent_broad_exceptions.py) | 静默宽异常捕获审计 |
| [check_architecture.py](file:///workspace/scripts/check_architecture.py) | 模块依赖规则校验(shared/brain_api/research/web 分层) |
| [final_release_gate.py](file:///workspace/scripts/final_release_gate.py) | Fail-closed 最终发布就绪门禁 |
| [check_dependency_policy.py](file:///workspace/scripts/check_dependency_policy.py) | 离线依赖策略检查 |
| [check_log_redaction.py](file:///workspace/scripts/check_log_redaction.py) | 日志脱敏绕过检测 |
| [check_module_size.py](file:///workspace/scripts/check_module_size.py) | 模块大小基线审计 |
| [check_capability_registry.py](file:///workspace/scripts/check_capability_registry.py) | BRAIN 能力注册表一致性 |
| [check_brain_contract.py](file:///workspace/scripts/check_brain_contract.py) | BRAIN 生产契约零偏差验证 |
| [scan_sensitive_artifacts.py](file:///workspace/scripts/scan_sensitive_artifacts.py) | 凭据泄露扫描 |
| [redline_verifier.py](file:///workspace/brain_alpha_ops/compliance/redline_verifier.py) | 6 条红线验证,`--block` 阻断模式退出码 2 |

### 环境约束

- **numpy 未在 requirements.lock 中**:全量 `pytest` collection 会因 `brain_alpha_ops/scoring/anti_overfit/permutation.py` 导入 numpy 而报 60+ collection 错误。这是预先存在的环境问题,与本系列修改无关。
- **应对策略**:不使用 `pytest -k`(仍扫描全部文件 collection),改为直接指定 3 个不依赖 numpy 的测试文件运行。

### 可运行测试文件(经 Glob 确认)

| 测试文件 | 对应修复 | 预期 |
|----------|---------|------|
| [test_prod_correlation.py](file:///workspace/tests/test_prod_correlation.py) | F-052 | 26 passed(含新增回归测试) |
| [test_record_sqlite_index.py](file:///workspace/tests/test_record_sqlite_index.py) | F-053 | 4 passed |
| [test_fusion_candidates.py](file:///workspace/tests/test_fusion_candidates.py) | F-055 | 需验证(可能因 fusion 导入链触发 numpy) |

> F-020(metrics)/F-028(backend_registration)/F-051(release_score_gate)/F-056(_slot_submission)无独立测试文件,以 `py_compile` + 功能性导入检查代替。

---

## 提议变更

### 变更 1:修正 CODE_WIKI.md 第 13.1 节计数(1 行编辑)

- **文件**:`/workspace/docs/CODE_WIKI.md`
- **位置**:第 1181 行
- **改法**:`### 13.1 本系列已修复（17 项）` → `### 13.1 本系列已修复（12 项）`
- **原因**:表格实际仅 12 行(5 前序:F-005/F-006/F-007/W-001/U-015 + 7 本轮:F-020/F-028/F-051/F-052/F-053/F-055/F-056),标题计数不符。修正为 12 使标题与表格一致。
- **影响范围**:仅文档准确性,无功能影响。

### 变更 2:执行最终验证(只读,无代码变更)

分 7 步执行,每步完成即记录结果,失败即诊断(不累积)。

#### 步骤 2.1 — 7 文件 py_compile 语法检查

确认全部 C2/C4 修改文件语法正确:

```bash
python -m py_compile \
  brain_alpha_ops/metrics.py \
  brain_alpha_ops/backend_registration.py \
  brain_alpha_ops/research/record_sqlite_index.py \
  brain_alpha_ops/scoring/release_score_gate/release_score_gate.py \
  brain_alpha_ops/research/prod_correlation.py \
  brain_alpha_ops/research/fusion.py \
  brain_alpha_ops/research/backtest_flow_service/_slot_submission.py
```

预期:无输出(全部通过)。退出码 0。

#### 步骤 2.2 — 直接运行 3 个测试文件(绕过 numpy collection 错误)

```bash
python -m pytest tests/test_prod_correlation.py tests/test_record_sqlite_index.py -v -p no:cacheprovider
```

预期:
- test_prod_correlation.py:26 passed(含 F-052 回归测试)
- test_record_sqlite_index.py:4 passed

若 `test_fusion_candidates.py` 因 fusion 导入链触发 numpy,单独尝试;失败则记录为预先存在的环境问题,不影响本系列验证结论。

#### 步骤 2.3 — C2 模块独立导入检查(F-020/F-028/F-053)

由于无独立测试文件,用 Python 内联脚本验证导入与基本行为:

```bash
python -c "
import threading
from brain_alpha_ops.metrics import MetricsCollector
m = MetricsCollector()
m.counter('test', 1)
assert m.summary()['counters']  # 锁内快照可读

from brain_alpha_ops.backend_registration import _get_brain_api, _api_lock
assert isinstance(_api_lock, type(threading.Lock()))

from brain_alpha_ops.research.record_sqlite_index import RecordSqliteIndex
import sqlite3, tempfile, os
with tempfile.TemporaryDirectory() as d:
    idx = RecordSqliteIndex(os.path.join(d, 't.db'))
    idx.append_record('a.jsonl', 0)
    assert idx.latest_index('a.jsonl') == 0
print('C2 import + behavior check: PASS')
"
```

预期:`C2 import + behavior check: PASS`

#### 步骤 2.4 — C4 功能性验证(F-051/F-055/F-056)

```bash
python -c "
# F-055: fusion max 分支校验
from brain_alpha_ops.research.fusion import composite_ensemble
r = composite_ensemble(['rank(close)', 'rank(volume)'], mode='max')
assert r and 'max' in r, f'F-055 max branch broken: {r!r}'
# 超长输入应被校验拦截返回空串
long_exprs = ['rank(close)'] * 100
r2 = composite_ensemble(long_exprs, mode='max')
assert r2 == '', f'F-055 validation not enforced: len={len(r2)}'
print('F-055 fusion max: PASS')

# F-052: fail-closed
from brain_alpha_ops.research.prod_correlation import ProdCorrelationService
svc = ProdCorrelationService(api=None)
res = svc.check(expression='group_neutralize(ts_mean(winsorize(market_cap, 0.01), 60), industry)')
assert res.passed is False, 'F-052 not fail-closed'
print('F-052 fail-closed: PASS')
"
```

预期:`F-055 fusion max: PASS` + `F-052 fail-closed: PASS`

> F-051(release_score_gate `else {}`)与 F-056(_slot_submission `continue`)为单行语义修复,已通过 Phase 1 代码审阅确认;若导入链不触发 numpy,可追加内联检查,否则以 py_compile + 代码审阅为准。

#### 步骤 2.5 — 静默异常审计

```bash
python scripts/check_python_silent_broad_exceptions.py
```

预期:退出码 0(无静默宽异常)。确认 C2 修改未引入 `except Exception: pass` 等反模式。

#### 步骤 2.6 — 架构合规检查

```bash
python scripts/check_architecture.py
```

预期:退出码 0(shared/ 不得 import research/web;brain_api/ 不得 import research/web;research/ 不得 import web/agents)。确认 C2/C4 修改未违反分层规则。

#### 步骤 2.7 — 最终发布门禁

```bash
python scripts/final_release_gate.py
```

预期:退出码 0。Fail-closed 发布就绪门禁,综合检查 red lines / thresholds / official context lineage / scoring simulation / frontend sync / checkpoint history。

#### 步骤 2.8 — 红线验证器(阻断模式)

```bash
python -m brain_alpha_ops.compliance.redline_verifier --block
```

预期:退出码 0(全部 6 条红线 RL-1 ~ RL-6 通过)。若退出码 2 表示阻断违规,需诊断;退出码 1 表示有违规但非阻断。

---

## 假设与决策

1. **numpy 缺失是预先存在的环境问题**,不在本计划修复范围。验证策略采用"直接指定测试文件 + 内联导入检查",绕过全量 collection。
2. **文档计数修正(17→12)纳入范围**:B 阶段文档的收尾准确性,属同一工作流的自然收尾。
3. **无新代码变更**:除 1 行文档计数修正外,本计划纯验证性质。若验证发现回归,再单独评估修复(不在本计划预设范围)。
4. **F-051/F-056 无独立测试文件**:以 Phase 1 代码审阅 + py_compile 为准;若步骤 2.3/2.4 的导入链可达,追加内联检查。
5. **质量门禁脚本以退出码为准**:0 = 通过,非 0 = 需诊断。脚本输出记录到验证报告。

---

## 验证步骤(执行清单)

执行者按顺序执行,每步完成即记录 PASS/FAIL:

| # | 步骤 | 命令 | 预期退出码 |
|---|------|------|-----------|
| 1 | 修正文档计数 | Edit `/workspace/docs/CODE_WIKI.md` L1181: `17 项` → `12 项` | N/A(编辑) |
| 2 | py_compile 7 文件 | `python -m py_compile <7 files>` | 0 |
| 3 | pytest 2-3 文件 | `python -m pytest tests/test_prod_correlation.py tests/test_record_sqlite_index.py -v` | 0(30 passed) |
| 4 | C2 导入检查 | 内联 python -c 脚本(步骤 2.3) | 0 |
| 5 | C4 功能检查 | 内联 python -c 脚本(步骤 2.4) | 0 |
| 6 | 静默异常审计 | `python scripts/check_python_silent_broad_exceptions.py` | 0 |
| 7 | 架构合规 | `python scripts/check_architecture.py` | 0 |
| 8 | 发布门禁 | `python scripts/final_release_gate.py` | 0 |
| 9 | 红线阻断 | `python -m brain_alpha_ops.compliance.redline_verifier --block` | 0 |

**完成标准**:步骤 1-9 全部 PASS(或步骤 3 中 test_fusion_candidates.py 因 numpy 豁免并记录)。任一步骤 FAIL 即停止诊断,不继续后续步骤。

---

## 完成后产出

1. 修正后的 `/workspace/docs/CODE_WIKI.md`(第 13.1 节计数准确)
2. 最终验证报告(9 步 PASS/FAIL 汇总 + 关键输出摘要)
3. 向用户返回最终完成响应(不调用 NotifyUser)
