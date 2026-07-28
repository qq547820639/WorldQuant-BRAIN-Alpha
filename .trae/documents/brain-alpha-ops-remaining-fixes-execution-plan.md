# BRAIN Alpha Ops 剩余缺陷修复执行计划

> 承接 `brain-alpha-ops-comprehensive-improvement-plan.md` 的阶段 A/B/C
> 本计划基于对当前代码库的逐项只读验证,仅列出**经验证仍存在**的缺陷
> 验证日期:2026-07-07

---

## 计划摘要 (Summary)

前序计划中阶段 A/B/C 共列出约 25 个修复点。经逐文件验证,**12 个代码缺陷仍存在**(其余已在前序工作中修复或重构消除),外加 **6 类 Code Wiki 文档待补充**。本计划聚焦这 18 项剩余工作,使项目达到生产就绪。

**验证结论速览**:
- A1(反过拟合数值):**全部已修复** — F-001/F-002(代码注释确认)+ F-039/F-040(前序会话修复并验证)
- A2(提交安全):F-011/F-012 已修复;**F-005 仍存在**
- A3(Docker):**F-006/F-007 部分存在**(evidence 755✓ / read_only+资源限制✓,但 root 运行 + 端口 0.0.0.0 + 缺 cap_drop)
- A4(WebUI):W-006/W-007 已修复;**W-001/U-015 仍存在**
- C1(静默异常):**全部已修复**(F-034/F-010/F-009)
- C2(线程安全):**全部仍存在**(F-020/F-028/F-053)
- C3(冗余代码):**全部已修复**(F-022/F-021/F-036)
- C4(数值正确性):F-008 已处理;**F-051/F-052/F-055/F-056 仍存在**
- B(Code Wiki):**全部待补充**

---

## 当前状态分析 (Current State Analysis)

### 已验证修复的项(无需再动)

| 缺陷 | 文件 | 验证依据 |
|------|------|----------|
| F-001 | scoring/anti_overfit/service.py | 代码注释明确,returns 不再回退到 ic_series |
| F-002 | scoring/anti_overfit/checks.py | `_rank_ic` 按 window 分段返回多元素 |
| F-039 | scoring/anti_overfit/checks.py | `_pearson_r` cov 用 `/(n-1)`,有 F-039 注释 |
| F-040 | research/local_backtest_metrics_helpers.py | `rank_values` 平均 rank 处理 ties,有 F-040 注释 |
| F-011 | browser/execution_adapter/_submit.py + _base.py | OrderedDict LRU + move_to_end,有 F-011 注释 |
| F-012 | brain_api/official_simulation/_mixin.py | `check_prod_correlation` 无 try/except,API 失败直接 raise,有 F-012 注释 |
| W-006 | (VirtualList 已移除) | 拆为 CandidateTableDesktop/Mobile,各自无条件调用单一 `useVirtualizer`,无三元分支 |
| W-007 | components/views/renderViewFromContext.tsx | 提升为 `ActiveViewRenderer` 标准组件,有 W-007 注释 |
| F-034 | web/__init__.py | 关键 facade `except` 后 `raise`,有 `see F-034` 标记 |
| F-010 | audit_trail/writer.py | `write_entry` 无 try/except 吞 IO |
| F-009 | research/submission_gate_service.py | `submit_alpha` 未被 try/except 包裹 |
| F-022 | web_candidates/payloads.py | 无 20 行重复 import |
| F-021 | presets.py | 统一 `_registry_default` 模式 |
| F-036 | web/_reexports.py | 改为 `raise ValueError`,无 `min(length, MAX)` 截断 |
| F-008 | research/rolling_validation.py | 显式 `direction_reversal` 检测 + 符号感知公式 |

### 仍存在的缺陷(本计划修复目标)

