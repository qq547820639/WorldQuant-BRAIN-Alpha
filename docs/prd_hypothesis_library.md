# PRD：假说驱动 Alpha 创作系统

## 项目信息

| 属性 | 值 |
|------|-----|
| **Language** | 中文（zh-CN） |
| **Programming Language** | Python 3.10+ |
| **Project Name** | `hypothesis_driven_alpha` |
| **文档版本** | v0.1-draft |
| **上游系统** | `brain_alpha_ops` |

### 原始需求复述

当前 Alpha 生成器（`generator.py`）采用模板驱动方式：10 个硬编码表达式骨架 + 从 7,725 个官方字段随机选取字段 + 窗口替换。生成质量不稳定，缺少经济学/行为金融学假说驱动。需要构建 **Hypothesis Library（假说库）**，让系统从"语法空间"（字段 × 算子 × 窗口 × 随机组合）升级为"研究空间"（市场假说 × 数据证据 × 合理表达式 × 官方回测反馈 × 统计校准）。

---

## 产品定义

### Product Goals

1. **假说驱动替代模板驱动**：将 Alpha 生成从"随机字段 + 硬编码表达式"升级为"假说 → 表达式族 → 适配上下文"的结构化生成流程，使每个 Alpha 有可追溯的经济学/行为金融学逻辑。

2. **闭环反馈的假说知识库**：假说库不是静态规则表，而是能与 `experience.py`（经验反馈）、scoring（评分）、diagnostics（诊断）模块形成闭环：回测结果 → 更新假说内字段/表达式的经验权重 → 提升后续生成命中率。

3. **生成策略可配置与可观测**：支持"假说驱动 / 经验反馈 / 随机探索"三种生成模式的比例配置，并提供生成来源 traceability，让研究团队能审计每个 Alpha 的来源和生成路径。

### User Stories

- **As a 量化研究员**, I want 系统基于经济学假说生成 Alpha，而不是随机拼接字段，so that 我能理解每个 Alpha 背后的逻辑并判断其是否值得深入回测。

- **As a 策略运营**, I want 能查看和编辑假说库中的假说定义（YAML 格式），so that 我能根据市场变化快速调整假说参数或新增假说。

- **As a 系统架构师**, I want HypothesisDrivenGenerator 能与现有的 DynamicThemeEngine、DatasetSelector、experience.py 解耦协作，so that 假说库可以作为独立模块迭代而不影响现有 pipeline。

- **As a 研究主管**, I want 经验反馈（experience.py）能自动调整假说库中字段/窗口/表达式的权重，so that 系统随着回测数据积累变得越来越聪明。

- **As a 运维人员**, I want 能配置"70% 假说驱动 + 20% 经验反馈 + 10% 随机探索"的生成比例，so that 能在效率和探索之间取得平衡。

---

## 技术规范

### Requirements Pool

#### P0（Must Have — 核心功能，MVP 必须交付）

| ID | 需求 | 说明 |
|----|------|------|
| P0-1 | **Hypothesis Library 定义与加载** | 支持至少 8 类市场假说的 YAML 定义文件，每类包含：经济学逻辑、候选字段类别、表达式族（2-5 种结构变体）、预期失败模式、适配建议。系统启动时加载全部假说。 |
| P0-2 | **HypothesisDrivenGenerator 核心流程** | 实现"选择假说 → 选择表达式族 → 选择字段（基于字段类别） → 适配上下文（region/universe/delay） → 组合生成 Alpha"的完整流程。 |
| P0-3 | **与 DatasetSelector 集成** | HypothesisDrivenGenerator 生成的字段需求传递给 DatasetSelector，由 DatasetSelector 根据策略（rotate/random/all）选择具体 dataset。 |
| P0-4 | **与 DynamicThemeEngine 兼容** | HypothesisDrivenGenerator 与 DynamicThemeEngine 共享统一的 Alpha 输出接口（相同的 Alpha 对象结构），确保下游 scoring/diagnostics 无需修改。 |
| P0-5 | **生成策略配置** | 支持 YAML/JSON 配置文件指定三种生成模式的比例：`hypothesis_driven` / `experience_feedback` / `random_exploration`，默认 70/20/10。 |
| P0-6 | **Alpha 溯源（Traceability）** | 每个生成的 Alpha 附加 `generation_meta`：记录了来自哪个假说、哪个表达式族、字段选择理由、生成模式。 |

