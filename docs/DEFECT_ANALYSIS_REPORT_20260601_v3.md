# 全面缺陷分析报告与修复实施计划 v3

**日期**: 2026-06-01 13:16 CST
**分析范围**: 全代码库（258 文件：189 Python + 28 JS + 13 TSX + 实验/脚本/测试/配置）
**分析方法**: 3 个并行 code-explorer 子代理（架构/安全/代码质量）+ 关键路径手动验证 + v1/v2 报告交叉对照
**代码行数统计**: brain_alpha_ops/ 核心包 ~12,000+ 行（80+ Py 文件）+ web/js/ ~3,500 行（14 JS 文件）

---

## 一、前序缺陷状态确认

### v1 报告 16 项缺陷：全部 CLOSED_CURRENT ✅
无回溯风险。

### v2 报告 8 项缺陷：状态更新

| 编号 | 描述 | v2 状态 | **v3 确认** |
|------|------|---------|-------------|
| NEW-001 | CLI `--base-url` SSRF | P1 未修复 | ✅ **已修复** — `cli.py:559-568` 已添加 `_ALLOWED_BASE_URLS` 白名单校验 |
| NEW-002 | `list_user_alphas()` 无限分页 | P1 未修复 | ✅ **已修复** — 已恢复 `_MAX_USER_ALPHAS_PAGES` 有界循环与回归测试 |
| NEW-003 | `setSafeHtml()` 不转义 XSS | P2 未修复 | ✅ **已修复** — `setSafeHtml` 改为转义，原始 HTML 仅走显式 `setRawHtml` |
| NEW-004 | `_update_dataclass` 无类型校验 | P2 未修复 | ✅ **已修复** — dataclass 更新时按 type hint fail-closed |
| NEW-005 | CLI `--password`/`--token` 仍可用 | P2 未修复 | ✅ **已修复** — CLI 凭据参数与 escape hatch 已移除 |
| NEW-006 | stdlib 延迟导入 | P3 未修复 | ✅ **已修复** — 本轮触达的标准库延迟导入已移到顶层 |
| NEW-007 | SERVER 裸变量无锁 | P3 未修复 | ✅ **已修复** — `SERVER` 读写已由 `SERVER_LOCK` 保护 |
| NEW-008 | MD5 弱哈希（测试桩） | P3 未修复 | ✅ **已修复** — 测试桩确定性分桶已改用 SHA-256 |

### v2 → v3 汇总
- **修复完成**: 8/8（NEW-001 至 NEW-008）
- **仍未修复**: 0/8
- **新发现**: 9 项（本轮深度扫描）

### 当前实施进展（2026-06-01 本轮更新）

