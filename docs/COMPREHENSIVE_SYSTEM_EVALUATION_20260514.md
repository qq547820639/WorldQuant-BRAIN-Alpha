# BRAIN Alpha Ops 系统 — 综合评价报告

> **评审日期**: 2026-05-14
> **评审范围**: 代码库全量审计（34 源文件，约 13,000+ 行）、架构设计文档、测试覆盖、Web 交互
> **评审方法**: 代码级深度审计 + 架构分析 + 用户交互体验评估
> **核心问题**: 系统能否完成目标——创作、估分、评价、迭代、收敛，产出高质量 Alpha

---

## 一、整体印象与主观评价

### 1.1 一句话评价

**这是一个架构野心与工程执行力高度匹配的量化 Alpha 自动化系统，已经越过了"能跑"的 MVP 阶段，正在向"科学评分系统"的方向系统性演进。在"零硬编码 + 官方数据驱动"这一核心原则上做到了高度的一致性和约束力。**

### 1.2 逐项印象

| 维度 | 评级 | 印象 |
|------|------|------|
| **架构设计** | ★★★★☆ | 分层清晰、职责明确、关键设计模式（Singleton / Protocol / Strategy）运用得当 |
| **工程纪律** | ★★★★☆ | 零硬编码原则贯彻到底、配置文件化、JSONL 可审计性、Mock/Official 双环境 |
| **科学严谨性** | ★★★★☆ | 三层评分体系、BRAIN 官方阈值对齐、Bootstrap 置信区间、收敛统计检验 |
| **代码质量** | ★★★☆☆ | monolith 函数过长（pipeline.run() 2400+ 行）、inline HTML、全局锁、零依赖的代价 |
| **文档完整性** | ★★★★★ | system_design 42KB + OPERATING_RULES + QA 报告 + 实现手册，文档体系堪称典范 |
| **用户交互** | ★★★☆☆ | 本地 Web 控制台功能齐全但代际老旧（纯轮询、无推送、HTML 内联），交互粗糙 |

---

## 二、核心能力逐项分析

### 2.1 创作（Alpha Generation）—— 评级：★★★★☆

**现状**: 系统具备三层生成体系：

| 模式 | 占比 | 说明 | 成熟度 |
|------|------|------|--------|
| **假设驱动** (hypothesis_driven) | 70% | YAML 定义假设 → 选择表达家族 → 映射字段 → 生成表达式 → 验证 | 高 |
| **经验反馈** (experience_feedback) | 20% | 从官方 PASS 记录中提取 winning patterns，指导字段/算子/窗口选择 | 中 |
| **随机探索** (random_exploration) | 10% | 维持搜索空间多样性 | 低（必要性低） |

**生成链路**:
```
HypothesisLibrary (13+ YAML 假设)
  → HypothesisSelector (EMA 加权选择)
    → ExpressionFamilySelector (字段组合规则)
      → FieldSelector (分类映射 → DatasetSelector)
        → ContextAdapter (适配数据集上下文)
          → DynamicThemeEngine (算子骨架生成)
            → CandidateGenerator → Candidate(expression, fields, operators, ...)
```

**优势**:
- 从 8 个硬编码字段扩展到利用 **7642 个官方字段**，16 个数据集，66 个官方算子
- DynamicThemeEngine 从 9 个分类自动生成表达骨架（momentum / reversal / value / quality / volatility / liquidity / cross_sectional / hybrid 等）
- 假设驱动的生成具有可追溯的 provenance（记录所选假设、表达家族、字段映射）

**缺陷**:
1. 字段池构建 `_build_official_field_pool(dataset_id)` 仅取 top 30 字段——虽然按 coverage × (1 + user_bonus + alpha_bonus) 评分排序有合理性，但 30 个字段对某些数据集可能过于受限
2. 窗口大小硬编码 14 个固定值 [3,5,8,10,12,15,20,30,40,60,90,120,180,252]——未按数据集频率特征自适应
3. DynamicThemeEngine 的骨架仍部分依赖预定义模式，并非完全从算子 combinatorics 生成

**判定**: **系统能够完成 Alpha 创作**，生成质量有结构化约束。假设驱动的生成方式相比随机生成具有显著的科学性优势。但字段选择范围和窗口自适应性有待加强。

---

