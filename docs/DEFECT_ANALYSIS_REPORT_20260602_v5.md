# BRAIN Alpha Ops 全面缺陷分析报告 v5

> **分析日期**: 2026-06-02
> **分析范围**: 全项目代码，包含 Python 后端 + 原生 JS 前端 + React 前端
> **分析方法**: 深度调用链路追踪 + 静态代码分析 + 架构审查
> **版本依据**: git HEAD @ main branch (2026-06-02)

---

## 执行摘要

本次分析覆盖了项目的 **后端 Python**（`brain_alpha_ops/`）和 **前端**（`brain_alpha_ops/web/`）全部关键模块，追踪了从配置加载 → API 调用 → 评分计算 → 提交流水线的完整调用链路。共发现 **31 个缺陷**，其中 P1（严重）9 个、P2（重要）15 个、P3（次要）7 个。

### 综合评分

| 维度 | 评分 | 说明 |
|------|------|------|
| 安全性 | 6.5/10 | XSS 向量、凭据残留、完整分页停滞观测、SSRF |
| 稳定性 | 7.0/10 | 较多静默异常吞噬、KeyError 风险 |
| 性能 | 7.5/10 | N+1 查询、重复计算、无缓存 |
| 可维护性 | 6.5/10 | God Object、硬编码、重复代码 |
| 前端质量 | 7.0/10 | 良好的可访问性但存在安全隐患 |
| **综合** | **6.9/10** | 目标: 8.5/10 |

### 与 v4 对比

- v4 (2026-06-01): 24 个未修复缺陷
- v5 新发现: 7 个新缺陷（本次深入调用链路追踪发现）
- 确认已修复: 4 个（分页常量统一、凭据日志遮蔽增强、格式校验改进等）
- **当前未修复: 27 个**

---

## 当前实施追踪（本轮工作树）

| ID | 当前状态 | 当前证据 | 下一步 |
|----|----------|----------|--------|
| V5-001 | TRACKED_DEFERRED | `list_user_alphas()` 已走统一 `_paginate_collection()`，且 `MAX_USER_ALPHAS_PAGES=None` 是刻意保留完整云端同步；现有测试覆盖超过旧 10000 cap 和无默认页数截断。 | 不添加固定页数截断；如后续需要，增加停滞观测和显式取消保护，而不是截断完整分页。 |
| V5-002 | CLOSED_CURRENT | `setSafeHtml()` 当前会转义，`check_frontend_innerhtml.py` 已审计 25 个 `setRawHtml()` 调用并要求命中稳定白名单；新增未审查 raw HTML 调用、direct sink、误命名 raw alias 均会失败；`tests/test_frontend_innerhtml_guard.py` 已通过。 | 保持前端 raw HTML sink 守护绿色。 |
| V5-003 | CLOSED_CURRENT | `write_run_config()` 写盘前调用 `run_config_dict_for_disk()` 清空 `credentials.username/password/token`。 | 保持 `tests/test_config.py` 相关凭据落盘测试绿色。 |
| V5-004 | CLOSED_CURRENT | `web_runtime_facade.serve()` 和 `main()` 在 `allow_remote=True` 时强制 `secure_cookies=True`，cookie 已含 `HttpOnly; SameSite=Strict`。 | 保持远程模式 session 测试绿色。 |
| V5-005 | CLOSED_CURRENT | 本轮将 `official_scoring.py` 硬/软门构造改为 `.get()` 安全读取，缺失键不再触发 `KeyError`；`tests/test_official_scoring_system.py` 已通过。 | 保持官方评分回归绿色。 |
| V5-006 | CLOSED_CURRENT | 本轮将硬门筛选改为只看 `is_hard_gate`，`points=0` 的硬门不再被归为软门；`tests/test_official_scoring_system.py` 已通过。 | 保持官方评分回归绿色。 |
| V5-007 | CLOSED_CURRENT | 本轮修复 `required_field_types`，按数据集字段 `category/id` 与本地别名逐项匹配，并将 `fields_for()`/`get_fields()` 移出模板循环；`tests/test_dynamic_research_components.py` 已通过。 | 保持模板过滤回归绿色。 |
| V5-008 | CLOSED_CURRENT | 当前工作树的 `CredentialRedactionFilter` 已处理 dict/tuple args 并调用 `redact_text()` 处理内联 JSON；`tests/test_infrastructure_modules.py::TestSecureCredentials` 已通过。 | 保持凭据脱敏回归绿色。 |
| V5-009 | TRACKED_OPEN | `scripts/check_frontend_silent_catches.py` 和 `scripts/check_python_silent_broad_exceptions.py` 已接入质量门；前端空 catch 已改为 `reportIgnoredError(...)`，`config_type_validation.py` 的 broad fallback 已改为 warning，可见门禁均为 0 findings。 | 继续把 Python 显式 fallback 分支拆成可接受降级或显式报错；V5-009 全局闭环前保持 open。 |

