# Alpha 评分体系结构化评估文档

> **评估范围**: `brain_alpha_ops/research/scoring.py` + `scoring_params.py` + `alpha_checks.py` + `auto_calibrator.py` + `calibrate_weights.py`  
> **评估日期**: 2026-05-16  
> **评估标准**: 真实模拟能力 / 门禁判断能力 / 维度丰富性 / 结构化程度 / 可解释性 / 可校准性 / 可演进性

---

## 1. 真实模拟能力 (4.5/5)

### 1.1 模拟链路完整性

```
┌─────────────────────────────────────────────────────────────┐
│  OfficialBrainAPI 完整模拟链路                               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  authenticate() ──→ 获取 Token / Session Cookie             │
│        │                                                    │
│  submit_simulation(expression, settings)                    │
│        │  POST /simulations                                 │
│        │  返回 simulation_id (通过 Location header 或 body)  │
│        ▼                                                    │
│  poll_simulation(simulation_id)                             │
│        │  GET /simulations/{id}                             │
│        │  返回 RUNNING / COMPLETED / FAILED                 │
│        ▼                                                    │
│  fetch_result(simulation_id)                                │
│        │  GET /simulations/{id} + GET /alphas/{alpha_id}    │
│        │  合并 simulation + alpha 数据                       │
│        ▼                                                    │
│  check_alpha(alpha_id)                                      │
│        │  GET /alphas/{alpha_id}/check                      │
│        │  返回 PASSED / FAILED + failed_checks              │
│        ▼                                                    │
│  submit_alpha(alpha_id)                                     │
│        │  POST /alphas/{alpha_id}/submit                    │
│        │  返回 SUBMITTED / ERROR                            │
│        ▼                                                    │
│  ┌──────────────────────────────────────┐                   │
│  │ 支持特性:                             │                   │
│  │  • 429 速率限制重试 (3 次 + 退避)      │                   │
│  │  • Bearer/Cookie/Basic 三模式认证      │                   │
│  │  • API 响应缓存 (TTL 86400s)          │                   │
│  │  • 并发模拟数限制 (max 3)             │                   │
│  │  • 过时缓存降级 (429 时使用旧缓存)     │                   │
│  └──────────────────────────────────────┘                   │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 评分的模拟结果获取

- ✅ 官方 API 返回的 metrics 通过 `normalize_metrics()` 规范化
- ✅ 支持双格式字段名 (camelCase/snake_case)
- ✅ `fetch_result()` 合并 simulation 和 alpha 两个 API 端点结果
- ✅ `check_prod_correlation()` 可选调用 BRAIN correlations API

### 1.3 GAP

- ⚠️ `fetch_result()` 返回错误时 (`BrainAPIError`) 静默跳过 alpha_payload，不记录日志
- ⚠️ 网络错误时无 metrics 重置机制，可能复用旧数据

---

## 2. 门禁判断能力 (4.3/5)

### 2.1 门禁层级架构

```
Layer 0: 本地预过滤 (local_quality)
  ├── expression 非空
  ├── 括号平衡
  ├── 至少包含 1 个 BRAIN 数据字段
  ├── 至少包含 1 个 BRAIN 算子
  ├── 长度 ≤ 2000 chars (compiler limit)
  └── 无危险模式 (裸逗号、未闭合函数)

Layer 1: 先验评分门禁 (prior_score ≥ 60/70)
  ├── min_prior_score_for_official_validation = 60
  └── min_prior_score_for_official_simulation = 70

Layer 2: 官方验证 (validate_expression)
  ├── 算子存在性检查 (vs official operators list)
  ├── 字段存在性检查 (vs official fields list)
  └── 表达式长度 / 嵌套深度 / 逗号检查

Layer 3: 官方模拟 (submit_simulation → poll → fetch_result)
  └── BRAIN 服务器端编译和回测

