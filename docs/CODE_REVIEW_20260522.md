# BRAIN Alpha Ops 全面代码检阅报告

审查日期：2026-05-22

审查范围：当前工作区 Python 后端、本地 Web 控制台、原生 JavaScript 前端、配置/质量门禁、持久化与测试。  
验证基线：本轮收口复跑 `scripts/quality_gate.py --json` 通过，pytest 阶段 598 passed；前端内联同步、前端语法、文本编码扫描和敏感信息扫描均通过。

## 总体结论

代码库的核心安全基线比一般本地工具扎实：有 session/CSRF、Host/Origin/Referer 检查、安全响应头、官方 API 同源 URL 限制、敏感信息扫描、配置校验、BRAIN 红线验证和较完整测试。当前没有发现默认质量门禁级别的阻断缺陷。

本轮已按清单完成所有当前可执行整改项。后续主要是持续性工程治理：继续保持白名单渲染、扩展静态分析覆盖，并按业务边界逐步深化模块拆分。

## 当前执行清单

- [x] H-02 让 ruff/mypy 扩展门禁恢复为可用信号。
- [x] M-02 收敛高成本 Web API 查询上限，降低本地性能抖动风险。
- [x] M-04 为 Assistant context/request 增加递归敏感信息脱敏。
- [x] L-03 封闭 Repository 内部 JSONL 文件名 API，增加路径 containment 防护。
- [x] H-01 将前端 `trustedHtml` 改为白名单 renderer 或 DOM builder。
- [x] H-03 拆分 `pipeline.py`、`web.py`、`official.py`、`app.js` 巨型协调模块。
- [x] M-01 完全移除样式侧 `style-src 'unsafe-inline'` 依赖。
- [x] M-03 将 Web API 长 `if/elif` 分发重构为 handler 映射。
- [x] L-01 校正文案/注释历史 mojibake 可读性问题。
- [x] L-02 为远程 HTTPS 部署模式追加 `Secure` cookie 策略。

## 高严重度问题

### H-01 前端 HTML 注入面仍偏大，`trustedHtml` 依赖人工约束

- 位置：
  - `brain_alpha_ops/web/js/app.js:458-468`
  - `brain_alpha_ops/web/js/app.js:478-484`
  - `brain_alpha_ops/web/js/components/table.js:91-106`
  - `brain_alpha_ops/web/js/app.js:837-888`
- 证据：表格和移动卡片通过 `innerHTML` 拼接整行 HTML；列定义中多处 `trustedHtml: true` 允许 renderer 原样进入 DOM。
- 影响：当前多数 renderer 调用了 `esc()`、`statusBadge()`、`scoreSpan()` 等安全 helper，未确认存在直接可利用 XSS；但该模式让新增列或后续改动很容易把 API/JSONL 中的未转义字段带入 DOM。一旦本地 Web 控制台被恶意记录、缓存数据或回放文件污染，攻击面会直接落到同源 session 上下文。
- 已执行：新增 `Utils.renderSafeHtmlFragment` 白名单片段渲染器，表格/移动卡片渲染入口不再读取 `trustedHtml` 作为 HTML 直通开关；主视图列定义改为 `htmlType: 'badge'|'score'|'buttonGroup'|'candidateId'|'riskText'`；补充前端回归测试覆盖旧 `trustedHtml` 被转义、白名单片段保留、恶意 `<script>`/`<img onerror>`/事件属性被拒绝。
- 建议：
  - 将 `trustedHtml` 改为小型白名单 renderer 类型，例如 `badge`、`score`、`buttonGroup`，禁止任意 renderer 返回 HTML 字符串。
  - 对主表格、移动卡片和详情页逐步迁移到 DOM builder：文本用 `textContent`，属性用 `setAttribute`，事件走委托。
  - 添加专门测试：任何 `trustedHtml` 列只能来自白名单 helper；包含 `<script>`, `<img onerror>`, `javascript:` 的候选/云端/生命周期字段必须被转义。

### H-02 ruff/mypy 扩展门禁不可用，类型和 lint 信号不能进入发布阻断

- 位置：
  - `scripts/quality_gate.py:38-126`
  - `scripts/quality_gate.py:226-235`
  - `scripts/check_dependency_policy.py:14`
  - `tests/test_web_cloud_snapshot.py:30`
- 证据：原始运行中 `scripts/quality_gate.py --skip-tests --ruff --mypy --json` 的基础步骤通过，但 ruff 仍报 7 个问题；mypy 因 `Source file found twice under different module names: "quality_gate" and "scripts.quality_gate"` 直接中止，未进入主体类型检查。
- 已执行：为 mypy 增加 `--explicit-package-bases`，修复 ruff 未使用导入/测试 lambda 噪声，并补齐当前静态目标集的类型窄化。复跑 `scripts/quality_gate.py --skip-tests --ruff --mypy --json` 已通过：ruff 输出 `All checks passed!`，mypy 输出 `Success: no issues found in 87 source files`。
- 后续建议：将 `--ruff --mypy` 纳入 CI 的非阻断报告，稳定后再转为发布阻断项。

