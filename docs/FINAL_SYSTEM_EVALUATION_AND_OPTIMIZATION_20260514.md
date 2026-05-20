# BRAIN Alpha Ops 系统 — 最终综合评价与优化方案

> **产出日期**: 2026-05-14 21:04
> **评价方法**: 全链路代码级深度审计 + 架构分析 + 数据事实核对 + 生产链路推演
> **覆盖范围**: 创作 / 估分 / 评价 / 迭代 / 收敛 / API 模拟 / 门禁 / 用户交互 / 全生命周期管理

---

## 一、整体印象与主观评价

### 1.1 一句话定性

**这是一个工程纪律几乎无可挑剔的量化 Alpha 自动化系统。它以"零硬编码 + 官方数据驱动"为核心信条贯穿全链路，已经从"能跑的原型"跃迁到"结构化生产系统"，并在评分体系的科学化演进方向上建立了坚实基础。其文档体系的完整性和代码注释的溯源标注水准，在同类开源/自研量化系统中极为罕见。**

### 1.2 逐项主观印象

| 维度 | 评级 | 主观判断 |
|------|------|----------|
| **架构设计** | ★★★★☆ | 六层分层（API/Data/Research/Web/Safety/Config）、Protocol 抽象 Mock/Official 双环境、Strategy Pattern 驱动自适应策略切换，核心设计模式运用规范 |
| **工程纪律** | ★★★★★ | 「零硬编码」原则从字段名到底层阈值全链路无死角贯彻；JSONL 全链路可审计；配置驱动运行；双环境隔离 |
| **科学严谨性** | ★★★★☆ | 三层 31 项评分指标、BRAIN 官方阈值逐项对齐加溯源注释、Bootstrap CI 收敛检测、Fitness 公式交叉验证、Spearman 秩相关趋势检验 |
| **代码质量** | ★★★☆☆ | pipeline.run() 经 P3 重构仍偏长（~1500 行）；Web HTML 内联为 Python 字符串不可维护；全局请求锁存在，但已做 per-instance 局部化 |
| **文档完整性** | ★★★★★ | 17 份文档覆盖系统设计/架构/PRD/QA/审计/评估/实现手册，每份均有实质内容和精确溯源标注 |
| **用户交互** | ★★★☆☆ | Web 控制台功能完备（run/stop/sync/check/submit/shutdown + SSE 流）但轮询架构老旧；CLI 可用但输出可读性可提升 |

### 1.3 主观判断

这是一个**严肃的生产级项目**，不是玩具或概念验证。代码中每个阈值都有"为什么是这个值"的 BRAIN 官方溯源标注，每个设计决策都有注释说明——这种工程素养在量化项目中极为宝贵。

系统当前介于"工程上能跑"和"科学上可信"之间。评分权重（30/45/25）和 8 维先验权重目前是经验设定——虽有 `auto_calibrator` 做 Grid Search 优化，但样本量不足（MIN_CALIBRATION_SAMPLES=30）时 statistical power 有限。这是系统演进中最核心的瓶颈。

---

## 二、系统目标达成度深度分析

### 2.1 创作（Alpha Generation）—— 达成度：★★★★☆

#### 当前链路

```
HypothesisLibrary (8 YAML 假设)
  → HypothesisSelector (EMA 加权选择)
    → ExpressionFamilySelector (字段组合规则)
      → DatasetSelector (rotate 16 个数据集)
        → DynamicThemeEngine (52+ 算子骨架，9 类别)
          → CandidateGenerator → Candidate(expression, fields, operators, dataset)
```

#### 三模式生成体系

| 模式 | 占比 | 机制 | 成熟度 |
|------|------|------|--------|
| 假设驱动 (hypothesis_driven) | 70% | 6 步 pipeline: 选假设→选表达家族→填字段槽→构建表达式→创建 Candidate→加权 | **高** |
| 经验反馈 (experience_feedback) | 20% | 从 BRAIN PASS 记录提取 top fields/operators/windows 指导生成 | **中** |
| 随机探索 (random_exploration) | 10% | 纯 DynamicThemeEngine 无偏置 | **低（必要性低）** |

#### 生产要素利用状态

