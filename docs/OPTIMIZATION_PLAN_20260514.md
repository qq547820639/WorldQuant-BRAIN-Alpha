# BRAIN Alpha Ops 系统 — 整体印象、主观评价与优化方案

> **产出日期**: 2026-05-14
> **评审依据**: 全链路代码审计（34 源文件 + data/official_*.json 数据源 + docs/ 16 份文档）+ 双 agent 并行探索（data/docs/config/tests + research/brain_api/data 全量）
> **审计方法**: 基于代码事实 + BRAIN 官方 API 阈值 + 数据文件逐项对照 + 生产链路推演 + archive 版本对比
> **覆盖范围**: 创作 / 估分 / 评价 / 迭代 / 收敛 / API 模拟 / 门禁 / 用户交互 / archive 差异分析

---

## 一、整体印象与主观评价

### 1.1 一句话评价

**这是一个工程纪律与架构野心高度匹配的量化 Alpha 自动化系统。它以"零硬编码 + 官方数据驱动"为核心信条，越过了"能跑"的 MVP 阶段，正从"精密筛选器"向"科学评分系统"的方向系统性演进。**

### 1.2 逐项主观印象

| 维度 | 评级 | 主观判断 |
|------|------|----------|
| **架构设计** | ★★★★☆ | 分层清晰（API/Data/Research/Web/Safety 六层），关键模式（Singleton/Protocol/Strategy）运用得当，零循环依赖 |
| **工程纪律** | ★★★★★ | 零硬编码原则全链路贯彻；JSONL 全链路可审计；Mock/Official 双环境隔离；配置化驱动的参数管理 |
| **科学严谨性** | ★★★★☆ | 三层评分（31 项指标）；BRAIN 官方阈值全对齐；Bootstrap CI 收敛检测；Fitness 公式交叉验证；自适应多策略切换 |
| **代码质量** | ★★★☆☆ | Monolith pipeline.run() 虽经 P3 重构仍偏长（~1500 行）；Web HTML 内联为 Python 字符串；全局请求锁 |
| **文档完整性** | ★★★★★ | system_design 42KB + OPERATING_RULES + QA 验证报告 + CODE_QUALITY_AUDIT + COMPREHENSIVE_SYSTEM_EVALUATION — 文档体系堪称典范 |
| **用户交互** | ★★★☆☆ | Web 控制台功能齐全但轮询架构老旧、HTML 内联难以维护；CLI 满足基本需求但输出可读性可提升 |

### 1.3 主观判断

这是一个**严肃的生产级项目**，绝非玩具或概念验证。代码风格一致、注释规范、无魔法数字、每个阈值均有"为什么是这个值"的 BRAIN 官方溯源标注。项目的核心信念——"不刷量，只提交经过多层门禁的高质量 Alpha"——是正确的且在全链路中始终保持了约束力。

但客观来说，系统介于"工程上能跑"和"科学上可信"之间。因为"科学上可信"需要的不仅是阈值对齐，还有可重复的实验设计、可归因的失败分析、可量化的改进效果。系统的评分权重（30/45/25）和 8 维先验权重（0.18/0.14/0.16...）目前是经验设定，虽可通过 `auto_calibrator` 校准，但样本量不足时校准可信度有限。

---

## 二、系统目标达成度深度分析

### 2.1 创作（Alpha Generation）—— 达成度：★★★★☆

**当前链路**:

```
HypothesisLibrary (13+ YAML 假设)
  → HypothesisSelector (EMA 加权选择)
    → ExpressionFamilySelector (字段组合规则)
      → DatasetSelector (rotate 待选数据集)
        → DynamicThemeEngine (自动生成表达式骨架)
          → CandidateGenerator → Candidate(expression, fields, operators, dataset)
```

| 关键项 | 状态 | 证据 |
|--------|------|------|
| 字段覆盖 | ✅ 7642 个官方字段 | `data/official_fields.json` → `OfficialDataLoader` 单例加载 |
| 算子覆盖 | ✅ 66 个官方算子 | `data/official_operators.json` → `DynamicThemeEngine` 按类生成骨架 |
| 数据集支持 | ✅ 16 个数据集 | `DatasetSelector` 支持 all/rotate/random/specific |
| 三模式生成 | ✅ 假设驱动(70%) / 经验反馈(20%) / 随机探索(10%) | `HypothesisDrivenGenerator` 可配置比例 |
| 字段池限制 | ⚠️ top 50 字段 | `_max_field_pool_size=50` — 对 model77(3256 fields) 偏保守 |
| 窗口自适应性 | ⚠️ 固定 14 个值 | `[3,5,8,10,12,15,20,30,40,60,90,120,180,252]` — 未按数据集频率自适应 |