Layer 4: 回测指标门禁 (empirical_score — 14 项)
  ├── [硬] Sharpe ≥ 1.25 (Delay-1) / 2.0 (Delay-0)
  ├── [硬] Fitness ≥ 1.0 (Delay-1) / 1.3 (Delay-0)
  ├── [硬] Turnover ≥ 0.01 (LOW_TURNOVER)
  ├── [硬] Turnover ≤ 0.70 (HIGH_TURNOVER)
  ├── [硬] Self Correlation ≤ 0.70 (含例外规则)
  ├── [硬] Prod Correlation ≤ 0.70
  ├── [硬] Weight Concentration ≤ 0.10
  ├── [硬] Sub Universe Sharpe ≥ 0.75 × √(sub/alpha) × sharpe
  ├── [软] Returns ≥ 0.0
  ├── [软] Drawdown ≤ 0.25
  ├── [软] Turnover Quality ≤ 0.30 (可升级)
  ├── [软] IS/OOS Ratio ≥ 0.5
  └── [软] Margin ≥ 4.0 bps

Layer 5: 提交清单门禁 (submission_checklist — 7 项)
  ├── official_metrics_present
  ├── official_pass
  ├── economic_logic
  ├── data_delay_conservative
  ├── local_quality
  ├── self_correlation_proxy
  └── diversity

Layer 6: 安全门禁 (SubmissionLedger)
  ├── 表达式去重 (完整匹配)
  ├── 微小变体检测 (similarity ≥ 0.90)
  ├── 每日提交上限 (max 3)
  ├── 运行提交上限 (max 2)
  ├── 提交间隔限制 (≥ 120 min)
  ├── Mock ID 检测
  └── pre-submit check 验证
