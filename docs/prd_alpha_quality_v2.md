# Brain Alpha OPS — Alpha 生产质量提升 PRD

> **文档版本**: v1.0  
> **状态**: DRAFT  
> **Language**: 中文  
> **Programming Language**: Python（现有技术栈）  
> **Project Name**: brain_alpha_ops  

---

## 1. 项目信息

| 属性 | 值 |
|------|----|
| 原始需求 | 系统性地修复 Brain Alpha OPS pipeline 中与 BRAIN 官方标准不一致的实现，提升 Alpha 生产质量与提交通过率 |
| 涉及模块 | `research/pipeline.py`, `research/alpha_checks.py`, `research/scoring.py`, `brain_api/context_defaults.py`, `brain_api/official.py`, `data/loader.py`, `research/experience.py`, `research/generator.py`, `config.py` |

---

## 2. 产品定义

### 2.1 Product Goals

1. **BRAIN 合规性**: 所有 Alpha Check 公式、阈值、检查顺序与 BRAIN 官方文档 100% 对齐，消除生产环境中不合规 Alpha 的产生
2. **数据驱动生产**: Pipeline 完全基于官方 JSON 数据（fields/operators/datasets）运行，消除硬编码 fallback 对生成质量的负面影响
3. **全流程质量保障**: AlphaCheckRegistry 完整接入 pipeline，经验学习反馈环闭合，实现「生成 → 检查 → 学习 → 优化生成」的质量闭环

### 2.2 User Stories

| ID | User Story | 价值 |
|----|-----------|------|
| US-1 | As a **量化研究员**, I want pipeline 使用 BRAIN 官方公式进行 Alpha Check，so that 我提交的 Alpha 不会被官方平台因公式不一致而误判为不合规 | 降低误拒率 |
| US-2 | As a **系统运维者**, I want 所有字段/算子/数据集从官方 JSON 文件加载而非硬编码 fallback，so that 系统在 BRAIN 平台更新时不会使用过期或不存在的数据 | 消除生产风险 |
| US-3 | As a **策略优化者**, I want pipeline 在每次官方回测后自动记录结果并提炼高分模式反馈给生成器，so that 后续生成的 Alpha 质量持续提升 | 闭环优化 |
| US-4 | As a **合规审查者**, I want AlphaCheckRegistry 的 22 项检查完整接入 pipeline 并在每次评分时执行，so that 所有 Alpha 在提交前都经过标准化质量审查 | 质量保障 |
| US-5 | As a **高级用户**, I want pipeline 支持 Power Pool、ATOM、Pyramid 等 BRAIN 特殊 Alpha 类型，so that 我可以利用平台全部能力最大化收益 | 能力完整 |

---

## 3. 需求池

### 3.1 P0 — 阻塞性（必须立即修复）

| ID | 需求 | 现状 | 目标 | 影响范围 |
|----|------|------|------|----------|
| **P0-1** | **官方数据 JSON 加载路径修复** | `OfficialDataLoader` 从 `data/official_*.json` 加载。`data/official_fields.json`（4.7MB, 数万字段）存在且可读，`data/official_operators.json`（72 个算子）存在，`data/official_datasets.json`（16 个数据集）存在。但当 JSON 不存在或解析失败时，回退到 `context_defaults.py` 中的 23 个字段 + 30 个算子（远少于官方数据），导致生成器视野严重受限 | ① 确保加载路径正确无误；② fallback 不再静默回退到硬编码列表，而是显式报错并阻断 pipeline；③ 或者在 JSON 不可用时自动从 BRAIN API 拉取并缓存 | `data/loader.py`, `brain_api/context_defaults.py`, `research/pipeline.py:_load_official_context` |
| **P0-2** | **LOW_SUB_UNIVERSE_SHARPE 公式修复** | `alpha_checks.py:291-303` 使用 `threshold = 0.75 * max(sharpe, 0.01)`；`scoring.py:106` 使用 `thresholds.sub_universe_sharpe_min_ratio * max(sharpe, 0.01)`。两者均缺少 BRAIN 官方公式中的 `√(sub_size / alpha_size)` 因子 | 改为 `threshold = 0.75 × √(sub_size / alpha_size) × alpha_sharpe`，当 `sub_size` 或 `alpha_size` 不可用时回退到当前公式并记录 WARNING | `research/alpha_checks.py:_check_sub_universe_sharpe`, `research/scoring.py:empirical_score` |
| **P0-3** | **Dataset ID 选取链路修复** | `DatasetSelector.initialize()` 从 `loader.get_datasets()` 获取数据集列表（当前 16 个数据集正常工作），但 `pipeline.py:_load_official_context` 在 advanced components 初始化失败时静默回退，导致 `_selector` 为 None，`generator.set_dataset()` 永不被调用，生成器始终使用 fallback 字段池 | ① DatasetSelector 初始化失败应触发 ERROR 级别事件且阻断 pipeline；② 确保 generator 始终在生成前设置 active dataset；③ 增加 dataset 为空的保护逻辑 | `research/pipeline.py:_load_official_context`, `research/dataset_selector.py`, `research/generator.py` |

