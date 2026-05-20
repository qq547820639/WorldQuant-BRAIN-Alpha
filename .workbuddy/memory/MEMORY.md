# 长期记忆

## 项目核心信息
- 项目：WorldQuant BRAIN Alpha 自动化生产系统
- 用户角色：WorldQuant BRAIN 平台顾问（Consultant），高级 PM/BA
- 核心目标：自动化 Alpha 发现全生命周期（生成→评估→迭代→提交）

## 用户偏好
- 所有参数必须来自官方 BRAIN API 文档，拒绝手动添加非官方参数
- 偏好高度结构化的技术简报（表格、编号章节、明确结论/判定、差异记录、风险项、QA 测试重点）
- 推进前系统性检查要素完整性
- 严格偏好按序逐步执行改进计划，而非并行处理
- 拒绝对临时上下文使用跨会程承诺语言

## 架构关键决策
- 零硬编码原则：所有字段/算子来自 data/official_*.json
- 评分体系：三层（先验 8 维 / 实证 16 项 / 提交清单 7 项），权重 30/45/25
- 门禁链路：8 阶段（本地预筛→评分构建→上下文校验→池管理→表达式验证→官方模拟→质量门禁→提交安全）
- AlphaCheckRegistry：25 checks（8 ERROR + 10 WARNING + 7 INFO）+ 类型特定
- Mock/Official 双环境，通过 BrainAPI Protocol 抽象
- 单例 OfficialDataLoader 加载 7642 字段
- 换手率：双层阈值 — platform_max_turnover=0.70（BRAIN 硬门禁）+ target_max_turnover=0.30（顾问质量 WARNING）
- 字段池：top 50 按 coverage 排序（可配置 max_field_pool_size）

## 前端完整性审计（2026-05-15 用户交付）
- 结论：有条件通过进入 QA，不建议直接正式上线
- 主路径覆盖良好，非主路径不完整（失败反馈、状态翻译、检查持久化、特殊类型入口）
- P1（6项）：批量提交失败明细不可见、BLOCKED 未入失败视图、状态码中文化缺 6+ code、检查结果刷新丢失、失败原因偏技术化、Alpha Type 仅 REGULAR
- P2（3项）：文档互斥 vs 代码并行矛盾、事件日志无前端视图、Chart.js CDN 依赖
- 修复顺序：批量提交明细 → BLOCKED 视图 → 状态码中文化 → 检查恢复 → 特殊 Type → 事件中心 → 离线图表 → a11y

## 阶段二方案设计结果（2026-05-15）
- 产出五份文档：接口契约重定义 / 职责边界矩阵 / 前端重构设计 / 后端补全设计 / 迁移计划
- 接口契约重定义：22 路由完整入参/出参规范 + error_code 枚举 + TypeScript 类型定义
- 职责边界：10 项前端逻辑迁移到后端 + 17 项后端数据前端新增消费
- 前端重构：IIFE 命名空间模式 + AppState 单一数据源 + 15 模块拆分 + ~884行精简
- 后端补全：4 Phase (致命→契约→状态机→基建) + 15 子任务 + ~280行改动 + 预计 10h
- 迁移策略：后端先行→前端对接→渐进切换 + 14天里程碑 + 6风险缓解

## 阶段一诊断结果（2026-05-15）
- 产出四份文档：接口差异清单(32项) / 前端逻辑地图(28项) / 后端缺陷清单(35项) / 重构候选清单(10项)
- 关键发现：`check_candidate()` 函数不存在(P0), SSE `await` 语法错误(P0), BLOCKED 状态不可见(P0), 批量提交失败明细缺失(P0)
- 前后端契约缺口：7个P0 + 9个P1 + 9个P2 = 25项有效差异
- 后端缺陷总数：3个P0 + 11个P1 + 21个P2 = 35项
- 前端重构潜力：预计节省~884行(28%)，拆分10个模块

## 已知待修复问题（2026-05-14 评估）
- P1-1: 换手率阈值策略明确化（用户预期 30% 也应硬门禁）
- P1-7: 表达式多样性不足 — checks.jsonl 中 75%+ 因云端 correlation≥0.96 阻断（骨架趋同）
- P1-2: Fields/Operators 刷新失败静默忽略
- P1-4: 硬门禁失败仍计入 empirical_score
- P1-3: PROD_CORRELATION 仅本地估算，未调用官方 API
- P1-5: 字段池 top 50 对 model77(3256 fields)偏保守
- P1-6: auto_calibrator 缺样本量门禁
- 档案中存在但当前缺失：LLM 集成模块（6 prompt 模板）、e2e 测试、pyworldquant SDK 参考

## Research 模块完整代码库认知（2026-05-15 通读完成）

