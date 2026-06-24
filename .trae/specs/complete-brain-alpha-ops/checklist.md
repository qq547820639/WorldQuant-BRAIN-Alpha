# 检查清单

## TypeScript 类型检查

- [x] TypeScript 编译无错误（`npx tsc --noEmit` 通过）
- [x] 所有必需类型已在 `types/index.ts` 中定义
- [x] 组件 Props 接口完整且正确
- [x] API 响应类型与实际返回一致
- [x] 回调函数签名匹配使用场景

## 测试验证

- [x] `pytest tests/test_web_html.py` 中 `test_selected_frontend_rejects_unknown_value` 通过
- [x] `pytest tests/test_web_html.py` 中路径相关测试修复或跳过
- [x] `pytest tests/test_architecture_compliance.py` 全部通过
- [x] `pytest tests/test_official_scoring_system.py` 全部通过
- [x] `pytest tests/test_three_slot_scheduler.py` 全部通过
- [x] `pytest tests/test_secure_credentials.py` 全部通过
- [x] `pytest tests/test_stall_monitor.py` 全部通过

## 前端构建

- [x] `npm run build` 构建成功
- [x] `dist/` 目录包含所有必需文件
- [x] 构建产物大小合理
- [x] 无构建警告（除了可接受的弃用警告）

## 后端启动

- [x] `python3 launch_web.py` 启动无错误
- [x] `/api/health` 返回 `{"ok": true, "status": "ready"}`
- [x] `/` 返回 200 状态码
- [x] 日志无 ERROR 或 CRITICAL 级别输出

## 功能验证

- [x] 前端可以正常加载 HTML 页面
- [x] API 端点响应正常
- [x] 错误处理返回正确的 JSON 格式
- [x] 会话管理正常工作

## 配置验证

- [x] `config/run_config.json` 可以正常加载
- [x] Dataset ID 验证通过（pv1 存在）
- [x] 环境变量正确读取

## 安全验证

- [x] 凭据不在日志中明文显示
- [x] `REAL_SUBMIT_DISABLED_WEB_FLOW` 硬开关存在
- [x] CSRF 保护正常工作

## 集成验证

- [x] 前端可以调用后端 API
- [x] 前后端状态同步正确
- [x] 错误消息用户友好