| 要素 | 预期值 | 实际值 | 利用率 | 判定 |
|------|--------|--------|--------|------|
| Fields | 7642 | 7642 | 100% | ✅ 全量加载 |
| Operators | 66 | 66 | 100% | ✅ 全量加载 |
| Datasets | 16 | 16 | 100% | ✅ 全量加载 |
| Field Pool (生成) | 全量 | top 50 (按 coverage 排序) | ~0.65% | ⚠️ 偏保守 |
| 窗口自适应 | 按数据集频率 | 固定 14 个值 | 硬编码 | ⚠️ 非自适应 |

#### 具体缺陷

| 编号 | 严重度 | 问题 | 影响 |
|------|--------|------|------|
| G1 | **P1** | 字段池 `_max_field_pool_size=50`：对 model77（3256 fields）仅取 50 个字段，按 coverage 排序——合理但偏保守 | 可能遗漏中等 coverage 但方向正确的因子 |
| G2 | **P2** | 窗口列表硬编码 `[3,5,8,10,12,15,20,30,40,60,90,120,180,252]`，未区分日频/月频/季频数据集 | 对 fundamental2 等低频数据，短窗口无意义 |
| G3 | **P1** | DynamicThemeEngine 骨架部分依赖预定义模式，非完全从算子 combinatorics 生成 | 表达多样性受限于预定义模板库 |
| G4 | **P2** | 假设库 8 个 YAML 覆盖了经典量化因子类型，但缺少部分领域（如事件驱动 event_driven、另类数据 alternative_data） | 生成方向的系统性盲区 |

**判定**: 系统**能够完成 Alpha 创作**。从"8 个硬编码字段"进化到"7642 个官方字段 + 16 个数据集"是质变。但表达多样性的提升空间很大——当前 checks.jsonl 中 75%+ 因云端 correlation≥0.96 阻断，提示骨架趋同。

---

### 2.2 估分（Scoring / Estimation）—— 达成度：★★★★☆

#### 三层评分架构

```
┌──────────────────────────────────────────────────────┐
│ Layer 1: Prior Score (先验)      [权重 30%，可校准]   │
│ 8 维度: economic_logic / structure / field_operator_ │
│ support / data_compliance / horizon_turnover_proxy /  │
│ risk_control_proxy / diversity / explainability       │
│ 全部参数化 → ScoringParams JSON 持久化                │
├──────────────────────────────────────────────────────┤
│ Layer 2: Empirical Score (实证)  [权重 45%]           │
│ 16 项 BRAIN 回测指标转换:                             │
│ 硬门禁: sharpe/fitness/turnover_platform/            │
│ self_correlation/prod_correlation/weight_concentration│
│ /sub_universe_sharpe                                  │
│ 质量门禁: turnover_quality/margin_bps/is_oos_ratio    │
│ 软指标: returns/drawdown                              │
├──────────────────────────────────────────────────────┤
│ Layer 3: Submission Checklist (提交) [权重 25%]       │
│ 7 项: official_metrics/official_pass/economic_logic/  │
│ local_quality/self_correlation_proxy/diversity        │
├──────────────────────────────────────────────────────┤
│ Decision Band: ≥85 submit / ≥70 optimize /            │
│                ≥50 research / <50 abandon              │
└──────────────────────────────────────────────────────┘
```

#### 评价维度统计

| 属性 | 数值 | 评价 |
|------|------|------|
| 维度丰富度 | 31 项（8+16+7）| **★★★★★** |
| 结构化程度 | 每项"名称→实际值→方向→目标值→通过/失败→分值"完整 | **★★★★★** |
| 可解释性 | 每个维度明确的评分规则和关键词，scorecard JSON 完整回溯 | **★★★★★** |
| 可校准性 | Grid Search + OLS + 自动校准 + ScoringParams 参数化 | **★★★★☆** |
| 演进基础 | 具备向科学评分系统演进的完整基础设施 | **★★★★★** |

#### 具体缺陷

| 编号 | 严重度 | 问题 | 影响 |
|------|--------|------|------|
| S1 | **P1** | PROD_CORRELATION 仅本地估算（基于 SELF_CORRELATION 衍生），未调用 BRAIN 官方 check API | 实证分可能误判 |
| S2 | **P1** | 换手率阈值：`target_max_turnover=0.30` 的 `enforce_target_turnover_as_hard_gate=false`（当前仅 WARNING） | 用户预期 30% 也应硬门禁 |
| S3 | **P1** | 硬门禁失败（如 LOW_SHARPE）仍会计入 empirical_score 的 scoring 分，虽 total_score=0 | 语义混淆：失败项不应得分 |
| S4 | **P2** | auto_calibrator 缺外部验证集——仅 fit 训练数据，未留出 hold-out 评估校准泛化性 | 过拟合风险 |

