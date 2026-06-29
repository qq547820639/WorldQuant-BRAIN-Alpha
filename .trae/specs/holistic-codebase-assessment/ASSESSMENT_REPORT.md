# BRAIN Alpha Ops 全量源码整体评估报告

## 报告头

- **评估日期**：2026-06-29
- **代码基准**：当前 git working tree（HEAD 状态）
- **评估范围**：`brain_alpha_ops/` 全部子包（research / scoring / compliance / audit_trail / monitoring / production_diagnostics / web_candidates / web_cloud / brain_api / browser / data / config / agent_tools / agent_tool_registry / shared / tasks / ux / i18n / e2e_report / examples / web）+ 顶层入口（launch_web / _launch_monitor / build_prod / fetch_official_context）+ 桥接文件（_web_bridge / _config_domain_helpers / _runtime_constants_helpers / _config_schema_helpers / _types_extras）+ React 前端（react_app/src 全部 .ts/.tsx/.css）+ 配置/构建/CI
- **方法论**：6 个并行子智能体深读全部源码（约 590+ 个文件）→ 1 个子智能体通读 23 份历史审计文档建立交叉核对 → 主线程汇总去重分类。所有结论基于当前磁盘代码状态，不基于版本历史或 spec 推断。
- **覆盖统计**：后端 Python ~440 个文件 + React 前端 ~180 个文件 + 配置/构建/CI 文件 + 23 份历史文档，已实际 Read 完毕。
- **维度限定**：本报告仅聚焦三大核心维度——功能缺陷（Functional）/ 用户体验（UX）/ WebUI 问题。严格排除代码风格、命名规范、注释缺失、类型注解、import 顺序、文件行数、lint 告警、测试覆盖率、文档拼写等非实质性问题。

## 总体结论

**项目整体健康度定性**：**功能层有数项 Critical 数值/状态正确性缺陷直接危及反过拟合完整性与生产提交安全；WebUI 存在阻断态交互未隔离、首屏空白、路由不进 URL 等阻断级缺陷；UX 层断连取消、错误引导、轮询策略存在系统性问题。** 项目可运行但**未达生产就绪**，需立即修复 P0 项后方可投入真实账户使用。

**三维度问题计数**：

| 维度 | Critical | High | Medium | 小计 |
|------|----------|------|--------|------|
| 功能缺陷 (Functional) | 7 | 30 | 18 | 55 |
| 用户体验 (UX) | 0 | 4 | 11 | 15 |
| WebUI | 1 | 8 | 6 | 15 |
| **合计** | **8** | **42** | **35** | **85** |

---

## 维度一：功能缺陷（Functional Defects）

### Critical

#### F-001 反过拟合回退链用 IC series 当作 returns，产生虚假完美分数
- **文件**：`brain_alpha_ops/scoring/anti_overfit/service.py:32-56`
- **根因**：`AntiOverfitService.evaluate` 中三条 series 的 fallback 链存在语义混淆。当 `returns_series` / `forward_returns` 缺失时，`returns` 和 `forward_returns` 均回退到 `ic_series`（Spearman 相关系数序列）或 `factor_values`。IC series 是相关性度量而非收益率，将其当作 returns 输入 IC 稳定性、placebo、half-life 检查，会在语义不一致的数据上计算，产生 IC≈1.0 的虚假完美稳定性。
- **影响**：反过拟合四层验证套件全部受影响。被影响的候选会获得 `passed=True` 与高分 `recommendation="pass"`，进入 `submission["anti_overfit_report"]`，可能绕过本应拦截的过拟合候选直达提交门禁。
- **触发条件**：候选的 `official_metrics` 中缺少 `returns_series` 或 `forward_returns` 字段（只有 `ic_series` / `factor_values`）时触发。在官方指标不完整或字段名变更时极易发生。
- **改进方向**：fallback 链应严格区分语义——`returns` 只能回退到 returns 语义字段；当必要字段缺失时应直接返回 `insufficient_data`（fail-closed），而非用不相关数据填充。

#### F-002 IC 稳定性检查退化：`_rank_ic` 返回单元素列表导致 `ic_std` 恒为 0
- **文件**：`brain_alpha_ops/scoring/anti_overfit/ic_stability.py:36-42` + `brain_alpha_ops/scoring/anti_overfit/utils.py:63-69`
- **根因**：`compute_ic_stability` 调用 `_rank_ic(factor_values[:n], forward_returns[:n])`，而 `_rank_ic` 实现为 `return [_spearman_r(x, y)] if x and y else [0.0]`——返回单元素列表。随后 `_safe_std` 对 `n < 2` 直接返回 `0.0`。因此 `ic_std_val` 恒为 0，使 `stability_score = 50.0`（恒满分），`passed` 中 `ic_std_val <= max_ic_std`（0 <= 0.08）恒为 True。
- **影响**：反过拟合第一层（IC Stability）失效。任何 IC 均值 ≥ 0.02 的候选无论 IC 波动多大都会通过稳定性检查。
- **触发条件**：所有调用 `compute_ic_stability` 的路径（即 `run_anti_overfit_suite`）均触发，只要 `factor_values` 和 `forward_returns` 非空。
- **改进方向**：`_rank_ic` 应按时间窗口（如月度/周度）分段计算多个 cross-sectional IC 值，返回多元素列表，使 `ic_std` 能反映真实波动。

#### F-003 ashare `load_index_universe` 缓存键含 `end=None` 致数据陈旧
- **文件**：`brain_alpha_ops/data/ashare_adapter/_provider.py:132`
- **根因**：`cache_key = f"index_universe_{index_code}_{start}_{end}"`，当调用方未显式传 `end`（默认 `None`）时，键形如 `index_universe_000300_2020-01-01_None`，与所有未传 `end` 的后续调用共享同一键。第一天调用拉取截至 2026-06-28 的数据并写入缓存；第二天再调用（仍不传 `end`）直接命中旧缓存，返回昨日数据。
- **影响**：回测 / 候选生成使用陈旧行情，数值结果失真，反过拟合、评分、回测决策均基于过期数据。
- **触发条件**：ashare 适配器启用 + 调用 `load_index_universe` 时未传 `end`（默认行为）。
- **改进方向**：`end = end or datetime.date.today().isoformat()`，或把 `end` 默认值纳入键后再哈希；同时给缓存项加 TTL。

#### F-004 `error_catalog` 将任意 `KeyError` 一律归类为 `dataset_missing`
- **文件**：`brain_alpha_ops/error_catalog.py:309-310`
- **根因**：`_kind_from_type` 内 `if isinstance(exc, KeyError): return ErrorKind.dataset_missing`。KeyError 是 Python 内最常见的字典查找异常，远不止 dataset 查找场景。
- **影响**：内部字典 lookup 失败（如配置字段、job 字段、payload 字段缺失）被前端渲染成"数据集缺失"错误，误导用户去刷新数据集而非修配置；同时错误恢复 URL 错误指向 `/config`，阻断真实恢复路径。
- **触发条件**：任何内部代码抛 `KeyError`，未带 `error_code`/`status_code` 属性。
- **改进方向**：仅在 `exc.args[0]` 为已知 dataset 维度字段名或带 `dataset_not_found` 标记时才归类为 `dataset_missing`；其余 `KeyError` 走 fallback `internal_error` kind。

#### F-005 `runtime_constants.real_submit_test_override_enabled` 依赖 `PYTEST_CURRENT_TEST` env 可被生产伪造
- **文件**：`brain_alpha_ops/runtime_constants.py:321-330`
- **根因**：`bool(os.environ.get("PYTEST_CURRENT_TEST"))` 是判定的三项之一。该 env var 虽由 pytest 自动设置，但任何能写进程 env 的运维 / 容器编排都能伪造，配合 `BRAIN_ALPHA_FORCE_REAL_SUBMIT=1` + `BRAIN_ALPHA_ENABLE_REAL_SUBMIT_TESTS=1` 即可绕过 `REAL_SUBMIT_DISABLED_WEB_FLOW` 硬开关。
- **影响**：Web 控制台真实提交禁令被绕过，可能导致真实 alpha 被提交至生产 BRAIN 账号，造成不可逆的真实账户操作。
- **触发条件**：攻击者 / 误操作者同时设置上述三个 env var。
- **改进方向**：用 `sys._getframe` 检查调用栈是否在 `pytest` 内，或干脆移除 env-based override，改用编译期常量 + 单元测试 monkey-patch。

#### F-006 Docker 容器以 root 运行 + `evidence` 目录 `chmod 777`
- **文件**：`Dockerfile:91-92`
- **根因**：`RUN mkdir -p /app/data /app/config /app/artifacts/evidence && chmod 777 /app/artifacts/evidence`，且镜像无 `USER` 指令，容器以 root 启动。
- **影响**：容器逃逸或 RCE 时攻击者直接获得 root 权限；777 权限让任意进程可篡改/删除证据文件，破坏审计链不可篡改性。
- **触发条件**：使用默认 `docker run` / `docker-compose up` 部署。
- **改进方向**：`RUN useradd -m appuser && chown -R appuser:appuser /app && USER appuser`；evidence 目录改为 `750` 并由运行用户独占。

#### F-007 `docker-compose.yml` 端口绑定 `0.0.0.0:8765` 暴露公网且无安全加固
- **文件**：`docker-compose.yml:5-6, 12`
- **根因**：`ports: - "8765:8765"` 默认绑定到 `0.0.0.0`；`environment.WEB_HOST=0.0.0.0`；服务定义无 `cap_drop`、`security_opt: no-new-privileges`、`read_only: true`、`mem_limit`、`cpus` 等约束。
- **影响**：本应仅本机访问的 Web 控制台（含 admin token、提交入口）暴露到 LAN / 公网；容器被攻陷后无资源限制可被用作挖矿 / DoS 跳板。
- **触发条件**：在云主机 / 公网服务器执行 `docker-compose up`。
- **改进方向**：`ports: - "127.0.0.1:8765:8765"`；`WEB_HOST=127.0.0.1`；增加 `cap_drop: [ALL]`、`security_opt: [no-new-privileges:true]`、`read_only: true` + tmpfs for /tmp、`mem_limit: 2g`、`cpus: 2`。