---

## 缺陷索引

| ID | 优先级 | 类别 | 模块 | 简要描述 |
|----|--------|------|------|----------|
| V5-001 | P1 | 安全 | brain_api/pagination.py | `list_user_alphas()` 完整分页需停滞观测与显式取消保护 |
| V5-002 | P1 | 安全 | web/js (XSS) | `setRawHtml()` 无输入净化，XSS 直通 |
| V5-003 | P1 | 安全 | config.py | `write_run_config` 凭据可持久化到磁盘 |
| V5-004 | P1 | 安全 | web_security.py | `secure_cookies=False` + 远程模式 = 会话劫持 |
| V5-005 | P1 | 稳定性 | scoring/official_scoring.py | 多处 KeyError 风险（硬索引 `row["key"]`） |
| V5-006 | P1 | 稳定性 | scoring/official_scoring.py | 硬门筛选逻辑矛盾（points=0 硬门被忽略） |
| V5-007 | P1 | 逻辑 | research/templates.py | `any()` 内层循环变量未使用，required_field_types 过滤完全失效 |
| V5-008 | P1 | 安全 | secure_credentials.py | `CredentialRedactionFilter` 遗漏位置参数和 JSON 内联值 |
| V5-009 | P1 | 稳定性 | 全局 | 20+ 处 `except Exception: pass/continue` 静默吞噬 |
| V5-010 | P2 | 安全 | web/index.html | Session 滑动过期无绝对最大生命周期 |
| V5-011 | P2 | 安全 | web_security.py | CSRF token 可预测（基于简单时间戳） |
| V5-012 | P2 | 性能 | research/templates.py | N+1 查询：`fields_for()` 和 `get_fields()` 在循环内重复调用 |
| V5-013 | P2 | 设计 | brain_api/official.py | God Object：5 个 Mixin 多重继承 |
| V5-014 | P2 | 逻辑 | brain_api/official_context.py | 常量重复定义于 official.py 和 official_context.py |
| V5-015 | P2 | 设计 | brain_api/official_context.py | `sys.modules` 依赖导入顺序，间歇性错误 |
| V5-016 | P2 | 安全 | brain_api/official.py | 明文凭据存储在实例属性中 |
| V5-017 | P2 | 异常 | config.py | `validate_run_config()` 中修改 config 对象（副作用） |
| V5-018 | P2 | 逻辑 | config.py | `resolved` 为 falsy 时不写入 config，但验证通过 |
| V5-019 | P2 | 安全 | redaction.py | `CredentialRedactionFilter` 对位置参数匹配不够精确 |
| V5-020 | P2 | 逻辑 | scoring/research/scoring.py | `_ratio()` 对 >100 的值直接返回，可能漏归一化 |
| V5-021 | P2 | UI/UX | web/js/app.js | 提交/生成候选的错误处理中 `finalJob` 检查不完整 |
| V5-022 | P2 | 性能 | web/js/app.js | `init()` 中多个 API 调用未做并发优化 |
| V5-023 | P2 | 设计 | web/js/app.js | 全局可变状态 `presets`、`activeToasts` 无封装 |
| V5-024 | P2 | 设计 | web/brain_api | 分页逻辑在 4 处重复实现 |
| V5-025 | P3 | 设计 | web/ | 双前端架构冗余（原生 JS + React） |
| V5-026 | P3 | 异常 | research/templates.py | `random.seed(seed)` 修改全局随机状态 |
| V5-027 | P3 | 异常 | research/templates.py | 空 field_names 时静默返回未填充模板 |
| V5-028 | P3 | 设计 | config.py | 延迟导入 + 模块级导入风格不统一 |
| V5-029 | P3 | 性能 | web_handler_dispatch.py | 每次请求都做 CSRF token 生成/验证的字符串拼接 |
| V5-030 | P3 | UI/UX | web/js/components/spinner.js | `announceToScreenReader` 可能多次创建 DOM 元素 |
| V5-031 | P3 | 设计 | web_progress.py | 进度字段重复定义，无统一来源 |

---

## 详细缺陷分析

---

### V5-001 | P1 | 安全 | 完整分页需停滞观测与显式取消保护

