# WorldQuant BRAIN Alpha 项目综合评估报告

**评估时间**: 2026-05-14
**评估范围**: 全链路 — 架构、生产、评分、评价、迭代、收敛、API 模拟、门禁系统
**前提**: 基于代码事实、官方 BRAIN API 文档阈值、已有审计记录的三角验证

---

## 一、整体印象与主观评价

### 1.1 一句话定性

一个**工程基因扎实、安全意识前置、官方阈值对齐严格、但量化科学性尚在过渡期**的 Alpha 半自动化生产系统。

### 1.2 架构印象

| 维度 | 评分 | 评语 |
|------|------|------|
| 模块化 | ★★★★★ | API 适配器 / 数据加载 / 生成 / 评分 / 安全 / Web 六层清晰分离，无循环依赖 |
| 配置化 | ★★★★★ | `run_config.json` 驱动全链路，dataclass 分层，CLI/Web 共用同一 runner |
| 安全设计 | ★★★★★ | 凭据仅环境变量、提交前 7 层门禁（日限/运行限/间隔/相似度/重复/微变体/预检）、Mock ID 拦截 |
| 官方对齐 | ★★★★☆ | 阈值逐条标注 BRAIN 来源，Fitness 公式可交叉验证，Delay-0/1 区分正确 |
| 数据覆盖 | ★★★☆☆ | production 模式依赖 `official_*.json`，Mock 模式仅 18 个硬编码字段 |
| 可观测性 | ★★★★☆ | JSONL 审计轨迹（candidate/event/lifecycle/check）、Web 控制台、ConvergenceTracker |
| 迭代闭环 | ★★★☆☆ | 诊断引擎 + 经验反馈 + 自适应策略切换，但"科学收敛"的证据链不完整 |

### 1.3 主观判断

这是一个**严肃的生产级项目**，不是玩具或概念验证。代码风格一致、注释规范、无魔法数字、每个阈值都有"为什么是这个值"的标注。项目的核心信念——"不刷量、只提交经过多层门禁的高质量 Alpha"——是正确的。

但客观来说，它目前**介于"工程上能跑"和"科学上可信"之间**。因为"科学上可信"需要的不仅是阈值对齐，而是：可重复的实验设计、可归因的失败分析、可量化的改进效果、以及最终产出的 Alpha 在真实世界中有统计显著的跟踪记录。

---

## 二、目标达成度分析：创建 → 估分 → 评价 → 迭代 → 收敛 → 高质量 Alpha

### 2.1 创建（Alpha Generation）

<table>
<tr><th>能力</th><th>状态</th><th>证据</th></tr>
<tr><td>基于官方字段/算子生成</td><td>✅ 达成</td><td><code>HypothesisDrivenGenerator</code> 6 步流水线（选假设→选家族→选字段→适配上下文→构建表达式→封装 Candidate）</td></tr>
<tr><td>多数据集支持</td><td>✅ 达成</td><td><code>DatasetSelector</code> 支持 rotate/all/random/specific 四种策略，<code>FieldDatasetMapper</code> 双向索引</td></tr>
<tr><td>三模式生成</td><td>✅ 达成</td><td>假设驱动(70%) / 经验反馈(20%) / 随机探索(10%)，可配置比例</td></tr>
<tr><td>动态模板</td><td>✅ 达成</td><td><code>DynamicThemeEngine</code> 基于官方算子自动构建 skeleton，零硬编码模板</td></tr>
<tr><td>数据集缺失时的降级</td><td>✅ 达成</td><td>DatasetSelector→loader fallback→skip cycle→break pipeline，四级降级策略</td></tr>
<tr><td>表达式超长/超深预警</td><td>✅ 达成</td><td><code>validate_expression()</code> 检测嵌套深度>6、算子>8、长度>250</td></tr>
<tr><td>Hypothesis Library</td><td>⚠️ 部分</td><td>框架完整（Library/Hypothesis/ExpressionFamily/FieldCategoryDef/Rationale），但 JSON 库内容质量未知</td></tr>
</table>

**评价**: 创建链路在工程层面完整。但 Alpha 的"质量"严重依赖 Hypothesis Library 的内容质量和 ExpressionFamily 的 skeleton 设计的有效性——这目前是外部知识注入，非系统内生。