### 文件清单（19 .py + 1 目录）
| 文件 | 行数 | 核心职责 |
|------|------|----------|
| `pipeline.py` | 2795 | 主循环编排：认证→上下文加载→循环(数据集选择→生成→评分→池管理→验证→模拟→提交)→收敛→融合 |
| `generator.py` | ~200 | 基础 CandidateGenerator：generate()、extract_fields/operators()、local_quality() |
| `hypothesis_driven_generator.py` | 1002 | 6 组件：GenerationModeRouter(70/20/10)、HypothesisSelector、ExpressionFamilySelector、FieldSelector、ContextAdapter、HypothesisDrivenGenerator |
| `hypothesis_library.py` | 512 | 数据模型(Hypothesis/ExpressionFamily/FieldCategoryDef 等)+ HypothesisLibrary YAML 加载器 |
| `hypotheses/` | 8 YAML | value_reversal, earnings_revision, sentiment_short, liquidity_premium, low_volatility, quality_profitability, microstructure, analyst_behavior |
| `scoring.py` | 753 | build_scorecard()、prior_score()(8维)、empirical_score()(16项)、evaluate_quality_gate()、decision_band() |
| `scoring_params.py` | 288 | DimensionParam + ScoringParams dataclass，JSON 持久化 |
| `alpha_checks.py` | 754 | AlphaCheckRegistry(25 checks) + CheckResult/CheckReport + 类型特定(POWER_POOL/ATOM/PYRAMID) |
| `convergence.py` | 392 | ConvergenceTracker：Bootstrap 90% CI、Spearman rank 趋势、停滞检测 |
| `experience.py` | 545 | record_alpha_result()、get_winning_patterns()、get_mutation_effectiveness()、update_hypothesis_weights(EMA α=0.2) |
| `safety.py` | 207 | SubmissionLedger：日/运行限制、微变体相似度检测、表达式去重 |
| `repository.py` | 115 | ResearchRepository：JSONL 持久化(candidates/events/lifecycle/cloud_alphas) |
| `theme_engine.py` | ~500 | DynamicThemeEngine：基于类别的随机模板生成 |
| `fusion.py` | ~400 | alpha_fusion：select_fusion_candidates()、generate_fusion_expressions() |
| `dataset_selector.py` | ~300 | DatasetSelector：rotate/random/best 策略 |
| `auto_calibrator.py` | ~200 | auto_calibrator：needs_calibration()、calibrate()、apply() |
| `diagnostics.py` | ~200 | diagnose()、get_mutation_mode()：失败根因诊断 |
| `iterative_optimizer.py` | ~200 | IterativeOptimizer：optimize() 定向变异 |
| `templates.py` | 192 | AlphaTemplateRegistry：6 内置模板 + JSON 加载 + 数据集感知实例化 |

### Pipeline 主循环关键阶段（pipeline.py run()）
1. `_sync_cloud_alphas()` — 同步云端已有 Alpha
2. `_load_official_context()` — JSON-first 加载 → 回退 API，同时装配 DatasetSelector/DynamicThemeEngine/HypothesisLibrary
3. **每轮循环**:
   - `_cycle_select_dataset()` — 数据集选择（支持 rotate 策略）
   - Experience feedback（每 5 轮）
   - Context refresh（每 50 轮 / 24h）
   - `generator.generate()` → `_local_prefilter()` → pool merge/prune
   - `_validate()` → `_fill_backtest_slots()` → `_poll_due_backtests()`
   - `_finalize_backtest_candidate()` → AlphaCheckRegistry → record_alpha_result()
   - `_maybe_switch_strategy()` → epsilon-greedy bandit (ε=0.20)
   - Auto-calibrate / Fusion trigger（收敛停滞时）

### 重要架构模式
- **_CycleState** 命名元组：pool_by_expression + accepted_candidates + archive_stats
- **双模式回测**：slot-based（_fill_backtest_slots）并发 + batch（_simulate_batch）批量，均支持 rate limit halt/resume
- **二次融合**：`_create_secondary_fusion_candidate()` 使用 diagnostics + IterativeOptimizer 定向变异，失败后备退到简单启发式
- **Smart ranking**：cloud correlation risk 扣分（high -30, medium -10）
- **Gate schema**：schema_version "production-gate-v2.1"，统一 submission_ready/status/failed_reasons/warnings
- **ADAPTIVE_PROFILES**：7 种策略配置（USA+TOP3000, USA+SMID, DEV+TOP3000 等），自动切换

### Hypothesis YAML 结构（_schema.yaml 定义）
- 顶层 hypothesis 对象，必填：id/name/category/version/rationale/field_categories/expression_families/adaptation
- category 枚举：momentum/quality/reversal/volatility/liquidity/value/growth/hybrid/cross_sectional
- field_categories: 含 category/priority(P0-P2)/examples/weight
- expression_families: 含 id/structure/description/windows/windows_short/windows_long/weight
- expected_failure_modes: gate/reason/mitigation
- adaptation: preferred_regions/universes/delays, unsuitable_regions
- experience_weights: overall/field_category_weights/expression_family_weights/window_weights（EMA 更新目标）

### 8 个已实现的 Hypothesis
| ID | 类别 | 核心理论 | 表达式家族数 |
|----|------|----------|-------------|
| value_reversal | reversal | 过度反应→均值回归 + 价值溢价 | 5 |
| earnings_revision_momentum | momentum | 分析师锚定偏差→上修持续性 | 4 |
| sentiment_short_interest | hybrid | 空头拥挤 vs 基本面空头 | 4 |
| liquidity_premium | liquidity | Amihud 非流动性补偿 | 4 |
| low_volatility_anomaly | volatility | 低波动异常(CAPM 违反) | 4 |
| quality_profitability | quality | 经济护城河+应计质量 | 4 |
| microstructure_order_flow | hybrid | 订单流信息不对称 | 5 |
| analyst_behavior_bias | cross_sectional | 分析师羊群效应+过度自信 | 5 |