### 2.2 估分（Scoring / Estimation）—— 评级：★★★★☆

**现状**: 三层评分体系（先验 + 实证 + 提交清单），总权重 30/45/25：

**第一层：先验评分 (prior_score)** — 8 维度 × 可校准权重：

| 维度 | 默认权重 | 评分逻辑 | 可校准 |
|------|----------|----------|--------|
| economic_logic | 18% | 9 类经济概念关键词检测（momentum/mean_reversion/value/quality/volatility/liquidity/growth/risk_management/cross_sectional），4+概念=92分 | 概念词典可调 |
| structure | 14% | 算子数量线性罚分：base=90, 每超出 4 个算子 -8 | ✅ 参数化 |
| field_operator_support | 16% | 字段数×8 + 去重算子数×4，上限 92 | ✅ 参数化 |
| data_compliance | 12% | 有字段=82，无字段=35（二值） | ✅ 参数化 |
| horizon_turnover_proxy | 14% | 窗口中位数三档（窗口内/外/无数据） | ✅ 参数化 |
| risk_control_proxy | 14% | 三条件分层（cross-section + time-series + risk-control） | ✅ 参数化 |
| diversity | 7% | 按 alpha 家族分类（Liquidity/Volatility/Hybrid 高，其余低） | ✅ 参数化 |
| explainability | 5% | 表达式长度阈值 | ✅ 参数化 |

**第二层：实证评分 (empirical_score)** — 16 项 BRAIN 指标转化，总分制：

| 序号 | 项目 | 阈值来源 | 分值 | 类型 |
|------|------|----------|------|------|
| 1 | sharpe ≥ 1.25 (Delay-1) | BRAIN LOW_SHARPE | 20 | 硬门禁 |
| 2 | fitness ≥ 1.0 (Delay-1) | BRAIN LOW_FITNESS | 15 | 硬门禁 |
| 3 | fitness_crosscheck | BRAIN 公式验证 | 0 | 调试项 |
| 4 | turnover_min ≥ 1% | BRAIN LOW_TURNOVER | 8 | 硬门禁 |
| 5 | turnover_platform ≤ 70% | BRAIN HIGH_TURNOVER | 8 | **平台硬门禁** |
| 6 | turnover_quality ≤ 30% | 顾问质量目标 | 6 | 质量警告 |
| 7 | returns ≥ 0 | 定性 | 5 | 软指标 |
| 8 | drawdown ≤ limit | 定性（非BRAIN硬检） | 5 | 软指标 |
| 9 | self_correlation ≤ 0.70 | BRAIN SELF_CORRELATION | 14 | 硬门禁+例外 |
| 10 | prod_correlation ≤ limit | 衍生自SELF_CORRELATION | 10 | 硬门禁 |
| 11 | weight_concentration ≤ 10% | BRAIN CONCENTRATED_WEIGHT | 5 | 硬门禁 |
| 12 | sub_universe_sharpe | BRAIN LOW_SUB_UNIVERSE_SHARPE | 10 | 硬门禁 |
| 13 | is_oos_ratio ≥ 0.5 | IS/OOS鲁棒性 | 8 | 质量门禁 |
| 14 | margin ≥ 4.0 bps | 顾问标准 | 10 | 质量门禁 |

**第三层：提交清单 (submission_checklist)** — 7 项，总分制：

- official_metrics_present (15) / official_pass (15) / economic_logic (15) / data_delay_conservative (10) / local_quality (15) / self_correlation_proxy (20) / diversity (10)

**决策分带 (decision_band)**:
- ≥85: submit_candidate
- ≥70: optimize_before_submit
- ≥50: research_only
- <50: abandon_or_rebuild

**优势**:
1. **维度丰富**: 8+16+7 = 31 个评分项，覆盖经济逻辑、结构、字段/算子、实证表现、风险控制、多样性、提交安全性
2. **结构化**: 三层架构（先验/实证/提交清单），每层有独立的权重分配和分带判定
3. **可解释**: 每个评分项有明确的"名称→实际值→比较方向→目标值→通过/失败→分值"，scorecard JSON 可完整回溯
4. **可校准**: 6 个维度参数化（structure/field_operator_support/horizon_turnover_proxy/risk_control_proxy/diversity/explainability），支持 Grid Search 自动优化；维度权重和层权重均可通过 calibrate_weights.py 校准
5. **BRAIN 对齐**: 所有阈值来源于官方 Alpha Check 标准（LOW_SHARPE/ LOW_FITNESS/ HIGH_TURNOVER/ CONCENTRATED_WEIGHT/ SELF_CORRELATION/ LOW_SUB_UNIVERSE_SHARPE）