### 2.2 估分（Scoring）

Scoring 系统是三层加权结构：

```
有官方指标时: total = 0.30 × prior + 0.45 × empirical + 0.25 × checklist
无官方指标时: total = local_rank = 0.65 × prior + 0.35 × local_quality
```

| 评分层 | 维度数 | 数据源 | 科学性评估 |
|--------|--------|--------|------------|
| **Prior Score**（先验评分） | 8 维 | 表达式结构分析 | ⚠️ 启发式权重，非统计校准 |
| **Empirical Score**（实证评分） | 17 项 | BRAIN 官方模拟结果 | ✅ 基于真实 API 数据 |
| **Submission Checklist** | 7 项 | 元数据检查 | ✅ 逻辑门禁 |
| **Scorecard v2.1** | 综合 | 三层加权 | ⚠️ 权重 30/45/25 为经验设定 |

**Prior Score 维度明细**:

| 维度 | 权重 | 评分逻辑 | 问题 |
|------|------|----------|------|
| economic_logic | 0.18 | hypothesis 长度≥40 → 85，否则 45 | 粗糙的二值化，不反映经济逻辑质量 |
| structure | 0.14 | 90 - max(0, 算子数-4)×8 | 合理但线性衰减过于简单 |
| field_operator_support | 0.16 | 42 + 字段数×8 + 唯一算子数×4 | 机械累加，不考虑字段间的互补/冗余 |
| data_compliance | 0.12 | 有字段→82，无→35 | 过于二值化 |
| horizon_turnover_proxy | 0.14 | 窗口 5-90→82，有窗口→68，无→50 | 忽略了窗口频率匹配 |
| risk_control_proxy | 0.14 | 三项齐备→84，两项→66，一项→48 | 方向正确但未考虑风险控制的"质量" |
| diversity | 0.07 | Liquidity/Volatility/Hybrid→80，其他→65 | family 来源于模板，非真实多样性 |
| explainability | 0.05 | 长度<140→85，否则 60 | 长度≠可解释性 |

**核心问题**:

1. **Prior Score 权重（0.30）未经校准**: 没有历史数据表明 prior_score 与最终官方 Sharpe 之间的相关系数
2. **三层权重（30/45/25）是经验设定**: 没有 A/B 测试或回测数据支撑这组权重确实优于其他配比
3. **Empirical Score 的 17 项检查** 各自得分简单相加，未考虑指标间的相关性（如 Sharpe 和 Fitness 高度相关）
4. **Calibration 字段存在但未激活**: `scorecard.calibration.prior_minus_empirical` 和 `sample_weight` 被记录，但没有任何代码消费这些数据来**自动调整权重**

### 2.3 评价（Evaluation + Gate）

Gating 系统分两层：

**A. AlphaCheckRegistry（20+ BRAIN 官方检查）**:

| 严重级别 | 检查数 | 示例 |
|----------|--------|------|
| ERROR | 9 | sharpe_positive, fitness_minimum, turnover_platform, self_correlation, prod_correlation, weight_concentration, sub_universe_sharpe, expression_valid, 类型专项检查 |
| WARNING | 8 | returns_positive, drawdown_limit, turnover_quality, marginal_contribution, margin_minimum, ic_mean, ic_ir, coverage_minimum, delay_consistent, is_oos_robustness |
| INFO | 6 | rank_ic, turnover_stability, drawdown_stability, neutralization_applied, pasteurization_applied, nan_handling, expression_complexity |

**B. Quality Gate（production-gate-v2.1）**:

- `submission_ready = not any(failed)` — 任何一项不通过即阻塞提交
- `failed_reasons` 逐条记录，可追溯
- `decision_band`: submit_candidate(≥85) / optimize_before_submit(≥70) / research_only(≥50) / abandon_or_rebuild(<50)

**C. Submission Safety（提交安全门禁）**:

| 检查项 | 说明 |
|--------|------|
| daily_auto_submission_limit | 每日最多 3 次 |
| run_auto_submission_limit | 每次运行最多 2 次 |
| minimum_auto_submit_interval | 间隔 ≥ 120 分钟 |
| duplicate_official_alpha_id | 不重复提交 |
| duplicate_expression | 不重复表达式 |
| micro_variant_similarity | SequenceMatcher + Jaccard 双重相似度 < 0.90 |
| account_risk_level | 基于 correlation/concentration/turnover 的 3 级风险评估 |