| 编号 | 当前状态 | 实施证据 | 后续动作 |
|------|----------|----------|----------|
| NEW-002 / DEFECT-A7 | ✅ CLOSED_CURRENT | `brain_api/official.py` 已恢复 `_MAX_USER_ALPHAS_PAGES = 500` 和有界分页循环；`tests/test_official_adapter.py` 恢复最大页数回归测试。 | 用户 Alpha 仍保留独立 offset recovery 语义。 |
| NEW-003 | ✅ CLOSED_CURRENT | `web/js/utils.js` 已拆分 `setSafeHtml`（转义）与 `setRawHtml`（显式原始 HTML）；调用方改为显式 raw wrapper；`check_frontend_innerhtml.py` 不再允许裸 `setSafeHtml` raw sink。 | 持续用 `check_frontend_innerhtml.py` 守卫新增 HTML sink。 |
| NEW-004 / DEFECT-A9 | ✅ CLOSED_CURRENT | `config.py::_update_dataclass` 已按 dataclass type hint 做 fail-closed 类型校验并记录 warning。 | 范围/枚举仍由现有 schema 与 `validate_run_config()` 覆盖。 |
| NEW-005 | ✅ CLOSED_CURRENT | `cli.py` 已移除 `--username` / `--password` / `--token` / `--allow-insecure-cli-credentials`，CLI 凭据仅走环境变量。 | 如需临时调试，应使用环境变量或专用本地配置，不恢复命令行凭据。 |
| NEW-006 / DEFECT-A8 | ✅ CLOSED_CURRENT | `official_scoring.py`、`data/loader.py`、`brain_api/official.py`、`research/safety.py` 等相关标准库导入已移到模块顶层。 | 可继续用局部扫描发现新增延迟导入。 |
| NEW-007 | ✅ CLOSED_CURRENT | `web.py` 新增 `SERVER_LOCK`，`web_runtime_facade.py` 对 `SERVER` 读写加锁。 | 若后续拆 facade，可将 server 状态进一步封装。 |
| NEW-008 | ✅ CLOSED_CURRENT | `tests/production_api_stub.py` 的确定性分桶已由 MD5 改为 SHA-256。 | None。 |
| DEFECT-A3 | ✅ CLOSED_CURRENT | `web_handler_dispatch.py` 已提取 `_reject_auxiliary_conflict()` 消除 5 处重复冲突响应样板。 | None for this duplication pattern。 |
| DEFECT-A4 | ✅ CLOSED_CURRENT | `research/safety.py`、`research/assistant.py`、`research/templates.py`、`research/repository.py` 的 JSON 解析失败现在留下 warning 或最后错误上下文。 | 可按需增加 corrupt-line 指标汇总。 |
| DEFECT-A5 | ✅ CLOSED_CURRENT | `_launch_monitor.py` 已移除导入即执行和重复主逻辑，子进程环境改为 allowlist 且不透传 BRAIN 凭据。 | 如果生产 exe 需要凭据，需设计显式安全凭据通道，不能回退为全环境透传。 |
| DEFECT-A2 | ✅ CLOSED_CURRENT | `brain_api/official.py` 已提取 `_paginate_collection()`，四个列表方法统一复用同一分页/重复页/上限逻辑；通用实现已下沉到 `brain_api/pagination.py`；`tests/test_official_adapter.py` 相关回归通过。 | 后续官方 API 拆分可继续围绕认证、数据、模拟、提交等职责分批下沉。 |
| DEFECT-A6 | ✅ CLOSED_CURRENT | `FRONTEND_SURFACE_PARITY_PLAN.json` 已映射全部 16 个 inline 视图并接受 4 个 React-only 运营页；当前发布决策保持 inline 为生产面、React 为 mirror/preview；严格 parity 检查通过。 | 未来是否推广 React 为唯一生产面属于产品决策，推广前继续保持 parity gate 与 preview smoke 绿色。 |
| MODULE-SIZE-GATE | ✅ CLOSED_CURRENT | `config.py`、`research/assistant.py`、`web_handler_dispatch.py`、`ux/guided_pipeline.py` 已拆分到阈值内；`guided_pipeline.py` 进一步降至 467 行，`guided_models.py` / `guided_storage.py` / `guided_display.py` / `guided_cli.py` 分担模型、存储、展示、CLI 职责；`scripts/check_module_size.py --json` 与 `scripts/quality_gate.py --skip-tests --json` 均通过。 | 继续避免在高热模块内堆叠新职责。 |
| DEFECT-A1 | ✅ CLOSED_CURRENT | 本轮已收口 module size 门禁、分页重复与双前端当前发布决策；`redline_verifier.py` 已拆成编排层、`redline_models.py`、`redline_helpers.py` 和 6 个 `redline_check_*.py` 模块，主编排文件降至 126 行；`official.py` 通用分页实现已下沉到 `brain_api/pagination.py`，cache key/path/read/write 已下沉到 `brain_api/cache.py`，auth/profile 方法已下沉到 `brain_api/official_auth.py`，official context 数据拉取方法已下沉到 `brain_api/official_context.py`，HTTP request 构造/重试已下沉到 `brain_api/official_request.py`，simulation/check/submit/prod-correlation 方法已下沉到 `brain_api/official_simulation.py`，表达式验证已下沉到 `brain_api/official_validation.py`，`OfficialBrainAPI` 保留旧私有 cache/auth/request 和公开 client 方法兼容门面，主文件降至 155 行；`web_handler_dispatch.py` 已用 `_validated_post_route()` / `_read_validated_payload()` 统一 POST JSON 读取、payload 校验和错误包装样板，主文件降至 669 行；`config.py` 已拆出 `config_models.py`、`config_domain_validation.py`、`config_type_validation.py`、`config_update.py` 与 `config_validation_helpers.py`，主文件降至 199 行并保留旧 dataclass/validator re-export 兼容；`cli.py` 已拆成 58 行入口 facade、`cli_handlers.py` 命令执行表、`cli_parser.py` per-command parser builder；`guided_pipeline.py` 已拆出 guided 模型、checkpoint/history、console display 与 CLI adapter，主文件降至 467 行且保留兼容 re-export；`agent_tools.py` 已拆出 live API/simulation/submit/sync/parallel backtest mixin，主门面降至 509 行。 | None。 |

