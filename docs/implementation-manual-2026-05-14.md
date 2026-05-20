# BRAIN Alpha Ops — 完整实施手册

> 基于 2026-05-14 对话回顾整理。覆盖所有已识别问题、根因分析、修复方案和实施顺序。

---

## 一、问题总览（按严重程度排序）

| # | 问题 | 严重度 | 根因 |
|---|------|--------|------|
| P0 | 生成器只用 8 个硬编码字段，不用官方 API 返回的字段列表 | 🔴 致命 | `CandidateGenerator` 初始化不接收字段参数 |
| P0 | Turnover 阈值错误：代码 70%，官网要求 <30% | 🔴 致命 | `max_turnover: 0.70` 配置错误 |
| P1 | Dataset Id 缺失，`list_fields()` 不支持 dataset 参数 | 🟠 严重 | `official.py` 第 92 行没有 dataset 查询参数 |
| P1 | 官方回测结果没有被"学习"，失败后盲目随机变异 | 🟠 严重 | `_create_secondary_fusion_candidate()` 不看 metrics 做定向改进 |
| P1 | Margin 指标完全缺失 | 🟠 严重 | `QualityThresholds` 没有 `min_margin_bps` |
| P2 | 生成器只用 17 个硬编码算子 | 🟡 中等 | `DEFAULT_OPERATORS` 不完整且生成器不用 API 返回值 |
| P2 | Neutralization 默认值为 INDUSTRY，应为 SUBINDUSTRY | 🟡 中等 | `BrainSettings.neutralization` 默认值 |
| P2 | 不支持批处理（Max Run）| 🟡 中等 | `submit_simulation()` 一次只提交一个表达式 |
| P3 | 本地预筛分数与官方 Sharpe 相关性弱 | 🟢 轻微 | `local_quality()` 是结构规则，不是预测模型 |
| P3 | IS/OOS 检查缺失 | 🟢 轻微 | `empirical_score()` 没有单独检查样本外 Sharpe |

---

## 二、根因分析

### 根因 1：生成器与官方上下文完全脱节

**代码路径**：`pipeline.py` 第 104 行

```python
# 当前代码
self.generator = CandidateGenerator()  # ← 无任何参数

# _load_official_context() 返回值存为 self.context_summary
# 但完全没有传给 self.generator
fields, operators = self._load_official_context()  # ← 返回值被忽略（对生成器而言）
```

**后果**：
- API 拉取了数百个官方字段 → cache 有 → 生成器看不到
- 生成器永远只用 `KNOWN_FIELDS = {close, open, vwap, volume, adv20, returns, market_cap, sector}`（8个）
- 无法利用 analyst4、fundamentals 等其他数据集的字段

---

### 根因 2：配置阈值与官网标准脱节

**代码路径**：`config.py` 第 65-81 行（`QualityThresholds`）

| 指标 | 代码值 | 官网标准（顾问价值） | 差距 |
|------|--------|----------------------|------|
| `max_turnover` | 0.70 | < 0.30 | 🔴 严重偏高 |
| `min_sharpe` | 1.25 | ≥ 2.0（D0 目标）| 🟠 偏低 |
| `min_fitness` | 1.0 | 越高越好（应 ≥ 1.5）| 🟠 偏低 |
| `min_margin_bps` | 不存在 | > 4bps | 🟠 缺失 |

---

### 根因 3：失败后无针对性迭代

**代码路径**：`pipeline.py` 第 1328-1398 行（`_create_secondary_fusion_candidate`）

```python
# 当前做法：完全随机变异，不看官方 metrics
for attempt in range(1, 9):
    seed = self._simulation_retry_count(candidate) * 8 + attempt
    expression = mutate_expression(candidate.expression, seed)  # ← 盲目变异
    # 完全没有检查：为什么失败？Sharpe 低？Correlation 高？Turnover 异常？
```

**后果**：失败后生成的变异 Alpha 也是盲目的，浪费官方回测槽位。

---

## 三、实施计划（分三阶段）

---

### 阶段一：修复致命配置 + 接入官方字段（P0）

