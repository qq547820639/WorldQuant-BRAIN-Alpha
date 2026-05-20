# BRAIN Alpha Ops v3.0 — PRD

> **文档版本**: v1.0  
> **状态**: DRAFT  
> **Language**: 中文  
> **Programming Language**: Python（纯标准库 + 内嵌 HTML/CSS/JS）  
> **Project Name**: brain_alpha_ops  

---

## 1. 项目信息

| 属性 | 值 |
|------|----|
| 原始需求 | 修复 v2.1 致命短板（随机生成、伪科学评分、不完整迭代闭环），使系统能自主完成「有经济逻辑的 alpha 创作 → 本地估分 → 官方回测 → 结构化评价 → 基于反馈的迭代 → 质量收敛」的完整闭环 |
| 当前状态 | `generator.py` 的 `_generate_dynamic()` / `_generate_fallback()` 本质是模板随机拼接；`prior_score()` 8 个维度全部硬编码 if-else；经验反馈只影响模板/窗口偏好但不校准评分权重；`secondary_fusion` 仅包裹 zscore/winsorize |
| 技术栈约束 | 零外部依赖（纯 Python 标准库 + 内嵌 HTML/CSS/JS）；配置文件 `config/run_config.json`；生产/模拟环境分离；凭据走环境变量 |

---

## 2. 产品定义

### 2.1 Product Goals

1. **经济逻辑驱动的 Alpha 生成**：生成器从"随机模板拼接"进化为"经济假设 → 因子构造 → 表达式生成"的推理链路。每个 alpha 必须有可追溯的经济 rationale，而非随机组合产物

2. **可校准的科学评分系统**：`prior_score()` 的 8 维权重和评分函数能通过 `calibration.prior_minus_empirical` 历史数据自动校准。评分不仅是形式检查，而是对回测结果有预测力的先验估计

3. **系统性的迭代搜索**：迭代从"停滞→切换策略"进化为"局部扰动+定向改进"。`secondary_fusion` 实现真正的因子融合（正交化组合、残差 alpha），经验反馈闭环驱动生成器参数调优

4. **可解释的可视化控制台**：Web 界面支持表达式编辑器（语法高亮）、评分维度钻取（雷达图/柱状图）、Sharpe 趋势图（折线图）、因子对比分析（表格），全部零外部依赖实现

5. **闭环质量收敛**：系统能自我评估当前生产质量是否在提升，并在多轮迭代后产出可提交的高质量 alpha（Sharpe ≥ 1.25, Fitness ≥ 1.0, 通过全部 BRAIN Alpha Check）

### 2.2 User Stories

| ID | User Story | 价值 |
|----|-----------|------|
| US-1 | As a **量化研究员**, I want 生成器能基于经济假设（如"分析师上调评级的股票应跑赢"）构造 alpha 表达式，so that 我产出的 alpha 有逻辑可解释性而非随机试错 | 从随机到推理 |
| US-2 | As a **策略开发者**, I want 先验评分系统能通过历史回测结果自动校准各维度权重，so that 本地评分与官方回测结果的相关性持续提升，减少无效的官方 API 调用 | 评分预测力 |
| US-3 | As a **系统运维者**, I want 迭代过程能基于回测反馈定向改进 alpha（而非盲目重试），so that 每一轮迭代都有真实的质量提升 | 效率与收敛 |
| US-4 | As a **因子分析师**, I want Web 控制台能钻取每个 alpha 的评分维度、对比多个候选因子的指标、查看 Sharpe 趋势，so that 我可以快速判断哪些 alpha 值得深入 | 可观测性 |
| US-5 | As a **质量管理者**, I want 系统自动追踪收敛状态并在质量停滞时给出可操作的改进建议，so that 我不需要人工监控生产流程 | 自主运行 |

---

## 3. 技术规范

### 3.1 Requirements Pool

#### P0 — 阻塞性（v3.0 必须实现）