**缺陷**:
1. `economic_logic` 维度关键词检测虽比原二值化方案（hypothesis 长度 ≥ 40 → 85/否则 45）进步显著，但仍是字符串匹配，未涉及 NLP 语义理解
2. `empirical_score` 将硬门禁和软指标混在同一计分函数中——硬门禁失败应该是阻断性（score=0），而非仅扣分
3. 置信度估算仅基于 item 离散度，未考虑数据完备性以外的外部不确定性（如市场制度变化）

**判定**: **评分体系已达到"维度丰富、结构化、可解释、可校准"的标准。具备向科学评分系统演进的基础。** 8 维度先验 + 16 项实证 + 7 项清单的覆盖度远超一般量化系统的评分精度。

---

### 2.3 评价（Evaluation / Quality Gate）—— 评级：★★★★☆

**门禁链路**:

```
Candidate
  → local_prefilter (local_quality + convergence_score)
    → expression_validate (BRAIN API pre-check)
      → submit_simulation (BRAIN API simulation)
        → poll_simulation → fetch_result (官方 metrics)
          → build_scorecard (三层评分)
            → evaluate_quality_gate (门禁判定)
              → SubmissionLedger.assess() (安全门禁)
                → submit_alpha() (BRAIN API 提交)
```

**门禁层级**:

| 层级 | 触发点 | 判定逻辑 | 阻断方式 |
|------|--------|----------|----------|
| **本地预筛** | local_convergence_score < 阈值 | 先验+本地质量分 | 不入官方模拟队列 |
| **表达式验证** | BRAIN API validate | 语法/字段/算子有效性 | 不入模拟 |
| **实证硬门禁** | sharpe/fitness/turnover/correlation | BRAIN 官方标准 | 门禁 FAIL |
| **质量门禁** | turnover_quality/margin/sub_universe | 顾问质量目标 | 门禁 WARNING |
| **安全门禁** | 日限/次限/间隔/相似度/风险评估 | 账户安全策略 | BLOCK 提交 |

**优势**:
1. 门禁逻辑贯穿全链路——从生成到提交 6 道关卡，分层阻断
2. `evaluate_quality_gate()` 的 failed_reasons 结构化输出，精确到 `{name} {direction} {target} (actual: {actual})` 格式
3. SELF_CORRELATION 实现了 BRAIN 官方例外规则（Sharpe 优势 10% → 豁免）
4. Market regime adjustment（延迟感知 + 市场制度调整）使门禁阈值具有场景适应性

**缺陷**:
1. `evaluate_quality_gate()` 中的 passed/not failed 逻辑与 `failed.append()` 之间有一定耦合——warnings 不会被计入 failed，但 passed = not failed 的判断基于 failed 列表
2. 缺少 BRAIN 官方 Alpha Check 中"多 Alpha 交叉污染"检查（PROD_CORRELATION 虽然存在但仅限本地指标）

**判定**: **门禁体系覆盖全面、分层清晰、与 BRAIN 官方标准对齐。** 具备生产级提交安全控制能力。

---

### 2.4 迭代（Iteration / Improvement）—— 评级：★★★★☆

**迭代引擎**: 系统具备 **诊断→突变→重试→对比** 的完整迭代回路：

```
官方回测结果
  → diagnose() [diagnostics.py]
    ├─ 识别 primary_failure
    ├─ 列出 failed_dimensions
    └─ 建议 mutation 方向
      → IterativeOptimizer [iterative_optimizer.py]
        ├─ field_swap（替换字段）
        ├─ window_perturb（窗口扰动）
        ├─ structure_refine（结构调整）
        ├─ field_swap_semantic（语义替换）
        ├─ operator_substitute（算子替代）
        └─ longer_window（延长窗口）
          → 生成 mutant → submit_simulation → AB 对比
            → experience.record_ab_comparison()
              → 更新 Hypothesis 权重 (EMA)
```