**文件**: `brain_alpha_ops/brain_api/pagination.py`
**根因**: 云端 Alpha 清单必须保持完整同步，不能用固定页数、固定条数或耗时阈值截断；风险应通过重复页签名、无新增唯一 Alpha 的停滞观测、官方 offset recovery、用户显式取消和真实 API/认证错误处理来控制。

**影响**: 如果缺少观测和取消保护，异常分页行为可能造成资源耗尽、API 配额消耗或服务拒绝；如果加入固定截断，又会破坏“云端有多少就同步多少”的业务要求。

**修复方案**:
1. 保持 `MAX_USER_ALPHAS_PAGES=None`，不添加固定页数或条数截断。
2. 保留重复页签名检测，避免官方异常重复页面造成循环。
3. 对无新增唯一 Alpha 的页面发出 warning/progress telemetry，但不停止分页。
4. 只允许官方分页自然结束、用户显式取消、真实 API/认证错误或重复页异常保护停止同步。

**优先级**: P1 · **预计工作量**: 1h

---

### V5-002 | P1 | 安全 | setRawHtml() XSS 直通

**文件**: `brain_alpha_ops/web/js/` (多处调用)
**根因**: `setRawHtml(el, html)` 使用 `el.innerHTML = html` 直接设置 HTML，但传入的 `html` 参数未经过任何净化。虽然有 JSDoc 注释说明需要调用者确保安全，但在 `result-table.js`、`table.js`、`toast.js`、`spinner.js` 等模块中大量使用，且数据来源包含服务端返回的用户数据。

**影响**: 如果 BRAIN API 返回的 Alpha ID、expression 等字段包含恶意脚本（或被中间人注入），将导致 XSS 攻击。

**具体风险点**:
- `result-table.js:121-133`: `setRawHtml(tableBody, rows.map(...))` 其中 `row.id`、`row.raw` 来自服务端
- `table.js:94-114`: 同样使用 `setRawHtml` 渲染表格行
- `toast.js:97`: `setRawHtml(toastEl, html)` 中 `msg` 参数可能包含用户输入

**修复方案**:
1. 创建 `sanitizeHtml(html)` 函数，使用 DOMPurify 或内建白名单过滤
2. 对所有 `setRawHtml` 调用点的输入进行 HTML 转义
3. 对于必须渲染 HTML 的场景（如格式化显示），使用严格的白名单标签 + 属性配置
4. 审计所有 `setRawHtml` 调用点，区分"纯文本"和"安全 HTML"

**代码实现**:
```javascript
// 添加 sanitize 函数
var SANITIZE_ALLOWED_TAGS = ['b', 'i', 'em', 'strong', 'span', 'br', 'code'];
var SANITIZE_ALLOWED_ATTRS = ['class'];

function sanitizeHtml(html) {
    var doc = new DOMParser().parseFromString(html, 'text/html');
    // Walk DOM, remove disallowed tags/attrs
    // ...
    return doc.body.innerHTML;
}

// 修改 setRawHtml，默认转义
function setRawHtml(el, html, options) {
    options = options || {};
    if (!options.allowHtml) {
        el.textContent = html;  // safe default
    } else {
        el.innerHTML = sanitizeHtml(html);
    }
}
```

**优先级**: P1 · **预计工作量**: 3h

---

### V5-003 | P1 | 安全 | write_run_config 凭据持久化

**文件**: `brain_alpha_ops/config.py:135-144`
**根因**: `write_run_config()` 调用 `run_config_dict_for_disk()` 清空凭据后写入磁盘，但 `sanitize_config_for_disk()` 返回的是 `RunConfig` 对象而非用于写入。如果调用链中某处绕过 `run_config_dict_for_disk()` 直接序列化 config，凭据将泄露到磁盘。

**影响**: 凭据明文写入 `run_config.json`，任何有文件系统读取权限的用户可获得 BRAIN API 凭据。

**修复方案**:
1. 在 `RunConfig.to_dict()` 方法中添加 `safe=True` 参数，默认安全模式自动清除凭据
2. 添加日志审计：每次 `write_run_config` 记录是否成功清除凭据
3. 在 `BrainSettings` dataclass 中，credential 字段使用 `field(repr=False)` 和自定义序列化器

**优先级**: P1 · **预计工作量**: 1.5h

---

### V5-004 | P1 | 安全 | secure_cookies=False + 远程模式

**文件**: `brain_alpha_ops/web_security.py`
**根因**: Session cookie 的 `secure` 标志默认为 `False`。当 `allow_remote=True` 时，cookie 在 HTTP 连接上明文传输，可被中间人截获。