| ID | 需求 | 现状（v2.1 源码依据） | 目标 |
|----|------|----------------------|------|
| **P0-1** | **经济假设驱动的 Alpha 生成引擎** | `generator.py:_generate_dynamic()` 使用 `DynamicThemeEngine.generate()` 随机选 skeleton → 随机填 field/window；`_generate_fallback()` 用 10 个硬编码模板循环拼接。均无经济推理 | 实现 `HypothesisDrivenGenerator`：① 定义因子原型库（momentum/value/quality/growth/volatility/liquidity），每个原型绑定经济 rationale、适用的数据集类别、构造规则；② 生成流程：选择因子原型 → 根据数据集字段映射选择相关字段 → 按构造规则组装表达式 → 附加 hypothesis 文本；③ hypothesis 不再是 "Auto-generated momentum alpha from dataset X" 而是 "捕捉 [字段含义] 在 [窗口] 周期内的 [经济逻辑]" |
| **P0-2** | **可校准的先验评分系统** | `scoring.py:prior_score()` 8 维全部硬编码 if-else（如 `hypothesis>=40 → 85 else 45`），权重 `weights` 字典固定；`calibration.prior_minus_empirical` 被记录但从未用于校准 | 实现 `CalibratableScorer`：① 保持 8 维结构但每维评分函数支持参数化（如 `score = sigmoid((value - threshold) / scale) * 100`）；② 当积累 ≥ 20 个 official_verified 样本后，用 prior_minus_empirical 误差最小化校准各维阈值/缩放参数和权重；③ 校准算法使用纯标准库实现的简单梯度下降或网格搜索；④ 校准结果持久化到 `data/scoring_calibration.json` |
| **P0-3** | **定向迭代与真实融合** | `pipeline.py:_create_secondary_fusion_candidate()` 调用 `mutate_expression(..., mode="structure_change")` 仅包裹 zscore/winsorize；`_maybe_switch_strategy()` 基于 ready_rate 阈值切换 region/universe，非系统性搜索 | 实现 `IterativeOptimizer`：① 定向变异算子：field_swap（同类别字段替换）、window_perturb（窗口 ±20% 扰动）、structure_refine（增加/移除标准化层）、operator_substitute（同功能算子替换，如 ts_rank→ts_zscore）；② 融合算子：orthogonal_blend（对两个 alpha 做正交化组合）、residual_alpha（用 alpha1 的残差作为 alpha2 的输入）；③ 迭代策略：对低 Sharpe alpha 优先 field_swap + window_perturb，对高自相关 alpha 优先 structure_refine，对低 fitness alpha 尝试 operator_substitute |
| **P0-4** | **闭合的经验反馈环** | `experience.py` 的 `get_winning_patterns()` 每 5 个 cycle 调用一次并反馈给 `generator.set_experience_guidance()`，但这仅影响模板/窗口选择偏差，不校准评分也不指导迭代策略 | 实现完整反馈环：① 经验提炼结果同时反馈给三个模块：Generator（字段/算子/窗口偏好）、Scorer（用于校准权重）、IterativeOptimizer（指导变异策略选择）；② 增加反馈效果追踪：记录每次反馈前后的平均 Sharpe 变化，用于评估反馈有效性；③ 当某类反馈连续 3 次无改善时自动降低其权重 |
| **P0-5** | **Web 控制台增强** | `web.py` 当前是基础仪表盘：侧栏统计 + 候选池列表 + 事件日志 + 回测槽状态。无表达式编辑器、无图表、无钻取 | 实现 v3.0 控制台：① **表达式编辑器**：带语法高亮的 textarea（纯 JS 实现，正则着色 BRAIN 算子/字段/数字）；② **评分维度雷达图**：纯 SVG 绘制 8 维雷达图；③ **Sharpe 趋势图**：纯 SVG 折线图展示最近 20 轮的 avg/max Sharpe 变化；④ **因子对比表**：最多选 5 个 alpha 并排对比关键指标；⑤ **收敛仪表盘**：展示当前收敛状态、趋势箭头、建议操作。全部零外部依赖（纯 SVG + Canvas-free JS） |

#### P1 — 高优先级（应尽快实现）

| ID | 需求 | 现状 | 目标 |
|----|------|------|------|
| **P1-1** | **本地统计预筛选** | 当前 `local_quality()` 是规则检查（字段数、嵌套深度、表达式长度），不做任何统计检验 | 实现 `LocalStatisticalFilter`：① 利用 `data/` 目录下的本地历史数据（如有）或模拟数据，对生成的 alpha 做简单的秩相关检验、平稳性检验；② 筛掉缺乏统计显著性的候选，减少无效官方 API 调用 |
| **P1-2** | **因子原型库结构化** | `theme_engine.py` 的 `TEMPLATE_SKELETONS` + `_build_auto_skeletons()` 是表达式骨架列表，无经济语义 | 将因子原型形式化为包含经济 rationale 的结构：`{"name": "Analyst Revision Momentum", "rationale": "...", "applicable_field_categories": ["analyst"], "construction_rules": [...], "quality_notes": "..."}` |
| **P1-3** | **生成多样性保证** | 当前去重仅靠 `expression` 字符串完全匹配（`pool_by_expression`），高度相似的表达式（仅窗口不同）可能都被提交 | 实现基于算子集合 + 字段集合的语义去重：相同 `(sorted_fields, sorted_operators)` 的 alpha 只保留最高分的一个 |