**评价**: 门禁系统是项目最强环节之一。检查维度丰富、严重级别分明、可追溯、可审计。

**缺失**:
- 缺少"与已有 production Alpha 的相关性"检查（只能检查与已提交表达式的相似度，无法检查与云端已上线的 Alpha 的实际相关性）
- 缺少"市场环境适配"检查（如当前是高波动还是低波动市场）

### 2.4 迭代（Iteration）

迭代闭环由以下组件构成：

```
官方回测失败 → diagnose() 诊断 → get_mutation_mode() 确定变异方向 → mutate_expression() 变异 → 下一轮生产
                                    ↑
经验反馈 ← record_alpha_result() ← 高分 Alpha 特征 → get_winning_patterns() → 指导生成
                                    ↑
自适应策略切换 ← ConvergenceTracker.stalled → switch_strategy_profile()
```

| 迭代能力 | 状态 | 详情 |
|----------|------|------|
| 失败诊断 | ✅ | `diagnose()` 覆盖 7 个失败维度（Sharpe/Fitness/Turnover/Correlation/Concentration/Margin/SubSharpe），每个有 3-5 条具体改进建议 |
| 变异引导 | ✅ | 4 种 mutation_mode：default / field_swap / structure_change / longer_window |
| 经验反馈 | ✅ | `alpha_features.jsonl` 记录每次官方回测特征，5 轮一次提炼高分模式 |
| 收敛检测 | ✅ | `ConvergenceTracker` 滚动窗口 10 轮、停滞阈值 5 轮 |
| 策略切换 | ⚠️ | 仅切换预设的 7 个 strategy profile（region/universe/neutralization 变体），不能自动探索新组合 |
| 假设库权重更新 | ✅ | `update_hypothesis_weights()` EMA 平滑更新假设/字段/家族的 winner ratio |

**核心问题**:

1. **迭代的效果无法量化比较**: 例如，"将 ts_mean(close,20) 改为 ts_mean(close,60)" 这个变异是否能提升 Sharpe，系统**没有 A/B 对照机制**（虽然有 `save_ab_test()` 方法，但未见管道中主动使用）
2. **变异空间有限**: 只支持 4 种预设变异模式，没有基于算子语义的智能替换（如"将 momentum 算子替换为 mean_reversion 算子"）
3. **经验反馈的滞后性**: 每 5 轮才提炼一次，且 `min_sample=2` 的阈值偏低，容易引入噪声

### 2.5 收敛（Convergence）

`ConvergenceTracker` 的设计是好的，但它的判定标准是**正确但粗糙**的：

```
stalled = (连续 N 轮 best_sharpe 未创新高)
```

**问题**:

1. **仅用 best_sharpe 判定收敛**: 忽略了均值趋势、变异系数、成功率的稳定性。一个 alpha 在 10 轮中只有 1 个高 Sharpe（偶然）和 10 轮中 8 个稳定高 Sharpe（真实能力），当前算法无法区分
2. **stall_threshold=5 可能偏小**: 在 random exploration(10%) 模式下，5 轮无新高是正常现象
3. **推荐策略切换是唯一动作**: 没有"调高 exploration 比例"、"换数据集"、"增加候选预算"等更细粒度的自适应

---

## 三、官方 API 流程真实模拟能力

### 3.1 模拟链路完整性

```
authenticate() → list_fields() → list_operators() → validate_expression()
→ submit_simulation() → poll_simulation() → fetch_result()
→ normalize_metrics() → check_alpha() → submit_alpha()
```

