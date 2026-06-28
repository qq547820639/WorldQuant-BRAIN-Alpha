# Tasks

## 阶段一：P0 核心业务安全

- [x] Task 1.1: 修复 9 处静默吞异常
  - [x] SubTask 1.1.1: 重新扫描 scoring/、research/、scripts/quality_gate/ 下所有 except Exception
  - [x] SubTask 1.1.2: 对每个 except 块分类（A 类有日志有默认值/B 类有日志无默认值/C 类纯静默）
  - [x] SubTask 1.1.3: 按处理策略修复（预期错误 warning+默认值/不该发生 exception+raise/保护兜底 exception+错误结果）
  - [x] SubTask 1.1.4: 运行相关测试确认无回归
  - [x] SubTask 1.1.5: 输出修改清单（文件:行号 | 处理前 | 处理后 | 分类）

- [x] Task 1.2: 修复 _json 方法 CORS 缺失
  - [x] SubTask 1.2.1: 找到 _json 方法定义位置
  - [x] SubTask 1.2.2: 提取 _send_json 的 CORS 头设置逻辑
  - [x] SubTask 1.2.3: 将相同 CORS 逻辑应用到 _json（含 ACAO + Vary: Origin）
  - [x] SubTask 1.2.4: curl 带 Origin 头验证 ACAO
  - [x] SubTask 1.2.5: 运行测试确认无回归

- [x] Task 1.3: 统一 CORS 封装
  - [x] SubTask 1.3.1: 找到所有设置 ACAO 的代码位置
  - [x] SubTask 1.3.2: 创建统一 _set_cors_headers(request_headers, response_headers) 辅助函数
  - [x] SubTask 1.3.3: 替换所有分散 CORS 设置为调用统一函数
  - [x] SubTask 1.3.4: 确保 OPTIONS 预检也使用统一函数
  - [x] SubTask 1.3.5: curl 验证（白名单内/外/无 Origin/OPTIONS 预检）
  - [x] SubTask 1.3.6: 运行测试确认无回归

- [x] Task 1.4: 安装 jsonschema
  - [x] SubTask 1.4.1: pip install jsonschema
  - [x] SubTask 1.4.2: 确认配置校验模块正确使用 jsonschema
  - [x] SubTask 1.4.3: 重启后端确认无"jsonschema 未安装"提示
  - [x] SubTask 1.4.4: 运行配置相关测试确认无回归

## 阶段二：P1 输入校验与安全加固

- [x] Task 2.1: /api/trends 添加输入范围校验
  - [x] SubTask 2.1.1: 找到 /api/trends 路由处理函数
  - [x] SubTask 2.1.2: 添加 candidates/submissions/cycles 正整数 + 上限校验
  - [x] SubTask 2.1.3: 校验失败返回 400 + 明确错误信息
  - [x] SubTask 2.1.4: curl 验证超范围参数返回 400
  - [x] SubTask 2.1.5: 运行测试确认无回归

- [x] Task 2.2: Content-Type 校验
  - [x] SubTask 2.2.1: 找到 HTTP 请求解析入口点
  - [x] SubTask 2.2.2: POST/PUT/PATCH 校验 Content-Type: application/json
  - [x] SubTask 2.2.3: 不匹配返回 415 Unsupported Media Type
  - [x] SubTask 2.2.4: 校验逻辑放在公共层（中间件/装饰器）
  - [x] SubTask 2.2.5: curl 验证错误 Content-Type 返回 415
  - [x] SubTask 2.2.6: 运行测试确认无回归

- [x] Task 2.3: Host 头回退构造 ACAO 修复
  - [x] SubTask 2.3.1: 找到从 Host 头构造 ACAO 的代码
  - [x] SubTask 2.3.2: 修改逻辑：无 Origin 时不设置 ACAO（不回退 Host）
  - [x] SubTask 2.3.3: curl 验证无 Origin 请求响应中无 ACAO
  - [x] SubTask 2.3.4: 运行测试确认无回归

## 阶段三：TypeScript strict 模式（分批修复）

