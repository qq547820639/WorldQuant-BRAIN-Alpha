# BRAIN Alpha Ops 深挖优化 Phase 6 - 实施计划

# Tasks

- [x] Task 1: 拆分前端 hooks 大文件（useJobMonitor 465行、useAppState 408行）
  - [x] SubTask 1.1: 拆分 useJobMonitor.ts → useJobMonitor/ 子目录（状态管理、SSE连接、通知等）
  - [x] SubTask 1.2: 拆分 useAppState.ts → useAppState/ 子目录（全局状态、导航、会话等）
  - [x] SubTask 1.3: 验证导入兼容性和 TypeScript 类型检查

- [x] Task 2: 拆分前端组件大文件（ScoringPanel 464行、SnapshotPanel 461行、CandidateTableSubComponents 455行、CandidateTable 444行、StateCards 430行）
  - [x] SubTask 2.1: 拆分 ScoringPanel.tsx → ScoringPanel/ 子目录
  - [x] SubTask 2.2: 拆分 SnapshotPanel.tsx → SnapshotPanel/ 子目录（补充现有子组件）
  - [x] SubTask 2.3: 拆分 CandidateTableSubComponents.tsx → 子模块
  - [x] SubTask 2.4: 拆分 CandidateTable.tsx → 子模块
  - [x] SubTask 2.5: 拆分 StateCards.tsx → StateCards/ 子目录（补充现有子组件）
  - [x] SubTask 2.6: 验证所有组件导入和渲染正常

- [x] Task 3: 拆分前端工具文件（ConfigPanel/utils 462行、runPayload 443行）
  - [x] SubTask 3.1: 拆分 ConfigPanel/utils.ts → 多个工具模块
  - [x] SubTask 3.2: 拆分 helpers/runPayload.ts → 多个模块
  - [x] SubTask 3.3: 验证导入兼容性

- [x] Task 4: 拆分 Python 后端大文件（simulation.py 1031行、web_routes.py 961行、snapshot.py 905行）
  - [x] SubTask 4.1: 拆分 web_candidates/simulation.py → simulation/ 子包
  - [x] SubTask 4.2: 拆分 web/dispatch/web_routes.py → get_routes/ 子包
  - [x] SubTask 4.3: 拆分 web_cloud/snapshot.py → snapshot/ 子包
  - [x] SubTask 4.4: 运行 Python 测试验证（pytest tests/test_anti_overfit.py tests/test_web_routes_handlers.py）

- [x] Task 5: 最终验证与提交
  - [x] SubTask 5.1: 确认所有前端文件 ≤ 400 行
  - [x] SubTask 5.2: 确认所有后端文件 ≤ 500 行
  - [x] SubTask 5.3: 运行 Python 测试套件
  - [x] SubTask 5.4: 提交并推送到 origin/main

# Task Dependencies
- Task 1, Task 2, Task 3, Task 4 可并行执行
- Task 5 依赖 Task 1-4 全部完成