**判定**: 系统能够完成 Alpha 创作。假设驱动的生成方式相比随机生成具有显著的科学性优势。生成链路从"8 个硬编码字段"进化到"7642 个官方字段 + 16 个数据集"是质的飞跃。

### 2.2 估分（Scoring）—— 达成度：★★★★☆

**三层评分架构**:

```
┌──────────────────────────────────────────────────┐
│  Layer 1: Prior Score (8 维度 × 可校准权重)       │
│  economic_logic / structure / field_operator_     │
│  support / data_compliance / horizon_turnover_    │
│  proxy / risk_control_proxy / diversity /         │
│  explainability                    [权重 30%]     │
├──────────────────────────────────────────────────┤
│  Layer 2: Empirical Score (16 项 BRAIN 指标转化)   │
│  sharpe / fitness / turnover_platform /           │
│  turnover_quality / self_correlation /            │
│  prod_correlation / weight_concentration /        │
│  sub_universe_sharpe / is_oos_ratio / margin_bps  │
│  / returns / drawdown ...          [权重 45%]     │
├──────────────────────────────────────────────────┤
│  Layer 3: Submission Checklist (7 项安全检查)       │
│  official_metrics / official_pass /               │
│  economic_logic / local_quality /                 │
│  self_correlation_proxy / diversity               │
│                                    [权重 25%]     │
├──────────────────────────────────────────────────┤
│  Decision Band: ≥85 submit / ≥70 optimize /       │
│                 ≥50 research / <50 abandon        │
└──────────────────────────────────────────────────┘
```

**维度丰富度**: 8 + 16 + 7 = **31 项**评分指标，远超一般量化系统的评分精度。

**结构化程度**: 每个评分项有明确的 "名称 → 实际值 → 比较方向 → 目标值 → 通过/失败 → 分值"，scorecard JSON 可完整回溯。

**可解释性**: 每个维度均有明确的评分规则（如 `economic_logic`: 9 类经济概念关键词检测，4+概念=92 分）。

**可校准性**: `calibrate_weights.py` 支持 Grid Search + OLS；`auto_calibrator` 从 BRAIN 官方 PASS 记录自动学习；`ScoringParams` 支持 6 个维度参数化覆盖。

**缺陷**:

| # | 缺陷 | 影响 | 改进方向 |
|---|------|------|----------|
| 1 | `economic_logic` 基于关键词字符串匹配 | 不反映真实经济逻辑质量 | 需引入更结构化的概念模型 |
| 2 | 硬门禁失败仅扣分而非阻断 | 模糊了门禁边界 | P1-2 已部分修复（`hard_gate_failed`标记），但 `score` 仍包含硬门禁分 |
| 3 | 三层权重 30/45/25 为经验设定 | 未经过充分校准 | `auto_calibrator` 已有框架，需积累足够样本 |

**判定**: 评分体系已达"维度丰富、结构化、可解释、可校准"的标准。具备向科学评分系统演进的核心基础。31 项指标 + 分层架构 + 可校准参数 + 统计检验构成了完整的科学评分基础设施。

### 2.3 评价（Evaluation / Quality Gate）—— 达成度：★★★★☆

**6 层门禁链路**:

```
Candidate
  → [1] local_prefilter (local_convergence_score + local_quality)
    → [2] expression_validate (BRAIN API pre-check)
      → [3] submit_simulation → poll → fetch_result (官方 metrics)
        → [4] empirical_score.evaluate_quality_gate (BRAIN 硬门禁 + 质量门禁)
          → [5] SubmissionLedger.assess() (账户安全门禁)
            → [6] submit_alpha() (BRAIN API 最终提交)
```

| 层级 | 类型 | 阻断条件 | 与 BRAIN 官方对齐 |
|------|------|----------|-------------------|
| 本地预筛 | 资源节约 | local_convergence_score < 阈值 | — |
| 表达式验证 | 语法有效性 | 字段/算子/括号/嵌套深度 | ✅ BRAIN validate API |
| 实证硬门禁 | BRAIN 官方标准 | sharpe<1.25 / fitness<1.0 / turnover>70% / self_corr≥0.70 / concentration>10% | ✅ 全部来自官方 Alpha Check |
| 质量门禁 | 顾问标准 | turnover>30%(WARNING) / margin<4bps / is_oos<0.5 | ⚠️ 顾问设定，非官方 |
| 安全门禁 | 账户安全 | 日限/运行限/间隔/相似度/重复/风险评估 | ✅ 自主策略 |
| 最终提交 | BRAIN API | submit_alpha() 成功返回 | ✅ BRAIN API |

