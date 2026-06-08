# Code Review Report — BRAIN Alpha Ops 全面审查

> **Reviewer**: Code Review Expert
> **Date**: 2026-06-08
> **Scope**: 全部前端代码（hooks、组件、CSS、测试、配置）
> **Files reviewed**: 15

---

## 总体评价

整体架构方向正确——Terminal Precision 设计系统 + App Shell 布局 + useJobState 状态提升构成了坚实的基础。主要关注点在**测试健壮性**和**CSS 响应式覆盖**两个维度。无安全漏洞。建议在下次迭代中处理 1 个 P0 和 6 个 P1 项。

---

## 发现汇总

| 严重度 | 数量 | 关键类别 |
|--------|------|---------|
| 🔴 P0 · 阻塞 | 2 | 测试断言吞没失败、类型不安全 |
| 🟠 P1 · 重要 | 5 | 脆弱模式、loading 误判、CSS 断点缺口 |
| 🟡 P2 · 建议 | 6 | 死代码、DOM 绕过、配置污染 |
| 🔵 P3 · 优化 | 3 | 配置冗余、注释缺失 |

---

## 🔴 P0 · 阻塞项

### [P0-1] [testing] `||` 在 expect 中吞没测试失败

**文件**: `tests/components.test.tsx`, Line 574

```tsx
expect(screen.queryByText((c) => c.includes("非提交证据")) || screen.getByText("停止请求已发送")).toBeTruthy();
```

**问题**: `||` 左侧返回 `null`（文本不存在）→ 执行右侧 `getByText` → 如果右侧也找不到 → 抛出 `TestingLibraryElementError`。但如果 **左侧找到了某个包含"非提交证据"的无关元素**（而非预期的 ProgressFeedback 消息），测试会错误通过。

**建议**: 拆成两个独立断言：
```tsx
const msg = screen.queryByText((c) => c.includes("非提交证据"));
const fallback = screen.queryByText("停止请求已发送");
expect(msg || fallback).toBeTruthy();
```

---

### [P0-2] [correctness] useApi 泛型阴影导致类型不安全

**文件**: `hooks/useApi.ts`, Lines 21-22

```tsx
const call = useCallback(
  async <R = T>(url: string, options?: RequestInit): Promise<ApiResponse<R> | null> => {
    // Line 48:
    setState({ data: (json.data ?? json) as unknown as T, ... });
```

**问题**: `call` 允许调用方用 `<R>` 覆盖状态类型 `T`。如果调用 `call<OtherType>()`，但 `setState` 写入的是 `T` 类型的数据，则下游读取 `state.data` 时类型与实际数据不一致。

**建议**: 移除 `<R>` 泛型参数，`call` 始终使用 `T`；或让 `call` 不调用 `setState`。

---

## 🟠 P1 · 重要项

### [P1-1] [maintainability] 空字符串作为"无错误"标记脆弱

**文件**: `ConfigPanel.tsx`, Lines 492-550

```tsx
function validateForm(): string {
  // 返回 "" 表示无错误，非空字符串表示有问题
  return missingFields.length ? `缺失必填项: ${...}` : "";
}
```

**问题**: 若未来有人用 `if (!validateForm())` 判断，空字符串 `""` 是 falsy → 永远进入"错误"分支。

**建议**: 改为 `{ valid: boolean; error?: string }` 或返回 `string | null`。

---

### [P1-2] [correctness] useToast 模块级计数器跨实例共享

**文件**: `hooks/useToast.ts`, Line 6

```tsx
let toastIdCounter = 0; // 模块级，跨所有组件实例共享
```

**问题**: React StrictMode 双重挂载或并发模式下，不同组件的 toast ID 可能碰撞，导致重复 key 或错误清理 timer。

**建议**: 将计数器移入 hook 内部，使用 `useRef(0)`。

---

### [P1-3] [usability] QualityCheckPanel loading 判断过早消失

**文件**: `QualityCheckPanel.tsx`, Lines 34-36