### H-03 巨型协调模块仍是主要回归风险源

- 位置：
  - `brain_alpha_ops/research/pipeline.py` 3228 行
  - `brain_alpha_ops/web.py` 1208 行
  - `brain_alpha_ops/brain_api/official.py` 1101 行
  - `brain_alpha_ops/web/js/app.js` 1044 行
- 证据：最大模块曾同时承担配置装配、业务协调、API 调用、状态转换、错误处理、UI 渲染或兼容导出等多种职责。
- 影响：小改动容易牵连提交安全、云端同步、候选生命周期、UI 状态和测试契约；此前已有 `view-registry.js` 拆分，但主要复杂度仍集中在后端 pipeline/web/official 以及前端 app orchestrator。
- 已执行：
  - 新增 `brain_alpha_ops/web/js/view-renderers.js`，承接主结果视图的 row source、搜索过滤、桌面列定义和移动端动作渲染；`app.js` 收敛为页面状态、事件委托和流程协调入口。
  - 新增 `brain_alpha_ops/brain_api/official_helpers.py`，承接 Official API URL 同源校验、重试延迟、响应解析、指标归一化、分页/缓存辅助和数据 scrub 逻辑；`official.py` 保留适配器和兼容导出。
  - 新增 `brain_alpha_ops/research/pipeline_helpers.py`，承接候选排序、Assistant guidance 转换、上下文默认值合并、slot 状态消息和 CLI 汇总统计；`pipeline.py` 继续保留核心编排。
  - 新增 `brain_alpha_ops/web_csp.py`，承接 CSP script/style hash 计算和策略拼装；`web.py` 保留 server bootstrap/兼容 facade。
  - 更新前端内联模板和模块契约测试，重建 `brain_alpha_ops/web/index.html`，确认内联 bundle 从 14 个模块扩展为 15 个模块。
- 后续建议：继续按业务阶段深化拆分，例如 pipeline 的 generation/validation/simulation/submission 子流程、official 的 auth/session/cache 子层，以及 app 的 action controller/state adapter。

## 中严重度问题

### M-01 CSP 仍保留 `style-src 'unsafe-inline'`

- 位置：`brain_alpha_ops/web.py:324-330`
- 证据：脚本 CSP 已基于 hash 收紧，但样式仍允许内联；模板中存在大量内联 CSS 和 `style=`。
- 影响：这不是直接执行脚本的洞，但会削弱防御纵深；若未来出现 HTML 注入，攻击者可更容易做 UI 欺骗或覆盖交互元素。
- 已执行：移除模板和 JS 字符串中的 `style=` 属性依赖，迁移为 class 或受控 `data-style-width`/`data-style-left` + CSSOM 应用；新增样式块 SHA-256 hash 计算并将 CSP 收紧为 `style-src 'self' 'sha256-...'`，不再包含 `'unsafe-inline'`；补充测试覆盖静态 HTML 无内联样式属性、CSP 样式 hash 和前端渲染回归。
- 建议：逐步把内联样式迁移为 class；对动态 width/color 这类样式引入受限 helper；最终将 `style-src` 收紧到 `'self'` 或 nonce/hash 策略。

### M-02 API 查询上限较高，局部端点可能造成本地性能抖动

- 位置：
  - `brain_alpha_ops/web_handler_dispatch.py:115-128`
  - `brain_alpha_ops/web_handler_dispatch.py:150-178`
  - `brain_alpha_ops/jsonl.py:81-125`
  - `brain_alpha_ops/web/js/app.js:454`
- 证据：多个端点原允许 `limit` 到 50,000；JSONL tail reader 会按请求行数回读并解析；前端最终只渲染 `MAX_RENDERED_ROWS` 300 行。
- 已执行：将 research/assistant 历史快照类端点最大 `limit` 收敛到 10,000，将 prompt/knowledge/guidance 账本类端点收敛到 5,000，将 sqlite record lookup 收敛到 500，并补充 `test_dispatch_get_clamps_high_cost_history_limits` 覆盖异常大查询参数。
- 后续建议：若历史数据继续增长，再引入 server-side pagination/cursor 和只返回聚合摘要的轻量端点。

### M-03 Web API 路由分发是长 if/elif 链，扩展和审计成本较高

- 位置：
  - `brain_alpha_ops/web_handler_dispatch.py:78-213`
  - `brain_alpha_ops/web_handler_dispatch.py:216-230`
  - `brain_alpha_ops/web_routes.py:17-74`
