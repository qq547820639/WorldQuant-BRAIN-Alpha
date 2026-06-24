# BRAIN Alpha Ops 对外产品升级 - 实施计划

## [x] Task 1: 错误边界与全局错误处理
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 创建 `ErrorBoundary` 组件，捕获组件渲染错误
  - 实现错误降级页面，包含错误说明、重试按钮、返回首页
  - 集成到 App 根组件
  - 添加错误日志记录
- **Acceptance Criteria Addressed**: AC-1
- **Test Requirements**:
  - `programmatic` TR-1.1: ErrorBoundary 组件正确渲染错误子组件正常时显示子组件
  - `programmatic` TR-1.2: 子组件抛错时显示错误界面
  - `human-judgement` TR-1.3: 错误页面信息清晰，按钮可操作
- **Notes**: 参考 React 官方 ErrorBoundary 实现模式

## [x] Task 2: 全局通知系统 (Toast)
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 创建 `Toast` 组件，支持 success/error/warning/info 四种类型
  - 创建 `useToast` hook 管理通知队列
  - 支持自动消失（默认3秒）、手动关闭、堆叠显示
  - 集成到应用根组件
- **Acceptance Criteria Addressed**: AC-2
- **Test Requirements**:
  - `programmatic` TR-2.1: useToast hook 可以添加和移除通知
  - `programmatic` TR-2.2: 通知自动超时消失
  - `human-judgement` TR-2.3: 通知位置合理，动画流畅
- **Notes**: 右上角堆叠，新通知在上方

## [x] Task 3: 暗色模式支持
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 基于 Tailwind CSS 的 dark mode 实现
  - 创建 `useTheme` hook 管理主题状态
  - 主题偏好持久化到 localStorage
  - 所有组件适配暗色模式
  - 在设置中添加主题切换开关
- **Acceptance Criteria Addressed**: AC-3
- **Test Requirements**:
  - `programmatic` TR-3.1: 主题切换后 html 元素有 dark class
  - `programmatic` TR-3.2: 刷新页面后主题保持
  - `human-judgement` TR-3.3: 所有页面在暗色模式下可读性良好
- **Notes**: 使用 `class` 策略，配合 CSS 变量

## [x] Task 4: 确认对话框组件
- **Priority**: high
- **Depends On**: Task 2 (可共享动画逻辑)
- **Description**: 
  - 创建 `ConfirmDialog` 组件
  - 支持标题、描述、确认/取消按钮
  - 支持危险操作样式（红色按钮）
  - 创建 `useConfirm` hook 简化调用
- **Acceptance Criteria Addressed**: AC-6
- **Test Requirements**:
  - `programmatic` TR-4.1: 对话框显示/隐藏正常
  - `programmatic` TR-4.2: 确认和取消回调正确触发
  - `human-judgement` TR-4.3: 对话框样式符合设计规范
- **Notes**: 危险操作使用红色主按钮

## [x] Task 5: 键盘快捷键系统
- **Priority**: medium
- **Depends On**: Task 2 (通知提示)
- **Description**: 
  - 创建 `useKeyboardShortcuts` hook
  - 支持常用快捷键：/ (搜索)、r (刷新)、g d (Dashboard)、g c (配置)、? (快捷键帮助)
  - 创建快捷键帮助对话框
  - 在输入框内自动禁用快捷键
- **Acceptance Criteria Addressed**: AC-4
- **Test Requirements**:
  - `programmatic` TR-5.1: 快捷键触发对应动作
  - `programmatic` TR-5.2: 输入框内不触发全局快捷键
  - `human-judgement` TR-5.3: 快捷键帮助页面清晰易读
- **Notes**: 参考 Gmail/Linear 的快捷键设计

## [x] Task 6: 导出功能
- **Priority**: medium
- **Depends On**: None
- **Description**: 
  - 实现候选列表 CSV 导出
  - 实现候选列表 JSON 导出
  - 导出包含当前筛选结果
  - 在工具栏添加导出按钮
