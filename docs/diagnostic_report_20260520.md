# BRAIN Alpha Ops 一页纸诊断报告与 Gap 矩阵

**日期**: 2026-05-20 | **基线**: 本地项目 + QuantGPT 架构对照 | **验证结果**: `redline_verifier` 61/61 PASS，`quality_gate.py --skip-tests --json` PASS

## 一页纸诊断

系统已经从"研究辅助脚本"推进到"受 BRAIN API 约束的本地 Alpha 生产系统"：生成、官方上下文、验证、仿真、评分、门禁、提交、安全与 Web 控制台均有闭环。当前最大改进点不是再补概念，而是把已有能力继续产品化：更细的模块边界、更稳定的数据版本溯源、更高效的批量官方调用、以及把评分归因/红线结果贯穿 Web 与 CLI。

## Gap 分析矩阵

| 维度 | 当前状态 | Gap | 优先级 | 修复方案/落地代码 |
|---|---|---|---|---|
| 功能闭环 | 生成→验证→仿真→评分→门禁→提交已具备；断点和历史层已在 `ux/guided_pipeline.py` | Guided UX 尚未成为默认 CLI/Web 入口 | P1 | 将 `GuidedPipeline` 接入 CLI/Web 生产按钮，复用 `CheckpointData` 与 `RunRecord` |
| BRAIN 技术合规 | 六条红线自动化验证 PASS；质量门禁已接入红线阻断 | 官方资料更新后需要定期刷新与元数据审计 | P1 | `scripts/quality_gate.py` 新增 `redline_verification`；继续使用 `fetch_official_context.py` + cache metadata |
| 参数准确性 | `QualityThresholds`、API 路径、Delay-aware 阈值集中管理 | 官方 pass/fail 与本地重构差异需显式归因 | P0 已修 | `OfficialScoringSystem._simulate_api_output()` 以 `official_metrics.pass_fail` 为优先真值并输出 deviation |
| 数据链路 | `OfficialDataLoader` 统一字段/算子/Dataset；Candidate 有 `dataset_id` | Dataset 元数据源仍由 fields 派生，缺官方 datasets 端点直连 | P2 | 保持派生可用，后续若 BRAIN 提供 dataset 端点则加 `list_datasets()` 适配 |
| 用户体验 | 前端语法、敏感扫描、Web payload、错误体系已覆盖；GuidedPipeline 提供引导/进度/断点 | Web 尚未完全展示红线报告、评分归因树、checkpoint 恢复入口 | P1 | 新增 Web API/组件展示 `ScoringResult.to_dict()`、`ComplianceReport.to_dict()` |
| 评分体系 | 三层 scorecard、硬门禁、归因树、可配置 GateConfig、JSONL 历史 | prior/empirical 自动校准还未成为在线闭环 | P2 | 扩展 `ScoreHistoryDB.convergence_stats()` 触发 `calibrate_weights.py` |

## 严重度问题清单与修复方案

| 严重度 | 问题 | 影响 | 状态/方案 |
|---|---|---|---|
| P0 | 官方 API 模拟状态曾依赖本地 `decision_band` | 会把官方 PASS 的候选错误模拟为 FAIL | 已修：状态优先使用 `official_metrics.pass_fail`，本地重构只作为 deviation 证据 |
| P0 | 技术红线此前不是聚合质量门禁的正式步骤 | 交接/打包可能漏跑合规校验 | 已修：`quality_gate.py` 接入 `redline_verification --block` |
| P1 | GuidedPipeline 未默认入口化 | 用户仍可能绕过流程引导/断点续跑 | 建议：CLI 增加 `guided-run`，Web 生产按钮走 guided wrapper |
| P1 | 评分归因未完全前端化 | 失败原因不够可操作 | 建议：详情页展示 hard/soft gate、top_failures、improvement_hints |
| P2 | Dataset 元数据无独立官方端点抓取 | Dataset 全量性依赖 fields 覆盖面 | 建议：若 API 支持，新增 datasets endpoint；否则保留 fields 派生并在 metadata 标记 source |
| P2 | pipeline/web/official adapter 仍偏长 | 维护和审计成本高 | 建议：按服务边界拆成 validation/simulation/finalization/context sync |

## 六大技术红线执行口径

| 红线 | 强制要求 | 自动化验证 |
|---|---|---|
| 字段/算子禁自定义 | 只能来自 `data/official_fields.json` 与 `data/official_operators.json` | `RedLineVerifier` 检查 loader、context defaults、generator 来源 |
| 阈值零偏差 | Sharpe/Fitness/Turnover/Correlation/Concentration/SubUniverse 阈值集中一致 | `CANONICAL_THRESHOLDS` 对比配置与 dataclass |
| Dataset ID 全量可用 | `official_datasets.json` 可加载，Candidate 可追溯 `dataset_id` | 红线-3 + dataset selection tests |
| 参数全链路可溯 | 配置版本、scorecard schema、events/run_id 可追踪 | 红线-4 + `config_hash` |
| 要素全覆盖 | BRAIN Alpha Check 硬门禁全部覆盖 | 红线-5 + `empirical_score` hard gates |
| 代码强对齐 | API base/path/settings/metric names 对齐 BRAIN | 红线-6 + official adapter tests |

## QuantGPT 对标升级建议

| 优先级 | 维度 | QuantGPT 可借鉴点 | 本项目落地 |
|---|---|---|---|
| P1 | 架构与模块化 | Agent tools + services + UI 分层清晰 | 继续拆 `pipeline.py` 与 Web handler；保留 BRAIN API 合规层为唯一外部入口 |
| P1 | 数据获取与处理效率 | 批量任务、缓存、并发控制 | 扩展官方上下文缓存 metadata；官方调用继续使用 rate-limit guard 与 slot coordinator |
| P1 | LLM 提示词与调用链路 | 知识库、失败记录、交叉评审 | 强化 `assistant.py` 的 prompt diagnostics，将 redline/score attribution 放入 LLM 上下文 |
| P2 | 策略执行与回测 | mutation/crossover、rolling validation、anti-overfit | 已有 robustness/rolling/secondary fusion；下一步做自动 A/B 与假说库回写 |
| P2 | 异常处理与日志 | 任务状态机、进度流、结构化错误 | 将 `brain_alpha_ops.errors.classify_error` 与 `ux.classify_error` 合并为单一错误知识库 |

## 本次新增/更新代码

- `brain_alpha_ops/scoring/official_scoring.py`: 官方 Pass/Fail 优先模拟、deviation 明细、门禁与归因输出。
- `scripts/quality_gate.py`: 接入六大红线阻断验证。
- `tests/test_official_scoring_system.py`: 覆盖评分模拟、可配置 GateConfig、ScoreHistoryDB。
- `tests/test_quality_gate.py`: 锁定质量门禁中的红线步骤。
- `README.md`: 更新质量门禁、红线命令、评分/UX 能力说明。
