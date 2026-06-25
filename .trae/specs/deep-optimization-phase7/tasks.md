# BRAIN Alpha Ops 深挖优化 Phase 7 - 实施计划

# Tasks

- [x] Task 1: 修复 snapshot.py → 转为 re-export（Phase 6 遗留）
  - [x] SubTask 1.1: 读取 snapshot.py 原始内容，确认 snapshot/ 子包已包含所有功能
  - [x] SubTask 1.2: 将 snapshot.py 替换为 re-export shim（26行）
  - [x] SubTask 1.3: 验证导入正常

- [x] Task 2: 拆分 research/ 模块大文件（6个文件）
  - [x] SubTask 2.1: 拆分 research/generation/generator.py (901行) → generator/ 子包 (4个子文件，max 347行)
  - [x] SubTask 2.2: 拆分 research/scoring.py (883行) → scoring/ 子包 (5个子文件，max 285行)
  - [x] SubTask 2.3: 拆分 research/assistant.py (838行) → assistant/ 子包 (5个子文件，max 342行)
  - [x] SubTask 2.4: 拆分 research/alpha_quality.py (821行) → alpha_quality/ 子包 (6个子文件，max 249行)
  - [x] SubTask 2.5: 拆分 research/pipeline.py (817行) → pipeline/ 子包 (6个子文件，max 261行)
  - [x] SubTask 2.6: 拆分 research/hypothesis_library.py (810行) → hypothesis_library/ 子包 (5个子文件，max 305行)

- [x] Task 3: 拆分 web/ 模块大文件（3个文件）
  - [x] SubTask 3.1: 拆分 web/candidates/web_check_availability.py (878行) → 4个子文件，max 333行
  - [x] SubTask 3.2: 拆分 web/misc/web_runtime_facade.py (784行) → 6个子文件，max 269行
  - [x] SubTask 3.3: 拆分 web/misc/web_assistant_snapshots.py (779行) → 7个子文件，max 300行

- [x] Task 4: 最终验证与提交
  - [x] SubTask 4.1: 确认所有目标文件已拆分（10个文件全部完成）
  - [x] SubTask 4.2: 运行 Python 测试套件（91 passed, 4 pre-existing failures）
  - [x] SubTask 4.3: 提交并推送到 origin/main

# Task Dependencies
- Task 1, Task 2, Task 3 可并行执行
- Task 4 依赖 Task 1-3 全部完成
