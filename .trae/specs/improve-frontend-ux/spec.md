# 用户体验改进规格

## 为什么
当前 BRAIN Alpha Ops 的用户界面体验存在明显问题：加载缓慢、布局混乱、反馈不清晰、错误处理不友好，亟需系统性改进以提升用户满意度。

## 什么变化
- 优化前端加载性能，减少白屏时间
- 改进 Dashboard 和 ConfigPanel 的布局与对齐
- 增强错误提示和加载状态的视觉反馈
- 改善表格和卡片的可读性
- 优化移动端响应式布局
- 添加骨架屏和进度指示器
- 改进空状态和错误状态的展示

## 影响
- 受影响的规格：用户体验与交互
- 受影响的代码：
  - `/workspace/brain_alpha_ops/web/react_app/src/components/Dashboard.tsx`
  - `/workspace/brain_alpha_ops/web/react_app/src/components/ConfigPanel.tsx`
  - `/workspace/brain_alpha_ops/web/react_app/src/components/StateCards.tsx`
  - `/workspace/brain_alpha_ops/web/react_app/src/components/CandidateTable.tsx`
  - `/workspace/brain_alpha_ops/web/react_app/src/components/ScoringPanel.tsx`
  - `/workspace/brain_alpha_ops/web/react_app/src/components/OfficialBacktestSlots.tsx`
  - `/workspace/brain_alpha_ops/web/react_app/src/hooks/`
  - `/workspace/brain_alpha_ops/web/react_app/src/index.css`

## 新增需求
### 需求：骨架屏加载状态
系统必须提供骨架屏（Skeleton）组件，用于页面加载时的视觉占位。

#### 场景：Dashboard 加载
- **WHEN** Dashboard 数据正在加载时
- **THEN** 应显示骨架屏，而不是空白或闪烁

### 需求：进度指示器
系统必须在执行耗时操作时显示明确的进度指示。

#### 场景：API 请求进行中
- **WHEN** 发起 API 请求时
- **THEN** 应显示加载动画或进度条

### 需求：空状态友好展示
系统必须在数据为空时显示有意义的提示，而不是空白区域。

#### 场景：候选池为空
- **WHEN** 候选列表为空时
- **THEN** 应显示友好的空状态提示和引导操作

### 需求：统一错误处理展示
系统必须在发生错误时显示统一的错误卡片，包含错误信息、原因分析和重试按钮。

#### 场景：API 请求失败
- **WHEN** API 请求返回错误时
- **THEN** 应显示错误卡片，包含可操作的重试按钮

## 修改的需求
### 需求：Dashboard 布局优化
#### 场景：桌面端显示
- **WHEN** 在桌面端浏览器中访问 Dashboard 时
- **THEN** 卡片应正确对齐，间距均匀，不出现溢出

### 需求：ConfigPanel 表单布局
#### 场景：配置表单显示
- **WHEN** 配置面板加载完成时
- **THEN** 表单字段应正确对齐，标签清晰，输入框宽度一致

### 需求：候选表格可读性
#### 场景：候选列表展示
- **WHEN** 候选列表有大量数据时
- **THEN** 表格应支持横向滚动，列宽合理，信息层次清晰

### 需求：评分面板可解释性
#### 场景：评分详情展示
- **WHEN** 查看 Alpha 评分详情时
- **THEN** 评分卡片应清晰展示分数、排名和归因，图标和颜色语义明确

### 需求：回测槽位状态可视化
#### 场景：回测状态展示
- **WHEN** 查看回测槽位状态时
- **THEN** 应以卡片形式清晰展示每个槽位的状态、进度和剩余时间

## 技术约束
- 保持响应式设计，支持移动端（最小 375px 宽度）
- 保持无障碍访问（ARIA 标签、键盘导航）
- 保持 Tailwind CSS 样式一致性
- 保持 TypeScript 类型安全
