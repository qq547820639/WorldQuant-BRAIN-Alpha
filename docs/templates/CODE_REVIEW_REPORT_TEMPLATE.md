# Code Review Report

> **Reviewer**: &lt;姓名&gt;
> **Date**: &lt;YYYY-MM-DD&gt;
> **PR**: #&lt;PR 编号&gt; · [标题]
> **Author**: &lt;提交者&gt;
> **Files Reviewed**: &lt;数量&gt; files (+&lt;新增行&gt; / -&lt;删除行&gt;)

---

## 总体评价

&lt;一句话总结代码质量、主要关注点和是否建议合并。&gt;

---

## 发现汇总

| 严重度 | 数量 |
|--------|------|
| 🔴 P0 · 阻塞 | X |
| 🟠 P1 · 重要 | X |
| 🟡 P2 · 建议 | X |
| 🔵 P3 · 优化 | X |

---

## 🔴 P0 · 阻塞项（必须修复才能合并）

&gt; 安全漏洞、数据丢失、生产崩溃风险

### [P0-1] [security/maintainability/performance/correctness] &lt;简短标题&gt;

**文件**: `path/to/file.tsx`, Line XX

**问题**: &lt;清晰描述问题&gt;

**风险**: &lt;不修复的后果&gt;

**建议**:
```diff
- 旧代码
+ 新代码
```

---

## 🟠 P1 · 重要项（强烈建议修复后合并）

&gt; 逻辑错误、内存泄漏、明显性能问题

### [P1-1] [category] &lt;简短标题&gt;
**文件**: `path/to/file.py`, Line XX
**问题**: ...
**建议**: ...

---

## 🟡 P2 · 建议项（可在后续 PR 中处理）

- [ ] **建议 1**: &lt;描述 + 理由&gt; — 文件: `path/file`, Line XX
- [ ] **建议 2**: ...

---

## 🔵 P3 · 优化项（可选，不阻塞合并）

- [ ] **命名优化**: &lt;当前名称&gt; → &lt;建议名称&gt;，因为 &lt;理由&gt;
- [ ] **注释补充**: `path/file` 的 `functionName()` 缺少 JSDoc
- [ ] ...

---

## ✅ 亮点

&lt;值得肯定的代码片段、设计决策、干净实现&gt;

1. **&lt;亮点标题&gt;**: &lt;描述&gt; — `path/file:line`

---

## 合并建议

- [ ] ✅ 修复 P0 后可以合并
- [ ] ⚠️ 建议修复 P0+P1 后合并
- [ ] ❌ 建议重写 / 重构（原因: ...）

---

## 后续追踪

| Issue | 描述 | 优先级 |
|-------|------|--------|
| #XXX  | &lt;追踪事项&gt; | P1/P2 |

---

**Reviewer 签字**: &lt;姓名&gt;
**完成时间**: &lt;YYYY-MM-DD HH:mm&gt;
