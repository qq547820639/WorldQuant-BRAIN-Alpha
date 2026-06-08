# BRAIN Alpha Ops — Code Review Checklist

> 每次 PR 提交前自查，Reviewer 使用此清单逐项验证

## 🔴 阻塞项 (PR 合并前 MUST)

### 类型安全
- [ ] 无 `any` 类型逃逸（前端 TypeScript）
- [ ] 无裸 `Any` 参数（后端 Python）
- [ ] 无 `as unknown as Type` 双重断言
- [ ] 无 `# type: ignore` 注释
- [ ] API 响应有明确的 interface/type 定义

### 异常处理
- [ ] 无空的 `catch {}` 块 — 至少 `console.error()` 记录
- [ ] 无 `except Exception:` 裸捕获 — 区分业务异常和系统异常
- [ ] 无吞没异常且不传播的情况
- [ ] API 调用有错误/加载/空三种状态处理

### 安全
- [ ] 无 `dangerouslySetInnerHTML`
- [ ] 无硬编码凭证、Token、密钥
- [ ] CSRF token 不在 window 对象上暴露
- [ ] 用户输入有长度限制和格式校验
- [ ] POST/PUT 请求有 CSRF 头

### 性能
- [ ] 无 `eslint-disable react-hooks/exhaustive-deps`
- [ ] useEffect 有 cleanup 函数 (AbortController / clearInterval)
- [ ] 列表/表格组件有分页或虚拟滚动
- [ ] 非首屏组件使用 `React.lazy()` 懒加载

### 测试
- [ ] 新组件/函数有对应测试文件
- [ ] 覆盖错误/加载/空三种状态的测试用例
- [ ] 无仅测试 happy path 的"假通过"测试

---

## 🟡 建议项 (PR 合并前 SHOULD)

### React 模式
- [ ] 纯展示组件使用 `React.memo`
- [ ] 回调 props 使用 `useCallback`
- [ ] 计算量大的派生值使用 `useMemo`
- [ ] 列表使用正确的 `key` prop

### 无障碍
- [ ] 装饰性 SVG 有 `aria-hidden="true"`
- [ ] 交互元素可通过键盘操作
- [ ] 表单输入有关联的 `<label>`
- [ ] 动态内容更新有 `aria-live` 区域
- [ ] 颜色不是唯一的信号载体（配合图标/文字）

### CSS / 设计
- [ ] 使用 `text-text-*` 等语义 token，不硬编码颜色
- [ ] 无 oklch() 裸色值在组件中（应通过 token 或 Tailwind 类）
- [ ] 断点测试: Mobile (320px) / Tablet (768px) / Desktop (1024px+)
- [ ] 动画包裹在 `@media (prefers-reduced-motion: reduce)` 中
- [ ] 深色模式截图已附在 PR 描述中

### Git
- [ ] commit message 遵循 `type(scope): description` 格式
- [ ] PR 描述说明了"做了什么" 和 "为什么这样做"
- [ ] 无合并冲突
- [ ] 无 `console.log` / `print()` 残留

---

## 🟢 优化项 (下个迭代可做)

- [ ] 组件有 JSDoc 注释说明用途和 props
- [ ] 大文件 (>300 行) 有拆分计划
- [ ] 旧代码有 TODO 标记和对应的 issue
- [ ] 性能瓶颈有 profiling 数据支持

---

**最后更新**: 2026-06-08 · Senior Developer
