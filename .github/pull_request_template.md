## 做了什么

<!-- 一句话描述主要变更 -->


## 为什么这样做

<!-- 业务背景 / 技术决策原因 -->


## 改动文件

- `path/to/file.tsx` — 描述
- `path/to/file.py` — 描述


## 验证方式

- [ ] TypeScript / mypy 类型检查通过
- [ ] 相关测试通过
- [ ] 手动测试：<测试步骤>
- [ ] 深色模式截图（前端 UI 变更时）
- [ ] 响应式测试：Mobile (320px) / Tablet (768px) / Desktop (1024px+)


## 自查清单

### 类型安全
- [ ] 无 `any` / `Any` 类型逃逸
- [ ] 无 `as unknown as Type` 双重断言
- [ ] API 响应有明确类型定义

### 异常处理
- [ ] 无空的 `catch {}` 或裸 `except:`
- [ ] API 调用有加载/错误/空三态处理
- [ ] 异常被正确记录（logger / console.error）

### 安全
- [ ] 无 `dangerouslySetInnerHTML`
- [ ] 无硬编码凭证 / Token / 密钥
- [ ] 用户输入有格式校验和长度限制
- [ ] POST/PUT 请求有 CSRF 头

### 性能
- [ ] useEffect 有 cleanup 函数
- [ ] 非首屏组件使用 `React.lazy()` 懒加载
- [ ] 列表有分页或虚拟滚动

### 测试
- [ ] 新组件/函数有对应测试
- [ ] 覆盖了错误/加载/空三种状态的测试用例


## 风险点

<!-- 需要 Reviewer 特别关注的部分 -->


## Related Issues

Closes #