| 步骤 | 状态 | 实现质量 |
|------|------|----------|
| 认证 | ✅ | Basic Auth + Bearer Token + Session Cookie 三级退降 |
| 获取 fields | ✅ | 分页遍历 + 缓存 + 429 重试 + 过期降级 |
| 获取 operators | ✅ | 同上 |
| 表达式预检 | ✅ | 括号/算子/字段/长度/嵌套 6 项本地检查，标注"BRAIN 编译由提交确认" |
| 提交模拟 | ✅ | `build_simulation_payload()` 正确构建 platform dict，pasteurization→pasteurize 字段名转换 |
| 轮询结果 | ✅ | 60 次 × 6 秒 = 最长 360 秒，状态识别 COMPLETED/FAILED/RUNNING/TIMEOUT |
| 提取指标 | ✅ | `normalize_metrics()` 递归提取 12 项指标，自动百分比→比率转换 |
| Alpha Check | ✅ | 检查 fails 列表，支持 exception rule（SELF_CORRELATION Sharpe 优势） |
| 提交 Alpha | ✅ | 两次门禁：Official 预检 + 本地安全性检查 |
| 限速控制 | ✅ | 全局限速锁 + 最小间隔 3 秒 + 429 退避 + 并发模拟限制检测 |
| 结果缓存 | ✅ | SHA256 参数摘要 + TTL 86400 秒 |

### 3.2 Mock API 保真度

| 方面 | 评估 |
|------|------|
| 接口兼容 | ✅ 与 OfficialBrainAPI 接口完全一致 |
| 字段来源 | ⚠️ 内置 18 个硬编码字段，**可选**从 `official_*.json` 加载 |
| 指标生成 | ⚠️ 基于 MD5 hash + 表达式关键词启发式，不反映真实金融逻辑 |
| 门禁判断 | ✅ 使用相同的 QualityThresholds，但 mock 数据总是 PASS |
| Check | ✅ 总是 PASS |

**评价**: Mock API 的确定性使其适用于**流程测试和 UI 演示**，但不适用于**策略回测或 Alpha 质量评估**。这是合理的设计取舍，但需要文档明确标注其局限性。

### 3.3 官方结果可信度

`normalize_metrics()` 从 BRAIN API 响应中提取以下指标：

```
sharpe, fitness, turnover, returns, drawdown, margin,
sub_universe_sharpe, correlation, weight_concentration,
pass_fail, failure_reason
```

**可信度评估**: ✅ 数据源为 BRAIN 官方 API，提取逻辑已在生产环境验证。`_ratio()` 函数正确处理百分比/比率转换。

**边缘风险**: 
- `margin` 字段有时不返回 → fallback 为 `returns/turnover/100` 的本地估算
- `correlation` 字段替代了 `selfCorrelation` — 确认 BRAIN API 返回的是哪个字段名

---

## 四、评价标准维度分析：丰富度、结构化、可解释性、可校准性

### 4.1 维度丰富度

| 类别 | 维度数 | 涵盖内容 |
|------|--------|----------|
| 收益类 | 3 | Sharpe(含Delay区分), Fitness(含交叉验证), Returns |
| 风险类 | 5 | Drawdown, SelfCorrelation(含exception), ProdCorrelation, WeightConcentration, MarginalContribution |
| 换手类 | 3 | Turnover平台硬门槛(1%-70%), Turnover质量目标(<30%), Turnover稳定性 |
| 稳健性类 | 3 | SubUniverseSharpe(含公式校验), IS/OOS比率, Coverage |
| IC类 | 2 | IC_Mean, IC_IR, RankIC |
| 结构类 | 4 | Expression有效性, 复杂度, 中性化, 巴氏杀菌 |
| 数据类 | 2 | Delay一致性, NaN处理 |
| 经济类 | 1 | Hypothesis长度(粗糙代理) |
| **总计** | **23** | |

**评价**: 维度覆盖全面，与 BRAIN 官方 Alpha Check 清单高度对齐。但经济逻辑纬度的指标太粗糙。

### 4.2 结构化程度

- `scorecard.schema_version: "scorecard-v2.1"` — 版本化
- `gate.schema_version: "production-gate-v2.1"` — 版本化
- 每个 item 有 name/actual/direction/target/passed/points/source — 元数据完整
- 门禁有 failed_reasons 列表 — 可追溯

**评价**: ✅ 结构化程度高。

### 4.3 可解释性

- 每个失败的检查有明确的消息（如 "Sharpe=1.12 (below 1.25)"）
- 诊断引擎输出具体的改进建议（如 "添加 winsorize + rank 链"）
- 来源标注清晰（"经验" / "BRAIN_official_simulation_result" / "BRAIN_API"）

**评价**: ✅ 可解释性好。但 Prior Score 的 8 维权重缺乏解释（为什么 economic_logic 权重是 0.18 而不是 0.15？）

### 4.4 可校准性