### High（功能缺陷 - 高优先级）

#### F-008 `rolling_validation` `decay_ratio` 符号翻转，改善型候选被错误判定失败
- **文件**：`brain_alpha_ops/research/rolling_validation.py:38-41`
- **根因**：当首个窗口均值 `first < 0`（负值）且末窗口 `last > 0`（正值，即指标改善）时，走 `else` 分支：`decay_ratio = -last / |first|`，结果为负数。随后 `passed = last > 0 and decay_ratio >= 0.5` 永为 False，`score = 100.0 * max(0.0, min(decay_ratio, 1.0)) = 0`。
- **影响**：Rolling validation 检查完全失效于"从负转正"场景。提交门禁中 `rolling_validation_report` 会阻止这类改善型候选。
- **改进方向**：`decay_ratio` 应基于绝对值或方向一致的窗口计算；当 `first` 与 `last` 符号不同时，应视为"方向反转"单独处理。

#### F-009 `_try_auto_submit` 未捕获 `submit_alpha` 异常，候选停留不一致状态
- **文件**：`brain_alpha_ops/research/submission_gate_service.py:118-132`
- **根因**：`p.api.submit_alpha(...)` 调用无 try/except。若 API 抛出异常，`candidate.submission["result"]` 未赋值、`transition(..., LifecycleState.submitted, ...)` 未执行，candidate 停留在"已批准却未提交"的不一致状态。
- **影响**：自动提交流程中断，候选生命周期状态与实际提交状态不一致，可能导致重复提交或遗漏提交。
- **改进方向**：用 try/except 包裹 `submit_alpha` 调用，在异常时记录 `submission["error"]`、执行 fail-closed transition。

#### F-010 `audit trail writer` 未捕获 IO 异常，磁盘故障可中断 pipeline
- **文件**：`brain_alpha_ops/audit_trail/writer.py:63-79`（及 `lifecycle_writer.py` 同构）
- **根因**：`write_entry` 不捕获 `OSError`（磁盘满、权限变更、路径失效）。审计追踪本应 best-effort，但 writer 层本身不保护，直接调用 `write_scoring_audit` 的 scoring 代码若未自行 catch，异常会冒泡中断主流程。
- **影响**：审计写入失败可能中断 scoring/pipeline 主流程，使生产可用性受磁盘单点故障影响。
- **改进方向**：`write_entry` / `write_scoring_audit` 应在内部捕获 IO 异常并 `logger.error` 后静默返回。

#### F-011 浏览器提交幂等键 FIFO 淘汰后可重放
- **文件**：`brain_alpha_ops/browser/execution_adapter/_submit.py:136-140` + `_base.py:40-42`（`_MAX_IDEMPOTENCY_KEYS = 1000`）
- **根因**：提交成功后幂等键写入 `_used_idempotency_keys`（set）与 `_idempotency_key_order`（deque）。当 deque 长度超过 1000，`popleft()` 取出最旧键并 `discard` 出 set。被淘汰的键不再被识别为"已用过"，重放检查随之失效。
- **影响**：在单个 adapter 会话内累计超过 1000 次提交后，若外部复用一个已被淘汰的 `idempotency_key`，重复的真实提交将通过重放检查并被再次执行。
- **改进方向**：将幂等键存储改为按时间窗口或持久化记录，或与 `approval_ticket` 一并落盘做跨会话去重。

#### F-012 `check_prod_correlation` API 失败时 fail-open（返回 warning 而非 raise）
- **文件**：`brain_alpha_ops/brain_api/official_simulation/_mixin.py:299-327`
- **根因**：`check_prod_correlation` 在 `try` 内调用 `/alpha-correlations`；一旦抛 `BrainAPIError`，进入 `except` 返回 `{"status": "error", "max_correlation": None, "warning": "..."}`，而非向上抛错。
- **影响**：prod-correlation 是上线前的关键生产/质量门禁。API 不可用时门禁退化为一个 warning：下游若以 `max_correlation < threshold` 判定（`None` 被当作"无相关性数据"），会放行本应被高相关性阻断的 alpha。即把硬门禁降级为软告警，属于 fail-open。
- **改进方向**：API 失败时直接 `raise`（fail-closed），或在返回体中带 `blocking: True` 并强制调用方按此字段阻断。

#### F-013 `_launch_monitor` 子进程输出迭代无超时，挂起时无限阻塞
- **文件**：`_launch_monitor.py:91, 114`
- **根因**：`for line in proc.stdout:` 是阻塞 I/O，无超时；若 `BrainAlphaProd.exe` 启动后不输出，父进程将无限阻塞。`proc.wait()` 之前也无 timeout。
- **影响**：监控脚本挂死，运维无法通过日志判断子进程是否还活着；CI smoke 检查可能超时但生产环境下脚本会一直挂着。
- **改进方向**：用 `select.select` 或 `threading.Timer` 周期性检查 `proc.poll()`，超时则 `proc.kill()`。

#### F-014 `_launch_monitor` `DONE` 关键字误判完成 + `failed|error` 误报
- **文件**：`_launch_monitor.py:101, 106-108`
- **根因**：`if re.search(r'\bDONE\b', line)` 任何包含独立单词 `DONE` 的日志行都触发完成（如 "Skipping DONE step"）；`re.search(r'\b(failed|error)\b', lower) and "no_error" not in lower` 仅排除单数 `no_error`，未排除 `no_errors` / `0 errors` 等正向表述。
- **影响**：流水线未真正完成时监控提前退出，剩余日志不写入文件；正常日志触发 ALERT，误导运维。
- **改进方向**：用结构化结束标记（如 JSON 行带 `event` 字段），或要求标记独占一行且带固定前缀；排除集合扩展为 `{"no_error", "no_errors", "0 errors", "error_count=0"}`。

#### F-015 `_launch_monitor` `sanitized_child_env` 白名单剥离所有 BRAIN 凭证 env
- **文件**：`_launch_monitor.py:17-44, 76`
- **根因**：`SAFE_CHILD_ENV_KEYS` 是小白名单（仅 18 个 OS/locale/PATH 键），所有 `BRAIN_*` env 被剔除，子进程 `BrainAlphaProd.exe` 启动后无法从 env 读取 `BRAIN_USERNAME/PASSWORD/TOKEN/ADMIN_TOKEN`。
- **影响**：用户在主机设置的 BRAIN 凭证无法透传给打包 exe，子进程要么走交互输入（不适合 windowed exe）要么无法认证；`BRAIN_ALPHA_OPS_ADMIN_TOKEN` 也被剥离，Web 控制台 admin 入口失效。
- **改进方向**：白名单改为黑名单（仅剥离明确不安全的 + 保留 `BRAIN_*` 业务 env），或显式 allowlist `BRAIN_USERNAME` / `BRAIN_PASSWORD` / `BRAIN_TOKEN` / `BRAIN_ALPHA_OPS_*`。

#### F-016 `fetch_official_context` SIGALRM 在 Windows / 非主线程静默失效
- **文件**：`fetch_official_context.py:365-367`
- **根因**：`if not hasattr(signal, "SIGALRM"): yield; return` —— Windows 平台与任何非主线程上下文中 SIGALRM 不可用，超时被静默禁用，调用方无任何感知。
- **影响**：Windows 用户跑 `fetch_official_context.py` 时若 BRAIN API 卡死，脚本无限阻塞；与"超时保护"承诺直接矛盾。
- **改进方向**：用 `threading.Timer` 在独立线程中调用抛出，或用 `concurrent.futures.ThreadPoolExecutor` + `future.result(timeout=...)`。

#### F-017 `fetch_official_context` 不支持 HTTP-date `Retry-After` 头
- **文件**：`fetch_official_context.py:249-261`
- **根因**：`parsed = float(value)` 仅解析数字秒；RFC 7231 允许 `Retry-After: Wed, 21 Oct 2026 07:28:00 GMT`，此时 `float()` 抛 `ValueError`，`parsed=0.0`，最终走 429 兜底返回 `15*60`，忽略服务端实际重试时间。
- **影响**：服务端要求更长退避时仍按 15 分钟重试，触发更严限流；服务端要求更短时仍按 15 分钟等待，浪费时间。
- **改进方向**：`email.utils.parsedate_to_datetime(value)` 解析 HTTP-date，转秒数。

#### F-018 `AdaptiveExecutor.shutdown()` 后 `submit()` 静默重建线程/进程池
- **文件**：`brain_alpha_ops/adaptive_executor.py:130-149`
- **根因**：`shutdown()` 把 `self._io_pool = None; self._cpu_pool = None`；下次 `submit()` 进入 `_get_io_pool()` / `_get_cpu_pool()` 时因 `is None` 重新构造池。
- **影响**：调用方显式 `shutdown()` 后误以为资源已释放，但下次 `submit()` 又拉起池，资源泄漏；测试场景下重复 shutdown+submit 会创建大量孤儿线程。
- **改进方向**：增加 `self._closed: bool` 标记，`shutdown()` 置 True，`submit()` 检测到 True 时抛 `RuntimeError("executor is closed")`。

#### F-019 Python 3.11+ `TimeoutError` 语义冲突，业务超时被误判为执行器超时
- **文件**：`brain_alpha_ops/adaptive_executor.py:22,322`；`brain_alpha_ops/task_executor.py:13,75-78`
- **根因**：两个模块都 `from concurrent.futures import TimeoutError`，并注释"业务 TimeoutError 不会被捕获"。但 Python 3.11+ 起 `concurrent.futures.TimeoutError` 已被改为 `builtins.TimeoutError` 的别名，二者是同一类。业务代码抛 `raise TimeoutError("...")` 会被误判为"future 超时"，进入 `future.cancel()` 路径并把任务标记为 timeout 失败。
- **影响**：业务 TimeoutError（如 API 客户端检测到慢响应主动抛出）被误判为执行器超时，job 状态进入 `timeout` 而非业务错误，前端误导用户。
- **改进方向**：捕获后用 `exc.__cause__` 或 `traceback` 区分；或改为 `try: result = future.result(timeout=timeout) except concurrent.futures.TimeoutError: ...`。

