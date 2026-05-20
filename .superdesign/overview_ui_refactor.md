# BRAIN Alpha Ops — 全链路 UI 重构总结

**日期**: 2026-05-15
**文件**: `brain_alpha_ops/web/index.html`
**QA 结果**: 91/91 PASS (100%)

---

## 变更概要

| 维度 | 重构前 | 重构后 |
|------|--------|--------|
| 主题 | 单一浅色 | Light/Dark 双主题 (oklch) |
| CSS 框架 | 纯手写 (~860行) | Tailwind CDN + 自定义 CSS 变量 |
| 设计系统 | 无 | 完整 Design Tokens (颜色/字体/间距/圆角/阴影/动画) |
| 字体 | 微软雅黑 | Satoshi + General Sans (专业量化终端) |
| 图标 | 无统一系统 | Lucide Icons (Iconify CDN) |
| 主题切换 | 不支持 | 固定按钮 + localStorage 持久化 + 系统偏好检测 |
| JS 业务逻辑 | 完整 | 完整保留，零变更 |
| 行数 | 4321 → 1665 | 紧凑化但功能无损 |

## 设计系统

### 颜色 (oklch)
- Light: teal #0f766e 主色调, 浅灰层级背景
- Dark: teal #14b8a6 主色调, 近OLED黑色背景
- 语义色: success/warning/danger/info 四色

### 字体
- Display: General Sans (标题/数字)
- Body: Satoshi (正文)
- Mono: JetBrains Mono (代码/数据)

### 布局
- Sidebar 360px + Main (CSS Grid)
- 响应式: <1120px 折叠侧栏, <720px 单列

## QA 验证 (91/91 PASS)

| 类别 | 检查项 | 结果 |
|------|--------|------|
| 结构完整性 | DOCTYPE, CDN, script平衡 | 7 ✓ |
| DOM ID | 46 个 ID 全部保留 | 46 ✓ |
| CSRF 安全 | 占位符 + API函数 | 3 ✓ |
| 主题系统 | IIFE + toggle + localStorage | 3 ✓ |
| CSS 功能类 | .hidden, .badge-* | 5 ✓ |
| 图表 | 4 Canvas 元素 | 4 ✓ |
| 函数清单 | 23 关键函数 | 23 ✓ |

## 关键技术决策
1. **单文件兼容**: 保持 `__BRAIN_ALPHA_OPS_CSRF_TOKEN__` 占位符不变
2. **CSS 变量桥接**: Tailwind config 扩展绑定到 CSS 自定义属性
3. **Dark 选择器**: `[data-theme="dark"]` 而非 Tailwind `dark:` 类
4. **零后端变更**: Python 服务器代码不变
5. **原文件备份**: `index_backup_20260515_*.html`

## 后续建议
- 可考虑在 Python 服务器端读取 HTML 中的主题选择并提前设置 data-theme（避免 FOUC）
- 图表颜色可进一步适配双主题（Chart.js 动态主题色）