#### P1（Should Have — 重要功能，v1.0 交付）

| ID | 需求 | 说明 |
|----|------|------|
| P1-1 | **假说-表达式-字段的经验权重系统** | 假说库中每个假说的字段、表达式族、窗口范围携带经验权重（初始 1.0），由 experience.py 根据回测结果更新。 |
| P1-2 | **经验反馈闭环** | experience.py 提炼的高分 Alpha 模式能反向写入假说库的权重：同字段被多次高分验证 → 权重提升；字段持续低分 → 权重衰减。 |
| P1-3 | **假说级别的门禁适配策略** | 每个假说携带"门禁适配策略"：生成时自动选择该假说最容易通过的 region/universe/delay 组合，减少无效回测。 |
| P1-4 | **假说库 CLI 管理工具** | 提供 `hypothesis-cli` 命令行工具，支持：列出假说、查看假说详情、新增假说模板、验证假说 YAML schema。 |
| P1-5 | **生成统计仪表盘** | Dashboard 展示：各假说的生成数量、通过率、高分率、平均 SHARPE，便于研究主管评估假说有效性。 |
| P1-6 | **字段类别到 OfficialDataLoader 的映射** | 假说定义中"候选字段类别"（如 `profitability_ratio`）能自动解析为 OfficialDataLoader 中的具体字段列表。 |

#### P2（Nice to Have — 增强功能，后续迭代）

| ID | 需求 | 说明 |
|----|------|------|
| P2-1 | **假说自动发现** | 基于 experience.py 累积的高分 Alpha 模式，自动聚类发现新假说候选并提示研究人员审核。 |
| P2-2 | **多假说融合生成** | 支持一个 Alpha 融合多个假说（如"Quality + Momentum"），生成复合逻辑的表达式。 |
| P2-3 | **假说版本管理** | 假说库支持版本化：每次修改假说定义生成新版本，可追溯历史，支持 A/B 测试不同版本的假说定义。 |
| P2-4 | **假说库 Web 编辑器** | 在现有 Dashboard 中增加假说库的可视化编辑界面，拖拽式调整表达式族结构和权重。 |
| P2-5 | **回测结果与假说的关联分析** | 自动分析哪些假说在哪些市场条件下表现最好，生成"假说-市场状态"适配矩阵。 |

### 系统架构关系图

```
┌─────────────────────────────────────────────────────────┐
│                   Alpha 生成 Pipeline                     │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────────┐                                    │
│  │ Hypothesis Library│ ← YAML 假说定义（8+ 类）           │
│  │  (hypotheses/)    │                                    │
│  └────────┬─────────┘                                    │
│           │ 假说选择 + 表达式族选择                         │
│           ▼                                               │
│  ┌──────────────────────────┐                            │
│  │ HypothesisDrivenGenerator │                            │
│  │  - 选择假说→表达式族→字段   │                            │
│  │  - 适配 region/universe    │                            │
│  │  - 生成策略路由 70/20/10    │                            │
│  └───┬──────────┬───────────┘                            │
│      │          │                                        │
│      ▼          ▼                                        │
│  ┌────────┐ ┌──────────────┐                             │
│  │Dataset │ │DynamicTheme  │  ← 现有模块，接口不变          │
│  │Selector│ │Engine(fallback)│                            │
│  └───┬────┘ └──────┬───────┘                             │
│      │              │                                     │
│      ▼              ▼                                     │
│  ┌──────────────────────────┐                            │
│  │    CandidateGenerator    │  ← 组合生成 Alpha 对象        │
│  └──────────┬───────────────┘                            │
│             │                                             │
│             ▼                                             │
│  ┌──────────────────────────┐                            │
│  │  Scoring → Gate → Diag   │  ← 现有评估 Pipeline         │
│  └──────────┬───────────────┘                            │
│             │ 回测结果                                     │
│             ▼                                             │
│  ┌──────────────────────────┐                            │
│  │    experience.py         │  ← 提炼模式 → 更新假说权重    │
│  │  (经验反馈)               │                             │
│  └──────────────────────────┘                            │
└─────────────────────────────────────────────────────────┘
```

### 存储格式设计

#### 推荐：YAML（主格式）+ JSON Schema 校验

