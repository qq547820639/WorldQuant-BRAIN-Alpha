# Code Review Report — 今日改动关键文件审查

> **Reviewer**: Code Review Expert
> **Date**: 2026-06-08
> **Scope**: App.tsx, Sidebar.tsx, Dashboard.tsx, JobMonitor.tsx, 测试文件
> **Files Reviewed**: 5 files (+970 / -800 lines net)

---

## 总体评价

整体代码质量良好，Terminal Precision 迁移的架构决策（Sidebar + Suspense + 代码分割）方向正确。主要关注点在**移动端 sidebar 的实现方式**和**几处遗漏的类型安全**。没有发现安全漏洞或数据丢失风险。建议在合并前修复 3 个 P0 项，其余可在后续迭代中处理。

---

## 发现汇总

| 严重度 | 数量 |
|--------|------|
| 🔴 P0 · 阻塞 | 3 |
| 🟠 P1 · 重要 | 2 |
| 🟡 P2 · 建议 | 4 |
| 🔵 P3 · 优化 | 3 |

---

## 🔴 P0 · 阻塞项（必须修复才能合并）

### [P0-1] [correctness] 移动端遮罩层 display:none 导致遮罩不可见

**文件**: `App.tsx`, Lines 346-357

**问题**: 移动端侧边栏遮罩（overlay）被设置为 `display: "none"`，导致在移动端点击汉堡菜单后，遮罩层不会显示，用户无法通过点击遮罩来关闭侧边栏。

**风险**: 侧边栏打开后在移动端无法通过点击外部区域关闭，只能点击导航项关闭。如果用户打开侧边栏后改变主意，会卡住。

**建议**:
```tsx
// ❌ 当前代码
style={{
  display: "none",  // 遮罩永远不会显示！
  position: "fixed", inset: 0, zIndex: 150,
  backgroundColor: "rgba(0,0,0,0.4)",
}}

// ✅ 修正
style={{
  position: "fixed", inset: 0, zIndex: 150,
  backgroundColor: "rgba(0,0,0,0.4)",
}}
// 不需要 display:none — 用 sidebarOpen 条件渲染已经控制可见性了
```

---

### [P0-2] [maintainability] 运行时注入 style 标签存在性能和可维护性风险

**文件**: `App.tsx`, Lines 358-361

```tsx
{sidebarOpen && (
  <style>{`@media(max-width:1023px){.app-sidebar{display:flex!important}}`}</style>
)}
```

**问题**: 
1. 每次 `sidebarOpen` 变化都会在 DOM 中插入/移除 `<style>` 标签，触发样式重计算
2. `!important` 是设计上的警示信号，说明 CSS 架构有缺陷
3. 这种模式在 React 中非常罕见，对后续维护者造成困惑

**建议**: 在 `index.css` 中已有的 `.app-sidebar.is-open` 规则基础上，在 JSX 中通过 class 控制：

```css
/* index.css — 已有的规则 */
@media (max-width: 1023px) {
  .app-sidebar { display: none; }
  .app-sidebar.is-open { display: flex; }
}
```

```tsx
// App.tsx — 修改 Sidebar 渲染
<Sidebar
  className={sidebarOpen ? "is-open" : ""}
  activeView={activeView}
  ...
/>
```

然后在 `Sidebar.tsx` 的根元素上应用 className prop。这消除了 style 标签注入，利用了已有的 CSS 规则。

---

### [P0-3] [maintainability] CARD_CONFIG 常量定义但未使用

**文件**: `App.tsx`, Lines 52-64

```tsx
const CARD_CONFIG: Record<string, { title: string; subtitle: string }> = {
  official_operations: { title: "官方操作", ... },
  dashboard: { title: "运行总览", ... },
  // ...10个条目
};
```

**问题**: 这个常量在重构后没有被任何地方引用。`VIEW_LABELS`（Lines 38-50）提供了简化的标题映射，而 `CARD_CONFIG` 中的 `subtitle` 字段完全未被使用。

**风险**: 中等 — 死代码增加了维护负担。如果有人修改了 `CARD_CONFIG` 期望它生效，会困惑为什么没有变化。

**建议**: 删除 `CARD_CONFIG`，或将其与 `VIEW_LABELS` 合并为一个统一的结构。

---

## 🟠 P1 · 重要项

### [P1-1] [maintainability] Sidebar 中两个 section 的 map 逻辑完全重复

**文件**: `Sidebar.tsx`, Lines 70-86 和 92-108

两段代码除了 `workflowItems` vs `toolItems` 外完全相同。如果后续需要修改导航项的渲染逻辑（如增加 tooltip、调整布局），需要改两处。

