# 产品需求文档 (PRD) — BRAIN Alpha Ops v1.0

| 字段 | 内容 |
|------|------|
| **文档版本** | v1.1 |
| **创建日期** | 2026-05-27 |
| **产品名称** | BRAIN Alpha Ops |
| **产品简介** | 账户安全优先的 WorldQuant BRAIN Alpha 自动化研究操作平台 |
| **目标版本** | v1.0 |
| **作者** | Product Team |
| **状态** | 已交付验收 🟢 |

---

## 1. 产品概述与背景

### 1.1 产品愿景

让量化研究员通过一个本地 Web 控制台，即可完成 WorldQuant BRAIN 平台上 Alpha 因子的**全生命周期管理**——从候选生成、质量评分、官方模拟回测到安全提交——全程无需离开浏览器，无需编码，无需担心误操作导致账户风险。

### 1.2 目标用户群

| 用户角色 | 核心场景 | 技术能力 |
|---------|---------|---------|
| **量化研究员** | 日常 Alpha 发现与迭代，需要高效生成候选并进行质量评估 | 了解 FASTEXPR，不要求 Python 编程能力 |
| **策略分析师** | 分析历史研究数据，识别有效因子模式，指导研究方向 | 熟悉量化指标，需要数据可视化 |
| **风险管理岗** | 审核提交内容，确保符合 BRAIN 平台规范和内部合规要求 | 关注合规性，不涉及因子开发 |
| **LLM Agent 集成者** | 通过 MCP 协议接入 AI 助手，实现自治研究循环 | 开发者背景，需要 API/协议集成 |

### 1.3 核心痛点

| 痛点 | 现状 | 产品解决方案 |
|------|------|-------------|
| **账户安全焦虑** | 手动调用 API 容易误提交不合规 Alpha，导致 BRAIN 账号被限 | 六条技术红线自动校验 + 提交前双重确认 + 完整的 SubmissionLedger 审计追溯 |
| **重复劳动** | 研究人员反复提交相似因子，浪费 API 配额 | 表达式指纹识别 + 去重预检 + 表达式相似度比对 |
| **缺乏研究记忆** | 跨会话无法回溯哪些字段/算子/模式有效，重复试错 | 结构化三层知识库（规则/发现/失败）+ ResearchMemory 统计汇总 |
| **API 配额昂贵** | 每次 BRAIN API 调用都消耗配额，本地无法预筛选 | 本地回测引擎预评估（20+ FASTEXPR 算子 + 11项指标），仅高分候选提交官方 API |
| **LLM 幻觉风险** | AI 生成的因子可能重复、不合规或质量低 | 双 LLM 交叉审查 + 知识库证据检查 + 可观测性去重守卫 |
| **信息碎片化** | 配置、候选、回测结果、云数据分散在多个系统 | 统一 Web 控制台：5个 Tab 面板覆盖研究→评分→提交→配置全链路 |

### 1.4 产品定位

**BRAIN Alpha Ops** 定位为 WorldQuant BRAIN 平台的上层操作工具，不替代 BRAIN 的核心功能（数据、回测引擎、Alpha 检查），而是在其之上提供**安全层、效率层和智能层**。

---

## 2. 功能需求

### 2.1 功能架构总览

```
┌──────────────────────────────────────────────────────┐
│                   Web 控制台 (React 18)               │
│  Dashboard │ Candidates │ Scoring │ Submit │ Config   │
├──────────────────────────────────────────────────────┤
│                    API 服务层                          │
│  GET/POST 路由 (33+17) │ SSE 实时流 │ CSRF/Token 认证  │
├──────────────────────────────────────────────────────┤
│                    研究引擎层                          │
│  Pipeline(6-Stage) │ Scoring(3-Layer) │ Safety(Ledger)│
│  LocalBacktestEngine │ KnowledgeBase │ CrossReview    │
├──────────────────────────────────────────────────────┤
│                    BRAIN API 适配层                    │
│  OfficialBrainAPI │ Canonical │ RedLineVerifier       │
└──────────────────────────────────────────────────────┘
```

### 2.2 核心功能模块

#### 2.2.1 模块 A: 研究流水线 (Research Pipeline)

**功能描述**: 自动化的六阶段 Alpha 研究流水线，从候选生成到安全提交。

