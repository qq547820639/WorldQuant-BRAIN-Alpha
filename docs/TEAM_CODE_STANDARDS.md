# BRAIN Alpha Ops — 团队编码规范与技术提升指南

> 资深开发工程师 · 2026-06-09

---

## 1. 路由安全模式 (Critical)

### 问题背景

项目从单文件 Web 控制台演进而来，历史上形成了三套路由系统：
- `web_handler_dispatch.py` — 新安全路由（有 Session/CSRF/Origin/Replay 四层校验）
- `web/__init__.py` — 旧 dispatch（无安全校验）
- `web_routes.py` — 独立路由（混合新旧）

### 正确做法

```python
# ✅ 正确：始终通过统一的安全 dispatch 入口
def do_POST(self):
    from brain_alpha_ops.web_handler_dispatch import dispatch_post
    dispatch_post(self, urlparse(self.path), ctx)

# ❌ 错误：直接在 Handler 中调用 handler 函数，绕过安全层
def do_POST(self):
    self._send_json(_real_generate(body))  # 无 session/origin/csrf 检查！
```

### 新增路由时的检查清单

- [ ] 在 `web_routes.py` 的 `_build_route_map()` 中添加路由定义（GET 或 POST）
- [ ] 设置正确的 `requires_session`（API 默认 True，session 创建和健康检查为 False）
- [ ] 在 `web_handler_dispatch.py` 的 `_GET_DISPATCH_HANDLERS` 或 `_POST_DISPATCH_HANDLERS` 中添加 handler
- [ ] 对于 POST 路由，使用 `@_validated_post_route` 装饰器添加 payload 验证
- [ ] 验证路由在所有三个入口 (`web/__init__.py dispatch_get/dispatch_post`, `web_handler_dispatch`) 都有安全覆盖

### 安全层执行顺序

```
请求 → Origin 校验 → Session 校验 → CSRF 校验 → Replay 检测 → Rate Limit → Payload 验证 → 业务逻辑
```

---

## 2. 错误处理规范

### 禁止的模式

```python
# ❌ 禁止：静默吞异常
try:
    critical_operation()
except Exception:
    pass  # 永远不要这样做！

# ❌ 禁止：暴露原始异常给前端
try:
    api_call()
except Exception as e:
    return {"ok": False, "error": str(e)}  # 可能包含敏感信息
```

### 正确做法

```python
# ✅ 正确：脱敏 + 记录 + 结构化返回
from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.errors import AppError, classify_error

try:
    result = critical_operation()
except Exception as exc:
    logger.error("critical_operation failed: %s", redact_error_message(exc))
    error_info = classify_error(exc, default_code="OPERATION_FAILED")
    return error_info.to_dict()
```

### 异常层次结构

```
AppError (base)
├── ValidationError (400)     — 输入参数不合法
├── AuthError (400)           — BRAIN API 认证失败
├── SessionError (403)        — Session 无效或过期
├── OriginForbiddenError (403)— 非本地请求源
├── NotFoundError (404)       — 资源不存在
├── SubmitBlockedError (400)  — 提交被安全门禁阻断
├── ConflictError (409)       — 资源冲突（同类型 job 运行中）
├── MissingOfficialIdError (400) — 缺少官方 Alpha ID
└── ContextRefreshError (500) — 上下文刷新失败
```

---

## 3. 凭据安全规范

### 凭据生命周期

```
解析(环境变量) → 使用(仅内存) → 脱敏(日志) → 销毁(不持久化)
```

### 规则

1. **永远不要**硬编码凭据（密码、token、API key）
2. **永远不要**在日志中打印凭据或认证响应体
3. **永远不要**将凭据写入配置文件或 JSON 存储
4. 凭据仅通过环境变量传入：`BRAIN_USERNAME`、`BRAIN_PASSWORD`、`BRAIN_TOKEN`
5. 所有异常消息在返回前必须经过 `redact_error_message()` 脱敏

```python
# ✅ 正确
from brain_alpha_ops.secure_credentials import resolve_credentials
creds = resolve_credentials()  # 从环境变量解析，自动脱敏日志

# ✅ 正确
logger.info("Auth result: %s", redact_error_message(auth_response))

# ❌ 错误  
logger.info("Auth result: %s", auth_response)  # 可能泄露 token
```

---

## 4. Session 与 CSRF 安全

### Session 创建

```python
from brain_alpha_ops.web_security import LocalSessionManager

# Session 用 secrets.token_urlsafe(32) 生成（256 位熵）
# CSRF token 和 Stream token 独立生成
# 超时：默认 12h，绝对上限 24h
```

### CSRF 验证流程

```
客户端 → 获取 CSRF token（从 / 返回的 HTML 中）→ 
  每次 POST 请求在 X-Brain-Alpha-CSRF 头中发送 → 
  服务端用 secrets.compare_digest() 常量时间比对
```

### Replay 防护

- 每个请求携带 `X-Brain-Alpha-Request-ID`（唯一 ID）
- 服务端在 5 分钟内拒绝重复 ID
- 缓存上限 10,000 条（防止内存耗尽）
- 请求时间戳必须在 ±5 分钟内