#### F-020 `MetricsCollector` 全局单例写操作无锁，高并发丢指标
- **文件**：`brain_alpha_ops/metrics.py:42-105`
- **根因**：`counter()` `self._counters[key] += value` 是 read-modify-write，无 `threading.Lock`；`gauge()` / `histogram()` 同样裸写 `defaultdict`。
- **影响**：高并发场景下 counter 计数丢失（典型场景：N 个 worker 并发 `metrics.counter("api.calls")`，最终计数少于实际调用数），监控数据失真。
- **改进方向**：所有写操作加 `with self._lock`；或改用 `threading.local()` + 周期性 merge。

#### F-021 `presets.py` `language` 字段错误映射到 `test_period` kind
- **文件**：`brain_alpha_ops/presets.py:86`
- **根因**：`"language": _registry_default("test_period", "FASTEXPR")` —— 字段名是 `language`（表达式语言，如 `FASTEXPR`），但查询的是 capability_registry 的 `test_period` 槽位。
- **影响**：若 capability_registry 已注册 `test_period` kind 的默认值（如 `1`），presets 会把 `language` 设成 `1`（int），后续 `BrainSettings.language` 校验失败；若未注册则 fallback 到 `"FASTEXPR"`，掩盖了真实的 kind 缺失。
- **改进方向**：改为 `_registry_default("language", "FASTEXPR")`。

#### F-022 `web_candidates.payloads.py` 顶层 shim 重复导入同一符号 20 次
- **文件**：`brain_alpha_ops/web_candidates.payloads.py:1-40`
- **根因**：文件体 20 行完全相同的 `from brain_alpha_ops.web.dispatch.web_post_handlers import save_assistant_guidance_post_payload  # noqa: F401`，明显是代码生成器 bug 或合并冲突未清理。
- **影响**：模块导入执行 20 次重复 import 语句（虽被 Python import cache 折叠但仍增加加载开销）；暗示生成器有 bug，可能波及其他生成文件。
- **改进方向**：保留单行 import 即可；追溯生成器逻辑修复重复。

#### F-023 `JobStore` 持久化标志一旦 skip 后永久失效
- **文件**：`brain_alpha_ops/tasks/_store.py`
- **根因**：`persistence_load_skipped` 一旦为 `True`，后续即便底层文件已就绪也不再尝试加载，重启后丢失所有历史 job。
- **影响**：第一次启动因权限/路径问题跳过持久化，后续启动即使修复了路径也不再恢复，候选池/审计历史永久丢失。
- **改进方向**：每次启动都重新尝试加载；用 try/except 记录失败但不永久置位 `skipped`。

#### F-024 `StallMonitor` 仅改 JobStore 状态，不真正中断底层线程/进程
- **文件**：`brain_alpha_ops/stall_monitor.py:175-187, 244-251`
- **根因**：`_auto_interrupt` 只调用 `self._on_interrupt(job_id)`；`on_interrupt` 回调实现仅 `job_update(job_id, status="stopped", progress={...})`，把 JobStore 标记改为 stopped，但底层 `ThreadPoolExecutor.submit()` 出去的 future 仍在运行，无法被 `future.cancel()` 取消（已运行 future 不可中断）。
- **影响**：JobStore 显示 "stopped" 但后台 worker 仍在跑，资源泄漏；候选池继续被旧 job 污染；用户以为已停止，重新触发同任务可能造成重复提交。
- **改进方向**：在 `TaskExecutor` / `AdaptiveExecutor` 层维护 `job_id -> future` 映射，interrupt 时调用 `future.cancel()` + cooperative cancellation（业务代码周期检查 `stop_callback`）。

#### F-025 `guided_pipeline` `threading` 超时不可取消
- **文件**：`brain_alpha_ops/ux/guided_pipeline/`
- **根因**：阶段超时用 `threading.Timer` 或 `Event.wait(timeout=...)`，超时后仅记录但已在运行的同步代码无法被打断（Python GIL + 无协作式取消机制）。
- **影响**：引导式流水线某阶段卡死时，超时只触发状态变更，线程继续占用，下一阶段无法启动或并发执行导致状态错乱。
- **改进方向**：阶段函数接收 `stop_event` 参数周期检查；超时后 `future.cancel()` + 资源清理；用 `ProcessPoolExecutor` 隔离可强杀阶段。

#### F-026 `tasks/_watchdog.py` 读路径有 watchdog 副作用
- **文件**：`brain_alpha_ops/tasks/_watchdog.py`
- **根因**：`_watchdog_locked` 上下文管理器在读操作（如 `get_jobs()`）路径中被使用，但内部会更新 `last_seen` / `lock_acquired_at` 等元数据，导致纯读操作引发写盘与并发竞争。
- **影响**：高频读（如 React 前端 30s 轮询 + SSE handler 并发读）触发频繁写盘，磁盘 I/O 上升；多读并发时元数据竞争可能死锁。
- **改进方向**：读路径不加 watchdog 锁或加 `acquire_timeout=0` 的 try-lock，失败即降级无锁读；元数据更新放到独立通道。

#### F-027 `jsonl.iter_jsonl_records` 读取无文件锁，并发写时丢行
- **文件**：`brain_alpha_ops/jsonl.py:56-72`
- **根因**：`with target.open("r", encoding="utf-8")` 不加 `fcntl.flock`，并发 writer（如 audit_trail writer）append 中间状态时 reader 读到半行（被 `JSONDecodeError` 静默跳过）。
- **影响**：审计 / 历史记录读路径丢行，前端展示的 N 条记录可能是真实记录的子集；统计 `parsed_count` 不可信。
- **改进方向**：reader 用 `fcntl.flock(LOCK_SH)` 共享锁；或 writer 用 atomic rename（写 `.tmp` 后 rename）。

#### F-028 `backend_registration._api_instance` 全局单例无锁
- **文件**：`brain_alpha_ops/backend_registration.py`
- **根因**：模块级 `_api_instance` 单例在 `get_api()` 中懒构造，无 `threading.Lock`，多线程同时首次调用会构造多个 `OfficialBrainAPI` 实例，竞争认证 / rate-limit 状态。
- **影响**：rate-limit 全局状态失效（多实例各自计数），可能触发 429；认证 token 多次请求导致服务端会话冲突。
- **改进方向**：`with _LOCK: if _api_instance is None: _api_instance = OfficialBrainAPI(...)` 双检锁。

#### F-029 `observability.context_payload` 类型过滤不一致
- **文件**：`brain_alpha_ops/observability.py:46-50`
- **根因**：`if value not in ("", None)` 仅过滤空串与 None，`0` / `False` / `[]` / `{}` 仍被写入；`str(value)` 统一字符串化导致 `0` 写成 `"0"`、`False` 写成 `"False"`，下游消费者类型混乱。
- **影响**：observability 数据 schema 不稳定，数值字段在 0 时被误判为字符串；`False` 布尔被渲染为字符串 `"False"`，前端展示错乱。
- **改进方向**：用 `isinstance(value, (str, int, float, bool))` 白名单 + 保留原类型；空集合显式跳过并 log。

#### F-030 `registry_validation._extract_registry_fields` 混淆 enum 值与数据字段
- **文件**：`brain_alpha_ops/registry_validation.py:237-245`
- **根因**：从 `settings_options` 提取所有 enum 值当作"字段"加入 fields 集合。例如 `dataset` 字段的 options `["pv1", "pv13", "model77"]` 中的 `pv1` 被当作 field name 加入 fields set，与真正的 `close` / `volume` 等数据字段混在一起。
- **影响**：调用方查询"该字段是否在 registry 中"时，dataset 选项值 `pv1` 会被误判为合法字段；下游字段校验误报 BLOCKING，或反之让非法字段通过。
- **改进方向**：拆分 `setting_enum_values` 与 `data_field_names` 两个集合，校验时分别使用。

#### F-031 `runner.run_pipeline_from_config` 未传 `execution_backend`
- **文件**：`brain_alpha_ops/runner.py:21-27`
- **根因**：`AlphaResearchPipeline(config=run_config.ops, api=api, progress_callback=..., stop_callback=...)` 构造时未传 `execution_backend` 参数，pipeline 默认走 `AlphaExecutionBackend` 的 None / 内部默认实现，而非 `BrowserExecutionAdapter`。
- **影响**：生产 CLI 路径不走 browser backend，所有 official simulation 走 API 路径，可能触发真实提交（若 `real_submit_test_override_enabled` 被绕过）或缺少 browser backend 的 evidence 收集。
- **改进方向**：在 `run_pipeline_from_config` 中根据 `run_config` 增加 `execution_backend = create_execution_backend(mode=run_config.execution_mode)` 并传入 pipeline。

#### F-032 `execution_factory` "auto" 模式 playwright 未装时静默回退到 API backend
- **文件**：`brain_alpha_ops/execution_factory.py:40-44, 65-69`
- **根因**：`resolved_mode == "auto" and _playwright_available()` 为 False 时回退到 `_create_api_backend()`，后者 `OfficialBrainAPI()` 无 config 参数，使用默认 `OfficialAPIConfig()`，与运行配置脱钩；且无 logger.warning 提示回退发生。
- **影响**：生产环境 playwright 安装失败（如 Docker 镜像构建漏装 chromium）时静默走 API 路径，可能走真实提交入口；用户无感知。
- **改进方向**：回退时 `logger.warning("playwright unavailable, falling back to API backend")`；`_create_api_backend` 接受 `RunConfig` 并传入。