**理由**：
- YAML 人类可读、支持注释、量化研究员可直接编辑
- JSON Schema 提供自动校验，防止格式错误
- 加载时一次解析为 Python dict，性能可接受（假说库总量 < 500 条）

**文件结构**：

```
hypotheses/
├── _schema.yaml              # JSON Schema 定义
├── earnings_revision.yaml    # 盈利预测上修动量
├── quality_profitability.yaml
├── value_reversal.yaml
├── low_volatility.yaml
├── liquidity_premium.yaml
├── sentiment_short.yaml
├── analyst_behavior.yaml
├── microstructure.yaml
└── custom/                    # 用户自定义假说目录
    └── ...
```

**假说文件 Schema**：

```yaml
# 每个假说文件的结构
hypothesis:
  id: "earnings_revision_momentum"       # 唯一标识
  name: "Earnings Revision Momentum"     # 人类可读名称
  category: "momentum"                   # 对应 DynamicThemeEngine 主题
  version: "1.0.0"
  
  # 经济学/行为金融学逻辑
  rationale:
    theory: "分析师盈利预测上修具有持续性..."
    academic_refs: ["Chan, Jegadeesh, Lakonishok (1996)"]
    behavioral_bias: "anchoring"         # 行为偏差类型
    
  # 候选数据字段类别（非具体字段名）
  field_categories:
    - category: "earnings_estimate_revision"
      priority: P0
      examples: ["EPS_FY1_3M_REV", "SALES_FY1_REV"]  # 仅作为示例
    - category: "analyst_rating_change"
      priority: P1
      examples: ["REC_MEAN_3M_CHG"]
      
  # 表达式族（2-5 种结构变体）
  expression_families:
    - id: "revision_diff"
      structure: "(revision_up - revision_down) / coverage"
      description: "上修减下修，除以覆盖度做标准化"
      windows: [1, 3, 6]  # 月
      
    - id: "revision_momentum_zscore"
      structure: "zscore(revision_pct, window)"
      description: "上修比例的滚动 Z-Score"
      windows: [3, 6, 12]
      
    - id: "revision_acceleration"
      structure: "revision_short - revision_long"
      description: "短期上修 - 长期上修，捕捉加速"
      windows_short: [1, 2]
      windows_long: [6, 12]
      
  # 预期失败模式
  expected_failure_modes:
    - gate: "NEUTRALIZATION"
      reason: "行业中性化后信号衰减，因分析师覆盖集中度"
      mitigation: "使用 sector-relative 版本"
    - gate: "TURNOVER"
      reason: "月度再平衡可能导致换手率过高"
      mitigation: "使用 3M 或 6M 窗口降低换手"
    - gate: "CORRELATION"
      reason: "与已有 momentum Alpha 可能高度相关"
      mitigation: "orthogonalize to existing momentum"
      
  # 适配建议
  adaptation:
    preferred_regions: ["USA", "DEV_EX_US", "ASIA"]
    preferred_universes: ["TOP3000", "MID_LARGE_CAP"]
    preferred_delays: [1, 2]
    unsuitable_regions: ["FRONTIER"]
    
  # 经验权重（运行时更新）
  experience_weights:
    overall: 1.0              # 假说整体权重
    field_category_weights: {}  # 字段类别权重（运行时填充）
    expression_family_weights: {} # 表达式族权重（运行时填充）
    window_weights: {}          # 窗口权重（运行时填充）
```

### 假说库详细设计（8 类市场假说）

#### 1. Earnings Revision Momentum（分析师预期上修动量）

| 维度 | 内容 |
|------|------|
| **经济学逻辑** | 分析师盈利预测调整具有锚定偏差（anchoring bias），上修过程缓慢且具有持续性。最先上修的股票在未来 3-12 个月有显著超额收益。 |
| **候选字段类别** | `earnings_estimate_revision`, `revenue_estimate_revision`, `analyst_rating_change`, `earnings_surprise`, `estimate_dispersion` |
| **表达式族** | (a) `(up_rev - down_rev) / coverage` — 上下修差异标准化；(b) `zscore(revision_pct, window)` — 上修比例 Z-Score；(c) `revision_rate * forecasted_growth` — 上修 × 预期增长交互；(d) `revision_short / revision_long - 1` — 加速信号 |
| **预期失败模式** | NEUTRALIZATION（行业集中）、TURNOVER（月度换手高）、CORRELATION（与 momentum 相关） |
| **适配建议** | USA/DEV 市场、TOP3000 universe、delay=1~2 天、关注财报季前后 |

