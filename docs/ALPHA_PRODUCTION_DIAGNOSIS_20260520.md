# Alpha 生产系统诊断报告与 Gap 矩阵

日期: 2026-05-20  
范围: `D:\Works\WorldQuant BRAIN Alpha` 本地项目，对标 QuantGPT 公开架构与 WorldQuant BRAIN API 契约。  
参考: https://github.com/Miasyster/QuantGPT, https://www.quant-gpt.com/, https://platform.worldquantbrain.com/learn/documentation/consultant-information/brain-api

## 一页纸诊断

本地系统已经具备 Alpha 生产闭环: 官方上下文同步、候选生成、官方表达式校验、官方回测提交/轮询、评分归因、Pass/Fail 门禁、提交安全、Web/SSE 实时反馈、JSONL/历史回溯与断点续跑。当前主要风险不再是缺少模块，而是“看似科学”的本地增强逻辑不能改写 BRAIN 官方硬门槛，所有评分和提交决策必须保留 settings、阈值、数据集、字段/算子来源的可追溯证据。

本轮攻坚已把官方回测 settings 写入候选提交记录，并让评分系统按真实 settings 选择 delay=0/1 阈值；同时移除 market regime 对 LOW_SHARPE/LOW_FITNESS 官方硬门槛的乘法调整，仅保留为归因/校准元数据。红线验证新增阻断项，防止后续代码再次用本地因子改写官方硬门槛。

## Gap 分析矩阵

| 维度 | 当前状态 | Gap/风险 | 优先级 | 已落地/建议 |
|---|---|---|---|---|
| 功能闭环 | 生成 -> 校验 -> 回测 -> 评分 -> 门禁 -> 提交 -> 历史回溯已连通 | 历史回放仍偏状态浏览，完整 replay 体验可继续增强 | P2 | 保持 GuidedPipeline/checkpoint 主路径，后续增强 Run History 浏览 |
| BRAIN 技术合规 | 字段/算子、API path、settings enum 已集中到 canonical；红线 72/72 PASS | 任何本地评分增强都可能误伤官方硬门槛 | P0 | 新增 redline-2d，阻断 market regime 改写硬门槛 |
| 参数准确性 | delay=0/1、threshold、settings_trace 可追溯 | 旧评分入口未显式携带官方回测 settings | P0 | `submission.settings` 持久化，`build_scorecard(..., settings=...)` 使用真实 settings |
| 数据链路 | official fields/operators/datasets、dataset_id、JSONL、run_history、cache audit 已覆盖 | Dataset 新鲜度依赖官方权限与限流 | P2 | 继续用 `/data-sets` 优先，同步失败只允许从官方 fields 元数据派生 |
| 体验 | Web/SSE、结构化错误、归因详情、断点续跑、history 已具备 | 失败后的下一步操作可以继续产品化 | P2 | 保持可操作错误提示，扩展失败候选的“一键重试/派生”视图 |
| 评分体系 | OfficialScoringSystem、GateConfig、ScoreHistoryDB、归因树已实现 | 校准样本越多越可靠；官方硬门槛必须零偏差 | P1 | 本轮修复 delay-aware settings 和 regime 零偏差；继续积累真实 pass/fail 样本 |

## 严重度排序攻坚清单

| 严重度 | 问题 | 修复方案 | 状态 |
|---|---|---|---|
| P0 | market regime 乘法调整会改变 BRAIN 官方 LOW_SHARPE/LOW_FITNESS 阈值 | 删除硬门槛乘法调整，保留 regime 元数据；新增红线阻断检查 | 已修复 |
| P0 | 官方回测 settings 未进入评分主入口，delay=0 可能按 delay=1 阈值评分 | 提交回测时持久化 `candidate.submission["settings"]`，评分读取 settings_trace | 已修复 |
| P0 | 参数全链路可溯缺少自动化约束 | 红线-4 检查 `build_scorecard` 同时接受 `params` 与 `settings` | 已修复 |
| P1 | Web/评分归因需要把硬门禁、软门禁、失败项、建议结构化展示 | 保持 `OfficialScoringSystem` 和 `/api/scoring/attribution` 结构化输出 | 已具备 |
| P1 | QuantGPT 对标中的 API guard、反过拟合、不可篡改证据链仍可强化 | 将 redline/anti-overfit/score attribution 注入下一轮 LLM 生成上下文 | 建议升级 |

## QuantGPT 对标升级建议

| 优先级 | 方向 | 对标点 | 本地建议 |
|---|---|---|---|
| P1 | 架构与模块化 | QuantGPT 强调 Agent 工具、HTTP API、公开验证、治理边界 | 继续拆薄 `pipeline.py`，保持 BRAIN adapter、scoring、gating、submission 的边界 |
| P1 | 数据获取效率 | 缓存、批任务、公开验证链路 | 把 cache freshness 和 stale warning 更清晰暴露到 Web |
| P1 | LLM 调用链路 | 跨模型评审、工具约束、反过拟合反馈进入进化循环 | 将 redline report、score attribution、anti-overfit 结果注入 assistant context |
| P2 | 策略执行/回测 | Walk-forward、OOS、反过拟合直接影响评分和进化 | 让 rolling validation/anti-overfit 直接调整生成权重与二次融合策略 |
| P2 | 异常与日志 | API guard、不可篡改 snapshot、结构化错误 | 扩展 JSONL/run_history 为更强的不可变快照与前端错误 taxonomy |

## 自动化验证

- `python -m brain_alpha_ops.compliance.redline_verifier --block --json`: PASS, 72/72, failed=0, warnings=0
- `python scripts/quality_gate.py --skip-tests --json`: PASS
- `python -m pytest`: 518/518 PASS；仅有 `.pytest_cache` 写入权限警告。完整 pytest 后 Windows 额外打印一次 access violation 栈，但退出码为 0，且单跑 `tests/test_web_build_inline.py` 为 5/5 PASS。