**优势**:
1. 故障诊断引擎将每个 BRAIN 指标的失败映射到具体的突变策略——非盲目的随机变异
2. 算子家族体系（ranking/standardization/moving_average/difference/volatility/correlation/winsorization/decay/step/minmax）使算子替代具有语义合理性
3. AB 对比记录 (`data/ab_tests.jsonl`) 提供可审计的改进效果证据链
4. Alpha 融合 (`fusion.py`)：orthogonal_blend（正交化去冗余）+ composite_ensemble（多 alpha 组合）

**缺陷**:
1. 突变策略相对固定（6 种模式），未引入参数化突变强度（如窗口调整步长）
2. 融合限于两两组合，未实现 N-alpha 正交化套利组合
3. 迭代深度受限于 simulation budget（每轮 3 simulations / 20 candidates）——大量候选无法获得官方反馈

**判定**: **迭代闭环完整且有科学依据。** 诊断→突变→对比→学习的回路是系统逐步提升产出质量的核心机制。

---

### 2.5 收敛（Convergence）—— 评级：★★★★☆

**收敛追踪器 (ConvergenceTracker)**:

```
每轮生产
  → CycleRecord (produced/passed/simulated/submitted/avg_sharpe/avg_fitness/max_sharpe)
    → 滚动窗口 (默认 10 轮)
      ├─ Bootstrap 90% 置信区间 (avg_sharpe)
      ├─ Spearman 秩相关趋势检验
      └─ CI-重叠 stall 检测
        → 连续 5 轮无显著改善
          → ConvergenceStatus {stalled: true, recommendation: "建议切换策略"}
            → pipeline 自动切换 Adaptive Profile（7 选 1）
```

**优势**:
1. Bootstrap 置信区间替代了简单的前后半均值比较——具有统计严谨性
2. Spearman 秩相关检测单调趋势，比 Pearson 更适合小样本场景
3. CI-重叠 stall 检测避免了因噪声波动导致的误判
4. 自适应策略切换（7 个 profile: usa_standard/liquid/sector/market/europe/global/china）提供了多市场探索空间

**缺陷**:
1. 默认窗口 10 轮 × 收敛阈值 5 轮——小样本下统计功效有限
2. 策略切换逻辑基于简单轮换，未使用 Multi-Armed Bandit 等更优的 explore-exploit 算法
3. 未追踪跨策略的 "transfer learning" 效果——切换策略后是否保留了上一策略的经验

**判定**: **收敛检测在统计方法层面已达到科学研究标准。** Bootstrap + Spearman + CI-重叠的组合远超行业平均水平。

---

### 2.6 能否产出高质量 Alpha？—— 评级：★★★★☆

**证据链**:

| 环节 | 状态 | 判断依据 |
|------|------|----------|
| 生成质量 | ✅ | 假设驱动 + 7642 字段 + 66 算子 + 经验反馈 |
| 预筛精度 | ✅ | 先验 8 维 + 本地质量 + 本地收敛分排序 |
| 官方模拟 | ✅ | 完整 BRAIN API 流程（authenticate→validate→submit_sim→poll→fetch） |
| 评分校准 | ✅ | auto_calibrator 从官方 PASS 记录学习，最小化 prior-empirical 误差 |
| 门禁安全 | ✅ | 6 层门禁（预筛→验证→实证→质量→安全→提交），与 BRAIN 官方对齐 |
| 迭代改进 | ✅ | 诊断→突变→AB 对比→经验更新 |
| 收敛检测 | ✅ | Bootstrap CI + Spearman + stall + profile switch |

**核心判断**: 系统具备 **理论上的高质量 Alpha 产出能力**，但实际产出质量高度依赖：
1. 官方 simulation budget 的充足性（当前每轮最多 3 个 simulation，大量候选无法获得官方反馈）
2. 先验评分与实证评分的相关性——auto_calibrator 的存在就是为了弥合这一 gap

---

## 三、BRAIN API 流程对齐分析

### 3.1 官方 API 流程覆盖

