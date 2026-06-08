# Code Review Report — useJobState + JobMonitor 双模式实现

> **Reviewer**: Code Review Expert
> **Date**: 2026-06-08
> **Scope**: `hooks/useJobState.ts` (new, 211 lines), `components/JobMonitor.tsx` (modified, +90 lines), `App.tsx` (integration)
> **Context**: UX Phase 1 — 跨页面作业状态共享

---

## 总体评价

`useJobState` hook 的设计方向完全正确——将作业状态从组件本地提升到 App 层，解决了过去用户导航时"进度消失"的致命体验问题。SSE 流处理、轮询看门狗、自动中断逻辑准确移植了原有 JobMonitor 的所有保护机制。

主要关注点在 **JobMonitor 的双模式实现导致 100+ 行 UI 重复**，以及 **3 处 `as unknown as` 双重断言**的遗留问题。没有发现安全漏洞或数据损坏风险。

---

## 发现汇总

| 严重度 | 数量 |
|--------|------|
| 🔴 P0 · 阻塞 | 1 |
| 🟠 P1 · 重要 | 1 |
| 🟡 P2 · 建议 | 3 |
| 🔵 P3 · 优化 | 1 |

---

## 🔴 P0 · 阻塞项

### [P0-1] [maintainability] JobMonitor 中 UI 完全重复——受控模式与独立模式拥有两套相同的 JSX

**文件**: `JobMonitor.tsx`, Lines 18-108 (受控模式) vs Lines 150+ (独立模式)

**问题**: 当 `external` prop 存在时，组件返回一套完整的 JSX；不存在时返回另一套几乎完全相同的 JSX。现在有 **两套面板、两套 ProofMetric 网格、两套按钮组**需要同时维护。未来任何人修改 JobMonitor 的 UI，必须在两处同步。

**风险**: 这是经典的"fork-and-forget"反模式。三个月后的开发者修改了独立模式的 UI 样式，但不知道受控模式也需要同步修改——导致用户看到的界面不一致。

**建议**: 提取一个纯展示组件 `JobMonitorView`，两个模式都使用它：

```tsx
// 方案：提取公共视图
function JobMonitorView({ jobId, running, status, progress, error, events, ... }: ViewProps) {
  return <div className="panel mb-4">{/* 一套统一的 JSX */}</div>;
}

// 受控模式：直接传入
if (external) return <JobMonitorView {...external} credentialSource={...} />;

// 独立模式：用自己的 state 传入
return <JobMonitorView jobId={jobId} running={running} ... />;
```

当前合并条件：**修复后可合并**（功能正确，但建议本周内重构以避免维护债务累积）。

---

## 🟠 P1 · 重要项

### [P1-1] [correctness] `startJob` 中 `result` 为 null 时缺少错误处理

**文件**: `useJobState.ts`, Lines 137-150

```tsx
const jid = String((result as unknown as ...)?.job_id || "");
if (result?.ok && jid) {
  // success path
} else {
  setRunning(false);
  const message = result?.error || "启动验证流程失败";
  // error path
}
```

**问题**: 当 `api.call()` 因为网络错误返回 `null` 时（例如 fetch 超时），`result` 是 `null`。此时 `result?.ok` 是 `undefined`（falsy），进入 else 分支。但 `result?.error` 也是 `undefined`，所以 `message` 回退到通用字符串 "启动验证流程失败"。这掩盖了真实的网络错误信息。

**建议**: 在 else 分支中添加对 `result` 为 null 的显式检查：

```tsx
} else {
  setRunning(false);
  const message = result?.error || (!result ? "网络错误，请检查连接后重试" : "启动验证流程失败");
  ...
}
```

---

## 🟡 P2 · 建议项

- [ ] **P2-1**: `useJobState.ts:137,186,197` — 三处 `as unknown as Type` 双重断言。继承自原始 JobMonitor 代码。考虑在 `useApi` hook 中改进类型推导，或在独立的类型守卫文件中定义 `isJobStatus(data: unknown): data is JobStatus`。当前已通过 `tsc --noEmit` 验证，无运行时风险。

- [ ] **P2-2**: `useJobState.ts:61-66` — `progress` 对象在每次渲染时重新创建（非 `useMemo`）。这会导致 `JobState` 接口的 `progress` 引用每次渲染都变化，如果下游组件用 `React.memo` 并依赖 `progress` 会失效。考虑用 `useMemo` 包裹。

- [ ] **P2-3**: `useJobState.ts:89-115` — `handleSSEEvent` 依赖数组只有 `[notify]`，但内部使用了 `setPollFailures`、`setStatus`、`setRunning` 等。这些是 `useState` 返回的稳定 setter，React 保证不发生引用变化，所以当前实现正确。但注释说明此设计意图会有帮助。

---

## 🔵 P3 · 优化项

- [ ] **P3-1**: `useJobState.ts:38-45` — `runPayload` 函数与原始 JobMonitor.tsx 中完全一致。如果 JobMonitor 的独立模式仍需要此函数，考虑将其提取到共享模块 `helpers/runPayload.ts` 中。

---

## ✅ 亮点

1. **状态提升架构正确**: `useJobState` 的接口设计（`{ jobId, running, status, progress, error, connected, events, startJob, stopJob }`）清晰表达了作业的完整生命周期。App.tsx 的集成只需一行 `const jobState = useJobState(notify, credentials)`。

2. **SSE + Watchdog 双通道保护**: hook 内部同时维护了 SSE 实时流（`useSSE`）和 HTTP 轮询看门狗（`setInterval`），确保任一通道故障时另一通道可兜底。`WATCHDOG_MAX_FAILURES = 3` 的阈值合理。

3. **TopBar minibar 设计**: `jobState.running` 的存在让顶部栏可以随时显示作业进度，而不需要 Dashboard 页面必须在视图中。点击 minibar 跳回 Dashboard 的交互直观。

4. **向后兼容性保持**: JobMonitor 的 `jobState` 参数是可选的——不传时走独立模式，测试文件无需修改。

---

## 合并建议

- [x] ⚠️ **建议修复 P0-1（提取共同视图）后合并**
- P1-1 和 P2 项可在后续 PR 中处理

---

**Reviewer**: Code Review Expert
**完成时间**: 2026-06-08 19:12
