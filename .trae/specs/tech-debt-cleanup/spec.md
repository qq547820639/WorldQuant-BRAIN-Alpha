# Tech Debt Cleanup Spec

## Why
在完成 P0/P1 修复和项目收尾审查后，发现了大量技术债务：9 处静默吞异常、CORS 配置不一致、输入校验缺口、TypeScript strict 模式 29 个错误、198 个 ESLint warnings、40+ 冗余端点、npm 23 个安全漏洞、Docker 未分阶段构建。这些债务影响安全性、类型安全和部署就绪度，需要系统性清理以达成生产可部署状态。

## What Changes
- 阶段一：P0 核心业务安全
  - 修复 9 处静默吞异常（评分/候选生成/质量门路径），分类处理（A/B/C 类）
  - 修复 `_json` 方法 CORS 缺失（补齐 ACAO + Vary: Origin）
  - 统一 CORS 封装为单一辅助函数，替换所有分散设置
  - 安装 jsonschema 恢复完整配置校验
- 阶段二：P1 输入校验与安全加固
  - `/api/trends` 添加参数范围校验（candidates/submissions/cycles 上限）
  - 全局 Content-Type 校验（POST/PUT/PATCH 要求 application/json，不匹配返回 415）
  - 移除 Host 头回退构造 ACAO（无 Origin 时不设置 ACAO）
- 阶段三：TypeScript strict 模式（分批修复 29 个错误）
  - 临时开启 strict: true 评估
  - 修复 TS18047（8+2 个 possibly null/undefined）
  - 修复 TS2345（7 个实参类型不兼容）
  - 修复 TS2322（12 个赋值类型不兼容）
  - 保持 strict: true，不回退
- 阶段四：ESLint warnings 清理
  - 修复 no-base-to-string 遗漏（如有）
  - 修复 react-hooks/set-state-in-effect
  - 修复 react-hooks/preserve-manual-memoization
  - 其他高优先 warnings 修复或标注
- 阶段五：代码清理
  - 注释（不删除）冗余别名/未使用端点，标注废弃
  - 修复 7 处前后端参数不匹配
  - 修复 jobCancel API 统一（选最保守方案：依赖注入或提取纯函数）
  - 质量门 fail-open 评估（脚本错误 → fail-closed，不适用 → fail-open + 日志）
  - 评估 react-router-dom（选改动最小方案）
- 阶段六：npm 安全漏洞修复
  - 评估 vite 8 升级影响（CHANGELOG/配置兼容性/测试）
  - 安全升级或报告风险 + 替代方案
- 阶段七：Docker 优化
  - Dockerfile 改为多阶段构建（builder 安装全部依赖 + 构建前端，runtime 仅生产依赖 + dist）
  - 同步更新 docker-compose.yml（如有）
- 阶段八：最终报告
  - 修复成果文件清单（每阶段子表）
  - 全量回归验证（pytest + typecheck + lint + build + 启动 + health）
  - 项目健康度评分更新（7 维度，对比上次）
  - 剩余问题清单

## Impact
- Affected specs: `final-project-wrap-up`（延续其遗留问题清单）
- Affected code:
  - `brain_alpha_ops/scoring/`、`brain_alpha_ops/research/`、`scripts/quality_gate/`（异常处理修复）
  - `brain_alpha_ops/web/dispatch/web_http_handler/`（CORS 统一 + Content-Type 校验 + Host 头修复）
  - `brain_alpha_ops/web/`（/api/trends 校验）
  - `brain_alpha_ops/web/react_app/tsconfig.json`（strict: true）
  - 多个 `.ts/.tsx` 文件（strict 修复 + ESLint warnings 清理）
  - `brain_alpha_ops/web/react_app/src/api/jobCancel.ts`（API 统一）
  - `brain_alpha_ops/audit_trail/quality_gate.py`（fail-open 评估）
  - `brain_alpha_ops/web/react_app/src/main.tsx`（react-router-dom 评估）
  - `brain_alpha_ops/web/react_app/package.json`、`package-lock.json`（vite 升级）
  - `Dockerfile`、`docker-compose.yml`（多阶段构建）
