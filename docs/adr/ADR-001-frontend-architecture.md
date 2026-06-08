# ADR-001: 前端架构 — React SPA + 状态提升 + 代码分割

## Status
Accepted (2026-06-08)

## Context
BRAIN Alpha Ops 前端从卡片式导航（StateCards）迁移到侧边栏式 App Shell。在迁移过程中，我们发现两个核心架构问题：

1. **JobMonitor 的作业状态在页面导航时丢失** — 用户在 Dashboard 启动验证后切换到候选管理页面，进度完全消失。
2. **10 个页面视图全部在首屏加载** — 14 个组件 eager import，导致首屏 JS 290KB。

## Decision

### 1. 状态提升（useJobState hook）
- 将 `JobMonitor` 的核心状态（jobId、running、status、progress、events）提取为 `useJobState()` hook
- 在 `App.tsx` 层调用，子组件通过 props 共享
- JobMonitor 支持双模式：接收外部 `jobState`（受控模式）和独立维护内部状态（非受控，向后兼容测试）

**替代方案**：
- **React Context** — 引入后，所有子组件隐式依赖 context，测试需要 Provider 包裹。hook 方式更显式、更易测试。
- **Redux/Zustand** — 当前项目只有作业状态需要全局共享，引入状态管理库是过度工程。

### 2. 代码分割（React.lazy + Vite manualChunks）
- 非首屏页面（ScoringPanel、ConfigPanel、SnapshotPanel 等 7 个组件）使用 `React.lazy()`
- Dashboard、CandidateTable、JobMonitor 保持 eager（高频入口）
- Vite 构建配置 `manualChunks: { vendor: ["react", "react-dom"] }`

**结果**：首屏 JS 从 290KB → 203KB (↓30%)

### 3. 视图提取（JobMonitorView 纯展示组件）
- JobMonitor 的受控和非受控模式原本有 ~100 行重复 JSX
- 提取 `JobMonitorView` 纯展示组件，两种模式通过不同 props 传入

## Consequences

### What becomes easier
- **跨页面作业追踪** — 任何页面通过顶部栏 minibar 可以看到作业进度
- **新组件集成** — 只需在 switch 中添加 `lazy(() => import(...))` 即可懒加载
- **JobMonitor 维护** — UI 只在一处，修改即生效于两种模式

### What becomes harder
- **useJobState 的理解成本** — 新开发者需要理解 hook 返回的 `JobState` 接口（9 个字段）
- **Suspense 边界管理** — 每个 lazy 组件都需要正确的 Suspense 层级，错误放置会导致白屏

## References
- [React.lazy documentation](https://react.dev/reference/react/lazy)
- [Vite build rollupOptions](https://vitejs.dev/guide/build.html)
- 审查报告: `docs/reviews/REVIEW-2026-06-08-USEJOBSTATE.md`