---

## 二、本轮新发现缺陷（深度全栈扫描）

### DEFECT-A1: God Object 集群 — 7 个超大类/模块

| 文件 | 行数 | 类/模块 | 问题严重度 | 具体表现 |
|------|------|---------|------------|----------|
| `compliance/redline_verifier.py` | 126 + 6 个 check 模块 | `RedLineVerifier` 编排层 + 独立红线检查模块 | **P1** | ✅ 已拆分：主文件只保留编排/CLI，6 条 `_verify_redline_N_*` 已下沉到 `redline_check_*.py`，模型与 helper 也已独立。 |
| `brain_api/official.py` | 155 + `brain_api/official_validation.py` 107 + `brain_api/official_context.py` 205 + `brain_api/cache.py` 94 + `brain_api/official_auth.py` 108 + `brain_api/official_request.py` 113 + `brain_api/official_simulation.py` 134 | `OfficialBrainAPI` facade + validation/context/cache/auth/request/simulation helpers | **P1** | 通用分页 helper 已下沉到 `brain_api/pagination.py`，official context 数据拉取方法已下沉到 `brain_api/official_context.py`，cache key/path/read/write 已下沉到 `brain_api/cache.py`，auth/profile 方法已下沉到 `brain_api/official_auth.py`，HTTP request 构造/重试已下沉到 `brain_api/official_request.py`，simulation/check/submit/prod-correlation 方法已下沉到 `brain_api/official_simulation.py`，表达式验证已下沉到 `brain_api/official_validation.py`；主类保留 `_throttle` / `_open` / cache facade 等兼容点。 |
| `web_handler_dispatch.py` | 669 | 7 个 DispatchContext + 路由处理函数 | **P2** | ✅ 已拆分/收口：DispatchContext 已独立到 `web_dispatch_context.py`；POST 路由通过 `_validated_post_route()` 与 `_read_validated_payload()` 统一 `_read_json` → `validate_*_payload` → `_json(web_error(...))` 样板，各 handler 保留自身业务分支、冲突检查、job 启动和锁顺序。 |
| `config.py` | 199 + `config_models.py` 226 + `config_domain_validation.py` 343 + `config_type_validation.py` + `config_update.py` + `config_validation_helpers.py` | 配置加载 facade + dataclass 模型 + 域校验/类型校验/更新 helper | **P2** | ✅ 已拆分：dataclass 模型下沉到 `config_models.py`，配置域枚举与高层校验下沉到 `config_domain_validation.py`，dataclass 类型校验、合并更新和低层校验器分别保留在独立 helper；`config.py` 只保留加载、写入、路径解析、根级校验和兼容 re-export。 |
| `ux/guided_pipeline.py` | 467 + 4 个 guided helper 模块 | `GuidedPipeline` facade + 模型/存储/展示/CLI adapter | **P2** | ✅ 已拆分：`PipelinePhase` / `CheckpointData` / `RunRecord` 下沉到 `guided_models.py`；checkpoint/history 下沉到 `guided_storage.py`；终端展示下沉到 `guided_display.py`；CLI 入口下沉到 `guided_cli.py`；`guided_pipeline.py` 保留 `GuidedPipeline` facade、旧导入符号与 `run_pipeline_from_config` monkeypatch 兼容点。 |
| `cli.py` + `cli_handlers.py` + `cli_parser.py` | 58 + 606 + 162 | CLI facade + `COMMAND_HANDLERS` + per-command parser builder | **P2** | ✅ 已拆分：`cli.py` 只保留入口、错误包装和兼容 re-export；命令执行下沉到 `cli_handlers.py`；parser 构造下沉到 `cli_parser.py` 的 per-command builder。 |
| `agent_tools.py` | 509 + `agent_live_tools.py` 279 | `BrainAlphaToolbox` facade + live API mixin | **P2** | ✅ 已拆分 live API、simulation batch、submit、sync、parallel backtest 到 `agent_live_tools.py`；`agent_tools.py` 保留安全 dispatch、工具注册、研究/assistant 本地工具和 monkeypatch 兼容导入。 |

