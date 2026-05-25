# BRAIN Alpha Ops 全面代码检阅报告

审查日期：2026-05-21  
审查范围：当前工作区源代码、Web 前端模板与拆分 JS、配置/官方 API 适配、持久化层、测试与质量门禁脚本。  
说明：当前工作区已有未提交的前端改动，本报告按当前文件状态审查，未回滚或修改业务代码。

## 验证基线

- 通过：`scripts/quality_gate.py --json`
  - Python compileall、配置校验、依赖策略、六条红线验证、前端 inline 同步、前端语法、文本编码扫描、源码敏感信息扫描、缓存元数据审计、全量 pytest 均通过。
  - pytest 阶段：590 passed。
  - `.pytest_cache` 权限警告已通过独立 cache 目录修复；本次完整门禁 stderr 为空。
- 通过：目标测试 `tests/test_official_adapter.py::test_submit_simulation_rejects_cross_origin_location_header tests/test_official_adapter.py::test_request_rejects_cross_origin_absolute_url tests/test_official_adapter.py::test_request_allows_same_origin_absolute_url tests/test_quality_gate.py::test_dependency_policy_accepts_project_pyproject`
  - 4 passed，pytest cache 目录为 `.pytest_cache_runtime`。
- 工具状态：`ruff 0.15.13`、`mypy 1.20.2`、`pip-audit 2.10.0` 已通过 dev extras 安装并可通过 `python -m ...` 调用；初始 ruff/mypy/pip-audit 信号已采集，发现项仍需后续分批治理。

## 当前执行清单状态

- [x] C-01 完整质量门禁恢复为通过。
- [x] C-02 图表资源策略与 CSP 冲突已处理：移除外部 CDN 依赖，使用本地 canvas fallback。
- [x] C-03 前端安全/行为测试已迁移到当前渲染路径，覆盖当前 `getColumnsForView`、移动卡片、详情、toast 与图表 fallback 的关键契约。
- [x] H-01 模板和生成 HTML 的行内事件已迁移到 `data-action` 委托。
- [x] H-02 官方 API 绝对 URL 与提交响应 `Location` 已限制为同源。
- [x] H-03 前端运行态已统一为单一 `AppState` 状态源。
- [x] M-01 前端 generated HTML 与模块源码同步已由质量门禁验证。
- [x] M-02 Web 前端乱码文本已完成当前源码扫描与质量门禁化。
- [x] M-03 巨型模块拆分已完成当前可执行前端拆分切片。
- [x] M-04 `ruff`、`mypy`、`pip-audit` 静态/依赖审计工具已安装并完成初始信号采集。
- [x] L-01 脚本 CSP 已去除 `unsafe-inline`，改为内联脚本 hash 白名单；样式仍因模板内联 CSS 保留 `style-src 'unsafe-inline'`。
- [x] L-02 字符串实现细节断言已完成当前可执行迁移切片。
- [x] L-03 pytest cache 权限警告已通过 `.pytest_cache_runtime` 规避。

## 总体判断

代码库已经具备较强的业务安全意识：生产/Mock 隔离、配置校验、CSRF/session、官方红线验证、敏感信息扫描、提交前置检查、JSONL 审计链和较丰富的测试都已存在。本轮已恢复完整质量门禁，并处理 Web 前端重构后暴露的资源策略、事件委托、脚本 CSP、官方 API URL 边界、前端运行态状态源、文本编码扫描、静态分析工具链、前端测试契约行为化和前端视图注册拆分问题。当前主要剩余风险集中在静态分析/依赖审计发现项的分批清理，以及后续更大范围架构拆分。

架构上，系统功能完整但仍偏重“巨型协调模块”：`research/pipeline.py` 3461 行、`web.py` 1463 行、`brain_api/official.py` 1202 行、`web/js/app.js` 1011 行。后续优化应优先围绕发布门禁、Web 资源策略、前端事件安全和模块边界收敛展开。

## 严重问题

### C-01 完整质量门禁失败，当前代码不能按既定发布标准交付

