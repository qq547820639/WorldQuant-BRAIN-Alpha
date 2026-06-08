# BRAIN Alpha Ops — 团队技术提升路线图

> 资深工程师代码审查 · 2026-06-08 · 基于全栈审计结果

---

## 一、审计概览

| 维度 | 前端 | 后端 |
|------|------|------|
| 审计文件数 | 23 source + 1 test | 70+ source + 80+ test |
| P0 问题 | 2 | 4 |
| P1 问题 | 5 | 5 |
| P2 问题 | 10 | 4 |
| 得分 | 基础扎实，需性能/类型强化 | 安全优秀，需模块化/错误处理强化 |

---

## 二、P0 — 本周必修复

### P0-1：移除未使用依赖 recharts（前端）

- **文件**: `brain_alpha_ops/web/react_app/package.json`
- **问题**: `recharts` (~150KB gzip) 已安装但代码中零引用
- **影响**: Bundle 体积增加 150KB，首屏加载变慢
- **修复**: `npm uninstall recharts`

### P0-2：添加代码分割 / React.lazy 懒加载（前端）

- **文件**: `App.tsx`
- **问题**: 14 个组件全部在启动时加载，首屏 JS 290KB
- **修复**:
```tsx
const ScoringPanel = lazy(() => import("@/components/ScoringPanel"));
const ConfigPanel = lazy(() => import("@/components/ConfigPanel"));
// ...其余非首屏页面
```
- **预期**: 首屏 JS 减少 40-50%

### P0-3：修复过宽异常处理（后端）

- **文件**: `brain_alpha_ops/web.py` 及 `web_routes.py`
- **问题**: 30+ 处 `except Exception:` 吞没所有异常，丢失调用栈
- **修复**: 区分 `AppError`（已知业务异常）和未知异常，后者记录完整 traceback

```python
# ❌ 现在的写法
except Exception:
    traceback.print_exc()

# ✅ 推荐写法
except AppError as e:
    return error_response(e.code, str(e))
except Exception:
    logger.exception("unhandled error in route")
    return error_response("INTERNAL_ERROR", "内部错误")
```

### P0-4：拆分超大文件（后端）

- **文件**: `web_routes.py` (916行), `web_assistant_snapshots.py` (888行), `web_handler_dispatch.py` (798行)
- **策略**: 按资源拆分 → `routes/candidates.py`, `routes/config.py`, `routes/scoring.py`
- **阈值**: 单文件不超过 400 行

---

## 三、P1 — 本月必做

### 前端

| # | 问题 | 修复方法 |
|---|------|---------|
| P1-1 | CSRF token 暴露在 `window` 对象上 | 使用 `sessionStorage` 或模块闭包存储 token |
| P1-2 | 3 处 `eslint-disable react-hooks/exhaustive-deps` | 正确声明依赖数组，必要时使用 `useRef` 存储回调 |
| P1-3 | `useSSE` 和 `jobCancel` 有空 `catch {}` 丢错误 | 至少 `console.error()` 记录，或将错误返回给调用方 |
| P1-4 | `useApi` 双重 `as unknown as T` 类型转换 | 定义判别类型守卫函数 `isJobIdResponse(data)` |
| P1-5 | `SubmissionPanel` 中琥珀色文字在深色背景下不可读 | 替换为 `text-text-primary` 或 `text-warning` semantic token |

### 后端

| # | 问题 | 修复方法 |
|---|------|---------|
| P1-1 | `web.py` 使用 `traceback.print_exc()` | 改为 `logger.exception()` 统一日志 |
| P1-2 | 分发函数 `Any` 类型泛滥 | 为 handler 参数定义 Protocol / TypedDict |
| P1-3 | `web/` 目录为空 | 建立清晰模块层级：`web/routes/`、`web/middleware/`、`core/services/` |

---

## 四、P2 — 本季度优化

### 前端

| # | 建议 |
|---|------|
| P2-1 | 为 `Dashboard`, `Sidebar`, `KpiCard` 添加独立测试（目前 0 覆盖） |
| P2-2 | 添加 `@media (prefers-reduced-motion: reduce)` 包裹所有动画 |
| P2-3 | 添加 Skip-to-main-content 跳转链接 |
| P2-4 | Vite build 配置 `manualChunks` 拆分 vendor bundle |
| P2-5 | 17 个组件零 `React.memo` — 为 KpiCard, Badge, ProgressFeedback 添加 memo |

### 后端

| # | 建议 |
|---|------|
| P2-1 | `web_sqlite_indexes.py` 缓存 index 实例避免重复初始化 |
| P2-2 | 集中化 `load_run_config()` 调用，避免 7+ 处重复读取 |
| P2-3 | 为核心路由添加独立单元测试（`test_web_routes.py`） |

---

## 五、团队编码规范（强制执行）

### 5.1 TypeScript 规范