#### 2. Quality / Profitability（质量因子）

| 维度 | 内容 |
|------|------|
| **经济学逻辑** | 高盈利能力的公司具有持久的竞争优势（经济护城河），市场系统性地低估这些优势的持续性。ROE、利润率等指标反映管理质量和定价权。 |
| **候选字段类别** | `profitability_ratio`, `margin`, `efficiency_ratio`, `accruals`, `earnings_quality`, `cash_flow_quality`, `balance_sheet_strength` |
| **表达式族** | (a) `(roe - cost_of_equity)` — 超额 ROE；(b) `gross_margin * asset_turnover` — DuPont 分解变体；(c) `(operating_cf - net_income) / assets` — 应计项目质量；(d) `rank(zscore(roic, 5y))` — 长期盈利稳定性 |
| **预期失败模式** | NEUTRALIZATION（防御性行业集中）、SELF_CORRELATION（质量信号自相关高）、CAPACITY（大市值股票拥挤） |
| **适配建议** | 所有发达市场、SMID_CAP 可能更有 alpha、delay=1、偏长期窗口 |

#### 3. Value / Reversal（价值反转）

| 维度 | 内容 |
|------|------|
| **经济学逻辑** | 短期（1-12 月）存在过度反应导致的均值回归，长期（3-5 年）存在价值溢价。行为金融学解释为投资者过度外推近期趋势。 |
| **候选字段类别** | `valuation_ratio`, `price_to_book`, `price_to_earnings`, `price_to_sales`, `price_to_cashflow`, `enterprise_value_multiples`, `dividend_yield`, `short_term_reversal`, `long_term_reversal` |
| **表达式族** | (a) `-1 * return(window)` — 短期反转；(b) `1 / pb_ratio` — 价值选股；(c) `(fcf_yield - sector_median)` — 行业相对便宜度；(d) `rank(-1 * momentum_12m) + rank(bm_ratio)` — 价值+反转复合；(e) `zscore(reversal_1m_neg, 36m)` — 极端下跌后的反弹 |
| **预期失败模式** | TURNOVER（反转策略换手极高）、SELF_CORRELATION（价值信号自相关）、NEUTRALIZATION（行业中性化削弱信号） |
| **适配建议** | 全球通用、small_cap 更强、delay=1、注意牛熊市表现差异 |

#### 4. Low Volatility / Low Beta（低波动异常）

| 维度 | 内容 |
|------|------|
| **经济学逻辑** | 低波动/低 Beta 股票长期风险调整后收益高于 CAPM 预测，违反"高风险高收益"假设。原因包括杠杆约束、彩票偏好、机构 benchmark 跟踪等。 |
| **候选字段类别** | `historical_volatility`, `beta`, `idiosyncratic_volatility`, `downside_risk`, `var_cvar`, `max_drawdown`, `correlation_to_market` |
| **表达式族** | (a) `-1 * volatility(window)` — 直接低波动；(b) `-1 * beta(window)` — 低 Beta；(c) `-1 * (idiosyncratic_vol / total_vol)` — 低特质波动比例；(d) `rank(sharpe_ratio) - rank(volatility)` — 效率优先 |
| **预期失败模式** | NEUTRALIZATION（低波动集中在防御行业）、CAPACITY（大市值拥挤）、CORRELATION（各类低波动 Alpha 之间高度相关） |
| **适配建议** | 发达市场、ALL_CAP、delay=1~5、熊市中表现更好 |

#### 5. Liquidity Premium（流动性溢价）

| 维度 | 内容 |
|------|------|
| **经济学逻辑** | 流动性差的股票需要提供更高预期收益作为补偿。Amihud 非流动性指标、买卖价差等衡量交易成本，流动性冲击时溢价最显著。 |
| **候选字段类别** | `bid_ask_spread`, `amihud_illiquidity`, `turnover_ratio`, `trading_volume`, `market_impact`, `free_float`, `days_to_trade` |
| **表达式族** | (a) `amihud_ratio(window)` — 经典 Amihud 非流动性；(b) `-1 * turnover_ratio(window)` — 低换手；(c) `-1 * log(market_cap) * spread` — 小盘+高差价交互；(d) `zscore(liquidity_shock, 12m)` — 流动性冲击后反弹 |
| **预期失败模式** | CAPACITY（小盘股容量不足）、TURNOVER（实际交易成本侵蚀收益）、MARKET_IMPACT（滑点） |
| **适配建议** | SMALL_CAP/MICRO_CAP universe、delay=2~5、注意实际交易成本 |