### 3.2 P1 — 高优先级（应尽快修复）

| ID | 需求 | 现状 | 目标 | 影响范围 |
|----|------|------|------|----------|
| **P1-1** | **SELF_CORRELATION 例外规则实现** | BRAIN 官方允许：`新Alpha.Sharpe ≥ 相关Alpha.Sharpe × 1.10` 时，即使 PnL 相关性 ≥ 0.70 仍可提交。代码未实现此例外（`alpha_checks.py:255-264`、`scoring.py:125` 仅检查阈值） | 实现例外逻辑：当 self_correlation ≥ 0.70 时，检查是否存在「Sharpe 优势」例外条件；若满足则标记为 PASS_WITH_EXCEPTION 而非 FAIL | `research/alpha_checks.py:_check_self_correlation`, `research/scoring.py:empirical_score` |
| **P1-2** | **AlphaCheckRegistry 接入 Pipeline** | `alpha_checks.py` 定义了 22 项检查 + `AlphaCheckRegistry.build_default_checks()`，但 `pipeline.py` 完全不导入也不调用该模块。当前 pipeline 仅使用 `scoring.py` 的评分逻辑（不执行完整的 BRAIN 检查序列） | 在 pipeline 的关键节点接入 AlphaCheckRegistry：① `_local_prefilter` 后执行 WARNING/INFO 级别检查；② 官方回测结果返回后执行全部 ERROR 级别检查；③ `evaluate_quality_gate` 前执行最终全量检查 | `research/pipeline.py`（新增检查节点） |
| **P1-3** | **Fitness 公式补全** | BRAIN 官方 Fitness = Sharpe × √(\|Returns\| / max(Turnover, 0.125))。代码仅在 `alpha_checks.py:198-207` 检查 `fitness >= 1.0` 阈值，不计算或验证公式 | ① 在 scoring 模块中实现 BRAIN Fitness 公式的计算函数；② 当 BRAIN API 返回 fitness 值时，用本地计算交叉验证；③ 不一致时记录差异供分析 | `research/scoring.py`（新增），`research/alpha_checks.py:_check_fitness_minimum` |
| **P1-4** | **Delay-0 阈值支持** | BRAIN 官方对 Delay-0 有不同的阈值：LOW_SHARPE ≤ 2.0, LOW_FITNESS ≤ 1.3。当前系统仅支持 Delay-1，所有阈值硬编码为 Delay-1 标准 | ① 根据 alpha 设置中的 delay 参数动态选择阈值；② `QualityThresholds` 增加 min_sharpe_delay0 和 min_fitness_delay0 字段；③ 检查逻辑自动路由 | `config.py:QualityThresholds`, `research/alpha_checks.py`, `research/scoring.py` |
| **P1-5** | **Power Pool / ATOM / Pyramid Alpha 类型支持** | Power Pool（Sharpe ≥ 1.0, 算子 ≤ 8, 字段 ≤ 3, 仅 USA/Delay-1, 自相关 ≤ 0.5）、ATOM（单数据集）、Pyramid（每用户最多 2 个）均未实现 | ① 在 `BrainSettings` 中增加 `type` 字段的 POWER_POOL/ATOM/PYRAMID 枚举；② 在 `AlphaCheckRegistry` 中增加对应类型的专项检查；③ 生成器支持按类型约束生成 | `config.py`, `research/alpha_checks.py`, `research/generator.py` |

### 3.3 P2 — 中优先级（计划内修复）

