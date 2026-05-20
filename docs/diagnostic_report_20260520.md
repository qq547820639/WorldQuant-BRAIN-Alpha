# BRAIN Alpha Ops 一页纸诊断报告与 Gap 矩阵

**日期**: 2026-05-20 | **基线**: 本地项目 + QuantGPT 架构对照 | **验证结果**: `compileall` PASS，`redline_verifier` 61/61 PASS，`quality_gate.py --json` PASS，`pytest` 508 passed

## 一页纸诊断

系统已经从"研究辅助脚本"推进到"受 BRAIN API 约束的本地 Alpha 生产系统"：生成、官方上下文、验证、仿真、评分、门禁、提交、安全与 Web 控制台均有闭环。红线验证、科学评分、评分归因、CLI/Web 评分端点和 Guided UX 入口已可运行。当前最大改进点不是再补概念，而是把已有能力继续产品化：更细的模块边界、更稳定的数据版本溯源、更高效的批量官方调用、以及把评分归因/红线结果完整展示到 Web 操作流。

## Gap 分析矩阵

| 维度 | 当前状态 | Gap | 优先级 | 修复方案/落地代码 |
|---|---|---|---|---|
| 功能闭环 | 生成→验证→仿真→评分→门禁→提交已具备；`guided-run` CLI 已接入 `GuidedPipeline` | Web 生产按钮尚未默认走 guided wrapper | P1 | Web 生产按钮复用 `GuidedPipeline` 的 checkpoint/history 语义 |
| BRAIN 技术合规 | 六条红线自动化验证 PASS；质量门禁已接入红线阻断 | 官方资料更新后需要定期刷新与元数据审计 | P1 | `scripts/quality_gate.py` 新增 `redline_verification`；继续使用 `fetch_official_context.py` + cache metadata |
| 参数准确性 | `QualityThresholds`、API 路径、Delay-aware 阈值集中管理 | 官方 pass/fail 与本地重构差异需显式归因 | P0 已修 | `OfficialScoringSystem._simulate_api_output()` 以 `official_metrics.pass_fail` 为优先真值并输出 deviation |
| 数据链路 | `OfficialDataLoader` 统一字段/算子/Dataset；Candidate 有 `dataset_id` | Dataset 元数据源仍由 fields 派生，缺官方 datasets 端点直连 | P2 | 保持派生可用，后续若 BRAIN 提供 dataset 端点则加 `list_datasets()` 适配 |
| 用户体验 | 前端语法、敏感扫描、Web payload、错误体系已覆盖；GuidedPipeline 提供引导/进度/断点；Web 已有红线/评分 API | Web 尚未完全展示 checkpoint 恢复入口与评分归因细节 | P1 | 详情页继续扩展 hard/soft gate、top_failures、improvement_hints 与 checkpoint 操作 |
| 评分体系 | 三层 scorecard、硬门禁、归因树、可配置 GateConfig、JSONL 历史 | prior/empirical 自动校准还未成为在线闭环 | P2 | 扩展 `ScoreHistoryDB.convergence_stats()` 触发 `calibrate_weights.py` |

## 严重度问题清单与修复方案

| 严重度 | 问题 | 影响 | 状态/方案 |
|---|---|---|---|
| P0 | 官方 API 模拟状态曾依赖本地 `decision_band` | 会把官方 PASS 的候选错误模拟为 FAIL | 已修：状态优先使用 `official_metrics.pass_fail`，本地重构只作为 deviation 证据 |
| P0 | 技术红线此前不是聚合质量门禁的正式步骤 | 交接/打包可能漏跑合规校验 | 已修：`quality_gate.py` 接入 `redline_verification --block` |
| P0 | CLI/Web 新评分与 UX 入口曾与真实类接口漂移 | `score`、`guided-run`、Web scoring endpoint 会运行时失败 | 已修：CLI/Web 使用 `Candidate.from_dict()` 与 `OfficialScoringSystem(config.ops)`，GuidedPipeline 补 `run/resume` |
| P0 | 包入口与 `research.__init__` 过早加载重依赖 | 单独运行红线/质量门禁会被无关 YAML/研究库依赖阻塞 | 已修：包级公开对象改为 lazy import，红线验证可独立启动 |
| P0 | `quality_gate.py` 作为脚本运行时缺少仓库根路径 | 缓存元数据审计步骤无法导入 `brain_alpha_ops` | 已修：脚本启动时把项目根目录加入 `sys.path` |
| P1 | Windows PowerShell 生成的 JSON 文件可能带 UTF-8 BOM | `brain-alpha-ops score --candidate-json file.json` 读取失败 | 已修：CLI 文件型 JSON 参数使用 `utf-8-sig` 读取 |
| P1 | Web 生产按钮未默认 guided 化 | 用户仍可能绕过流程引导/断点续跑 | 建议：Web 生产按钮走 guided wrapper |
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
| P2 | 异常处理与日志 | 任务状态机、进度流、结构化错误 | `error_knowledge.py` 已对齐核心 `ErrorInfo`；继续扩展 error taxonomy 与前端提示 |

## 本次新增/更新代码

- `brain_alpha_ops/scoring/official_scoring.py`: 官方 Pass/Fail 优先模拟、deviation 明细、门禁与归因输出。
- `brain_alpha_ops/cli.py`: 修通 `redline`/`score`/`guided-run` 与真实类接口。
- `brain_alpha_ops/web_redline_scoring.py`: 修通 Web 红线与评分归因端点，评分历史写入 `score_history.jsonl`。
- `brain_alpha_ops/ux/guided_pipeline.py`: 增加 `run()`、`resume()`、latest checkpoint 和 last-result summary。
- `brain_alpha_ops/__init__.py`、`brain_alpha_ops/research/__init__.py`: 改为 lazy import，避免红线/评分/质量门禁被无关研究依赖拖挂。
- `scripts/quality_gate.py`: 修复脚本方式运行时的仓库根目录导入路径。
- `tests/test_quality_gate.py`、`tests/test_cli.py`: 同步质量门禁步骤契约，并覆盖 UTF-8 BOM JSON 文件输入。

## 最新验证证据

- `python -m brain_alpha_ops.compliance.redline_verifier --json`: PASS，61/61 checks。
- `python scripts/quality_gate.py --json`: PASS，含 `python_compile`、config、dependency policy、redline、frontend inline/syntax、secret scan、cache metadata audit、pytest。
- `pytest`: 508 passed，1 个 pytest cache 写入 warning，不影响业务测试结果。
- `brain_alpha_ops.cli score --candidate-json <file> --json`: PASS，Windows UTF-8 BOM JSON 文件可读取，官方 `pass_fail=PASS` 输出 API deviation 0.0。
