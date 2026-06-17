# 全面缺陷分析报告 — WorldQuant BRAIN Alpha Ops

**日期**: 2026-06-01  
**分析范围**: 全代码库（256+ Python 文件、内联 JS/HTML、React 前端、测试、脚本、配置）  
**分析方法**: 代码探索子代理 + 专家团队并行分析（安全、质量、架构、测试） + 手动关键路径验证

---

## 一、缺陷清单总览

| 严重性 | 数量 | 说明 |
|--------|------|------|
| **P0 阻塞** | 1 | 运行时必崩 Bug |
| **P1 严重** | 4 | 安全/可靠性/可维护性重大风险 |
| **P2 中等** | 6 | 代码异味/架构债务/技术债 |
| **P3 轻微** | 5 | 风格/惯例/文档 |
| **合计** | **16** | |

> **重要说明**: 2026-06-01 交付审查中识别的 5 个阻塞项（baseUrl SSRF、请求体限制、traceback 泄露、静默吞异常、payload 上限）已全部通过 REVIEW_GAP_CLOSURE 验证关闭（CLOSED_CURRENT）。本报告聚焦于**新发现的或尚未完全修复的缺陷**。
>
> **实施更新**: 当前工作区已关闭 DEFECT-001 的运行时阻断路径，并补充自动校准回归测试；同时为部分高危静默回退补上 warning 级诊断，清理了循环内导入，并把 `calibrate_weights.py` 通过包内 wrapper + 安装声明一起稳定化。`dataset_selector`、`pipeline_official_context`、`iterative_optimizer`、`web_sync_payload`、`official_context_datasets`、`web_assistant_snapshots`、`web_cloud_snapshot`、`official_context_validation`、`brain_api/official.py`、`research/knowledge_base.py`、`agent_tools.py`、`agent_research_tools.py`、`research/repository.py`、`research/parallel_backtest.py`、`research/pipeline.py`、`scoring/visualization.py`、`web_runtime_facade.py`、`web_cloud_context_refresh.py`、`web_check_availability.py`、`production_diagnostics.py`、`e2e_report.py`、`research/strategy_plugins.py`、`research/alerting.py` 和 `compliance/redline_verifier.py` 的关键失败现在也会留下 warning；`web.py` 新增了显式 `WebApplicationContext` / `web_application_context()` 入口，公开 facade wrapper 的直接 `sys.modules[__name__]` 调用已收敛为 `_app_context()`，并且 78 个模块级 lambda alias 已全部替换为显式 `def`；`dataset_selector.py`、`generator.py`、`iterative_optimizer.py`、`hypothesis_driven_generator.py`、`hypothesis_library.py`、`experience.py`、`backtest_finalization.py`、`backtest_submission.py`、`backtest_polling.py`、`convergence.py`、`diagnostics.py`、`fusion.py`、`templates.py`、`scoring_params.py`、`alpha_checks.py`、`auto_calibrator.py`、`theme_engine.py` 和 `validated_generator.py` 的类型提示已切换为内置泛型写法，`brain_alpha_ops/research` 精确旧式注解扫描已无命中；同时新增 `scripts/check_defect_analysis_report.py` 与对应测试，锁定本报告 16 个缺陷条目、状态表一致性和 Python 3.10+ 运行时证据，避免追踪遗漏；高风险异常、表达式、identifier 和 cache-path 日志现在通过 `redact_error_message(...)` / `redact_text(...)` 输出截断脱敏文本，并由 `scripts/check_log_redaction.py` 守卫；`tests/test_pipeline.py` 还补上了 context refresh、scoring calibration、fusion attempt 三条回归；`AlphaResearchPipeline` 的运行态字段已收口到 `PipelineRuntimeState`，通过兼容属性保留现有 mixin 访问，并由 `scripts/check_pipeline_runtime_state.py` 守卫；Python 注释层面的中英混杂已清理完成，用户可见中文文案保留为产品文本。`DEFECT-014` 已按当前 release decision 收口，报告中无 tracked deferred 项。

---

## 二、详细缺陷清单

### DEFECT-001: `self.ops_config` 属性引用错误（运行时 Bug）

| 字段 | 值 |
|------|-----|
| **严重性** | **P0 阻塞** |
| **位置** | `brain_alpha_ops/research/pipeline.py` 第 574 行 |
| **类型** | 运行时 AttributeError |
| **原因** | `AlphaResearchPipeline.__init__` 中定义的是 `self.config = config`（第 138 行），但第 574 行引用 `self.ops_config.storage_dir`，该属性不存在。`ops_config` 是 `OfficialScoringService`（`scoring/official_scoring.py`）的属性，不属于 Pipeline 类。 |
| **影响** | 自动校准功能（auto-calibration）**完全失效**。每次 pipeline run 结束时都会触发 `AttributeError`，被外层 `except Exception` 静默吞掉（第 581-582 行仅 `logger.debug`）。用户无法获得校准建议，且无告警。 |
| **代码上下** | |
```python
# 第 571-582 行
try:
    from calibrate_weights import auto_calibrate_if_stalled
    calib = auto_calibrate_if_stalled(self.ops_config.storage_dir)  # ← BUG
    ...
except Exception:
    logger.debug("auto_calibration skipped", exc_info=True)  # ← 静默吞掉
```
| **修复方案** | `self.ops_config` → `self.config`（第 574 行） |

---

### DEFECT-002: 静默吞异常模式普遍存在

| 字段 | 值 |
|------|-----|
| **严重性** | **P1 严重** |
| **位置** | 全代码库 42 处 `except Exception:` 块 |
| **类型** | 可靠性 / 可调试性 |
| **原因** | 多处 `except Exception:` 后仅跟 `pass`、`continue`、空 `return` 或 `logger.debug`（非 warning 级别），错误被完全隐藏。 |
| **影响** | 功能静默失败、调试困难、隐藏级联故障。特别高危区域： |
| | - `research/generator.py:44` — `except Exception: return set()` |
| | - `research/hypothesis_driven_generator.py:333` — `except Exception: return set()` |
| | - `research/expression_index.py:147,163` — 静默索引失败 |
| | - `web_submission_single.py:73` — 提交路径静默失败 |
| **修复方案** | 1) 为所有 `except Exception:` 添加 `logger.warning(..., exc_info=True)`; 2) 评估是否需要重新抛出; 3) 对关键路径使用 `logger.error` |