### DEFECT-A2: 分页逻辑 4 次重复实现（✅ CLOSED_CURRENT）

| 文件 | 位置 | 严重度 |
|------|------|--------|
| `brain_api/official_context.py:45-81` | `list_fields()` | **P2** |
| `brain_api/official_context.py:83-122` | `list_datasets()` | **P2** |
| `brain_api/official_context.py:124-148` | `list_operators()` | **P2** |
| `brain_api/official_context.py:150-205` | `list_user_alphas()` | **P2** |

原始实现中，4 个方法包含**几乎完全相同**的分页逻辑（`seen_page_signatures` + 页循环 + 去重 + 截断 + 错误恢复），仅 URL、limit 常量和规范化函数不同。当前树已提取通用 `_paginate_collection()`；用户 Alpha 通过 `stop_when_total_reached=False` 和 `page_error_recovery` 保留“不能仅凭 total 提前结束”与 offset recovery 特殊语义。

### DEFECT-A3: 冲突检测模式 5 次重复

| 文件 | 行号 | 严重度 |
|------|------|--------|
| `web_handler_dispatch.py` | 616, 659, 699, 728, 904 | **P2** |

完全相同的 `ctx.active_auxiliary_operation(exclude=...)` + `handler._json({"ok": False, "error_code": "CONFLICT_AUX_OP", ...}, status=409)` 样板重复 5 次。

### DEFECT-A4: `json.JSONDecodeError` 静默吞噬

| 文件 | 行号 | 严重度 |
|------|------|--------|
| `research/safety.py` | 119-120 | **P2** |
| `research/assistant.py` | 616-617, 623-624 | **P2** |
| `research/templates.py` | 120-121 | **P2** |
| `research/repository.py` | 194-195 | **P2** |

使用 `except json.JSONDecodeError: pass` 跳过损坏的 JSON 行。在 append-only 日志场景中可能是设计选择，但缺乏可观测性：无日志、无计数、无告警。数据损坏只能通过不一致的结果来反推。

### DEFECT-A5: 环境变量凭据通过子进程泄露

| 文件 | 位置 | 严重度 |
|------|------|--------|
| `_launch_monitor.py` | 23, 83 | **P2** |

启动监控脚本使用 `subprocess.Popen(..., env=child_env)` 启动生产可执行文件，其中 `child_env = os.environ.copy()` 会包含 `BRAIN_TOKEN`、`BRAIN_PASSWORD` 等整个父环境。虽为 `subprocess` 标准行为，但在安全敏感场景下，凭据不应被传给子进程的完整环境。

### DEFECT-A6: 前端内联 HTML 与 React 双前端架构冗余（✅ CLOSED_CURRENT）

| 涉及文件 | 规模 | 严重度 |
|----------|------|--------|
| `web/js/` (14 个 JS 文件) | ~3,500 行 | **P2** |
| `web/index.html` (内联 JS 版本) | 多个副本 | **P2** |
| `web/react_app/` (React 18 TS) | ~2,000+ 行 | **P2** |

维护两套前端（内联 JS SPA + React 18 TS + Tailwind CSS）存在：
1. 功能不一致风险（内联版本有 `setSafeHtml` 定义，React 版本无）
2. 维护成本翻倍
3. 内联 `setSafeHtml` 名称误导已是跨前端一致性问题

当前发布决策已经明确：inline HTML/JS console 保持生产面，React 保持 mirror/preview。`docs/FRONTEND_SURFACE_PARITY_PLAN.json` 映射全部 16 个 inline 视图，显式接受 React-only 的 `dashboard`、`scoring`、`submission`、`config` 运营页；`scripts/check_frontend_surface_parity.py --json --fail-on-gaps --fail-on-unmapped-plan --fail-on-unimplemented-plan --fail-on-stale-plan` 通过。未来推广 React 为唯一生产面属于产品决策，推广前继续由 parity gate 和 React preview smoke 保护。

### DEFECT-A7: `while True` 无限循环无超时保护