| # | 缺陷 | 文件:行 | 风险 | 阶段 |
|---|------|---------|------|------|
| 1 | F-005 | runtime_constants.py:357-366 | 真实提交禁令被 env 伪造绕过 | A2 |
| 2 | F-006 | Dockerfile (无 USER 指令) | 容器以 root 运行,逃逸获 root | A3 |
| 3 | F-007 | docker-compose.yml:8,14 | 端口 0.0.0.0 暴露公网 + 缺 cap_drop | A3 |
| 4 | W-001 | components/PhaseShell.tsx:102-107 | 阻断阶段按钮仍可点击 | A4 |
| 5 | U-015 | components/CredentialQuickStart.tsx:166-169 | guided-retry setTimeout 泄漏,卸载后 setState | A4 |
| 6 | F-020 | metrics.py (MetricsCollector) | 计数器读写无锁,多线程竞态 | C2 |
| 7 | F-028 | backend_registration.py:66-74 | _api_instance 无双检锁,竞态创建 | C2 |
| 8 | F-053 | research/record_sqlite_index.py | 无 BEGIN IMMEDIATE,写事务升级死锁 | C2 |
| 9 | F-051 | scoring/release_score_gate/release_score_gate.py:411 | settings 为 None 时回退到 metrics(语义错误) | C4 |
| 10 | F-052 | research/prod_correlation.py:252-268 | 本地回退对 complexity≥50 放行,未 fail-closed | C4 |
| 11 | F-055 | research/fusion.py:152-156 | mode="max" 跳过 `_validate_fusion_expr` | C4 |
| 12 | F-056 | research/backtest_flow_service/_slot_submission.py:87 | `return` 应为 `continue`,中止后续槽提交 | C4 |

---

## 提议的改动 (Proposed Changes)

### 阶段 A2:生产提交安全开关加固(F-005)

**目标**:堵死真实提交被 env 伪造绕过的路径。