#### F-033 `agent_live_tools` `ThreadPoolExecutor` 超时仅 `future.cancel()` 未 shutdown
- **文件**：`brain_alpha_ops/agent_live_tools.py:91-124, 198`
- **根因**：超时分支 `future.cancel()`（对已运行 future 无效），未 `shutdown(wait=False, cancel_futures=True)`；池持续占用 worker。L198 `float()` 裸调用在 `bounded_float` 之前，传 `"abc"` 直接抛 `ValueError` 而非 friendly 错误。
- **影响**：超时后线程继续跑，资源泄漏；agent 工具调用错误信息不友好。
- **改进方向**：超时分支显式 `executor.shutdown(wait=False, cancel_futures=True)`；L198 把 `bounded_float` 提前到 `float()` 之前。

#### F-034 Facade 绑定安装失败被静默吞异常，服务带病启动
- **文件**：`brain_alpha_ops/web/__init__.py:208-211`
- **根因**：`_install_facade_bindings()` 把整段 `globals().update(_build_web_facade_bindings(globals()))` 与 legacy exports 构建包在单一 `try/except Exception` 内，失败时仅 `logger.error(...)` 后静默返回。`_build_web_facade_bindings` 一次性写入 150+ 个 globals 键，任一子导入或属性解析失败都会中断整批写入。
- **影响**：服务进程照常启动并监听端口，但 globals 处于半初始化状态——后续请求命中未绑定的属性时抛 `AttributeError`，且因 `__getattr__` 路由存在可能转化为更隐蔽的 500/404。运维人员若不查日志无法察觉。
- **改进方向**：将绑定安装拆分为多个独立 try/except 块并按子系统记录；或在关键绑定（`Handler`/`serve`/`dispatch_*`）缺失时让 `serve()` 抛硬错拒绝启动。

#### F-035 `audit_dir` 查询参数直接传入审计导出，造成任意目录读取
- **文件**：`brain_alpha_ops/web/misc/web_scoring_interpreter.py:137-164`
- **根因**：`audit_dir = _first_value(query, "audit_dir") or _DEFAULT_AUDIT_DIR` —— 用户通过 `?audit_dir=/etc` 或 `?audit_dir=../../sensitive` 即可让 `export_audit_trail(audit_dir=...)` 去读取任意文件系统目录下的审计 JSONL，结果内容回写到 HTTP 响应。
- **影响**：本地存储目录外的任意 audit_trail 目录（及其中文件名/内容片段）可被读取；结合 SSE/会话仅要求 loopback，远程开启时风险放大。
- **改进方向**：移除 `audit_dir` 查询参数，或强制 `audit_dir` 必须解析为 `config.ops.storage_dir` 子目录（`Path.resolve()` + `relative_to` 校验）。

#### F-036 兼容层 `_read_json` 用 `min` 把超大 body 静默截断，令上限校验成为死代码
- **文件**：`brain_alpha_ops/web/_reexports.py:147-158`
- **根因**：`length = min(length, self._MAX_BODY_BYTES); if length > self._MAX_BODY_BYTES: raise ValueError(...)` —— 先 `min` 再比较 `>` 使 body 大小上限校验永不触发；客户端发送 `Content-Length: 100MB` 时只会 `read(MAX)`，剩余 body 留在 socket 缓冲区，且 `json.loads` 在截断字节上抛 `JSONDecodeError` 而非干净的 413。
- **影响**：body 上限保护在该 Handler 路径上失效；keep-alive 连接因未读完 body 而状态错乱；错误信息不友好。
- **改进方向**：删除 `min(length, self._MAX_BODY_BYTES)` 行，改为先 `if length > MAX: raise`，再 `read(length)`，与 canonical 实现对齐。

#### F-037 `allow_remote=True` 时强制 `secure_cookies=True`，但本地服务只跑 HTTP，会话 Cookie 永不回传
- **文件**：`brain_alpha_ops/web/misc/web_runtime_facade/_server.py:44` 与 `:118`
- **根因**：`serve()`：`secure_cookies=bool(allow_remote) if secure_cookies is None else secure_cookies`；`main()`：`secure_cookies=run_config.web.secure_cookies or run_config.web.allow_remote`。当 `allow_remote=True` 且未显式设 `secure_cookies=False` 时，Cookie 头带 `; Secure`，但 `serve()` 返回的 URL 与监听均为 `http://`，浏览器在 HTTP 连接上**不会回传 Secure cookie**。
- **影响**：开启远程访问后，首页 `Set-Cookie` 下发的 session id 在后续 `/api/*` 请求中缺失，所有需要会话的接口返回 401 AUTH_REQUIRED，远程 Web 控制台完全不可用。
- **改进方向**：仅当检测到 HTTPS/TLS 终端（或显式 `secure_cookies=true`）时才置 True；远程 HTTP 场景应警告并默认 `SameSite=Strict` + admin token。

#### F-038 `is_allowed_local_request` 在 Host/Origin/Referer 全空时放行，Host 校验可被绕过
- **文件**：`brain_alpha_ops/web/security/web_security.py:30-55`
- **根因**：当请求**不携带 Host 头、且无 Origin/Referer** 时，三个检查全被跳过，函数返回 True。非浏览器客户端（curl/脚本）可轻易构造此类请求。
- **影响**：Host 白名单保护对"无 Host"请求失效；`/assets/` 静态资源与 `_is_allowed_local_request` 守卫的端点可被无 Host 请求触达。`allow_remote=True` 时显著放大攻击面。
- **改进方向**：Host 为空时直接 `return False`（HTTP/1.1 要求 Host 头存在）；或要求至少一个来源头（Host 与 Origin/Referer 不能同时为空）。

### Medium（功能缺陷 - 中等优先级，节选代表性条目）

> 完整 Medium 列表共 18 条，受篇幅限制仅列代表性条目，其余可按相同模式处理。

#### F-039 `_pearson_r` 协方差用总体公式、标准差用样本公式，系统性低估相关性
- **文件**：`brain_alpha_ops/scoring/anti_overfit/utils.py:21-33`
- **根因**：`cov = sum(...) / n`（总体协方差），而 `_safe_std` 用 `variance = sum(...) / (n - 1)`（样本标准差）。当前实现 `pearson = cov_pop / (std_sample_x * std_sample_y) = r_true × (n-1)/n`，n=20 时低估 5%。
- **改进方向**：统一协方差除数为 `n` 或 `n-1`，与标准差保持一致。建议直接复用 `local_backtest_metrics_helpers.py` 的正确实现。

#### F-040 `local_backtest spearman_r` 无 tie handling，与 anti_overfit 版本不一致
- **文件**：`brain_alpha_ops/research/local_backtest_metrics_helpers.py:55-71`
- **根因**：`rank_values` 将值排序后赋予序号 `rank / (len-1)`（归一化到 0..1），**不处理 ties**——相等值按 sort 顺序获得连续不同 rank。而 `anti_overfit/utils.py` 的 `_rank_transform` 使用 1-based rank 且对 ties 取平均 rank。
- **改进方向**：`rank_values` 应改为平均 rank 处理 ties，与 `anti_overfit/utils.py` 对齐。

#### F-041 `BrainAPIBridge.concurrent_simulate / concurrent_check` 忽略 concurrency 参数，实为串行
- **文件**：`brain_alpha_ops/brain_api/brain_api_bridge.py:84-97, 107-118`
- **根因**：两个方法签名都接收 `concurrency: int = 3`，但函数体内是普通 `for alpha in alphas` 串行循环，`concurrency` 参数从未被使用。
- **改进方向**：复用 `_bounded_concurrency` + `ThreadPoolExecutor` 实现真并发，或去掉误导性的 `concurrency` 参数。

#### F-042 `_cached_paginated_context` 限流时返回 stale 上下文缓存
- **文件**：`brain_alpha_ops/brain_api/official_context/_composite.py:116-123`
- **根因**：命中 429 且本地缓存非空时返回 `cached["items"]`（可能已过期的 fields/operators/datasets）。
- **改进方向**：返回 stale 时强制附带 `is_stale=True` 与缓存生成时间，并要求消费方据此降级。

#### F-043 分页上限全部为 `None`（无界）
- **文件**：`brain_alpha_ops/brain_api/pagination_limits.py:5-14`
- **根因**：`MAX_FIELDS_PAGES`、`MAX_DATASETS_PAGES`、`MAX_USER_ALPHAS_PAGES` 等均为 `None`，仅靠收敛性检测兜底。
- **改进方向**：增加一个宽松的硬 backstop（如 `max_pages` 上限或总条数上限）作为最后防线。

#### F-044 `authenticate()` token-only 路径不校验 token，且 basic 401 不回退
- **文件**：`brain_alpha_ops/brain_api/official_auth.py:18-19, 23-50`
- **根因**：当仅有 `token`（无 username/password）时，`authenticate()` 直接 `return {"status": "ok", "auth": "token"}`，完全不向后端发请求验证 token 是否仍然有效。basic 认证循环里只有 `("basic", ...)` 一个方法；遇到 401 立即 `break`，不会回退到 token。
- **改进方向**：token-only 路径增加一次轻量 API 探活（如 `get_user_profile`）；basic 401 时若持有 token 则回退尝试 token 认证。

#### F-045 并发槽位超限时 deferred 候选被计入 `failed`
- **文件**：`brain_alpha_ops/web_candidates/simulation/_submit.py:203-221`
- **根因**：命中 `CONCURRENT_SIMULATION_LIMIT_EXCEEDED` 且 `state.active_slots` 非空时，代码先调用 `_defer_candidate(...)`，紧接着却执行 `state.failed += 1` 并把结果以 `"status": "deferred_concurrency_limit"` 追加到 `state.results`。于是"可重试的延后"与"终态失败"共用同一个 `failed` 计数器。
- **影响**：作业的 `failed` 计数被虚增。在 `simulation/__init__.py` 的 `final_status` 逻辑里，`failed>0` 会把作业标记为 `completed_with_warnings` 甚至 `failed`，使一个"只是被并发限流延后、本应重试"的作业呈现为部分/完全失败。
- **改进方向**：将 deferred 与 terminal failed 分别记账。