| 阶段 | 名称 | 功能 | 验收标准 |
|------|------|------|---------|
| Stage 1 | Generation | 基于经验引导 + 助手引导 + 可观测性约束，生成候选 Alpha 表达式 | 每周期生成 20 个候选，字段来源仅限官方数据加载器 |
| Stage 2 | LocalScoring | 本地质量评分 + 三层评分卡（先验/实证/清单）预过滤 | 低于 min_local_quality_score 的候选被拒绝 |
| Stage 3 | OfficialValidation | 通过 BRAIN API alpha check 验证候选 | 预算内（max_official_validations_per_cycle）提交验证 |
| Stage 4 | Simulation | 提交 BRAIN 模拟回测并轮询结果 | 回测槽位管理 + 并发控制 + 断点续跑 |
| Stage 5 | QualityGate | 质量门禁评估 + 决策带（提交/优化/研究/放弃） | 7项 BRAIN Alpha Check 全覆盖，含豁免规则 |
| Stage 6 | Submission | 安全提交到 BRAIN + 分类账记录 | SubmissionLedger 记录每笔提交 + 每日/每运行次数限制 |

**用户流程**:
1. 用户在 Dashboard 点击「Start Pipeline」
2. 系统按配置的 max_cycles 循环执行 Stage 1-6
3. 每个周期实时推送进度（SSE 流 + 周期轮询）
4. 达标候选自动进入提交队列（需用户预先配置 auto_submit）
5. 用户可在 Candidates Tab 查看所有候选的排序/筛选/状态

#### 2.2.2 模块 B: 本地回测引擎 (Local Backtest Engine)

**功能描述**: 不依赖 BRAIN API 即可在本地评估因子质量，节省配额。

| 能力 | 说明 |
|------|------|
| 表达式求值 | 支持 ~20 个 FASTEXPR 算子（rank, zscore, ts_zscore, ts_mean, ts_std_dev, ts_delta, ts_sum, ts_min, ts_max, ts_corr, abs, log, sign, power, neg 等） |
| 投资组合构建 | Dollar-neutral 长/短组合（可配置 quantile） |
| 指标计算 | Sharpe, Fitness（BRAIN 公式）, Turnover, Returns, Drawdown, IC/IR, Correlation, Concentration, Margin(bps), Sub-universe Sharpe |
| 合成数据 | 20 个标准字段 × N 天 × M 股（可配置，252×500 默认） |
| 通过标准 | pass_local: Sharpe≥1.25, Fitness≥1.0, Turnover∈[0.01,0.70], Concentration≤0.10 |
| 安全限制 | 表达式最大长度 500 字符，嵌套深度限制（默认 6），NaN/Inf 替换为 0.0 |

**验收标准**: 本地回测结果与 BRAIN 官方模拟的方向性一致（Spearman ρ ≥ 0.6），用于预筛选而非替代官方回测。

#### 2.2.3 模块 C: 结构化知识库 (Knowledge Base)

**功能描述**: 跨会话持久化的三层知识管理，避免重复实验。

| 层级 | 目录 | 内容示例 |
|------|------|---------|
| **规则层** (rules/) | 已验证的稳定规则（必须遵守） | "rank(close) 是可靠基础信号"；"delay=1 下 Sharpe≥1.25" |
| **发现层** (findings/) | 经验发现（参考） | "close + volume 组合 Sharpe 均值 1.5"；"USA 市场 momentum 优于均值回归" |
| **失败层** (failures/) | 已证伪路径（禁止重复） | "避免仅使用短窗口动量"；"高 turnover 模式已被平台拒绝" |

**核心能力**:
- 自动提取：从 ResearchMemory 摘要中自动提取规则/发现/失败
- 模式匹配：通过表达式指纹查询相关规则
- 生成约束：为 CandidateGenerator 提供 preferred_fields/operators/forbidden_patterns
- 持久化：每个条目 = 一个 JSON 文件，按 layer/category/ 组织

**验收标准**: 运行 10 个周期后，规则层至少包含 5 条规则，发现层至少包含 10 条发现，失败层至少包含 3 条失败模式。

#### 2.2.4 模块 D: 双 LLM 交叉审查 (Cross-Review)

**功能描述**: 对 AI 助手的产出的结论性判断引入第二模型独立评审。

| 组件 | 功能 |
|------|------|
| KnowledgeEvidenceChecker | 将主要 LLM 的声明与知识库规则/失败层比对，计算证据支持度 |
| ReviewDecisionEngine | 七级决策逻辑：accept / accept_with_warnings / conservative_review_required / reject |
| CrossReviewPipeline | 编排器：auto-trigger 启发式 + 完整审查 + 审计追踪写入 |

**决策规则**:
1. primary_confidence < 0.3 → reject
2. LLM 不一致且 reviewer_confidence ≥ 0.5 → conservative_review_required
3. 证据支持度 < 0.2 → reject
4. 全部一致且证据 ≥ 0.6 → accept
5. 中等一致 → accept_with_warnings