#### P2 — 中优先级（计划内）

| ID | 需求 | 现状 | 目标 |
|----|------|------|------|
| **P2-1** | **策略档案持久化** | `ADAPTIVE_PROFILES` 硬编码在 `pipeline.py` | 将策略档案移到 `config/strategy_profiles.json`，支持用户自定义 |
| **P2-2** | **表达式模板热更新** | `TEMPLATE_SKELETONS` 硬编码在 `theme_engine.py` | 支持从 `data/alpha_templates.json` 加载用户自定义模板，运行时热更新 |
| **P2-3** | **收敛状态通知** | `ConvergenceTracker` 仅记录到事件日志 | 当收敛停滞超过阈值时，在 Web 控制台突出显示警告，并给出可操作建议 |

### 3.2 UI Design Draft — v3.0 Web 控制台

#### 整体布局

```
┌──────────────────────────────────────────────────────────────┐
│  BRAIN Alpha Ops v3.0                    [运行中] [停止] [⚙] │  ← Header
├──────────────┬───────────────────────────────────────────────┤
│ 收敛仪表盘   │                                               │
│ ┌──────────┐ │   ┌───────────────────────────────────────┐  │
│ │ 趋势 ↑   │ │   │  Alpha 表达式编辑器                    │  │
│ │ Sharpe   │ │   │  ┌─────────────────────────────────┐  │  │
│ │ 1.85→2.1│ │   │  │ rank(ts_delta(analyst_score, 20)│  │  │  ← 语法高亮
│ │ 停滞: 0  │ │   │  │ / ts_std(returns, 60))          │  │  │
│ └──────────┘ │   │  └─────────────────────────────────┘  │  │
│              │   │  [验证表达式] [提交回测] [保存草稿]    │  │
│ 生产统计     │   └───────────────────────────────────────┘  │
│ 产生: 342    │                                               │
│ 回测: 28     │   ┌───────────────────────────────────────┐  │
│ 就绪: 3      │   │  ▼ 候选池 (10)                        │  │
│ 提交: 1      │   │  ┌────┬──────┬──────┬────┬───────┐  │  │
│              │   │  │ ID │Sharpe│Fitns │得分│ 状态  │  │  │
│ 评分维度     │   │  │ a1 │ 2.15 │ 1.42 │ 87 │READY  │  │  │
│ [雷达图]     │   │  │ a2 │ 1.83 │ 1.21 │ 82 │SIM..  │  │  │
│              │   │  └────┴──────┴──────┴────┴───────┘  │  │
│ 快捷操作     │   └───────────────────────────────────────┘  │
│ [因子对比]   │                                               │
│ [导出报告]   │   ┌──────────────┬────────────────────────┐  │
│ [策略切换]   │   │ Sharpe 趋势  │ 回测槽位 (3)           │  │
│              │   │ [折线图]     │ slot1: RUNNING a5      │  │
│              │   │              │ slot2: COMPLETED a1     │  │
│              │   │              │ slot3: PENDING          │  │
├──────────────┴───┴──────────────┴────────────────────────┤  │
│  事件日志 (最新 20 条)                       [展开全部]    │  │
└──────────────────────────────────────────────────────────────┘
```

#### 关键组件描述