**优势**:
1. 门禁贯穿全链路，分层阻断
2. `failed_reasons` 结构化输出精确到 `{name} {direction} {target} (actual: {actual})`
3. SELF_CORRELATION 正确实现了 BRAIN 官方例外规则（Sharpe 优势 10% → 豁免）
4. Delay 感知阈值（Delay-0: Sharpe≥2.0 / Delay-1: Sharpe≥1.25）

**判定**: 门禁体系覆盖全面、分层清晰、与 BRAIN 官方标准对齐。具备生产级提交安全控制能力。

### 2.4 迭代（Iteration）—— 达成度：★★★★☆

**迭代回路**:

```
官方回测结果
  → diagnose() 识别 primary_failure
    → IterativeOptimizer 选择突变策略
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

**优势**: 诊断→突变→对比→学习的完整闭环，突变有方向有依据

**关键限制**: 迭代深度受 simulation budget 约束（每轮最多 3 simulation / 20 candidates），导致大量候选无法获得官方反馈。这是系统最根本的资源约束。

**判定**: 迭代闭环完整且有科学依据。诊断引擎将 BRAIN 指标失败映射到具体突变策略，非盲目的随机变异。

### 2.5 收敛（Convergence）—— 达成度：★★★★☆

**收敛检测**:

```
每轮生产 → CycleRecord
  → 滚动窗口 (默认 10 轮)
    ├─ Bootstrap 90% 置信区间 (avg_sharpe)
    ├─ Spearman 秩相关趋势检验
    └─ CI-重叠 stall 检测
      → 连续 5 轮无显著改善
        → 自动切换 Adaptive Profile (7 选 1)
