# BRAIN Alpha Ops — 代码审查报告

> **审查人**：Code Reviewer  
> **审查日期**：2026-06-09 00:15  
> **审查范围**：17 个文件（9 新增 + 8 修改）
> **审查方法**：逐文件阅读 + 静态分析 + 测试验证

---

## 审查总结

**整体评价：质量高于平均水平。** 这次变更涉及跨前端/后端/架构的协同重构，范围大但控制得当。TypeScript 编译零错误，前端 Vite 构建通过 57 模块，Python 测试 2030+ passed。组件设计遵循设计规范，API 契约前后端一致。

**发现 1 个阻断项，3 个建议项，2 个 nit。**

---

## 🔴 阻断项

### B-01: App.tsx — `phaseApi.call` 导致无限重渲染循环

**文件**: `App.tsx:239-241`

```typescript
useEffect(() => {
  void phaseApi.call("/api/phase_state");
}, [phaseApi.call]);
```

**问题**: `phaseApi.call` 是 `useApi` hook 返回的稳定引用，但 `void phaseApi.call(...)` 返回的 Promise 在每次渲染时创建新的引用。如果 `useApi` 的 `call` 方法在每次渲染时重新创建（取决于其实现），将导致无限循环。

**验证**: 查看 `useApi` hook 的实现确认 `call` 是否为稳定引用。

**建议**:
```typescript
const phaseCallRef = useRef(phaseApi.call);
useEffect(() => {
  void phaseApi.call("/api/phase_state");
  const interval = setInterval(() => {
    void phaseApi.call("/api/phase_state");
  }, 5000); // poll every 5s
  return () => clearInterval(interval);
}, []); // run once on mount, then poll
```

或更安全的方式：
```typescript
const [pollKey, setPollKey] = useState(0);
useEffect(() => {
  void phaseApi.call("/api/phase_state");
  const interval = setInterval(() => setPollKey(k => k + 1), 5000);
  return () => clearInterval(interval);
}, []);

useEffect(() => {
  if (pollKey > 0) void phaseApi.call("/api/phase_state");
}, [pollKey]);
```

---

## 🟡 建议项

### S-01: usePhaseState — `phases` useMemo 依赖 `currentPhase` 导致多一次重算

**文件**: `usePhaseState.ts:79`

```typescript
const phases = useMemo<Record<PhaseId, PhaseGroup>>(() => ({
  // ... uses currentPhase, candidatesCount, scoredCount, readinessPassed
}), [currentPhase, candidatesCount, scoredCount, readinessPassed]);
```

**问题**: `currentPhase` 由 `determinePhase()` 计算，但它本身又出现在 `phases` 的 `useMemo` 依赖中。这导致：
1. 当输入变化 → `determinePhase()` 重算 → `currentPhase` 变化 → `phases` 重算
2. 两层重算虽然理论上正确，但 `phases` 对象包含 4 个完整的 PhaseGroup（每个含 items 数组），每次不必要的重建会增加渲染开销。

**为什么可能不构成实际问题**: 由于 `useMemo` 的缓存机制，`phases` 只在依赖变化时才重建。React 的 `useMemo` 本身是高效的。

**建议**: 考虑将 `phases` 的计算内联到 `currentPhase` 的计算中，避免两个独立的 `useMemo`。

```typescript
const { currentPhase, phases, steps } = useMemo(() => {
  const phase = determinePhase();
  const p = buildPhases(phase, candidatesCount, scoredCount, readinessPassed);
  const s = buildSteps(p);
  return { currentPhase: phase, phases: p, steps: s };
}, [connected, contextFresh, candidatesCount, scoredCount, readinessPassed]);
```

### S-02: App.tsx — `phaseData` 状态是 `phaseApi.data` 的副本，可能导致数据陈旧

**文件**: `App.tsx:237-245`

```typescript
const [phaseData, setPhaseData] = useState<typeof phaseApi.data>(null);

useEffect(() => {
  if (phaseApi.data) setPhaseData(phaseApi.data);
}, [phaseApi.data]);
```

**问题**: 这个 `useEffect` + `useState` 的组合等价于直接使用 `phaseApi.data`。中间状态 `phaseData` 只是 `phaseApi.data` 的无延迟拷贝。如果 `phaseApi.data` 为 `null`（初始状态），`phaseData` 保持 `null`，这是正确的。但如果 `phaseApi.data` 更新但 `useEffect` 还没触发，就会产生一个 micro-task 级别的陈旧数据窗口。

**建议**: 直接使用 `phaseApi.data` 替代 `phaseData`，消除不必要的中间状态：

