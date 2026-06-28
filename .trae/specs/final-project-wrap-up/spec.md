# Final Project Wrap-up Spec

## Why
在完成 P0/P1 修复（Fix 1-6）和回归验证后，项目进入收尾阶段。需要保护现有修复成果、修复已知 P2 缺陷、进行深度安全与质量审查、并执行冒烟测试，最终输出项目健康度评估和后续建议，为部署决策提供依据。

## What Changes
- 阶段一：保护现有修复成果
  - 确认 6 个关键修复文件在 git 变更列表中
  - 统一 README.md / pyproject.toml / package.json 的版本号为 0.5.0
  - 扫描代码中所有环境变量引用，创建 .env.example
- 阶段二：修复已知 P2 缺陷
  - 运行 `npm audit fix`（不加 --force）修复安全漏洞
  - 添加前端 404 通配路由 + NotFound 组件
  - 修复 ESLint `no-base-to-string` warnings（仅此一类）
  - 统一 `jobCancel.ts` 使用 `useApi` 封装替代独立 fetch
  - 修复预存测试失败 `test_react_status_summaries_do_not_cap_reason_lists`
- 阶段三：深度安全审查（只审查、报告，不修改业务逻辑）
  - 凭证硬编码扫描
  - 后端 API 输入校验审查
  - CORS 配置一致性审查
  - XSS 防护审查（dangerouslySetInnerHTML / CSP）
- 阶段四：代码质量深度审查（只审查、报告，不修改）
  - 关键路径异常处理审查（认证/持久化/BRAIN API/生成管线/评分）
  - 前后端接口一致性深度校验
  - TypeScript strict 模式评估（只报告不修改）
- 阶段五：冒烟测试
  - 启动后端 + 前端，验证 /api/health
  - GET 端点冒烟（curl 逐个访问）
  - 前端页面 + 静态资源冒烟
- 阶段六：最终报告
  - 修复成果总结
  - 未修复问题清单（含原因/风险/建议处理时间）
  - 项目健康度评分（7 个维度 1-10 分）
  - 后续建议（按优先级）

## Impact
- Affected specs: 无（独立收尾任务）
- Affected code:
  - `README.md`、`brain_alpha_ops/web/react_app/package.json`（版本号统一）
  - `.env.example`（新增）
  - `brain_alpha_ops/web/react_app/package.json`、`package-lock.json`（npm audit fix）
  - 前端路由配置 + 新增 `NotFound` 组件
  - 多个含 `no-base-to-string` warning 的 .ts/.tsx 文件
  - `brain_alpha_ops/web/react_app/src/api/jobCancel.ts`
  - `tests/test_react_api_contract_static.py`（预存测试修复）
- **BREAKING**: 无

## ADDED Requirements

### Requirement: .env.example 文件
系统 SHALL 在项目根目录提供 `.env.example` 文件，列出代码中所有被引用的环境变量名，每个变量一行，格式为 `VARIABLE_NAME=  # 说明用途`，敏感变量（密码/API Key）使用 `YOUR_xxx_HERE` 占位符。

#### Scenario: 开发者首次配置环境
- **WHEN** 开发者克隆仓库并查看 .env.example
- **THEN** 能看到所有必需的环境变量名和用途说明
- **AND** 敏感变量显示占位符而非真实值

### Requirement: 前端 404 路由
系统 SHALL 在前端路由表末尾提供通配路由 `path="*"`，指向 NotFound 组件。

#### Scenario: 用户访问不存在的路由
- **WHEN** 用户访问未定义的 URL 路径
- **THEN** 显示 "页面未找到" 提示
- **AND** 提供返回首页的链接
- **AND** 不影响现有路由的正常访问

### Requirement: jobCancel 统一 API 封装
`jobCancel.ts` SHALL 使用项目的 `useApi` hook 进行 HTTP 请求，而非独立 `fetch` 调用。

#### Scenario: 取消任务
- **WHEN** 用户触发任务取消
- **THEN** 请求通过 useApi 发送
- **AND** 错误处理和超时处理与原有行为一致

## MODIFIED Requirements

### Requirement: 版本号一致性
README.md、pyproject.toml、brain_alpha_ops/web/react_app/package.json 中的版本号 SHALL 全部为 `0.5.0`（以 pyproject.toml 为准）。

### Requirement: ESLint no-base-to-string
所有在模板字符串或字符串拼接中可能产生 `[object Object]` 的代码 SHALL 显式调用 `.toString()`、`JSON.stringify()` 或自定义格式化函数。

### Requirement: 预存测试 test_react_status_summaries_do_not_cap_reason_lists
该测试 SHALL 通过；如果测试引用了不存在的函数，修正测试代码使其与实际业务代码一致。

## REMOVED Requirements
无