- **Acceptance Criteria Addressed**: AC-5
- **Test Requirements**:
  - `programmatic` TR-6.1: CSV 导出文件格式正确
  - `programmatic` TR-6.2: JSON 导出文件格式正确
  - `human-judgement` TR-6.3: 导出按钮位置合理，操作清晰
- **Notes**: 前端导出，不依赖后端

## [x] Task 7: 加载状态统一优化
- **Priority**: medium
- **Depends On**: None
- **Description**: 
  - 审计所有页面的加载状态
  - 确保骨架屏使用一致
  - 优化加载动画和过渡效果
  - 添加页面级加载指示器
- **Acceptance Criteria Addressed**: AC-8
- **Test Requirements**:
  - `human-judgement` TR-7.1: 所有页面加载状态有视觉反馈
  - `human-judgement` TR-7.2: 加载过程无空白闪烁
  - `human-judgement` TR-7.3: 加载动效统一协调

## [x] Task 8: 空状态统一优化
- **Priority**: medium
- **Depends On**: None
- **Description**: 
  - 审计所有空状态场景
  - 使用统一的 EmptyState 组件
  - 每个空状态提供引导操作
  - 优化空状态的文案和图标
- **Acceptance Criteria Addressed**: AC-9
- **Test Requirements**:
  - `human-judgement` TR-8.1: 所有空数据场景有友好展示
  - `human-judgement` TR-8.2: 空状态提供明确的下一步操作指引
  - `human-judgement` TR-8.3: 空状态样式统一

## [x] Task 9: 可访问性优化
- **Priority**: medium
- **Depends On**: Task 1 (可并行)
- **Description**: 
  - 添加语义化 HTML 标签
  - 完善 ARIA 标签
  - 确保键盘导航完整
  - 检查颜色对比度
  - 添加 Skip to content 链接
- **Acceptance Criteria Addressed**: AC-7
- **Test Requirements**:
  - `human-judgement` TR-9.1: 所有交互元素可键盘操作
  - `human-judgement` TR-9.2: 焦点可见且顺序合理
  - `human-judgement` TR-9.3: 颜色对比度符合 WCAG AA
- **Notes**: 重点是表单、按钮、表格

## [x] Task 10: 引导与帮助系统
- **Priority**: low
- **Depends On**: Task 2 (通知)
- **Description**: 
  - 实现首次使用引导提示
  - 关键功能点添加 Tooltip 说明
  - 创建帮助页面/快捷键说明
  - 添加"显示帮助"入口
- **Acceptance Criteria Addressed**: (FR-4)
- **Test Requirements**:
  - `human-judgement` TR-10.1: 关键功能有帮助说明
  - `human-judgement` TR-10.2: 引导不干扰正常使用
  - `human-judgement` TR-10.3: 帮助内容准确有用

## [x] Task 11: 构建产物优化
- **Priority**: medium
- **Depends On**: None
- **Description**: 
  - 配置代码分割（路由级 + 组件级）
  - 优化第三方依赖打包
  - 配置 gzip/brotli 压缩
  - 验证首屏加载性能
- **Acceptance Criteria Addressed**: AC-10, NFR-1
- **Test Requirements**:
  - `programmatic` TR-11.1: gzip 后主包 < 300KB
  - `programmatic` TR-11.2: 路由级代码分割生效
  - `human-judgement` TR-11.3: 首屏加载感觉流畅

## 任务依赖关系图
```
Task 1 ──────────┐
Task 2 ──────────┼─── Task 5
Task 3 ──────────┤
Task 4 ──────────┘
Task 6 (独立)
Task 7 (独立)
Task 8 (独立)
Task 9 (独立，可与 Task 1 并行)
Task 10 依赖 Task 2
Task 11 (独立)
```

高优先级任务：Task 1, 2, 3, 4
中优先级任务：Task 5, 6, 7, 8, 9, 11
低优先级任务：Task 10