---

### DEFECT-003: web.py Lambda 门面反模式

| 字段 | 值 |
|------|-----|
| **严重性** | **P1 严重** |
| **位置** | `brain_alpha_ops/web.py` 第 220-300 行 |
| **类型** | 架构 / 可测试性 |
| **原因** | 47+ 个 lambda 别名使用 `sys.modules[__name__]` 作为服务定位器，将模块级可变状态（`JOBS`, `SYNC_JOBS`, `SUBMIT_LOCK`, `RATE_LIMITER`, `TASK_EXECUTOR`, `SERVER`）暴露为全局变量。所有公共函数都是 lambda 包装器。 |
| **影响** | 1) 无法进行单元测试隔离（全局可变状态）; 2) 循环依赖风险; 3) 类型检查工具无法正确推断 lambda 类型; 4) `sys.modules[__name__]` 是 Python 黑魔法，IDE 和静态分析工具支持差 |
| **修复方案** | 分阶段重构：Phase 1 - 将全局状态封装到 `WebApplicationContext` 类中; Phase 2 - 将 lambda 包装器改为显式方法; Phase 3 - 使用依赖注入替代服务定位器 |

---

### DEFECT-004: WebHandlerDispatchContext 超大数据类（70+ 字段）

| 字段 | 值 |
|------|-----|
| **严重性** | **P1 严重** |
| **位置** | `brain_alpha_ops/web_handler_dispatch.py` 第 32-104 行 |
| **类型** | 接口隔离违反 / 可维护性 |
| **原因** | `WebHandlerDispatchContext` frozen dataclass 包含 70+ 个字段，每个 GET/POST handler 都接收完整上下文，违反接口隔离原则。 |
| **影响** | 1) 添加新 handler 需修改公共接口; 2) 字段间隐式依赖关系不清晰; 3) 测试需要构造庞大 mock 对象; 4) 18 个 POST handler 重复相同的 try/except/验证模式 |
| **修复方案** | 1) 将相关字段分组到子 dataclass（如 `SessionContext`, `JobContext`, `SnapshotContext`）; 2) 使用 Protocol/接口定义每个 handler 所需的最小依赖; 3) 创建通用 POST handler 装饰器 |

---

### DEFECT-005: AlphaResearchPipeline God Object（10 个 mixin）

| 字段 | 值 |
|------|-----|
| **严重性** | **P1 严重** |
| **位置** | `brain_alpha_ops/research/pipeline.py` 第 105-116 行 |
| **类型** | 架构 / 可维护性 |
| **原因** | `AlphaResearchPipeline` 继承 10 个 mixin，`__init__` 初始化 85+ 个实例属性，`run()` 方法约 370 行。虽然已拆分为 mixin 文件，但本质仍是 God Object。 |
| **影响** | 1) 认知复杂度极高，难以理解完整行为; 2) 修改一个 mixin 可能影响其他 mixin 的隐式依赖; 3) 测试困难（需 mock 85+ 属性）; 4) DEFECT-001 的根本原因之一 |
| **修复方案** | 1) 将属性分组到子组件中（如 `BacktestState`, `StrategyState`, `CloudState`）; 2) 使用组合替代继承; 3) 将 `run()` 拆分为独立的阶段处理器（pipeline_stages.py 已部分实现） |

---

### DEFECT-006: JobExecutionResult 重复定义

| 字段 | 值 |
|------|-----|
| **严重性** | **P2 中等** |
| **位置** | `brain_alpha_ops/task_executor.py:52-57` 和 `brain_alpha_ops/adaptive_executor.py:302-307` |
| **类型** | 代码重复 |
| **原因** | 两个文件定义了完全相同的 `JobExecutionResult` dataclass，以及几乎相同的 `run_job` / `run_adaptive_job` 生命周期逻辑。 |
| **影响** | 修改一处需同步修改另一处，容易遗漏导致不一致 |
| **修复方案** | 创建共享模块 `brain_alpha_ops/job_types.py`，提取 `JobExecutionResult` 和公共生命周期逻辑 |

---

### DEFECT-007: 循环体内导入遮蔽顶层导入

| 字段 | 值 |
|------|-----|
| **严重性** | **P2 中等** |
| **位置** | `brain_alpha_ops/research/pipeline.py` 第 313 行 |
| **类型** | 代码异味 |
| **原因** | 在循环体内执行 `import time as _time`，遮蔽了文件顶部的 `import time`（第 8 行）。 |
| **影响** | 1) 每次循环迭代都执行导入语句（虽然 Python 有模块缓存，但仍产生额外开销）; 2) `_time` 和 `time` 命名不一致造成混淆 |
| **修复方案** | 删除循环内的 `import time as _time`，使用文件顶部已导入的 `time` |

---

### DEFECT-008: `except Exception` + `logger.debug` 级别不当

| 字段 | 值 |
|------|-----|
| **严重性** | **P2 中等** |
| **位置** | `brain_alpha_ops/research/pipeline.py:581-582`, `brain_alpha_ops/research/pipeline.py:636-637` |
| **类型** | 日志级别错误 |
| **原因** | 关键功能（自动校准、助手引导）的异常使用 `logger.debug` 记录，生产环境默认不会输出。 |
| **影响** | 生产环境中这些功能的失败完全不可见，无法诊断 |
| **修复方案** | 将 `logger.debug` 改为 `logger.warning`，特别是对用户可感知的功能 |

---

### DEFECT-009: calibrate_weights 顶层模块导入路径不稳定

