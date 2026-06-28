# Tasks

## 阶段一：保护现有修复成果

- [x] Task 1.1: 确认修改完整性
  - [x] SubTask 1.1.1: 运行 `git status --short` 统计被修改/新增文件数量
  - [x] SubTask 1.1.2: 运行 `git diff --stat` 输出完整文件列表
  - [x] SubTask 1.1.3: 确认 7 个关键文件在列表中（test_quality_gate.py、config_models.py、_manifest.py、check_module_size.py、_status.py、.gitignore、package.json）
  - [x] SubTask 1.1.4: 缺失文件报告原因

- [x] Task 1.2: 统一版本号
  - [x] SubTask 1.2.1: 读取 README.md / pyproject.toml / package.json 版本号
  - [x] SubTask 1.2.2: 不一致则统一为 0.5.0
  - [x] SubTask 1.2.3: 验证三处版本号一致

- [x] Task 1.3: 创建 .env.example
  - [x] SubTask 1.3.1: 扫描 os.environ / os.getenv / process.env 引用
  - [x] SubTask 1.3.2: 汇总去重所有环境变量名
  - [x] SubTask 1.3.3: 创建 .env.example（敏感变量用 YOUR_xxx_HERE 占位符）

## 阶段二：修复已知缺陷（P2）

- [x] Task 2.1: npm 安全漏洞修复
  - [x] SubTask 2.1.1: 运行 `npm audit` 报告所有漏洞
  - [x] SubTask 2.1.2: 运行 `npm audit fix`（不加 --force）
  - [x] SubTask 2.1.3: 运行 `npm audit` 报告剩余漏洞
  - [x] SubTask 2.1.4: critical 级剩余漏洞列出包名和影响范围
  - [x] SubTask 2.1.5: 运行 `npm run typecheck` + `npm run lint` 确认无回归

- [x] Task 2.2: 添加 404 路由
  - [x] SubTask 2.2.1: 读取前端路由配置文件
  - [x] SubTask 2.2.2: 创建 NotFound 组件（"页面未找到" + 返回首页链接 + 现有风格）
  - [x] SubTask 2.2.3: 在路由表末尾添加 `path="*"` 通配路由
  - [x] SubTask 2.2.4: typecheck + lint 确认无回归

- [x] Task 2.3: 修复 ESLint no-base-to-string warnings
  - [x] SubTask 2.3.1: 运行 `npm run lint` 过滤 no-base-to-string warnings
  - [x] SubTask 2.3.2: 逐个修复（.toString() / JSON.stringify / 自定义格式化）
  - [x] SubTask 2.3.3: 运行 `npm run lint` 确认此类 warning 消失，其他 warning 不变

- [x] Task 2.4: 统一 jobCancel.ts 的 API 请求
  - [x] SubTask 2.4.1: 读取 src/api/jobCancel.ts 和 src/hooks/useApi.ts
  - [x] SubTask 2.4.2: 改造 jobCancel.ts 使用 useApi 封装
  - [x] SubTask 2.4.3: 确保错误处理/超时处理与原来一致
  - [x] SubTask 2.4.4: typecheck + lint 确认无回归

- [x] Task 2.5: 修复预存测试失败
  - [x] SubTask 2.5.1: 运行 `pytest tests/ -k "test_react_status_summaries_do_not_cap_reason_lists" -v --tb=long`
  - [x] SubTask 2.5.2: 分析失败原因（countLabel 函数不存在）
  - [x] SubTask 2.5.3: 确认是测试问题还是业务代码缺失
  - [x] SubTask 2.5.4: 修正测试或报告业务代码缺失
  - [x] SubTask 2.5.5: 确认该测试通过

## 阶段三：深度安全审查（只审查、报告）

- [x] Task 3.1: 凭证安全扫描
  - [x] SubTask 3.1.1: 扫描硬编码 API Key/Token/Secret/密码/BRAIN 凭据
  - [x] SubTask 3.1.2: 检查 .env 是否在 .gitignore 中
  - [x] SubTask 3.1.3: 检查前端代码是否泄露后端密钥
  - [x] SubTask 3.1.4: 输出扫描结果

