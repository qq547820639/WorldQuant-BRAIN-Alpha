# QuantGPT 参考审查与 BRAIN Alpha Ops 升级交付报告

**日期**: 2026-06-05  
**仓库**: `/Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha`  
**参考仓库**: `https://github.com/Miasyster/QuantGPT`  
**本轮原则**: 先读后改、最小改动、红线机器校验、官方提交路径不越界

---

## 一页纸诊断

| 维度 | 当前结论 | Gap | 本轮处理 |
|---|---|---|---|
| 功能闭环 | Alpha 生成、评分、检查、前端展示、提交前置门禁均有实现；当前 ledger 无可提交候选 | 缺少满足 `official_alpha_id + official metrics + low similarity + submit_candidate` 的候选 | 保持提交阻断，运行 `check_live_submit_readiness.py --json` 确认 `ready_to_submit=false` |
| BRAIN 平台技术合规 | 字段 7780、算子 66、Dataset 17 均来自 `official_api` 快照；无自定义扩展 | 公开网页无法替代登录态 API 文档；合规以当前官方快照和红线脚本为准 | 新增官方调用节流策略追溯检查，红线门禁仍全绿 |
| 参数准确性 | 阈值、API path、settings enum、Dataset ID、官方上下文 lineage 均零偏差 | 旧配置中官方批次等待 6 秒、rate-limit backoff 15 秒偏激进 | 改为 60 秒保守策略，rate-limit retry 改 0，限速即停止本轮 |
| 数据链路 | `official_fields/operators/datasets` metadata 完整且未过期；dataset field count 合计一致 | 当前生产候选链路仍缺官方模拟指标 | 不伪造官方指标，保留可信环境继续模拟/验证边界 |
| 用户体验 | React 状态卡导航、中文错误、SSE、静态响应式和 a11y 检查已通过 | 本轮未做视觉大改；没有启动浏览器截图复审 | 保留现有 UI，验证构建、Vitest、静态响应式/可访问性 |
| 评分体系 | 三层评分、Pass/Fail 门禁、阈值 trace、多维归因均实现 | 当前候选因 turnover/相似度/无官方指标不可提交 | 维持 `research_only`，通过 live readiness 报告阻断提交 |

## Gap 分析矩阵

| 红线 | 当前状态 | 证据 |
|---|---|---|
| 字段/算子禁自定义扩展 | PASS | `verify_canonical_compliance.py`: valid fields 7780, valid operators 66, invalid 0 |
| 阈值零偏差 | PASS | `min_sharpe=1.25`, `min_fitness=1.0`, `platform_max_turnover=0.70`, all match |
| Dataset ID 全量可用 | PASS | 17/17 valid IDs: `pv1`, `fundamental6`, `model77`, etc. |
| 参数全链路可溯 | PASS | `check_parameter_traceability.py`: settings/thresholds/API/rate-limit/Dataset/context all pass |
| 要素全覆盖 | PASS | 官方上下文 field count 7780、operator count 66、dataset count 17 |
| 代码强对齐 | PASS | `final_release_gate.py`: all redlines true, findings empty |

## 清单式问题攻坚

| 优先级 | 类别 | 状态 | 处理结果 |
|---|---|---|---|
| P0 | 架构与依赖 | PASS with debt | 当前 gate 未再报告架构阻塞；`web.py` 拆分债务保留为后续结构优化，不做本轮无关大重构 |
| P0 | 核心逻辑 | PASS | 全量 pytest 在 quality gate 中通过；提交前候选不足被阻断 |
| P0 | 合规性 | PASS | 官方上下文 metadata 未过期，红线脚本通过 |
| P1 | 业务映射 | PASS | React API/static checks 通过；live readiness 明确候选不可提交原因 |
| P1 | 评分系统 | PASS | 官方模拟输出零偏差检查通过；新增 rate-limit policy check |
| P2 | 用户体验 | PASS local static | React build/Vitest/static a11y/responsive checks 通过 |
| P2 | 测试覆盖 | PASS | 质量门禁全量 pytest 覆盖；新增节流策略单测 |
| P3 | 代码质量 | PASS after fix | 新增逻辑拆到 `rate_limit_policy.py`，模块大小门禁恢复 |

## QuantGPT 参考对比

| 参考点 | QuantGPT 模式 | 本仓库现状 | 升级决策 |
|---|---|---|---|
| Agent 工具箱 | MCP/REST/Web UI 三入口 | 本仓库也有 MCP、Web、pipeline 工具 | 保持多入口，优先加强机器门禁 |
| 表达式与回测 | Parser、Backtest、Validation 分层 | 本仓库已有 expression/backtest/scoring/official validation | 不引入 QuantGPT 自定义算子，避免违反 BRAIN 红线 |
| 数据管道 | 多数据源 + cache | 本仓库以官方 context + 本地 storage 为核心 | 保持官方 context 为生产要素来源 |
| 进化与防过拟合 | mutation/crossover/anti-overfit | 本仓库已有 evolution、anti_overfit、candidate pool | 不做大范围迁移，仅记录可借鉴方向 |
| UI | 监控面板 | 状态卡优先的中文 React 控制台 | 本轮验证而不重绘，避免无关 UI 扩散 |