- 位置：`scripts/quality_gate.py:242-283`、`tests/test_web.py:22-39`、`tests/test_web.py:221-379`
- 状态：已完成。
- 当前证据：`scripts/quality_gate.py --json` 通过，pytest 阶段 590 passed。
- 原证据：`scripts/quality_gate.py --json` 中 pytest 阶段失败，13 failed / 565 passed。
- 触发点：
  - `tests/test_web.py:314-324` 仍期待 `function renderCurrentView`，当前实现为 `var _renderCurrentView = function ()` 并导出到 `window.renderCurrentView`。
  - `tests/test_web.py:353-379` 仍期待 `workflowNav`、`renderWorkflowNav`、`emptyStateHtml`、`mobileCardHtml`，当前前端已迁移为 `viewTabs` / `renderViewTabs` / table empty state / inline mobile card rendering。
  - 多个测试仍检查旧研究面板函数，如 `renderResearchObservabilityPanel`、`openSqliteLookupDetail`、`applyRobustnessResultToCandidate`。
- 影响：项目文档与质量门禁承诺 `quality_gate.py` 是交付前门禁，但当前完整门禁失败，会让后续打包、提交、CI 接入和发布判断失真。
- 建议：
  - 先确认这是有意 UX 重构还是功能回退。如果是有意重构，更新 `tests/test_web.py` 的契约断言，保留等价的用户行为、安全转义和可访问性检查。
  - 若旧函数代表仍应存在的业务能力，则恢复或迁移对应功能。
  - 将全量 `quality_gate.py --json` 作为合并前阻断项，避免只跑 `--skip-tests`。

### C-02 Chart.js CDN 与服务端 CSP 冲突，图表功能在真实浏览器中会被安全策略拦截

- 位置：`brain_alpha_ops/web/index_template.html:7`、`brain_alpha_ops/web.py:651-654`、`brain_alpha_ops/web/js/views/charts.js:263-283`
- 状态：已完成。
- 当前证据：模板不再包含 `cdn.jsdelivr.net`，`charts.js` 已提供本地 canvas fallback，前端 inline sync 与语法检查均通过。
- 证据：
  - 模板从 `https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js` 加载 Chart.js。
  - 服务端 CSP 为 `script-src 'self' 'unsafe-inline'`，未允许 `cdn.jsdelivr.net`。
  - `charts.js` 在 `Chart` 不存在时只显示“Chart.js 未加载”，不会绘制替代图表。
- 影响：用户切到图表模式时，大概率只看到降级提示，核心图表不可用；同时测试里存在“不得使用 CDN”和“允许 Chart.js 未加载”的新旧策略冲突。
- 建议：
  - 推荐本地 vendoring Chart.js 到 `brain_alpha_ops/web/vendor/` 并纳入 inline/build 规则，保持 CSP `self`。
  - 或删除 CDN 依赖，实现真正的原生 canvas fallback。
  - 如果确实必须用 CDN，需要更新 CSP、SRI、离线策略和测试，但这不适合本地打包 EXE 的稳定性目标。

### C-03 前端安全测试覆盖随重构漂移，部分关键 XSS/行为断言不再覆盖真实渲染路径

- 位置：`tests/test_web.py:221-290`、`brain_alpha_ops/web/js/app.js:459-538`、`brain_alpha_ops/web/js/app.js:672-724`
- 状态：已完成当前可执行迁移。
- 当前证据：`tests/test_web.py`、`tests/test_web_frontend_modules.py`、`tests/test_web_frontend_v2.py` 已覆盖当前前端模块、事件委托、转义路径和离线图表 fallback；质量门禁通过。
- 证据：
  - 旧测试寻找已不存在的 `renderResearchObservabilityPanel`、`renderStatsPanelForView`、`safeClassTokens` 等函数。
  - 当前主表渲染大量使用 `innerHTML` 与 `trustedHtml` 列；虽然现有目标测试覆盖了部分 escape，但旧安全断言未迁移到当前 `getColumnsForView` / `_renderCurrentView` 路径。
- 影响：未来如果 `trustedHtml` 列引入未转义的后端字段，测试可能不会及时拦截。
- 建议：
  - 为当前 `getColumnsForView`、移动卡片、detail modal、toast、chart fallback 建立行为测试，不再只查旧函数名。
  - 将 `trustedHtml` 改为少量白名单 renderer，例如 `statusBadge`、`scoreSpan`、固定按钮，禁止 renderer 直接拼接外部字段。
  - 中期迁移为 DOM API 或组件级 builder，减少 `innerHTML` 面积。