| ID | 需求 | 现状 | 目标 | 影响范围 |
|----|------|------|------|----------|
| **P2-1** | **表达式验证增强** | `validate_expression()` 仅检查括号平衡和空表达式（`official.py:230-237`）。BRAIN 平台可接受的合法语法远超此范围，如算子签名合法性、字段存在性、参数类型匹配等 | ① 增加本地算子签名校验（参数数量/类型匹配）；② 增加字段名在官方列表中的存在性校验；③ 可选：调用 BRAIN API `/alphas/check` 端点进行远程语法校验 | `brain_api/official.py:validate_expression` |
| **P2-2** | **经验学习反馈环闭合** | `experience.py` 提供 `record_alpha_result()` 和 `get_winning_patterns()`。pipeline 在官方回测完成后调用 `record_alpha_result()` 记录（`pipeline.py:1351-1356`），但 `get_winning_patterns()` 的提炼结果从未反馈给生成器以指导后续生成 | ① 在每个 cycle 或每 N 个 cycle 后调用 `get_winning_patterns()`；② 将提炼的 top_operators/preferred_windows/field_combinations 传递给 `CandidateGenerator`；③ 生成器根据高分模式调整模板权重 | `research/pipeline.py`, `research/generator.py`, `research/experience.py` |
| **P2-3** | **Margin 计算改为 API 直接返回值** | `scoring.py:107-108` 和 `alpha_checks.py:319-337` 使用 `returns / turnover / 100` 推算 margin（代理值）。BRAIN API 在模拟结果中通常直接返回 margin 字段 | ① 优先使用 BRAIN API 返回的 `margin` 字段；② API 未返回时才使用本地推算并标记为 "estimated"；③ `margin_minimum` 检查增加数据来源标注 | `research/scoring.py:empirical_score`, `research/alpha_checks.py:_check_margin_minimum` |
| **P2-4** | **Drawdown 严重性统一** | `alpha_checks.py:124` 注册 `drawdown_limit` 为 ERROR，但 `_check_drawdown_limit()` 内部 `severity="INFO"`，注释说明 "BRAIN does not hard-check drawdown" | 统一为 INFO 或 WARNING 级别，消除注册级别与运行时级别的矛盾 | `research/alpha_checks.py:124`, `_check_drawdown_limit` |
| **P2-5** | **字段/算子实时刷新机制** | 系统在启动时通过 `OfficialDataLoader.instance()` 加载一次，之后使用内存缓存。若 BRAIN 平台新增字段/算子，运行中的 pipeline 不会感知 | ① 增加定时刷新机制（可配置间隔，默认每 24 小时）；② 刷新后通知 generator 更新上下文；③ 刷新失败时保留现有数据并记录 WARNING | `data/loader.py`, `research/pipeline.py` |

---

## 4. 验收标准

### 4.1 P0 验收标准

| ID | 验收标准 |
|----|---------|
| P0-1 | ① 启动 pipeline 时，日志明确显示 "Loaded N fields, M operators from official_*.json"；② N ≥ 1000（而非 23），M ≥ 70（而非 30）；③ JSON 加载失败时 pipeline 退出并报清晰错误，不回退到硬编码列表 |
| P0-2 | ① `sub_universe_sharpe` 检查日志包含 `sqrt(sub_size/alpha_size)` 因子计算过程；② 数学验证：当 sub_size=500, alpha_size=1000, sharpe=1.5 时，threshold = 0.75 × √(500/1000) × 1.5 = 0.795 而非原来的 1.125 |
| P0-3 | ① pipeline 每个 cycle 的 `_active_dataset_id` 非空；② 生成器 `_fields` 集合反映当前 dataset 的真实字段（数量和内容与 `FieldDatasetMapper.fields_for()` 一致）；③ dataset 为空时生成阶段应跳过并记录错误 |

### 4.2 P1 验收标准

