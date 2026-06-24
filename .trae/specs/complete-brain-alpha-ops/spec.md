# BRAIN Alpha Ops 项目完成规格

## 为什么
BRAIN Alpha Ops 是一个 WorldQuant BRAIN 平台的 Alpha 因子生产系统，目前处于"烂尾"状态——核心功能基本可用，但存在 TypeScript 类型不完整、少量测试失败、前端构建有警告等问题，需要系统性修复以达到生产就绪状态。

## 什么变化
- 完成 TypeScript 类型系统，消除 57 个类型错误
- 修复 test_web_html.py 中的 4-5 个测试失败
- 确保前端构建零错误
- 完成核心链路的端到端验证
- 确保后端和前端可以正常启动和运行

## 影响
- 受影响的规格：BRAIN 平台技术合规、科学评分系统、三槽调度器、实时状态监控
- 受影响的代码：
  - `/workspace/brain_alpha_ops/web/react_app/src/` (TypeScript 前端)
  - `/workspace/tests/test_web_html.py` (测试文件)
  - `/workspace/brain_alpha_ops/research/` (核心研究引擎)

## 新增需求
### 需求：完整的 TypeScript 类型定义
系统必须提供完整的 TypeScript 类型定义，确保前端代码零类型错误。

#### 场景：类型检查通过
- **WHEN** 执行 `npx tsc --noEmit` 时
- **THEN** 不应有任何 "error TS" 输出

### 需求：测试用例与实现同步
系统必须确保测试用例与实际实现保持同步。

#### 场景：所有核心测试通过
- **WHEN** 运行 `pytest tests/` 时
- **THEN** 核心测试（架构合规、评分、调度器、安全）必须全部通过

### 需求：前后端正常启动
系统必须能够正常启动后端和前端服务。

#### 场景：服务启动成功
- **WHEN** 执行 `python3 launch_web.py` 时
- **THEN** 健康检查返回 200，根路径返回 200

## 修改的需求
### 需求：ConfigPanel 缓存模式逻辑
系统必须正确处理缓存模式和正常模式的配置展示逻辑。

#### 场景：缓存模式凭据折叠
- **WHEN** `contextFresh=true` 且 `connected=false` 时
- **THEN** ConfigPanel 应显示 LocalCacheConnectionSection，凭据输入默认折叠

### 需求：web_html.py 前端选择
系统必须提供安全的前端选择函数。

#### 场景：无效值处理
- **WHEN** `selected_frontend("unknown")` 被调用时
- **THEN** 应抛出 ValueError
- **WHEN** `safe_selected_frontend("unknown")` 被调用时
- **THEN** 应返回 INLINE_FRONTEND，不抛出异常

## 移除的需求
无

## 技术约束
- 所有 BRAIN 平台字段/算子必须基于官方 API
- 禁止使用测试脚本进行过拟合
- 凭证必须通过安全方式管理，不落盘不日志
- 提交功能必须有人工确认机制