这是**最强弱点**。系统有校准的**基础设施**，但校准**未被激活**：

| 已具备 | 未激活 |
|--------|--------|
| `scorecard.calibration.prior_minus_empirical` 记录 | 无人消费此数据来调整权重 |
| `scorecard.calibration.sample_weight` 记录 | 无人利用此数据做加权回归 |
| `alpha_features.jsonl` 经验数据库 | 仅用于频率统计，未做相关性/归因分析 |
| `ab_tests.jsonl` | 有 `save_ab_test()` 但管道中未见主动调用 |
| Scorecard 三层权重 30/45/25 | 硬编码，无自适应机制 |
| Prior 8 维权重 0.18/0.14/0.16/... | 硬编码，无反向传播校准 |

**核心问题**: 系统**记录了数据但不学习**。拥有数千条 alpha_features 记录后，本可以：
1. 计算 prior_score 维度权重与 official_sharpe 的回归系数，自动优化权重
2. 发现哪些 prior 维度对真实表现有预测力（哪些是噪音）
3. 识别"高分 prior + 低分 empirical"的系统性偏差

但目前这些能力都不存在。

---

## 五、向科学评分系统演进的潜力评估

### 5.1 已有基础（强项）

| 基础设施 | 状态 | 科学评分系统需要什么 |
|----------|------|---------------------|
| 版本化评分 schema | ✅ | 实验可复现 |
| JSONL 审计轨迹 | ✅ | 追溯每一条决策 |
| 多维评分 | ✅ | 避免单一指标过拟合 |
| 门槛与质量目标分离 | ✅ | ERROR/WARNING 两级区分 |
| 官方阈值对齐 | ✅ | 可映射到 BRAIN 标准 |
| 经验数据库 | ✅ | 用于统计学习的训练集 |
| A/B 测试记录结构 | ✅ | 对照实验的基础 |
| ConvergenceTracker | ✅ | 效果量化的趋势分析 |
| Margin source 标注 | ✅ | 区分 API 数据与估计数据 |

### 5.2 缺失能力（需要新增）

| 能力 | 重要性 | 当前状态 |
|------|--------|----------|
| 统计显著性检验 | **Critical** | 无。无法判断 Sharpe=1.30 和 Sharpe=1.25 的差异是否显著 |
| 权重自动校准 | **Critical** | 无。权重全部硬编码 |
| 特征重要性分析 | **High** | 无。不知道哪些 prior 维度真正预测性能 |
| 过拟合检测 | **High** | 仅有 IS/OOS ratio 一个粗粒度指标，无 walk-forward 或多时间窗口验证 |
| 市场环境分层 | **High** | 无。不区分牛市/熊市/震荡市的 Alpha 表现 |
| 数据衰减追踪 | **Medium** | 无。Alpha 随时间的表现衰减未被追踪 |
| 集成评分 | **Medium** | 无。多个 Alpha 组合的协方差结构未被考虑 |
| 可解释 AI | **Low** | 不需要 ML，当前规则系统已足够透明 |

### 5.3 演进路线图建议

```
Phase 1: 证据基础（当前→立即） 
├── 运行多轮生产积累 100+ 条 official 结果
├── 为每条结果记录完整的 prior/empirical 对比
└── 手动分析 prior_score 各维度与 official_sharpe 的相关性

Phase 2: 统计校准（1-2 周）
├── 用回归分析优化 Prior Score 8 维权重
├── 用网格搜索优化三层权重 30/45/25
├── 引入 bootstrap 计算 Sharpe 的置信区间
└── 设立"统计显著"门槛（如 p<0.05 的提升才算有效迭代）

Phase 3: 自适应（1-2 周）
├── scorecard 权重基于历史数据自动更新
├── convergence 判定加入统计指标（不仅看 best，也看均值+方差）
├── 变异模式选择基于历史 AB 效果
└── 引入 walk-forward 验证替代单一 IS/OOS 比率

Phase 4: 预测性评分（长期）
├── 建立 prior → empirical 预测模型
├── 在提交前预测官方模拟结果
└── 实现"不浪费官方预算"的精准预筛
```

---

## 六、总体评定表