#### 6. Sentiment / Short Interest（情绪/做空信号）

| 维度 | 内容 |
|------|------|
| **经济学逻辑** | 高做空比例反映市场悲观情绪，但极端做空后可能出现 short squeeze。做空者通常是 informed trader，高做空比例也预示着基本面问题。需区分"拥挤做空"和"基本面做空"。 |
| **候选字段类别** | `short_interest_ratio`, `days_to_cover`, `short_interest_change`, `institutional_ownership_change`, `insider_trading`, `buyback_activity`, `news_sentiment` |
| **表达式族** | (a) `rank(short_interest_ratio)` — 高做空（负面信号）；(b) `-1 * rank(days_to_cover) + rank(momentum_1m)` — 高做空+近期涨势 = squeeze 信号；(c) `short_interest_change_rate(window)` — 做空变化趋势；(d) `insider_buy_ratio(window)` — 内部人买入比例 |
| **预期失败模式** | TURNOVER（squeeze 信号时效短）、CORRELATION（与 reversal 相关）、SELF_CORRELATION |
| **适配建议** | USA 市场（做空数据最全）、MID_CAP、delay=1~3 |

#### 7. Analyst Behavior（分析师行为偏差）

| 维度 | 内容 |
|------|------|
| **经济学逻辑** | 分析师存在系统性偏差：herding（羊群效应）、overconfidence（过度自信于预测精度）、confirmation bias（确认偏误）。分析师覆盖度变化、评级离散度、预测分歧度蕴含 alpha。 |
| **候选字段类别** | `analyst_coverage_change`, `recommendation_dispersion`, `estimate_dispersion`, `analyst_count`, `star_analyst_coverage`, `recommendation_consensus`, `target_price_upside`, `earnings_surprise_history` |
| **表达式族** | (a) `analyst_count_change(window)` — 覆盖度变化（增加=正面）；(b) `-1 * estimate_dispersion` — 低分歧度（共识=确定）；(c) `target_price_upside / implied_volatility` — 经风险调整的上行空间；(d) `rank(star_coverage_count)` — 明星分析师覆盖数量；(e) `surprise_persistence(window)` — 连续超预期次数 |
| **预期失败模式** | NEUTRALIZATION（分析师覆盖集中在特定行业）、DATA_LAG（评级数据有延迟）、SELF_CORRELATION |
| **适配建议** | USA/EUROPE/DEV、TOP3000（分析师覆盖充分）、delay=2~5 |

#### 8. Microstructure / Order Flow（微观结构/订单流）

| 维度 | 内容 |
|------|------|
| **经济学逻辑** | 订单流中的信息不对称：大单、暗池交易、开盘/收盘价差反映知情交易者行为。买卖不平衡 (OBI)、订单簿深度变化等高频指标含有短期 alpha。 |
| **候选字段类别** | `order_imbalance`, `block_trade_ratio`, `dark_pool_volume`, `close_open_return`, `realized_spread`, `intraday_volatility_pattern`, `vwap_deviation`, `trade_size_distribution`, `quote_stuffing_indicator` |
| **表达式族** | (a) `order_imbalance_ratio(window)` — 买卖失衡；(b) `(close_price - vwap) / vwap` — VWAP 偏离；(c) `block_trade_premium(window)` — 大宗交易溢价；(d) `overnight_return - intraday_return` — 隔夜 vs 日内收益差；(e) `-1 * realized_spread` — 逆向选择成本 |
| **预期失败模式** | MARKET_IMPACT（高频信号交易成本高）、CAPACITY（容量极有限）、DATA_QUALITY（微观结构数据噪声大） |
| **适配建议** | USA（微观结构数据最丰富）、TOP3000（流动性好）、delay=1、适合短期 Alpha |

### HypothesisDrivenGenerator 产品功能需求

#### 生成流程设计