| API 端点 | OfficialBrainAPI 方法 | 状态 | 备注 |
|----------|----------------------|------|------|
| POST /authentication | `authenticate()` | ✅ | Basic Auth + Token 双模式，Cookie + Bearer fallback |
| GET /fields | `list_fields()` | ✅ | 分页拉取 + SHA256 文件缓存 |
| GET /operators | `list_operators()` | ✅ | 同上 |
| GET /user/alphas | `list_user_alphas()` | ✅ | 去重 + 云端同步 |
| POST /alpha/validate | `validate_expression()` | ✅ | 本地预验证（括号/字段/算子）后调用 |
| POST /alpha/simulations | `submit_simulation()` | ✅ | BrainSettings→API payload 转换 |
| GET /alpha/simulations/{id} | `poll_simulation()` | ✅ | 状态轮询 |
| GET /alpha/simulations/{id}/result | `fetch_result()` | ✅ | metrics + alpha detail 提取 |
| POST /alpha/check | `check_alpha()` | ✅ | BRAIN 标准 Alpha Check |
| POST /alpha/submit | `submit_alpha()` | ✅ | mock/demo/test ID 拦截门禁 |
| GET /datasets | 无公开方法 | ⚠️ | `list_datasets()` 未实现——数据来自本地 JSON |
| POST /alpha/correlations/check | 未实现 | ❌ | PROD_CORRELATION 仅本地估算 |

### 3.2 关键对齐项

| 对齐项 | 状态 | 详情 |
|--------|------|------|
| 阈值对齐 | ✅ | 全部来自 BRAIN Alpha Check 文档（LOW_SHARPE 1.25/LOW_FITNESS 1.0/HIGH_TURNOVER 0.70/SELF_CORRELATION 0.70/CONCENTRATED_WEIGHT 0.10/LOW_SUB_UNIVERSE_SHARPE） |
| Fitness 公式 | ✅ | Official: Sharpe × √(|Returns| / max(Turnover, 0.125))，有交叉验证 |
| SELF_CORRELATION 例外 | ✅ | 官方规则：新 alpha Sharpe ≥ 关联 alpha Sharpe × 1.10 → 豁免 |
| 延迟感知阈值 | ✅ | Delay-0: min_sharpe=2.0 / min_fitness=1.3; Delay-1: min_sharpe=1.25 / min_fitness=1.0 |
| Alpha 类型感知 | ✅ | AlphaCheckRegistry.build_type_checks(POWER_POOL/ATOM/PYRAMID) |
| Pasteurize 字段 | ✅ | `BrainSettings.pasteurization → API payload pasteurize` 自动转换 |

### 3.3 未对齐项

| 未对齐项 | 严重度 | 影响 |
|----------|--------|------|
| datasets API 未调用 | P2 | 数据集列表来自本地 JSON，需手动同步 |
| PROD_CORRELATION API 未调用 | P2 | 仅本地估算，未使用 BRAIN `/alpha/correlations/check` |
| Fields/Operators 刷新失败静默忽略 | P1 | 已识别但未修复——`_refresh` 方法无告警机制 |

**判定**: **系统已完成 BRAIN API 核心流程的完整对接。** 能够执行真实模拟、获取官方结果、评分、门禁判断。3 项未对齐属于增强项而非阻断项。

---

## 四、评分体系向科学评分系统演进的潜力分析

### 4.1 当前体系的结构化程度