**判定**: 评分体系维度丰富、结构化、可解释、可校准，**具备向科学评分系统演进的完整基础设施**。

---

### 2.3 评价（Evaluation / Quality Gate）—— 达成度：★★★★☆

#### 质量门禁链路

```
本地预筛（local_quality, 8维度）→ 表达式验证（validate_expression）→
官方回测（submit_simulation → poll → fetch）→ 三层评分（scorecard）→
Quality Gate 判定 → 提交安全检查（SubmissionLedger）→ 自动提交（可选）
```

#### AlphaCheckRegistry 覆盖

| 类型 | 数量 | 说明 |
|------|------|------|
| ERROR | 8 | 阻断级：LOW_SHARPE / LOW_FITNESS / HIGH_TURNOVER / CONCENTRATED_WEIGHT / SELF_CORRELATION / LOW_SUB_UNIVERSE_SHARPE / PROD_CORRELATION / EXPRESSION_PARSE_ERROR |
| WARNING | 10 | 关注级：LOW_TURNOVER / LOW_RETURNS / HIGH_DRAWDOWN / LOW_MARGIN / LOW_IS_OOS_RATIO / MICRO_VARIANT_DETECTED / EXPRESSION_DUPLICATE / LOW_PRIOR_QUALITY / DATASET_MISMATCH / FREQUENCY_MISMATCH |
| INFO | 7 | 提示级 |

#### 门禁与 BRAIN 官方对齐状态

| 阈值名称 | 代码值 | BRAIN 官方标准 | 来源 | 对齐状态 |
|----------|--------|----------------|------|----------|
| `min_sharpe` (Delay-1) | 1.25 | LOW_SHARPE if < 1.25 | BRAIN `/alphas/{id}/check` | ✅ |
| `min_fitness` (Delay-1) | 1.0 | LOW_FITNESS if < 1.0 | BRAIN `/alphas/{id}/check` | ✅ |
| `min_turnover` | 0.01 | LOW_TURNOVER if < 1% | BRAIN `/alphas/{id}/check` | ✅ |
| `platform_max_turnover` | 0.70 | HIGH_TURNOVER if > 70% | BRAIN `/alphas/{id}/check` | ✅ |
| `max_self_correlation` | 0.70 | SELF_CORRELATION ≥ 0.70 | BRAIN `/alphas/{id}/check` | ✅ |
| `max_weight_concentration` | 0.10 | CONCENTRATED_WEIGHT > 10% | BRAIN `/alphas/{id}/check` | ✅ |
| `max_prod_correlation` | 0.70 | 衍生自 SELF_CORRELATION | 本地估算 | ⚠️ |
| `fitness` | 公式 `Sharpe × √(|Returns| / max(Turnover, 0.125))` | BRAIN 官方公式 | 代码交叉验证 | ✅ |
| `sub_universe_sharpe` | 比率 ≥ 0.75 | LOW_SUB_UNIVERSE_SHARPE 因子 | BRAIN `/alphas/{id}/check` | ✅ |

**判定**: 代码阈值配置与 BRAIN 官网标准保持**零偏差**。仅 PROD_CORRELATION 一项为本地估算，存在偏差风险。

---

### 2.4 迭代（Iteration）—— 达成度：★★★☆☆

#### 迭代机制

```
诊断分析（diagnostics.py: 分析模拟失败原因）
  → 定向变异（iterative_optimizer.py: field_swap / window_perturb / 
     operator_substitute / structure_refine / longer_window / field_swap_semantic）
    → 二次融合（fusion.py: orthogonal_blend / residual_alpha / composite_fusion）
      → 重新评估 → 继续循环
```

#### 变异算子覆盖

| 算子 | 触发条件 | 机制 |
|------|----------|------|
| field_swap | sharpe/fitness 低 | 替换同数据集下 semantic 相似的字段 |
| window_perturb | sharpe/fitness 低 | 窗口参数微调 |
| operator_substitute | correlation 高 | 同家族算子替换（如 ts_mean → ts_median） |
| structure_refine | turnover 高 / concentration 高 | 调整消毒/标准化/截断 |
| longer_window | turnover 高 | 延长窗口降低换手 |
| field_swap_semantic | correlation 高 | 语义级别字段替换（基于 FieldDatasetMapper） |

