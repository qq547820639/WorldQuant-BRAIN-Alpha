# Tasks

## 波次 1：P0 正确性（无前置依赖，可立即启动）

- [ ] Task 1.1: 引入 DSR 指标（2h）
  - [ ] SubTask 1.1.1: 实现 `scoring/dsr.py`，按 Bailey & Lopez de Prado 2014 解析公式计算 DSR
  - [ ] SubTask 1.1.2: 在 `ScoringContext` 中新增累计试验次数 N 计数器，跨候选持久化
  - [ ] SubTask 1.1.3: 设置分层阈值：DSR > 0.95 通过、DSR < 0.50 过滤；假设驱动型 ≥ 0.30、数据驱动型 ≥ 0.50
  - [ ] SubTask 1.1.4: 添加特性开关 `use_dsr`，支持回退到原始 Sharpe
  - [ ] SubTask 1.1.5: 编写单元测试覆盖 N=1/10/100/200 四档，验证 N=1 等价于 PSR
  - [ ] SubTask 1.1.6: 验证特性开关可在 1 分钟内回退

- [ ] Task 1.2: 预筛置换检验过滤器（3h）
  - [ ] SubTask 1.2.1: 实现 `PermutationFilter` 组件，支持 1,000 次环形置换（circular permutation）
  - [ ] SubTask 1.2.2: 在预筛管线中插入 `PermutationFilter`，仅 p < 0.05 候选推送至 API 回测
  - [ ] SubTask 1.2.3: 不通过候选标记为 `REJECTED_BY_PERMUTATION_TEST`
  - [ ] SubTask 1.2.4: 置换次数设为可配置参数（默认 1,000，高精度 10,000）
  - [ ] SubTask 1.2.5: p 值在 [0.04, 0.06] 区间自动触发 10,000 次高精度重算
  - [ ] SubTask 1.2.6: 添加旁路开关支持跳过置换检验
  - [ ] SubTask 1.2.7: 性能验证：84×160 数据集 1,000 次置换 < 1 秒
  - [ ] SubTask 1.2.8: 过滤率验证：纯随机信号在 p < 0.05 下被过滤率 ≥ 95%

## 波次 2：P0 安全（依赖波次 1 完成）

- [ ] Task 2.1: Token bug 局部修复（1h，前置：Task 1.x 完成）
  - [ ] SubTask 2.1.1: 定位 `official_request.py` 中 `token_before_auth_fallback` 在认证回退成功后未正确恢复的代码路径
  - [ ] SubTask 2.1.2: 补充 `restore_token()` 恢复逻辑
  - [ ] SubTask 2.1.3: 为该路径添加并发场景的回归测试
  - [ ] SubTask 2.1.4: 验证 cookie 回退成功后原始 bearer token 正确恢复
  - [ ] SubTask 2.1.5: 验证并发请求下 token 不丢失

- [ ] Task 2.2: AuthStateMachine 封装（4h，前置：Task 2.1 完成）
  - [ ] SubTask 2.2.1: 提取 `AuthStrategy` 协议（`apply(request)` + `is_valid()`）
  - [ ] SubTask 2.2.2: 实现 `BearerAuth`、`CookieAuth`、`BasicAuth` 三个具体策略
  - [ ] SubTask 2.2.3: 创建 `AuthStateMachine`，封装 `authenticate()`→`on_failure()`→`refresh()`→`restore_token()` 状态转换链
  - [ ] SubTask 2.2.4: `_request()` 简化为三步调用：`auth_sm.current()` → `send()` → `if 401: auth_sm.fallback()`
  - [ ] SubTask 2.2.5: 锁粒度从整个请求周期缩小至仅认证状态切换瞬间
  - [ ] SubTask 2.2.6: 补充三重失败组合测试（cookie 过期 + token 无效 + basic 凭据错误）
  - [ ] SubTask 2.2.7: 验证 `_request()` 行数从 170+ 降至 ≤20
  - [ ] SubTask 2.2.8: 验证认证状态变量从 6 个暴露降至 0 个
  - [ ] SubTask 2.2.9: 验证已知 P0 token bug 不再复现
  - [ ] SubTask 2.2.10: 验证新增 OAuth 2.0 策略只需实现协议，无需修改状态机核心

## 波次 3：P1 架构（依赖波次 1-2 全部完成）

- [ ] Task 3.1: Pipeline Mixin → Composition 迁移（8h，前置：Task 2.x 完成）
  - [ ] SubTask 3.1.1: 阶段1 — 将 `AlphaResearchPipeline` 转为纯编排器，`run()` 缩减为对 `PipelineServices` 的线性编排调用（≤15 行）
  - [ ] SubTask 3.1.2: 阶段2 — 将 9 个 Mixin 的 public 方法迁移到对应服务类，Mixin 变为 thin adapter
  - [ ] SubTask 3.1.3: 阶段3 — 当所有调用通过 `pipeline.services.X` 时移除 Mixin 继承
  - [ ] SubTask 3.1.4: 用 `importlab`/`pydeps` 绘制 `PipelineServices` 18 个服务的完整依赖图
  - [ ] SubTask 3.1.5: 识别并解除循环导入环
  - [ ] SubTask 3.1.6: 拆分 `test_pipeline.py`（82KB）为按功能域的独立模块
  - [ ] SubTask 3.1.7: 验证 Mixin 数量从 9 降至 ≤3
  - [ ] SubTask 3.1.8: 验证 `run()` 行数从 120+ 降至 ≤15
  - [ ] SubTask 3.1.9: 验证现有测试全部通过（adapter 层保证向后兼容）
  - [ ] SubTask 3.1.10: `pydeps` 验证无循环导入

