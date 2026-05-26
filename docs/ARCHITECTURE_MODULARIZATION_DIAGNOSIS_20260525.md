# 架构模块化诊断报告

日期: 2026-05-26
范围: `D:\Works\WorldQuant BRAIN Alpha`
说明: 以下结论以当前仓库实现和本轮重新执行的验证基线为准。

## 执行摘要

本轮架构模块化重构已经完成本地可执行闭环。工具注册边界、提示词外置、受限批量模拟、失败计数、轻量市场数据缓存、参数搜索、本地告警，以及对应的回归测试和质量门都已落地。  
本次续作进一步补齐了本地产品化扩展：向量化市场数据视图、容量受限的全市场回测规划、受控并行回测执行器、多轮参数搜索编排和多通道告警路由。仍然未完成的是需要真实外部平台或凭据的生产接入，例如重型行情数据后端、官方全市场实盘回测账号策略和企业监控平台配置。

## 当前结论

| 维度 | 已完成 | 仍然存在的 Gap | 备注 |
|---|---|---|---|
| 功能闭环 | `agent_tool_registry.py` 已统一 MCP/Web/助手工具边界；`run_simulation_batch` 已有 per-item 验证、重复预检、失败计数和受限并发；`run_parallel_backtest` 已提供多市场受控执行入口 | 真实官方全市场执行仍需凭据和账号策略 | 现状是 bounded concurrency，不是无限扩张的批量引擎 |
| 数据链路 | 提示词已从代码移到 `brain_alpha_ops/research/prompts/assistant_system_prompt.txt`；轻量 `market_data_cache` 已可本地刷新和摘要；`market_data_vector` 已能生成符号 x 特征矩阵 | 真实生产行情源尚未接入 | 当前是本地可验证的向量化视图，不冒充外部数据平台 |
| 参数管理 | `score_candidate` / `run_simulation` / `run_simulation_batch` 的流程边界已清晰，参数搜索与多轮编排工具已接入 | 大规模演化搜索仍需产品预算策略 | 现有实现已经有 rounds / keep_top / mutation budget |
| 用户体验 | 角色、流程和“先评分后回测”的提示词已经明确；本地告警和多通道路由可写入并可选 webhook | 实时进度反馈和运营面板级交互仍可加强 | 现在已是可用的本地工作流 |
| 评分体系 | 轻量评分、深度模拟、批量失败计数和参数搜索评分已分层 | 评分归因和可视化还可继续细化 | 现有实现已经足够支撑日常研究流转 |
| 监控告警 | 本地观测、告警日志、健康诊断和多通道告警路由已覆盖；告警工具 schema 已暴露 metadata | 外部监控凭据和平台配置尚未正式接入 | 这属于部署与运维扩展层 |

## 关键完成项

- `brain_alpha_ops/agent_tool_registry.py` 统一注册了 `score_candidate`、`run_simulation`、`run_simulation_batch` 等接口，并保留 QuantGPT 风格别名。
- `brain_alpha_ops/research/prompt_templates.py` 和 `brain_alpha_ops/research/prompts/assistant_system_prompt.txt` 已将系统提示词外置，明确角色与工作流。
- `brain_alpha_ops/agent_tools.py` 已接入批量模拟、参数搜索、告警、assistant 相关工具，并保持受限调用边界。
- 新增 `brain_alpha_ops/research/market_data_cache.py`、`brain_alpha_ops/research/parameter_search.py`、`brain_alpha_ops/research/alerting.py`，补齐了本地研究的轻量缓存、搜索和通知能力。
- 新增 `brain_alpha_ops/research/market_data_vector.py`、`brain_alpha_ops/research/parallel_backtest.py`、`brain_alpha_ops/research/search_orchestrator.py`，补齐本地向量化视图、并行回测规划和多轮参数搜索编排。
- `brain_alpha_ops/research/parallel_backtest.py` 现在包含 `ParallelBacktestExecutor`，支持受控多市场执行、per-job 失败记账和容量限制。
- `brain_alpha_ops/agent_tools.py` 现在注册并执行 `run_parallel_backtest`，继续保留 live API confirmation、重复表达式预检、验证后提交和并发上限。
- `brain_alpha_ops/agent_guidance_tools.py` 已承接 assistant guidance 的纯转换逻辑，使 `agent_tools.py` 回到模块体积门禁以内。
- `brain_alpha_ops/research/parameter_search.py` 已加入确定性兜底变体生成，避免参数搜索预算被底层优化器少量返回打空。
- 为避免主模块继续膨胀，进一步抽出 `brain_alpha_ops/agent_research_tools.py`、`brain_alpha_ops/research/observability_extensions.py`、`brain_alpha_ops/research/observability_errors.py`。
- 相关回归测试已覆盖注册器、别名、提示词模板、MCP 元数据、批量失败语义、新研究工具与观测扩展。

