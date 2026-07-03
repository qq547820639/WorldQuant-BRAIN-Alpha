# Checklist

## 波次 1：P0 正确性

- [ ] `scoring/dsr.py` 已实现 Bailey & Lopez de Prado 2014 解析公式
- [ ] `ScoringContext` 已记录累计试验次数 N，跨候选持久化
- [ ] DSR 阈值已设置：> 0.95 通过、< 0.50 过滤；假设驱动型 ≥ 0.30、数据驱动型 ≥ 0.50
- [ ] 特性开关 `use_dsr` 已添加，支持回退到原始 Sharpe
- [ ] 单元测试覆盖 N=1/10/100/200 四档
- [ ] N=1 时 DSR 等价于 PSR（向后兼容验证通过）
- [ ] 特性开关可在 1 分钟内回退验证通过
- [ ] `PermutationFilter` 组件已实现，支持 1,000 次环形置换（circular permutation）
- [ ] 预筛管线已插入 `PermutationFilter`，仅 p < 0.05 候选推送至 API 回测
- [ ] 不通过候选标记为 `REJECTED_BY_PERMUTATION_TEST`
- [ ] 置换次数可配置（默认 1,000，高精度 10,000）
- [ ] p 值在 [0.04, 0.06] 区间自动触发 10,000 次高精度重算
- [ ] 旁路开关支持跳过置换检验
- [ ] 84×160 数据集 1,000 次置换 < 1 秒性能验证通过
- [ ] 纯随机信号在 p < 0.05 下被过滤率 ≥ 95% 验证通过

## 波次 2：P0 安全

- [ ] `official_request.py` 中 `token_before_auth_fallback` 未恢复的代码路径已定位
- [ ] `restore_token()` 恢复逻辑已补充
- [ ] 并发场景回归测试已添加
- [ ] cookie 回退成功后原始 bearer token 正确恢复验证通过
- [ ] 并发请求下 token 不丢失验证通过
- [ ] `AuthStrategy` 协议（`apply(request)` + `is_valid()`）已提取
- [ ] `BearerAuth`、`CookieAuth`、`BasicAuth` 三个具体策略已实现
- [ ] `AuthStateMachine` 已创建，封装 `authenticate()`→`on_failure()`→`refresh()`→`restore_token()` 状态转换链
- [ ] `_request()` 已简化为三步调用：`auth_sm.current()` → `send()` → `if 401: auth_sm.fallback()`
- [ ] 锁粒度已从整个请求周期缩小至仅认证状态切换瞬间
- [ ] 三重失败组合测试（cookie 过期 + token 无效 + basic 凭据错误）已通过
- [ ] `_request()` 行数从 170+ 降至 ≤20 验证通过
- [ ] 认证状态变量从 6 个暴露降至 0 个验证通过
- [ ] 已知 P0 token bug 不再复现验证通过
- [ ] 新增 OAuth 2.0 策略只需实现协议，无需修改状态机核心验证通过

## 波次 3：P1 架构

- [ ] `AlphaResearchPipeline` 已转为纯编排器
- [ ] `run()` 方法行数从 120+ 降至 ≤15 验证通过
- [ ] 9 个 Mixin 的 public 方法已迁移到对应服务类
- [ ] Mixin 已变为 thin adapter
- [ ] 所有调用通过 `pipeline.services.X` 后 Mixin 继承已移除
- [ ] Mixin 数量从 9 降至 ≤3 验证通过
- [ ] `PipelineServices` 18 个服务的完整依赖图已绘制（`importlab`/`pydeps`）
- [ ] 循环导入环已识别并解除
- [ ] `pydeps` 验证无循环导入通过
- [ ] `test_pipeline.py`（82KB）已拆分为按功能域的独立模块
- [ ] 现有测试全部通过（adapter 层保证向后兼容）
- [ ] `WebHandler` Protocol 类型已创建，替代 `Any` 注解
- [ ] 旧 handler 已逐路由迁移到新系统（特性开关控制流量）
- [ ] 每条路由验证无误后才切断旧系统
- [ ] `web_compat_facade.py` 和 `web_legacy_exports.py` 已删除
- [ ] 冗余的 `web_*.py` 文件已合并或删除
- [ ] `web_*.py` 文件数从 82 降至 ≤60 验证通过
- [ ] 双重分发系统不再并行验证通过

## 波次 4：P1 代码质量