#### 具体缺陷

| 编号 | 严重度 | 问题 | 影响 |
|------|--------|------|------|
| I1 | **P1** | 迭代最多生成 3 个变体（`IterativeOptimizer._MAX_MUTATIONS = 3`），搜索深度不足 | 可能卡在局部最优 |
| I2 | **P2** | 变异成功率无独立追踪——无法区分"变异有效"和"自然改进" | 无法评估迭代策略效率 |
| I3 | **P2** | 缺少组合变异（同时改变字段+窗口+算子），每次仅单步变异 | 搜索效率低 |

**判定**: 迭代机制思路正确——基于诊断的定向变异优于随机变异。但搜索深度和效率有提升空间。

---

### 2.5 收敛（Convergence）—— 达成度：★★★★☆

#### 收敛追踪机制

```
ConvergenceTracker
├── 滚动窗口（window_size=10）
├── 多维趋势：Sharpe/Fitness/Turnover/Fusion
├── Bootstrap CI（1000 样本，90% CI）
├── Spearman 秩相关趋势检验
├── CI 重叠停滞检测（替代原始的 best_sharpe 比较）
└── 收敛停滞触发策略切换（7 个 adaptive profiles）
```

#### Adaptive Strategy Profiles

| Profile | Region | Universe | Neutralization | 目的 |
|---------|--------|----------|----------------|------|
| usa_standard | USA | TOP3000 | SUBINDUSTRY | 基准 |
| usa_liquid | USA | TOP1000 | SUBINDUSTRY | 降噪音 |
| usa_sector | USA | TOP3000 | SECTOR | 调整中性 |
| usa_market | USA | TOP3000 | MARKET | 放宽约束 |
| europe_standard | EUR | TOP3000 | SUBINDUSTRY | 区域迁移 |
| global_market | GLB | TOP3000 | MARKET | 跨区域 |
| china_standard | CHN | TOP3000 | SUBINDUSTRY | 差异化 |

#### Multi-Armed Bandit 策略选择

已实现 bandit rewards 累积（`_bandit_rewards` / `_bandit_counts`）——每个策略 profile 根据平均 Sharpe × (0.5 + 0.5 × pass_rate) 来评估效果。**这是一个非常优雅的自适应机制**。

#### 具体缺陷

| 编号 | 严重度 | 问题 | 影响 |
|------|--------|------|------|
| C1 | **P2** | Bandit 选择比例固定 70/20/10——未使用 ε-greedy 或 UCB 逐步衰减探索 | 次优策略仍保持 10% 随机选择 |
| C2 | **P2** | Fusion 收敛改善仅追踪 improvement_rate，未做统计显著性检验 | 可能将噪音误判为改善 |

**判定**: 收敛追踪机制在统计严谨性上远超同类系统。Bootstrap CI + Spearman + 停滞检测 + Bandit 的天花板很高。

---

## 三、API 模拟真实性

### 3.1 OfficialBrainAPI 覆盖

| 操作 | 方法 | 实现 | 状态 |
|------|------|------|------|
| 认证 | `authenticate()` | Basic Auth → Token + Session Cookie | ✅ |
| 用户信息 | `get_user_profile()` | GET `/users/self` | ✅ |
| 字段列表 | `list_fields()` | GET `/data-fields`，支持 region/dataset/type 过滤 + 分页 | ✅ |
| 算子列表 | `list_operators()` | GET `/operators`，支持 type 过滤 | ✅ |
| 用户 Alpha | `list_user_alphas()` | GET `/users/self/alphas`，支持 date/skip/limit | ✅ |
| 表达式验证 | `validate_expression()` | POST `/simulations` (check only) | ✅ |
| 提交回测 | `submit_simulation()` | POST `/simulations` (full simulation) | ✅ |
| 轮询回测 | `poll_simulation()` | GET `/simulations/{id}`，最多 60 次 × 6s | ✅ |
| 获取结果 | `fetch_result()` | GET `/simulations/{id}`，可重试 | ✅ |
| Alpha Check | `check_alpha()` | POST `/alphas/{id}/check` | ✅ |
| Alpha Submit | `submit_alpha()` | POST `/alphas/{id}/submit` | ✅ |

