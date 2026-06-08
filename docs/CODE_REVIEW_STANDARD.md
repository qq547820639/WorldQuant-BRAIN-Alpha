# BRAIN Alpha Ops — 代码审查标准 v1.0

> 本文档定义团队代码审查的完整标准：分类体系、严重度定义、各语言专项检查、审查流程、输出模板。
>
> 配套文件：[CODE_REVIEW_CHECKLIST.md](./CODE_REVIEW_CHECKLIST.md)（操作检查清单）
>
> 最后更新：2026-06-08 · Code Review Expert

---

## 一、审查目标

一次好的代码审查应该同时做到：

| 维度 | 核心问题 |
|------|---------|
| **正确性** | 代码是否实现了预期功能？边界情况是否覆盖？ |
| **安全性** | 是否有注入点、认证绕过、数据泄漏？ |
| **可维护性** | 6 个月后，新同事能否理解并修改这段代码？ |
| **性能** | 是否有明显的瓶颈（N+1 查询、大循环、不必要分配）？ |
| **测试** | 关键路径是否被测试？失败场景是否覆盖？ |

审查不是挑刺，而是作为**第一读者**帮助作者发现他们可能忽略的问题。

---

## 二、问题分类体系

### 2.1 五维分类

每个 review comment 必须标注所属维度：

| 标签 | 维度 | 典型场景 |
|------|------|---------|
| `correctness` | 正确性 | 逻辑错误、边界情况遗漏、状态不一致 |
| `security` | 安全性 | 注入、XSS、信息泄露、权限缺失 |
| `maintainability` | 可维护性 | 命名不清、重复代码、缺少注释、架构混乱 |
| `performance` | 性能 | N+1 查询、不必要渲染、大文件未分割 |
| `testing` | 测试 | 测试缺失、断言无效、Mock 不真实 |

### 2.2 严重度定义

| 级别 | 标识 | 含义 | 阻塞合并？ |
|------|------|------|-----------|
| **P0 · 阻塞** | 🔴 | 安全漏洞、数据丢失、生产崩溃 | ✅ 必须 |
| **P1 · 重要** | 🟠 | 逻辑错误、内存泄漏、测试失败 | ✅ 必须 |
| **P2 · 建议** | 🟡 | 不良模式、缺少测试、可读性问题 | ❌ 建议 |
| **P3 · 优化** | 🔵 | 命名优化、注释补充、风格微调 | ❌ 可选 |

### 2.3 判定规则

- **安全类问题自动 P0**：SQL 注入、XSS、任意用户输入未校验等
- **错误处理缺失自动 P1**：网络请求无超时、异常被吞没等
- **无测试不阻塞但强烈建议**：核心业务逻辑至少需要一个测试用例
- **命名 / 格式问题 P3**：只要不影响运行正确性

---

## 三、按语言的专项审查

### 3.1 TypeScript / React 前端

#### P0 必查项
```typescript
// ❌ 安全：dangerouslySetInnerHTML 直接使用用户输入
<div dangerouslySetInnerHTML={{ __html: userInput }} />

// ❌ 类型：any 类型逃逸
const parse = (data: any): any => data.value;

// ❌ 内存泄漏：useEffect 无 cleanup
useEffect(() => {
  const timer = setInterval(() => fetch(), 2000);
  // 缺少: return () => clearInterval(timer);
}, []);

// ❌ 竞态：未处理过期请求
useEffect(() => {
  fetch(`/api/user/${id}`).then(setUser);
}, [id]); // 如果 id 快速变化，后到达的响应可能覆盖正确的
```

#### 正确的写法
```typescript
// ✅ useEffect cleanup + AbortController
useEffect(() => {
  const controller = new AbortController();
  fetch("/api/data", { signal: controller.signal })
    .then(res => res.json())
    .then(data => { if (!controller.signal.aborted) setData(data); });
  return () => controller.abort();
}, []);

// ✅ 条件渲染的 loading / error / empty 三态
if (loading) return <Spinner />;
if (error) return <ErrorBanner message={error} onRetry={refetch} />;
if (!items.length) return <EmptyState />;
return <DataTable items={items} />;
```

#### React 专项检查清单

| 检查项 | 严重度 |
|--------|--------|
| 列表渲染有唯一 `key` prop | 🔴 P0 |
| useEffect 有 cleanup 函数 | 🔴 P0 |
| 异步请求有 AbortController | 🟠 P1 |
| 纯展示组件使用 `React.memo` | 🟡 P2 |
| 回调 props 使用 `useCallback` | 🟡 P2 |
| 派生值使用 `useMemo` | 🟡 P2 |
| 无 `eslint-disable` 注释 | 🟠 P1 |

#### TypeScript 类型安全检查