- [ ] `ScoringPolicy`（`frozen=True` dataclass）已创建
- [ ] `ScoringPolicy.from_config()` 工厂方法已实现，合并 `ScoringConfig` + `QualityThresholds` + `scoring_params.py`
- [ ] `ScoringPolicy.with_regime(regime)` 方法已实现
- [ ] `ScoringPolicy.explain()` 归因树方法已实现
- [ ] 5+ 个分散配置位置已统一为单一入口
- [ ] `ScoringPolicy` 已通过 `PipelineServices` 容器注入管线
- [ ] 评分权重配置位置数从 5+ 降至 1 验证通过
- [ ] `frozen=True` 保证运行时不可变（抛 `FrozenInstanceError`）验证通过
- [ ] `with_regime()` 返回新实例，原实例不变验证通过
- [ ] `ConfigParser` 已创建，实现 `parse_config(raw_dict) -> tuple[OpsConfig, list[ValidationError]]`
- [ ] 内部按管道顺序：jsonschema → dataclass → domain validation
- [ ] 任一阶段失败收集错误并继续后续阶段（非短路返回）验证通过
- [ ] 所有错误统一为结构化格式（字段路径 + 规则名 + 失败值 + 建议修复）
- [ ] `validate_update(current, patch)` 支持热更新验证已实现
- [ ] 6 个配置验证模块通过单一入口调用验证通过
- [ ] 一次调用返回全部配置问题验证通过

## 波次 5：P2 前端

- [ ] `CandidateTableContainer`（数据获取 + 状态管理）已实现
- [ ] `CandidateTableView`（纯渲染逻辑）已实现
- [ ] `CandidateTablePagination`（分页）已实现
- [ ] `CandidateTableFilters`（筛选 UI）已实现
- [ ] `CandidateTableRowEditor`（行内编辑）已实现
- [ ] 数据流遵循 unidirectional data flow 验证通过
- [ ] 每个组件 ≤400 行（原 2,107 行）验证通过
- [ ] `CandidateTableView` 可独立通过 Storybook 测试验证通过
- [ ] 所有现有功能不受影响验证通过

## 波次 6：P2 清理

- [ ] `LifecycleStatusNormalizer` 已创建，封装 `_LEGACY_STATUS_MAP` 30+ 项映射
- [ ] vN 版本引入 normalizer 并保持向后兼容
- [ ] vN+1 版本对遗留状态发出 `DeprecationWarning` 的计划已记录
- [ ] vN+2 版本移除遗留状态支持的计划已记录
- [ ] 新增状态必须通过规范 `LifecycleState` enum 验证通过
- [ ] 遗留状态映射项从 30+ 逐步降至 ≤10 验证通过
- [ ] 迁移过程中无功能回归验证通过
- [ ] 测试目录已重组为 `tests/unit/`、`tests/integration/`、`tests/e2e/`、`tests/static/`、`tests/fixtures/`
- [ ] 共享 mock factory 已提取至 `tests/fixtures/factories.py`（`BrainAPI` mock、`Candidate` factory、`ScoringPolicy` 实例）
- [ ] >30KB 巨型测试文件已拆分（目标从 ~15 个降至 ≤5 个）
- [ ] `test_official_adapter.py`（121KB）已按功能域拆分为 4 个 ≤30KB 文件
- [ ] `conftest.py` 已从 2.8KB 扩充，承载共享 fixtures
- [ ] property-based testing（Hypothesis）已新增，覆盖评分边界组合
- [ ] >30KB 测试文件数从 ~15 降至 ≤5 验证通过

## 跨波次：CI 持续监控指标硬门槛

- [ ] `scripts/check_refactor_metrics.py` 已新增，校验 6 项指标
- [ ] Mixin 继承链长度指标已接入（基线 9，增加即阻断合并）
- [ ] `web_*.py` 文件数指标已接入（基线 82，增加即阻断合并）
- [ ] 评分权重配置位置数指标已接入（基线 5+，增加即阻断合并）
- [ ] 认证状态变量暴露数指标已接入（基线 6，增加即阻断合并）
- [ ] 最大 Python 文件行数指标已接入（基线 ~800，超限需审批）
- [ ] >30KB 测试文件数指标已接入（基线 ~15，超限需审批）
- [ ] 已接入 `.github/workflows/quality-gate.yml`
- [ ] `scripts/check_module_size.py:BASELINE_LINE_LIMITS` 已同步至当前实际行数
- [ ] PR 引入新 Mixin 时 CI 阻断合并验证通过
- [ ] PR 新增 `web_*.py` 文件使总数超过基线时 CI 阻断合并验证通过
- [ ] PR 使最大 Python 文件行数超过 500 时 CI 标记需审批验证通过

## 风险缓解验证

- [ ] 每个修复单元 <10 行代码增量提交验证通过
- [ ] 先写测试再改代码流程验证通过
- [ ] Mixin adapter 层保证向后兼容验证通过
- [ ] 迁移期间不删除旧接口验证通过
- [ ] Web 双重分发切换逐路由特性开关验证通过
- [ ] 单条路由验证无误后才切断旧系统验证通过
- [ ] DSR 分层阈值（假设驱动型 ≥ 0.30，数据驱动型 ≥ 0.50）已实现
- [ ] 置换检验环形置换保留自相关结构验证通过
- [ ] 6 项指标纳入 CI 硬门槛单向收敛不回升验证通过