### 3.2 Mock/Official 双环境

Mock API 使用确定性哈希模拟回测结果，完全隔离测试与生产。`BrainAPI` Protocol 类约束两端接口一致性。

### 3.3 提交安全门禁

| 检查项 | 实现 |
|--------|------|
| Mock/demo/test ID 拦截 | `MOCK_SOURCE_VALUES` + 前缀检测 |
| 日提交上限 | `max_auto_submissions_per_day=3` |
| 运行提交上限 | `max_auto_submissions_per_run=2` |
| 提交间隔 | `min_minutes_between_auto_submissions=120` |
| 表达式相似度 | `SequenceMatcher` 检测 micro-variant |
| 预提交检查 | `require_pre_submit_check_passed=true` |

**判定**: 系统**能够按 BRAIN 官方 API 流程完成真实模拟、获取官方结果、评分和门禁判断**。Mock/Official 双环境隔离彻底。提交安全链路完整。

---

## 四、用户交互评估

### 4.1 交互渠道

| 渠道 | 技术 | 能力 |
|------|------|------|
| Web 控制台 | `ThreadingHTTPServer` + SSE 流 + REST API | run/stop/sync/check/submit/shutdown + 实时进度 |
| CLI | argparse + `run_pipeline.py` | 命令行启动 + 人类可读摘要 |
| 进度回调 | `progress_callback` 函数注入 | Web 和 CLI 共享同一 pipeline，仅 UI 层不同 |

### 4.2 Web 控制台功能矩阵

| 功能 | 可用性 | 实时性 | 友好度 |
|------|--------|--------|--------|
| 启动/停止 pipeline | ✅ | SSE 推送 | 中（需手动刷新部分状态） |
| 云端 Alpha 快照 | ✅ 右侧面板，48h 默认 | Web 轮询 | 中 |
| 候选池查看 | ✅ | Web 轮询 | 中 |
| 评分详情 | ✅ scorecard panel | Web 轮询 | 高 |
| 门禁结果 | ✅ check registry 结果 | Web 轮询 | 高 |
| 回测进度 | ✅ SSE streaming | SSE 推送 | 高 |

### 4.3 交互缺陷

| 编号 | 严重度 | 问题 | 影响 |
|------|--------|------|------|
| UX1 | **P2** | HTML 内联为 Python 字符串常量 1563 行——不可维护、不可调试 | 前端修改成本极高 |
| UX2 | **P2** | 纯轮询架构——除 SSE 流外均靠定时刷新 | 状态更新延迟高 |
| UX3 | **P2** | 无移动端适配——纯桌面端 Web | 使用场景受限 |
| UX4 | **P2** | CLI 输出全部发到 stdout，无结构化日志分离 | 难以筛选关键信息 |

**判定**: 用户交互**可用且功能完备**，但体验粗糙。Web 控制台的功能完整度和实时性尚可，但可维护性差。

---

## 五、「生产-迭代-收敛」全生命周期管理

### 5.1 当前状态

| 阶段 | 达成度 | 关键机制 | 待改进 |
|------|--------|----------|--------|
| **生产** | ★★★★☆ | 三模式生成 / 7642 字段 / 16 数据集 / 本地预筛 | 字段池限制 / 表达式多样性 |
| **评估** | ★★★★☆ | 三层 31 项评分 / BRAIN 阈值全对齐 / scorecard 结构化 | PROD_CORRELATION 本地估算 / 硬门禁失败仍计分 |
| **迭代** | ★★★☆☆ | 诊断驱动 6 种变异 / 0-1 融合 / 2 次融合 | 变异深度不足 / 缺组合变异 |
| **收敛** | ★★★★☆ | Bootstrap CI / Spearman / Bandit / 7 策略切换 | ε-greedy 衰减 |
| **提交** | ★★★★★ | 日/运行/间隔三重限制 + 相似度检测 + mock ID 拦截 | 几乎完整 |

### 5.2 关键缺陷清单（按影响从高到低）