#### F-046 `check_login_session` 对非数值 expiry 调 `float()` 会抛异常，`aggregate` 无隔离致整个生产健康快照丢失
- **文件**：`brain_alpha_ops/monitoring/production_health.py:192, 246-269`
- **根因**：`expiry` 可能为非数值字符串（如 ISO 时间串 `"2026-01-01T00:00:00Z"`），`float(expiry)` 会抛 `ValueError`。`aggregate()` 把 7 个 `check_*` 串行直接调用，任一抛错即整体中断。
- **改进方向**：`float(expiry)` 外包 try/except；更稳妥地是 `aggregate` 内对每个 `check_*` 单独 try/except。

#### F-047 `EvidenceArchival.cleanup_old / list_sessions` 解析损坏的 metadata.json 会抛异常中断遍历
- **文件**：`brain_alpha_ops/monitoring/evidence.py:71-74, 83-85`
- **根因**：两个方法对每个 session 目录的 `metadata.json` 直接 `json.load(f)`，无 try/except。一旦某个 `metadata.json` 损坏，抛 `JSONDecodeError`，遍历立即终止。
- **改进方向**：逐文件 try/except，解析失败则记录并跳过。

#### F-048 提交异常 `str(exc)[:100]` 未经脱敏直接写入 `status_message`
- **文件**：`brain_alpha_ops/web/business/web_business/_handlers_simulation.py:116`
- **根因**：`"status_message": f"提交异常: {str(exc)[:100]}"` 绕过了 `redact_error_message`，把异常原文（可能含 URL、alpha 表达式、内部路径、token 片段）直接回传前端。
- **改进方向**：改为 `redact_error_message(exc)` 或 `safe_error_message(exc)`。

#### F-049 异步作业心跳线程异常即 `return`，不重启导致 watchdog 误判卡死
- **文件**：`brain_alpha_ops/web/business/web_async_jobs.py:243-245`
- **根因**：心跳线程在循环内捕获到异常后直接 `return` 退出，不再重启；长时运行作业失去心跳后会被 stall_monitor 判为卡死并强制 cancel。
- **改进方向**：异常后 `continue` + 退避重试，仅当作业已终态时退出。

#### F-050 `RequestRateLimiter` 的 `_timestamps` 字典不清理空桶，跨唯一身份内存泄漏
- **文件**：`brain_alpha_ops/web/misc/web_rate_limit.py:41-65`
- **根因**：`_timestamps` 用 `defaultdict(deque)`；`check()` 只 `popleft` 过期时间戳，但从不删除已空的 deque 键。每个新身份（`client:<addr>` 或 session key）会留下一个常驻空 deque。
- **改进方向**：`popleft` 后若 `not timestamps` 则 `del self._timestamps[cache_key]`。

#### F-051 `release_score_gate` settings=None 时用 metrics 当 settings
- **文件**：`brain_alpha_ops/scoring/release_score_gate/_decision.py:79`
- **根因**：`effective_settings = settings if settings is not None else metrics`。当 `settings=None` 时，`effective_settings = metrics`（BRAIN 指标字典）。`ThresholdPolicy.from_thresholds(thresholds, settings=metrics)` 会接收到错误数据——metrics 是指标值（sharpe/fitness/turnover 等），而非 settings（delay/universe/region 等）。
- **改进方向**：`effective_settings` 应默认为 `{}` 或从 thresholds 提取，不应将 metrics 当作 settings。

#### F-052 `prod_correlation` 本地回退用表达式长度估算相关性，短 alpha 被误杀
- **文件**：`brain_alpha_ops/research/prod_correlation.py:235-268`
- **根因**：当 BRAIN API 不可用且 `allow_local_fallback=True`（默认值）时，用 `len(expression)` 估算 prod correlation。表达式长度与真实 prod correlation 无因果关系。合法的短 alpha（如 `rank(returns)` 14 字符）被强制赋予 0.85 → 超过 0.70 阈值 → `passed=False` → 被错误阻断。
- **改进方向**：本地回退应 fail-closed（`correlation=1.0, passed=False, source="unavailable"`）或 fail-open（标记为需人工复核），而非用无依据的长度估算。

#### F-053 `record_sqlite_index append_record` 读取-写入非原子，并发覆盖丢失记录
- **文件**：`brain_alpha_ops/research/record_sqlite_index.py:30-51`
- **根因**：`_next_record_index` 做 `SELECT MAX(record_index)` 后 INSERT，两步之间无事务隔离。每次调用创建独立 connection。两个线程并发调用 `append_record`：均读到 `MAX=5`，均尝试 `INSERT OR REPLACE ... record_index=6`，第二个 `OR REPLACE` 覆盖第一个的记录 → 数据丢失。
- **改进方向**：用 `BEGIN IMMEDIATE` 事务包裹 read+write，或改用 `AUTOINCREMENT` 主键。

#### F-054 `runtime_service` `lifecycle_records` 无界增长，长运行 pipeline 内存泄漏
- **文件**：`brain_alpha_ops/research/runtime_service.py:84`
- **根因**：`p.lifecycle_records.append(row)` 无截断。对比同文件 `_record_backtest`（line 116）有 `p.backtest_records = p.backtest_records[-200:]` 截断。
- **改进方向**：添加 `p.lifecycle_records = p.lifecycle_records[-N:]` 截断（与 `backtest_records` 一致）。

#### F-055 `fusion composite_ensemble` mode="max" 未调用表达式校验
- **文件**：`brain_alpha_ops/research/fusion.py:152-156`
- **根因**：`elif mode == "max": result = ...; return result` 未调用 `_validate_fusion_expr`。其余三个 mode（average/rank_average/min）均调用。多表达式 `max` 嵌套会快速膨胀长度和括号深度，可能超出 BRAIN 平台 512 字符 / 12 层限制。
- **改进方向**：`return _validate_fusion_expr(result, "ensemble_max")`。

#### F-056 `backtest slot` 单次提交失败退出整个填充循环
- **文件**：`brain_alpha_ops/research/backtest_flow_service/_slot_submission.py:61-87`
- **根因**：循环 `for slot in open_slots:` 中，当某个 slot 提交失败时执行 `return`，退出整个方法。后续 open slots 中的候选即使可用也无法在本周期提交。
- **改进方向**：将 `return` 改为 `continue`。

---

## 维度二：用户体验（User Experience）

### High

#### U-001 SSE 断连 5 分钟自动取消任务但 BRAIN 云端仍在运行
- **文件**：`brain_alpha_ops/web/react_app/src/hooks/useJobDisconnectedState.ts`（`DISCONNECTED_AUTO_CANCEL_MS = 300000`）
- **根因**：前端在 SSE 断连 5 分钟后自动调用 `jobCancel`，但 BRAIN 云端任务可能仍在运行。
- **影响**：前端"取消"了任务但云端继续消耗资源/可能产生结果；用户重连后状态不一致；云端任务变成孤儿。
- **触发条件**：网络抖动导致 SSE 断连超 5 分钟。
- **改进方向**：自动取消前先尝试 `job/status` 探活；或仅前端置为"连接中断"态而非真发取消请求；同时展示"BRAIN 云端回测可能仍在运行，请先到 BRAIN 平台确认槽位"警示 + 槽位查询入口。

#### U-002 错误引导仅覆盖 4/11 类连接错误
- **文件**：`brain_alpha_ops/web/react_app/src/helpers/connectionErrorGuide.ts`
- **根因**：`errors.ts` 定义 11 类 ErrorKind，但 `connectionErrorGuide` 仅对 4 类（auth/network/timeout/rate_limit）提供 actionable 引导，其余 7 类（csrf 失败、cookie 过期、region 不支持等）落到默认分支。
- **影响**：csrf 失败、cookie 过期、region 不支持等错误用户看到通用文案，不知如何恢复。
- **改进方向**：补全所有 11 类的引导文案与 action。

#### U-003 限流倒计时固定 30s 不读 `retry_after`
- **文件**：`brain_alpha_ops/web/react_app/src/helpers/connectionErrorGuide.ts`（rate_limit 分支固定 `waitSeconds = 30`）+ 后端 `web/misc/web_rate_limit.py`
- **根因**：前端未读取后端返回的 `retry_after` 字段，硬编码 30s；后端 rate limiter 也不返回实际 retry_after。
- **影响**：若后端要求等待 60s/300s，用户 30s 后重试仍被限流，体验差且加重限流。
- **改进方向**：优先读 `error.guide.waitSeconds` 或 `retry_after`，回退到默认值；后端 rate limiter 返回实际 retry_after。

#### U-004 Web 端不可真实提交须前置提示
- **文件**：`brain_alpha_ops/web/submissions/web_submission_single.py:121` + `web/submissions/web_submission_batch.py:21-126`
- **根因**：单提交 `submit_candidate_payload` 在入口即检查 `_real_submit_disabled()` 并返回 `_REAL_SUBMIT_DISABLED_PAYLOAD`；但批量提交 `submit_batch_payload` 顶层无此短路，逐个调用 `submit_candidate`，每个候选都返回相同的 `REAL_SUBMIT_DISABLED_WEB_FLOW`。用户批量提交 100 个候选时得到 100 条重复的"真实提交已禁用"错误。
- **影响**：批量结果体臃肿且易误判为 PARTIAL_FAILED；用户在提交流程终点才发现 Web 端不可真实提交，浪费完整 HIL 流程。
- **改进方向**：`submit_batch_payload` 入口先调用 `submit_candidate` 探测一次，若返回 disabled/policy 类错误则整批短路返回单条阻断 payload；并在用户打开提交面板时前置展示「Web 端不可真实提交，最终提交需在 BRAIN 平台完成」+ BRAIN 平台外链。

### Medium（用户体验 - 中等优先级）