```
评分体系架构:

┌─────────────────────────────────────────────────────────────┐
│                    ScoringParams (可持久化校准参数)            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │structure │ │field_ops │ │ horizon  │ │  risk    │  ...  │
│  │参数      │ │参数      │ │参数      │ │ 参数     │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: prior_score (8 dim × weights)  → 先验推理         │
│  Layer 2: empirical_score (16 items)      → 实证验证         │
│  Layer 3: submission_checklist (7 items)  → 提交安全         │
├─────────────────────────────────────────────────────────────┤
│  Convergence Tracker: Bootstrap CI + Spearman + Stall       │
│  Auto Calibrator: Grid Search + OLS + Layer Weights        │
│  Confidence: Item dispersion → score reliability          │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 演进潜力评估

| 科学评分系统要素 | 当前状态 | 差距 | 可行性 |
|------------------|----------|------|--------|
| **多维指标体系** | ✅ 31 项 | — | 已实现 |
| **层次化评分** | ✅ 三层 | 可增加层级交互 | 低 |
| **可解释性** | ✅ 每项有名/值/方向/目标/通过/得分 | — | 已实现 |
| **可校准性** | ✅ Grid Search + OLS | 缺少贝叶斯校准 | 中 |
| **置信区间** | ✅ Bootstrap CI + item dispersion | 可增加预测区间 | 低 |
| **统计显著性** | ✅ Spearman + CI-overlap | 可增加 hypothesis testing | 低 |
| **时序一致性** | ✅ ConvergenceTracker | 可增加 CUSUM | 低 |
| **外部验证** | ✅ BRAIN 官方指标 | — | 已实现 |
| **正则化防过拟合** | ⚠️ 权重归一化 | 缺少 L1/L2 / 交叉验证 | 中 |
| **A/B 实验框架** | ✅ ab_tests.jsonl | 可增加统计检验 | 低 |
| **自适应调参** | ✅ 自动校准 + profile 切换 | 缺少在线学习 | 高 |

**结论**: **系统已具备向科学评分系统演进的核心基础。** 31 项指标 + 三层架构 + 可校准参数 + 统计检验 + A/B 框架构成了完整的科学评分基础设施。主要 gap 在于正则化和在线学习能力，但这两项在量化 Alpha 评分场景中的优先级相对较低。

---

## 五、用户交互评估

### 5.1 Web 控制台

| 评估项 | 评级 | 详情 |
|--------|------|------|
| **视觉设计** | ★★★★☆ | 配色克制（Teal 主题）、CSS 变量体系、圆角卡片、渐变过渡、暗色/亮色一致性好 |
| **功能完整度** | ★★★★☆ | 环境切换、凭据输入、市场预设、启停控制、进度条、Backtest 槽位管理、候选列表、评分徽章、批量操作、云端同步、历史记录、统计面板 |
| **交互流畅度** | ★★★☆☆ | 依赖 setInterval 轮询（非 WebSocket 推送），操作响应延迟取决于轮询间隔；无操作反馈动画（如按钮 loading 状态） |
| **反馈及时性** | ★★★☆☆ | 轮询式更新，典型延迟 1-3 秒。无实时推送能力。Pipeline 启停需要等待当前周期完成 |
| **信息架构** | ★★★★☆ | 左侧控制面板 + 右侧监控/列表的经典双栏布局，信息分层合理（仪表盘→监控→候选列表→详情） |
| **可维护性** | ★★☆☆☆ | ~500 行 HTML 内联为 Python 原始字符串（`r"""..."""`），CSS/JS/HTML 混排，无模块化，无构建工具 |

### 5.2 CLI 交互

| 评估项 | 评级 | 详情 |
|--------|------|------|
| **命令设计** | ★★★☆☆ | `brain-alpha-ops run` + `init-config`，覆盖主流程 |
| **参数覆盖** | ★★★★☆ | --env/--cycles/--candidates/--validations/--simulations/--auto-submit/--storage-dir/--base-url/--username/--password/--token |
| **输出质量** | ★★★☆☆ | JSON 输出完整但冗长，缺少人类可读的进度摘要 |

### 5.3 改进建议（优先级排序）

| 优先级 | 改进项 | 期望效果 |
|--------|--------|----------|
| P1 | WebSocket 推送替代轮询 | 实时更新，接近原生体验 |
| P1 | HTML/CSS/JS 拆分到独立文件 | 大幅提升可维护性 |
| P2 | 按钮 loading 状态 + 操作确认弹窗 | 防误操作，心理安全感 |
| P2 | 图表可视化（评分趋势、Sharpe 分布） | 替代纯表格展示 |
| P3 | 响应式移动端适配 | 手机上监控管线 |

---

## 六、系统架构整体评分

```
                    创作 (Generation)     ★★★★☆
                         │
                         ▼
                    估分 (Scoring)        ★★★★☆
                         │
                         ▼
                    评价 (Evaluation)     ★★★★☆
                         │
                     ┌───┴───┐
                     ▼       ▼
              迭代 (Iterate)  ← 收敛 (Converge)
                 ★★★★☆          ★★★★☆
                     │               │
                     └───┬───────────┘
                         ▼
                   高质量 Alpha
                     ★★★★☆