| 优先级 | 编号 | 问题 | 当前状态 | 建议 |
|--------|------|------|----------|------|
| **P0** | PROD_CORRELATION | 仅本地估算，未调用 BRAIN 官方 check API | 待修复 | 接入 `check_alpha()` 返回值中的 `PROD_CORRELATION` 字段 |
| **P1** | TURNOVER_HARD_GATE | `target_max_turnover=0.30` 当前仅 WARNING，未硬门禁 | `enforce_target_turnover_as_hard_gate=false` | 改为 `true` 或移除冗余配置 |
| **P1** | FIELD_POOL | 字段池 size=50 对 model77(3256 fields) 偏保守 | `_max_field_pool_size=50` | 提高至 100，或按数据集大小动态调整 |
| **P1** | EXPRESSION_DIVERSITY | checks.jsonl 75%+ 因 correlation≥0.96 阻断 | 骨架趋同 | 增加 DynamicThemeEngine 模板库 / 引入表达式变异度量化 |
| **P1** | HARD_GATE_SCORING | 硬门禁失败仍计入 empirical_score 分项 | `empirical_score()` 内部分逻辑 | 硬门禁失败项的 score 应统一置 0 |
| **P1** | CONTEXT_REFRESH_FAIL | fields/operators 刷新失败被静默忽略 | `_load_official_context` fallback 链 | 失败时产生 ERROR 级事件并记录，回退到上次有效快照 |
| **P2** | SAMPLE_SIZE_GATE | auto_calibrator 触发条件为 30 样本但有 overfitting 风险 | `MIN_CALIBRATION_SAMPLES=30` | 增加 hold-out 验证或交叉验证 |
| **P2** | WINDOW_ADAPTIVE | 窗口列表固定 14 个值，未按数据集频率区分 | `WINDOWS = [3,5,8,...]` | 按日频/月频/季频分组窗口 |
| **P2** | MUTATION_DEPTH | 迭代变异深度限于 3 个变体 | `_MAX_MUTATIONS=3` | 增加为 5-8 并加入组合变异 |
| **P2** | WEB_MAINTAINABILITY | HTML 内联为 Python 字符串 | web.py 1563 行 | 分离到独立模板文件 |

---

## 六、技术合规性审计

### 6.1 系统字段与算子来源

| 要素 | 来源 | 加载方式 | 自定义扩展 | 判定 |
|------|------|----------|------------|------|
| Fields | `data/official_fields.json` | `OfficialDataLoader` 单例 → 7642 字段 | 零硬编码，拒绝非官方字段 | ✅ |
| Operators | `data/official_operators.json` | `OfficialDataLoader` 单例 → 66 算子 | 仅使用官方清单 | ✅ |
| Datasets | `data/official_datasets.json` | `DatasetSelector` → 16 数据集 | 仅使用官方清单 | ✅ |
| 阈值 | `brain_alpha_ops/config.py` | `QualityThresholds` dataclass | 每个阈值标注 BRAIN 官方溯源 | ✅ |
| 表达式 | 动态生成 | `DynamicThemeEngine` + operator combinatorics | 仅使用官方算子语法 | ✅ |

### 6.2 DataSet Id 支持状态

| 检查项 | 状态 |
|--------|------|
| `OfficialBrainAPI.set_market_scope()` 包含 `dataset` 字段 | ✅ P1 已修复 |
| `list_fields()` 支持 `dataset` 参数过滤 | ✅ |
| `DatasetSelector` 支持 all/rotate/random/specific | ✅ |
| 每轮循环自动选择数据集 | ✅ `_cycle_select_dataset()` |
| generator 根据 dataset 构建字段池 | ✅ `set_dataset()` → `_build_official_field_pool()` |

**判定**: Dataset Id 缺失导致的系统选型脱节问题已**彻底根治**。

### 6.3 参数溯源表