```

### 2.2 门禁配置化

```python
# 所有门禁均可通过 config/run_config.json 配置
# 或通过 Web API 运行时修改 (config_from_payload)
{
  "thresholds": {
    "min_sharpe": 1.25,           # 可配置
    "min_fitness": 1.0,            # 可配置
    "platform_max_turnover": 0.70, # 可配置
    "enforce_target_turnover_as_hard_gate": false  # 可升级
  },
  "submission_policy": {
    "max_auto_submissions_per_day": 3,
    "max_expression_similarity": 0.9
  }
}
```

### 2.3 GAP

- ⚠️ `data_delay_conservative` 审核项恒返回 True，未实际校验 delay 设定
- ⚠️ `margin_bps` 无 BRAIN API 数值时使用本地估计，可能不够准确
- ⚠️ 缺少 PROD_CORRELATION 的独立硬门禁项

---

## 3. 维度丰富性 (4.0/5)

### 3.1 评分维度全景

| 类别 | 维度数 | 覆盖指标 |
|------|:------:|----------|
| **收益类** | 3 | Sharpe, Returns, Margin (bps) |
| **风险类** | 3 | Drawdown, Self Correlation, Prod Correlation |
| **稳定性** | 2 | Sub Universe Sharpe, IS/OOS Ratio |
| **换手率** | 3 | Turnover Min, Turnover Platform Max, Turnover Quality |
| **集中度** | 1 | Weight Concentration |
| **Fitness** | 2 | Fitness, Fitness Crosscheck |
| **先验** | 8 | Economic Logic, Structure, Field/Op Support, Data Compliance, Horizon/Turnover Proxy, Risk Control Proxy, Diversity, Explainability |
| **提交** | 7 | Metrics Present, Official Pass, Economic Logic, Data Delay, Local Quality, Corr Proxy, Diversity |

> **总计**: 31 项可量化评分维度

### 3.2 维度实现质量

| 维度 | 数据来源 | 计算公式 | 可解释性 |
|------|---------|---------|:------:|
| Sharpe | BRAIN API | API 返回 | 高 |
| Fitness | BRAIN API + 本地 crosscheck | Sharpe × √(\|Returns\| / max(Turnover, 0.125)) | 高 |
| Turnover | BRAIN API | API 返回 | 高 |
| Self Correlation | BRAIN API | API 返回 (含例外规则) | 高 |
| Sub Universe Sharpe | BRAIN API | 0.75 × √(sub_size/alpha_size) × sharpe | 高 |
| Weight Concentration | BRAIN API | API 返回 | 高 |
| Drawdown | BRAIN API | API 返回 | 中 |
| Margin | BRAIN API / 本地估计 | API: 直接使用; 本地: returns/turnover/100 | 中 |
| IS/OOS Ratio | 计算 | SubUniverseSharpe / Sharpe | 中 |
| Economic Logic | 关键词检测 | 9 类 ~50 个关键词 | 中 |

---

## 4. 结构化程度 (4.5/5)

### 4.1 统一评分项结构

每个评分项遵循六元组结构：

```python
{
  "name": "sharpe",           # 指标名称
  "actual": 1.75,             # 实际值
  "direction": ">=",          # 比较方向
  "target": 1.25,             # 目标阈值
  "passed": True,             # 是否通过
  "points": 20,               # 分值
  "is_hard_gate": True,       # 是否硬门禁
  "source": "BRAIN_Official", # 来源标注
}
```

### 4.2 Scorecard 结构 (v2.3)

```python
{
  "schema_version": "scorecard-v2.3",
  "total_score": 85.5,
  "decision_band": "submit_candidate | optimize_before_submit | research_only | abandon_or_rebuild | hard_gate_blocked",
  "score_basis": "official_verified | local_prior",
  "local_rank_score": 76.2,
  "layer_weights": {"prior": 0.30, "empirical": 0.45, "checklist": 0.25},
  "prior": {
    "score": 72.5,
    "dimensions": { /* 8 维度 */ },
    "weights": { /* 8 维度权重 */ },
    "source": "经验+校准"
  },
  "empirical": {
    "score": 88.0,
    "items": [ /* 14 项评分项 */ ],
    "status": "ready",
    "hard_gate_failed": False,
    "hard_gate_failures": [],
    "margin_source": "BRAIN_API | estimated",
    "delay": 1,
    "market_regime": "normal"
  },
  "submission_checklist": {
    "score": 90,
    "items": [ /* 7 项检查 */ ]
  },
  "confidence": {
    "confidence_level": "high | medium | low",
    "score_dispersion": 0.15,
    "data_completeness": 0.92
  },
  "calibration": {
    "prior_minus_empirical": -15.5,
    "sample_weight": 1.0,
    "params_used": True
  }
}
```

### 4.3 Gate 结构 (v2.2)

```python
{
  "schema_version": "production-gate-v2.2",
  "submission_ready": True,
  "status": "SUBMISSION_READY | NEEDS_ITERATION",
  "failed_reasons": [],
  "warnings": [],
  "hard_gate_blocked": False,
  "source_notes": {
    "thresholds": "BRAIN 官方 Alpha Check 标准...",
    "official_checks": "官方模拟与 alpha check 是提交前必要证据。",
    "hard_gate_policy": "BRAIN hard gates are blocking..."
  }
}
```

---

## 5. 可解释性 (3.5/5)

### 5.1 已实现的解释能力

| 能力 | 实现方式 | 质量 |
|------|---------|:----:|
| 阈值来源标注 | `source` 字段 ("BRAIN_Official" / "经验") | 高 |
| 硬/软门禁区分 | `is_hard_gate` 标签 | 高 |
| 失败原因输出 | `failed_reasons` / `hard_gate_failures` 数组 | 高 |
| 经济逻辑归因 | `_economic_logic_score()` 关键词检测 → `concepts_detected` | 中 |
| 评分置信度 | `estimate_score_confidence()` dispersion/completeness | 中 |
| 市场状态调整 | `market_regime` + `regime_adjustments` | 中 |
| 决策建议 | `decision_band()` 分类建议 | 高 |

### 5.2 缺失的解释能力

- ❌ **逐维度归因**: 无法回答"这个 Alpha 为什么好/差"
- ❌ **对比解释**: 无法说明"相比上一轮最佳 Alpha，这个改进了哪些维度"
- ❌ **失败诊断**: empirical_score 中仅给出 failed name → 缺少"如何修复"的建议
- ⚠️ **经济逻辑深度**: 仅关键词匹配，未做经济逻辑的连贯性推理

### 5.3 改进建议

```yaml
P0: 添加 attribution 字段到 scorecard:
  对每个维度输出"与历史最佳候选的差值"
  
