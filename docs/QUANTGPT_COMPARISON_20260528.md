# QuantGPT 对标分析与升级建议

- 调研日期：2026-05-28
- 对标对象：`https://github.com/Miasyster/QuantGPT` 及其公开文档/工程笔记
- 本轮范围：P3 文档交付，不扩大 P0-P2 已完成的代码修复范围

## 参考信息

- QuantGPT 官网（`https://www.quant-gpt.com/`）描述其目标是 Agent 自主研究、回测、评分、反过拟合、Cloud 验证、GitHub 信号存证和公开验证 API。
- QuantGPT 安装文档（`https://www.quant-gpt.com/guides/setup-quantgpt.html`）确认开源引擎通过 `make setup`、`restart.sh` 和 `python -m quantgpt --transport http` 启动，默认提供 HTTP API 与 MCP 工具。
- QuantGPT 入门文档（`https://www.quant-gpt.com/guides/first-factor.html`）列出 `run_backtest`、`run_anti_overfit`、`diagnose_factor` 等因子研究工具。
- Miasyster 工程笔记（`https://miasyster.github.io/en/`）强调三点：API guard 约束所有回测调用必须经过边界；反过拟合应进入评分与演化；跨模型评审用于降低单模型确认偏误。

## 五维对比

| 维度 | QuantGPT 公开设计 | BRAIN Alpha Ops 当前状态 | 差距判断 | 升级建议 |
|---|---|---|---|---|
| 架构 | Agent-native，HTTP API + MCP 工具链，强调 Harness 约束与 API guard。 | Python 包按 BRAIN adapter、research、scoring、compliance、web 分层；`web_handler_dispatch.py` 与 CLI/质量门已经形成边界。 | P1 非阻断：`web.py`、`pipeline.py` 仍偏大。 | 继续按工作流边界抽薄服务层；将“必须走 API/服务边界”的检查纳入模块尺寸和依赖策略门禁。 |
| 数据处理 | 本地行情缓存、股票池工具、滚动验证、Cloud/track record 公开验证。 | 官方 fields/operators/datasets 通过 metadata、hash、TTL、lineage 校验；云端 Alpha 缓存已支持同步与相似度阻断。 | PASS/P2：BRAIN 官方上下文更强，公开 track record 弱于 QuantGPT。 | 保持官方上下文为单源真相；新增 run-history 到报告导出的固定摘要，减少诊断与 E2E 手工漂移。 |
| LLM 提示 | `/factor-mine` 加载研究笔记和知识库，必要时 DeepSeek 交叉审查。 | Assistant context 已包含 redline、scoring attribution、anti-overfit、rolling validation、duplicate-expression evidence；新增 `cross_review_pipeline.py` 与三层知识库。 | PASS/P1：证据链已接近，跨模型执行仍依赖外部 LLM 配置。 | 将 cross-review 决策摘要写入候选生命周期，便于 Web 和提交账本统一展示证据。 |
| 策略执行 | 本地回测、反过拟合、评分、滚动验证，再上传 Cloud 做样本外跟踪。 | 本地回测引擎支持 FASTEXPR 子集和指标预筛；官方验证/模拟/质量门/提交安全串联；真实 E2E 已证明高相似候选会被阻断。 | PASS/P2：本地算子覆盖小于 QuantGPT 公开笔记中的 80+ 算子目标。 | 扩展本地 FASTEXPR 覆盖前，先基于真实失败样本排序；不要为覆盖率牺牲与 BRAIN 官方契约的一致性。 |
| 错误处理 | 工具约束、边界错误、失败模式诊断、可审计轨迹。 | Web/CLI 已结构化错误；敏感信息扫描、CSRF/session/stream token、SubmissionLedger 和红线门禁均 fail-closed。 | PASS：生产安全优先于便利性。 | 把 E2E console、job 账本、截图清单自动汇总到报告，避免人工复制时暴露敏感片段。 |

## 升级优先级

| 优先级 | 建议 | 验证方法 |
|---|---|---|
| P1 | 保持 `canonical.py` 单源真相，并让诊断报告自动引用最新 contract/gate 摘要。 | `python3 scripts/check_brain_contract.py --config config/run_config.json --json` |
| P1 | 将 cross-review 结果落到候选生命周期与 Web 详情，不只停留在研究层。 | `python3 -m pytest tests/test_enhanced_pipeline_components.py` |
| P2 | 为 E2E 报告生成器增加 job 账本、console 摘要、截图索引自动脱敏；基础版已落地到 `scripts/summarize_e2e_artifacts.py`，并嵌入当前 Web 控制台 contract 检查。 | `python3 scripts/summarize_e2e_artifacts.py --root . --evidence-dir data/e2e_screenshots --output-json docs/E2E_ARTIFACT_SUMMARY_20260528.json --output-md docs/E2E_ARTIFACT_SUMMARY_20260528.md --json` + `python3 scripts/check_web_console_contract.py --html brain_alpha_ops/web/index.html --json` + `python3 scripts/scan_sensitive_artifacts.py --root . --json --fail-on-findings` |
| P2 | 按真实失败样本扩展 `local_backtest_engine.py` 算子覆盖和诊断提示。 | 回测 slice + `python3 -m brain_alpha_ops.compliance.redline_verifier --block --json` |
| P2 | 区分 UI 中的“官方表达式验证通过”和“官方回测指标完成”。 | 前端 slice + 浏览器 E2E 复核 |

## 本轮结论

QuantGPT 更偏 Agent-native 研究基础设施，优势在 MCP/HTTP 工具边界、公开 track record、反过拟合进入演化循环；BRAIN Alpha Ops 更偏 WorldQuant BRAIN 生产合规运维，优势在官方契约单源真相、红线门禁、提交安全和真实 BRAIN 账号联机验证。当前 P0-P2 不需要再扩核心代码面；证据链自动化与报告脱敏已完成基础版，后续应继续把它固化为 E2E 归档流水线，而不是重写核心流程。