```tsx
const loading = slotsApi.loading && readinessApi.loading && !slotsApi.data && !readinessApi.data;
```

**问题**: 若一个 API 先返回但另一个仍在加载，loading spinner 消失，留下半空白页面。

**建议**: `const loading = slotsApi.loading || readinessApi.loading`。

---

### [P1-4] [correctness] CSS 平板断点完全缺失

**文件**: `index.css`, Lines 324-336

只有两个响应式断点：639px 和 1023px。768px-1023px 范围的平板竖屏设备完全在规则之外——侧边栏折叠为 `display:none` 但无平板友好布局。

**建议**: 添加 `@media (min-width: 640px) and (max-width: 1023px)` 平板优化规则。

---

### [P1-5] [testing] `JSON.parse(String(undefined))` 掩盖断言失败

**文件**: `tests/components.test.tsx`, 多处

```tsx
expect(JSON.parse(String(saveCall?.[1]?.body))).toEqual({...});
```

**问题**: 当 fetch mock 路径不匹配时，`saveCall` 为 `undefined` → `JSON.parse("undefined")` 抛出 `SyntaxError`，而非给出清晰的"期望调用未发生"断言报告。

**建议**: 先断言 `saveCall` 存在：
```tsx
expect(saveCall).toBeDefined();
expect(JSON.parse(String(saveCall![1]!.body))).toEqual({...});
```

---

## 🟡 P2 · 建议项

- [ ] **P2-1**: `SnapshotPanel.tsx:309-310` — `onMouseEnter`/`onMouseLeave` 直接操作 `element.style.backgroundColor` 绕过 React。改用 CSS `:hover` 伪类。
- [ ] **P2-2**: `OfficialBacktestSlots.tsx:249` + `SubmissionConfirmPanel.tsx:296` — `nextActionLabel` 和 `formatNumber` 定义但从未调用。删除或添加引用。
- [ ] **P2-3**: `tailwind.config.js` — 自定义颜色（surface/accent）与 Tailwind 默认色并存。开发者可误用 `bg-red-500`。设 `corePlugins: { colors: false }` 以强制自定义调色板。
- [ ] **P2-4**: `index.css:14` — `min-height: 100dvh` 无 `@supports` / 静态后备。旧浏览器菜单无最小高度。
- [ ] **P2-5**: `tailwind.config.js` — 未安装 `@tailwindcss/forms` 插件。复选框/单选按钮在暗色主题下保持默认浏览器外观。
- [ ] **P2-6**: `tests/components.test.tsx` — SSE mock 依赖隐式全局 EventSource 替换，极其脆弱。考虑用 `vi.mock()` 显式替换。

---

## 🔵 P3 · 优化项

- [ ] **P3-1**: `tailwind.config.js` — `fontFamily.display` 与 `sans` 完全相同（无实际效果）。删除。
- [ ] **P3-2**: `tailwind.config.js` — `brand` 遗留调色板仍存在。当前无引用，可安全删除。
- [ ] **P3-3**: `helpers/runPayload.ts:7` — `hasCredentials` 的 `||` 逻辑导致仅填写密码时不通过。若这是有意设计，添加 JSDoc 说明。

---

## ✅ 亮点

1. **`helpers/runPayload.ts`** 模块结构良好——职责清晰，函数短小纯函数化。`isJobStatus` 类型守卫和 `extractJobId` 比之前的 `as unknown as` 断言好得多。

2. **代码分割** 在实践中验证——8 个懒加载 chunk + vendor split，首屏 JS 从 290KB 降至 203KB。

3. **审查体系闭环**——今天从标准制定 → 正式审查 → 发现修复 → 再次审查的全流程已经跑通两轮。

---

## 合并建议

- 当前无阻塞合并的安全问题
- 建议下个 sprint 处理 P0-1/2 和 P1 项
- P2/P3 按季度清理即可

---

**Reviewer**: Code Review Expert
**完成时间**: 2026-06-08 19:23