| 文件 | 行号 | 描述 | 严重度 |
|------|------|------|--------|
| `brain_api/official_context.py` | 185-197 | `list_user_alphas()` 有界分页 | **P1** |
| `brain_api/official_context.py` | 150-205 | 用户 Alpha 分页职责已下沉并保留硬上限 | **P1** |

虽有 `seen_page_signatures` 去重保护、`page_items < limit` 截断保护，但若 API 持续返回非重复且满页数据，无硬上限会导致死循环。

### DEFECT-A8: 标准库延迟导入（模块级应顶层导入）

| 文件 | 导入 | 严重度 |
|------|------|--------|
| `research/pipeline.py` | `import hashlib` 在函数内 | **P3** |
| `config.py` 或 `research/context.py` | `import logging` 在函数内 | **P3** |
| `research/pipeline.py` | `import time` 在函数内 | **P3** |

标准库模块应从模块顶层导入。延迟导入仅适用于：循环导入消除、重型可选依赖、条件平台导入。这 3 处不满足条件。

### DEFECT-A9: `_update_dataclass` 缺少类型/范围校验

| 文件 | 行号 | 严重度 |
|------|------|--------|
| `config.py` | 882-898 | **P2** |

`_update_dataclass(instance, data)` 直接 `setattr(instance, key, value)`，不校验值的类型、范围或约束。若传入恶意或错误数据（如将 `int` 字段设为 `str`、将有限范围字段设为超大值），会被静默接受，后续逻辑可能抛无法追溯的错误。

---

## 三、完整缺陷清单（v1+v2+v3 合并）

### P1 严重缺陷（必须修复）

| 编号 | 描述 | 位置 | 状态 |
|------|------|------|------|
| NEW-002 | `list_user_alphas()` 无限分页 | `brain_api/official_context.py:185-197` | ✅ CLOSED_CURRENT |
| DEFECT-A1a | `redline_verifier.py` God Object (1,143 行) | `compliance/redline_verifier.py` | ✅ CLOSED_CURRENT |
| DEFECT-A1b | `official.py` God Object (935 行) | `brain_api/official.py` | ✅ CLOSED_CURRENT |
| DEFECT-A7 | `while True` 无超时保护的无限循环 | `brain_api/official_context.py:150-205` | ✅ CLOSED_CURRENT |

### P2 中等缺陷（应该修复）

| 编号 | 描述 | 位置 | 状态 |
|------|------|------|------|
| NEW-003 | `setSafeHtml()` 不转义 HTML | `web/js/utils.js:154-157` | ✅ CLOSED_CURRENT |
| NEW-004 | `_update_dataclass` 无类型校验 | `config.py:882-898` | ✅ CLOSED_CURRENT |
| NEW-005 | CLI `--password`/`--token` 仍可用 | `cli.py:70-88, 570-582` | ✅ CLOSED_CURRENT |
| DEFECT-A1c-g | 5 个 God Object (config/web_handler/guided/cli/agent_tools) | 见上文 | ✅ CLOSED_CURRENT |
| DEFECT-A2 | 分页逻辑 4 次重复 | `brain_api/official.py` | ✅ CLOSED_CURRENT |
| DEFECT-A3 | 冲突检测模式 5 次重复 | `web_handler_dispatch.py` | ✅ CLOSED_CURRENT |
| DEFECT-A4 | `json.JSONDecodeError` 静默吞噬 4 处 | 多个文件 | ✅ CLOSED_CURRENT |
| DEFECT-A5 | 子进程凭据泄露 | `_launch_monitor.py:23,83` | ✅ CLOSED_CURRENT |
| DEFECT-A6 | 双前端架构冗余 | `web/js/` + `web/react_app/` | ✅ CLOSED_CURRENT |

### P3 轻微缺陷

| 编号 | 描述 | 位置 | 状态 |
|------|------|------|------|
| NEW-006 | stdlib 延迟导入 3 处 | pipeline.py, config.py, context.py | ✅ CLOSED_CURRENT |
| NEW-007 | SERVER 裸变量无锁 | `web.py:625` | ✅ CLOSED_CURRENT |
| NEW-008 | MD5 弱哈希（测试桩） | `tests/` 内 | ✅ CLOSED_CURRENT |
| DEFECT-A8 | 标准库延迟导入（额外 3 处确认） | pipeline.py | ✅ CLOSED_CURRENT |