---

## 5. Rate Limiting 与 Payload 验证

### API 限速策略

| 桶 | 窗口 | 上限 |
|----|------|------|
| read | 1s | 60 请求 |
| write | 1s | 20 请求 |
| submit | 1s | 5 请求 |

桶自动按 HTTP 方法和路径分类。

### Payload 上限

| 参数 | 默认值 | 最大值 |
|------|--------|--------|
| 候选生成数 | — | 100 |
| 批量 Alpha ID | — | 100 |
| Assistant 文本 | — | 200,000 字符 |
| Alpha ID 长度 | — | 128 字符 |
| 请求体大小 | — | `WebDefaults.MAX_BODY_BYTES` |

---

## 6. 代码审查清单

### 每个 PR 必须检查

- [ ] 路由是否有完整的安全检查（Origin → Session → CSRF → Replay）？
- [ ] 异常是否被正确处理（分类 → 脱敏 → 记录 → 返回）？
- [ ] 日志中是否可能泄露凭据、token 或敏感数据？
- [ ] Payload 是否有类型/长度/范围验证？
- [ ] 是否有静默吞异常（`except: pass`）？
- [ ] 是否有死代码或不可达路径？
- [ ] 测试是否覆盖了新增路径和错误情况？
- [ ] 是否符合项目的错误码规范（`AppError` 层次结构）？

### 安全热点

以下文件/路径变更需要额外审查：
- `brain_alpha_ops/web_security.py` — 会话和认证
- `brain_alpha_ops/secure_credentials.py` — 凭据管理
- `brain_alpha_ops/web/__init__.py` — 旧路由 dispatch
- `brain_alpha_ops/web_handler_dispatch.py` — 新路由 dispatch
- `brain_alpha_ops/brain_api/official.py` — 官方 API 调用

---

## 7. 团队技能提升路线图

### 第一周：安全加固

- [x] 修复 R-01：旧 dispatch 安全绕过
- [x] 修复 R-02：路由表补全
- [x] 修复 R-03：Replay cache 容量限制
- [ ] 清理 web/__init__.py 死代码
- [ ] 修复 test_fetch_official_context.py 导入错误
- [ ] 使 119 个失败测试通过
- [ ] 添加 CI 自动安全检查

### 第二周：架构整洁

- [ ] 完全移除 `web/__init__.py` 中的旧 dispatch（迁移到 web_handler_dispatch）
- [ ] 统一 `_build_route_map()` 为唯一路由定义源
- [ ] 消除 `web_routes.py` 和 `web/__init__.py` 的功能重叠
- [ ] 模块化拆分 `web/__init__.py`（当前约 700 行 → 目标 200 行）

### 第三周：质量提升

- [ ] 为 web_handler_dispatch 添加完整的集成测试
- [ ] 为所有 POST 路由添加恶意 payload 测试
- [ ] 建立性能基准和回归测试
- [ ] 添加 Python 3.13 CI 矩阵
- [ ] 文档化所有路由的 API 契约

### 第四周：运维强化

- [ ] 结构化日志 + 可配置级别
- [ ] SSE 背压控制
- [ ] OPTIONS CORS 白名单对齐
- [ ] 依赖版本锁定（pip freeze → requirements.lock）
- [ ] 定期安全审计自动化

---

## 8. 常用代码片段

### 新建 API 端点模板

```python
# === 1. 在 web_routes.py 添加路由定义 ===
# POST_ROUTES 中添加：
#   "/api/new_endpoint": Route("new_endpoint"),

# === 2. 在 web_payload_validation.py 添加验证（如需要）===
def validate_new_endpoint_payload(payload: dict | None) -> str:
    error = validate_json_object_payload(payload)
    if error:
        return error
    # 自定义验证逻辑
    return ""

# === 3. 在 web_handler_dispatch.py 添加 handler ===
@_validated_post_route(validate_new_endpoint_payload, "NEW_ENDPOINT_ERROR")
def _post_new_endpoint(handler, _parsed, ctx, payload):
    result = ctx.do_something(payload)
    handler._json(result)

# === 4. 注册到 _POST_DISPATCH_HANDLERS ===
# "new_endpoint": _post_new_endpoint,
```

### 后台 Job 模板

```python
def start_background_job(job_id: str, payload: dict) -> None:
    """Pattern for long-running operations as background jobs."""
    from brain_alpha_ops.web_jobs import job_update
    from brain_alpha_ops.redaction import redact_error_message
    
    job_update(job_id, status="running", progress={"phase": "processing", "percent": 0})
    
    try:
        # 执行实际工作
        result = do_work(payload)
        job_update(job_id, status="completed", result=result, progress={"percent": 100})
    except Exception as exc:
        logger.exception("Background job %s failed", job_id)
        job_update(
            job_id,
            status="failed",
            error=redact_error_message(exc),
            progress={"percent": 100, "error": redact_error_message(exc)},
        )
```

---

*本指南将随项目演进持续更新。新成员入职时请先阅读本文档。*
