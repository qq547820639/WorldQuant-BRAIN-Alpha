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
- 单例 OfficialDataLoader 加载官方字段（8599，2026-06-15 计数）
- 换手率：双层阈值 — platform_max_turnover=0.70（BRAIN 硬门禁）+ target_max_turnover=0.30（顾问质量 WARNING）
- 字段池：top 50 按 coverage 排序（可配置 max_field_pool_size）
- Pipeline 由 9 个 Mixin 组合（AlphaResearchPipeline 总 ~720 行），不是 God Class
- `runtime_constants.REAL_SUBMIT_DISABLED_WEB_FLOW: Final[bool] = True` 是 web 提交守门，被 `BRAIN_ALPHA_FORCE_REAL_SUBMIT=1` 环境变量绕过（仅测试用）

## Research 模块代码库认知（2026-06-15 通读完成）
- 19 个 .py + 1 个 hypotheses/ 目录，详见 `2026-06-15.md` 当日日志
- Pipeline 主循环 8 阶段（认证→上下文加载→循环(数据集→生成→评分→池管理→验证→模拟→提交)→收敛→融合）
- 三模式生成 70/20/10（GenerationModeRouter）
- 8 个已实现 Hypothesis：value_reversal / earnings_revision / sentiment_short / liquidity_premium / low_volatility / quality_profitability / microstructure / analyst_behavior
- 2026-06-15 扩容至 11 个：+ cross_asset_momentum / event_driven_earnings / alternative_data_sentiment
- 双模式回测：slot-based 并发 + batch 批量
- 二次融合：diagnostics + IterativeOptimizer 定向变异
- 2026-06-15 三方向决策：A (E2E 验证) ✅ / B (治理债) ⏸️ / C (骨架扩容 8→11) ✅

## 关键模式教训（跨会程有效）
### frozen=True 改造
- 加 frozen=True 后必须找所有 setattr/mutate 调用并改为 dataclasses.replace
- web_config.run_config_from_payload 是最重灾区 (QualityThresholds + ScoringConfig)
- tests 也需要改用 dataclasses.replace

### 3.9 + PEP 604 + frozen + get_type_hints 陷阱
- get_type_hints 在 3.9 + frozen + 含 PEP 604 union 的注解会立即求值失败
- 修复: 字段级别 try/except, 失败时回退到 Any
- 必须保留 diagnostics 记录 (测试期望)

### 大规模添加 `from __future__ import annotations`
- 用 ast 扫描源码找 PEP 604 union 用法
- 在 docstring/shebang 之后, 其它 import 之前插入
- 必须清理重复 (docstring 描述中如果含 "from __future__" 字符串会触发误判)

### 测试反咬回归 (2026-06-15 教训)
- "修改测试让失败消失" 与 "修复生产 bug" 是两件事，不可混为一谈
- 现象：测试 Loader 类加 `list_fields = get_fields` 别名 → 测试绿但 `OfficialDataLoader` 生产实例没有 `list_fields` → `generator.py:151` AttributeError
- 现象：conftest 默认 `BRAIN_ALPHA_FORCE_REAL_SUBMIT=1` + web 端再次强制设置 → `REAL_SUBMIT_DISABLED_WEB_FLOW` 守门被绕过 → 真提交路径激活
- 验证方法：始终独立跑测试 + diff 审计每个"修复"，而非仅看测试通过数

## 已闭环问题（2026-06-15 18:00 REVIEW 12 项全部处理后回填）
- ~~P1-7: 表达式多样性不足~~ → ✅ 多样性反馈回路已实现（云端 prod_correlation 阻断反哺生成骨架）
- ~~P1-1: 换手率 30% 应硬门禁~~ → ✅ `target_max_turnover=0.30` 升级为 ERROR
- ~~P1-2: Fields/Operators 刷新失败静默忽略~~ → ✅ 改为显式日志 + 上抛
- ~~P1-4: 硬门禁失败仍计入 empirical_score~~ → ✅ `empirical_score` 计算逻辑修复，硬门禁失败不再计分
- ~~P1-3: PROD_CORRELATION 仅本地估算~~ → ✅ 已调官方 API
- ~~P1-5: 字段池 top 50 对 model77 偏保守~~ → ✅ 字段池配置化
- ~~P1-6: auto_calibrator 缺样本量门禁~~ → ✅ 已加样本量门禁
- ~~P1-15: pipeline_candidates.py logger NameError 风险~~ → ✅ logger 模块级定义
- §6 改进项 5：AST 静态扫描预防"测试加方法别名"反模式 → ✅ 已加 check_python_silent_alias_anti_pattern.py 类检查
- §6 改进项 6：sub_universe_sharpe 豁免规则 → ✅ 已实现 LOW_SUB_UNIVERSE_SHARPE exception
- §6 改进项 7：universe 切换 conflict 检测 → ✅ 已实现

## Web UI 历史（2026-05-15 用户交付审计）
- 结论：有条件通过进入 QA，不建议直接正式上线
- P1（6项）：批量提交失败明细不可见、BLOCKED 未入失败视图、状态码中文化缺 6+ code、检查结果刷新丢失、失败原因偏技术化、Alpha Type 仅 REGULAR
- P2（3项）：文档互斥 vs 代码并行矛盾、事件日志无前端视图、Chart.js CDN 依赖
- 修复顺序：批量提交明细 → BLOCKED 视图 → 状态码中文化 → 检查恢复 → 特殊 Type → 事件中心 → 离线图表 → a11y
