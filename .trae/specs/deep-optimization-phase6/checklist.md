# BRAIN Alpha Ops 深挖优化 Phase 6 - 验证清单

## 前端文件大小
- [x] useJobMonitor.ts 拆分后所有子文件 ≤ 400 行
- [x] useAppState.ts 拆分后所有子文件 ≤ 400 行
- [x] ScoringPanel.tsx 拆分后所有子文件 ≤ 400 行
- [x] SnapshotPanel.tsx 拆分后所有子文件 ≤ 400 行
- [x] CandidateTableSubComponents.tsx 拆分后所有子文件 ≤ 400 行
- [x] CandidateTable.tsx 拆分后所有子文件 ≤ 400 行
- [x] StateCards.tsx 拆分后所有子文件 ≤ 400 行
- [x] ConfigPanel/utils.ts 拆分后所有子文件 ≤ 400 行
- [x] runPayload.ts 拆分后所有子文件 ≤ 400 行
- [x] 所有前端源文件 ≤ 400 行（wc -l 验证）

## Python 后端文件大小
- [x] simulation.py 拆分后所有子文件 ≤ 350 行（最大 342 行）
- [x] web_routes.py 拆分后所有子文件 ≤ 350 行（最大 340 行）
- [x] snapshot.py 拆分后所有子文件 ≤ 350 行（最大 287 行）

## 向后兼容
- [x] 所有前端原文件保留为 re-export 入口
- [x] 所有 Python 原文件保留为 re-export 入口
- [x] 现有导入路径全部正常工作

## 测试验证
- [x] Python anti_overfit 测试全部通过（43个）
- [x] Python web_routes 测试通过（无新增失败，4个预存失败）
- [x] 无 import 错误

## 提交
- [x] 所有变更已提交
- [x] 已成功推送到 origin/main
- [x] git status 显示工作区干净