#### T1.1 修复 Turnover 阈值

**文件**：`brain_alpha_ops/config.py`（第 72 行）

```python
# 修改前
max_turnover: float = 0.70

# 修改后
max_turnover: float = 0.30  # 官网顾问标准：Turnover < 30%
min_turnover: float = 0.05  # 保持不变
```

#### T1.2 `list_fields()` 支持 dataset 参数

**文件**：`brain_alpha_ops/brain_api/official.py`（第 92-101 行）

```python
# 修改前
def list_fields(self, query: str = "all", region: str = "", progress_callback=None) -> list[dict]:
    params = {
        "instrumentType": ...,
        "region": ...,
        "delay": ...,
        "universe": ...,
        "limit": 50,
        "offset": 0,
    }

# 修改后
def list_fields(self, query: str = "all", region: str = "", dataset: str = "", progress_callback=None) -> list[dict]:
    params = {
        "instrumentType": ...,
        "region": ...,
        "delay": ...,
        "universe": ...,
        "limit": 50,
        "offset": 0,
    }
    if dataset:
        params["dataset"] = dataset  # ← 新增：支持按数据集过滤字段
```

#### T1.3 `BrainSettings` 增加 dataset 字段

**文件**：`brain_alpha_ops/config.py`（第 16-31 行）

```python
@dataclass
class BrainSettings:
    # ... 原有字段 ...
    dataset: str = ""  # ← 新增：当前使用的数据集，空字符串=默认数据集

    def to_platform_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # ... 原有逻辑 ...
        # dataset 不是 simulation settings 的参数，
        # 它是 list_fields() 的查询参数，存着用于上下文获取
        return {"type": alpha_type, "settings": settings}
```

#### T1.4 `CandidateGenerator` 接入官方字段/算子列表

**文件**：`brain_alpha_ops/research/generator.py`

```python
class CandidateGenerator:
    def __init__(self, fields: list[dict] | None = None, operators: list[dict] | None = None):
        self._cursor = 0
        # 从官方 API 结果中提取字段名称列表
        self.field_names = [f["name"] for f in (fields or DEFAULT_FIELDS)]
        self.operator_names = [o["name"] for o in (operators or DEFAULT_OPERATORS)]
        # 按类别分组，便于针对性生成
        self.fields_by_category = {}
        for f in (fields or DEFAULT_FIELDS):
            cat = f.get("category", "other")
            self.fields_by_category.setdefault(cat, []).append(f["name"])

    def generate(self, count: int) -> list[Candidate]:
        candidates = []
        attempts = 0
        while len(candidates) < count and attempts < count * 8:
            attempts += 1
            index = self._cursor
            self._cursor += 1
            theme = THEME_LIBRARY[index % len(THEME_LIBRARY)]

            # 修改：使用官方字段列表，而不是硬编码的 KNOWN_FIELDS
            base = theme["expressions"][(index // len(THEME_LIBRARY)) % len(theme["expressions"])]
            expression = self._mutate_with_official_fields(base, index)

            if any(item.expression == expression for item in candidates):
                continue
            candidates.append(Candidate(
                alpha_id=new_id("alpha"),
                expression=expression,
                family=theme["family"],
                hypothesis=theme["hypothesis"],
                data_fields=self._extract_fields(expression),
                operators=self._extract_operators(expression),
            ))
        return candidates

    def _mutate_with_official_fields(self, expression: str, index: int) -> str:
        """使用官方字段列表进行变异，而不是硬编码字段。"""
        # 先按原有逻辑变异窗口
        mutated = mutate_expression(expression, index)
        # 随机将部分硬编码字段替换为官方字段列表中的字段
        for known_field in ["close", "volume", "adv20", "vwap"]:
            if known_field in mutated and (index + hash(known_field)) % 3 == 0:
                replacement = self.field_names[(index + hash(known_field)) % len(self.field_names)]
                mutated = mutated.replace(known_field, replacement, 1)
        return mutated

    def _extract_fields(self, expression: str) -> list[str]:
        # 使用官方字段列表进行提取，而不是 KNOWN_FIELDS
        return sorted(f for f in self.field_names if re.search(rf"\b{re.escape(f)}\b", expression))
```

