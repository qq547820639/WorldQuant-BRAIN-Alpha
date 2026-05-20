# BRAIN Alpha Ops 一页纸诊断报告与 Gap 分析矩阵

日期: 2026-05-20
范围: 本地 `D:\Works\WorldQuant BRAIN Alpha` 项目 + QuantGPT 公开架构对照
当前收尾验证: `scripts/quality_gate.py --skip-tests --json` PASS; `brain_alpha_ops.compliance.redline_verifier --block --json` PASS 72/72; 聚焦 pytest PASS 108/108; `dist\BrainAlphaOps.exe --smoke-test --port 8765` PASS。当前 bundled Python 已安装项目 `test` extra 与 PyInstaller。

## 一页纸诊断

项目已经具备 Alpha 生产闭环: 官方上下文加载、候选生成、官方验证/仿真、评分、门禁、提交安全、Web 控制台、断点/历史与质量门禁均已成形。最大的风险不再是“没有模块”，而是多层配置与 BRAIN 平台契约漂移、评分/归因在前端展示不够完整、以及 LLM 研究链路还没有把红线/评分/反过拟合结果完全变成下一轮生成约束。

本次修复把 BRAIN 平台参数枚举收敛到 `brain_alpha_ops/brain_api/canonical.py`，并让 `config.py`、`web_config.py`、`redline_verifier.py` 共用同一来源；红线-6 新增配置/Web 枚举漂移阻断检查。本轮又从官方发布前端契约确认并接入 `https://api.worldquantbrain.com/data-sets`，让 Dataset 清单优先来自官方独立端点，fields 派生仅作为官方字段元数据兜底。这样“字段/算子禁自定义、阈值零偏差、Dataset ID、参数可溯、要素覆盖、代码强对齐”不再只检查业务逻辑，也覆盖配置入口和官方 Dataset 直取入口。

## Gap 分析矩阵

| 维度 | 当前状态 | Gap | 优先级 | 修复/攻坚方案 |
|---|---|---|---|---|
| 功能闭环 | 生成 -> 验证 -> 仿真 -> 评分 -> 门禁 -> 提交已具备，Web/SSE/JSONL 历史齐全；Web 生产按钮默认走 guided/checkpoint 主路径 | checkpoint 历史回放仍可继续增强为更完整的浏览器视图 | P2 | 在现有 checkpoint status 基础上扩展历史筛选/回放 |
| BRAIN 技术合规 | 红线验证 71/71 PASS，字段/算子来自官方 JSON，API 路径受控 | 配置/Web 枚举此前可能与红线 canonical 漂移 | P0 已修 | 新增 `brain_api/canonical.py` + 红线-6 枚举对齐检查 |
| 参数准确性 | 阈值、Delay-0/1、API path、评分 schema 可追踪 | 官方资料刷新后仍需周期审计 cache 元数据 | P1 | 保持 `quality_gate.py` 的 redline/cache 步骤，定期跑 `fetch_official_context.py` |
| 数据链路 | `official_fields/operators/datasets.json`、`dataset_id`、JSONL 历史、SQLite 索引已覆盖；本地 DatasetSelector、fields-derived datasets、canonical enum 均已验证；官方 `/data-sets` 已接入 `OfficialBrainAPI.list_datasets()` 与 Web/同步链路 | Dataset 新鲜度仍受官方限流与账号权限影响，需保留官方 fields 元数据兜底 | P2 已修 | 同步时优先拉官方 `/data-sets`，失败再从官方 fields 的 `dataset` 元数据派生，严禁自定义 Dataset ID |
| 用户体验 | GuidedPipeline 提供流程引导、实时状态、可操作错误、断点续跑、历史回溯；Web 已显示红线/checkpoint 概览；详情页已接入 score attribution、hard/soft gate、top failures、improvement hints；断点续跑复用同一生产启动/SSE 主路径 | 历史回放仍偏状态展示 | P2 | 增强 run history 浏览与回放交互 |
| 评分体系 | `OfficialScoringSystem` 支持官方 pass/fail 优先、零偏差标记、GateConfig、归因树、ScoreHistoryDB；`/api/scoring/health` 已暴露 AutoCalibrator 状态并支持显式触发 | 校准策略仍需更多真实 PASS 样本持续验证 | P2 已接入 | 继续用历史样本质量评估权重演进效果 |

## 严重度排序问题清单

| 严重度 | 问题 | 影响 | 状态 |
|---|---|---|---|
| P0 | 配置层、Web 层、红线层各自维护 BRAIN 参数枚举 | 会出现红线 PASS 但入口允许/拒绝错误参数 | 已修: canonical 单一来源 + 红线阻断漂移 |
| P0 | `brain_api.__init__` 急切导入 official adapter | 轻量 canonical 导入会触发 config/official 循环 | 已修: `brain_api.__getattr__` lazy export |
| P0 | 红线验证曾只覆盖业务逻辑，未覆盖配置枚举漂移 | “代码强对齐”口径不完整 | 已修: 红线-6 增加 config/web enum alignment |
| P1 | 完整 pytest 当前运行环境缺依赖 | 无法在 bundled runtime 复现完整测试结果 | 已修: 安装项目 `test` extra，full pytest 512/512 PASS |
| P1 | Web 详情页归因展示不足 | 用户看见 FAIL 但操作性不足 | 已修: 后端支持 candidate 或 alpha_id 查找，前端展示 hard/soft gates、top failures、improvement hints、attribution tree |
| P2 | Dataset 独立官方端点缺失 | Dataset 全量性此前依赖 fields 覆盖；本地派生链路已通过测试 | 已修: 官方发布契约确认 `/data-sets`，已补 `list_datasets()`、配置路径、红线路径对齐与同步链路优先调用 |