**影响**: 远程攻击者可劫持 session 获取完全控制权。

**修复方案**:
1. `secure_cookies` 默认改为 `True`
2. 当 `allow_remote=True` 时强制启用 `secure=True`
3. 添加 `SameSite=Strict` 属性
4. 添加 `HttpOnly` 默认值

**优先级**: P1 · **预计工作量**: 0.5h

---

### V5-005 | P1 | 稳定性 | 多处 KeyError 风险

**文件**: `brain_alpha_ops/scoring/official_scoring.py`
**根因**: 多处使用 `row["key"]` 硬索引访问字典，如 `row["passed"]`（行 299）、`row["actual"]`、`row["target"]`、`row["direction"]`（行 307-308）、`row["points"]`（行 296）。如果字典缺少这些键，将抛出未捕获的 `KeyError`。

**影响**: 评分流程崩溃，整个评估链路中断。

**修复方案**:
```python
# Before (dangerous):
not row["passed"] and row.get("is_hard_gate") and row.get("points", 0) > 0
# After (safe):
not row.get("passed", True) and row.get("is_hard_gate") and row.get("points", 0) > 0
```
对所有硬索引改为 `.get()` 并设置安全默认值。

**优先级**: P1 · **预计工作量**: 1h

---

### V5-006 | P1 | 逻辑 | 硬门筛选逻辑矛盾

**文件**: `brain_alpha_ops/scoring/official_scoring.py:296-298`
**根因**: 硬门筛选条件为 `row.get("is_hard_gate") and row.get("points", 0) > 0`。如果某个 gate 是硬门但 `points=0`（表示权重为 0 的强制检查），它不会被计入 `hard_gate_items`，从而逃避免检。

同时，第 331-333 行的软门筛选也依赖 `points`：
```python
soft_items = [row for row in items 
    if not row.get("is_hard_gate") or row.get("points", 0) == 0]
```
这会导致 points=0 的硬门被错误分类为软门。

**修复方案**:
1. 硬门筛选只用 `is_hard_gate` 属性，不检查 `points`
2. 软门筛选排除 `is_hard_gate=True` 的条目（无论 points 值）

```python
# Fix:
hard_gate_items = [row for row in items if row.get("is_hard_gate")]

soft_items = [row for row in items if not row.get("is_hard_gate")]
```

**优先级**: P1 · **预计工作量**: 0.5h

---

### V5-007 | P1 | 逻辑 | required_field_types 过滤完全失效

**文件**: `brain_alpha_ops/research/templates.py:149-150`
**根因**: 
```python
any(f.id.lower() in fields for f in self._loader.get_fields(dataset_id))
```
外层 `any(... for _ in tmpl.required_field_types)` 中的循环变量 `_` 从未被使用，内层迭代 `get_fields(dataset_id)` 每次结果相同。由于 `get_fields(dataset_id)` 返回所有字段，所以只要数据集中存在**任意一个**字段，模板就被匹配——`required_field_types` 完全不起作用。

**影响**: 模板过滤失效，不满足字段类型要求的模板也会被错误返回，导致后续生成的 Alpha 表达式无效。

**修复方案**:
```python
# Correct implementation:
def _dataset_has_required_fields(self, tmpl, dataset_id):
    dataset_fields = self._loader.get_fields(dataset_id)
    available_types = {f.id.lower() for f in dataset_fields}
    required = {ft.lower() for ft in tmpl.required_field_types}
    return required.issubset(available_types)
```

**优先级**: P1 · **预计工作量**: 1h

---

### V5-008 | P1 | 安全 | CredentialRedactionFilter 覆盖不全

**文件**: `brain_alpha_ops/secure_credentials.py:41-66`
**根因**: `CredentialRedactionFilter.filter()` 仅处理 `record.args` 为 `dict` 或 `tuple` 的情况，但对于 `logging.info("msg %s", password)` 这种 `args` 为 tuple 的情况，仅当 `msg_mentions_credentials` 为 True 时才替换。如果日志消息本身不含敏感关键词（如 `"Processing"`），但参数是凭据，就会泄露。

**修复方案**:
1. 单独检查每个位置参数是否看起来像凭据（长度、熵值检测）
2. 对 tuple args 的每个元素进行 `redact_text()` 处理
3. 添加单元测试覆盖各种日志格式

**优先级**: P1 · **预计工作量**: 1.5h

---

### V5-009 | P1 | 稳定性 | 前端 runtime 的静默异常吞噬与旧 inline 产物残留