- [x] Task 3.1: 临时开启 strict 模式评估
  - [x] SubTask 3.1.1: tsconfig.json 设置 strict: true（删除 noImplicitAny/strictNullChecks 覆盖）
  - [x] SubTask 3.1.2: 运行 npm run typecheck 记录所有错误
  - [x] SubTask 3.1.3: 按错误类型分类统计
  - [x] SubTask 3.1.4: 保持 strict: true 直接在 strict 模式下修复

- [x] Task 3.2: 修复 TS18047（possibly null/undefined，8 个）
  - [x] SubTask 3.2.1: 逐个定位错误
  - [x] SubTask 3.2.2: 修复（非空断言 ! / null 检查 / 可选链 ?.）
  - [x] SubTask 3.2.3: 每修一个运行 typecheck 确认无新错误

- [x] Task 3.3: 修复 TS2345（实参类型不兼容，7 个）
  - [x] SubTask 3.3.1: 逐个定位错误
  - [x] SubTask 3.3.2: 分析调用方 vs 签名问题
  - [x] SubTask 3.3.3: 修正参数类型或函数签名
  - [x] SubTask 3.3.4: 每修一个确认无新错误

- [x] Task 3.4: 修复 TS2322（赋值类型不兼容，12 个）
  - [x] SubTask 3.4.1: 逐个定位错误
  - [x] SubTask 3.4.2: 分析目标太窄 vs 源太宽
  - [x] SubTask 3.4.3: 扩展类型定义或修正数据来源/添加类型守卫
  - [x] SubTask 3.4.4: 每修一个确认无新错误

- [x] Task 3.5: 修复 TS18048 剩余（2 个）
  - [x] SubTask 3.5.1: 同 Task 3.2 处理方式

- [x] Task 3.6: strict 模式验证
  - [x] SubTask 3.6.1: npm run typecheck 确认 strict 模式下 0 错误
  - [x] SubTask 3.6.2: npm run lint 确认无新增 lint 错误
  - [x] SubTask 3.6.3: npm test 确认无回归（如有）
  - [x] SubTask 3.6.4: tsconfig.json 保持 strict: true 不回退

## 阶段四：ESLint warnings 清理

- [x] Task 4.1: 修复 no-base-to-string 遗漏（如有）
  - [x] SubTask 4.1.1: npm run lint 过滤 no-base-to-string
  - [x] SubTask 4.1.2: 如有剩余逐个修复

- [x] Task 4.2: 修复 react-hooks/set-state-in-effect
  - [x] SubTask 4.2.1: npm run lint 过滤 set-state-in-effect
  - [x] SubTask 4.2.2: 重构为条件更新或 eslint-disable 注释说明
  - [x] SubTask 4.2.3: 逐个修复或标注

- [x] Task 4.3: 修复 react-hooks/preserve-manual-memoization
  - [x] SubTask 4.3.1: npm run lint 过滤 preserve-manual-memoization
  - [x] SubTask 4.3.2: 移除不必要手动 memo 或 eslint-disable 注释
  - [x] SubTask 4.3.3: 逐个修复或标注

- [x] Task 4.4: 修复剩余高优先 warnings + 最终报告
  - [x] SubTask 4.4.1: 列出剩余 warnings 规则分布
  - [x] SubTask 4.4.2: 修复 no-base-to-string/set-state-in-effect/preserve-manual-memoization 剩余
  - [x] SubTask 4.4.3: 其他规则 warnings 标注为已知
  - [x] SubTask 4.4.4: 最终 npm run lint 报告 errors 和 warnings 数量

## 阶段五：代码清理

- [x] Task 5.1: 清理后端冗余端点
  - [x] SubTask 5.1.1: 列出所有后端 API 端点
  - [x] SubTask 5.1.2: 前端代码搜索每个端点调用
  - [x] SubTask 5.1.3: 标记 A（前端调用）/B（功能入口）/C（别名废弃）类
  - [x] SubTask 5.1.4: C 类端点注释（不删除）+ 标注废弃日期
  - [x] SubTask 5.1.5: 运行测试确认无回归

- [x] Task 5.2: 修复前后端参数不匹配
  - [x] SubTask 5.2.1: 逐个列出 7 处不匹配参数
  - [x] SubTask 5.2.2: 修复（添加后端校验/移除前端误发/添加可选校验）
  - [x] SubTask 5.2.3: typecheck + Python 测试无回归