```typescript
// ✅ DO: 显式返回类型
function fetchCandidates(): Promise<Candidate[]> { ... }

// ✅ DO: 类型守卫替代 as 断言
function isJobResponse(data: unknown): data is { job_id: string } {
  return typeof data === "object" && data !== null && "job_id" in data;
}

// ❌ DON'T: 双重 as unknown as
const result = data as unknown as SomeType;

// ❌ DON'T: 禁用 eslint 规则
// eslint-disable-next-line react-hooks/exhaustive-deps
```

### 5.2 React 规范

```tsx
// ✅ DO: 为纯展示组件使用 memo
const KpiCard = memo(({ label, value }: Props) => { ... });

// ✅ DO: useEffect 中的 fetch 使用 AbortController
useEffect(() => {
  const controller = new AbortController();
  fetch("/api/data", { signal: controller.signal });
  return () => controller.abort();
}, []);

// ✅ DO: 大于 10KB 的页面用 lazy
const HeavyPanel = lazy(() => import("./HeavyPanel"));
```

### 5.3 Python 规范

```python
# ✅ DO: 使用 logger.exception 而非 traceback.print_exc
except Exception:
    logger.exception("failed to process alpha %s", alpha_id)

# ✅ DO: 区分已知异常和未知异常
except ValidationError as e:
    return json_error(e.code, str(e), 400)
except Exception:
    logger.exception("unexpected error")
    return json_error("INTERNAL", "请稍后重试", 500)

# ✅ DO: 函数签名使用类型提示
def process_alpha(alpha_id: str, config: RunConfig) -> AlphaResult: ...

# ❌ DON'T: 裸 Any 参数
def handler(data: Any) -> Any: ...
```

### 5.4 Git 提交规范

```
feat: 新功能      feat(candidates): 添加按 score 排序
fix:  修复        fix(job-monitor): 修复 SSE 重连计数错误
refactor: 重构    refactor(web): 拆分 web_routes 为独立模块
perf:  性能       perf(candidate-table): 虚拟滚动替换分页
test:  测试       test(scoring): 添加归因树边界测试
chore: 杂项       chore: 升级 TypeScript 到 5.5
```

---

## 六、CI/CD 流水线建议

### 当前缺失项

| 检查项 | 状态 | 建议 |
|--------|------|------|
| TypeScript strict mode | ❌ 缺失 | `tsconfig.json` 开启 `"strict": true` |
| ESLint pre-commit | ❌ 缺失 | 添加 `lint-staged` + `husky` |
| Lighthouse CI | ❌ 缺失 | PR 阻塞低于 90 分的 Performance/Accessibility |
| Bundle size 监控 | ❌ 缺失 | `vite-bundle-visualizer` 或 `@next/bundle-analyzer` |
| Python mypy strict | ❌ 部分 | `pyproject.toml` 中启用 `strict = true` |
| Python ruff pre-commit | ❌ 缺失 | `pre-commit` hook: `ruff check --fix` |

### 推荐 CI 配置 (.github/workflows/ci.yml)

```yaml
quality:
  - lint: ESLint + Prettier (前端) + Ruff (后端)
  - typecheck: tsc --noEmit (前端) + mypy (后端)
  - test: vitest (前端) + pytest (后端) -- 覆盖率 >= 80%
  - security: npm audit + pip-audit
  - build: vite build + python build_prod.py
performance:
  - lighthouse: Performance >= 90, Accessibility >= 95
  - bundlesize: JS main bundle < 200KB gzip
```

---

## 七、代码审查检查清单

### 每 PR 必查

- [ ] TypeScript/Python 类型安全，无 `any` / `Any` 逃逸
- [ ] 无 `eslint-disable` / `# type: ignore` 注释
- [ ] 错误/加载/空三种状态均已处理
- [ ] API 调用有 AbortController (前端) / timeout (后端)
- [ ] 新组件有对应测试文件
- [ ] UI 变更附带深色模式截图
- [ ] 无 console.log / print() 残留
- [ ] 无硬编码凭据/URL

### 每功能必查

- [ ] 无障碍: 键盘可导航、ARIA 正确、对比度达标
- [ ] 响应式: Mobile / Tablet / Desktop 三种断点均正常
- [ ] 性能: 无不必要的 re-render、无内存泄漏
- [ ] 安全: 无 XSS 载体、CSRF 正确处理

---

## 八、学习资源推荐

| 主题 | 资源 |
|------|------|
| React 性能 | [React 官方文档 - useMemo/useCallback](https://react.dev/reference/react) |
| TypeScript 进阶 | [TypeScript Deep Dive](https://basarat.gitbook.io/typescript/) |
| 无障碍 | [WebAIM WCAG 2 Checklist](https://webaim.org/standards/wcag/checklist) |
| Python 类型 | [mypy 文档 - Protocols](https://mypy.readthedocs.io/en/stable/protocols.html) |
| 错误处理 | [Python logging HOWTO](https://docs.python.org/3/howto/logging.html) |

---

**审查人**: Senior Developer (高级开发工程师)
**版本**: v1.0
**下次审查**: 2026-07-08（执行 P0 + P1 后复查）