**验收标准**: 高置信度（>0.8）且无风险标记的响应自动跳过审查；有争议或低置信度的响应触发审查并生成决策。

#### 2.2.5 模块 E: Web 控制台 (React Frontend)

**功能描述**: 用户与系统的交互界面。

| Tab | 功能 | 关键交互 |
|-----|------|---------|
| **Dashboard** | KPI 概览 + 流水线状态 + 云 Alpha 缓存 + Top 族系/字段/失败 | 启动/停止流水线；SSE 实时进度条 |
| **Candidates** | 候选列表（可排序/筛选） | 按 Score/Sharpe/Fitness/TO/Status 排序；文本过滤 |
| **Scoring** | 评分卡可视化 + 质量门禁检查 | 三层评分进度条；7 项 Alpha Check 通过/失败详情 |
| **Submit** | 提交控制面板 | Alpha ID 验证 + Pre-Submit Check + 确认复选框 |
| **Config** | 只读配置展示 | Brain Settings / Budget / Thresholds / Scoring |

**UX 标准**:
- 加载态：骨架屏 (Skeleton) 动画，非纯文本 "Loading..."
- 空态：EmptyState 组件（图标 + 标题 + 描述 + 操作按钮）
- 错误态：ErrorBanner 组件（role="alert" + 错误消息 + Retry 按钮）
- 无障碍：ARIA 全标注，键盘导航，屏幕阅读器播报，focus-visible 样式，prefers-reduced-motion
- 响应式：xs:480px 断点，移动端隐藏次要元素，表单 flex-wrap

**验收标准**: Lighthouse Accessibility 评分 ≥ 90，所有交互元素可通过键盘访问。

#### 2.2.6 模块 F: Agent 工具箱 (Agent Toolbox)

**功能描述**: 通过 MCP 协议暴露 26 个安全工具供 LLM Agent 调用。

| 类别 | 工具数 | 代表工具 |
|------|--------|---------|
| 上下文 | 1 | list_context（字段/算子/数据集） |
| 生成 | 1 | generate_candidates（带经验引导+助手引导） |
| 验证 | 1 | validate_expression（本地+API 验证） |
| 评分 | 1 | score_candidate |
| 模拟 | 2 | run_simulation / run_simulation_batch |
| 提交 | 2 | check_alpha / submit_alpha（强制 confirm_submit） |
| 研究 | 5 | query_research_memory / expression_index / observability / market_data_cache / vectorized |
| 助手 | 4 | build_assistant_context / request / parse_response / guidance |
| 风控 | 2 | run_anti_overfit / run_rolling_validation |
| 审查 | 1 | cross_review_assistant_response |
| 告警 | 2 | send_alert / route_alert |

**安全机制**:
- confirm_live_api → 必须显式确认才允许调用 BRAIN API
- confirm_submit → 必须双重确认才允许提交
- 表达式去重预检 → 重复表达式自动阻断
- MAX_TOOL_CANDIDATES=100 → 单次生成上限

**验收标准**: 无 confirm_live_api 参数时，所有写操作返回 `LIVE_API_NOT_ALLOWED` 错误。

#### 2.2.7 模块 G: A股数据适配器 (A-Share Adapter)

**功能描述**: 为中国 A 股市场提供免费数据源接入。

| 数据源 | 提供数据 | 缓存 |
|--------|---------|------|
| baostock | 日线 OHLCV + 换手率 + 复权因子 | Parquet（优先）/ JSON（降级） |
| akshare | 指数成分股（沪深300/中证500/上证50/创业板）/ 行业分类 | Parquet / JSON |

**核心能力**:
- `load_daily_batch(symbols, start, end)` → dict[symbol → list[DailyBar]]
- `load_index_universe(index_code)` → 获取指数全成分股的日线数据
- `to_backtest_format()` → 转换为 LocalBacktestEngine 兼容的 2D 数组
- Parquet 缓存：跨会话缓存，命中时零 API 调用

**验收标准**: 安装 baostock 后，`load_daily_batch(['000001'], start='2024-12-01', end='2024-12-10')` 返回 7 个交易日数据。Parquet 缓存命中时无网络请求。

### 2.3 用户使用流程