| 字段 | 值 |
|------|-----|
| **严重性** | **P2 中等** |
| **位置** | `brain_alpha_ops/research/pipeline.py:573` |
| **类型** | 导入路径 |
| **原因** | `from calibrate_weights import auto_calibrate_if_stalled` 使用顶层模块路径，但 `calibrate_weights.py` 位于项目根目录，不在 `brain_alpha_ops` 包内。运行时是否可导入取决于 `sys.path` 配置。 |
| **影响** | 不同运行方式（CLI、web server、测试）可能导致导入失败 |
| **修复方案** | 将导入改为相对路径或使用 try/except 包装，明确处理导入失败 |

---

### DEFECT-010: 旧式类型提示

| 字段 | 值 |
|------|-----|
| **严重性** | **P2 中等** |
| **位置** | 多个文件（特别是 `hypothesis_driven_generator.py`, `generator.py`, `knowledge_base.py`） |
| **类型** | 代码风格 |
| **原因** | 使用旧式 `List[str]`, `Optional[Candidate]`, `Dict[str, Any]` 而非 Python 3.10+ 内置类型 `list[str]`, `Candidate | None`, `dict[str, Any]`。 |
| **影响** | 需要额外的 `from typing import ...` 导入，代码可读性略差 |
| **修复方案** | 逐步迁移到现代类型注解（项目已声明 `python >= 3.10`） |

---

### DEFECT-011: `web.py` 中大量导入污染模块命名空间

| 字段 | 值 |
|------|-----|
| **严重性** | **P2 中等** |
| **位置** | `brain_alpha_ops/web.py` 第 1-120 行 |
| **类型** | 模块设计 |
| **原因** | `web.py` 作为"聚合入口"导入了 40+ 个子模块的所有公开符号，文件头部 120+ 行全是导入语句。 |
| **影响** | 1) 命名空间膨胀; 2) 循环导入风险; 3) 启动时加载所有子模块（即使不需要） |
| **修复方案** | 使用 lazy import 或延迟加载模式；将 web.py 从"聚合器"改为纯粹的 server 启动入口 |

---

### DEFECT-012: 测试覆盖盲区 — auto_calibrate 路径未测试

| 字段 | 值 |
|------|-----|
| **严重性** | **P2 中等** |
| **位置** | `tests/` — 无测试覆盖 `auto_calibrate_if_stalled` |
| **类型** | 测试盲区 |
| **原因** | 搜索整个测试目录未发现对 `auto_calibrate_if_stalled` 的任何测试。由于 DEFECT-001，该功能本身也是坏的。 |
| **影响** | 自动校准功能回归无保护 |
| **修复方案** | 修复 DEFECT-001 后，补充集成测试 |

---

### DEFECT-013: 中英文混合

| 字段 | 值 |
|------|-----|
| **严重性** | **P3 轻微** |
| **位置** | 多个文件（注释、错误消息、progress 回调） |
| **类型** | 代码风格 |
| **原因** | 注释和用户消息中中英文混用，无统一规范。 |
| **影响** | 国际化困难、代码风格不一致 |
| **修复方案** | 建议代码注释英文，用户界面消息可中文（面向中文用户） |

---

### DEFECT-014: 内联 HTML 前端 335KB 单文件

| 字段 | 值 |
|------|-----|
| **严重性** | **P3 轻微** |
| **位置** | `brain_alpha_ops/web/index.html` |
| **类型** | 可维护性 / 发布封装 |
| **原因** | 生产前端仍以单文件 HTML 交付，但源码已拆分为 `brain_alpha_ops/web/js`、`brain_alpha_ops/web/css`、`index_template.html` 和 `build_inline.py`，并由 `scripts/check_frontend_surface_parity.py` 与 React mirror 严格对齐；当前 release 明确保留 inline 作为 authoritative surface。 |
| **影响** | 维护风险已由构建与 parity 守卫覆盖，不再构成未关闭缺陷。 |
| **修复方案** | None for current release; revisit only if the product decision changes and React mirror is promoted. |

---

### DEFECT-015: 日志消息中嵌入用户数据无脱敏

| 字段 | 值 |
|------|-----|
| **严重性** | **P3 轻微** |
| **位置** | 多处 logger 调用 |
| **类型** | 安全 / 日志 |
| **原因** | 部分日志消息直接嵌入用户提供的表达式、alpha ID 等数据，无长度限制或脱敏。 |
| **影响** | 日志注入风险、日志文件膨胀 |
| **修复方案** | 对嵌入日志的用户数据进行长度截断和敏感字符过滤 |

---

### DEFECT-016: Python 3.9.6 兼容性问题

| 字段 | 值 |
|------|-----|
| **严重性** | **P3 轻微** |
| **位置** | 运行环境 |
| **类型** | 兼容性 |
| **原因** | 原分析环境为 Python 3.9.6，低于项目声明的 `python >= 3.10`，可能导致 `X | Y` 等 3.10+ 语法或新标准库 API 不可用。 |
| **影响** | 在低于 3.10 的运行时可能出现 SyntaxError 或 ImportError；当前 `.venv` 已验证为 Python 3.12.13，符合项目声明。 |
| **修复方案** | 运行环境保持 Python 3.10+；`scripts/check_defect_analysis_report.py` 在 DEFECT-016 关闭时校验当前运行时满足项目要求。 |

---

## 三、修复优先级排序

### 立即修复（P0 — 本次提交）

| 序号 | 缺陷 | 修复工作量 | 风险 |
|------|------|-----------|------|
| 1 | DEFECT-001: `self.ops_config` → `self.config` | **1 行修改** | 极低 |

### 短期修复（P1 — 本周内）

| 序号 | 缺陷 | 修复工作量 | 风险 |
|------|------|-----------|------|
| 2 | DEFECT-002: 静默异常添加日志 | ~42 处修改 | 低 |
| 3 | DEFECT-008: debug → warning 级别提升 | ~5 处修改 | 极低 |
| 4 | DEFECT-009: 导入路径修复 | ~1 处修改 | 低 |
| 5 | DEFECT-006: JobExecutionResult 去重 | 提取共享模块 | 低 |
| 6 | DEFECT-012: 补充 auto_calibrate 测试 | 新增测试文件 | 极低 |