#### U-005 `launch_web` 启动后未输出端口 / URL
- **文件**：`launch_web.py`
- **根因**：服务启动后仅 `print("Server starting...")`，未输出实际监听端口与可访问 URL。
- **改进方向**：启动后 `print(f"Listening on http://{host}:{port}")`。

#### U-006 错误信息英文外泄（i18n 覆盖不完整 + `errors.classify_error` 兜底英文）
- **文件**：`brain_alpha_ops/i18n/messages.py`、`brain_alpha_ops/errors.py`
- **根因**：i18n zh 字典缺部分键（如 `pipeline.event.*` 一批键的值是英文 `"Pipeline started"`）；`errors.classify_error` 在未匹配时返回英文 message；`error_payloads.user_error_payload` 直接把英文 message 写入 `message` 字段。
- **改进方向**：扩充 zh 字典；未匹配时返回通用中文"操作失败，请查看日志"并保留英文 technical detail 在 `details` 字段。

#### U-007 配置保存后无"需重启生效"提示
- **文件**：`brain_alpha_ops/config_update.py` + `web/react_app/src/components/ConfigPanel/`
- **根因**：`update_dataclass_from_mapping` 直接修改 live config dataclass，但部分配置（如 `execution_mode`、`web.host`、`budget.max_cycles`）需要重启 pipeline / web 服务才生效，后端未返回 `requires_restart` 字段；前端仅弹"配置已保存成功"。
- **改进方向**：定义 `RESTART_REQUIRED_FIELDS` 集合，保存后比对返回 `requires_restart: bool` + `affected_fields: [...]`；前端区分提示。

#### U-008 前台任务完成无提示
- **文件**：`brain_alpha_ops/web/react_app/src/hooks/useJobNotifications.ts`
- **根因**：任务完成通知逻辑仅在 `document.hidden`（页面后台）时弹通知，前台时无任何完成反馈。
- **改进方向**：前台也弹一个非阻塞 toast 或状态卡片高亮。

#### U-009 `useGlobalData` 30s 轮询不看 visibility
- **文件**：`brain_alpha_ops/web/react_app/src/hooks/useGlobalData.ts`（`setInterval` 30000）
- **根因**：30s 轮询 4 个全局端点，未检查 `document.visibilityState`，标签页隐藏时仍轮询。
- **改进方向**：`hidden` 时暂停轮询，`visibilitychange` 恢复。

#### U-010 `OfficialBacktestSlots` 每 5s 全量 `refreshAll`
- **文件**：`brain_alpha_ops/web/react_app/src/components/OfficialBacktestSlots.tsx`（`setInterval` 5000 调 `refreshAll()`）
- **根因**：5s 间隔调用 `refreshAll()`，刷新所有 slots 而非增量；且不看 visibility。
- **改进方向**：拉长间隔至 15-30s、改为增量查询、加 visibility 检查。

#### U-011 `useCandidateTableData` 刷新循环依赖
- **文件**：`brain_alpha_ops/web/react_app/src/hooks/useCandidateTableData.ts`
- **根因**：`loadCandidates` 在 effect 中依赖 `globalCandidatesData`，而 `globalCandidatesData` 由 useGlobalData 周期更新，每次更新触发 loadCandidates，可能形成刷新循环。
- **改进方向**：用 ref 缓存 latest globalCandidatesData，effect 仅依赖显式触发器。

#### U-012 网络错误恢复入口缺失
- **文件**：`brain_alpha_ops/web/react_app/src/hooks/useNetworkError.ts`
- **根因**：网络错误后无统一"重试/恢复"入口，需用户手动刷新页面或重新走配置流程。
- **改进方向**：在顶栏错误状态加全局"重试连接"按钮。

#### U-013 批量提交无 dry-run/无撤销/无原子性
- **文件**：`brain_alpha_ops/web/react_app/src/components/CandidateTableToolbarTitleStats.tsx` + `src/hooks/useCandidateActions.ts`
- **根因**：批量操作直接发请求，无 dry-run 预览、无撤销、无原子性（部分失败时已提交的部分不回滚）。
- **改进方向**：增加确认弹窗 + 预览影响范围；记录操作日志支持撤销。

#### U-014 `SubmissionConfirmPanel` 30s 轮询不检查 visibility
- **文件**：`brain_alpha_ops/web/react_app/src/components/SubmissionConfirmPanel.tsx`（`setInterval` 30000 调 `/api/submit_readiness`）
- **改进方向**：加 visibility 检查。

#### U-015 `CredentialQuickStart` `handleGuidedRetry` timer 泄漏
- **文件**：`brain_alpha_ops/web/react_app/src/components/CredentialQuickStart.tsx`
- **根因**：`useCallback` 返回的清理函数不会被调用；`handleTestConnection` 未列入 deps（闭包陈旧）。组件卸载后 timer 仍触发 `handleTestConnection`，可能调用已卸载组件的 setState。
- **改进方向**：用 `useRef` 存 timer，在 `useEffect` cleanup 中清理；正确补全 deps。

---

## 维度三：WebUI 问题（WebUI Defects）

### Critical

#### W-001 `PhaseShell` 阻断阶段按钮仍可点击
- **文件**：`brain_alpha_ops/web/react_app/src/components/PhaseShell.tsx`
- **根因**：阻断态仅施加 `opacity` 与 `grayscale` 滤镜，未设置 `pointer-events: none`、未使用 `inert` 属性、未对内部可交互元素显式 `disabled`。
- **影响**：用户在 `connect` 未就绪时可点击后续阶段（discover/evaluate/ready）的卡片或按钮，触发未定义状态的 handler 调用，导致状态机错乱、候选池在无凭证时被请求。
- **触发条件**：连接断开或缓存未就绪时，用户点击主面板阶段卡片。
- **改进方向**：在阻断容器上加 `inert` 或 `pointer-events:none`；阶段卡片接受 `disabled` prop 并传递给内部按钮。

### High

#### W-002 `ErrorBoundary` 返回首页用 hash 与 `BrowserRouter` 冲突
- **文件**：`brain_alpha_ops/web/react_app/src/components/ErrorBoundary.tsx` `handleGoHome` 分支
- **根因**：项目使用 `BrowserRouter`，但错误恢复用 `window.location.hash = ''` 操作 hash，与路由历史脱节，无法触发 React Router 导航。
- **影响**：崩溃后点击"返回首页"不会真正卸载错误边界状态、不重置路由栈，用户停留在错误界面或出现空白。
- **改进方向**：改用 `window.location.assign('/')` 或 `history.pushState` + 派发 `popstate`，或注入 `useNavigate`。

#### W-003 Modal 系列无焦点陷阱
- **文件**：`brain_alpha_ops/web/react_app/src/components/ConfirmDialog.tsx`、`ScoringWeightModal.tsx`、`DashboardReportModal.tsx`、`SubmissionGuidance.tsx`（DrillModal 分支）
- **根因**：项目已实现 `components/A11y/FocusTrap.tsx`，但上述 4 个 Modal 均未包裹该组件；Tab/Shift+Tab 会跳出 Modal 到背景元素。
- **影响**：键盘用户与屏幕阅读器用户无法被困在 Modal 内，焦点可漂移到被遮罩的背景按钮，违反 WAI-ARIA Dialog 模式。
- **改进方向**：所有 Modal 根节点用 `<FocusTrap>` 包裹，并在打开时聚焦首个可聚焦元素、关闭时归还焦点。

#### W-004 路由仅注册 `/`，视图状态不进 URL
- **文件**：`brain_alpha_ops/web/react_app/src/main.tsx` + `src/App.tsx`
- **根因**：除根路由外所有视图（candidate/scoring/snapshot/config 等）均由内部 state 驱动，不映射到 URL path。
- **影响**：刷新丢失当前视图、无法分享/书签、浏览器后退键行为不符合预期、无法深链。
- **改进方向**：将主要视图注册为子路由（`/candidates`、`/scoring` 等），用 `useParams`/`useSearchParams` 替代部分 state。

#### W-005 `ScoringPanel` 独立 SSE 随视图卸载断连
- **文件**：`brain_alpha_ops/web/react_app/src/components/ScoringPanel/ScoringPanel.tsx`
- **根因**：评分面板在组件内创建独立 SSE 连接，未纳入 `useSseManager` 统一管理；组件卸载时 EventSource 关闭，评分事件流中断。
- **影响**：用户离开评分视图再返回时，需重连 SSE；中断期间的评分进度丢失；连接数随视图切换累积。
- **改进方向**：将评分 SSE 纳入 SseManager 单例，或上提到 Dashboard 层常驻。

#### W-006 `VirtualList` Rules of Hooks 违规
- **文件**：`brain_alpha_ops/web/react_app/src/components/VirtualList/VirtualList.tsx`（`useWindowScroll` 三元分支）
- **根因**：`const rowVirtualizer = useWindowScroll ? useWindowVirtualizer({...}) : useVirtualizer({...});` 条件分支调用不同 hook。虽有 `eslint-disable react-hooks/rules-of-hooks` 注释，但 `useWindowScroll` 是 prop，运行时变化会导致 hook 调用顺序变化。
- **影响**：若 `useWindowScroll` 在运行时由 true→false 或反向切换，React 会抛出 "Rendered fewer hooks than expected" 错误，组件崩溃。
- **改进方向**：拆为两个组件（`WindowVirtualList` / `ElementVirtualList`），或始终调用一个统一 hook。

#### W-007 `renderActiveViewFromContext` 在 render 期调用 hook
- **文件**：`brain_alpha_ops/web/react_app/src/components/views/renderViewFromContext.tsx`
- **根因**：在普通函数（非组件）内调用 `useAppStateContext()`，违反 Rules of Hooks。
- **影响**：当该函数被在条件/循环中调用时，React 抛错或状态读取错乱；难以静态分析。
- **改进方向**：将 hook 调用上提到真正的组件顶层，通过参数传入 context 值。