```
[启动] → Dashboard 点击「Start Pipeline」
  → (Stage 1) 生成候选 → 实时推送
  → (Stage 2) 本地评分过滤 → 实时推送
  → (Stage 3) BRAIN 官方验证 → 实时推送
  → (Stage 4) BRAIN 模拟回测 → 轮询结果
  → (Stage 5) 质量门禁 → 决策带
  → (Stage 6) [可选] 自动提交 → SubmissionLedger 记录
  → [查看] Candidates Tab 查看排序后的候选
  → [分析] Scoring Tab 查看评分详情 + 门禁检查项
  → [提交] Submit Tab 手动确认提交（如需手动作业）
  → [优化] Config Tab 根据结果调整配置参数
```

### 2.4 技术红线合规 (六大红线)

| 红线 | 要求 | 验证方式 |
|------|------|---------|
| RL-1: 字段/算子禁自定义扩展 | 所有字段和算子必须来自 BRAIN 官方数据源 | OfficialDataLoader + context_defaults 无硬编码回退 |
| RL-2: 阈值零偏差 | 所有阈值必须与 BRAIN 官方文档完全一致 | QualityThresholds 默认值 ≡ CANONICAL_THRESHOLDS |
| RL-3: Dataset ID 全量可用 | 所有 dataset ID 可用且可追溯 | official_datasets.json 在线验证 |
| RL-4: 参数全链路可溯 | 从配置到评分到提交的参数链完整 | ScoringConfig + PipelineResult 含完整审计字段 |
| RL-5: 要素全覆盖 | 覆盖全部 7 项 BRAIN Alpha Check | empirical_score 含 LOW_SHARPE/FITNESS/TURNOVER_HI/LO/SELF_CORR/CONCENTRATED/SUB_UNIVERSE |
| RL-6: 代码强对齐 | Config/Web validators 必须从 canonical.py 导入枚举 | redline_verifier.py 自动比对 |

---

## 3. 非功能需求

### 3.1 性能指标

| 指标 | 目标 | 测量方式 |
|------|------|---------|
| **API 响应时间** | GET < 200ms, POST < 500ms (P95) | Web 服务器日志 |
| **SSE 推送延迟** | < 1 秒 | 前端 EventSource 时间戳差值 |
| **本地回测引擎** | 单表达式 < 2 秒（252×500 数据集） | Python time.perf_counter() |
| **表达式解析** | < 10ms/表达式 | 解析器计时 |
| **知识库查询** | < 50ms（<1000 个条目） | 文件系统 stat + JSON 解析 |
| **并发用户** | 单用户本地部署（127.0.0.1） | 默认配置，非多用户系统 |
| **内存占用** | < 500MB（空闲），< 1GB（运行） | 系统监控 |
| **启动时间** | < 5 秒（冷启动，首次加载） | launch_web.py 到 ready |

### 3.2 安全要求

| 要求 | 实现 |
|------|------|
| **认证** | Session 认证 + CSRF Token + SSE Stream Token |
| **凭证保护** | 仅支持环境变量（BRAIN_USERNAME/PASSWORD/TOKEN），禁止命令行明文 |
| **网络隔离** | 默认绑定 127.0.0.1，allow_remote=False |
| **CSP** | Content-Security-Policy 头含 script-src/style-src/connect-src 限制；React 模式自动扩展 CDN 白名单 |
| **提交安全** | confirm_submit 必选；SubmissionLedger 审计日志；max_auto_submissions_per_day/run 限制 |
| **输入验证** | 表达式深度限制（max_depth=6）+ 长度限制（500 字符）；JSON body 大小限制（2MB） |
| **敏感信息脱敏** | redact_data() 统一脱敏 credential/password/token/cookie/path 字段 |

### 3.3 兼容性要求

| 维度 | 要求 |
|------|------|
| **Python** | ≥ 3.9（推荐 3.10+） |
| **操作系统** | macOS / Windows / Linux |
| **浏览器** | Chrome/Firefox/Safari/Edge 近两个主版本 |
| **BRAIN API** | https://api.worldquantbrain.com |
| **浏览器 JavaScript** | ES6+，无构建工具依赖（React 通过 CDN + Babel Standalone） |
| **可选依赖** | baostock/akshare（A 股数据），pyarrow（Parquet 缓存），jsonschema（配置验证） |

### 3.4 可靠性要求

| 要求 | 实现 |
|------|------|
| **SSE 断线重连** | 前端自动重连（最多 10 次，3 秒间隔） |
| **API 速率限制** | 429 响应自动退避，stale cache fallback |
| **回测断点续跑** | resume_persisted_backtests 从持久化槽位恢复 |
| **研究记忆持久化** | JSONL 追记，SQLite 索引（可选） |
| **优雅降级** | A 股适配器在数据源不可用时返回空数据，不阻塞主流程 |

