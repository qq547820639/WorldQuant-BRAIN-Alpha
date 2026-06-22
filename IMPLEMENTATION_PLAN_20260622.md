# WorldQuant BRAIN Alpha — 审查整改实施方案

**日期**：2026-06-22
**状态**：执行中
**基线**：BRAINALPHA_FULLSTACK_AUDIT_20260622.md

---

## 一、审计发现与现状差距分析

审计报告识别了 7 项问题（2×P0 + 3×P1 + 2×P2）。**本轮行动前的物资盘点表明：审计建议的核心代码基建已在仓库中就绪，但尚未集成到主生产管线。**真正需要做的不是"从零建设"，而是"联通管线 + 补齐治理缝隙"。

### 已完成（无需重复建设）

| 资产 | 位置 | 状态 |
|---|---|---|
| `AlphaExecutionBackend` Protocol | `brain_alpha_ops/execution_backend.py` | ✅ 已定义，含 `ExecutionEvidence` |
| `BrainBrowserRunner` (Playwright) | `brain_alpha_ops/browser/brain_ui_runner.py` | ✅ 178 行，完整 login/simulate/check/heartbeat |
| `BrowserMonitor` + heal | `brain_alpha_ops/browser/monitor.py` | ✅ 89 行，health check + auto-heal |
| `EvidenceArchival` | `brain_alpha_ops/monitoring/evidence.py` | ✅ 存在 |
| QA 测试降级 | `qa_e2e_new_user_walkthrough.py` | ✅ 已 `pytest.mark.skip` |
| QA 前端降级 | `qa_full_chain_frontend.py` | ✅ 已 `pytest.mark.skip` |
| 提交守门 | `REAL_SUBMIT_DISABLED_WEB_FLOW` | ✅ 已三层传播（web_business / web_submission_single / official_simulation） |

### 待建设（本轮推进）

| # | 优先级 | 工作项 | 工作量 |
|---|---|---|---|
| 1 | P0 | 将 `AlphaExecutionBackend` Protocol 接入主 Pipeline 流程 | 中 |
| 2 | P0 | 为 `BrainBrowserRunner` 创建 API 适配器，挂载到 Protocol | 中 |
| 3 | P0 | 创建 `tests/e2e/test_real_web_flow_playwright.py` 占位 | 小 |
| 4 | P1 | `BrowserMonitor` ↔ `StallMonitor` 统一监控总线 | 中 |
| 5 | P1 | 证据归档集成到 Pipeline 执行流程 | 小 |
| 6 | P1 | README 提交语义修正 | 小 |
| 7 | P1 | `pyproject.toml` 添加 `playwright` 可选依赖 | 小 |
| 8 | P2 | 编写 Dockerfile（Python + Node 双阶段） | 小 |
| 9 | P2 | 执行后端注册表与工厂 | 小 |

### 延后项（本轮不处理）

- 大模块拆分（web.py / official.py 重构）—— 破坏性大，另开专项
- CI/CD 完整流水线 —— 依赖 Dockerfile 先就绪
- 收敛式迭代算法落地 —— 依赖真实浏览器流先跑通

---

## 二、执行计划（严格串行，逐项验证）

```
Phase 0: 基线验证 (run existing skipped tests to confirm they pass)
  │
Phase 1: P0 集成 (execution_backend → pipeline wiring)
  ├── 1a: 创建 BrowserExecutionAdapter (API 适配器)
  ├── 1b: 创建 ExecutionBackendRegistry + factory
  ├── 1c: 在 Pipeline 中注入 backend，验证 Protocol 兼容
  │
Phase 2: P0 测试 (E2E placeholder)
  ├── 2a: 创建 tests/e2e/ 目录与 Playwright 测试骨架
  │
Phase 3: P1 监控集成
  ├── 3a: UnifiedMonitor 桥接 BrowserMonitor + StallMonitor
  ├── 3b: EvidenceArchival 挂载到 Pipeline
  │
Phase 4: P1 治理补齐
  ├── 4a: README 提交语义修正
  ├── 4b: pyproject.toml 添加 playwright
  │
Phase 5: P2 DevOps
  ├── 5a: Dockerfile
  └── 5b: 回归验证（pytest --skip-contract）
```

### 验收标准（逐项）

| # | 验收标准 |
|---|---|
| 1 | `AlphaExecutionBackend` Protocol 可被 Pipeline 消费 |
| 2 | `BrowserExecutionAdapter` 实现 Protocol，可独立测试 |
| 3 | `tests/e2e/test_real_web_flow_playwright.py` 存在且可被 `pytest -m slow` 收集 |
| 4 | `UnifiedMonitor` 同时消费 browser 心跳 + job store 状态 |
| 5 | Pipeline 每次模拟/检查后自动归档证据 |
| 6 | README 提交描述与代码三层守门一致 |
| 7 | `pip install -e ".[browser]"` 可安装 playwright |
| 8 | `docker build -t brain-alpha-ops .` 构建成功 |
| 9 | 现有测试全部通过（降级测试被 skip 不算失败） |

---

## 三、风险矩阵

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| Playwright 浏览器依赖在 CI 环境不可用 | 中 | 阻塞 P0 验证 | `browser` 标记为可选依赖，Adapter 导入时懒加载 |
| Pipeline 重构引入回归 | 低 | 中 | 每步后运行 `pytest -x -k "not e2e"` 验证 |
| BrowserMonitor ↔ StallMonitor API 不兼容 | 低 | 中 | 统一 `MonitorEvent` 协议，桥接模式 |