| 组件 | 位置 | 功能 | 实现方式 |
|------|------|------|---------|
| **收敛仪表盘** | 左上 | 显示当前趋势箭头（↑/→/↓）、最近 avg Sharpe、停滞轮数、建议操作 | 纯 CSS + 内嵌数据刷新 |
| **表达式编辑器** | 中上 | 多行 textarea，实时语法高亮：BRAIN 算子蓝色、字段名绿色、数字橙色、括号匹配高亮 | 纯 JS 正则着色，无外部依赖 |
| **评分维度雷达图** | 左下 | 8 维雷达图（economic_logic/structure/field_operator_support/data_compliance/horizon_turnover/risk_control/diversity/explainability） | 纯 SVG polygon + 轴线 |
| **候选池表格** | 中下 | 可排序表格：ID/Sharpe/Fitness/总分/状态，点击行展开 scorecard 详情 | HTML table + JS 排序 |
| **Sharpe 趋势图** | 右下 | 最近 20 轮 avg/max Sharpe 折线图，带停滞阈值参考线 | 纯 SVG polyline + circle |
| **因子对比表** | 弹窗 | 选中 2-5 个 alpha，并排对比全部指标（Sharpe/Fitness/Turnover/Correlation/Margin/SubSharpe/评分维度） | Modal 弹窗 + 表格 |

### 3.3 Open Questions

1. **经济假设的粒度与来源**：因子原型库中的经济 rationale 应该由人工预先定义（固定库），还是从已有高分 alpha 的模式中自动提炼？如果人工定义，初期需要覆盖多少个因子原型（建议 15-20 个）？

2. **评分校准的样本量阈值**：`CalibratableScorer` 的校准触发条件是积累 ≥ 20 个 official_verified 样本。考虑到每人每天最多 3 次官方回测，积累 20 个样本约需 1 周。此阈值是否合理？是否需要支持模拟模式下用本地模拟数据加速校准？

3. **定向迭代的变异策略优先级**：当 alpha 有多个问题（如低 Sharpe + 高自相关），变异策略的优先级应为：先修最差指标 → 逐一修复 → 组合修复？还是并行尝试多种变异取最优？

4. **Web 控制台的实时性 vs 简洁性**：v3.0 控制台是否需要 WebSocket 式的实时推送（轮询替代方案），还是保持当前的 HTTP 轮询即可？考虑到零外部依赖约束，标准库不支持 WebSocket，轮询频率建议多少（当前似乎没有轮询机制）？

5. **因子融合的复杂度边界**：orthogonal_blend（正交化组合）需要计算两个 alpha 向量的正交投影，这可能需要本地存储 alpha 的截面权重向量。是否接受 `data/` 目录下存储中间计算结果的 JSON 文件（可能较大，如 3000×N 的权重矩阵）？

---

## 4. 与 v2.1 的对比

| 维度 | v2.1 (当前) | v3.0 (目标) |
|------|------------|------------|
| **生成方式** | 模板随机拼接（10 硬编码模板 + 自动生成骨架） | 经济假设驱动（因子原型 → 字段映射 → 构造规则） |
| **评分系统** | 8 维硬编码 if-else，权重固定 | 8 维参数化评分 + 历史回测校准权重 |
| **迭代策略** | 停滞→切换 region/universe | 定向变异 + 正交融合 + 经验指导策略选择 |
| **融合算法** | `mutate_expression(mode="structure_change")`：包裹 zscore/winsorize | orthogonal_blend + residual_alpha + 定向变异算子 |
| **经验反馈** | 仅影响生成器模板/窗口偏好 | 同时影响 Generator / Scorer / IterativeOptimizer |
| **Web 界面** | 基础仪表盘（统计+列表+事件） | 表达式编辑器 + 雷达图 + 趋势图 + 因子对比 |
| **收敛追踪** | 停滞计数 + 建议切换策略 | 趋势分析 + 反馈效果评估 + 可操作建议 |

---

## 5. 实施建议

### 推荐顺序

1. **第一阶段**：P0-1（经济假设生成引擎）+ P0-2（可校准评分）— 解决最核心的"生成无逻辑 + 评分无预测力"问题
2. **第二阶段**：P0-3（定向迭代 + 真实融合）— 完成"有质量的迭代闭环"
3. **第三阶段**：P0-4（闭合经验反馈环）+ P0-5（Web 控制台增强）— 体验和可观测性
4. **第四阶段**：P1 + P2 各项

### 风险与注意事项

| 风险 | 缓解 |
|------|------|
| 经济假设驱动可能导致生成多样性降低 | 保留 30% 探索性随机生成（类似当前 P2-2 的 70/30 混合） |
| 评分校准在小样本下可能过拟合 | 设置最小样本阈值（默认 20），低于阈值使用默认权重 |
| SV G图表性能（大量 alpha 时） | 限制展示最近 20 轮，多余数据仅存文件 |
| 零外部依赖限制 UI 表现力 | 纯 SVG 图表在功能上可满足需求，美观度通过 CSS 补足 |