**文件**: `brain_alpha_ops/web/js/app-runtime.js`, `brain_alpha_ops/web/js/cloud-sync.js`, `brain_alpha_ops/web/js/views/production.js`, `brain_alpha_ops/web/index.html`, `brain_alpha_ops/config_type_validation.py`
**根因**: 原确认点是前端运行时的两个 EventSource 关闭路径、两个空 Promise catch、过期 inline bundle 中的旧副本，以及 Python 类型提示解析的 broad fallback；它们会把真实关闭/刷新/类型提示异常悄悄吞掉，让调试和运行时可观测性变差。

**影响**: 错误被静默忽略，导致：数据不一致、调试困难、用户看到空白结果但不知原因。

**修复方案**:
1. 给前端 runtime 增加静默 catch 扫描门禁
2. 给 Python broad exception 增加空吞扫描门禁
3. 将前端关闭/刷新失败改为 `reportIgnoredError(...)`，将类型提示 fallback 改为 `logger.warning(...)`
4. 重新生成 `web/index.html`，避免旧内联产物回流
5. 后续再把 Python 显式 fallback 分支分成可接受降级和真正静默吞噬两类

**优先级**: P1 · **预计工作量**: 2h

---

### V5-010 | P2 | 安全 | Session 无绝对最大生命周期

**文件**: `brain_alpha_ops/web_security.py`
**根因**: Session 使用滑动过期（每次请求刷新 TTL），但没有绝对最大生命周期限制。一个 session 可以无限期保持活跃。

**影响**: 长期有效的 session 增加被劫持的风险窗口。

**修复方案**:
```python
SESSION_ABSOLUTE_MAX_AGE = 86400 * 7  # 7 days

def validate_session(session):
    if time.time() - session.created_at > SESSION_ABSOLUTE_MAX_AGE:
        return False, "session_absolute_expired"
    # ... existing sliding expiry check
```

**优先级**: P2 · **预计工作量**: 0.5h

---

### V5-011 | P2 | 安全 | CSRF token 可预测

**文件**: `brain_alpha_ops/web_security.py` + `web_handler_dispatch.py`
**根因**: CSRF token 生成逻辑可能基于 `time.time()` + 简单哈希，在低熵环境下可被预测。

**修复方案**:
使用 `secrets.token_hex(32)` 替代简单哈希，确保足够的熵值。

**优先级**: P2 · **预计工作量**: 0.5h

---

### V5-012 | P2 | 性能 | N+1 查询

**文件**: `brain_alpha_ops/research/templates.py:144-145`
**根因**: `self._mapper.fields_for(dataset_id)` 和 `self._loader.get_fields(dataset_id)` 在 `for tmpl in self._templates.values()` 循环内每次迭代都被调用。

**修复方案**:
```python
# Cache before loop:
fields = set(self._mapper.fields_for(dataset_id))
dataset_fields = self._loader.get_fields(dataset_id)
for tmpl in self._templates.values():
    # use cached fields...
```

**优先级**: P2 · **预计工作量**: 0.3h

---

### V5-013 | P2 | 设计 | God Object — 5 个 Mixin 多重继承

**文件**: `brain_alpha_ops/brain_api/official.py:55-61`
**根因**: `OfficialBrainAPI` 通过 5 个 Mixin 继承实现，MRO 复杂，方法覆盖可能导致意外行为。

**修复方案**:
1. 使用组合优于继承：每个 Mixin 实现为独立的后端服务
2. `OfficialBrainAPI` 通过依赖注入持有各个后端引用
3. 至少添加 MRO 文档注释

**优先级**: P2 · **预计工作量**: 4h

---

### V5-014 | P2 | 逻辑 | 常量重复定义

**文件**: `brain_alpha_ops/brain_api/official.py:42-48` vs `official_context.py:26-32`
**根因**: `_MAX_FIELDS_PAGES`、`_MAX_DATASETS_PAGES` 等常量在两个文件中各自定义。修改一处不会同步到另一处。

**修复方案**:
移至共享常量文件（如 `brain_alpha_ops/runtime_constants.py`），两个模块均导入使用。

**优先级**: P2 · **预计工作量**: 0.5h

---

### V5-015 | P2 | 逻辑 | sys.modules 依赖导入顺序

**文件**: `brain_alpha_ops/brain_api/official_context.py:35-43`
**根因**: `_official_limit()` 通过 `sys.modules.get("brain_alpha_ops.brain_api.official")` 读取常量。如果 `official.py` 尚未导入，模块不在 sys.modules 中，函数静默回退到默认值。