## 问题攻坚清单

- 数据并行化（P1）：本地 vectorized 视图已完成；真实生产行情源接入仍需外部依赖决策。
- 并行回测（P1）：全市场回测规划与受控执行器已完成；真实官方全市场生产执行仍受账户、速率和凭据约束。
- 搜索优化（P2）：多轮参数搜索编排已完成；大规模演化搜索可继续作为产品预算策略扩展。
- 监控告警（P2）：本地多通道路由已完成；外部监控平台配置仍需实际渠道和凭据。

## 当前任务状态

### 已完成任务

- [x] 工具注册器、提示词外置、批量模拟和失败记账已完成。
- [x] 轻量市场数据缓存、参数搜索和本地告警已实现并接入工具层。
- [x] 向量化市场数据视图、并行回测规划、多轮参数搜索编排和多通道告警路由已实现并接入工具层。
- [x] 受控并行回测执行器、`run_parallel_backtest` 工具入口、per-job 失败记账和标量/数组参数归一化已完成。
- [x] assistant guidance helper 抽取和参数搜索确定性兜底已完成，模块体积门禁恢复绿色。
- [x] 观测模块增量逻辑已拆分，模块体积门禁已恢复。
- [x] 相关测试、模块体积审计、标准质量门和严格官方上下文质量门都已通过。

### 尚未完成任务

- [ ] 真实生产行情源或重型数据后端接入。
- [ ] 真实官方全市场生产执行的凭据、账号策略和市场范围配置。
- [ ] 企业级外部监控平台/凭据配置。

## 验证基线

- `tests/test_market_data_cache.py tests/test_parameter_search.py tests/test_alerting.py tests/test_new_research_tools.py tests/test_market_data_cache_observability.py tests/test_batch_backtest_coordinator.py tests/test_agent_tools.py tests/test_mcp_server.py tests/test_research_observability.py tests/test_research_memory.py tests/test_assistant_request.py tests/test_windows_packaging.py`: `79 passed`
- `scripts/check_module_size.py --json`: passed, no oversized-module findings
- Productization focused slice: `16 passed`
- `tests/test_parallel_backtest.py tests/test_new_research_tools.py tests/test_agent_tools.py tests/test_mcp_server.py`: `45 passed`
- `tests/test_parameter_search.py tests/test_search_orchestrator.py tests/test_new_research_tools.py`: `9 passed`
- `scripts/quality_gate.py --skip-tests --json`: passed
- `scripts/quality_gate.py --strict-official-context --skip-tests --json`: passed, including strict freshness
- Full repository pytest: `738 passed`

## 结论

本轮已经把“工具边界、提示词边界、批量模拟边界、轻量缓存、向量化视图、参数搜索、并行规划、受控并行执行、告警路由、观测扩展”都落成了可运行代码。  
因此，最准确的结论是“本地可执行闭环和本地产品化扩展均已完成；剩余项是需要真实外部平台、凭据或生产策略的部署接入”。