- 证据：已有 route metadata，但实际 handler 曾靠长条件链分发。
- 已执行：`dispatch_get`/`dispatch_post` 改为通用 origin/route/session 校验后，通过 `WebRoute.handler` 查 `_GET_DISPATCH_HANDLERS`/`_POST_DISPATCH_HANDLERS` 显式映射执行；新增测试校验所有 route metadata handler 均有映射。
- 后续建议：继续把每个端点的参数 schema/limit 上限逐步提升到 route metadata 层，减少 handler 内散落解析。

### M-04 Assistant context 的敏感字段控制只覆盖 `storage_dir`

- 位置：
  - `brain_alpha_ops/research/context.py:48-79`
  - `tests/test_assistant_context.py:146-153`
- 证据：原实现中 `include_sensitive=False` 只移除顶层 `storage_dir`；测试也只断言该字段。
- 已执行：扩展共享 redaction helper，支持按敏感 key/片段递归脱敏；`build_assistant_context_pack(..., include_sensitive=False)` 会先脱敏再渲染 prompt，`build_assistant_request_pack` 从已脱敏 context 派生，测试覆盖 token/password/path/storage_dir 不出现在 context 与 request 中。
- 后续建议：未来新增 assistant 上下文字段时，继续把外部 LLM 可见字段纳入敏感信息回归测试。

## 低严重度问题

### L-01 前端文案/注释仍存在可读性问题

- 位置：
  - `brain_alpha_ops/web/js/view-registry.js:20-55`
  - `brain_alpha_ops/web/js/utils.js:37-68`
- 证据：多处中文文案在当前 PowerShell/文件显示中呈 mojibake 形态。文本编码扫描通过，说明这更像历史转码/显示链路问题，而非当前新增坏编码。
- 影响：维护者难以确认文案真实语义，后续改 UI、测试断言或本地化时容易误删业务含义。
- 已执行：用 `scripts/check_text_encoding.py --root ... --json` 纳入质量门禁扫描 UTF-8 解码错误和常见 mojibake 模式；复核 `view-registry.js`、`utils.js`、本检阅报告等目标文件的 Python UTF-8 读取内容为可读中文，当前全量扫描结果为 `ok: true`、293 个文本文件无发现。
- 建议：逐文件用 UTF-8 重新校正文案源；核心业务文案放到集中 registry，并用语义 key 测试。

### L-02 Cookie 未设置 `Secure`

- 位置：`brain_alpha_ops/web_security.py:94-99`
- 证据：session cookie 包含 `HttpOnly; SameSite=Strict`，但原先没有 `Secure`。
- 已执行：`LocalSessionManager` 新增 `secure_cookies` 策略，远程绑定/HTTPS 部署模式可追加 `Secure`；Web 配置新增 `web.secure_cookies` 布尔项，`serve(..., allow_remote=True)` 默认启用 secure cookie，本地 HTTP/loopback 模式保持兼容行为。
- 后续建议：若后续加入反向代理/TLS 终止配置，可把 scheme/proxy 信任边界也纳入 cookie 策略测试。

### L-03 SQLite 与 JSONL 持久化整体安全，但写入文件名 API 仍需保持封闭

- 位置：
  - `brain_alpha_ops/research/repository.py:248-260`
  - `brain_alpha_ops/research/repository.py:201-233`
- 证据：公开 save 方法使用固定文件名，当前未发现 Web payload 可直接控制 filename；内部 `_append(filename)`、`maybe_archive(filename)` 曾接受字符串拼路径。
- 已执行：新增 Repository JSONL/lock 允许清单，所有内部 append、lock、archive 路径经 `resolve()` 后校验仍位于 storage root；未知文件名、子目录和 `..` 路径会抛出 `ValueError`。新增测试覆盖路径穿越拒绝与已知 JSONL 文件正常写入。
- 后续建议：未来若新增持久化文件，先扩展允许清单和对应测试，再接入公开调用路径。

## 当前优势

- 默认质量门禁、前端 inline 同步、前端语法、文本编码、敏感信息扫描、缓存审计和 pytest 基线均已建立。
- 官方 API URL 已限制同源：`brain_alpha_ops/brain_api/official.py:971-986` 拒绝跨源绝对 URL。
- Web session 具备 `HttpOnly`、`SameSite=Strict`、CSRF header/stream token、Host/Origin/Referer 校验。
- SQL 查询基本使用参数化绑定，未发现直接拼接用户输入的 SQL 注入证据。

## 建议优先级

1. 先修复 mypy target 配置和 ruff 低噪声项，让静态分析变成可用信号。
2. 将前端 `trustedHtml` 改为白名单 renderer，并补 XSS 回归用例。
3. 降低高成本 API 的默认/最大 limit，引入分页或摘要端点。
4. 继续拆分巨型模块，优先拆 `web.py` dispatch/service 和 `app.js` renderer/action。
5. 为 assistant context/request 增加递归 redaction 与敏感信息测试。