组件          评级    权重    加权得分
─────────────────────────────────────
创作          4.2     0.20    0.84
估分          4.3     0.20    0.86
评价          4.2     0.15    0.63
迭代          4.2     0.15    0.63
收敛          4.1     0.10    0.41
API 对齐      4.0     0.10    0.40
用户交互      3.5     0.10    0.35
─────────────────────────────────────
综合加权评分   4.1 / 5.0
```

---

## 七、优化建议（按优先级）

### P0 — 阻断性缺陷

| # | 缺陷 | 影响 | 建议 |
|---|------|------|------|
| 1 | `run_config.json` 重复 JSON key | JSON 解析使用最后一个值——暂不影响功能但有歧义 | 删除重复项 |
| 2 | Fields/Operators 刷新静默失败 | `check_batch` 只刷新云 Alpha，漏 fields/operators 同步且无告警 | 添加刷新失败告警 + 自动回退 |

### P1 — 重要改进

| # | 改进项 | 影响 | 建议 |
|---|--------|------|------|
| 3 | `pipeline.run()` 超长函数（2400+ 行） | 可维护性差、难以单元测试、易引入 bug | 按生命周期阶段分解：`_gen_phase()` / `_sim_phase()` / `_eval_phase()` / `_submit_phase()` |
| 4 | empirical_score 硬门禁 vs 软指标混淆 | 硬门禁失败应阻断而非仅扣分 | 添加 `hard_fail` 标记，硬门禁失败 → score=0 或单独报错 |
| 5 | 字段池 top 30 限制 | 对字段丰富的数据集（如 model77）可能遗漏低覆盖但高 alpha 的稀有字段 | 增加到 top 50 或按百分位动态截断 |
| 6 | `_ratio()` 百分比检测 heuristic | `abs > 1.0 → /100` 可能误处理某些边界值 | 添加 API 响应 `is_percentage` 字段或从文档获取单位信息 |
| 7 | 全局请求锁串行化 | 多 pipeline 实例无法并发（当前影响小，仅本地单实例） | 改为 per-instance 锁 + 可配置并发数 |

### P2 — 体验与工程改进

| # | 改进项 | 影响 | 建议 |
|---|--------|------|------|
| 8 | HTML/CSS/JS 拆分 | 维护成本高 | 独立 `web/` 目录下的文件，Python 读取后注入 |
| 9 | WebSocket 推送 | 轮询体验差 | 用 `websockets` 库或 SSE |
| 10 | PROD_CORRELATION API | 仅本地估算 | 调用 BRAIN `/alpha/correlations/check` |
| 11 | 可视化图表 | 纯表格展示 | 集成轻量图表库（Chart.js CDN） |
| 12 | pytest 迁移 | 测试框架不标准 | 重写测试为 pytest，集成 CI/CD |
| 13 | logging 统一 | print/logging 混用 | 统一使用 logging + handlers |

---

## 八、结论

### 8.1 系统能否完成目标？

**可以。** 系统在创作→估分→评价→迭代→收敛的完整闭环中，每个环节都有坚实的工程实现和科学依据支撑。具体而言：

- **创作**: 假设驱动的三模式生成体系，从 7642 字段中抽取，结构严谨
- **估分**: 31 项指标的三层评分体系，维度丰富、结构化、可解释、可校准
- **评价**: 6 层门禁链路，与 BRAIN 官方标准对齐
- **迭代**: 诊断→突变→AB 对比→经验更新的完整闭环
- **收敛**: Bootstrap + Spearman + CI-重叠的科学收敛检测

### 8.2 能否产出高质量 Alpha？

**理论上能，实际效果受 simulation budget 和先验-实证相关性约束。** auto_calibrator 的存在就是为了持续缩小这一 gap。在没有大量官方 simulation passage 记录的情况下，系统更像一个"精密筛选器"——绝大部分 Alpha 会被门禁淘汰，少数通过者需要真实市场的检验。

### 8.3 评分体系能否向科学评分系统演进？

**已具备基础，路径清晰。** 31 项指标的分层架构 + 可校准参数 + 统计检验 + A/B 框架构成了科学评分系统的核心基础设施。当前主要差距在正则化防过拟合和在线学习——但这两项在量化 Alpha 场景下优先级不高。

### 8.4 用户交互是否足够？

**功能足，体验糙。** Web 控制台功能齐全，但 HTML 内联 + 轮询架构的代际老旧。如不依赖 Web 交互（大多数量化研究者偏好 CLI），则当前 CLI 已满足基本需求。Web 控制台更建议视为"本地监控面板"而非"专业工作台"。

---

*报告结束。数据来源：代码库全量审计（34 源文件），架构设计文档，测试覆盖分析。*