#### T1.5 Pipeline 正确传递字段/算子给生成器

**文件**：`brain_alpha_ops/research/pipeline.py`（第 104 行）

```python
# 修改前
self.generator = CandidateGenerator()

# 修改后
fields, operators = self._load_official_context()
self.generator = CandidateGenerator(fields=fields, operators=operators)
```

---

### 阶段二：补齐顾问标准指标 + 诊断迭代引擎（P1）

#### T2.1 `QualityThresholds` 增加 Margin 和修正阈值

**文件**：`brain_alpha_ops/config.py`（第 64-81 行）

```python
@dataclass
class QualityThresholds:
    min_total_score: float = 85.0
    min_sharpe: float = 2.0           # ← 修正：1.25 → 2.0（追求 D0）
    min_fitness: float = 1.5           # ← 修正：1.0 → 1.5
    min_turnover: float = 0.05
    max_turnover: float = 0.30        # ← 修正：0.70 → 0.30
    min_returns: float = 0.0
    max_drawdown: float = 0.25
    min_sub_universe_sharpe_ratio: float = 0.50
    max_correlation: float = 0.65
    max_concentration: float = 0.30
    min_margin_bps: float = 4.0       # ← 新增：官网顾问标准
    require_official_pass: bool = True
    require_official_metrics: bool = True
    require_data_compliance: bool = True
    require_economic_logic: bool = True
```

#### T2.2 `empirical_score()` 增加 Margin 检查

**文件**：`brain_alpha_ops/research/scoring.py`（第 92-119 行）

```python
def empirical_score(metrics: dict, thresholds: QualityThresholds) -> dict:
    if not metrics:
        return {"score": 0.0, "items": [], "status": "missing_official_metrics"}

    sharpe = _num(metrics.get("sharpe"))
    fitness = _num(metrics.get("fitness"))
    turnover = _ratio(metrics.get("turnover"))
    returns = _num(metrics.get("returns"))
    drawdown = abs(_ratio(metrics.get("drawdown")))
    sub_u = _num(metrics.get("sub_universe_sharpe"))
    sub_ratio = sub_u / max(abs(sharpe), 0.01) if sharpe else 0.0
    correlation = abs(_ratio(metrics.get("correlation")))
    concentration = _ratio(metrics.get("weight_concentration"))
    margin = _num(metrics.get("margin"))  # ← 新增：提取 Margin

    items = [
        item("sharpe", sharpe, ">=", thresholds.min_sharpe, sharpe >= thresholds.min_sharpe, 20),
        item("fitness", fitness, ">=", thresholds.min_fitness, fitness >= thresholds.min_fitness, 15),
        item("turnover_min", turnover, ">=", thresholds.min_turnover, turnover >= thresholds.min_turnover, 8),
        item("turnover_max", turnover, "<=", thresholds.max_turnover, turnover <= thresholds.max_turnover, 8),
        item("returns", returns, ">=", thresholds.min_returns, returns >= thresholds.min_returns, 10),
        item("drawdown", drawdown, "<=", thresholds.max_drawdown, drawdown <= thresholds.max_drawdown, 10),
        item("sub_universe_sharpe_ratio", round(sub_ratio, 3), ">=", thresholds.min_sub_universe_sharpe_ratio, sub_ratio >= thresholds.min_sub_universe_sharpe_ratio, 10),
        item("correlation", correlation, "<=", thresholds.max_correlation, correlation <= thresholds.max_correlation, 14),
        item("concentration", concentration, "<=", thresholds.max_concentration, concentration <= thresholds.max_concentration, 5),
        # ← 新增：Margin 检查
        item("margin", margin, ">=", thresholds.min_margin_bps, margin >= thresholds.min_margin_bps, 10),
    ]
    score = round(sum(row["points"] for row in items if row["passed"]), 2)
    return {"score": score, "items": items, "status": "ready" if score >= 70 else "needs_iteration"}
```

#### T2.3 新增诊断引擎

**新文件**：`brain_alpha_ops/research/diagnostics.py`