| 检查项 | 严重度 |
|--------|--------|
| 无 `any` 类型使用（除非有注释说明理由） | 🟠 P1 |
| 无 `as unknown as T` 双重断言 | 🟠 P1 |
| API 响应有明确的 interface 定义 | 🟠 P1 |
| 无 `@ts-ignore` 或 `@ts-expect-error` | 🟡 P2 |

---

### 3.2 Python 后端

#### P0 必查项
```python
# ❌ 安全：格式化字符串构建 SQL
cursor.execute(f"SELECT * FROM alphas WHERE id = '{alpha_id}'")

# ❌ 异常：裸 except 吞没所有异常
try:
    process_alpha(alpha_id)
except:
    pass  # 不知道发生了什么

# ❌ 输入：未验证的用户输入直接使用
def delete_alpha(alpha_id: str):
    os.remove(f"/data/{alpha_id}.json")  # 路径遍历风险
```

#### 正确的写法
```python
# ✅ 参数化查询
cursor.execute("SELECT * FROM alphas WHERE id = %s", (alpha_id,))

# ✅ 区分异常类型
try:
    process_alpha(alpha_id)
except ValidationError as e:
    return json_error(e.code, str(e), 400)
except Exception:
    logger.exception("unexpected error processing alpha %s", alpha_id)
    return json_error("INTERNAL", "内部错误", 500)

# ✅ 输入验证
import re
def delete_alpha(alpha_id: str):
    if not re.match(r'^[a-zA-Z0-9_-]{1,64}$', alpha_id):
        raise ValidationError("invalid alpha_id format")
```

#### Python 专项检查清单

| 检查项 | 严重度 |
|--------|--------|
| 无裸 `except:` 或 `except Exception:` | 🔴 P0 |
| 日志使用 `logger.exception()` 而非 `traceback.print_exc()` | 🟠 P1 |
| 用户输入有格式校验和长度限制 | 🔴 P0 |
| 文件/路径操作防止目录遍历 | 🔴 P0 |
| 函数签名使用类型提示 | 🟡 P2 |
| 无 `# type: ignore` 注释 | 🟡 P2 |
| 单文件不超过 500 行 | 🟡 P2 |

---

## 四、审查流程

### 4.1 角色定义

| 角色 | 职责 | 频率 |
|------|------|------|
| **Author**（提交者） | 自查清单完成 → 写清晰 PR 描述 → 响应 review 意见 | 每 PR |
| **Reviewer**（审查者） | 按标准审查 → 标注严重度 → 在 24h 内完成首轮 | 每 PR |
| **Lead Reviewer**（主审查者） | 争议裁决 → 最终批准合并 | 按需 |

### 4.2 审查节奏

| PR 规模 | 预期审查时间 | SLA |
|---------|-------------|-----|
| 小型（<50 行，1-3 文件） | 15-30 分钟 | 24h 内完成 |
| 中型（50-200 行，3-7 文件） | 30-60 分钟 | 24h 内完成 |
| 大型（>200 行，7+ 文件） | 分多次审查，建议先拆 PR | 48h 内完成首轮 |

**原则**：如果 PR 超过 400 行，先问"能否拆成两个 PR？"

### 4.3 审查流程

```
Author                          Reviewer
  |                                |
  | 1. 完成自查清单                |
  | 2. 填写 PR 模板                |
  | 3. 提交 PR                     |
  |------------------------------->|
  |                                | 4. 阅读 PR 描述
  |                                | 5. 按标准逐维审查
  |                                | 6. 标注问题 + 严重度
  |<-------------------------------|
  | 7. 处理 P0/P1（必须）          |
  | 8. 处理 P2/P3（视情况）        |
  | 9. 回复每个 comment            |
  |------------------------------->|
  |                                | 10. 验证修改
  |                                | 11. 批准合并
  |<-------------------------------|
  | 12. 合并到主分支                |
```

### 4.4 争议解决

当 Author 和 Reviewer 对某个问题有不同意见时：

1. **先看是否有现有规范** → 查阅本文档和 `CODE_REVIEW_CHECKLIST.md`
2. **讨论时间不超过 15 分钟** → 超过则升级到 Lead Reviewer
3. **Lead Reviewer 最终裁定** → 记录决策到 ADR（架构决策记录）
4. **安全/P0 问题没有争议空间** → 必须修复

---

## 五、PR 模板

每个 PR 必须包含以下信息：