### 中期重构（P2 — 下个迭代）

| 序号 | 缺陷 | 修复工作量 | 风险 |
|------|------|-----------|------|
| 7 | DEFECT-003: web.py Lambda 门面 | 大规模重构 | 中 |
| 8 | DEFECT-004: WebHandlerDispatchContext 拆分 | 中等重构 | 中 |
| 9 | DEFECT-005: Pipeline runtime state 收口 | 当前运行态收口已完成 | 低 |
| 10 | DEFECT-007: 循环内导入 | 1 处修改 | 极低 |
| 11 | DEFECT-011: web.py 导入优化 | 中等重构 | 低 |
| 12 | DEFECT-010: 类型提示现代化 | 批量修改 | 低 |

### 长期改进（P3 — 按需）

| 序号 | 缺陷 | 修复工作量 | 风险 |
|------|------|-----------|------|
| 13 | DEFECT-013: 语言统一 | Python 注释统一已完成 | 极低 |
| 14 | DEFECT-014: 前端现代化 | 已收口 | 低 |
| 15 | DEFECT-015: 日志脱敏 | 批量修改 | 低 |
| 16 | DEFECT-016: Python 版本升级 | 已由当前 `.venv` Python 3.12.13 关闭 | 低 |

---

## 四、实施执行方案

### Phase 1: P0 紧急修复（立即执行）

**目标**: 修复运行时 Bug，恢复自动校准功能。

**步骤**:
1. 修改 `brain_alpha_ops/research/pipeline.py:574`
   - `self.ops_config.storage_dir` → `self.config.storage_dir`
2. 将 `pipeline.py:582` 的 `logger.debug` 改为 `logger.warning`
3. 验证修复: 运行 `pytest tests/ -k "pipeline" -v`

**预期时间**: 10 分钟

### Phase 2: P1 异常处理改善（本周内）

**目标**: 消除静默吞异常，确保所有异常至少有 warning 级别日志。

**步骤**:
1. **审计所有 `except Exception:` 块**:
   - 使用 `grep -rn "except Exception:" brain_alpha_ops/` 列出所有 42 处
   - 分类: (a) 已有 `logger.warning/error` — OK; (b) 仅有 `logger.debug` — 升级; (c) `pass/continue/return` — 添加日志
2. **批量修复**:
   - 对所有 `except Exception: pass/continue` 添加 `logger.warning(..., exc_info=True)`
   - 对所有 `except Exception: return` 添加 `logger.warning` 后再 return
   - 将 `logger.debug` 升级为 `logger.warning`（关键路径）
3. **补充测试**: 为 auto_calibrate 路径添加集成测试
4. **修复导入路径**: `pipeline.py:573` 的 `calibrate_weights` 导入

**预期时间**: 2-3 小时

### Phase 3: P2 代码质量改善（下个迭代）

**目标**: 消除代码重复，改善架构。

**步骤**:
1. **提取共享 JobExecutionResult**:
   - 创建 `brain_alpha_ops/job_types.py`
   - 将 `task_executor.py:52-57` 和 `adaptive_executor.py:302-307` 的 `JobExecutionResult` 移入
   - 更新两个文件的导入
2. **消除循环内导入**:
   - `pipeline.py:313` 删除 `import time as _time`，使用顶部的 `time`
3. **web.py 重构规划**:
   - 设计 `WebApplicationContext` 类封装全局状态
   - 设计 handler 所需最小接口（Protocol）
   - 创建通用 POST handler 装饰器

**预期时间**: 1-2 天

---

## 五、已关闭缺陷确认

以下缺陷在 2026-06-01 REVIEW_GAP_CLOSURE 中已验证关闭，本报告确认无需重复修复：

| 原始缺陷 | 关闭证据 |
|----------|----------|
| baseUrl SSRF 风险 | `web_config.py` 白名单验证，`test_web.py` 覆盖 |
| 请求体大小限制 | `runtime_constants.py:MAX_BODY_BYTES=2MB`，`web_http_handler.py` 拦截 |
| traceback 泄露到前端 | `web_errors.py` + `safe_error_message` 脱敏 |
| payload 数值无上限 | `web_config.py` + `web_payload_validation.py` 边界校验 |
| XSS via innerHTML | `utils.js:setSafeHtml` + 白名单验证 + `check_frontend_innerhtml.py` 守护 |
| 会话/CSRF/重放保护 | `web_security.py` + `web_session.py` 完整实现 |
| 速率限制 | `web_rate_limit.py` + 路由级 429 处理 |
| 敏感数据扫描 | `scan_sensitive_artifacts.py` 含 git history |

---

## 六、质量门禁建议

建议在 CI 中新增以下检查：

1. **bare except 检测**: 禁止 `except Exception: pass` 模式（需至少 `logger.warning`）
2. **属性存在性检查**: mypy 可捕获 `self.ops_config` 类型错误（建议启用 strict mode）
3. **导入路径检查**: 禁止从项目根目录导入（`from calibrate_weights import ...` 应改为包内导入）
4. **模块行数限制**: 单文件不超过 500 行（当前 pipeline.py 已通过 mixin 拆分缓解）

---

## 七、当前实施状态（2026-06-01）