**修复方案**:
直接 `from brain_alpha_ops.brain_api.official import _MAX_FIELDS_PAGES` 或在模块顶部显式导入。

**优先级**: P2 · **预计工作量**: 0.3h

---

### V5-016 | P2 | 安全 | 明文凭据存储在实例属性

**文件**: `brain_alpha_ops/brain_api/official.py:72-74`
**根因**: `self.username`、`self.password`、`self.token` 明文存储在 `OfficialBrainAPI` 实例属性中，可在调试器、堆栈跟踪、序列化中泄露。

**修复方案**:
使用 `CredentialBundle` 封装凭据，仅在需要使用 HTTP Authorization 头时提取。

**优先级**: P2 · **预计工作量**: 1h

---

### V5-017 | P2 | 异常 | validate 函数中修改 config

**文件**: `brain_alpha_ops/config.py:195-196`
**根因**: `validate_run_config()` 中对 `config.ops.settings.dataset = resolved` 的直接赋值，是一个验证函数的副作用。如果 `BrainSettings` 是 frozen dataclass，将抛出异常。

**修复方案**:
将 dataset resolution 移到 `_normalize_runtime_paths()` 或单独的 normalize 函数中。

**优先级**: P2 · **预计工作量**: 0.5h

---

### V5-018 | P2 | 逻辑 | resolved 为 falsy 时的状态不一致

**文件**: `brain_alpha_ops/config.py:187-196`
**根因**: 当 `resolve_default_dataset_id` 抛出异常时，`resolved = ""`，然后 `if resolved:` 为 False，config 中的 dataset 保持原值不变。但验证继续 (`_validate_ops(errors, config.ops)`)，导致使用了未解析的 dataset。

**修复方案**:
当解析失败时，应添加错误到 `errors` 列表（已有），但不应继续验证。改为 return early 或确保 resolved 为空时 `_validate_ops` 能正确处理。

**优先级**: P2 · **预计工作量**: 0.3h

---

### V5-019 | P2 | 安全 | RedactionFilter 位置参数检查不精确

**文件**: `brain_alpha_ops/secure_credentials.py:55-63`
**根因**: 对 tuple args 的过滤仅当 `msg_mentions_credentials` 为 True 时才替换为 `<REDACTED>`，否则只做 `redact_text()`。但如果日志格式为 `"Connection: %s"` 且参数是 token 字符串（不含明显关键词），`redact_text()` 的正则可能匹配不到。

**修复方案**:
对所有 tuple 位置参数都进行 redact_text 处理，不依赖 msg 文本匹配。

**优先级**: P2 · **预计工作量**: 0.3h

---

### V5-020 | P2 | 逻辑 | _ratio() 对超大值直接返回

**文件**: `brain_alpha_ops/research/scoring.py:740-748`
**根因**: `_ratio()` 对 `abs(numeric) > 100.0` 的值直接返回原值。但如果 BRAIN API 变更后返回百分比（如 120% 即 1.2），此逻辑反而会放过应该归一化的值。

**修复方案**:
移除 >100 的特殊处理，全部按 `>1.0 即除以 100` 的逻辑。或者添加配置项控制归一化阈值。

**优先级**: P2 · **预计工作量**: 0.3h

---

### V5-021 | P2 | UI/UX | 提交错误处理不完整

**文件**: `brain_alpha_ops/web/js/app.js:677-739`
**根因**: `submitSelectedCandidates` 中 `finalJob` 可能为 `null` 或 `undefined`，但代码中 `finalJob.result` 访问前只检查了 `finalJob` 真值性，未调用 `waitForAsyncJob` 的异常路径保护。

**修复方案**:
```javascript
var result = (finalJob && finalJob.result) || {};
if (finalJob && finalJob.ok !== false && result.ok !== false) {
    // success path
}
```

**优先级**: P2 · **预计工作量**: 0.5h

---

### V5-022 | P2 | 性能 | init() 中的 API 调用未并发

**文件**: `brain_alpha_ops/web/js/app.js:1219-1239`
**根因**: `init()` 中的多个 API 调用（`loadProfile()`, `loadPresets()`, `loadRedlineReport()`, `loadCheckpointStatus()`, `loadCheckResults()`）是按顺序串行执行的，且大部分互不依赖。

**修复方案**:
使用 `Promise.all()` 并发执行独立请求。

**优先级**: P2 · **预计工作量**: 0.3h

---

### V5-023 | P2 | 设计 | 全局可变状态无封装