## 本轮代码改动

| 文件 | 原因 |
|---|---|
| `brain_alpha_ops/brain_api/rate_limit_policy.py` | 新增官方调用并发、批次等待、退避、stale context 策略校验 |
| `scripts/check_parameter_traceability.py` | 将 rate-limit policy 纳入参数全链路追溯，作为 release audit 的机器检查项 |
| `tests/test_canonical_compliance.py` | 覆盖保守策略通过、激进外部调用策略被捕获 |
| `config/run_config.json` | 将 `official_retry_pause_seconds` 与 `rate_limit_backoff_seconds` 调整为 60 秒，`rate_limit_retry_attempts` 调整为 0，限速即停止本轮 |
| `docs/ALPHA_PRODUCTION_DIAGNOSIS_20260522.md` | 同步配置收紧后的参数审计 hash |
| `brain_alpha_ops/web/react_app/dist/*` | React production build 刷新产物 |
| `docs/QUANTGPT_COMPREHENSIVE_REVIEW_AND_UPGRADE_20260605.md` | 本轮结构化交付报告 |

## 验证结果

| 验证 | 结果 |
|---|---|
| `pytest tests/test_canonical_compliance.py::TestParameterTraceabilityRateLimitPolicy ...` | 3 passed |
| `check_parameter_traceability.py --config config/run_config.json --json` | PASS, 0 errors, 0 warnings, includes `rate_limit_policy_check` |
| `verify_canonical_compliance.py --config config/run_config.json --json` | PASS, 6/6 checks, 0 deviations |
| `final_release_gate.py --config config/run_config.json --json` | PASS, all redlines true |
| `pytest tests/test_parameter_audit.py tests/test_canonical_alignment.py tests/test_config.py tests/test_canonical_compliance.py -q` | 150 passed |
| React static checks | 28 passed |
| `vite build` | PASS, production assets generated |
| `vitest run` | PASS, 5 tests |
| `check_v5_defect_tracking.py` | PASS |
| `check_prod_defect_tracking.py` | PASS |
| `check_live_submit_readiness.py --json` | `ready_to_submit=false`, eligible count 0 |
| `quality_gate.py` | PASS after module-size/report-sync fixes |

## 未覆盖与风险

1. 未执行真实官方模拟或提交；当前候选缺 `official_alpha_id`、official metrics，且存在 high cloud similarity / high turnover generation risk，不能被声称为可提交。
2. 公开网页不能提供完整登录态 BRAIN API 文档；本轮以本地 `official_api` 来源快照和自动化红线脚本做可验证闭环。
3. `web.py` 结构债务不再是当前门禁阻塞；如要继续拆分，应另起单独重构任务，避免影响已通过的路由契约。
4. 本轮未做浏览器截图 A/B 视觉迭代，因为没有改 UI 布局；UI 只做构建、组件测试、静态 a11y/responsive 守卫验证。

## 任务状态跟踪

- [x] 全面阅读当前仓库结构、关键报告、配置、红线脚本、参考 QuantGPT 架构
- [x] 输出一页纸诊断报告与 Gap 矩阵
- [x] 技术红线验证与自动化比对
- [x] 参数全链路追溯增强
- [x] 官方调用节流/退避策略收紧
- [x] 评分系统零偏差检查
- [x] 前端构建、组件测试、静态响应式/a11y 验证
- [x] 缺陷跟踪脚本验证
- [x] 质量门禁验证
- [ ] 生成新的官方可提交候选并取得官方模拟 metrics：当前候选条件不足，需可信环境继续执行
- [ ] 大规模架构拆分：非本轮必要改动，建议单独排期

## 实际调用角色摘要

| 角色/技能 | 工作摘要 |
|---|---|
| context-management | 恢复历史缺陷跟踪、官方上下文、提交边界记忆，并以当前工作树复核 |
| superpowers | 按设计/实现/验证闭环执行；用户已给出完整方案，视为本轮实施授权 |
| agent-team-orchestration | 进行角色分配；受工具规则限制未实际 spawn 子代理 |
| fullstack-dev | 检查配置、API 路径、官方调用策略、前后端契约 |
| ui-ux-pro-max / frontend-design | 复核状态卡 UI 相关构建、响应式、a11y 与组件测试 |
| impeccable | 最终质量审查落在 quality gate、模块大小、报告同步、前端守卫 |