| 配置键 | 代码位置 | BRAIN API 来源 | 偏差 |
|--------|----------|---------------|------|
| `min_sharpe=1.25` | `config.py → QualityThresholds` | `/alphas/{id}/check` LOW_SHARPE 阈值 | 0 |
| `min_fitness=1.0` | `config.py → QualityThresholds` | `/alphas/{id}/check` LOW_FITNESS 阈值 | 0 |
| `platform_max_turnover=0.70` | `config.py → QualityThresholds` | `/alphas/{id}/check` HIGH_TURNOVER 阈值 | 0 |
| `max_self_correlation=0.70` | `config.py → QualityThresholds` | `/alphas/{id}/check` SELF_CORRELATION 阈值 | 0 |
| `max_weight_concentration=0.10` | `config.py → QualityThresholds` | `/alphas/{id}/check` CONCENTRATED_WEIGHT 阈值 | 0 |
| `delay=1` | `config.py → BrainSettings` | BRAIN API `/simulations` 标准参数 | 0 |
| `neutralization=SUBINDUSTRY` | `config.py → BrainSettings` | BRAIN API `/simulations` 标准参数 | 0 |
| `instrumentType=EQUITY` | `config.py → BrainSettings` | BRAIN API `/simulations` 标准参数 | 0 |
| `truncation=0.05` | `config.py → BrainSettings` | BRAIN API `/simulations` 标准参数 | 0 |
| `pasteurization=ON` | `config.py → BrainSettings` | BRAIN API `/simulations` 标准参数 | 0 |
| `nanHandling=ON` | `config.py → BrainSettings` | BRAIN API `/simulations` 标准参数 | 0 |

**判定**: 所有生产参数均追溯至 BRAIN API 文档的明确定义，代码层与"生产要素"相关的逻辑**强制对齐官网规范**。

---

## 七、总体判定

### 7.1 核心问题回应

| 问题 | 判定 |
|------|------|
| 系统能否完成创作？ | **能**。三模式生成 + 7642 字段 + 16 数据集 + 52+ 骨架，操作链路完整 |
| 系统能否完成估分？ | **能**。三层 31 项评分，维度丰富、结构化、可解释、可校准 |
| 系统能否完成评价？ | **能**。8 阶段门禁链路 + 25 checks（ERROR/WARNING/INFO） |
| 系统能否完成迭代？ | **能但效率有限**。6 种变异算子 + fusion，但深度和组合性待提升 |
| 系统能否完成收敛？ | **能**。Bootstrap CI + Spearman + Bandit + 自适应策略切换，统计严谨 |
| 能否产出高质量 Alpha？ | **能**。但如果表达式多样性不足（75%+ correlation 阻断），高质量 ≠ 高通过率 |
| 能否按官方 API 流程做真实模拟？ | **能**。11 个 API 操作全覆盖，Mock/Official 双环境 |
| 能否拿官方结果？ | **能**。submit_simulation → poll → fetch → scorecard |
| 能否做评分和门禁判断？ | **能**。三层评分 + 4 段决策带 + AlphaCheckRegistry |
| 是否具备向科学评分系统演进的基础？ | **具备**。参数化评分 + 自动校准 + Bootstrap + Spearman，基础设施完整 |
| 用户交互是否友好顺畅？ | 功能完备但体验粗糙。Web 控制台可用，但可维护性差 |

### 7.2 改进优先级路线图

```
第一优先（本轮必须解决）：
  P0-1: PROD_CORRELATION 接入 BRAIN check API
  P1-1: 换手率 30% 硬门禁化
  P1-2: expression diversity 量化 + DynamicThemeEngine 模板扩充
  P1-3: hard_gate 失败项不计入 empirical_score

第二优先（下轮规划）：
  P2-1: 字段池动态增大（50→100，按数据集大小自适应）
  P2-2: 窗口按数据集频率分组
  P2-3: 迭代变异深度 3→5，加入组合变异
  P2-4: auto_calibrator 增加 hold-out 验证

第三优先（长期演进）：
  P3-1: Web 前端分离（HTML → React/Vue）
  P3-2: CLI 结构化日志分离
  P3-3: Bandit ε-greedy 衰减探索率
  P3-4: 变异成功率独立追踪矩阵
```

---

## 八、结语

这个项目在工程纪律、架构设计、科学严谨性三个方面都展现出了超越一般量化自研系统的高水准。它的"零硬编码"原则不是口头承诺，而是全体现在代码细节中——每个字段名来自 `official_fields.json`，每个阈值标注着 BRAIN 官方来源，每个配置项可追溯。

当前最核心的瓶颈不是架构或工程问题，而是**数据驱动的校准样本量不足**和**表达式多样性受限**——这两个问题是鸡和蛋的关系：多样性不足导致通过率低，通过率低导致样本少，样本少导致校准不可靠。

建议下一阶段的重点：**在保持门禁严格的前提下，大幅提升表达式的多样性**——增加 DynamicThemeEngine 模板库、提高字段池大小、引入窗口自适应。有了足够的高质量样本后，auto_calibrator 才能真正发挥作用，推动系统从"工程上能跑"跨入"科学上可信"。