---

## 四、修复实施计划

### 第 1 阶段：安全阻断项（预计 1 小时）

| 优先级 | 缺陷 | 修复方案 | 预期工时 |
|--------|------|----------|----------|
| **P1** | NEW-002: 无限分页 | 在 `list_user_alphas()` 循环中添加 `_MAX_USER_ALPHAS_PAGES = 500` 上限，超限时 `logger.warning` + `break` | 15 min |
| **P1** | DEFECT-A7: `while True` 超时保护 | 同上，添加页计数器 + 硬上限 + 截断告警 | 同上（合并修复） |
| **P2** | NEW-005: CLI 凭据参数 | 移除 `--username`/`--password`/`--token`/`--allow-insecure-cli-credentials` 参数，仅保留环境变量方式 | 20 min |
| **P2** | NEW-003: `setSafeHtml` | 1) 内部调用 `Utils.escapeHtml` 转义后再设置 `innerHTML`；2) 新增 `setRawHtml` 用于已知安全的 HTML；3) 更新所有调用方审计 | 25 min |

### 第 2 阶段：代码质量改善（预计 3.5 小时）

| 缺陷 | 修复方案 | 预期工时 |
|------|----------|----------|
| **NEW-004**: `_update_dataclass` 校验 | 添加字段类型检查：验证 `value` 类型与 dataclass 字段类型匹配，不匹配时 `logger.warning` + skip | 20 min |
| **DEFECT-A2**: 分页去重 | 已实施：提取通用 `_paginate_collection(...)` 方法，4 个方法委托调用 | 45 min |
| **DEFECT-A3**: 冲突检测去重 | 提取 `_check_auxiliary_conflict(ctx, exclude, handler)` 辅助函数 | 20 min |
| **DEFECT-A4**: JSON 解析错误处理 | 在 4 处 `except json.JSONDecodeError` 中添加 `logger.warning("corrupt JSON line skipped in ...", exc_info=True)` + `corrupt_lines` 计数器 | 30 min |
| **DEFECT-A5**: 子进程凭据清理 | `_launch_monitor.py` 中 `child_env = os.environ.copy()` 后显式 `child_env.pop(key, None)` 清理 BRAIN_USERNAME/BRAIN_PASSWORD/BRAIN_TOKEN | 10 min |
| **DEFECT-A6**: 双前端统一 | 已实施当前发布决策：inline 保持生产面，React 保持 mirror/preview；`FRONTEND_SURFACE_PARITY_PLAN.json` 与严格 parity gate 约束未来推广条件 | 路线图 30 min，推广另计 |

### 第 3 阶段：架构重构（预计 6-8 小时，可分批次）

| 缺陷 | 重构方案 | 预期工时 |
|------|----------|----------|
| **DEFECT-A1a**: `redline_verifier.py` | 已拆分为 `redline_models.py`、`redline_helpers.py` 和 6 个 `redline_check_*.py` 模块，`redline_verifier.py` 保留为编排/CLI facade，并 re-export 旧私有函数名保持兼容。 | 已完成 |
| **DEFECT-A1b**: `official.py` | 已完成：通用分页 helper 下沉到 `brain_api/pagination.py`，official context 数据拉取方法下沉到 `brain_api/official_context.py`，cache key/path/read/write 下沉到 `brain_api/cache.py`，auth/profile 方法下沉到 `brain_api/official_auth.py`，HTTP request 构造/重试下沉到 `brain_api/official_request.py`，simulation/check/submit/prod-correlation 方法下沉到 `brain_api/official_simulation.py`，表达式验证下沉到 `brain_api/official_validation.py`，`OfficialBrainAPI` 保留 facade 与旧私有 helper 名称兼容。 | 已完成 |
| **DEFECT-A1c**: `web_handler_dispatch.py` | 已提取 `_validated_post_route()` 装饰器和 `_read_validated_payload()` helper，统一 POST payload 校验与错误包装样板，同时保留原路由表和业务 side-effect 顺序。 | 已完成 |
| **DEFECT-A1d**: `cli.py` | 已完成：`_main()` 委托 `cli_handlers.run_command()`，具体命令由 `COMMAND_HANDLERS` 字典映射到独立 handler；`build_parser()` 已拆到 `cli_parser.py` 的 per-command sub-builder。 | 已完成 |
| **DEFECT-A1e-g**: config/guided/agent_tools | `config.py` 已拆出 dataclass 模型、配置域校验、类型校验、dataclass 更新和低层校验器，主文件降至 199 行；`guided_pipeline.py` 已拆出模型、checkpoint/history、console display 与 CLI adapter，主文件降至 467 行；`agent_tools.py` 已拆出 live API 工具 mixin，主门面降至 509 行。 | 已完成 |