```python
"""Alpha 质量诊断引擎——分析失败原因，指导针对性迭代。"""


from brain_alpha_ops.config import QualityThresholds
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.scoring import _num, _ratio


def diagnose(candidate: Candidate, thresholds: QualityThresholds) -> dict:
    """分析 Alpha 的官方回测结果，输出失败原因和改进方向。"""
    metrics = candidate.official_metrics or {}
    diagnosis = {
        "alpha_id": candidate.alpha_id,
        "lifecycle_status": candidate.lifecycle_status,
        "primary_failure": None,
        "failed_dimensions": [],
        "suggested_mutations": [],
    }

    sharpe = _num(metrics.get("sharpe"))
    fitness = _num(metrics.get("fitness"))
    turnover = _ratio(metrics.get("turnover"))
    correlation = abs(_ratio(metrics.get("correlation")))
    margin = _num(metrics.get("margin"))

    # Sharpe 不达标
    if sharpe < thresholds.min_sharpe:
        diagnosis["failed_dimensions"].append("sharpe")
        diagnosis["suggested_mutations"].append({
            "dimension": "sharpe",
            "suggestions": ["increase_window", "add_volume_filter", "try_inverse"],
        })

    # Turnover 过高（交易成本太高）
    if turnover > thresholds.max_turnover:
        diagnosis["failed_dimensions"].append("turnover_high")
        diagnosis["suggested_mutations"].append({
            "dimension": "turnover",
            "suggestions": ["decrease_window", "add_truncation", "use_rank_not_raw"],
        })

    # Turnover 过低（信号不更新）
    if turnover < thresholds.min_turnover:
        diagnosis["failed_dimensions"].append("turnover_low")
        diagnosis["suggested_mutations"].append({
            "dimension": "turnover",
            "suggestions": ["decrease_window", "reduce_smoothing"],
        })

    # 相关性过高
    if correlation > thresholds.max_correlation:
        diagnosis["failed_dimensions"].append("correlation")
        diagnosis["suggested_mutations"].append({
            "dimension": "correlation",
            "suggestions": ["use_different_fields", "change_operator_chain", "add_group_neutralization"],
        })

    # Margin 过低
    if margin < thresholds.min_margin_bps:
        diagnosis["failed_dimensions"].append("margin")
        diagnosis["suggested_mutations"].append({
            "dimension": "margin",
            "suggestions": ["increase_signal_strength", "reduce_complexity"],
        })

    if diagnosis["failed_dimensions"]:
        diagnosis["primary_failure"] = diagnosis["failed_dimensions"][0]

    return diagnosis
```

#### T2.4 修改 `_create_secondary_fusion_candidate()` 使用诊断结果

**文件**：`brain_alpha_ops/research/pipeline.py`（第 1328-1398 行）

```python
# 在 _create_secondary_fusion_candidate 开头增加诊断
def _create_secondary_fusion_candidate(
    self,
    candidate: Candidate,
    pool_by_expression: dict[str, Candidate],
    blocked_expressions: set[str],
    reason: str,
) -> Candidate | None:
    if not self.config.budget.enable_secondary_fusion:
        return None

    # ← 新增：先诊断失败原因
    from brain_alpha_ops.research.diagnostics import diagnose
    diagnosis = diagnose(candidate, self.config.thresholds)

    # ← 新增：基于诊断结果做针对性变异，而不是盲目随机
    parent_key = _expr_key(candidate)
    failed_reasons = candidate.gate.get("failed_reasons", [])
    note = "; ".join(str(item) for item in failed_reasons if item) or reason

    for attempt in range(1, 9):
        seed = self._simulation_retry_count(candidate) * 8 + attempt

        # ← 修改：如果有诊断建议，按诊断方向变异
        if diagnosis["suggested_mutations"]:
            expression = self._targeted_mutate(candidate.expression, diagnosis, seed)
        else:
            expression = mutate_expression(candidate.expression, seed)

        # ... 其余逻辑保持不变 ...
```

---

### 阶段三：支持批处理 + 经验学习（P2/P3）