- [ ] Task 3.2: Web 分发系统统一（6h，前置：Task 2.x 完成，可与 3.1 并行）
  - [ ] SubTask 3.2.1: 创建 `WebHandler` Protocol 类型替代 `Any` 注解
  - [ ] SubTask 3.2.2: 逐路由迁移旧 handler 到新系统（特性开关控制流量）
  - [ ] SubTask 3.2.3: 每条路由验证无误后才切断旧系统
  - [ ] SubTask 3.2.4: 删除 `web_compat_facade.py` 和 `web_legacy_exports.py`
  - [ ] SubTask 3.2.5: 合并或删除冗余的 `web_*.py` 文件
  - [ ] SubTask 3.2.6: 验证 `web_*.py` 文件数从 82 降至 ≤60
  - [ ] SubTask 3.2.7: 验证双重分发系统不再并行

## 波次 4：P1 代码质量（依赖波次 3 完成）

- [ ] Task 4.1: 评分权重统一为 ScoringPolicy（5h，前置：Task 3.1 完成）
  - [ ] SubTask 4.1.1: 创建 `ScoringPolicy`（`frozen=True` dataclass），封装所有评分配置（权重、阈值、门控规则）
  - [ ] SubTask 4.1.2: 实现 `ScoringPolicy.from_config()` 工厂方法，合并 `ScoringConfig` + `QualityThresholds` + `scoring_params.py`
  - [ ] SubTask 4.1.3: 实现 `with_regime(regime)` 方法支持市场体制动态调整
  - [ ] SubTask 4.1.4: 实现 `explain()` 生成归因树供前端展示
  - [ ] SubTask 4.1.5: 统一 5+ 个分散配置位置为单一入口
  - [ ] SubTask 4.1.6: 通过 `PipelineServices` 容器注入管线
  - [ ] SubTask 4.1.7: 验证评分权重配置位置数从 5+ 降至 1
  - [ ] SubTask 4.1.8: 验证 `frozen=True` 保证运行时不可变（抛 `FrozenInstanceError`）
  - [ ] SubTask 4.1.9: 验证 `with_regime()` 返回新实例，原实例不变

- [ ] Task 4.2: 配置验证整合为 ConfigParser（4h，前置：Task 3.1 完成，可与 4.1 并行）
  - [ ] SubTask 4.2.1: 创建 `ConfigParser`，实现 `parse_config(raw_dict) -> tuple[OpsConfig, list[ValidationError]]`
  - [ ] SubTask 4.2.2: 内部按管道顺序：jsonschema → dataclass → domain validation
  - [ ] SubTask 4.2.3: 任一阶段失败收集错误并继续后续阶段（非短路返回）
  - [ ] SubTask 4.2.4: 所有错误统一为结构化格式（字段路径 + 规则名 + 失败值 + 建议修复）
  - [ ] SubTask 4.2.5: 提供 `validate_update(current, patch)` 支持热更新验证
  - [ ] SubTask 4.2.6: 验证 6 个配置验证模块通过单一入口调用
  - [ ] SubTask 4.2.7: 验证一次调用返回全部配置问题

## 波次 5：P2 前端（可与波次 3-4 并行，无前置依赖）

- [ ] Task 5.1: CandidateTable.tsx 拆分（5h，无前置依赖）
  - [ ] SubTask 5.1.1: 实现 `CandidateTableContainer`（数据获取 + 状态管理）
  - [ ] SubTask 5.1.2: 实现 `CandidateTableView`（纯渲染逻辑）
  - [ ] SubTask 5.1.3: 实现 `CandidateTablePagination`（分页）
  - [ ] SubTask 5.1.4: 实现 `CandidateTableFilters`（筛选 UI）
  - [ ] SubTask 5.1.5: 实现 `CandidateTableRowEditor`（行内编辑）
  - [ ] SubTask 5.1.6: 数据流遵循 unidirectional data flow
  - [ ] SubTask 5.1.7: 验证每个组件 ≤400 行（原 2,107 行）
  - [ ] SubTask 5.1.8: `CandidateTableView` 可独立通过 Storybook 测试
  - [ ] SubTask 5.1.9: 验证所有现有功能不受影响

## 波次 6：P2 清理（可与波次 3-4 并行，无前置依赖）