**建议**: 提取一个 `NavSection` 子组件：
```tsx
function NavSection({ items }: { items: NavItem[] }) {
  return items.map((item) => (
    <button key={item.id} type="button"
      onClick={() => { onNavigate(item.id); onClose?.(); }}
      className={`sidebar-nav-item${activeView === item.id ? " is-active" : ""}`}
      aria-current={activeView === item.id ? "page" : undefined}
    >
      ...
    </button>
  ));
}
```

---

### [P1-2] [testing] Dashboard 测试的加载态断言不足

**文件**: `tests/dashboard.test.tsx`, Lines 15-20

```tsx
it("shows loading state on initial render", async () => {
  const neverResolve = () => new Promise<Response>(() => {});
  vi.stubGlobal("fetch", vi.fn(neverResolve));
  render(<Dashboard notify={vi.fn()} />);
  // 仅断言了标题存在，没有断言 loading 指示器
  expect(screen.getByText("运行总览")).toBeInTheDocument();
});
```

**问题**: 测试名叫"显示加载状态"但只验证了标题存在。这个 `neverResolve` Promise 会导致测试永远不会自动结束（Promise 悬垂）——vitest 会在测试函数返回后继续等待。

**建议**: 
1. 添加具体的 loading 状态断言（如 spinner 存在或 "--" 占位符）
2. 使用 `vi.useFakeTimers()` 后 mock 延迟响应来控制加载状态，避免悬垂 Promise

---

## 🟡 P2 · 建议项

- [ ] **P2-1**: `App.tsx:259` — `detailContent` 使用 `let` 赋值模式。考虑改为 `useMemo` 返回 JSX，使 React 能正确追踪依赖并在 `activeView`/`selectedCandidate` 变化时仅重渲染相关部分。

- [ ] **P2-2**: `Sidebar.tsx:39` — `activeView` prop 类型包含 `| "cards"`，但 Sidebar 中从未处理 `"cards"` 值（因为现在没有 StateCards 了）。应从类型中移除 `"cards"`。

- [ ] **P2-3**: `new-components.test.tsx:78` — `"candidates" as CardViewId` 是不必要的类型断言。`"candidates"` 本身就是合法的 `CardViewId`。这暗示测试作者对类型系统不够信任——如果类型定义正确，不需要 as 断言。

- [ ] **P2-4**: `App.tsx:242-244` — `cloud` badge 使用了 IIFE（立即执行函数表达式）。虽然功能正确，但对于未来维护者来说可读性较差。建议提取为辅助函数 `formatCloudBadge(total?: number)`。

---

## 🔵 P3 · 优化项

- [ ] **P3-1**: `App.tsx:209` — `notify` 回调的 `action` 参数定义了但从未在任何调用中使用。如果确认不需要，可以简化签名；如果计划使用，建议在至少一个调用点启用。

- [ ] **P3-2**: `Sidebar.tsx:51` — `getBadge` 中对 `official_operations` 硬编码返回 `"web"`。考虑将其作为 NavItem 配置的一部分：`{ id: "official_operations", staticBadge: "web" }`。

- [ ] **P3-3**: `App.tsx:366` — Skip-to-content 链接的 `href="#main-content"` 指向自身所在的元素。应改为指向页面顶部或实际的第一个可交互内容区域。

---

## ✅ 亮点

1. **代码分割架构清晰**: `App.tsx` 的 eager/lazy 划分合理——Dashboard、CandidateTable 等高频页面保持 eager，低频页面全部 lazy。Suspense 边界位置正确（包裹整个 switch router）。

2. **Sidebar 设计简洁**: `NAV_ITEMS` 配置数组 + `getBadge` 映射函数的模式干净、声明式，添加新导航项只需一行。

3. **测试覆盖进展显著**: 从 1 个测试文件（29 tests）扩展到 3 个（42 tests），覆盖了之前零测试的 KpiCard 和 Sidebar 组件。Dashboard 的 error/happy-path 测试框架正确。

4. **TypeScript 类型追踪到位**: 所有 ESLint 禁用注释已移除，依赖数组正确声明。`useApi` hook 的泛型使用一致。

---

## 合并建议

- [x] ⚠️ **建议修复 P0-1 和 P0-2 后合并**（移动端 sidebar 功能修复）
- P0-3（死代码删除）和 P1 项可在合并后的下一个 PR 中处理

---

## 后续追踪

| Issue | 描述 | 优先级 |
|-------|------|--------|
| #TBD  | 移动端 sidebar 遮罩 + style 注入修复 | P0 |
| #TBD  | 删除 CARD_CONFIG 死代码 | P0 |
| #TBD  | 提取 Sidebar NavSection 子组件 | P1 |
| #TBD  | Dashboard 测试完善（loading 态断言） | P1 |

---

**Reviewer**: Code Review Expert
**完成时间**: 2026-06-08 18:02