P1: 失败项映射到修复建议:
  "LOW_SHARPE" → "建议增加 cross-sectional operator / 拓展时间窗口"
  "HIGH_TURNOVER" → "建议增加 decay 参数 / 使用长周期信号"
  "SELF_CORRELATION" → "建议修改 operator 组合 / 更换数据集"

P2: 经济逻辑连贯性检查:
  检测 hypothesis 文本与实际使用的 operators 是否语义一致
```

---

## 6. 可校准性 (3.5/5)

### 6.1 校准基础设施

| 组件 | 功能 | 状态 |
|------|------|:----:|
| `calibrate_weights.py` | 网格搜索最优三层权重 + Pearson 校准 | ✅ 可运行 |
| `ScoringParams` | 8 维度参数化公式 | ✅ 设计完整 |
| `AutoCalibrator` | 自动收集官方数据 → 校准 → 应用 | ⚠️ 未激活 |
| `calibration` 字段 | 在 scorecard 中追踪 prior-vs-empirical 偏差 | ✅ |
| `calibrate_prior_weights()` | Pearson r 归一化 prior 维度权重 | ✅ |
| `calibrate_scorecard_weights()` | 网格搜索 (prior, empirical, checklist) 权重 | ✅ |

### 6.2 校准流程

```
1. 收集数据 (alpha_features.jsonl)
   └── 候选 → 本地评分 → 官方评分 → 记录偏差

2. Prior 权重校准 (calibrate_prior_weights)
   └── 对 8 个 prior 维度计算与 official_sharpe 的 Pearson r
   └── 归一化得到新权重

3. 三层权重校准 (calibrate_scorecard_weights)
   └── 网格搜索 (w_prior, w_empirical, w_checklist)
   └── 最大化 (local_score, official_sharpe) 的 Spearman ρ
```

### 6.3 GAP

- ❌ `auto_calibrator.py` 未在 pipeline 默认运行中激活
- ⚠️ economic_logic 维度不可通过 ScoringParams 校准
- ⚠️ 缺少历史回测校准数据集的自动累积

---

## 7. 可演进性 (4.0/5)

### 7.1 架构可扩展点

| 扩展点 | 实现机制 | 新增成本 |
|--------|---------|:------:|
| 新评分维度 | `AlphaCheckRegistry.register()` | 低 |
| 新指标类型 | `scoring.item()` 六元组 | 低 |
| 新校准方法 | `ScoringParams.get_dimension()` + `_parameterized_dimensions()` | 中 |
| 新门禁类型 | `is_hard_gate=True` 标签 | 低 |
| 新先验维度 | `prior_score._parameterized_dimensions()` 扩展 | 中 |
| 新决策带 | `decision_band()` 多阈值 | 低 |

### 7.2 版本兼容

- ✅ Scorecard schema 版本化 (`scorecard-v2.3`)
- ✅ Gate schema 版本化 (`production-gate-v2.2`)
- ✅ `build_scorecard()` 向后兼容 (支持无 ScoringConfig 的旧调用)

---

## 8. 总结

| 评估维度 | 评分 | 核心优势 | 核心短板 |
|----------|:----:|----------|----------|
| 真实模拟能力 | 4.5 | 完整 API 链路 + 双认证 + 缓存 | 错误静默 |
| 门禁判断能力 | 4.3 | 6 层门禁 + 8 硬门禁 + 配置化 | 一项形同虚设 |
| 维度丰富性 | 4.0 | 31 项可量化维度 | 缺少情绪/宏观类 |
| 结构化程度 | 4.5 | 六元组 + versioned schema | - |
| 可解释性 | 3.5 | 来源标注 + 失败原因 | 无归因/修复建议 |
| 可校准性 | 3.5 | 完整校准基础设施 | 未激活使用 |
| 可演进性 | 4.0 | 注册模式 + 版本化 | - |

**综合**: **4.1/5.0** — 架构优良，补齐可解释性和激活校准能力后可达 4.5+。