#### T3.1 `build_simulation_payload()` 支持多表达式（Max Run）

**文件**：`brain_alpha_ops/brain_api/official.py`（第 455-462 行）

```python
def build_simulation_payload(expression: str | list[str], settings: dict | BrainSettings) -> dict:
    if isinstance(settings, BrainSettings):
        settings_obj = settings
    else:
        settings_obj = BrainSettings(**{**BrainSettings().__dict__, **(settings or {})})
    platform = settings_obj.to_platform_dict()
    # ← 修改：支持单个表达式或表达式列表
    if isinstance(expression, list):
        platform["regular"] = expression  # 列表：批处理
    else:
        platform["regular"] = expression  # 单个：原有行为
    return platform
```

#### T3.2 `submit_simulation()` 支持批处理

```python
def submit_simulation(self, expression: str | list[str], settings: dict) -> str | list[str]:
    body = build_simulation_payload(expression, settings)
    data, headers = self._request("POST", self.config.simulations_path, body=body)
    location = headers.get("Location") or headers.get("location")
    sim_id = location or _first_value(data, ["id", "simulation_id", "location"], "")
    if not sim_id:
        raise BrainAPIError(f"simulation submission did not return a location/id: {_scrub(data)}")
    return str(sim_id)
    # ← 注意：如果是批处理，API 可能返回一个 simulation job id，
    # 然后通过 poll_simulation 拿到所有表达式的结果
```

#### T3.3 增加 `ExperienceDB`（从官方结果中学习）

**新文件**：`brain_alpha_ops/research/experience.py`

```python
"""从官方回测结果中提炼经验，指导生成。"""


import json
import os
from collections import Counter


def record_alpha_result(candidate: Candidate, storage_dir: str = "data"):
    """记录 Alpha 的官方结果，用于提炼经验。"""
    from brain_alpha_ops.research.scoring import _num, _ratio

    metrics = candidate.official_metrics or {}
    features = {
        "alpha_id": candidate.alpha_id,
        "expression": candidate.expression,
        "field_set": list(candidate.data_fields or []),
        "operator_set": list(candidate.operators or []),
        "window_values": [int(v) for v in __import__("re").findall(r"\b\d+\b", candidate.expression)],
        "sharpe": _num(metrics.get("sharpe")),
        "fitness": _num(metrics.get("fitness")),
        "turnover": _ratio(metrics.get("turnover")),
        "correlation": abs(_ratio(metrics.get("correlation"))),
        "margin": _num(metrics.get("margin")),
        "passed": metrics.get("pass_fail") == "PASS",
    }

    path = os.path.join(storage_dir, "alpha_features.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(features, ensure_ascii=False) + "\n")


def get_winning_patterns(storage_dir: str = "data", min_sharpe: float = 1.0) -> dict:
    """提炼高分 Alpha 的共同特征。"""
    path = os.path.join(storage_dir, "alpha_features.jsonl")
    if not os.path.exists(path):
        return {"field_combinations": [], "operator_chains": [], "window_preferences": []}

    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
                if rec.get("passed") and rec.get("sharpe", 0) >= min_sharpe:
                    records.append(rec)
            except json.JSONDecodeError:
                continue

    if not records:
        return {"field_combinations": [], "operator_chains": [], "window_preferences": []}

    # 高频字段组合
    field_combos = Counter(
        tuple(sorted(r["field_set"])) for r in records if len(r["field_set"]) >= 2
    ).most_common(5)

    # 高频算子
    operator_counts = Counter(op for r in records for op in r["operator_set"])
    top_operators = [op for op, _ in operator_counts.most_common(5)]

    # 高分窗口偏好
    window_counter = Counter(w for r in records for w in r.get("window_values", []) if w > 0)
    preferred_windows = [w for w, _ in window_counter.most_common(3)]

    return {
        "field_combinations": [{"fields": list(f), "count": c} for f, c in field_combos],
        "top_operators": top_operators,
        "preferred_windows": preferred_windows,
        "sample_size": len(records),
    }
```

#### T3.4 Pipeline 在拿到官方结果后记录经验