- **BREAKING**: TypeScript strict 模式开启（影响所有前端代码类型检查）；Content-Type 校验可能拒绝不符合规范的客户端（保守方案：仅对 POST/PUT/PATCH 强制）

## ADDED Requirements

### Requirement: 统一 CORS 辅助函数
系统 SHALL 提供单一 CORS 辅助函数 `_set_cors_headers(request_headers, response_headers)`，所有 CORS 头设置（包括 OPTIONS 预检、JSON 响应、HTML 响应）SHALL 通过此函数完成。

#### Scenario: 白名单内 Origin
- **WHEN** 请求 Origin 头在白名单中
- **THEN** 响应设置 `Access-Control-Allow-Origin: <origin>` + `Vary: Origin`
- **AND** 设置 `Access-Control-Allow-Credentials: true`

#### Scenario: 无 Origin 头
- **WHEN** 请求无 Origin 头
- **THEN** 响应不设置 `Access-Control-Allow-Origin`（不回退到 Host 头）

#### Scenario: 白名单外 Origin
- **WHEN** 请求 Origin 头不在白名单中
- **THEN** 响应不设置 `Access-Control-Allow-Origin`

### Requirement: Content-Type 校验
系统 SHALL 对 POST/PUT/PATCH 请求校验 Content-Type，JSON API 端点要求 `application/json`，不匹配时返回 415 Unsupported Media Type。

#### Scenario: 正确 Content-Type
- **WHEN** POST 请求 Content-Type 为 `application/json`
- **THEN** 请求正常处理

#### Scenario: 错误 Content-Type
- **WHEN** POST 请求 Content-Type 为 `text/plain`
- **THEN** 返回 415 Unsupported Media Type

### Requirement: /api/trends 输入范围校验
`/api/trends` 端点 SHALL 对 candidates/submissions/cycles 参数校验为正整数并限制上限，超出范围返回 400。

#### Scenario: 超范围参数
- **WHEN** POST /api/trends 请求 body 中 candidates=99999999
- **THEN** 返回 400 + 明确错误信息

### Requirement: 静默异常分类处理
评分计算、候选生成、质量门路径上的所有 `except Exception` SHALL 按以下分类处理：
- 预期内错误（如外部 API 超时）→ `logger.warning` + 返回默认值
- 不该发生的错误（如数据格式错误）→ `logger.exception` + raise 重新抛出
- 保护性兜底（如子进程执行）→ `logger.exception` + 返回包含错误信息的结果

#### Scenario: 评分数据格式错误
- **WHEN** 评分计算中数据格式不符合预期抛出异常
- **THEN** 记录 logger.exception 并 raise（不静默吞掉）

### Requirement: TypeScript strict 模式
前端 `tsconfig.json` SHALL 设置 `strict: true`，`npm run typecheck` SHALL 返回 0 错误。

#### Scenario: 类型检查通过
- **WHEN** 运行 npm run typecheck
- **THEN** exit code 0，无类型错误

### Requirement: Docker 多阶段构建
Dockerfile SHALL 使用多阶段构建，runtime 阶段仅包含生产依赖 + 前端构建产物，不含 dev/test 依赖和源码。

#### Scenario: 镜像构建
- **WHEN** docker build
- **THEN** runtime 镜像不含 node_modules、tests/、.pyc 等

## MODIFIED Requirements

### Requirement: 质量门 fail-open 策略
质量门检查 SHALL 区分"检查脚本报错"和"检查不通过"：
- 检查脚本报错 → fail-closed（阻断）+ 记录日志
- 检查不通过 → fail-closed（阻断）
- 检查不适用 → fail-open（放行）+ 记录日志

### Requirement: jobCancel API 统一
`jobCancel.ts` SHALL 通过依赖注入或提取纯函数的方式与项目统一 API 封装共享错误处理逻辑，不再使用完全独立的 fetch 实现。

## REMOVED Requirements
无（所有清理采用注释/保守方案，不删除功能）