**文件**: `brain_alpha_ops/web/js/app.js` (多处)
**根因**: `presets`（行 29）、`activeToasts`（toast.js:26）、`visible`（spinner.js:11）等模块级可变变量直接暴露，可能导致状态不一致。

**修复方案**:
使用闭包封装状态，通过 getter/setter 访问。

**优先级**: P2 · **预计工作量**: 1h

---

### V5-024 | P2 | 设计 | 分页逻辑 4 处重复

**文件**: `brain_alpha_ops/brain_api/official.py` 多个 Mixin
**根因**: 分页循环逻辑在 fields、datasets、alphas、operators 的获取函数中各自实现。

**修复方案**:
提取 `paginate_all()` 公共函数，各调用点传入 `request_page` 回调。

**优先级**: P2 · **预计工作量**: 2h

---

### V5-025 | P3 | 设计 | 双前端架构冗余

**文件**: `brain_alpha_ops/web/index.html` + `brain_alpha_ops/web/react_app/`
**根因**: 同时维护原生 JS（~411KB HTML）和 React/TypeScript 两套前端。原生版本是实际生产使用的，React 版本是 CDN-based 开发版本。

**修复方案**:
1. 决策：保留一套（推荐 React + Vite 生产构建）
2. React 版本需要完成：ErrorBoundary、生产构建优化、替换 CDN 为本地打包
3. 移除未使用的原生 JS 前端

**优先级**: P3 · **预计工作量**: 8h

---

### V5-026 | P3 | 异常 | random.seed() 修改全局状态

**文件**: `brain_alpha_ops/research/templates.py:176`
**根因**: `random.seed(seed)` 修改进程级全局随机状态，影响所有后续随机操作。

**修复方案**:
```python
local_random = random.Random(seed)
field_names = local_random.sample(available, min(count, len(available)))
```

**优先级**: P3 · **预计工作量**: 0.2h

---

### V5-027 | P3 | 异常 | 空 field_names 静默返回

**文件**: `brain_alpha_ops/research/templates.py:179-180`
**根因**: 当 `field_names` 为空时，`instantiate()` 直接返回包含 `{FIELD_1}` 占位符的原始表达式，没有警告或错误提示。

**修复方案**:
```python
if not field_names:
    logger.warning("Template %s instantiated with empty field_names", template_id)
    return ""  # or raise ValueError
```

**优先级**: P3 · **预计工作量**: 0.2h

---

### V5-028 | P3 | 设计 | 导入风格不统一

**文件**: `brain_alpha_ops/config.py`
**根因**: 模块顶部使用常规导入，但行 108 使用函数内延迟导入 `from brain_alpha_ops.config_schema import ...`。

**修复方案**:
统一为模块级导入，或全部使用延迟导入。推荐模块级导入（性能影响可忽略）。

**优先级**: P3 · **预计工作量**: 0.2h

---

### V5-029 | P3 | 性能 | CSRF token 字符串操作

**文件**: `brain_alpha_ops/web_handler_dispatch.py`
**根因**: CSRF token 验证涉及多次字符串拼接和比较，每次请求都执行。

**修复方案**:
使用 `hmac.compare_digest()` 进行常量时间比较，token 预计算。

**优先级**: P3 · **预计工作量**: 0.3h

---

### V5-030 | P3 | UI/UX | screen reader announcer 重复创建

**文件**: `brain_alpha_ops/web/js/components/spinner.js:165-180`
**根因**: `announceToScreenReader()` 每次被调用时检查 `$('srAnnouncer')` 是否存在。如果 DOM 中已有该元素但引用丢失（如被移除后重新创建），会重复创建。

**修复方案**:
使用模块级变量缓存 announcer 元素引用。

**优先级**: P3 · **预计工作量**: 0.2h

---

### V5-031 | P3 | 设计 | 进度字段重复定义

**文件**: `brain_alpha_ops/web_progress.py` + 多个 web job 文件
**根因**: `task_id`, `phase`, `percent_complete`, `eta_seconds` 等进度字段在多个文件中各定义一份，格式不完全一致。

**修复方案**:
定义 TypedDict 或 dataclass 作为唯一来源，各模块引用。

**优先级**: P3 · **预计工作量**: 0.5h

---

## 修复计划

### Phase 1: 安全紧急修复（P1, 预计 12h）