**文件**:[brain_alpha_ops/runtime_constants.py](file:///workspace/brain_alpha_ops/runtime_constants.py) 第 357-366 行

- **What**:重写 `real_submit_test_override_enabled()`,移除对 `PYTEST_CURRENT_TEST` env var 的依赖,改用调用栈检查判断是否在 pytest 框架内执行
- **Why**:`PYTEST_CURRENT_TEST` 是普通环境变量,运维/容器编排可伪造;配合另外两个 env(`BRAIN_ALPHA_FORCE_REAL_SUBMIT=1` + `BRAIN_ALPHA_ENABLE_REAL_SUBMIT_TESTS=1`)即可绕过 `REAL_SUBMIT_DISABLED_WEB_FLOW=True` 硬开关,触发真实提交
- **How**:用 `sys._getframe` 遍历调用栈,检测栈帧的 `__file__` 是否匹配 pytest 内部模块(如 `pytest`/`_pytest`),仅在确认调用链源自 pytest 时才允许 override。仍保留另外两个 env 作为显式双重确认。伪代码:
  ```python
  def real_submit_test_override_enabled() -> bool:
      import os, sys
      if os.environ.get("BRAIN_ALPHA_FORCE_REAL_SUBMIT") != "1":
          return False
      if os.environ.get("BRAIN_ALPHA_ENABLE_REAL_SUBMIT_TESTS") != "1":
          return False
      # F-005: 不再信任 PYTEST_CURRENT_TEST env(可伪造),改用调用栈验证
      frame = sys._getframe(1)
      while frame is not None:
          f = frame.f_globals.get("__file__", "")
          if "pytest" in f or "_pytest" in f:
              return True
          frame = frame.f_back
      return False
  ```
- **验证**:`pytest -k "submit" -v`;新增/调整测试验证非 pytest 调用栈下三个 env 齐设仍返回 False

---

### 阶段 A3:Docker 安全加固(F-006, F-007)

**目标**:容器最小权限 + 仅本机暴露。

**文件 1**:[Dockerfile](file:///workspace/Dockerfile) 第 86-98 行(F-006)

- **What**:在 runtime stage 添加非 root 用户;`USER appuser` 指令置于 CMD 之前;确保 `/app/data`、`/app/config`、`/app/artifacts` 归属 appuser
- **Why**:当前容器以 root 运行,容器逃逸直接获宿主 root
- **How**:
  ```dockerfile
  # 在 mkdir/chmod 之后(line 87 后)添加:
  RUN useradd --create-home --shell /bin/bash appuser \
      && chown -R appuser:appuser /app
  USER appuser
  ```
  evidence 目录已是 755(前序修复),保持不变。注意 runtime-full stage 继承 runtime,Playwright 需在 appuser 下运行,`playwright install chromium --with-deps` 的 `--with-deps` 装 OS 依赖需在切 USER 之前的 root 阶段完成(当前 runtime-full 在 runtime 之后,需调整:OS 依赖安装保留 root,`USER appuser` 在 runtime 中设好后 runtime-full 继承即可,但 apt-get 需 root → 需在 runtime-full 中临时 `USER root` 装 deps 再 `USER appuser`,或把 USER 指令移到 runtime 末尾且 runtime-full 在 apt-get 后重新声明 USER)

**文件 2**:[docker-compose.yml](file:///workspace/docker-compose.yml) 第 7-14 行(F-007)

- **What**:端口绑定改为 `127.0.0.1:8765:8765`;`WEB_HOST=127.0.0.1`;添加 `cap_drop: [ALL]`、`security_opt: [no-new-privileges:true]`
- **Why**:当前 `"8765:8765"` 等价 `0.0.0.0:8765:8765` 暴露公网;无 cap_drop/no-new-privileges 缺少纵深防御
- **How**:
  ```yaml
  ports:
    - "127.0.0.1:8765:8765"
  environment:
    - WEB_HOST=127.0.0.1
  cap_drop:
    - ALL
  security_opt:
    - no-new-privileges:true
  ```
  保留已有 `read_only: true`、`tmpfs`、`deploy.resources.limits`
- **注意**:`read_only: true` 与 browser 模式不兼容(已有注释说明),headless 默认场景适用。若用户需 browser 模式,文档提示禁用 read_only

---

### 阶段 A4:WebUI 阻断级修复(W-001, U-015)

**文件 1**:[web/react_app/src/components/PhaseShell.tsx](file:///workspace/brain_alpha_ops/web/react_app/src/components/PhaseShell.tsx) 第 102-107 行(W-001)

- **What**:阻断态容器加 `inert` 属性(React 19 原生支持,或用 `pointer-events: none` + `aria-disabled`);保留现有 opacity/grayscale 视觉提示
- **Why**:当前仅 `style={{opacity: 0.45, filter: 'grayscale(0.3)'}}`,按钮仍可点击,用户可触发未就绪阶段导致状态机错乱
- **How**:
  ```tsx
  <div
    className="phase-shell-body"
    style={isBlocked ? { opacity: 0.45, filter: 'grayscale(0.3)', pointerEvents: 'none' } : undefined}
    inert={isBlocked ? '' : undefined}
    aria-disabled={isBlocked || undefined}
  >
    {children}
  </div>
  ```
  `pointer-events: none` 兜底旧浏览器;`inert` 屏蔽所有交互+焦点+辅助技术访问。需确认项目 React 版本是否支持 `inert`(React 19 原生支持,18 需用 `inert` polyfill 或仅 `pointer-events`)

**文件 2**:[web/react_app/src/components/CredentialQuickStart.tsx](file:///workspace/brain_alpha_ops/web/react_app/src/components/CredentialQuickStart.tsx) 第 157-172 行(U-015)

- **What**:将 `handleGuidedRetry` 中的 `setTimeout` 存入 ref,在组件卸载时清理;当前返回的清理函数未被 useEffect 消费
- **Why**:第 166 行 `const timer = setTimeout(...)` 返回 `() => clearTimeout(timer)` 但 onClick 不处理返回值,组件卸载后 setTimeout 仍触发 `handleTestConnection()` → setState,产生 "setState on unmounted component" 警告/泄漏
- **How**:新增 `guidedRetryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)`,在 `handleGuidedRetry` 中赋值,并新增一个 `useEffect` cleanup 在卸载时 `clearTimeout`:
  ```tsx
  const guidedRetryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    return () => {
      if (guidedRetryTimerRef.current) {
        clearTimeout(guidedRetryTimerRef.current);
        guidedRetryTimerRef.current = null;
      }
    };
  }, []);
  // handleGuidedRetry 内:
  guidedRetryTimerRef.current = setTimeout(() => {
    guidedRetryTimerRef.current = null;
    handleTestConnection();
  }, waitSeconds * 1000);
  ```
  移除原 `return () => clearTimeout(timer)`(未被消费)

---

### 阶段 C2:线程安全修复(F-020, F-028, F-053)

**文件 1**:[brain_alpha_ops/metrics.py](file:///workspace/brain_alpha_ops/metrics.py) `MetricsCollector` 类(F-020)

- **What**:添加 `self._lock = threading.Lock()`,所有写操作(`counter`/`gauge`/`histogram`/`timer`)用 `with self._lock:` 包裹;读操作(`get_snapshot` 等)用 `with self._lock:` 拷贝
- **Why**:Web 控制台用 `ThreadPoolExecutor`(WebDefaults.TASK_EXECUTOR_MAX_WORKERS=4)并发跑任务,多线程同时 `self._counters[key] += value` 会丢更新;`histogram.append` 非原子
- **How**:在 `__init__` 加 `self._lock = threading.Lock()`;每个写方法体包 `with self._lock:`。锁粒度按方法级即可(计数器操作极短)

**文件 2**:[brain_alpha_ops/backend_registration.py](file:///workspace/brain_alpha_ops/backend_registration.py) 第 63-74 行(F-028)

- **What**:`_get_brain_api()` 改用模块级 `threading.Lock()` + 双检锁
- **Why**:当前单次检查 `_api_instance is not None`,两线程同时通过检查会各自 `OfficialBrainAPI()` 创建实例并相互覆盖,可能导致半初始化实例被使用
- **How**:
  ```python
  _api_lock = threading.Lock()
  def _get_brain_api():
      global _api_instance
      if _api_instance is not None:  # fast path
          return _api_instance
      with _api_lock:
          if _api_instance is not None:  # double-check
              return _api_instance
          from brain_alpha_ops.brain_api.official import OfficialBrainAPI
          _api_instance = OfficialBrainAPI()
          return _api_instance
  ```

**文件 3**:[brain_alpha_ops/research/record_sqlite_index.py](file:///workspace/brain_alpha_ops/research/record_sqlite_index.py)(F-053)

- **What**:写事务用 `BEGIN IMMEDIATE` 包裹 read+write,避免 deferred 隔离下多写者升级死锁
- **Why**:当前 `conn.execute(...)` + `conn.commit()` 用默认 deferred 隔离,多线程同时写时 SQLite 在升级锁时可能抛 `database is locked`;`BEGIN IMMEDIATE` 在事务开始即获写锁,失败快速返回而非死锁
- **How**:在写操作前显式 `conn.execute("BEGIN IMMEDIATE")`,完成后 `conn.commit()`;或在 `_connect` 中设 `conn.isolation_level = None`(autocommit)后手动 `BEGIN IMMEDIATE`/`COMMIT`。读操作保持默认即可

---

### 阶段 C4:数值正确性修复 P1(F-051, F-052, F-055, F-056)

**文件 1**:[brain_alpha_ops/scoring/release_score_gate/release_score_gate.py](file:///workspace/brain_alpha_ops/scoring/release_score_gate/release_score_gate.py) 第 411 行(F-051)

- **What**:`effective_settings = settings if settings is not None else metrics` 改为 `effective_settings = settings if settings is not None else {}`
- **Why**:settings 为 None 时回退到 metrics,把 sharpe/returns 等指标误当作 region/universe/delay 等 settings 传给 `ThresholdPolicy.from_thresholds`,导致阈值策略基于错误字段计算
- **How**:单行修改为 `else {}`。确认 `ThresholdPolicy.from_thresholds` 能处理空 dict(应有默认值)

**文件 2**:[brain_alpha_ops/research/prod_correlation.py](file:///workspace/brain_alpha_ops/research/prod_correlation.py) 第 252-268 行(F-052)

- **What**:`_local_fallback` 改为 fail-closed:当官方 API 不可用时,`passed=False`(或 `correlation=1.0`),不再用表达式长度估算后放行
- **Why**:当前对 complexity≥50 的表达式 estimated_corr<0.70 → `passed=True`,即 API 不可用时仍放行高相关性 alpha,违反提交门禁安全语义
- **How**:参考同文件第 124 行 `allow_local_fallback=False` 路径已返回 `correlation=1.0`(fail-closed)。将 `_local_fallback` 统一为返回 `correlation=1.0, passed=False, source="local_estimate_unavailable", error=reason`。保留 source 字段供下游区分原因,但 passed 强制 False
- **注意**:需检查调用方是否有依赖 `passed=True` 的本地回退路径,若有需同步调整或提供 `allow_local_fallback` 开关

**文件 3**:[brain_alpha_ops/research/fusion.py](file:///workspace/brain_alpha_ops/research/fusion.py) 第 152-156 行(F-055)

- **What**:mode="max" 分支末尾 `return result` 改为 `return _validate_fusion_expr(result, "ensemble_max")`,与其他分支一致
- **Why**:同函数 `"average"`/`"rank_average"`/`"min"` 分支均调用 `_validate_fusion_expr` 校验结果表达式,唯独 "max" 跳过,可能产出未校验的非法表达式
- **How**:单行修改 `return _validate_fusion_expr(result, "ensemble_max")`

**文件 4**:[brain_alpha_ops/research/backtest_flow_service/_slot_submission.py](file:///workspace/brain_alpha_ops/research/backtest_flow_service/_slot_submission.py) 第 87 行(F-056)

- **What**:第 87 行 `return` 改为 `continue`
- **Why**:在 `for slot in open_slots:` 循环内,单槽提交失败时 `return` 会退出整个函数,放弃后续所有 open_slots 的提交机会;应为 `continue` 跳过当前失败槽继续下一槽(同函数第 52 行对"重复屏蔽"已用 `continue`,佐证循环语义)
- **How**:单行修改 `return` → `continue`

---

### 阶段 B:Code Wiki 改进

**目标**:补充 [docs/CODE_WIKI.md](file:///workspace/docs/CODE_WIKI.md) 的 6 类缺失内容。

**改动**(仅编辑 `docs/CODE_WIKI.md`,在现有 8 章后追加):

- **B1. HTTP API 端点参考**:新增章节,列出主要 POST 处理器 + GET 路由,含路径、请求体、响应体、鉴权要求、HIL 确认门。来源:[web/dispatch/web_post_routes.py](file:///workspace/brain_alpha_ops/web/dispatch/web_post_routes.py)、[web/dispatch/web_routes.py](file:///workspace/brain_alpha_ops/web/dispatch/web_routes.py)。重点覆盖 `/api/candidates/simulate`(HIL gate)、`/api/submit_*`(REAL_SUBMIT_DISABLED)、`/api/health`、`/api/snapshot/*`

- **B2. React 前端架构**:新增章节,覆盖组件树(App → PhaseShell → views)、状态管理(AppStateContext composition root,见 [hooks/useAppState](file:///workspace/brain_alpha_ops/web/react_app/src/hooks/useAppState))、SSE/轮询通信、路由策略(activeView 状态切换)、构建配置(Vite)。说明 VirtualList 已拆为 CandidateTableDesktop/Mobile

- **B3. 测试策略与结构**:新增章节,覆盖测试标记(slow/integration/e2e/browser/live/readonly/mock,见 [tests/conftest.py](file:///workspace/tests/conftest.py))、覆盖率门槛 80%([pyproject.toml](file:///workspace/pyproject.toml))、夹具工厂、E2E 框架(Playwright)

- **B4. CI/CD 流程**:新增章节,覆盖 [.github/workflows/](file:///workspace/.github/workflows/) 下 workflow 的触发条件、阶段、产物

- **B5. 已知缺陷索引**:新增章节,汇总评估报告 85 条缺陷的编号、文件、严重度、状态。标注本计划修复的 12 项 + 已修复的 15 项,其余 backlog

- **B6. 贡献者指南**:新增章节,覆盖代码规范(ruff/mypy,见 [pyproject.toml](file:///workspace/pyproject.toml))、提交规范、分支策略、质量门禁脚本([scripts/check_*.py](file:///workspace/scripts/))

---

## 假设与决策 (Assumptions & Decisions)

### 假设
1. 上述 12 项缺陷的文件路径与行号基于 2026-07-07 代码状态,执行时可能因其他改动偏移,以缺陷 ID + 函数名为准定位
2. 测试套件(2874+ 用例)能覆盖改动影响范围;C2 线程安全改动可能无直接并发测试,需人工复核
3. React 前端项目 React 版本需确认是否支持 `inert`(W-001),若不支持则用 `pointer-events: none` + `tabIndex={-1}` 兜底
4. `ThresholdPolicy.from_thresholds` 能处理空 dict(F-051),需在执行时确认
5. prod_correlation `_local_fallback` 改 fail-closed(F-052)可能影响依赖本地回退的测试,需同步调整测试或保留 `allow_local_fallback` 开关

### 决策
1. **优先级**:A2(P0 提交安全)> A3(P0 容器安全)> A4(P0 WebUI 崩溃)> C2(P1 线程安全)> C4(P1 数值正确性)> B(文档)
2. **不重复已修复项**:前序已修复的 15 项(F-001/F-002/F-039/F-040/F-011/F-012/W-006/W-007/F-034/F-010/F-009/F-022/F-021/F-036/F-008)不再触碰
3. **最小改动**:每个修复点只改必要行,不顺带重构;F-005/F-051/F-055/F-056 均为单行~数行修改
4. **保持契约**:所有修复保持现有 API/配置/测试兼容;F-052 若破坏现有回退契约,保留 `allow_local_fallback` 开关而非强制全局 fail-closed
5. **Docker USER 处理**:runtime stage 末尾设 `USER appuser`;runtime-full 因需 apt-get 装 Playwright 依赖,在 apt-get 后重新 `USER appuser`
6. **验证方式**:每阶段完成后跑相关 pytest 子集;阶段 B 完成后人工审阅文档链接

---

## 验证步骤 (Verification Steps)

### 阶段 A2 验证(F-005)
1. `pytest -k "submit" -v` — 提交相关测试
2. 新增验证:非 pytest 调用栈下,三 env 齐设仍返回 False(可用内联脚本模拟)

### 阶段 A3 验证(F-006, F-007)
1. `docker build -t brain-alpha-ops . && docker run --rm brain-alpha-ops python -c "import os; print(os.getuid())"` — 应输出非 0
2. `docker compose config` — 验证端口绑定 127.0.0.1 + cap_drop + security_opt
3. 若环境无 docker,人工审阅 Dockerfile/docker-compose.yml 改动

### 阶段 A4 验证(W-001, U-015)
1. `cd brain_alpha_ops/web/react_app && npm run typecheck && npm run build` — 类型检查与构建
2. 若有前端测试:`npm test -- --run`
3. 人工审阅:PhaseShell 阻断态 inert 生效;CredentialQuickStart 卸载无 setState 警告

### 阶段 C2 验证(F-020, F-028, F-053)
1. `pytest tests/test_metrics.py -v`(若存在)
2. `pytest tests/test_backend_registration.py -v`(若存在)
3. `pytest tests/test_record_sqlite_index.py -v`(若存在)
4. `pytest -k "sqlite or metrics or backend_registration" -v`

### 阶段 C4 验证(F-051, F-052, F-055, F-056)
1. `pytest tests/test_release_score_gate.py -v`(若存在)
2. `pytest tests/test_prod_correlation.py -v`(若存在)
3. `pytest tests/test_fusion.py -v`(若存在)
4. `pytest tests/test_backtest_flow_service.py -v`(若存在)
5. `pytest -k "fusion or release_score or prod_correlation or slot_submission" -v`

### 阶段 B 验证
1. 人工审阅 [docs/CODE_WIKI.md](file:///workspace/docs/CODE_WIKI.md) 新增 6 章的完整性与准确性
2. 验证所有 `file:///` 链接指向真实存在的文件

### 最终验证
1. `pytest --cov=brain_alpha_ops --cov-fail-under=80` — 覆盖率门槛(若环境缺 numpy 等依赖,跑可运行子集)
2. `python scripts/check_python_silent_broad_exceptions.py` — 静默异常检查(确认 C1 仍 OK)
3. `python scripts/check_architecture.py` — 架构合规(若存在)
4. `python -m brain_alpha_ops.compliance.redline_verifier --block` — 红线验证(确认 zero_deviation 未破坏)

---

## 实施顺序

1. **A2**(F-005,1 项):runtime_constants.py 调用栈检查
2. **A3**(F-006, F-007,2 项):Dockerfile USER + docker-compose 端口/cap_drop
3. **A4**(W-001, U-015,2 项):PhaseShell inert + CredentialQuickStart timer ref
4. **C2**(F-020, F-028, F-053,3 项):metrics Lock + 双检锁 + BEGIN IMMEDIATE
5. **C4**(F-051, F-052, F-055, F-056,4 项):单行修复 + prod_correlation fail-closed
6. **B**(6 类文档):Code Wiki 章节补充
7. **最终验证**:pytest 子集 + 质量门禁脚本

每阶段完成后立即跑相关测试,失败即修,不累积。