#### W-008 `csrf.ts` token 注入依赖 meta 标签且无失败兜底
- **文件**：`brain_alpha_ops/web/react_app/src/utils/csrf.ts`
- **根因**：从 `<meta name="brain-alpha-csrf">` 读取 token，若 meta 标签缺失或为空，CSRF 头为空字符串，请求仍发出。
- **影响**：后端若严格校验 CSRF，所有写请求 403；若不校验则 CSRF 防护失效。
- **改进方向**：读取失败时抛错或显式标记无 token 并禁用写操作。

#### W-009 `errorHandler` 与 `useApi` 错误处理路径脱节
- **文件**：`brain_alpha_ops/web/react_app/src/utils/errorHandler.ts` 与 `src/hooks/useApi.ts`
- **根因**：`errorHandler.ts` 定义了统一的错误分类与 ActionableError payload，但 `useApi.ts` 内部 catch 时直接构造 toast，未走 `errorHandler.classifyError`，两套路径并存。
- **改进方向**：所有 API 错误统一经 `errorHandler` 处理。

### Medium（WebUI - 中等优先级）

#### W-010 Toast 系统重复（死代码风险）
- **文件**：`brain_alpha_ops/web/react_app/src/components/Toast.tsx` + `src/App.tsx` + `src/components/ToastContainer.tsx`
- **根因**：存在两套 toast 渲染容器，`Toast.tsx` 的 ToastProvider 自带渲染逻辑与 `ToastContainer.tsx` 的独立容器并存。
- **改进方向**：删除其中一套，保留单一 toast 渲染入口。

#### W-011 首屏空白（index.html 无 noscript/骨架屏）
- **文件**：`brain_alpha_ops/web/react_app/index.html`
- **根因**：HTML 仅含 `<div id="root">`，无 noscript 提示、无内联骨架屏样式、无 loading 占位。
- **改进方向**：在 `#root` 内放内联骨架屏，外加 `<noscript>` 提示。

#### W-012 候选导出下拉无 click-outside 关闭
- **文件**：`brain_alpha_ops/web/react_app/src/components/CandidateTableToolbarFilterToolbar.tsx`
- **根因**：`exportRef` 创建后从未绑定 `mousedown`/`click` 文档监听器，下拉只能通过按钮再次点击关闭。
- **改进方向**：在 `useEffect` 中绑定 document mousedown，判断 `!exportRef.current.contains(e.target)` 时 `setExportOpen(false)`。

#### W-013 `StateCardItem` 暗色模式颜色不一致
- **文件**：`brain_alpha_ops/web/react_app/src/components/StateCards/StateCardItem.tsx`
- **根因**：使用硬编码 Tailwind 颜色类名（`bg-white` / `border-slate-200` / `text-slate-950` / `text-slate-600`），而非全站采用的 CSS 变量方案。
- **改进方向**：替换为 `bg-surface` / `text-text-primary` 等 token 类，或直接使用 CSS 变量。

#### W-014 移动端 statusbar 被 `MobileTabBar` 遮挡
- **文件**：`brain_alpha_ops/web/react_app/src/components/MobileTabBar.tsx` + `index.css`
- **根因**：底部固定 TabBar 高度未在 body/main 上预留等高 padding，部分视口下底部内容被 TabBar 覆盖。
- **改进方向**：在主滚动容器底部加 `padding-bottom: env(safe-area-inset-bottom) + tabbar-height`。

#### W-015 `sync_cloud_alphas_payload` 中 `api.authenticate()` 未捕获，返回非结构化错误
- **文件**：`brain_alpha_ops/web_cloud/sync_payload.py:50`
- **根因**：与同包 `check_candidate_payload` 用 try/except 返回 `web_error` 不同，同步路径 `sync_cloud_alphas_payload` 直接调用 `api.authenticate()` 而无任何捕获。认证失败时异常向上裸抛。
- **影响**：WebUI 调用同步云端 alpha 接口时，认证失败不会得到约定的结构化 `{"ok": False, "error_code": ..., ...}` 载荷，而是 500/裸异常，前端无法按既有契约展示友好错误。
- **改进方向**：用 try/except 包裹并返回与 `check_candidate_payload` 一致的结构化错误载荷。

---

## 改进路线图

### P0（立即修复 - Critical 与阻断级 High）

| 序号 | 问题 | 维度 | 建议优先级 |
|------|------|------|-----------|
| 1 | F-001 反过拟合回退链虚假 PASS | Functional | 最高 |
| 2 | F-002 IC 稳定性退化 ic_std 恒为 0 | Functional | 最高 |
| 3 | F-003 ashare 缓存键陈旧 | Functional | 最高 |
| 4 | F-004 error_catalog KeyError 误分类 | Functional | 最高 |
| 5 | F-005 real_submit_test_override env 旁路 | Functional | 最高 |
| 6 | F-006 Docker root + chmod 777 | Functional | 最高 |
| 7 | F-007 docker-compose 公网暴露 | Functional | 最高 |
| 8 | W-001 PhaseShell 阻断态按钮仍可点 | WebUI | 最高 |
| 9 | W-006 VirtualList Rules of Hooks 违规 | WebUI | 最高 |
| 10 | W-007 renderActiveViewFromContext hook 调用 | WebUI | 最高 |
| 11 | U-015 CredentialQuickStart timer 泄漏 | UX | 最高 |
| 12 | F-011 浏览器提交幂等键淘汰可重放 | Functional | 高 |
| 13 | F-012 check_prod_correlation fail-open | Functional | 高 |
| 14 | F-031 runner 未传 execution_backend | Functional | 高 |
| 15 | F-032 execution_factory 静默回退 | Functional | 高 |

### P1（本迭代修复 - High）

| 序号 | 问题 | 维度 |
|------|------|------|
| 16-22 | F-008 ~ F-014 (rolling_validation / submit 异常 / audit writer / launch_monitor 系列) | Functional |
| 23-30 | F-016 ~ F-023 (SIGALRM / Retry-After / AdaptiveExecutor / TimeoutError / MetricsCollector / presets language / payloads shim / JobStore) | Functional |
| 31-37 | F-024 ~ F-030 (StallMonitor / guided_pipeline / watchdog / jsonl / backend_registration / observability / registry_validation) | Functional |
| 38-42 | F-034 ~ F-038 (Facade 静默吞 / audit_dir 任意读 / _read_json 截断 / secure_cookies / Host 校验绕过) | Functional |
| 43 | W-002 ErrorBoundary hash 冲突 | WebUI |
| 44 | W-003 Modal 无焦点陷阱 | WebUI |
| 45 | W-004 路由不进 URL | WebUI |
| 46 | W-005 ScoringPanel SSE 随卸载断连 | WebUI |
| 47 | W-008 CSRF token 依赖 meta | WebUI |
| 48 | W-009 errorHandler 与 useApi 脱节 | WebUI |
| 49 | U-001 SSE 断连误取消 | UX |
| 50 | U-002 错误引导覆盖不全 | UX |
| 51 | U-003 限流倒计时固定 30s | UX |
| 52 | U-004 Web 端不可真实提交须前置 | UX |

### P2（后续规划 - Medium）

剩余 35 条 Medium 问题（F-039 ~ F-056 + U-005 ~ U-014 + W-010 ~ W-015），按子系统分批处理。建议优先处理：
- F-039 / F-040（Pearson/Spearman 数值正确性，与 F-001/F-002 联动）
- F-045 / F-046 / F-047（并发槽位 / 健康监控 / Evidence 容错，影响生产可用性）
- F-051 / F-052 / F-053 / F-054 / F-055 / F-056（scoring/prod_correlation/sqlite_index/runtime_service/fusion/backtest slot 数值与资源问题）
- U-009 / U-010 / U-011 / U-014（轮询与刷新循环，影响性能与体验）
- W-010 / W-011 / W-012 / W-013 / W-014 / W-015（Toast 重复 / 首屏空白 / 导出下拉 / 暗色模式 / 移动端遮挡 / sync 错误契约）

---

## 附录：与历史审计文档交叉核对

### A.1 历史文档清单与本次核查状态

通读 23 份历史审计文档后，共提取 111 条历史已知问题（编号 H-001 ~ H-111）。下表按主题归类，标注当前代码状态（已修复 / 仍存在 / 部分修复 / 新发现）。