## 高优先级问题

### H-01 行内事件处理与动态 HTML 仍扩大 XSS 爆炸半径

- 位置：`brain_alpha_ops/web/js/app.js:682`、`brain_alpha_ops/web/js/app.js:691`、`brain_alpha_ops/web/js/app.js:719-721`、`brain_alpha_ops/web/js/app.js:738-739`
- 状态：已完成。
- 当前证据：`index_template.html` / `index.html` / `web/js` 中已无 `onclick`、`onchange`、`oninput` 等静态行内事件；页面操作由 `installStaticActionHandlers()` 和 `data-action` 委托接管。
- 证据：详情、提交、选择按钮通过 `onclick="..."` 字符串注入到 HTML；CSP 也保留了 `unsafe-inline`。
- 影响：虽然多数参数经过 `escapeAttr` / `jsStringAttr`，但行内 JS + `innerHTML` 模式对未来改动很脆弱，一旦新增未正确转义字段，XSS 会直接获得本地控制台 session 上下文。
- 建议：
  - 使用事件委托：渲染 `data-action` / `data-id`，在容器上 `addEventListener('click', ...)`。
  - 移除行内 `onclick` / `onkeydown`，逐步收紧 CSP，至少把脚本执行入口集中到 JS 模块中。
  - 对 `escapeAttr` 增加单测覆盖反斜杠、引号、换行和 `</script>` 类输入。

### H-02 官方 API 适配器允许绝对 URL path，缺少同源/官方域约束

- 位置：`brain_alpha_ops/brain_api/official.py:597-606`、`brain_alpha_ops/brain_api/official.py:615-624`、`brain_alpha_ops/brain_api/official.py:731`、`brain_alpha_ops/brain_api/official.py:967-976`
- 状态：已完成。
- 当前证据：`_url()` 拒绝跨源绝对 URL，`submit_simulation()` 对绝对 `Location` 立即执行同源校验；新增 `test_submit_simulation_rejects_cross_origin_location_header`。
- 证据：`_url()` 遇到 `http://` 或 `https://` 的 `path_or_url` 会直接使用；`submit_simulation()` 接受上游 `Location` 或响应 `location` 并传给 `poll_simulation()` / `fetch_result()`。
- 影响：如果官方响应、代理、测试桩或错误配置返回非官方绝对 URL，后续请求会携带认证头或 cookie 请求到非预期域名。这是低概率但高影响的凭据外发/SSRF 类风险。
- 建议：
  - `_url()` 对绝对 URL 做 host allowlist，默认只允许 `config.base_url` 同源。
  - 对 `Location` 仅接受相对路径或同源 URL；否则抛出 `BrainAPIError` 并脱敏记录。
  - 增加 `test_official_adapter` 覆盖跨域 absolute Location 被拒绝。

### H-03 前端运行态与 AppState 存在双状态，容易造成忙碌锁和提交状态不一致

- 位置：`brain_alpha_ops/web/js/app.js:98-101`、`brain_alpha_ops/web/js/state.js:34-39`、`brain_alpha_ops/web/js/app.js:128-165`、`brain_alpha_ops/web/js/app.js:751-777`
- 状态：已完成当前可执行状态源收敛。
- 当前证据：`syncInFlight`、`batchCheckJobId`、`submitInFlight`、`selectedSubmitIds` 不再保存在 `app.js` 局部变量中，读写统一通过 `AppState` helper、`S.set()` 和 `S.setBatch()`；`S.onUpdate()` 已覆盖忙碌锁与提交选择状态刷新。
- 验证：`brain_alpha_ops/web/build_inline.py --check --json`、`scripts/check_frontend_syntax.py --json` 和 H-03 聚焦测试 4 项均通过。
- 证据：`syncInFlight`、`batchCheckJobId`、`submitInFlight`、`selectedSubmitIds` 同时在 app 局部变量和 `AppState` 中有类似字段；部分逻辑读取局部变量，部分测试和状态读取 `S.get(...)`。
- 影响：刷新、异步失败、模块调用或测试桩可能让 UI 按钮状态、提交锁、选择状态与真实后端/前端状态不同步。
- 建议：
  - 选定 `AppState` 为唯一状态源，局部变量只保留纯派生值。
  - 所有状态变更统一走 `S.setBatch()`，并由监听器刷新控件。
  - 为“提交中时检查/同步/生产按钮全部锁定”和“异常后释放锁”补端到端测试。

