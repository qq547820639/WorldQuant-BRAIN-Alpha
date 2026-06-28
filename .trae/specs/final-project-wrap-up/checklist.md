# Checklist

## 阶段一：保护现有修复成果
- [ ] git status --short 输出已查看，修改/新增文件数量已统计
- [ ] git diff --stat 完整文件列表已输出
- [ ] 7 个关键文件全部在变更列表中（或缺失原因已分析）
  - [ ] tests/test_quality_gate.py
  - [ ] brain_alpha_ops/config_models.py
  - [ ] scripts/final_release_gate/_manifest.py
  - [ ] scripts/check_module_size.py
  - [ ] scripts/check_review_gap_closure_tracker_helpers/_status.py
  - [ ] .gitignore
  - [ ] brain_alpha_ops/web/react_app/package.json
- [ ] README.md / pyproject.toml / package.json 版本号已读取
- [ ] 三处版本号统一为 0.5.0
- [ ] 代码中所有 os.environ / os.getenv / process.env 引用已扫描
- [ ] .env.example 已创建，包含所有环境变量名 + 用途说明
- [ ] .env.example 中敏感变量使用 YOUR_xxx_HERE 占位符

## 阶段二：修复已知缺陷（P2）
- [ ] npm audit 初始漏洞清单已输出（包名/严重程度/是否有修复版本）
- [ ] npm audit fix 已运行（不加 --force），修复数量已报告
- [ ] npm audit 剩余漏洞已报告
- [ ] critical 级剩余漏洞已列出包名和影响范围
- [ ] npm audit fix 后 npm run typecheck + npm run lint 无回归
- [ ] 前端路由配置文件已读取
- [ ] NotFound 组件已创建（"页面未找到" + 返回首页链接 + 现有风格）
- [ ] 路由表末尾已添加 path="*" 通配路由
- [ ] 现有路由未受影响（typecheck + lint 通过）
- [x] npm run lint 中 no-base-to-string warnings 已逐个修复
- [x] 修复后 no-base-to-string warnings 消失，其他 warning 数量不变
- [ ] src/api/jobCancel.ts 已读取
- [ ] src/hooks/useApi.ts 已读取
- [ ] jobCancel.ts 已改造使用 useApi 封装
- [ ] 取消功能错误处理/超时处理与原来一致
- [ ] jobCancel.ts typecheck + lint 无回归
- [ ] test_react_status_summaries_do_not_cap_reason_lists 失败原因已分析
- [ ] 已确认是测试问题还是业务代码缺失
- [ ] 测试已修正或业务代码缺失已报告
- [ ] 该测试通过

## 阶段三：深度安全审查
- [ ] 硬编码凭证扫描完成（API Key/Token/Secret/密码/BRAIN 凭据）
- [ ] .env 在 .gitignore 中已确认
- [ ] 前端代码未泄露后端密钥已确认
- [ ] 凭证扫描结果已输出
- [ ] 所有后端 API 端点已列出
- [ ] 每个端点的 Content-Type/请求体大小/类型范围/文件上传校验已检查
- [ ] 输入校验检查结果表格已输出
- [ ] 所有设置 CORS 头的代码位置已找到
- [ ] 白名单一致性和宽松配置已检查
- [ ] CORS 检查结果已输出
- [ ] dangerouslySetInnerHTML 使用已检查
- [ ] 后端返回数据 HTML 转义已检查
- [ ] CSP 配置已检查
- [ ] XSS 检查结果已输出

## 阶段四：代码质量深度审查
- [ ] 5 类关键路径代码已找到（认证/持久化/BRAIN API/生成管线/评分）
- [ ] 裸 except / 过宽 except Exception 已检查
- [ ] 吞掉异常的高风险点已标记
- [ ] 异常处理审查表格已输出（文件:行号/关键路径/当前处理/风险等级/建议）
- [ ] 前端所有 API 调用已提取（URL/方法/参数）
- [ ] 后端所有路由定义已提取（URL/方法/期望参数）
- [ ] 前后端接口不一致已找出
- [ ] 不一致清单已输出
- [ ] tsconfig.json 已备份，strict: true 已临时开启
- [ ] npm run typecheck 新增错误已记录
- [ ] tsconfig.json 已恢复
- [ ] strict 模式评估报告已输出（错误数量 + 类型分布）

## 阶段五：冒烟测试
- [ ] 后端已启动，无 WARNING/ERROR
- [ ] 前端已启动，Vite 正常
- [ ] curl /api/health 返回 ok
- [ ] 所有 GET 端点已列出
- [ ] curl 逐个访问 GET 端点，HTTP 状态码已记录
- [ ] 非 200 端点已标记（排除预期 401/403）并分析原因
- [ ] curl http://localhost:3000 返回 HTML
- [ ] curl 关键静态资源路径返回 200
- [ ] HTML 引用资源路径可加载已确认

## 阶段六：最终报告
- [ ] 修复成果总结已输出（本次新修复 + 验证结果）
- [ ] 未修复问题清单已输出（原因/风险等级/建议处理时间）
- [ ] 项目健康度评分已输出（7 维度 1-10 分 + 理由）
- [ ] 后续建议已输出（按优先级 + 预计工作量 + 排序理由）