- [ ] Task 6.1: 遗留状态映射清理（3h，无前置依赖）
  - [ ] SubTask 6.1.1: 创建 `LifecycleStatusNormalizer`，封装 `_LEGACY_STATUS_MAP` 30+ 项映射
  - [ ] SubTask 6.1.2: vN 版本引入 normalizer 并保持向后兼容
  - [ ] SubTask 6.1.3: vN+1 版本对遗留状态发出 `DeprecationWarning`
  - [ ] SubTask 6.1.4: vN+2 版本移除遗留状态支持（仅规划，本规格执行 vN）
  - [ ] SubTask 6.1.5: 新增状态必须通过规范 `LifecycleState` enum
  - [ ] SubTask 6.1.6: 验证遗留状态映射项从 30+ 逐步降至 ≤10
  - [ ] SubTask 6.1.7: 验证迁移过程中无功能回归

- [ ] Task 6.2: 测试架构重组（3h，无前置依赖）
  - [ ] SubTask 6.2.1: 重组为 `tests/unit/`、`tests/integration/`、`tests/e2e/`、`tests/static/`、`tests/fixtures/`
  - [ ] SubTask 6.2.2: 提取共享 mock factory（`BrainAPI` mock、`Candidate` factory、`ScoringPolicy` 实例）至 `tests/fixtures/factories.py`
  - [ ] SubTask 6.2.3: 拆分 >30KB 巨型测试文件（目标从 ~15 个降至 ≤5 个）
  - [ ] SubTask 6.2.4: `test_official_adapter.py`（121KB）按功能域拆分为 4 个 ≤30KB 文件
  - [ ] SubTask 6.2.5: `conftest.py` 从 2.8KB 扩充，承载共享 fixtures
  - [ ] SubTask 6.2.6: 新增 property-based testing（Hypothesis）覆盖评分边界组合
  - [ ] SubTask 6.2.7: 验证 >30KB 测试文件数从 ~15 降至 ≤5

## 跨波次：CI 持续监控指标硬门槛

- [ ] Task 7.1: CI 重构指标硬门槛接入（无前置依赖，可与任意波次并行）
  - [ ] SubTask 7.1.1: 新增 `scripts/check_refactor_metrics.py`，校验 6 项指标
  - [ ] SubTask 7.1.2: Mixin 继承链长度（基线 9，增加即阻断合并）
  - [ ] SubTask 7.1.3: `web_*.py` 文件数（基线 82，增加即阻断合并）
  - [ ] SubTask 7.1.4: 评分权重配置位置数（基线 5+，增加即阻断合并）
  - [ ] SubTask 7.1.5: 认证状态变量暴露数（基线 6，增加即阻断合并）
  - [ ] SubTask 7.1.6: 最大 Python 文件行数（基线 ~800，超限需审批）
  - [ ] SubTask 7.1.7: >30KB 测试文件数（基线 ~15，超限需审批）
  - [ ] SubTask 7.1.8: 接入 `.github/workflows/quality-gate.yml`
  - [ ] SubTask 7.1.9: 同步 `scripts/check_module_size.py:BASELINE_LINE_LIMITS` 至当前实际行数

# Task Dependencies

- [Task 2.1] depends on [Task 1.1, Task 1.2]（波次 2 依赖波次 1 完成）
- [Task 2.2] depends on [Task 2.1]（先修复 bug，再封装状态机）
- [Task 3.1] depends on [Task 2.1, Task 2.2]（波次 3 依赖波次 1-2 全部完成）
- [Task 3.2] depends on [Task 2.1, Task 2.2]（可与 3.1 并行）
- [Task 4.1] depends on [Task 3.1]（ScoringPolicy 需通过 PipelineServices 注入）
- [Task 4.2] depends on [Task 3.1]（ConfigParser 需通过 PipelineServices 注入，可与 4.1 并行）
- [Task 5.1] 无前置依赖（可与波次 3-4 并行）
- [Task 6.1] 无前置依赖（可与波次 3-4 并行）
- [Task 6.2] 无前置依赖（可与波次 3-4 并行）
- [Task 7.1] 无前置依赖（可与任意波次并行）

# Parallelizable Work

以下任务组可并行执行：
- 波次 5（Task 5.1）+ 波次 6（Task 6.1, Task 6.2）可与波次 3-4（Task 3.1, 3.2, 4.1, 4.2）并行
- Task 3.1 与 Task 3.2 可并行（均依赖波次 2 完成后启动）
- Task 4.1 与 Task 4.2 可并行（均依赖 Task 3.1 完成后启动）
- Task 7.1 可与任意波次并行

# Risk Mitigation

- 每个修复单元 <10 行代码增量提交，先写测试再改代码
- Mixin adapter 层保证向后兼容，迁移期间不删除旧接口
- Web 双重分发切换采用逐路由特性开关，单条验证无误后才切断旧系统
- DSR 采用分层阈值：假设驱动型 Alpha DSR ≥ 0.30，数据驱动型 ≥ 0.50
- 置换检验 p 值在 0.05±0.01 区间自动触发 10,000 次高精度重算，采用环形置换保留自相关结构
- 6 项指标纳入 CI 硬门槛，单向收敛不回升