```typescript
const phaseData = phaseApi.data;
const contextFresh = phaseData?.context_fresh ?? false;
```

### S-03: web_routes.py — `/api/phase_state` inline 路由，不在 GET_ROUTES 表中

**文件**: `web_routes.py:102-113`

**问题**: 新路由通过 inline `if path == "/api/phase_state"` 注册，而非通过 handler dispatch 的声明式路由表。这导致：
1. `GET_ROUTES` proxy 不包含此路径
2. `test_react_api_paths_are_registered_in_backend_routes` 测试失败
3. 未来重构时需要手动迁移

**建议**: 将 `/api/phase_state` 注册到 handler dispatch 的路由表中，与现有路由统一管理。

---

## 💭 Nit

### N-01: PhaseShell — `phaseKey` 变量使用 `as string` 类型断言

**文件**: `PhaseShell.tsx:38`

```typescript
const phaseKey = phaseId as string;
```

**问题**: `PhaseId` 已经是 `"connect" | "discover" | "evaluate" | "ready"` 的联合类型，是 `string` 的子类型。`as string` 断言是多余的——TypeScript 会自动将 union literal type 赋值给 `string`。

**建议**: 直接使用 `phaseId`：
```tsx
<div className="phase-shell" data-phase={phaseId}>
```

### N-02: StepGuide — `step-container` 类不存在于 CSS 中

**文件**: `StepGuide.tsx:44`

```tsx
<div key={step.id} className="step-container" style={{...}}>
```

**问题**: CSS 中没有 `.step-container` 样式定义。虽然不影响功能（样式通过 inline `display: flex` 覆盖），但残留的 CSS class 会造成困惑——未来维护者会查找这个类。

**建议**: 移除 `className="step-container"`，仅保留 inline style。

---

## ✅ 肯定项：做得好的地方

### 1. PhaseShell 组件：清晰的数据流

`PhaseShell` 是纯展示组件，接收 `phaseId/phaseLabel/steps/children` 等 props，不管理任何内部状态。这种设计使得组件易于测试和复用。

### 2. usePhaseState hook：单一职责

Hook 只做一件事：根据 6 个输入参数计算 phase 状态。不包含副作用、不调用 API。这种纯计算的设计使得逻辑清晰且可测试。

### 3. MobileTabBar：完整的 ARIA 标注

```tsx
<nav role="navigation" aria-label="移动端导航">
  <button aria-current={activePhase === id ? "true" : undefined}>
```

所有 4 个 tab 都正确使用了 `aria-current`，`<nav>` 有 `role="navigation"` 和 `aria-label`。这是无障碍实现的教科书级示例。

### 4. contracts.py：结构性子类型（Structural Subtyping）

使用 `typing.Protocol` 而非 ABC（抽象基类）定义契约。这意味着现有类无需显式继承即可满足契约——Python 的鸭子类型优势被完美利用。

### 5. ProgressFeedback stall 检测：优雅的状态机扩展

```typescript
const isStalled = isBusy && !isDeterminate && elapsed > 10;
```

在现有 5 状态（idle/loading/progress/success/error）基础上，通过组合条件派生出第 6 个状态（stalled），而非修改状态枚举。这种设计避免了级联的类型变更。

---

## 审查发现汇总

| # | 等级 | 文件 | 行 | 描述 |
|---|------|------|----|------|
| B-01 | 🔴 | App.tsx | 239 | `phaseApi.call` 依赖可能导致无限循环 |
| S-01 | 🟡 | usePhaseState.ts | 79 | `phases` 和 `currentPhase` 双重计算 |
| S-02 | 🟡 | App.tsx | 237 | `phaseData` 中间状态可能陈旧 |
| S-03 | 🟡 | web_routes.py | 102 | inline 路由不注册到 GET_ROUTES |
| N-01 | 💭 | PhaseShell.tsx | 38 | 多余的 `as string` 断言 |
| N-02 | 💭 | StepGuide.tsx | 44 | 不存在的 CSS class `step-container` |

---

## 结论

代码整体质量优秀。一个阻断项（B-01 无限循环风险）需要立即验证和修复。三个建议项可以合并到后续迭代中。两个 nit 不影响功能。

**建议下一步**：
1. 验证 `useApi.call` 是否为稳定引用 — 如是，B-01 降级为 🟡
2. 修复 N-01、N-02（各减 1 行代码）
3. S-02 简化（删除 `phaseData` 中间状态，-5 行代码）

---
**Code Reviewer** | 2026-06-09