## 中优先级问题

### M-01 前端 generated HTML 与模块源码同步依赖人工门禁

- 位置：`brain_alpha_ops/web/index_template.html:1256-1268`、`brain_alpha_ops/web/index.html`、`brain_alpha_ops/web/build_inline.py`
- 状态：已完成当前门禁化。
- 当前证据：`frontend_inline_sync` 是默认质量门禁步骤，`scripts/quality_gate.py --json` 通过。
- 证据：当前 `frontend_inline_sync` 通过，但工作区同时修改模板、模块 JS 和生成后的 `index.html`。
- 影响：若后续只提交模板或只提交生成 HTML，会造成运行包与源码不一致。
- 建议：CI 强制运行 `brain_alpha_ops/web/build_inline.py --check --json`；提交说明中明确 `index.html` 是生成产物但必须同步。

### M-02 Web 前端仍存在大量乱码文本，影响可读性和维护

- 位置：`brain_alpha_ops/web/js/utils.js:38-68`、`brain_alpha_ops/web/js/app.js:540-559`、`README.md:1-120`
- 状态：已完成当前源码扫描与门禁化。
- 当前证据：新增 `scripts/check_text_encoding.py`，并接入 `scripts/quality_gate.py` 的 `text_encoding_scan` 步骤；`check_text_encoding.py --json` 扫描 292 个文本文件，`findings: []`。
- 验证：新增 `test_text_encoding_scan_rejects_mojibake` 和 `test_text_encoding_scan_accepts_current_workspace`，相关质量门禁测试 6 项通过。
- 证据：多个中文文本显示为 mojibake，例如 `鎺掗槦`、`浜戠`、`鏆傛棤`。
- 影响：用户体验、测试断言和维护沟通都被干扰；后续替换文案时容易误删业务含义。
- 建议：统一以 UTF-8 重新保存受影响文件，增加一个轻量扫描脚本查常见乱码片段；测试断言尽量验证语义常量或 data 属性。

### M-03 架构模块体量过大，修改风险集中

- 位置：`brain_alpha_ops/research/pipeline.py` 3461 行、`brain_alpha_ops/web.py` 1463 行、`brain_alpha_ops/brain_api/official.py` 1202 行、`brain_alpha_ops/web/js/app.js` 1011 行
- 状态：已完成当前可执行前端拆分切片；后续更大范围 `pipeline.py`、`web.py`、`official.py` 拆分仍建议单独规划。
- 当前证据：新增 `brain_alpha_ops/web/js/view-registry.js`，将视图顺序、分组、标题、图标和提示文本从 `app.js` 中拆出；`app.js` 改为通过 `window.ViewRegistry` 引用注册信息。
- 验证：`brain_alpha_ops/web/build_inline.py --check --json` 通过，inline 模块数 14；`scripts/check_frontend_syntax.py --json` 检查 14 个脚本通过；相关模块契约测试 10 项通过。
- 影响：功能边界模糊，测试定位困难，小改动容易牵连运行、提交、同步、可观测和 UI 多条路径。
- 建议：
  - `web.py` 继续按 route/service 拆分，仅保留 server bootstrap 和兼容导出。
  - `app.js` 拆分为 view controller、actions、renderers、state adapters。
  - `pipeline.py` 以阶段服务或状态机拆分：context、generation、validation、simulation、submission、observability。

### M-04 发布验证缺少静态分析和依赖漏洞审计