| 评估维度 | 状态 | 详细评级 |
|----------|------|----------|
| 创建（Generation） | ✅ 达成 | B+ — 工程完整，但假设库质量是外部依赖 |
| 估分（Scoring） | ⚠️ 部分达成 | B- — 结构好，但权重未校准，prior 维度过粗 |
| 评价（Evaluation） | ✅ 达成 | A — 门禁系统是项目最强环节 |
| 迭代（Iteration） | ⚠️ 部分达成 | B- — 诊断精准，但变异空间有限，无 AB 对照 |
| 收敛（Convergence） | ⚠️ 部分达成 | B- — 追踪框架好，但判定逻辑过简 |
| 官方 API 模拟 | ✅ 达成 | A- — 全链路完备，限速/重试/缓存/退降设计完善 |
| 官方结果可信度 | ✅ 达成 | A — 数据源官方，提取逻辑正确 |
| 评分维度丰富度 | ✅ 达成 | A — 23 维，覆盖 BRAIN 官方 Alpha Check 全集 |
| 结构化程度 | ✅ 达成 | A — 版本化 schema + 元数据完整 |
| 可解释性 | ✅ 达成 | A- — 逐项消息清晰，但 prior 权重缺乏解释 |
| 可校准性 | ❌ 未达成 | C — 基础设施齐全但未激活 |
| 科学评分演进潜力 | ⚠️ 中等 | B — 基础扎实，缺统计推断和自动校准层 |

**综合判定**: 系统**能跑完整闭环**（创建→模拟→评分→门禁→提交），在"模拟真实 API 流程、拿官方结果、做官方门禁判断"这三个维度上表现出色。但"产出高质量 Alpha"这一终极目标，目前依赖的是**工程纪律**（多层门禁+安全控制）而非**统计证据**（权重校准+效果量化+显著性检验）。

**一句话总结**: 这是一个**工程上可靠、科学上待证**的系统。它不会因为 bug 或安全漏洞伤害你的 BRAIN 账户，但它能否持续产出优于人工挑选的 Alpha，目前没有数据证明。

---

## 七、本轮优化建议（优先级排序）

### P0 — 立即执行

1. **激活校准基础设施**: 在生产环境跑 20+ 轮，积累足够的 official 结果后，写一个 `calibrate_weights.py` 脚本，计算 prior_score 各维度与 official_sharpe 的线性回归系数，输出优化后的权重建议。

2. **修复评分维度的粗糙问题**: `economic_logic` 不要再二值化（≥40 / <40），改为对 hypothesis 做关键词检测（如"momentum"/"reversal"/"value"/"quality"/"liquidity"等经济概念分类），每类给予不同基础分。

### P1 — 短期执行

3. **增强 ConvergenceTracker**: 加入 `avg_sharpe` 的置信区间计算（bootstrap），stall 判定改为"均值无显著改善"而非"best 未创新高"。

4. **引入 AB 对照机制**: 在 `mutate_expression()` 之后，对变异前后的 Alpha 都提交官方模拟，对比结果记录到 `ab_tests.jsonl`，用于后续变异模式的效果统计。

### P2 — 中期执行

5. **建立 prior → empirical 预测模型**: 用 `alpha_features.jsonl` 中的历史数据训练一个简单的回归模型，预测 candidate 的 expected_sharpe，替代当前的启发式 prior_score。

6. **市场环境分层**: 在评分中加入 market_regime（基于 VIX 或其他波动率指标），使 Scorecard 能区分"高波动环境下 1.5 的 Sharpe"和"低波动环境下 1.5 的 Sharpe"的不同意义。

---

## 八、风险登记

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 经验权重误导评分 | 中 | 中 | 尽快激活统计校准 |
| 变异模式效果未知 | 高 | 低 | 引入 AB 对照后可见 |
| Hypothesis Library 内容质量差 | 中 | 高 | 人工审查假设库，补充经济逻辑 |
| 长期跑不出高质量 Alpha | 中 | 高 | 这是系统设计的固有问题，需科学方法补充 |
| BRAIN API 字段变更导致解析失败 | 低 | 中 | refresh 机制已有，加监控告警 |

---

**评估人**: WorkBuddy AI 代理
**评估依据**: 代码审查 + 配置审查 + 文档审查 + 已有审计报告交叉验证
**下次评估建议**: 在系统积累 100+ 条官方回测结果后重新评估校准状态
