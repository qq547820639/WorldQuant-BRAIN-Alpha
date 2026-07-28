# BRAIN Alpha Ops 综合改进计划

> 覆盖四类任务:改进 Code Wiki / 新增功能 / 重构优化 / 修复缺陷
> 基于 `.trae/specs/holistic-codebase-assessment/ASSESSMENT_REPORT.md`(85 条缺陷)+ 现有 spec 文档 + 当前代码状态

---

## 计划摘要 (Summary)

本计划对 `brain_alpha_ops` 项目进行系统性改进,按优先级分为四个阶段:

- **阶段 A (P0 紧急缺陷修复)**: 修复评估报告中 8 条 Critical + 阻断级缺陷,涉及反过拟合数值正确性、生产提交安全开关、Docker 安全加固、WebUI 阻断态隔离。这是项目「未达生产就绪」的核心阻塞项。
- **阶段 B (Code Wiki 改进)**: 补充现有 `docs/CODE_WIKI.md` 的 6 类缺失内容:HTTP API 参考、React 前端架构、测试策略、CI/CD 流程、已知缺陷索引、贡献者指南。
- **阶段 C (重构优化)**: 处理评估报告中识别的技术债 —— 9 处静默吞异常、线程安全缺陷、重复 shim 清理、模块过大拆分。
- **阶段 D (新功能 backlog)**: 列出可考虑的新功能候选,作为后续迭代输入,不在本计划实施范围内。

**预期产出**: 项目达到生产就绪(Code Wiki 完整 + P0 缺陷清零 + 关键技术债清理)。

---

## 当前状态分析 (Current State Analysis)

### 项目规模
- 后端 Python: ~440 个文件
- React 前端: ~180 个文件
- 测试套件: 2874+ 用例,覆盖率门槛 80%
- 已有 spec 文档: 23 份历史审计 + 23 份 spec

### 关键问题计数(来自评估报告)

| 维度 | Critical | High | Medium | 小计 |
|------|----------|------|--------|------|
| 功能缺陷 (Functional) | 7 | 30 | 18 | 55 |
| 用户体验 (UX) | 0 | 4 | 11 | 15 |
| WebUI | 1 | 8 | 6 | 15 |
| **合计** | **8** | **42** | **35** | **85** |

### 现有 Code Wiki 缺口