| ID | 验收标准 |
|----|---------|
| P1-1 | ① 构造测试用例：SelfCorrelation=0.75（≥0.70），但新 Alpha Sharpe=2.2，相关 Alpha Sharpe=2.0（2.2 ≥ 2.0 × 1.10 = 2.2），检查结果应为 PASS_WITH_EXCEPTION；② 反之，若 Sharpe 不满足条件，检查结果应为 FAIL |
| P1-2 | ① pipeline 运行日志中出现 AlphaCheckRegistry 的执行记录；② 一次完整 cycle 至少包含 ERROR 级别的 8 项检查（sharpe/fitness/turnover_range/self_correlation/prod_correlation/weight_concentration/sub_universe_sharpe/drawdown_limit）；③ 单项失败时 pipeline gate 标记对应 reason |
| P1-3 | ① `calculate_fitness(sharpe, returns, turnover)` 函数可独立调用；② 与 BRAIN API 返回的 fitness 值对比，误差 < 0.01（对于 returns=0.05, turnover=0.3, sharpe=1.5，预期 fitness ≈ 1.5 × √(0.05/0.3) ≈ 0.612）|
| P1-4 | ① Delay-1 使用 min_sharpe=1.25, min_fitness=1.0；② Delay-0 使用 min_sharpe=2.0, min_fitness=1.3；③ threshold 选择基于 settings["delay"] 自动路由 |
| P1-5 | ① 提交 type="POWER_POOL" 时，AlphaCheckRegistry 额外检查：Sharpe≥1.0, operators≤8, unique_fields≤3, region="USA", delay=1, self_corr≤0.5；② 提交 type="ATOM" 时，验证所有字段来自同一数据集 |

### 4.3 P2 验收标准

| ID | 验收标准 |
|----|---------|
| P2-1 | ① `validate_expression("rank(unknown_op(x))")` 返回 FAIL（unknown_op 不在官方算子列表）；② `validate_expression("rank(nonexistent_field)")` 返回 FAIL（字段不存在）|
| P2-2 | ① pipeline 运行 ≥ 5 个 cycle 后，`get_winning_patterns()` 的 `top_operators` 非空；② 生成器生成日志中出现 "Guided by experience: preferring operators [ts_delta, rank, ...]" |
| P2-3 | ① API 返回 margin=5.2 时，检查使用 5.2 而非推算值；② 日志标注数据来源："margin_source": "api" 或 "margin_source": "estimated" |
| P2-4 | ① `drawdown_limit` 的注册级别与运行时级别一致；② 建议统一为 WARNING（因 BRAIN 官方不硬性检查 drawdown）|
| P2-5 | ① 配置文件新增 `context_refresh_interval_hours` 字段；② 运行超过刷新间隔后，日志显示 "Context refreshed: fields N→M, operators X→Y" |

---

## 5. BRAIN 官方对照表

> 所有参数的真实来源标注为 "BRAIN API 文档 / Alpha Check 标准"。以下为参数 → 代码位置的精确映射。

| BRAIN 检查项 | 官方阈值/公式 | 代码位置 | 状态 |
|-------------|-------------|---------|------|
| **LOW_SHARPE** (Delay-1) | Sharpe < 1.25 → FAIL | `config.py:77` min_sharpe=1.25 | ✅ 阈值正确 |
| **LOW_SHARPE** (Delay-0) | Sharpe < 2.0 → FAIL | — | ❌ 未实现 |
| **LOW_FITNESS** (Delay-1) | Fitness < 1.0 → FAIL | `config.py:78` min_fitness=1.0 | ⚠️ 阈值正确，但 Fitness 公式未本地验证 |
| **LOW_FITNESS** (Delay-0) | Fitness < 1.3 → FAIL | — | ❌ 未实现 |
| **Fitness 公式** | Sharpe × √(\|Returns\| / max(Turnover, 0.125)) | — | ❌ 本地未实现 |
| **LOW_TURNOVER** | Turnover < 1% (0.01) → FAIL | `config.py:79` min_turnover=0.01 | ✅ 阈值正确 |
| **HIGH_TURNOVER** | Turnover > 70% (0.70) → FAIL | `config.py:80` max_turnover=0.70 | ✅ 阈值正确 |
| **CONCENTRATED_WEIGHT** | 单股票权重 > 10% (0.10) → FAIL | `config.py:86` max_weight_concentration=0.10 | ✅ 阈值正确 |
| **SELF_CORRELATION** | PnL 相关性 ≥ 0.70 → FAIL | `config.py:84` max_self_correlation=0.70 | ⚠️ 阈值正确，但缺少例外规则 |
| **SELF_CORRELATION 例外** | 新Alpha.Sharpe ≥ 相关Alpha.Sharpe × 1.10 → 允许提交 | — | ❌ 未实现 |
| **LOW_SUB_UNIVERSE_SHARPE** | sub_sharpe ≥ 0.75 × √(sub_size/alpha_size) × alpha_sharpe | `alpha_checks.py:291-303`, `scoring.py:106` | ❌ 缺少 √(sub_size/alpha_size) 因子 |
| **Margin** (顾问标准) | ≥ 4.0 bps | `config.py:83` min_margin_bps=4.0 | ⚠️ 阈值正确，但值为本地推算而非 API 返回 |
| **Drawdown** | 非硬性检查（定性参考） | `config.py:82` max_drawdown=0.25 | ⚠️ 严重性标记不一致 |
| **检查顺序** | CW → SC → LF → Delay-1 Sharpe → LSS | `alpha_checks.py` 注册顺序 | ⚠️ 已定义但 pipeline 未调用 |
| **Power Pool** | Sharpe ≥ 1.0, ops ≤ 8, fields ≤ 3, USA/Delay-1, SC ≤ 0.5 | — | ❌ 未实现 |
| **ATOM** | 仅使用单个数据集 | — | ❌ 未实现 |
| **Pyramid** | 每用户最多 2 个 | — | ❌ 未实现 |