| 缺陷 | 当前状态 | 当前证据 | 后续动作 |
|------|----------|----------|----------|
| DEFECT-001: `self.ops_config` 属性引用错误 | CLOSED_CURRENT | `brain_alpha_ops/research/pipeline.py` 现在使用 `self.config.storage_dir` 调用 `auto_calibrate_if_stalled`，并通过 `_event(...)` 构造完整 `PipelineEvent`，避免修复属性后触发新的事件构造错误。 | None for the P0 runtime blocker. |
| DEFECT-002: 部分静默回退缺少 warning 诊断 | CLOSED_CURRENT | `brain_alpha_ops/research/generator.py`, `brain_alpha_ops/research/hypothesis_driven_generator.py`, `brain_alpha_ops/research/expression_index.py`, `brain_alpha_ops/research/dataset_selector.py`, `brain_alpha_ops/research/pipeline_official_context.py`, `brain_alpha_ops/research/iterative_optimizer.py`, `brain_alpha_ops/web_sync_payload.py`, `brain_alpha_ops/official_context_datasets.py`, `brain_alpha_ops/web_assistant_snapshots.py`, `brain_alpha_ops/web_cloud_snapshot.py`, `brain_alpha_ops/data/official_context_validation.py`, `brain_alpha_ops/brain_api/official.py`, `brain_alpha_ops/config.py`, `brain_alpha_ops/research/knowledge_base.py`, `brain_alpha_ops/research/llm_review.py`, `brain_alpha_ops/agent_tools.py`, `brain_alpha_ops/agent_research_tools.py`, `brain_alpha_ops/research/repository.py`, `brain_alpha_ops/research/parallel_backtest.py`, `brain_alpha_ops/research/pipeline.py`, `brain_alpha_ops/scoring/gates.py`, `brain_alpha_ops/scoring/visualization.py`, `brain_alpha_ops/web_redline_scoring.py`, `brain_alpha_ops/ux/guided_pipeline.py`, `brain_alpha_ops/web_runtime_facade.py`, `brain_alpha_ops/web_cloud_context_refresh.py`, `brain_alpha_ops/web_check_availability.py`, `brain_alpha_ops/production_diagnostics.py`, `brain_alpha_ops/e2e_report.py`, `brain_alpha_ops/research/strategy_plugins.py`, `brain_alpha_ops/research/alerting.py`, `brain_alpha_ops/cli.py`, and `brain_alpha_ops/compliance/redline_verifier.py` now log warning-level fallback diagnostics instead of silently swallowing the same high-risk metadata/index/cache/evidence/context/guidance/callback/visualization/CLI-output/template-extraction failures. `brain_alpha_ops/web_cloud_snapshot.py` also warns when official-context save falls back from a bad config to the runtime data dir, `brain_alpha_ops/research/pipeline_official_context.py` warns when official context JSON loading falls back to the API path and when advanced official context components fall back to the base generator context, `brain_alpha_ops/config.py` warns when default dataset resolution fails before fail-closed config validation, `brain_alpha_ops/research/parallel_backtest.py` warns when individual runner jobs fail through `_job_error()` and when progress callbacks fail before returning structured job errors, `brain_alpha_ops/research/pipeline.py` warns on context refresh, scoring auto-calibration, and secondary fusion fallback failures, `brain_alpha_ops/web_redline_scoring.py` warns when scoring health auto-calibration or checkpoint status fallbacks fire, `brain_alpha_ops/scoring/gates.py` warns when configured gate checks raise before returning a failed gate item, `brain_alpha_ops/ux/guided_pipeline.py` warns when guided error classification, stop callback, core pipeline, redline, context, finalize, checkpoint, or snapshot fallbacks fire, `brain_alpha_ops/compliance/redline_verifier.py` now warns whenever a red-line check is blocked by an exception before it is recorded in the compliance report and when generator template validation cannot load official context, `brain_alpha_ops/research/llm_review.py` now warns on fallback/router provider failures with redacted messages, and `brain_alpha_ops/cli.py` now warns when an unexpected top-level CLI failure is downgraded to the user-facing error payload. | None for the warning-diagnostic scope tracked in this report. |
| DEFECT-006: JobExecutionResult 重复定义 | CLOSED_CURRENT | `brain_alpha_ops/job_types.py` now owns the shared `JobExecutionResult` dataclass, and both `brain_alpha_ops/task_executor.py` and `brain_alpha_ops/adaptive_executor.py` import the same type. | None for the duplicate result type. |
| DEFECT-007: 循环体内导入遮蔽顶层导入 | CLOSED_CURRENT | `brain_alpha_ops/research/pipeline.py` now uses the module-level `time` import directly in the periodic context refresh branch. | None for the loop-local import site. |
| DEFECT-008: 自动校准异常仅 debug 记录 | CLOSED_CURRENT | 自动校准失败日志已升级为 `logger.warning(..., exc_info=True)`，并由 `tests/test_pipeline.py::test_pipeline_auto_calibration_uses_config_storage_dir` 和 `tests/test_calibrate_weights.py` 系列覆盖。 | None for the auto-calibration failure path. |
| DEFECT-009: calibrate_weights 顶层模块导入路径不稳定 | CLOSED_CURRENT | `brain_alpha_ops/research/calibration.py` now provides a package-local wrapper for `auto_calibrate_if_stalled`, `brain_alpha_ops/research/pipeline.py` imports through that wrapper, and `pyproject.toml` explicitly installs `calibrate_weights` as a top-level module for direct CLI usage. | None for the current pipeline import path. |
| DEFECT-010: 旧式类型提示 | CLOSED_CURRENT | `brain_alpha_ops/research/dataset_selector.py`, `brain_alpha_ops/research/generator.py`, `brain_alpha_ops/research/iterative_optimizer.py`, `brain_alpha_ops/research/hypothesis_driven_generator.py`, `brain_alpha_ops/research/hypothesis_library.py`, `brain_alpha_ops/research/experience.py`, `brain_alpha_ops/research/backtest_finalization.py`, `brain_alpha_ops/research/backtest_submission.py`, `brain_alpha_ops/research/backtest_polling.py`, `brain_alpha_ops/research/convergence.py`, `brain_alpha_ops/research/diagnostics.py`, `brain_alpha_ops/research/fusion.py`, `brain_alpha_ops/research/templates.py`, `brain_alpha_ops/research/scoring_params.py`, `brain_alpha_ops/research/alpha_checks.py`, `brain_alpha_ops/research/auto_calibrator.py`, `brain_alpha_ops/research/theme_engine.py`, and `brain_alpha_ops/research/validated_generator.py` now use built-in generic and union annotations. `rg -n "\b(List|Dict|Tuple|Optional|Set|Union)\[" brain_alpha_ops/research` returns no results, and related behavior tests remain green. | None for the current `brain_alpha_ops/research` old-typing scope. |
| DEFECT-003: web.py Lambda 门面反模式 | CLOSED_CURRENT | `brain_alpha_ops/web.py` now has an explicit `WebApplicationContext` / `web_application_context()` entry point, module wrappers no longer pass `sys.modules[__name__]` through `web_runtime_facade`, and the prior 78 module-level lambda aliases have been replaced with explicit `def` wrappers. `scripts/check_web_facade_contract.py --json` reports `lambda_alias_count=0`, `runtime_facade_sys_modules_count=0`, and `direct_sys_modules_count=1` for the single context bootstrap line. | None for the lambda facade scope. |
| DEFECT-004: WebHandlerDispatchContext 超大数据类（70+ 字段） | CLOSED_CURRENT | `brain_alpha_ops/web_handler_dispatch.py` now splits the dispatch dependencies into seven grouped dataclasses (`core`, `session`, `job`, `config`, `research`, `assistant`, `actions`) while preserving legacy flat `ctx.foo` access through `WebHandlerDispatchContext.__getattr__`; `brain_alpha_ops/web_runtime_facade.py` now constructs the grouped context explicitly. `scripts/check_web_handler_dispatch_context.py --json` reports 7 top-level fields, max group size 12, no duplicate field names, and flat/grouped constructor compatibility. | None for the grouped dispatch context scope. |
| DEFECT-005: AlphaResearchPipeline God Object（10 个 mixin） | CLOSED_CURRENT | `brain_alpha_ops/research/pipeline.py` now owns runtime data through a single `PipelineRuntimeState` container with compatibility properties bound by `bind_runtime_state_properties(AlphaResearchPipeline)`. `scripts/check_pipeline_runtime_state.py --json` reports `init_self_assignment_count=3`, `runtime_state_field_count=62`, `bind_call_present=true`, and no findings; `tests/test_pipeline_runtime_state.py` verifies the pipeline instance only owns `_runtime_state` directly while legacy property access still works. | None for the current runtime-state decomposition scope; deeper mixin/run-stage decomposition remains a future architecture initiative rather than an open defect in this report. |
| DEFECT-011: `web.py` 中大量导入污染模块命名空间 | CLOSED_CURRENT | `brain_alpha_ops/web.py` now imports `brain_alpha_ops.*` implementation dependencies through private aliases and exposes legacy imported names only through the module-level `__getattr__` compatibility map. `scripts/check_web_facade_contract.py --json` reports `public_brain_alpha_import_count=0`, `lambda_alias_count=0`, and `runtime_facade_sys_modules_count=0`, while existing public calls such as `web.route_for` and monkeypatched `web.load_run_config` still work through compatibility providers. | None for the current Web facade namespace scope. |
| DEFECT-013: 中英文混合 | CLOSED_CURRENT | Python source comments and developer-facing docstrings now use English consistently; `rg -n "#.*[\\u4e00-\\u9fff]" --glob '*.py' brain_alpha_ops` returns no results. Remaining Chinese strings are intentional UI/user-facing copy, so this defect is no longer a code-comment issue. | None for the Python comment/docstring scope; UI copy can be reviewed separately if product style requires it. |
| DEFECT-014: 内联 HTML 前端 335KB 单文件 | CLOSED_CURRENT | The inline HTML/JS production surface remains intentionally authoritative for the current release, but the maintainability concern is covered by the modular source layout, build_inline synchronization, and strict frontend parity checks. | None for the current release surface. |
| DEFECT-015: 日志消息中嵌入用户数据无脱敏 | CLOSED_CURRENT | `brain_alpha_ops/research/cross_review_pipeline.py`, `brain_alpha_ops/research/hypothesis_driven_generator.py`, `brain_alpha_ops/data/ashare_adapter.py`, `brain_alpha_ops/web_redline_scoring.py`, `brain_alpha_ops/ux/guided_pipeline.py`, `brain_alpha_ops/research/strategy_plugins.py`, `brain_alpha_ops/research/knowledge_base.py`, `brain_alpha_ops/research/hypothesis_library.py`, `brain_alpha_ops/research/pipeline_submission_gate.py`, `brain_alpha_ops/research/pipeline_stages.py`, `brain_alpha_ops/research/checkpoint.py`, `brain_alpha_ops/research/alerting.py`, `brain_alpha_ops/research/local_backtest_engine.py`, `brain_alpha_ops/adaptive_executor.py`, `brain_alpha_ops/compliance/redline_verifier.py`, `brain_alpha_ops/research/repository.py`, `brain_alpha_ops/web_cloud_snapshot.py`, `brain_alpha_ops/web_submission_safety.py`, `brain_alpha_ops/web_submission_single.py`, `brain_alpha_ops/web_candidate_check.py`, `brain_alpha_ops/brain_api/official.py`, `brain_alpha_ops/research/backtest_finalization.py`, `brain_alpha_ops/research/pipeline_backtest_flow.py`, `brain_alpha_ops/research/secondary_fusion.py`, `brain_alpha_ops/web_assistant_snapshots.py`, and `brain_alpha_ops/web_check_availability.py` now redact or truncate exception, expression, identifier, and cache-path log fields before emission. `scripts/check_log_redaction.py --json` reports `finding_count=0`, and targeted tests cover the main regression paths. | None for current logger redaction scope. |
| DEFECT-016: Python 3.9.6 兼容性问题 | CLOSED_CURRENT | `pyproject.toml` declares `requires-python = ">=3.10"` and the current `.venv/bin/python` runtime is Python 3.12.13, so the previously observed Python 3.9.6 environment mismatch is no longer present. `scripts/check_defect_analysis_report.py` also reports `python_runtime_ok=true`. | None for the current Python runtime contract. |
| DEFECT-012: auto_calibrate 路径缺少测试 | CLOSED_CURRENT | `tests/test_pipeline.py::test_pipeline_auto_calibration_uses_config_storage_dir` covers the pipeline integration path, and `tests/test_calibrate_weights.py` covers the algorithm-level branches for not-ready, insufficient-features, and triggered advice paths. | None for the auto-calibrate coverage gap. |