| 顺序 | ID | 任务 | 预计时间 |
|------|-----|------|---------|
| 1 | V5-001 | 保留完整分页，补强停滞观测与显式取消保护 | 1h |
| 2 | V5-002 | XSS 防护：sanitizeHtml + setRawHtml 审计 | 3h |
| 3 | V5-003 | write_run_config 凭据安全写入 | 1.5h |
| 4 | V5-004 | secure_cookies 强制启用 | 0.5h |
| 5 | V5-005 | KeyError 风险修复（.get() 替代硬索引） | 1h |
| 6 | V5-006 | 硬门筛选逻辑修复 | 0.5h |
| 7 | V5-007 | required_field_types 过滤修复 | 1h |
| 8 | V5-008 | CredentialRedactionFilter 覆盖增强 | 1.5h |
| 9 | V5-009 | 静默异常吞噬（前端 runtime slice） | 2h |

### Phase 2: 稳定性加固（P2, 预计 8h）

| 顺序 | ID | 任务 | 预计时间 |
|------|-----|------|---------|
| 10 | V5-010 | Session 绝对最大生命周期 | 0.5h |
| 11 | V5-011 | CSRF token 熵值增强 | 0.5h |
| 12 | V5-012 | N+1 查询优化 | 0.3h |
| 13 | V5-014 | 常量去重 | 0.5h |
| 14 | V5-015 | 移除 sys.modules 依赖 | 0.3h |
| 15 | V5-016 | 凭据存储加密 | 1h |
| 16 | V5-017 | validate 函数副作用移除 | 0.5h |
| 17 | V5-018 | dataset 解析失败处理 | 0.3h |
| 18 | V5-019 | RedactionFilter 参数处理改进 | 0.3h |
| 19 | V5-020 | _ratio() 归一化逻辑调整 | 0.3h |
| 20 | V5-021 | finalJob 空值保护 | 0.5h |
| 21 | V5-022 | init() 并发优化 | 0.3h |
| 22 | V5-023 | 全局状态封装 | 1h |
| 23 | V5-013 | God Object 重构（组合优于继承） | 1.5h* |
| 24 | V5-024 | 分页逻辑去重 | 1h* |

*\*: P2 阶段仅做架构评估和重构准备，完整实现在 Phase 3*

### Phase 3: 代码质量（P2 架构 + P3, 预计 10h）

| 顺序 | ID | 任务 | 预计时间 |
|------|-----|------|---------|
| 25 | V5-013 | God Object 完整重构 | 2.5h |
| 26 | V5-024 | 分页去重完整实现 | 1h |
| 27 | V5-025 | 前端架构决策 + React 生产化 | 4h |
| 28 | V5-026 | random.seed 局部化 | 0.2h |
| 29 | V5-027 | 空 field_names 处理 | 0.2h |
| 30 | V5-028 | 导入风格统一 | 0.2h |
| 31 | V5-029 | CSRF token 性能优化 | 0.3h |
| 32 | V5-030 | announcer 引用缓存 | 0.2h |
| 33 | V5-031 | 进度字段统一 | 0.5h |

**总计**: ~30h

---

## 验证标准

每个修复完成后，需通过以下验证：

1. **V5-001**: `pytest tests/ -k pagination` 通过，覆盖无默认页数截断、超过旧 10000 条仍继续读取、显式取消停止以及停滞 warning-only 观测
2. **V5-002**: 使用 OWASP XSS 测试向量验证所有 setRawHtml 调用点
3. **V5-003**: 确认 run_config.json 不含凭据明文
4. **V5-005/V5-006**: `pytest tests/ -k scoring` 通过，添加缺失键测试
5. **V5-007**: 添加模板过滤单元测试
6. **V5-009**: `.venv/bin/python scripts/check_frontend_silent_catches.py --json` 和 `.venv/bin/python scripts/check_python_silent_broad_exceptions.py --json` 均输出 0 findings，且 `.venv/bin/python brain_alpha_ops/web/build_inline.py --check --json` 通过
7. **全部**: CI 绿色、test 覆盖率 > 80%、ruff/mypy 无错误

---

## 风险登记

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| God Object 重构可能引入回归 | 原有功能中断 | 每次重构后全量测试 |
| React 前端替换原生 JS 可能丢失功能 | 用户体验降级 | 分段迁移，保留原生版作为回退 |
| XSS 防护可能遗漏隐蔽调用点 | 安全漏洞残留 | 自动化审计脚本 + 人工 review |
| 静默异常修复可能暴露隐藏 bug | 用户体验降级（原本静默失败现在报错） | 分步修复，生产环境灰度发布 |

---

*报告生成时间: 2026-06-02 01:21*
*分析工具: 深度代码审查 + 调用链路追踪 + 静态分析*