### 4.1 代码位置速查

```
brain_alpha_ops/
├── config.py                              # QualityThresholds（阈值集中定义）
├── research/
│   ├── alpha_checks.py                    # AlphaCheckRegistry + 22 项检查实现
│   │   ├── _check_sharpe_positive         # LOW_SHARPE
│   │   ├── _check_fitness_minimum         # LOW_FITNESS
│   │   ├── _check_turnover_range          # LOW/HIGH_TURNOVER
│   │   ├── _check_self_correlation        # SELF_CORRELATION（缺例外）
│   │   ├── _check_weight_concentration    # CONCENTRATED_WEIGHT
│   │   ├── _check_sub_universe_sharpe     # LOW_SUB_UNIVERSE_SHARPE（公式不完整）
│   │   └── _check_margin_minimum          # Margin（代理值推算）
│   ├── scoring.py                         # empirical_score / build_scorecard
│   ├── pipeline.py                        # Pipeline 主循环（未调用 AlphaCheckRegistry）
│   ├── generator.py                       # CandidateGenerator
│   └── experience.py                      # record_alpha_result / get_winning_patterns
├── brain_api/
│   ├── official.py                        # validate_expression（仅检查括号）
│   └── context_defaults.py                # 硬编码 fallback（23 fields, 30 operators）
└── data/
    └── loader.py                          # OfficialDataLoader（JSON → 内存）
```

---

## 6. 实施建议

### 6.1 推荐实施顺序

1. **Week 1**: P0-1（JSON 加载路径）+ P0-2（LSS 公式）+ P0-3（Dataset 链路）→ 打通数据流
2. **Week 2**: P1-2（AlphaCheckRegistry 接入）+ P1-4（Delay-0）→ 质量检查上线
3. **Week 3**: P1-1（SELF_CORRELATION 例外）+ P1-3（Fitness 公式）→ 补全检查逻辑
4. **Week 4**: P1-5（特殊 Alpha 类型）+ P2 各项 → 功能完善

### 6.2 风险与依赖

| 风险 | 缓解措施 |
|------|---------|
| BRAIN API 实际返回字段与 documentation 不一致 | 优先以 API 实际返回值为准，文档仅作参考 |
| `official_fields.json` (4.7MB) 加载性能 | 已有单例缓存机制，增加按需加载/分页支持 |
| AlphaCheckRegistry 接入可能误杀现有高分 Alpha | 先用 WARNING 模式运行 1 周，确认无误后在切换为 ERROR 阻断 |
| Self-correlation 例外需要访问其他 alpha 数据 | 需确保 cloud sync 已同步足够的 alpha 列表 |

### 6.3 Open Questions

1. **sub_size 和 alpha_size 的数据来源**: BRAIN API 的模拟结果中是否直接返回这两个值？需要查看实际 API 响应字段名确认
2. **Power Pool 的提交 API 路径**: 是否与 REGULAR alpha 使用相同的 `/alphas/{id}/submit` 端点？需验证 BRAIN API 文档
3. **Pyramid alpha 的每用户上限**: 是软限制（警告）还是硬限制（API 拒绝）？需在实际环境测试确认
4. **经验学习反馈的权重**: `get_winning_patterns()` 的结果应如何影响生成器的模板选择权重？需要实验确定最佳平衡点
