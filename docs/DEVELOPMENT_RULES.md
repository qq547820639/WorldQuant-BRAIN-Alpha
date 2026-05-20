# BrainAlphaOps 开发规范 v2.0

> 基于 2026-05-15 前后端全面重构沉淀的最佳实践。

---

## 一、架构原则

### 1.1 三层架构（铁律）

```
Controller (web.py HTTP handler)  →  只做：解析请求、调 Service、格式化响应
Service   (业务逻辑)               →  只做：规则判定、编排、事务管理
Repository (数据存取)              →  只做：文件读写、API 调用
```

**反模式**：Controller 中直接写 BRAIN API 调用 ❌

### 1.2 前端数据流

```
用户操作 → ApiClient → JSON Response → AppState.set() → Render
```

**反模式**：直接在事件回调中操作 DOM ❌

### 1.3 零硬编码原则

所有字段名、算子名、枚举值来源于：
- `data/official_fields.json`
- `data/official_operators.json`
- `config/presets.json`

**禁止**：在前端/后端散落硬编码的中文标签映射表。

---

## 二、后端规范

### 2.1 错误处理

**必须**使用 `brain_alpha_ops.errors` 异常类：

```python
from brain_alpha_ops.errors import ValidationError, SubmitBlockedError

if not candidate:
    raise ValidationError("Candidate not found")
if blocked:
    raise SubmitBlockedError("Alpha blocked by safety gate")
```

**必须**在所有 API handler 中返回 `error_code`：

```python
{"ok": False, "error_code": "VALIDATION_ERROR", "error": "details..."}
```

**禁止**：裸 `raise Exception("...")` 或 `return {"ok": False, "error": "..."}` 不带 error_code。

### 2.2 新功能添加清单

- [ ] 在 `errors.py` 中添加对应异常类（如需要新的 error_code）
- [ ] 在 web.py handler 中统一 JSON 响应格式
- [ ] 在 `api-client.js` 的 `ERROR_MESSAGES` 中添加用户消息
- [ ] 在新字段中附带 `phase_label`、`label_cn` 等中文字段
- [ ] `python -m py_compile` 验证

### 2.3 Progress 对象规范

所有 `progress` dict 必须包含：
```python
{
    "phase": "machine_readable_code",
    "phase_label": "中文阶段名",
    "current": int,
    "total": int,
    "percent": int,  # 0-100
    "message": str,
    "data": {}       # 运行时数据快照
}
```

### 2.4 文件管理

- `lifecycle.jsonl` > 50MB → 自动归档（`maybe_archive`）
- 所有 `.jsonl` 追加写入，不覆盖
- 缓存目录 `data/api_cache/` 不纳入版本控制

---

## 三、前端规范

### 3.1 模块组织

```
web/js/
├── api-client.js    # API 调用层（唯一出口）
├── state.js         # AppState 管理
├── utils.js         # 纯工具函数
├── app.js           # 初始化、事件绑定、render 调度
├── components/      # 可复用 UI 组件
│   ├── toast.js, spinner.js, modal.js, progress.js, table.js
└── views/           # 页面视图
    ├── detail.js, monitor.js, charts.js
```

### 3.2 添加新功能的流程

1. 在 `api-client.js` 添加 API 方法（如需要）
2. 在 `state.js` 添加状态字段
3. 在对应 `views/` 模块添加渲染函数
4. 在 `app.js` 添加事件绑定
5. 运行 `build_inline.py` 构建
6. `node --check` 验证语法

### 3.3 不引入新依赖

- ❌ 不引入 React/Vue/jQuery
- ❌ 不引入新的 CDN 脚本
- ✅ 使用 IIFE 命名空间模式
- ✅ 通过 `window.ApiClient` / `window.AppState` / `window.Utils` 通信

### 3.4 中文标签

- 后端字段 > 前端硬编码
- 优先使用 `progress.phase_label` 而非 `phaseName(phase)`
- 优先使用 `check.label_cn` 而非 `humanCheckName(name)`

---

## 四、API 契约

### 4.1 响应格式（统一）

```json
// 成功
{"ok": true, "...业务字段..."}

// 失败
{"ok": false, "error": "用户可读消息", "error_code": "MACHINE_CODE"}
```

### 4.2 错误码表

| error_code | HTTP | 含义 |
|-----------|------|------|
| `SESSION_INVALID` | 403 | 本地会话无效 |
| `ORIGIN_FORBIDDEN` | 403 | 非本地请求 |
| `VALIDATION_ERROR` | 400 | 参数校验失败 |
| `AUTH_FAILED` | 400 | BRAIN API 认证失败 |
| `CONFLICT_RUNNING` | 409 | 生产任务已在运行 |
| `CONFLICT_AUX_OP` | 409 | 同步/检查/提交冲突 |
| `JOB_NOT_FOUND` | 404 | 任务不存在 |
| `NOT_FOUND` | 404 | 资源不存在 |
| `MISSING_OFFICIAL_ID` | 400 | 缺少官方 Alpha ID |
| `SUBMIT_BLOCKED` | 400 | 提交被门禁阻断 |
| `INTERNAL_ERROR` | 500 | 内部错误 |

### 4.3 新增 API 检查清单

- [ ] 路由注册在 `do_GET` / `do_POST`
- [ ] Session 鉴权（`_path_requires_session`）
- [ ] error_code 在所有错误分支返回
- [ ] progress 对象含 `phase_label`
- [ ] `python -m py_compile` 验证

---

## 五、构建与发布

### 5.1 前端构建

```bash
cd brain_alpha_ops/web
python build_inline.py     # 将 js/*.js 内联到 index.html
```

### 5.2 验证命令

```bash
# Python 全量编译
python -m py_compile brain_alpha_ops/web.py
python -m py_compile brain_alpha_ops/research/*.py

# JS 语法检查（Windows PowerShell）
$html = Get-Content index.html -Raw
$js = [regex]::Matches($html, '<script[^>]*>([\s\S]*?)</script>') | %{ if($_ -notmatch 'src='){$_.Groups[1].Value} }
$js | Out-File temp.js; node --check temp.js

# JSON 校验
python -c "import json; json.load(open('config/presets.json'))"

# 敏感信息扫描
python scripts/scan_sensitive_artifacts.py
```

### 5.3 Windows 打包

```powershell
.\scripts\build_windows.ps1  # 包含 build_inline.py 步骤
```

---

## 六、禁止模式

| ❌ 禁止 | ✅ 替代 |
|--------|--------|
| Controller 中调 BRAIN API | 通过 Service/Repository |
| `raise Exception("...")` | `raise AppError subclasses` |
| `return {"ok": False}` 无 error_code | 加 `"error_code": "..."` |
| 前端 `phaseName()` 硬编码 | 后端 `progress.phase_label` |
| 前端 `humanCheckName()` 硬编码 | 后端 `check.label_cn` |
| 静默 `except: pass` | 至少 `logger.warning` |
| 前端裸 `fetch()` | `ApiClient.get/post()` |
| 全局 `let currentResult` | `AppState.set/get()` |
| `<script>` 直写 3000+ 行 | `build_inline.py` 构建 |