- [x] Task 3.2: 输入校验审查
  - [x] SubTask 3.2.1: 列出所有后端 API 端点
  - [x] SubTask 3.2.2: 逐端点检查 Content-Type/请求体大小/类型范围/文件上传校验
  - [x] SubTask 3.2.3: 输出检查结果表格

- [x] Task 3.3: CORS 配置审查
  - [x] SubTask 3.3.1: 找到所有设置 CORS 头的代码位置
  - [x] SubTask 3.3.2: 检查白名单一致性和宽松配置
  - [x] SubTask 3.3.3: 输出检查结果

- [x] Task 3.4: XSS 防护审查
  - [x] SubTask 3.4.1: 检查 dangerouslySetInnerHTML 使用
  - [x] SubTask 3.4.2: 检查后端返回数据 HTML 转义
  - [x] SubTask 3.4.3: 检查 CSP 配置
  - [x] SubTask 3.4.4: 输出检查结果

## 阶段四：代码质量深度审查（只审查、报告）

- [x] Task 4.1: 关键路径异常处理审查
  - [x] SubTask 4.1.1: 找到认证/持久化/BRAIN API/生成管线/评分 5 类关键路径代码
  - [x] SubTask 4.1.2: 检查裸 except / 过宽 except Exception
  - [x] SubTask 4.1.3: 标记吞掉异常的高风险点
  - [x] SubTask 4.1.4: 输出审查表格

- [x] Task 4.2: 前后端接口一致性深度校验
  - [x] SubTask 4.2.1: 提取前端所有 API 调用（URL/方法/参数）
  - [x] SubTask 4.2.2: 提取后端所有路由定义（URL/方法/期望参数）
  - [x] SubTask 4.2.3: 逐一对比找出不一致
  - [x] SubTask 4.2.4: 输出不一致清单

- [x] Task 4.3: TypeScript 严格模式评估（只报告不修改）
  - [x] SubTask 4.3.1: 备份 tsconfig.json，临时开启 strict: true
  - [x] SubTask 4.3.2: 运行 `npm run typecheck` 记录新增错误
  - [x] SubTask 4.3.3: 恢复 tsconfig.json
  - [x] SubTask 4.3.4: 报告错误数量和类型分布

## 阶段五：冒烟测试

- [x] Task 5.1: 启动验证
  - [x] SubTask 5.1.1: 启动后端确认无 WARNING/ERROR
  - [x] SubTask 5.1.2: 启动前端确认 Vite 正常
  - [x] SubTask 5.1.3: curl /api/health 确认返回 ok

- [x] Task 5.2: API 端点冒烟
  - [x] SubTask 5.2.1: 列出所有 GET 端点
  - [x] SubTask 5.2.2: curl 逐个访问记录 HTTP 状态码
  - [x] SubTask 5.2.3: 标记非 200 端点（排除预期 401/403）并分析原因

- [x] Task 5.3: 前端页面冒烟
  - [x] SubTask 5.3.1: curl http://localhost:3000 确认返回 HTML
  - [x] SubTask 5.3.2: curl 关键静态资源路径确认 200
  - [x] SubTask 5.3.3: 检查 HTML 引用资源路径可加载

## 阶段六：最终报告

- [x] Task 6.1: 汇总修复成果（本次新修复内容 + 验证结果）
- [x] Task 6.2: 汇总未修复问题清单（原因/风险等级/建议处理时间）
- [x] Task 6.3: 项目健康度评分（7 维度 1-10 分 + 理由）
- [x] Task 6.4: 后续建议（按优先级 + 预计工作量 + 排序理由）

# Task Dependencies
- Task 2.1 完成后才能运行 Task 5.1（前端依赖 npm 依赖完整性）
- Task 2.2/2.3/2.4 完成后才能运行 Task 5.3（前端冒烟依赖路由和代码修复）
- 阶段三/四（审查类）可与阶段二并行（只读不改），但报告需在阶段六前完成
- Task 4.3 必须在所有代码修改完成后执行（评估最终代码状态）
- 阶段五必须在所有代码修改完成后执行
- 阶段六依赖所有前置阶段完成