**文件**：`brain_alpha_ops/research/pipeline.py`（第 1258-1260 行）

```python
# 在 _finalize_backtest_candidate 中，拿到 official_metrics 后：
if candidate.official_metrics:
    build_scorecard(candidate, self.config.thresholds)
    evaluate_quality_gate(candidate, self.config.thresholds)
    # ← 新增：记录到经验数据库
    from brain_alpha_ops.research.experience import record_alpha_result
    record_alpha_result(candidate, self.config.storage_dir)
```

---

## 四、验证步骤

### 验证阶段一（T1.1-T1.5）

```powershell
# 1. 确认 Turnover 阈值已修正
Select-String -Path "brain_alpha_ops\config.py" -Pattern "max_turnover"

# 2. 确认 list_fields() 支持 dataset 参数
Select-String -Path "brain_alpha_ops\brain_api\official.py" -Pattern "dataset"

# 3. 确认生成器接收字段参数
Select-String -Path "brain_alpha_ops\research\pipeline.py" -Pattern "CandidateGenerator"

# 4. 运行测试，确认字段列表被正确传入
python -m brain_alpha_ops.research.generator
```

### 验证阶段二（T2.1-T2.4）

```powershell
# 1. 确认 Margin 指标已加入
Select-String -Path "brain_alpha_ops\config.py" -Pattern "min_margin_bps"

# 2. 确认 emprical_score 包含 Margin 检查
Select-String -Path "brain_alpha_ops\research\scoring.py" -Pattern "margin"

# 3. 运行模拟，确认失败后生成诊断报告
python -m brain_alpha_ops.research.diagnostics
```

### 验证阶段三（T3.1-T3.4）

```powershell
# 1. 确认批处理 payload 正确构建
Select-String -Path "brain_alpha_ops\brain_api\official.py" -Pattern "build_simulation_payload"

# 2. 确认经验数据库能提炼高分模式
python -c "from brain_alpha_ops.research.experience import get_winning_patterns; print(get_winning_patterns())"
```

---

## 五、配置修改速查表

### `config.py` — `QualityThresholds`

| 参数 | 原值 | 新值 | 原因 |
|--------|------|------|------|
| `min_sharpe` | 1.25 | **2.0** | 追求 D0，不是 D1 |
| `min_fitness` | 1.0 | **1.5** | 1.0 只是及格，不是好 |
| `max_turnover` | 0.70 | **0.30** | 官网顾问标准 |
| `min_margin_bps` | 不存在 | **4.0** | 官网顾问标准，新增 |

### `config.py` — `BrainSettings`

| 参数 | 原值 | 新值 | 原因 |
|--------|------|------|------|
| `neutralization` | `INDUSTRY` | **`SUBINDUSTRY`** | 更细粒度，降低相关性 |
| `dataset` | 不存在 | **`""`** | 新增，支持多数据集 |

### `config/run_config.json`

```json
{
  "ops": {
    "thresholds": {
      "min_sharpe": 2.0,
      "min_fitness": 1.5,
      "max_turnover": 0.30,
      "min_margin_bps": 4.0
    },
    "settings": {
      "neutralization": "SUBINDUSTRY"
    }
  }
}
```

---

## 六、实施优先级总结

```
第一批（P0 - 立即实施）：
  ✅ T1.2  list_fields() 支持 dataset 参数
  ✅ T1.1  修正 max_turnover = 0.30
  ✅ T1.4  生成器接入官方字段列表

第二批（P1 - 第一阶段完成后）：
  ✅ T2.1  修正 min_sharpe = 2.0, min_fitness = 1.5
  ✅ T2.2  增加 Margin 检查
  ✅ T2.3  新增诊断引擎
  ✅ T2.4  修改 secondary_fusion 使用诊断结果

第三批（P2 - 第二批完成后）：
  ✅ T3.1  支持批处理（Max Run）
  ✅ T3.3  新增 ExperienceDB
  ✅ T3.4  Pipeline 记录官方结果到经验库
```

---

*手册版本：v1.0 | 日期：2026-05-14 | 基于对话回顾整理*