```

**判定**: 收敛检测在统计方法层面已达科学研究标准。Bootstrap + Spearman + CI-重叠的组合远超行业平均水平。

### 2.6 综合判定：系统能否完成目标？

**可以。** 系统在创作 → 估分 → 评价 → 迭代 → 收敛的完整闭环中，每个环节都有坚实的工程实现和科学依据支撑。具体：

| 环节 | 达成度 | 关键证据 |
|------|--------|----------|
| 创作 | ★★★★☆ | 7642 字段/66 算子/16 数据集/三模式生成 |
| 估分 | ★★★★☆ | 31 项三层评分/可校准/可解释/收敛检测 |
| 评价 | ★★★★☆ | 6 层门禁/BRAIN 官方标准全对齐 |
| 迭代 | ★★★★☆ | 诊断→突变→AB 对比→经验更新闭合回路 |
| 收敛 | ★★★★☆ | Bootstrap CI + Spearman + stall + profile switch |

**能否产出高质量 Alpha**：理论上能，实际效果高度依赖：
1. Simulation budget 的充足性（当前每轮最多 3 simulation，是最大瓶颈）
2. 先验评分与实证评分的相关性（auto_calibrator 正在弥合此 gap）

---

## 三、用户关注的三个关键问题专项审查

### 3.1 换手率阈值：70% vs 30%

**审查结论**：系统**没有错误**，但需澄清设计与用户预期的差距。

| 配置项 | 代码值 | 来源 | 用途 | 判定 |
|--------|--------|------|------|------|
| `platform_max_turnover` | **0.70** | BRAIN API Alpha Check: HIGH_TURNOVER if > 70% | 平台硬门禁 —— 超过 70% 提交被拒 | ✅ BRAIN 官方标准 |
| `target_max_turnover` | **0.30** | 顾问质量目标 | 质量门禁 —— 30%-70% 触发 WARNING，提示优化后优先提交 | ✅ 顾问标准 |

**说明**: BRAIN 平台的 HIGH_TURNOVER 硬门禁是 70%（详见 API 文档 Alpha Check 标准）。系统正确实现了双层阈值：
- 70% 是**提交底线**（不可逾越）
- 30% 是**质量目标**（超过 30% 会产生 WARNING 但不阻断，鼓励优化）

如果用户的意图是"将 30% 也设为硬门禁（提交必需满足 turnover ≤ 30%）"，则需要调整代码逻辑：将 `turnover_quality` 从软指标（WARNING 级）改为硬门禁（阻断级）。**但需明确：这与 BRAIN 平台官方标准不同，是用户自定义的强化约束。**

**当前代码状态**（`scoring.py` 第 391-397 行）：
```python
# BRAIN 平台硬门槛: HIGH_TURNOVER if > 70% (0.70) — 合规底线
item("turnover_platform", turnover, "<=", 0.70, ..., 8, is_hard_gate=True),
# 顾问质量目标: Turnover < 30% — 优先提交信号 (WARNING级)
item("turnover_quality", turnover, "<=", 0.30, ..., 6),  # ← 注意：无 is_hard_gate=True
```

### 3.2 字段覆盖：8 字段 vs 7642 字段

**审查结论**：此问题**已修复**。系统已从 8 个硬编码字段扩展至完整的 7642 个官方字段。

| 时间线 | 状态 | 字段数 | 证据 |
|--------|------|--------|------|
| 旧系统（`_archive_before_rebuild`） | 8 个硬编码字段 | ~8 | `DEFAULT_FIELDS` 硬编码 |
| 当前系统（P0 重构后） | 全量官方字段 | 7642 | `data/official_fields.json` → `OfficialDataLoader` |
| 字段池筛选 | Top 50（按 coverage 排序） | 50 | `_max_field_pool_size=50` |

**当前唯一限制**：`_build_official_field_pool()` 对每个数据集取 top 50 字段（按 `coverage × (1 + user_bonus + alpha_bonus)` 排序）。对于字段丰富的数据集（如 model77 有 3256 fields），50 可能偏保守。但这是**有意的抽样**而非覆盖缺失，可配置为更大值。

### 3.3 数据集支持

**审查结论**：此问题**已修复**。系统已完整支持 16 个 BRAIN 官方数据集。

| 组件 | 状态 | 功能 |
|------|------|------|
| `data/official_datasets.json` | ✅ 16 个数据集 | 含 ID、名称、字段数 |
| `DatasetSelector` | ✅ 四种策略 | all / rotate / random / specific |
| `FieldDatasetMapper` | ✅ 双向索引 | dataset → fields 快速查找 |
| `set_market_scope()` | ✅ dataset 参数传递 | 已修复 P1 bug（原缺失 dataset 传递） |
| `Candidate.dataset_id` | ✅ 记录 | 每个候选 Alpha 记录来源数据集 |

**缺失**：BRAIN API 的 `/datasets` 端点未直接调用 —— 数据集列表完全依赖 `data/official_datasets.json`（从 fields 数据提取）。这不影响功能但有数据新鲜度风险。

---

## 四、BRAIN API 流程对齐检查

### 4.1 官方 API 流程覆盖

| API 端点 | 实现方法 | 状态 | 备注 |
|----------|----------|------|------|
| POST /authentication | `authenticate()` | ✅ | Basic + Token 双模式 |
| GET /data-fields | `list_fields()` | ✅ | 分页 + SHA256 缓存 |
| GET /operators | `list_operators()` | ✅ | 同上 |
| GET /users/self/alphas | `list_user_alphas()` | ✅ | 去重 + 云端同步 |
| POST /alphas/{id}/validate | `validate_expression()` | ✅ | 本地预验证后调用 |
| POST /simulations | `submit_simulation()` | ✅ | BrainSettings → API payload |
| GET /simulations/{id} | `poll_simulation()` | ✅ | 状态轮询 |
| GET /simulations/{id}/result | `fetch_result()` | ✅ | metrics 提取 |
| POST /alphas/{id}/check | `check_alpha()` | ✅ | BRAIN 标准 Alpha Check |
| POST /alphas/{id}/submit | `submit_alpha()` | ✅ | mock/demo/test ID 拦截门禁 |
| POST /alphas/correlations/check | **未实现** | ❌ | PROD_CORRELATION 仅本地估算 |
| GET /datasets | **未实现** | ⚠️ | 数据来自本地 JSON |

### 4.2 生产参数溯源

| 参数 | 代码来源 | BRAIN API 定义 | 溯源状态 |
|------|----------|---------------|----------|
| instrumentType | `config.run_config.json` | API settings 参数 | ✅ |
| region | 同上 | API settings 参数 | ✅ |
| universe | 同上 | API settings 参数 | ✅ |
| delay | 同上 | API settings 参数 | ✅ |
| neutralization | 同上 | API settings 参数 | ✅ |
| truncation | 同上 | API settings 参数 | ✅ |
| pasteurization→pasteurize | `BrainSettings.to_platform_dict()` | API 字段名转换 | ✅ |
| unitHandling | 同上 | API settings 参数 | ✅ |
| nanHandling | 同上 | API settings 参数 | ✅ |
| language | 同上 | API settings 参数 | ✅ |
| decay | 同上 | API settings 参数 | ✅ |
| dataset | `DatasetSelector` → `set_market_scope()` | API 查询参数 | ✅ (P1 修复后) |
| type | 同上 | API alpha 类型 | ✅ |

**判定**: 所有生产参数均可追溯至 BRAIN API 文档的明确定义，代码层与"生产要素"相关的逻辑已强制对齐官网规范。

---

## 五、优化方案：清单式逐项攻坚

### 5.1 优化优先级体系

| 优先级 | 定义 | 操作原则 |
|--------|------|----------|
| **P0** | 阻断性缺陷 / 安全漏洞 / 功能无法运行 | 立即修复，不可延期 |
| **P1** | 显著影响产出质量 / API 对齐度 / 用户体验 | 本轮优先处理 |
| **P2** | 提升科学严谨性 / 代码可维护性 / 交互体验 | 后续迭代 |
| **P3** | 锦上添花 / 长远演进 | 视资源安排 |

### 5.2 P0 — 阻断性缺陷（已识别 0 项待修复）

经代码审计确认，已有的 P0 缺陷已全部修复（明文凭据、category 解析、dataset 参数传递）。**当前无新增 P0 缺陷。**

### 5.3 P1 — 重要改进（6 项）

#### P1-1: 换手率阈值策略明确化

**现状**: `platform_max_turnover=0.70`（硬门禁）+ `target_max_turnover=0.30`（WARNING），双层阈值逻辑正确但用户感知为"阈值设置错误"。

**问题**: 用户期望 Turnover ≤ 30% 为提交硬性条件，但当前系统仅将其作为 WARNING 级。

**方案**: 在 `config.run_config.json` 中新增 `turnover_hard_limit` 配置项或复用 `target_max_turnover`，将 30% 也升级为硬门禁（可配置开关）。

**涉及文件**: `config.py`（新增字段）、`scoring.py`（升级 `turnover_quality` 的 `is_hard_gate`）、`run_config.json`（新增配置项）

**风险**: 提高提交门槛会导致更少的 Alpha 能进入提交阶段，但符合用户质量优先的理念。

#### P1-2: Fields/Operators 刷新失败静默忽略修复

**现状**: `_load_official_context()` 中 `OfficialDataLoader.refresh()` 失败时仅在 cycle>=1 场景下产生事件，但 `check_batch` pipeline 中遗漏 fields/operators 同步。

**方案**: 在 `_load_official_context()` 的 refresh 块中，添加明确的重试和告警机制；在 `check_batch` 中添加 fields/operators 同步逻辑。

**涉及文件**: `pipeline.py`（`_load_official_context`）、`brain_api/official.py`（`check_batch`）

#### P1-3: PROD_CORRELATION API 对接

**现状**: `prod_correlation` 仅本地估算，未调用 BRAIN 官方 `/alphas/correlations/check` 端点。

**方案**: 在 `OfficialBrainAPI` 中实现 `check_correlations()` 方法，调用官方端点，替换本地估算。

**涉及文件**: `brain_api/official.py`、`brain_api/base.py`、`scoring.py`

#### P1-4: 硬门禁阻断逻辑强化

**现状**: `empirical_score()` 虽已区分 `hard_gate_failed` 标记，但最终 `score` 仍然包含硬门禁失败的分值。用户期望硬门禁失败应导致 `score=0`。

**方案**: 当 `hard_gate_failed=True` 时，`empirical_score.score` 强制归零；`build_scorecard` 中 `decision_band` 直接返回 "hard_gate_blocked"。

**涉及文件**: `scoring.py`

#### P1-5: 字段池大小动态化

**现状**: `_max_field_pool_size=50` 对所有数据集统一应用。model77 有 3256 字段，50 个仅覆盖 1.5%。

**方案**: 改为按数据集字段总数的百分位动态截断（如 min(100, max(30, len(ds_fields) × 0.05))），或通过配置项 `field_pool_ratio` 控制。

**涉及文件**: `generator.py`、`dataset_selector.py`

#### P1-6: 评分权重校准样本量门禁

**现状**: `auto_calibrator` 在样本不足时仍可能触发校准，产生统计不可靠的权重。

**方案**: 添加最小样本量门禁（如 ≥ 30 条官方 PASS 记录），未达门禁时仍使用经验权重，并在事件中标注 "样本不足，校准推迟"。

**涉及文件**: `auto_calibrator.py`、`pipeline.py`

#### P1-7: 表达式多样性提升（新增 — 基于 checks.jsonl 数据分析）

**现状**: `data/checks.jsonl`（150 条记录）中 **75%+ 的提交前检查**因"与云端已有 Alpha 高自相关性（correlation 0.96-1.00）"被阻断。

**根因**: 当前 10 个表达式骨架（`rank(ts_delta({f1}, {w}) / ts_std(...))` 等）高度趋同，虽然字段/算子有所变化，但表达式结构自身的多样性不足，导致大量产出成为云端已有 alpha 的近重复变体。

**方案**: 
- 增加 DynamicThemeEngine 的骨架模板数量（10→30+），覆盖更多结构模式
- 引入"骨架指纹"去重机制：对生成的表达式做归一化处理后与云端 alpha 做 Jaccard/Levenshtein 预筛选
- 在 checks.jsonl BLOCKED 的候选上触发强制性结构突变（不是简单的 field_swap）

**涉及文件**: `theme_engine.py`、`generator.py`、`pipeline.py`（checks 阻断后的强制突变逻辑）

### 5.4 P2 — 工程与体验改进（5 项）

| # | 改进项 | 涉及文件 | 预期效果 |
|---|--------|----------|----------|
| P2-1 | HTML/CSS/JS 从 Python 字符串拆分到独立文件 | `web.py` | 大幅提升 Web UI 可维护性 |
| P2-2 | WebSocket 推送替代轮询 | `web.py` | 实时更新，接近原生体验 |
| P2-3 | `pipeline.run()` 按阶段进一步分解 | `pipeline.py` | 提升可测试性和可读性 |
| P2-4 | pytest 迁移 | `tests/` | 标准化测试框架 |
| P2-5 | logging 统一（替换 print/logging 混用） | 全局 | 统一日志管理 |

### 5.5 P3 — 长远演进（3 项）

| # | 改进项 | 涉及文件 | 预期效果 |
|---|--------|----------|----------|
| P3-1 | Multi-Armed Bandit 策略切换替代简单轮换 | `pipeline.py` | 更优的 explore-exploit 平衡 |
| P3-2 | 贝叶斯校准替代 Grid Search | `calibrate_weights.py` | 更鲁棒的权重估计 |
| P3-3 | N-alpha 正交化套利组合替代两两融合 | `fusion.py` | 更丰富的 Alpha 多样性 |

---

## 六、用户交互评估

### 6.1 Web 控制台

| 评估项 | 评级 | 详情 |
|--------|------|------|
| 视觉设计 | ★★★★☆ | 配色克制（Teal 主题）、CSS 变量体系、卡片布局 |
| 功能完整度 | ★★★★☆ | 环境切换、启停控制、进度条、Backtest 槽位、候选列表、评分徽章 |
| 交互流畅度 | ★★★☆☆ | setInterval 轮询（非 WebSocket），操作反馈延迟 1-3 秒 |
| 反馈及时性 | ★★★☆☆ | 无实时推送，Pipeline 启停需等待当前周期 |
| 信息架构 | ★★★★☆ | 左控右监经典双栏，仪表盘→监控→候选列表→详情层次清晰 |
| 可维护性 | ★★☆☆☆ | ~500 行 HTML 内联为 Python 字符串，CSS/JS/HTML 混排 |

### 6.2 CLI 交互

| 评估项 | 评级 | 详情 |
|--------|------|------|
| 命令设计 | ★★★☆☆ | `brain-alpha-ops run` + `init-config`，覆盖主流程 |
| 参数覆盖 | ★★★★☆ | --env/--cycles/--candidates/--validations/--simulations/--auto-submit |
| 输出质量 | ★★★☆☆ | JSON 完整但冗长，缺少人类可读的进度摘要 |

### 6.3 改进建议

| 优先级 | 改进项 | 方案 | 预期效果 |
|--------|--------|------|----------|
| P1 | HTML/CSS/JS 拆分 | 独立 `web/` 目录文件，Python 读取后注入 | 维护性从 ★★ 提升至 ★★★★ |
| P2 | WebSocket 推送 | 用 `websockets` 库或 SSE 替代轮询 | 实时更新，操作响应降至 <100ms |
| P2 | 按钮 loading 状态 | 添加 CSS animation + 操作确认弹窗 | 防误操作，心理安全感 |
| P3 | 可视化图表 | 集成 Chart.js CDN（评分趋势、Sharpe 分布） | 替代纯表格展示 |

---

## 七、结论与建议

### 7.1 综合评定

| 指标 | 评分 | 关键证据 |
|------|------|----------|
| 系统能否完成目标 | **是** | 创作→估分→评价→迭代→收敛闭环完整 |
| 能否产出高质量 Alpha | **理论上是，受 simulation budget 约束** | 31 项评分确保筛选精度，auto_calibrator 持续缩小先验-实证 gap |
| 评分体系能否演进为科学评分系统 | **已具备基础，路径清晰** | 多层架构 + 可校准参数 + 统计检验 + A/B 框架 |
| BRAIN API 流程对齐度 | **核心流程 100% 覆盖** | 10/12 端点实现，2 项增强端点待对接 |
| 用户交互是否友好 | **功能足，体验糙** | Web 功能齐全但架构老旧 |

### 7.2 本轮建议优先执行（按序）

1. **P1-1**: 换手率阈值策略明确化 → 消除用户对"70% 应为 30%"的疑虑
2. **P1-2**: Fields/Operators 刷新失败静默忽略修复 → 消除数据同步盲区
3. **P1-4**: 硬门禁阻断逻辑强化 → 提升门禁严谨性
4. **P1-3**: PROD_CORRELATION API 对接 → 完善 API 覆盖
5. **P1-5**: 字段池大小动态化 → 提升字段覆盖度
6. **P1-6**: 评分权重校准样本量门禁 → 确保校准可信度

### 7.3 关键风险提示

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| Simulation budget 不足 | 高 | 大量候选无法获得官方反馈 | 提升先验评分精度，优化本地预筛 |
| 先验-实证相关性低 | 中 | 评分体系失去预测力 | auto_calibrator 持续校准 |
| Fields/Operators 过期 | 中 | 生成表达式可能引用已废弃字段 | 定时刷新 + 版本追踪 |
| 速率限制导致 pipeline 停滞 | 低 | 短期内无法提交 | 自适应退避 + 本地队列缓冲 |

---

## 八、双 Agent 探索补充发现

### 8.1 归档版本 vs 当前版本的架构差异

Explore-2 agent 对比了 `_archive_before_rebuild_20260512_152528/`（2026-05-12 归档）与当前代码库，发现以下**当前版本完全缺失**的关键组件：

| 档案组件 | 档案中存在 | 当前版本 | 评估 |
|----------|-----------|----------|------|
| **LLM 集成模块** (`llm/`) | client.py + parser.py + 6 个 prompt 模板 | ❌ 完全缺失 | 曾规划用 LLM 增强诊断→突变→修复→评分循环 |
| **pyworldquant SDK** | BRAIN 官方 Python SDK v0.0.2 | ❌ 完全缺失 | 官方 API 契约参考丢失 |
| **模块化服务架构** | autonomous_kernel/explainer/gatekeeper/mutator/static_checker | ❌ 合并为 pipeline.py 单体 | 服务拆分回调 |
| **模块化评分** | 7 个独立评分文件 | ⚠️ 合并为 scoring.py | 功能更丰富但模块化回归 |
| **结构化存储** | 4 个独立存储文件 | ⚠️ 合并到 models/repository/safety | 功能未丢失但文件结构简化 |
| **额外测试覆盖** | 13 个文件（含 e2e/policy/project 类） | ⚠️ 缺 e2e/project 类 | 部分覆盖丢失 |

**LLM 模块是最值得关注的发现。** 档案中的 6 个 prompt 模板暗示了曾被规划的方向：用 LLM 增强 `economic_logic` 维度——从"关键词匹配"升级为"语义化经济逻辑理解"。当前系统全部依赖规则引擎。

### 8.2 AlphaCheckRegistry 完整清单（25 checks）

Explore-3 agent 深度探索确认完整 **25 项**检查（远超之前估计的 20+）：

**ERROR 级（阻断 — 8 项）:**
sharpe_positive / fitness_minimum / turnover_platform / self_correlation（含 Sharpe×1.10 例外）/ prod_correlation / weight_concentration / sub_universe_sharpe / expression_valid

**WARNING 级（质量 — 10 项）:** returns_positive / drawdown_limit / turnover_quality / margin_minimum / ic_mean(≥0.02) / ic_ir(≥0.3) / coverage_minimum(≥0.5) / delay_consistent(≥1) / is_oos_robustness(≥0.5) / marginal_contribution(>0)

**INFO 级（记录 — 7 项）:** rank_ic / turnover_stability / drawdown_stability / neutralization_applied / pasteurization_applied / nan_handling / expression_complexity

**类型特定**: POWER_POOL / ATOM / PYRAMID 每类额外 5-6 项。

**判定**: AlphaCheckRegistry 是三份报告中最被低估的亮点——25 项 + 三级分类 + 类型特异性。

### 8.3 修正：完整 8 阶段门禁链路

之前 6 层模型修正为 Explore-3 确认的 **8 阶段**（Stage 2 Scorecard Build 和 Stage 3 Official Context 此前隐含在"本地预筛"中）：

```
S1: Local Prefilter        → S2: Scorecard Build
S3: Official Context       → S4: Pool Management
S5: Expression Validation  → S6: Official Simulation
S7: Quality Gate           → S8: Submission Safety
```

### 8.4 生产数据关键发现

| 数据文件 | 记录数 | 大小 | 关键洞察 |
|----------|--------|------|----------|
| `candidates.jsonl` | 905 | 3.2 MB | 含完整 scorecard（schema v2.1） |
| `cloud_alphas.jsonl` | 12,197 | 42.4 MB | BRAIN 平台同步的真实 Alpha |
| `events.jsonl` | 1,135,415 | 348 MB | 全量 pipeline 事件日志 |
| `lifecycle.jsonl` | 27,295 | 28.7 MB | 每 Alpha 完整生命周期追踪 |
| `checks.jsonl` | 150 | 164 KB | **75%+ 因云端 correlation≥0.96 被阻断** |

**checks.jsonl 暴露了头号问题**：提交前检查中大部分候选因"与云端已有 Alpha 高自相关性（0.96-1.00）"被阻断。说明**表达式多样性不足**——骨架趋同导致大量产出成为云端已有 alpha 的近重复变体。

### 8.5 字段分类统计

| 分类 | 字段数 | 占比 | 代表数据集 |
|------|--------|------|------------|
| model | 3,296 | 43% | model77 (Analysts' Factor Model) |
| fundamental | 1,652 | 22% | fundamental2 + fundamental6 |
| analyst | 1,324 | 17% | analyst4 |
| news | 996 | 13% | news12 + news18 |
| pv | 195 | 3% | pv1 + pv13 |
| option | 138 | 2% | option9 + option8 |
| socialmedia | 22 | — | socialmedia12 + socialmedia8 |
| sentiment | 19 | — | sentiment1 |

---

## 九、修订后的综合结论与新增优化项

### 9.1 档案对比洞察

"当前比档案更强"：字段 8→7642、数据集 0→16、评分 31项+可校准、收敛追踪从无到有。
"档案有而当前缺失"的可恢复项：LLM 集成（P2）、e2e 测试（P2）、SDK 参考（P3）。

### 9.2 新增优化项（基于双 agent 发现）

| # | 来源 | 优先级 | 改进项 | 原因 |
|---|------|--------|--------|------|
| P1-7 | Explore-2 | **P1** | **表达式多样性提升** | checks.jsonl 中 75%+ 因云端 correlation≥0.96 阻断 |
| P2-6 | Explore-3 | P2 | 恢复 LLM 集成模块 | 档案有完整 prompt 模板，增强 economic_logic 语义评分 |
| P2-7 | Explore-2 | P2 | 恢复 e2e/project 类测试 | 归档版本有更完整测试覆盖 |
| P3-4 | Explore-2 | P3 | 恢复 pyworldquant SDK 参考 | 用于 API 契约交叉验证 |
| P3-5 | Explore-3 | P3 | scoring.py 模块化拆分 | 参考档案架构，拆分为 prior/empirical/checklist |

### 9.3 修订后优先级排序（7 项 P1）

1. **P1-1**: 换手率阈值策略明确化
2. **P1-7** (新增): 表达式多样性提升 — checks.jsonl 暴露的头号问题
3. **P1-2**: Fields/Operators 刷新失败静默忽略修复
4. **P1-4**: 硬门禁阻断逻辑强化
5. **P1-3**: PROD_CORRELATION API 对接
6. **P1-5**: 字段池大小动态化
7. **P1-6**: 评分权重校准样本量门禁

---

*报告结束。基于：34 源文件代码审计 + 双 agent 并行探索（Explore-2: data/docs/config/tests + Explore-3: research/brain_api/data 全量）+ 6 份已有文档三角验证 + data/ 全量数据文件核对 + archive 版本对比。*