- [x] Task 5.3: 修复 jobCancel API 统一
  - [x] SubTask 5.3.1: 重新评估上次跳过原因
  - [x] SubTask 5.3.2: 选最保守方案（依赖注入 apiCall 参数 / 提取纯函数 / 完整错误处理）
  - [x] SubTask 5.3.3: 执行改造
  - [x] SubTask 5.3.4: 验证取消功能正常 + typecheck + lint 无回归

- [x] Task 5.4: 质量门 fail-open 评估
  - [x] SubTask 5.4.1: 找到 3 处 fail-open 代码
  - [x] SubTask 5.4.2: 逐处分析（脚本报错/检查不通过/不适用）
  - [x] SubTask 5.4.3: 修改逻辑（脚本报错+检查不通过 → fail-closed，不适用 → fail-open + 日志）
  - [x] SubTask 5.4.4: 运行质量门测试确认无回归
  - [x] SubTask 5.4.5: 如测试因 fail-closed 失败分析是否更新测试期望

- [x] Task 5.5: 评估 react-router-dom
  - [x] SubTask 5.5.1: 检查引入前视图切换机制
  - [x] SubTask 5.5.2: 评估方案 A（保留精简）vs 方案 B（移除用状态管理）
  - [x] SubTask 5.5.3: 选改动最小方案执行
  - [x] SubTask 5.5.4: typecheck + lint + 页面跳转验证

## 阶段六：npm 安全漏洞修复

- [x] Task 6.1: 评估 vite 8 升级
  - [x] SubTask 6.1.1: npm audit 列出所有漏洞详情
  - [x] SubTask 6.1.2: 读取 vite CHANGELOG/MIGRATION GUIDE
  - [x] SubTask 6.1.3: 检查 vite.config.ts 兼容性 + vitest 兼容性
  - [x] SubTask 6.1.4: 安全升级（npm install vite@latest vitest@latest）或报告风险
  - [x] SubTask 6.1.5: 验证 dev/build/test/audit
  - [x] SubTask 6.1.6: 输出升级/不升级决策报告

## 阶段七：Docker 优化

- [x] Task 7.1: Docker 分阶段构建
  - [x] SubTask 7.1.1: 读取当前 Dockerfile
  - [x] SubTask 7.1.2: 改为多阶段（builder 全依赖+构建前端 / runtime 生产依赖+dist）
  - [x] SubTask 7.1.3: 确保 Python 生产依赖不含 test/dev 可选依赖
  - [x] SubTask 7.1.4: 前端只复制 dist/ 不复制源码和 node_modules
  - [x] SubTask 7.1.5: 数据/配置目录正确挂载
  - [x] SubTask 7.1.6: 同步更新 docker-compose.yml（如有）
  - [x] SubTask 7.1.7: 报告优化前后镜像预估大小对比

## 阶段八：最终报告

- [ ] Task 8.1: 修复成果总结（每阶段子表，去重文件清单）
- [ ] Task 8.2: 全量回归验证（pytest/typecheck/lint/build/启动/health）
- [ ] Task 8.3: 项目健康度评分更新（7 维度，对比上次）
- [ ] Task 8.4: 剩余问题清单

# Task Dependencies
- Task 1.2 和 1.3 有依赖：1.3 统一封装后 1.2 自动解决，建议先做 1.3 再验证 1.2
- Task 1.4（安装 jsonschema）独立，可并行
- 阶段二依赖阶段一 1.3（CORS 统一封装）完成
- 阶段三（strict 修复）独立，可与阶段一/二并行（前端 vs 后端）
- 阶段四依赖阶段三（strict 修复后 lint 基线稳定）
- Task 5.3（jobCancel）独立
- Task 5.4（质量门）依赖 Task 1.1（异常处理修复）
- Task 5.5（react-router-dom）独立
- 阶段六独立但建议在阶段三/四后（前端代码稳定后升级）
- 阶段七独立
- 阶段八依赖所有前置阶段完成
- **刹车机制**：任何修复若导致 >10 个测试失败，停下来报告分析，不强行改