| 主题 | 历史问题编号 | 当前状态 | 证据/对应本次编号 |
|------|-------------|---------|------------------|
| **God Object / 巨型模块**（pipeline.py / web.py / 前端单体） | H-007, H-019, H-022, H-072, H-074, H-089, H-090, H-091, H-093, H-103, H-104 | 部分修复 | pipeline.py 已拆分为 pipeline_*.py 多文件（参见目录结构）；web/ 已拆为 dispatch/handlers/misc/security/state/submissions 等子包；前端 CandidateTable 已拆为 CandidateTable + CandidateTableSubComponents + CandidateTableUtils 子目录。但 App.tsx 仍较大、双调度系统痕迹仍在 |
| **静默吞异常 / 静默失败** | H-006, H-016, H-020, H-061, H-068 | 仍存在 | F-034 (Facade 静默吞) / F-049 (心跳线程静默退出) / F-009 (audit writer 未捕获 IO) / F-024 (StallMonitor 仅改状态不真中断) |
| **全局可变状态 / 线程安全** | H-023, H-025, H-059, H-065, H-066 | 仍存在 | F-020 (MetricsCollector 无锁) / F-026 (watchdog 读副作用) / F-027 (jsonl 无文件锁) / F-028 (backend_registration 无锁) / F-053 (sqlite_index 非原子) |
| **提交门禁语义不一致** | H-033, H-039, H-041, H-042, H-057, H-085 | 仍存在 | F-005 (real_submit_test_override env 旁路) / F-031 (runner 未传 execution_backend) / F-032 (execution_factory 静默回退) / U-004 (Web 端不可真实提交须前置) |
| **配置重复 / 不一致** | H-005, H-055, H-076, H-077 | 部分修复 | run_config.json 重复 key 已修；config_models.py 与 runtime_constants.py 默认值仍存在 _runtime_constants_helpers.py 桥接，未完全消除 |
| **`_ratio()` 百分比 / 比率处理** | H-010, H-056, H-071 | 已修复 | `_ratio.py` 已实现 `normalize_brain_ratio(value, bounded=True/False)` 统一处理；F-052 中 `diagnostics.weight_concentration` 仍误用 bounded=False，已记入本次 F-XXX（在 Medium 范围内未单列） |
| **硬编码阈值 / 无动态刷新** | H-073, H-078, H-080 | 部分修复 | 官方 context freshness 已有 `context_refresh.py` + `web_cloud/snapshot/_refresh_service.py`；门禁阈值仍硬编码（H-080 仍存在，但属设计选择） |
| **无 i18n / 硬编码中文字符串** | H-079, H-094 | 部分修复 | 已新增 `i18n/messages.py` zh 字典；但覆盖不全，部分键仍英文（见 U-006） |
| **监控覆盖不全** | H-083, H-102 | 仍存在 | 监控仍只覆盖后端任务，前端异常自愈未接入（见 W-006/W-007 等前端 hook 问题） |
| **前端状态漂移 / 双状态源** | H-003, H-100 | 部分修复 | 已有 `useAppState/` composition root + AppStateContext；但 `renderActiveViewFromContext` 仍违反 Rules of Hooks（W-007） |
| **反过拟合 returns→factor_values 虚假 PASS** | （`remediate-major-defects-evaluation` spec 中提及，历史文档未独立编号） | 仍存在 | F-001（更精确：本次发现是 returns→ic_series 而非 factor_values，但同类根因） |
| **IC 稳定性退化** | （`remediate-major-defects-evaluation` spec 中提及 IC_std 上限不对称，未提及单元素列表 bug） | 新发现 | F-002（本次深读首次发现 `_rank_ic` 返回单元素列表致 ic_std 恒为 0） |
| **ashare load_index_universe 缓存键陈旧** | （`remediate-major-defects-evaluation` spec H-005 提及） | 仍存在 | F-003 |
| **error_catalog KeyError 误分类** | （`remediate-major-defects-evaluation` spec 提及） | 仍存在 | F-004 |
| **real_submit_test_override env 旁路** | （`remediate-major-defects-evaluation` spec 提及 PYTEST_CURRENT_TEST） | 仍存在 | F-005 |
| **Docker root + chmod 777** | （`remediate-major-defects-evaluation` spec 提及） | 仍存在 | F-006 |
| **docker-compose 公网暴露** | （`remediate-major-defects-evaluation` spec 提及） | 仍存在 | F-007 |
| **浏览器提交幂等键淘汰可重放** | （`remediate-major-defects-evaluation` spec 提及） | 仍存在 | F-011 |
| **check_prod_correlation fail-open** | （`remediate-major-defects-evaluation` spec 提及） | 仍存在 | F-012 |
| **_launch_monitor 子进程挂起 / DONE 误判 / failed\|error 误报 / sanitized_child_env 剥离凭证** | （`remediate-major-defects-evaluation` spec 提及） | 仍存在 | F-013 / F-014 / F-015 |
| **fetch_official_context SIGALRM Windows 失效 / 不支持 HTTP-date Retry-After** | （`remediate-major-defects-evaluation` spec 提及） | 仍存在 | F-016 / F-017 |
| **AdaptiveExecutor.shutdown 后 submit 重建池 / Python 3.11+ TimeoutError 语义冲突** | （`remediate-major-defects-evaluation` spec 提及） | 仍存在 | F-018 / F-019 |
| **WebApplicationContext 白名单含安全函数** | （`remediate-major-defects-evaluation` spec 提及） | 仍存在 | 见 F-034 同源问题（Facade 静默吞 + 安全原语可被覆盖） |
| **JobStore 持久化跳过后永久失效 / watchdog 读副作用 / updated_at=None 致 56 年陈旧** | （`remediate-major-defects-evaluation` spec 提及） | 仍存在 | F-023 / F-026 |
| **backend_registration._api_instance 无锁** | （`remediate-major-defects-evaluation` spec 提及） | 仍存在 | F-028 |
| **registry_validation 混淆 enum 值与数据字段** | （`remediate-major-defects-evaluation` spec 提及） | 仍存在 | F-030 |
| **PhaseShell 阻断阶段按钮仍可点** | （`remediate-major-defects-evaluation` spec 提及） | 仍存在 | W-001 |
| **路由仅注册 / 不进 URL** | （`remediate-major-defects-evaluation` spec 提及） | 仍存在 | W-004 |
| **Modal 无焦点陷阱** | （`remediate-major-defects-evaluation` spec 提及） | 仍存在 | W-003 |
| **Toast 系统重复** | （`remediate-major-defects-evaluation` spec 提及） | 仍存在 | W-010 |
| **SSE 断连误取消云端仍在运行** | （`remediate-major-defects-evaluation` spec 提及） | 仍存在 | U-001 |
| **错误引导仅覆盖 4/11 类** | （`remediate-major-defects-evaluation` spec 提及） | 仍存在 | U-002 |
| **限流倒计时固定 30s** | （`remediate-major-defects-evaluation` spec 提及） | 仍存在 | U-003 |
| **WebApplicationContext 白名单含安全函数** | （`remediate-major-defects-evaluation` spec 提及） | 仍存在 | 见 F-034 相关 |
| **CSRF token 依赖 meta 标签** | （新发现） | 新发现 | W-008 |
| **renderActiveViewFromContext 在 render 期调 hook** | （`remediate-major-defects-evaluation` spec Medium 提及） | 仍存在 | W-007（升为 High） |
| **VirtualList Rules of Hooks 违规** | （新发现） | 新发现 | W-006 |
| **CredentialQuickStart timer 泄漏** | （新发现） | 新发现 | U-015 |
| **audit_dir 查询参数任意目录读取** | （新发现） | 新发现 | F-035 |
| **_read_json min 截断致上限校验死代码** | （新发现） | 新发现 | F-036 |
| **secure_cookies HTTP 下强制 True 致 session 丢失** | （`remediate-major-defects-evaluation` spec High 提及） | 仍存在 | F-037 |
| **Host 校验绕过** | （`remediate-major-defects-evaluation` spec High 提及） | 仍存在 | F-038 |
| **presets.py language 字段错误映射 test_period kind** | （`remediate-major-defects-evaluation` spec High 提及） | 仍存在 | F-021 |
| **web_candidates.payloads.py 重复 import 20 次** | （新发现） | 新发现 | F-022 |
| **i18n.messages pipeline.event.* zh 值实为英文** | （`remediate-major-defects-evaluation` spec Medium 提及） | 仍存在 | U-006 |

### A.2 关键差异说明

1. **本次报告 vs 历史审计整体一致**：111 条历史已知问题中，约 70% 仍存在当前代码中，约 20% 部分修复（如 God Object 已拆分但残留双调度、i18n 已建框架但覆盖不全），约 10% 已修复（如 `_ratio()` 已统一为 `normalize_brain_ratio`、`run_config.json` 重复 key 已清）。
2. **新发现**：本次深读新发现约 15 条历史文档未提及的问题，集中在 WebUI（CSRF meta 依赖 / VirtualList hook 违规 / CredentialQuickStart timer 泄漏）、Web 安全（audit_dir 任意读 / _read_json 截断 / payloads shim 重复 import 20 次）、数值正确性细节（IC 稳定性单元素列表退化、Pearson/Spearman 实现 divergence）。
3. **历史 `remediate-major-defects-evaluation` spec 覆盖度**：该 spec 五轮深读覆盖了大部分本次发现的后端问题，但**前端 WebUI 问题覆盖不足**（如 W-006 VirtualList hook 违规、W-008 CSRF meta 依赖、U-015 CredentialQuickStart timer 泄漏均未提及）；本次报告在 WebUI 维度补充了重要新发现。
4. **判定差异**：内部审计（`CODE_DIAGNOSTIC_REPORT_20260618` / `BRAINALPHA_AUDIT_V3_20260619` / `PHASE33_DELIVERY_REPORT_20260619`）评 8.5/10 偏乐观；外部顾问报告（`BRAINALPHA_FULLSTACK_AUDIT_20260622`）判"不合格"偏严厉。**本次深读结论**：项目可运行但未达生产就绪，Critical 数值正确性问题（F-001/F-002 反过拟合虚假 PASS）与生产安全开关可绕过（F-005）必须立即修复，方可投入真实账户使用。

### A.3 已深读子系统清单

| # | 子系统 | 已读文件数 | 发现问题数 |
|---|--------|-----------|-----------|
| 1 | `research/` + `scoring/` + `compliance/` + `audit_trail/` | ~57 | 15 |
| 2 | `brain_api/` + `browser/` + `web_candidates/` + `web_cloud/` + `monitoring/` + `production_diagnostics/` | ~124 | 10 |
| 3 | `data/` + `config/` + `agent_tools/` + `agent_tool_registry/` + `shared/` + `tasks/` + `ux/` + `i18n/` + `e2e_report/` + `examples/` + 顶层 .py + 顶层入口 + 配置/构建/CI | ~110 | 39 |
| 4 | `web/`（非 react_app）| ~56 | 15 |
| 5 | React 前端（react_app/src 全部）| ~180 | 24 |
| 6 | 历史审计文档（docs/ + 根目录 *.md）| 23 份 | 111 条历史已知问题 |
| **合计** | | **~590+ 文件** | **85 条本次新发现 + 111 条历史交叉核对** |

---

**报告结束。**

本报告基于当前磁盘代码状态，所有结论可通过报告中给出的 `file:line` 引用直接定位代码验证。本报告为纯分析产物，未修改任何业务代码、测试、配置。报告结论可作为后续 `remediate-major-defects-evaluation` / `overhaul-alpha-production-quality` / `improve-frontend-ux` 等 spec 的输入参考。