- 位置：`scripts/quality_gate.py:210-233`、`scripts/check_optional_tooling.py`
- 状态：已完成工具链安装与初始信号采集；发现项仍需后续专项治理。
- 当前证据：`scripts/check_optional_tooling.py --json` 显示 `ruff 0.15.13`、`mypy 1.20.2 (compiled: yes)`、`pip-audit 2.10.0` 均 available。
- 初始结果：`ruff check brain_alpha_ops scripts tests` 可运行但报告 224 个既有 lint 问题；`mypy --hide-error-codes --no-error-summary brain_alpha_ops scripts` 可运行但报告多处既有类型问题；`pip_audit --strict --progress-spinner off --cache-dir .pip_audit_cache` 可运行但被非 PyPI 依赖 `artifact-tool-v2==2.8.0` 阻断。
- 证据：`ruff`、`mypy`、`pip_audit` 当前均缺失。
- 影响：类型漂移、未使用/未定义符号、依赖 CVE 无法在本地门禁发现。
- 建议：安装 dev extras 后先以 non-blocking 收集 ruff/mypy/pip-audit 结果；稳定后把关键路径纳入阻断门禁。

## 低优先级问题

### L-01 CSP 仍依赖 `unsafe-inline`

- 位置：`brain_alpha_ops/web.py:651-654`
- 状态：脚本侧已完成；样式侧保留。
- 当前证据：`script-src` 不再包含 `unsafe-inline`，而是按返回 HTML 生成 SHA-256 hash；由于模板仍包含内联 CSS 和若干 `style=`，`style-src 'unsafe-inline'` 暂时保留。
- 说明：当前大量 inline script/handler 需要它，短期可接受；长期应随着移除行内事件逐步收紧。
- 建议：先移除动态行内事件，再考虑 nonce/hash 或纯 external self 脚本策略。

### L-02 测试中存在过多字符串实现细节断言

- 位置：`tests/test_web.py:22-39`、`tests/test_web.py:221-379`
- 状态：已完成当前可执行迁移切片。
- 当前证据：`tests/test_web.py` 中研究/SQLite/robustness 行、前端动作按钮、筛选空态、显示模式、操作锁、移动端动作等测试已从读取 `app.js` 内部函数片段迁移为 Node/DOM harness 下执行真实 `AppState` + `renderCurrentView()` / `renderAll()` 行为契约。
- 验证：L-02 聚焦测试 10 项通过。
- 说明：重构函数名、布局名后大量测试失败，但部分用户行为可能仍正常。
- 建议：减少“函数名存在”断言，改为 jsdom/Node 环境下执行渲染函数并验证 DOM、安全转义和可访问属性。

### L-03 `.pytest_cache` 权限警告会干扰验证输出

- 位置：测试运行输出 `.pytest_cache\v\cache` WinError 5
- 状态：已完成。
- 当前证据：`pyproject.toml` 设置 `cache_dir = ".pytest_cache_runtime"`，`.gitignore` 已忽略该目录；聚焦 pytest 与质量门禁不再出现 `.pytest_cache` 权限警告。
- 说明：不阻断目标测试，但会让 CI/人工审查看起来不干净。
- 建议：修复缓存目录权限，或在本地验证命令中设置独立 `PYTEST_ADDOPTS=--cache-clear` / 临时 cache 目录。

## 优化与重构路线

1. 已恢复发布门禁：`scripts/quality_gate.py --json` 全绿。
2. 已修复图表资源策略：移除 CDN，使用本地 canvas fallback，并让 CSP、测试、打包同步。
3. 已收敛前端行内事件入口：模板操作迁移为 `data-action` 委托；下一步继续减少 `trustedHtml` 面积。
4. 已加固官方 API URL 边界：绝对 URL 只允许同源，跨域 `Location` 拒绝并测试。
5. 后续统一前端状态源：把 busy/submission/selection 状态纳入 `AppState`，减少局部变量漂移。
6. 后续分阶段拆分巨型模块：先拆 Web 和 `app.js`，再拆 `pipeline.py` 与 `official.py`。
7. 后续补齐静态工具链：ruff、mypy、pip-audit 先 advisory 后 blocking。

## 当前优点

- 本地 Web 已有 session、CSRF、stream token、Host/Origin/Referer 检查和安全响应头。
- 生产 baseUrl 在 Web payload 层已有 allowlist，敏感扫描当前通过。
- BRAIN 六条技术红线验证通过，官方字段/算子/阈值对齐有自动化守卫。
- JSONL 持久化已有文件锁和 SQLite 辅助索引，审计链设计方向正确。
- 前端模块化比旧版单体 HTML 更清晰，当前测试契约已同步到现有 UX 架构。