```
INPUT: generation_config (策略比例、目标数量)
OUTPUT: List[Alpha]

Step 1: 模式路由（Mode Router）
  - 根据比例（如 70/20/10）决定本次生成使用哪种模式
  - hypothesis_driven → Step 2
  - experience_feedback → 调用 experience.py 提炼的模式
  - random_exploration → fallback 到 DynamicThemeEngine

Step 2: 假说选择（Hypothesis Selector）
  - 基于假说经验权重加权随机选择
  - 权重越高的假说被选中概率越大
  - 支持 exclude_recently_used 避免重复

Step 3: 表达式族选择（Expression Family Selector）
  - 基于表达式族经验权重选择
  - 支持 window 参数化（从假说定义的 windows 列表中选择）

Step 4: 字段选择（Field Selector）
  - 根据假说的 field_categories 获取字段类别
  - 调用 DatasetSelector 获取对应 dataset 的具体字段
  - 字段维度（如 EPS vs Sales）基于经验权重随机选择

Step 5: 上下文适配（Context Adapter）
  - 根据假说的 adaptation.preferred_regions / preferred_universes / preferred_delays
  - 结合 DatasetSelector 当前可用数据
  - 生成 region/universe/delay 组合

Step 6: Alpha 组装（Alpha Assembler）
  - 将表达式、字段、上下文组合为 Alpha 对象
  - 附加 generation_meta（溯源信息）
  - 输出到 CandidateGenerator（复用现有接口）
```

#### 与现有模块的集成关系

| 现有模块 | 集成方式 | 变更范围 |
|----------|---------|---------|
| `DynamicThemeEngine` | HypothesisDrivenGenerator 作为外层包装，ThemeEngine 作为 fallback 和 random_exploration 模式的后端 | 不改 ThemeEngine |
| `CandidateGenerator` | HypothesisDrivenGenerator 输出与现有 `generate_candidates()` 相同结构的 Alpha 对象 | 不改 CandidateGenerator |
| `DatasetSelector` | 通过字段类别映射接口调用 DatasetSelector | DatasetSelector 需增加 `get_fields_by_category()` |
| `experience.py` | 回测结果 → experience 提炼模式 → 通过 `HypothesisLibrary.update_weights()` 更新假说权重 | experience.py 需增加权重回写接口 |
| `OfficialDataLoader` | 通过 DatasetSelector 间接调用 | 不改 |
| Scoring/Gate/Diagnostics | Alpha 对象结构不变 → 下游完全兼容 | 不改 |

### Open Questions（待确认问题）

1. **假说库的初始权重如何设定？** 全部 1.0 起步，还是基于团队历史经验预设差异权重？建议从 1.0 起步，让经验反馈逐步调整。

2. **字段类别到具体字段的映射由谁维护？** 是手动维护 mapping 文件，还是自动从 OfficialDataLoader 的 7,725 个字段中按关键词匹配？建议混合：核心映射手动维护，辅助字段自动匹配。

3. **假说库修改是否需要审批流程？** 如果研究员可以直接编辑 YAML 并 reload，需要防止错误修改影响生产 pipeline。建议 v1.0 用 Git version control + PR review。

4. **experience.py 更新权重的频率？** 每天更新 vs 每周更新 vs 阈值触发？建议每日更新 + 平滑（EMA），避免单日噪声。

5. **多假说融合（P2-2）的优先级？** 是否在 v1.0 之前需要？如果复合假说预期收益显著，可能提前到 P1。

6. **假说库与 DynamicThemeEngine 的 7 类主题如何映射？** 一一映射还是一对多？建议允许假说定义携带 `theme_tags`（可多标签），灵活映射。

7. **生成策略比例（70/20/10）是可动态调整的吗？** 是否需要支持"探索期"（高 random 比例）→"收敛期"（高假说驱动比例）的自动调度？

---

## 附录：术语对照

| 术语 | 英文 | 说明 |
|------|------|------|
| 假说库 | Hypothesis Library | 8+ 类经济学/行为金融学市场假说的结构化定义集合 |
| 表达式族 | Expression Family | 同一假说下的多种表达式结构变体 |
| 字段类别 | Field Category | 语义层面的数据分组，不是具体字段名 |
| 经验权重 | Experience Weight | 基于回测结果动态调整的权重，提升有效假说/字段的被选概率 |
| 生成溯源 | Generation Traceability | 每个 Alpha 携带的元数据，记录生成路径 |
| 模式路由 | Mode Router | 根据配置比例决定本次生成使用哪种模式 |
| 上下文适配 | Context Adapter | 根据假说特性选择合适的 region/universe/delay |