### 第 4 阶段：P3 微修复（预计 1 小时）

| 缺陷 | 修复方案 | 预期工时 |
|------|----------|----------|
| **NEW-006**: stdlib 延迟导入 | 将 `import hashlib`/`logging`/`time` 移到模块顶层 | 10 min |
| **NEW-007**: SERVER 裸变量 | `web.py:625` 的 `web.SERVER = server` 使用 `threading.Lock` 保护，或使用 `web_runtime_facade.py` 的模块级变量 | 15 min |
| **NEW-008**: MD5 弱哈希 | 测试桩中的 `hashlib.md5` 替换为 `hashlib.sha256` | 10 min |

---

## 五、实施优先级路线图

```
第 1 阶段（紧急，1h）
  ├── NEW-002 + DEFECT-A7: 无限分页修复 (15min)
  ├── NEW-005: 移除 CLI 凭据参数 (20min)
  └── NEW-003: setSafeHtml 安全加固 (25min)

第 2 阶段（本周，3.5h）
  ├── DEFECT-A2: 分页去重 (45min, 已完成)
  ├── DEFECT-A4: JSON 错误处理 (30min)
  ├── NEW-004: _update_dataclass 校验 (20min)
  ├── DEFECT-A3: 冲突检测去重 (20min)
  ├── DEFECT-A5: 子进程凭据清理 (10min)
  └── DEFECT-A6: 前端统一路线图 (30min, 当前发布决策已完成)

第 3 阶段（下周起，分批 8h）
  ├── DEFECT-A1b: official.py 拆分 (已完成)
  ├── DEFECT-A1a: redline_verifier 拆分 (2h)
  ├── DEFECT-A1c+d: web_handler + cli 重构 (已完成)
  └── DEFECT-A1e-g: config/guided/agent_tools (已完成)

第 4 阶段（快速清扫，1h）
  ├── NEW-006: stdlib 顶层导入 (10min)
  ├── NEW-007: SERVER 锁保护 (15min)
  └── NEW-008: MD5→SHA256 (10min)
```

---

## 六、验证计划

每阶段修复完成后执行：

| 阶段 | 验证步骤 |
|------|----------|
| 1 | `python -m pytest tests/ -x -q` + `python scripts/quality_gate.py` + 手动测试 `cli.py run --base-url` 白名单拒绝 |
| 2 | `python -m pytest tests/brain_api/ tests/research/ -x -q` + `python scripts/check_frontend_syntax.py` |
| 3 | 全量回归 `python -m pytest tests/ -x --cov=brain_alpha_ops --cov-fail-under=80` + `python scripts/quality_gate.py` |
| 4 | `python -m pytest tests/ -x -q` + CI 质量门禁全绿 |

---

## 七、综合评分

| 维度 | v1 | v2 | v3 |
|------|----|----|-----|
| 安全 | 6/10 | 8/10 | 8.5/10 |
| 代码质量 | 5/10 | 7/10 | 6.5/10 |
| 架构 | 6/10 | 7.5/10 | 7/10 |
| 测试覆盖 | 8/10 | 8/10 | 8/10 |
| 可维护性 | 5/10 | 7/10 | 6/10 |
| **综合** | **6/10** | **7.5/10** | **7.2/10** |

> v3 评分略有下降原因：本轮深度扫描发现了 9 项新缺陷（7 个 God Object、分页/冲突检测重复、JSON 错误吞噬、子进程凭据泄露、双前端冗余），降低了代码质量和可维护性评分。这些先前被忽视的结构性问题构成了显著的技术债。

**目标修复后评分**: 8.8/10（修复所有 P1/P2 缺陷，完成前 2 阶段）
