# BRAIN Alpha Ops 深挖优化 Phase 7 - 验证清单

## snapshot.py 修复
- [x] snapshot.py 转为 re-export，原文件 ≤ 100 行
- [x] snapshot/ 子包所有子文件 ≤ 350 行
- [x] `from brain_alpha_ops.web_cloud.snapshot import *` 正常工作

## research/ 模块拆分
- [x] research/generation/generator.py 拆分后所有子文件 ≤ 350 行
- [x] research/scoring.py 拆分后所有子文件 ≤ 350 行
- [x] research/assistant.py 拆分后所有子文件 ≤ 350 行
- [x] research/alpha_quality.py 拆分后所有子文件 ≤ 350 行
- [x] research/pipeline.py 拆分后所有子文件 ≤ 350 行
- [x] research/hypothesis_library.py 拆分后所有子文件 ≤ 350 行

## web/ 模块拆分
- [x] web/candidates/web_check_availability.py 拆分后所有子文件 ≤ 350 行
- [x] web/misc/web_runtime_facade.py 拆分后所有子文件 ≤ 350 行
- [x] web/misc/web_assistant_snapshots.py 拆分后所有子文件 ≤ 350 行

## 向后兼容
- [x] 所有原文件保留为 re-export 入口
- [x] 现有导入路径全部正常工作

## 测试验证
- [x] Python anti_overfit 测试全部通过 (43/43)
- [x] Python web_routes 测试无新增失败 (14 个失败为预存在问题，与本次重构无关)
- [x] 无 import 错误

## 提交
- [x] 所有变更已提交
- [x] 已成功推送到 origin/main
- [x] git status 显示工作区干净（除测试产生的数据文件）