```markdown
## 做了什么
<!-- 一句话描述主要变更 -->

## 为什么这样做
<!-- 业务背景 / 技术决策原因 -->

## 改动文件
- `path/to/file.tsx` — 描述

## 验证方式
- [ ] TypeScript / mypy 类型检查通过
- [ ] 相关测试通过 (`npm test` / `pytest`)
- [ ] 手动测试：<测试步骤>
- [ ] 深色模式截图（前端 UI 变更时）
- [ ] 响应式测试：Mobile / Tablet / Desktop

## 自查清单
- [ ] 无 any / Any 类型逃逸
- [ ] 异常被正确处理（非吞没）
- [ ] 安全：无注入、无 XSS、输入校验
- [ ] 加载 / 错误 / 空三种状态均已处理
- [ ] 新功能有对应测试

## 风险点
<!-- 如果有需要 Reviewer 特别关注的部分 -->

## Related Issues
Closes #<issue-number>
```

---

## 六、Review 报告模板

正式审查（大型 PR / 重要里程碑）使用以下模板：

```markdown
# Code Review Report — [PR 标题]

**Reviewer**: [姓名]
**Date**: [日期]
**PR**: #[PR 编号]
**Files Reviewed**: [数量]

## 总体评价
<!-- 一句话总结：代码质量、主要关注点、是否建议合并 -->

## 发现汇总

| 严重度 | 数量 |
|--------|------|
| 🔴 P0 阻塞 | X |
| 🟠 P1 重要 | X |
| 🟡 P2 建议 | X |
| 🔵 P3 优化 | X |

## 🔴 P0 阻塞项（必须修复才能合并）

### [P0-1] [维度] 标题
**文件**: `path/to/file`, Line XX
**问题**: 具体描述
**风险**: 不修复的后果
**建议**: 如何修复

## 🟠 P1 重要项（建议修复后合并）

### [P1-1] ...
（同上格式）

## 🟡 P2 建议项
- [ ] 建议 1
- [ ] 建议 2

## ✅ 亮点
<!-- 值得肯定的代码片段或设计决策 -->

## 合并建议
- [ ] 修复 P0 后可以合并
- [ ] 修复 P0+P1 后可以合并
- [ ] 建议重写 / 重构

## 后续追踪
- [ ] Issue #XXX — 拆分大文件
- [ ] Issue #XXX — 补充集成测试
```

---

## 七、审查反模式（不要做）

| 反模式 | 为什么不好 | 正确做法 |
|--------|-----------|---------|
| "我觉得换个名字更好" 不给具体建议 | 让 Author 猜测 | "考虑用 `fetchCandidates`：更准确地描述返回的是候选列表" |
| 一次审查指出 30+ 个问题 | 压倒性，沮丧 | 分轮次：首轮 P0/P1，二轮 P2/P3 |
| 只批评不肯定 | 降低动力 | 每条 review 至少找一个值得肯定的点 |
| "你这样写不对" 不说原因 | 无法学习 | "这里有竞态风险，因为 fetch 可能乱序返回。建议用 AbortController" |
| 审查拖了 3 天 | PR 堆积，合并冲突 | P0/P1 必须在 24h 内给出首轮反馈 |

---

## 八、工具链集成

### 推荐配置

```yaml
# .github/workflows/pr-review.yml
name: PR Review Gate
on: [pull_request]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: TypeScript Check
        run: cd brain_alpha_ops/web/react_app && npm ci && npx tsc --noEmit
      - name: Lint Check
        run: cd brain_alpha_ops/web/react_app && npx eslint src/ --max-warnings 0
      - name: Unit Tests
        run: cd brain_alpha_ops/web/react_app && npx vitest run
      - name: Python Type Check
        run: mypy brain_alpha_ops/ --strict
      - name: Python Lint
        run: ruff check brain_alpha_ops/
```

### 自动检查项（CI 强制）

| 检查 | 工具 | 阻塞合并？ |
|------|------|-----------|
| TypeScript 类型 | `tsc --noEmit` | ✅ |
| ESLint | `eslint --max-warnings 0` | ✅ |
| 前端测试 | `vitest run` | ✅ |
| Python 类型 | `mypy --strict` | ✅ |
| Python Lint | `ruff check` | ✅ |
| 构建 | `vite build` / `python build_prod.py` | ✅ |

---

## 九、度量与改进

### 团队指标（按月跟踪）

| 指标 | 目标 |
|------|------|
| PR 首轮审查时间 | ≤ 24h（80% 分位） |
| PR 审查轮次 | ≤ 2 轮（70% 分位） |
| P0/P1 返修率 | < 15%（每 PR 平均 P0/P1 找到数） |
| 审查覆盖率 | 100% （每个 PR 至少 1 人审查） |

### 回顾与改进

- **每月回顾**：随机抽样 3 个已合并 PR，重新审查
- **季度回顾**：更新本文档，根据实际发现的问题补充检查项
- **知识共享**：将典型的 P0 问题匿名化后作为团队学习案例

---

**制定**: Code Review Expert
**版本**: v1.0
**下次审查**: 2026-09-08（季度回顾）