---

## 4. 数据指标

### 4.1 核心 KPI

| KPI | 定义 | 目标 | 测量周期 |
|-----|------|------|---------|
| **Alpha 生成率** | 每周期有效候选数 | ≥ 15/cycle | 每日 |
| **验证通过率** | Stage 3 验证通过 / 提交验证 | ≥ 40% | 每周 |
| **回测完成率** | Stage 4 模拟完成 / 提交模拟 | ≥ 80% | 每周 |
| **质量达标率** | Stage 5 门禁通过 / 回测完成 | ≥ 30% | 每周 |
| **因子重复率** | 表达式指纹命中已有记录 / 总生成 | ≤ 10% | 每周 |
| **本地与官方一致性** | 本地 Sharpe 和官方 Sharpe 的 Spearman ρ | ≥ 0.6 | 每月 |
| **API 配额节省率** | (本地验证通过的候选数) / (总 API 验证调用) | ≥ 2x | 每月 |
| **用户满意度** | 可从 Pipeline 启动到完成无需人工干预的比例 | ≥ 80% | 每季度 |

### 4.2 埋点追踪方案

| 事件 | 触发时机 | 上报字段 | 存储 |
|------|---------|---------|------|
| `pipeline.cycle.start` | 每个研究周期开始 | run_id, cycle, strategy, dataset_id | events.jsonl |
| `pipeline.cycle.end` | 每个研究周期结束 | run_id, cycle, candidates_generated, candidates_validated, backtests_completed | events.jsonl |
| `candidate.generated` | Stage 1 生成候选 | alpha_id, expression_fingerprint, family, hypothesis, source_tags | candidates.jsonl |
| `candidate.scored` | Stage 2 评分完成 | alpha_id, total_score, prior_score, empirical_score | lifecycle.jsonl |
| `candidate.validated` | Stage 3 验证完成 | alpha_id, official_alpha_id, validation_status | lifecycle.jsonl |
| `backtest.submitted` | Stage 4 提交回测 | alpha_id, simulation_id, expression, settings | backtests.jsonl |
| `backtest.completed` | Stage 4 回测完成 | alpha_id, sharpe, fitness, turnover, pass_fail | backtests.jsonl |
| `submission.recorded` | Stage 6 提交 Alpha | alpha_id, official_alpha_id, mode(auto/manual), status | submissions.jsonl |
| `api.rate_limit` | BRAIN API 返回 429 | endpoint, retry_after, attempt | 日志 |
| `frontend.page_view` | 用户切换 Tab | tab_id, timestamp | 前端本地存储（可选） |
| `frontend.action` | 用户操作（启动/停止/排序/筛选/提交） | action, target, timestamp | 前端本地存储（可选） |

### 4.3 可观测性指标

研究可观测性快照 `research_observability_snapshot` 提供以下维度：

| 指标 | 说明 |
|------|------|
| unique_expression_count | 去重后的唯一表达式数量 |
| duplicate_expression_count | 重复表达式数量 |
| backtest_failure_rate | 回测失败比例 |
| official_guard_blocked_count | 官方调用守卫阻断次数 |
| retryable_error_count | 可重试错误次数 |
| risk_level | 当前风险等级（low/medium/high） |
| recommended_actions | 系统推荐的操作 |

---

## 附录

### A. 术语表

| 术语 | 定义 |
|------|------|
| **Alpha** | 量化因子表达式，用于预测股票未来收益 |
| **FASTEXPR** | BRAIN 平台的表达式语言 |
| **Sharpe** | 风险调整后收益指标 |
| **Fitness** | BRAIN 定义的复合指标：Sharpe × sqrt(|Returns| / max(Turnover, 0.125)) |
| **Turnover** | 持仓周转率 |
| **CSI 300** | 沪深 300 指数 |
| **MCP** | Model Context Protocol，LLM Agent 工具调用协议 |
| **SSE** | Server-Sent Events，服务器推送事件 |
| **CSP** | Content Security Policy，内容安全策略 |

### B. 参考链接

- BRAIN API 文档: https://api.worldquantbrain.com
- 项目仓库: <your-repository-url>
- QuantGPT 参考: https://github.com/Miasyster/QuantGPT

### C. 变更记录

| 版本 | 日期 | 变更内容 | 作者 |
|------|------|---------|------|
| v1.0 | 2026-05-27 | 初版 PRD，覆盖 v0.3.0 已交付功能 | Product Team |
| v1.1 | 2026-05-27 | 补充验收标准、埋点方案、红线合规 | Product Team |