## 当前执行清单状态

| 状态 | 任务 | 落地结果 | 验证 |
|---|---|---|---|
| 已完成 | P0 canonical 单一来源 | `brain_alpha_ops/brain_api/canonical.py` 统一阈值、API path、settings、metrics；`config.py`、`web_config.py`、`redline_verifier.py` 共用 canonical | `redline_verifier --json` 71/71 PASS |
| 已完成 | P0 lazy export 防循环导入 | `brain_alpha_ops/brain_api/__init__.py` 延迟导出 `MockBrainAPI`、`OfficialBrainAPI` | `compileall` PASS |
| 已完成 | P0 红线-6 覆盖配置/Web 枚举漂移 | 红线验证扩展到 config/web enum alignment，阻断入口契约偏移 | full `quality_gate.py --json` PASS |
| 已完成 | P1 Web 评分归因产品化 | `/api/scoring/attribution` 支持 `candidate` 或 `alpha_id`，按 `candidates.jsonl` 与 `run_history` 回查；详情页展示硬门禁、软门禁、Top failures、改进建议与归因树 | smoke PASS；`check_frontend_syntax.py` PASS；新增 `tests/test_web_redline_scoring.py` |
| 已完成 | P1 完整 pytest 复现 | bundled Python 已安装 `.[test]`，完整测试集可复现 | full `pytest` 516/516 PASS；full `quality_gate.py --json` PASS |
| 已完成 | P1 checkpoint 续跑成为 Web 主路径 | Web 生产启动默认设置 `guided=true`；断点恢复复用 `resumeProductionFromCheckpoint()`，统一进入同一启动、SSE 和按钮状态链路 | frontend inline sync PASS；syntax PASS；full pytest PASS |
| 已完成 | P2 Dataset 官方直取可执行性复核 | 已直接复查 WorldQuant/BRAIN 官方发布入口；官方前端 bundle 明确暴露 `https://api.worldquantbrain.com/data-sets`、`/data-fields`、`/data-categories`、`/data-sets/search`；API 端点响应头可达但本轮被官方限流 | 2026-05-20 官方发布契约复核完成；定向测试 PASS；质量门禁 PASS |
| 已完成 | P2 Dataset 独立官方端点 | `OfficialAPIConfig.data_sets_path`、`CANONICAL_API_PATHS["data_sets"]`、`OfficialBrainAPI.list_datasets()` 已实现；Web 同步/云端上下文刷新优先使用官方 `/data-sets`，失败时仅从官方 fields 元数据派生 | 新增 `tests/test_official_adapter.py::test_list_datasets_*`、`tests/test_config.py::test_official_api_paths_use_canonical_contract`、`tests/test_web_sync_payload.py::test_sync_cloud_alphas_payload_prefers_official_datasets`；full `pytest` PASS |
| 已完成 | P2 自动校准闭环 | `/api/scoring/health` 返回 `auto_calibration` 状态，支持 `auto_calibrate=true` 显式触发 `AutoCalibrator.calibrate()` 并持久化 `scoring_calibration.json` | web scoring health test PASS；full pytest PASS |

## 六大技术红线验证口径

| 红线 | 强制要求 | 自动化验证代码 |
|---|---|---|
| 字段/算子禁自定义扩展 | 只能来自官方 JSON/context loader | `RedLineVerifier` 红线-1 |
| 阈值零偏差 | Sharpe/Fitness/Turnover/Correlation/Concentration/SubUniverse 阈值一致 | `CANONICAL_THRESHOLDS` + 红线-2 |
| Dataset ID 全量可用 | 官方 `/data-sets` 可直取，`official_datasets.json` 可加载，Candidate 可追踪 `dataset_id` | 红线-3 + `OfficialBrainAPI.list_datasets()` |
| 参数全链路可溯 | config version、run_id、events、score schema、config_hash 可追踪 | 红线-4 + scoring result |
| 要素全覆盖 | BRAIN Alpha Check 硬门禁全覆盖 | 红线-5 + `empirical_score` |
| 代码强对齐 | API path/settings/metrics/config/web 枚举同源 | 红线-6 + `brain_api/canonical.py` |

## QuantGPT 对标升级建议

| 优先级 | 维度 | QuantGPT 可借鉴点 | 本项目建议 |
|---|---|---|---|
| P1 | 架构与模块化 | Agent research、HTTP API、本地部署、GitHub 存证、公开验证闭环 | 继续拆薄 `pipeline.py`/Web handler，把 BRAIN adapter 和 scoring/gating 保持为清晰边界 |
| P1 | 数据获取效率 | 缓存、批量任务、公开校验链路 | 保持 context/similarity cache，增加 cache metadata freshness 告警到 Web |
| P1 | LLM 提示词链路 | 跨模型评审、语义清晰工具、代码化约束 | 将 redline report、score attribution、anti-overfit 结果注入 assistant context |
| P2 | 策略执行与回测 | 反过拟合、Walk-Forward/OOS、自动评分影响进化 | 让 rolling validation 和 anti-overfit 结果直接影响生成权重与二次融合 |
| P2 | 异常与日志 | API guard、可审计快照、不可篡改历史 | 扩展 JSONL/run_history 的不可变快照与错误 taxonomy 前端呈现 |

参考来源: QuantGPT 公开页描述 Agent 自主研究、回测、评分、反过拟合和 GitHub 存证闭环；Miasyster 工程笔记强调工具约束、API guard、反过拟合内建评分；WorldQuant BRAIN 官方页确认平台提供数据集和工具，用于实时构建和测试 Alpha。