已生成 [docs/CODE_WIKI.md](file:///workspace/docs/CODE_WIKI.md) 覆盖:项目概览、整体架构、目录结构、核心数据模型、15 个模块职责、依赖关系、运行方式、安全模型。**缺失**:
1. HTTP API 端点参考(25 个 POST + GET 路由)
2. React 前端内部架构(组件树、状态管理、SSE/WebSocket)
3. 测试策略与结构
4. CI/CD 流程(GitHub workflows)
5. 已知缺陷索引(85 条)
6. 贡献者指南

### 已识别的 P0 阻塞项(必须立即修复)

| # | 问题 | 文件 | 风险 |
|---|------|------|------|
| F-001 | 反过拟合回退链用 IC series 当 returns,虚假完美分数 | scoring/anti_overfit/service.py:32-56 | 过拟合候选绕过门禁 |
| F-002 | IC 稳定性 `_rank_ic` 返回单元素列表致 ic_std 恒为 0 | scoring/anti_overfit/checks.py | 反过拟合第一层失效 |
| F-005 | real_submit_test_override 依赖 PYTEST_CURRENT_TEST env 可伪造 | runtime_constants.py:321-330 | 真实提交禁令被绕过 |
| F-006 | Docker 容器以 root 运行 + evidence 目录 chmod 777 | Dockerfile:91-92 | 容器逃逸获 root |
| F-007 | docker-compose 端口绑定 0.0.0.0 暴露公网 | docker-compose.yml:5-6 | Web 控制台暴露公网 |
| F-011 | 浏览器提交幂等键 FIFO 淘汰后可重放 | browser/execution_adapter/_submit.py:136-140 | 重复真实提交 |
| F-012 | check_prod_correlation API 失败时 fail-open | brain_api/official_simulation/_mixin.py:299-327 | 高相关性 alpha 放行 |
| W-001 | PhaseShell 阻断阶段按钮仍可点击 | web/react_app/src/components/PhaseShell.tsx | 状态机错乱 |
| W-006 | VirtualList Rules of Hooks 违规 | web/react_app/src/components/VirtualList/VirtualList.tsx | 运行时崩溃 |
| W-007 | renderActiveViewFromContext 在 render 期调 hook | web/react_app/src/components/views/renderViewFromContext.tsx | React 抛错 |
| U-015 | CredentialQuickStart timer 泄漏 | web/react_app/src/components/CredentialQuickStart.tsx | 卸载后 setState |

---

## 提议的改动 (Proposed Changes)

### 阶段 A: P0 紧急缺陷修复(最高优先级)

#### A1. 反过拟合数值正确性修复(F-001, F-002, F-039, F-040)

**目标**: 恢复反过拟合四层验证套件的真实判别能力。

**文件与改动**:

- [scoring/anti_overfit/service.py](file:///workspace/brain_alpha_ops/scoring/anti_overfit/service.py) (F-001)
  - **What**: 修改 `AntiOverfitService.evaluate` 的 fallback 链,严格区分语义
  - **Why**: 当 returns_series/forward_returns 缺失时回退到 ic_series(相关性度量),产生 IC≈1.0 虚假完美分数
  - **How**: `returns` 只能回退到 returns 语义字段;必要字段缺失时直接返回 `insufficient_data`(fail-closed),不用不相关数据填充

- [scoring/anti_overfit/checks.py](file:///workspace/brain_alpha_ops/scoring/anti_overfit/checks.py) (F-002)
  - **What**: 修改 `_rank_ic` 实现按时间窗口分段计算多个 cross-sectional IC 值
  - **Why**: 当前返回单元素列表,`_safe_std` 对 n<2 返回 0,致 `ic_std` 恒为 0,稳定性检查恒满分
  - **How**: 按月度/周度分段计算 spearman IC,返回多元素列表使 `ic_std` 反映真实波动

- [scoring/anti_overfit/checks.py](file:///workspace/brain_alpha_ops/scoring/anti_overfit/checks.py) (F-039)
  - **What**: 统一 `_pearson_r` 协方差与标准差除数(都用 n 或都用 n-1)
  - **Why**: 协方差用总体公式(n),标准差用样本公式(n-1),系统性低估相关性 n=20 时低估 5%

- [research/local_backtest_metrics_helpers.py](file:///workspace/brain_alpha_ops/research/local_backtest_metrics_helpers.py) (F-040)
  - **What**: `rank_values` 改为平均 rank 处理 ties,与 anti_overfit/utils.py 对齐
  - **Why**: 当前不处理 ties,与 anti_overfit 版本不一致

#### A2. 生产提交安全开关加固(F-005, F-011, F-012)

**目标**: 堵死真实提交被绕过的路径。

**文件与改动**:

- [runtime_constants.py](file:///workspace/brain_alpha_ops/runtime_constants.py) (F-005)
  - **What**: 移除 `PYTEST_CURRENT_TEST` env-based override,改用 `sys._getframe` 检查调用栈是否在 pytest 内,或用编译期常量 + 单元测试 monkey-patch
  - **Why**: env var 可被运维/容器编排伪造,配合另两个 env 可绕过 `REAL_SUBMIT_DISABLED_WEB_FLOW` 硬开关

- [browser/execution_adapter/_submit.py](file:///workspace/brain_alpha_ops/browser/execution_adapter/_submit.py) + [_base.py](file:///workspace/brain_alpha_ops/browser/execution_adapter/_base.py) (F-011)
  - **What**: 幂等键存储改为按时间窗口或持久化记录,与 approval_ticket 一并落盘做跨会话去重
  - **Why**: FIFO 淘汰超 1000 键后,被淘汰键不再被识别为「已用过」,重放检查失效

- [brain_api/official_simulation/_mixin.py](file:///workspace/brain_alpha_ops/brain_api/official_simulation/_mixin.py) (F-012)
  - **What**: `check_prod_correlation` API 失败时直接 `raise`(fail-closed),或在返回体带 `blocking: True` 强制调用方阻断
  - **Why**: 当前 fail-open 返回 warning,下游以 `max_correlation < threshold` 判定时 None 被当作「无相关性数据」放行高相关性 alpha

#### A3. Docker 安全加固(F-006, F-007)

**目标**: 容器最小权限 + 仅本机暴露。

**文件与改动**:

- [Dockerfile](file:///workspace/Dockerfile) (F-006)
  - **What**: 添加 `RUN useradd -m appuser && chown -R appuser:appuser /app` + `USER appuser`;evidence 目录改 `750`
  - **Why**: 当前以 root 运行 + chmod 777,容器逃逸直接获 root,777 让任意进程可篡改证据

- [docker-compose.yml](file:///workspace/docker-compose.yml) (F-007)
  - **What**: `ports: - "127.0.0.1:8765:8765"`;`WEB_HOST=127.0.0.1`;增加 `cap_drop: [ALL]`、`security_opt: [no-new-privileges:true]`、`read_only: true` + tmpfs
  - **Why**: 当前绑定 0.0.0.0 暴露公网,无资源限制可被用作挖矿/DoS 跳板

#### A4. WebUI 阻断级修复(W-001, W-006, W-007, U-015)

**目标**: 消除运行时崩溃与状态错乱。

**文件与改动**:

- [web/react_app/src/components/PhaseShell.tsx](file:///workspace/brain_alpha_ops/web/react_app/src/components/PhaseShell.tsx) (W-001)
  - **What**: 阻断容器加 `inert` 或 `pointer-events:none`;阶段卡片接受 `disabled` prop 传递给内部按钮
  - **Why**: 当前仅 opacity+grayscale,用户可点击未就绪阶段触发未定义状态

- [web/react_app/src/components/VirtualList/VirtualList.tsx](file:///workspace/brain_alpha_ops/web/react_app/src/components/VirtualList/VirtualList.tsx) (W-006)
  - **What**: 拆为 `WindowVirtualList` / `ElementVirtualList` 两个组件,或始终调用统一 hook
  - **Why**: `useWindowScroll ? useWindowVirtualizer : useVirtualizer` 三元分支违反 Rules of Hooks,运行时切换会崩溃

- [web/react_app/src/components/views/renderViewFromContext.tsx](file:///workspace/brain_alpha_ops/web/react_app/src/components/views/renderViewFromContext.tsx) (W-007)
  - **What**: 将 `useAppStateContext()` 调用上提到真正的组件顶层,通过参数传入 context 值
  - **Why**: 在普通函数(非组件)内调用 hook 违反 Rules of Hooks

- [web/react_app/src/components/CredentialQuickStart.tsx](file:///workspace/brain_alpha_ops/web/react_app/src/components/CredentialQuickStart.tsx) (U-015)
  - **What**: 用 `useRef` 存 timer,在 `useEffect` cleanup 中清理;正确补全 deps
  - **Why**: timer 泄漏,组件卸载后仍触发 setState

---

### 阶段 B: Code Wiki 改进

**目标**: 补充 [docs/CODE_WIKI.md](file:///workspace/docs/CODE_WIKI.md) 的 6 类缺失内容。

**改动**(仅编辑 `docs/CODE_WIKI.md`):

- **B1. HTTP API 端点参考**: 新增章节,列出 25 个 POST 处理器 + GET 路由,含路径、请求体、响应体、鉴权要求。来源:[web/dispatch/web_post_routes.py](file:///workspace/brain_alpha_ops/web/dispatch/web_post_routes.py)、[web/dispatch/web_routes.py](file:///workspace/brain_alpha_ops/web/dispatch/web_routes.py)

- **B2. React 前端架构**: 新增章节,覆盖组件树结构、状态管理(AppStateContext composition root)、SSE/WebSocket 通信、路由策略、构建配置。来源:[web/react_app/src/](file:///workspace/brain_alpha_ops/web/react_app/src/)

- **B3. 测试策略与结构**: 新增章节,覆盖测试标记(slow/integration/e2e/browser/live/readonly/mock)、覆盖率门槛、夹具工厂、E2E 框架。来源:[tests/conftest.py](file:///workspace/tests/conftest.py)、[pyproject.toml](file:///workspace/pyproject.toml)

- **B4. CI/CD 流程**: 新增章节,覆盖 [.github/workflows/build-release.yml](file:///workspace/.github/workflows/build-release.yml) 与 [quality-gate.yml](file:///workspace/.github/workflows/quality-gate.yml) 的触发条件、阶段、产物

- **B5. 已知缺陷索引**: 新增章节,汇总评估报告 85 条缺陷的编号、文件、严重度、状态(本计划修复哪些)

- **B6. 贡献者指南**: 新增章节,覆盖代码规范(ruff/mypy)、提交规范、分支策略、质量门禁脚本(scripts/check_*.py)

---

### 阶段 C: 重构优化(P1 技术债)

**目标**: 清理评估报告识别的关键技术债。本阶段处理 P1 级别(不阻塞生产但有风险)。

#### C1. 静默吞异常修复(9 处)

**文件**: 评分/候选生成/质量门路径上的 `except Exception` 块

**策略**(来自 tech-debt-cleanup spec):
- 预期内错误(外部 API 超时)→ `logger.warning` + 返回默认值
- 不该发生的错误(数据格式错误)→ `logger.exception` + raise
- 保护性兜底(子进程执行)→ `logger.exception` + 返回含错误信息的结果

**关键文件**:
- [web/__init__.py:208-211](file:///workspace/brain_alpha_ops/web/__init__.py) (F-034): Facade 绑定拆分为多个独立 try/except
- [audit_trail/writer.py:63-79](file:///workspace/brain_alpha_ops/audit_trail/writer.py) (F-010): `write_entry` 内部捕获 IO 异常
- [research/submission_gate_service.py:118-132](file:///workspace/brain_alpha_ops/research/submission_gate_service.py) (F-009): `_try_auto_submit` 用 try/except 包裹 `submit_alpha`

#### C2. 线程安全修复

**文件与改动**:
- [metrics.py](file:///workspace/brain_alpha_ops/metrics.py) (F-020): `MetricsCollector` 所有写操作加 `with self._lock`
- [backend_registration.py](file:///workspace/brain_alpha_ops/backend_registration.py) (F-028): `_api_instance` 双检锁
- [tasks/_watchdog.py](file:///workspace/brain_alpha_ops/tasks/_watchdog.py) (F-026): 读路径不加 watchdog 锁或加 try-lock
- [jsonl.py](file:///workspace/brain_alpha_ops/jsonl.py) (F-027): reader 用 `fcntl.flock(LOCK_SH)` 或 writer 用 atomic rename
- [research/record_sqlite_index.py](file:///workspace/brain_alpha_ops/research/record_sqlite_index.py) (F-053): 用 `BEGIN IMMEDIATE` 事务包裹 read+write

#### C3. 冗余代码清理

**文件与改动**:
- [web_candidates/payloads.py](file:///workspace/brain_alpha_ops/web_candidates/payloads.py) (F-022): 删除 20 行重复 import,保留单行
- [presets.py:86](file:///workspace/brain_alpha_ops/presets.py) (F-021): `"language": _registry_default("language", "FASTEXPR")` 修正 kind
- [web/_reexports.py:147-158](file:///workspace/brain_alpha_ops/web/_reexports.py) (F-036): 删除 `min(length, MAX)` 行,先 `if length > MAX: raise` 再 read

#### C4. 数值正确性修复(P1)

- [research/rolling_validation.py:38-41](file:///workspace/brain_alpha_ops/research/rolling_validation.py) (F-008): `decay_ratio` 符号翻转修复,首末窗口符号不同时单独处理
- [scoring/release_score_gate/_decision.py:79](file:///workspace/brain_alpha_ops/scoring/release_score_gate/_decision.py) (F-051): `effective_settings` 默认 `{}` 而非 metrics
- [research/prod_correlation.py:235-268](file:///workspace/brain_alpha_ops/research/prod_correlation.py) (F-052): 本地回退 fail-closed 而非用表达式长度估算
- [research/fusion.py:152-156](file:///workspace/brain_alpha_ops/research/fusion.py) (F-055): `mode="max"` 调用 `_validate_fusion_expr`
- [research/backtest_flow_service/_slot_submission.py:61-87](file:///workspace/brain_alpha_ops/research/backtest_flow_service/_slot_submission.py) (F-056): `return` 改 `continue`

---

### 阶段 D: 新功能 backlog(仅记录,不实施)

以下为可考虑的新功能候选,作为后续迭代输入:

1. **多机分布式协作**: 当前单机运行,可考虑候选池合并协议
2. **alpha 自动提交(可选 opt-in)**: 在 HIL 闸门基础上增加「白名单 alpha 自动提交」模式(需额外安全审查)
3. **前端路由深化**: 将主要视图注册为子路由(/candidates、/scoring 等),支持深链与书签(W-004)
4. **Toast 系统一体化**: 合并重复的 Toast 渲染容器(W-010)
5. **首屏骨架屏**: index.html 增加内联骨架屏 + noscript 提示(W-011)
6. **i18n 覆盖完善**: 扩充 zh 字典,未匹配时返回通用中文(U-006)
7. **配置重启提示**: 保存后返回 `requires_restart` 字段(U-007)
8. **前台任务完成通知**: 前台也弹非阻塞 toast(U-008)
9. **visibility-aware 轮询**: useGlobalData/OfficialBacktestSlots/SubmissionConfirmPanel 加 visibility 检查(U-009/U-010/U-014)
10. **网络错误全局重试入口**: 顶栏加「重试连接」按钮(U-012)
11. **批量提交 dry-run**: 增加确认弹窗 + 预览影响范围(U-013)

---

## 假设与决策 (Assumptions & Decisions)

### 假设
1. 评估报告(2026-06-29)中列出的缺陷在当前代码中仍然存在(基于报告 `file:line` 引用,未逐一重新验证)
2. 测试套件(2874+ 用例)能覆盖改动影响范围,改动后跑 `pytest` 验证
3. React 前端源码位于 [web/react_app/src/](file:///workspace/brain_alpha_ops/web/react_app/src/),可正常编辑

### 决策
1. **优先级**: 阶段 A(P0) > 阶段 B(Wiki) > 阶段 C(P1 技术债) > 阶段 D(backlog 不实施)
2. **粒度**: 阶段 A 每个修复点给出具体文件+行号+改法;阶段 B 给出章节大纲;阶段 C 给出文件+策略;阶段 D 仅列名
3. **范围限定**: 阶段 A 修复 P0(11 项);阶段 C 修复 P1 代表性项(约 20 项),不覆盖全部 42 个 High + 35 个 Medium
4. **不破坏现有契约**: 所有修复保持现有 API/配置/测试兼容,除非评估报告明确标注 BREAKING
5. **验证方式**: 每阶段完成后跑 `pytest` + 相关 `scripts/check_*.py` 质量门禁

---

## 验证步骤 (Verification Steps)

### 阶段 A 验证
1. `pytest tests/test_anti_overfit.py tests/test_anti_overfit_dsr.py tests/test_anti_overfit_permutation.py -v` — 反过拟合套件
2. `pytest tests/test_compliance_verification.py -v` — 红线验证(确保 zero_deviation 未破坏)
3. `pytest -k "submit" -v` — 提交相关测试
4. `docker build -t brain-alpha-ops . && docker run --rm brain-alpha-ops python -c "import os; print(os.getuid())"` — 验证非 root
5. `cd brain_alpha_ops/web/react_app && npm run typecheck && npm run build` — 前端类型检查与构建
6. `python scripts/check_architecture.py` — 架构合规

### 阶段 B 验证
1. 人工审阅 [docs/CODE_WIKI.md](file:///workspace/docs/CODE_WIKI.md) 新增章节的完整性与准确性
2. 验证所有 `file:///` 链接可点击且指向真实存在的文件

### 阶段 C 验证
1. `pytest -v` — 全量测试(2874+ 用例)无新增失败
2. `python scripts/check_module_size.py` — 模块大小检查
3. `python scripts/check_python_silent_broad_exceptions.py` — 静默异常检查
4. `python -m brain_alpha_ops.compliance.redline_verifier --block` — 红线验证

### 最终验证
1. `pytest --cov=brain_alpha_ops --cov-fail-under=80` — 覆盖率门槛
2. `python scripts/final_release_gate.py` — 最终发布门禁
3. `python launch_web.py` + 浏览器访问 `http://127.0.0.1:8765` — 启动冒烟测试

---

## 实施顺序建议

1. **阶段 A**(P0 紧急,~11 个修复点): 先修复反过拟合数值(A1),再修提交安全(A2),再修 Docker(A3),最后修 WebUI(A4)
2. **阶段 B**(Wiki 改进): 在 A 完成后补充文档,记录 A 的修复成果到「已知缺陷索引」章节
3. **阶段 C**(P1 技术债): 按 C1→C2→C3→C4 顺序,每完成一组跑测试
4. **阶段 D**: 不实施,仅作为 backlog 记录