### 当前验证

| Command | Result |
|---------|--------|
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_pipeline.py::test_pipeline_auto_calibration_uses_config_storage_dir -q` | 1 passed; 覆盖 DEFECT-001 修复和自动校准事件构造路径。 |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_pipeline.py -q` | 25 passed; pipeline 回归面保持通过。 |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_guided_pipeline.py tests/test_review_gap_closure_tracker.py -q` | 29 passed; 2026-06-01 review triage 跟踪器与 guided pipeline warning 证据保持通过。 |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_generation.py tests/test_hypothesis_driven_generator.py tests/test_expression_index.py tests/test_quality_gate.py tests/test_pipeline.py -q` | 99 passed; package-local calibration wrapper, installable-module declaration, and pipeline regressions all remained green together after the import-path stabilization. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_task_executor.py tests/test_infrastructure_modules.py::TestAdaptiveExecutor -q` | 10 passed; task and adaptive executors share one `JobExecutionResult` type while their lifecycle behavior remains green. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_infrastructure_modules.py::TestIterativeOptimizer tests/test_dynamic_research_components.py tests/test_pipeline_official_context.py tests/test_task_executor.py tests/test_infrastructure_modules.py::TestAdaptiveExecutor -q` | 27 passed; dataset selector, active dataset field lookup, and iterative optimizer strategy failures now leave warning diagnostics, and executor shared-type coverage remained green. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_pipeline_official_context.py -q` | 6 passed; official context JSON load failures and advanced component wiring failures now warn while preserving the API/base-context fallback paths and rate-limit behavior. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_generation.py tests/test_hypothesis_driven_generator.py tests/test_expression_index.py tests/test_quality_gate.py tests/test_pipeline.py tests/test_dynamic_research_components.py tests/test_pipeline_official_context.py tests/test_task_executor.py tests/test_infrastructure_modules.py -q` | 148 passed; combined verification for current generator/index/pipeline/executor/official-context/infrastructure changes. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_calibrate_weights.py tests/test_quality_gate.py::test_calibrate_weights_is_declared_as_installable_module tests/test_quality_gate.py::test_research_calibration_wrapper_exports_auto_calibrate -q` | 5 passed; auto-calibrate algorithm branches and packaging wrapper coverage are green. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_config.py -q` | 21 passed; default dataset resolution failures now warn before fail-closed config validation reports the existing error. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_web_sync_payload.py tests/test_calibrate_weights.py tests/test_dynamic_research_components.py tests/test_pipeline_official_context.py tests/test_task_executor.py tests/test_infrastructure_modules.py tests/test_quality_gate.py -q` | 90 passed; web sync context fallback diagnostics, auto-calibration coverage, dataset/context diagnostics, shared executor result type, and quality-gate coverage are green. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_web_sync_payload.py tests/test_web_sync_job.py tests/test_web_cloud_context_refresh.py -q` | 12 passed; official dataset metadata API failure now keeps the original derived-dataset fallback while emitting a warning-level diagnostic. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_web_assistant_snapshots.py -q` | 6 passed; durable job row collection and run-history lookup now warn on failure while preserving fallback behavior. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_web_assistant_snapshots.py tests/test_web_sync_job.py -q` | 12 passed; Web assistant snapshot warnings and sync job fallback behavior stayed green together. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_web_cloud_snapshot.py -q` | 11 passed; cached user alpha directory listing, per-file reads, and official-context save fallback now warn on failures while preserving the existing fallback behavior. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_cli.py -q` | 28 passed; unexpected top-level CLI failures now warn while the user-facing JSON error payload remains unchanged. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_pipeline.py -q` | 28 passed; pipeline context refresh, scoring calibration, and secondary fusion fallback failures now warn while the existing event payloads remain unchanged. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_dynamic_research_components.py -q` | 11 passed; dataset selector type-hint normalization kept the selector behavior unchanged. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_generation.py tests/test_hypothesis_driven_generator.py -q` | 35 passed; candidate generator type-hint normalization kept generation behavior unchanged. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_hypothesis_driven_generator.py tests/test_generation.py tests/test_dynamic_research_components.py tests/test_infrastructure_modules.py::TestIterativeOptimizer -q` | 47 passed; hypothesis-driven generator and iterative optimizer type-hint modernization kept their behaviors unchanged. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_hypothesis_library.py tests/test_hypothesis_driven_generator.py -q` | 42 passed; hypothesis library type-hint normalization kept loading, querying, weight update, and generation integration behavior unchanged. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_experience.py tests/test_experience_feedback.py tests/test_hypothesis_driven_generator.py -q` | 29 passed; experience-pattern type-hint normalization kept winning-pattern and feedback behavior unchanged. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_backtest_finalization.py tests/test_backtest_submission.py tests/test_backtest_polling.py -q` | 14 passed; backtest finalization/submission/polling type-hint normalization kept state transitions unchanged. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_pipeline.py tests/test_calibrate_weights.py -q` | 31 passed; convergence tracker type-hint normalization kept pipeline and calibration integration behavior unchanged. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_secondary_fusion.py tests/test_fusion_candidates.py tests/test_pipeline.py::test_pipeline_logs_secondary_fusion_exceptions -q` | 7 passed; fusion-related type-hint normalization kept secondary fusion behavior and fallback diagnostics unchanged. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_dynamic_research_components.py tests/test_hypothesis_library.py tests/test_official_scoring_system.py -q` | 35 passed; template, scoring-params, and official-scoring type-hint normalization kept their behavior unchanged. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_auto_calibrator.py tests/test_auto_calibrator_coverage.py tests/test_dynamic_research_components.py tests/test_generation.py tests/test_hypothesis_driven_generator.py tests/test_official_scoring_system.py tests/test_backtest_finalization.py -q` | 61 passed; remaining alpha checks, auto-calibrator, theme-engine, and validated-generator type-hint normalization kept their behavior unchanged. |
| `rg -n "\b(List|Dict|Tuple|Optional|Set|Union)\[" brain_alpha_ops/research` | No results; precise research old-typing scan is clean. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python scripts/check_pipeline_runtime_state.py --json` | PASS; runtime-state guard reports `init_self_assignment_count=3`, `runtime_state_field_count=62`, `bind_call_present=true`, and no findings for the current DEFECT-005 closure scope. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python scripts/check_defect_analysis_report.py --json` | PASS; report has 16 detailed defect sections, 16 status rows, 16 closed items, 0 tracked deferred items, `python_runtime=3.12.13`, `python_runtime_ok=true`, and no findings. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_defect_analysis_report.py tests/test_parallel_backtest.py tests/test_review_gap_closure_tracker.py -q` | 34 passed; defect-analysis report consistency, parallel-backtest warning diagnostics, and review-gap tracker contracts remain green together. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python scripts/check_log_redaction.py --json` | PASS; `finding_count=0` across `brain_alpha_ops`, covering raw exception logger args, logger f-strings, raw expressions, identifiers, and path-like values. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python scripts/check_web_facade_contract.py --json` | PASS; `WebApplicationContext` exists, `web_application_context()` exists, direct `sys.modules[__name__]` use is down to the single context bootstrap line, runtime facade wrappers no longer route through direct module lookups, `lambda_alias_count=0`, and `public_brain_alpha_import_count=0`. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_web.py -q` | 73 passed, 10 skipped; Web facade namespace privatization preserved legacy module access, config monkeypatch compatibility, official context cache handling, assistant guidance persistence, and local server behavior. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python scripts/check_web_handler_dispatch_context.py --json` | PASS; dispatch context has 7 top-level groups, max group size 12, no duplicate field names, and both flat and grouped construction keep legacy attribute access intact. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_log_redaction_guard.py tests/test_defect_015_log_redaction.py tests/test_guided_pipeline.py tests/test_strategy_plugins.py tests/test_ashare_adapter.py tests/test_web_redline_scoring.py tests/test_knowledge_base.py tests/test_hypothesis_library.py tests/test_checkpoint_resume.py tests/test_alerting.py tests/test_research_contracts.py tests/test_redline_verifier_diagnostics.py tests/test_web_cloud_snapshot.py tests/test_web_submission_safety.py tests/test_web_submission_single.py tests/test_web_candidate_check.py tests/test_official_adapter.py tests/test_web_assistant_snapshots.py tests/test_web_check_availability.py tests/test_enhanced_pipeline_components.py::TestLocalBacktestEngine tests/test_defect_analysis_report.py -q` | 158 passed; the logger-redaction guard and updated logging paths keep token-like exception fragments, raw f-string logger calls, direct expression leaks, identifiers, and path-like values out of logs while preserving fallback behavior. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_official_context_validation.py -q` | 4 passed; official context validation now warns when config resolution falls back to the default data directory. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_official_adapter.py -q` | 29 passed; invalid official API cache files now emit a warning and still fall back to an empty cache result. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_official_scoring_system.py -q` | 7 passed; configured gate check exceptions now warn while preserving failed gate item semantics. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_redline_verifier_diagnostics.py -q` | 3 passed; redline verifier template extraction failures, blocked verification helper paths, and official-context validation failures now warn while keeping the original blocking report behavior. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_knowledge_base.py -q` | 4 passed; evidence serialization fallback now warns while still persisting a stringified evidence payload. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_llm_review.py -q` | 12 passed; LLM fallback/router provider failures now warn with redacted messages while keeping fallback and health tracking behavior unchanged. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_agent_tools.py -q` | 36 passed; agent `list_context` and research memory guidance fallbacks now warn while preserving their default/empty fallback behavior. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_research_contracts.py -q` | 7 passed; repository incremental sqlite cache updates now warn while JSONL persistence still succeeds. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_parallel_backtest.py -q` | 6 passed; progress callback failures and per-job runner exceptions now warn while the backtest execution still completes with structured job-error payloads. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_guided_pipeline.py tests/test_guided_pipeline_coverage.py -q` | 10 passed; guided pipeline error classification, stop-callback, core, redline, finalize, checkpoint, and snapshot fallbacks now warn while preserving phase/state behavior. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_web_redline_scoring.py -q` | 7 passed; scoring health auto-calibration and checkpoint status fallbacks now warn while preserving the existing response payloads. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_new_research_tools.py -q` | 7 passed; agent research job-row collection now warns on failed stores while preserving rows from healthy stores. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_scoring_visualization.py -q` | 2 passed; attribution-tree build failures now warn and fall back to an empty visualization payload. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_web_runtime_facade_coverage.py -q` | 7 passed; CLI smoke-test output failures now warn while the command still returns success. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_redline_verifier_diagnostics.py -q` | 1 passed; redline verifier template extraction failures now warn while returning an empty fallback list. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_web_cloud_context_refresh.py -q` | 3 passed; cloud context refresh failures now warn while preserving existing fallback and partial-error behavior. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_web_check_availability.py -q` | 4 passed; official pre-submit check failures now warn while preserving the existing blocked-check fallback. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_production_diagnostics.py -q` | 6 passed; frontend inline status check failures now warn while preserving the diagnostic error payload. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_e2e_report.py -q` | 4 passed; unavailable web-console contract checker now warns while preserving the E2E summary finding payload. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_strategy_plugins.py -q` | 4 passed; strategy plugin load/runtime failures now warn while preserving registry error summaries. |
| `PYTHONPYCACHEPREFIX=/private/tmp/brain-alpha-pycache .venv/bin/python -m pytest tests/test_alerting.py -q` | 4 passed; alert callback/webhook failures now warn while preserving local alert records and existing non-blocking delivery semantics. |

---

**分析完成时间**: 2026-06-01 01:45 UTC+8  
**分析工具**: code-explorer 子代理 + 安全/质量/架构/测试四专家团队 + 手动关键路径验证
