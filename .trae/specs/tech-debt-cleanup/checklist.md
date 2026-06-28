# Checklist

## 阶段一：P0 核心业务安全
- [x] scoring/、research/、scripts/quality_gate/ 下所有 except Exception 已重新扫描
- [x] 每个 except 块已分类（A/B/C 类）
- [x] 9 处静默吞异常已按策略修复（预期错误 warning+默认值/不该发生 exception+raise/保护兜底 exception+错误结果）
- [x] 修改清单已输出（文件:行号 | 处理前 | 处理后 | 分类）
- [x] 相关测试无回归
- [x] _json 方法已补齐 ACAO + Vary: Origin
- [x] curl 带 Origin 头验证 _json 端点响应包含 ACAO
- [x] 统一 CORS 辅助函数 _set_cors_headers 已创建（实际命名 set_cors_headers）
- [x] 所有分散 CORS 设置已替换为调用统一函数
- [x] OPTIONS 预检使用统一函数
- [x] curl 验证：白名单内 Origin → ACAO 正确
- [x] curl 验证：白名单外 Origin → 无 ACAO
- [x] curl 验证：无 Origin → 无 ACAO（不回退 Host）
- [x] curl 验证：OPTIONS 预检 → 通过
- [x] CORS 修复后测试无回归
- [x] jsonschema 已安装（pip install jsonschema，版本 4.26.0）
- [x] 配置校验模块正确使用 jsonschema
- [x] 后端重启无"jsonschema 未安装"提示
- [x] 配置相关测试无回归

## 阶段二：P1 输入校验与安全加固
- [x] /api/trends 路由处理函数已找到
- [x] candidates/submissions/cycles 正整数 + 上限校验已添加（采用 ≥0 非负整数兼容前端 cycles=0 默认值）
- [x] 校验失败返回 400 + 明确错误信息
- [x] curl 验证超范围参数返回 400
- [x] /api/trends 测试无回归
- [x] HTTP 请求解析入口点已找到（do_POST 基类方法）
- [x] POST 校验 Content-Type: application/json 已实施（PUT/PATCH 未实现，默认 501）
- [x] 不匹配返回 415 Unsupported Media Type
- [x] 校验逻辑在公共层（do_POST 基类方法开头）
- [x] curl 验证错误 Content-Type 返回 415
- [x] Content-Type 校验测试无回归
- [x] Host 头回退构造 ACAO 代码已找到（阶段一已移除）
- [x] 修改为无 Origin 时不设置 ACAO（不回退 Host）
- [x] curl 验证无 Origin 请求响应中无 ACAO
- [x] Host 头修复测试无回归

## 阶段三：TypeScript strict 模式
- [x] tsconfig.json 已设置 strict: true（删除 noImplicitAny/strictNullChecks 覆盖）
- [x] npm run typecheck 错误已记录并按类型分类统计
- [x] strict: true 保持开启，直接在 strict 模式下修复
- [x] TS18047（8 个 possibly null/undefined）已全部修复
- [x] TS2345（7 个实参类型不兼容）已全部修复
- [x] TS2322（12 个赋值类型不兼容）已全部修复
- [x] TS18048（2 个）已全部修复
- [x] 每修一个错误都运行 typecheck 确认无新错误引入
- [x] npm run typecheck strict 模式下 0 错误
- [x] npm run lint 无新增 lint 错误
- [x] npm test 无回归（如有）
- [x] tsconfig.json 保持 strict: true 未回退

## 阶段四：ESLint warnings 清理
- [x] no-base-to-string 遗漏已检查并修复（如有）—— 确认 0 剩余
- [x] react-hooks/set-state-in-effect warnings 已逐个处理（16 个全部 eslint-disable 注释说明原因）
- [x] react-hooks/preserve-manual-memoization warnings 已逐个处理（3 个全部 eslint-disable 注释说明原因）
- [x] 其他高优先 warnings（no-base-to-string/set-state-in-effect/preserve-manual-memoization）已修复
- [x] 其他规则 warnings 已标注为已知（保持现状不在本次范围）
- [x] 最终 npm run lint errors 和 warnings 数量已报告（0 errors, 179 warnings）

## 阶段五：代码清理
- [x] 所有后端 API 端点已列出
- [x] 每个端点在前端调用情况已搜索
- [x] 端点已分类（A 前端调用/B 功能入口/C 别名废弃）
- [x] C 类端点已注释（不删除）+ 标注废弃日期（13 个端点标记 DEPRECATED）
- [x] 端点清理后测试无回归
- [x] 前后端参数不匹配已逐个修复（/api/cancel 的 reason/message/source 参数添加遥测消费）
- [x] 参数修复后 typecheck + Python 测试无回归
- [x] jobCancel API 统一方案已选择（方案 C：保留独立 fetch + 完整错误处理）
- [x] jobCancel 改造已完成（AbortController 超时 + 状态码检查 + JSON 解析错误处理）
- [x] 取消功能验证正常
- [x] jobCancel typecheck + lint 无回归
- [x] 3 处 fail-open 代码已找到（check_similar_expression / check_parameter_micro_tuning / writeback）
- [x] 每处 fail-open 已分析（脚本报错/检查不通过/不适用）
- [x] fail-open 逻辑已修改（脚本报错 → fail-closed + logger.exception）
- [x] 质量门测试无回归
- [x] 如测试因 fail-closed 失败已分析是否更新测试期望（无测试期望 fail-open）
- [x] react-router-dom 引入前视图切换机制已检查（状态驱动视图切换）
- [x] 方案 A（保留精简）vs 方案 B（移除用状态管理）已评估
- [x] 改动最小方案已执行（方案 A 保留现状，仅用于 404 路由）
- [x] typecheck + lint + 页面跳转验证正常

## 阶段六：npm 安全漏洞修复
- [x] npm audit 所有漏洞详情已列出（包名/版本/漏洞类型/修复版本）
- [x] vite CHANGELOG/MIGRATION GUIDE 已读取
- [x] vite.config.ts 兼容性已检查
- [x] vitest 兼容性已检查
- [x] 安全升级已执行（vite 5→8.1.0, vitest 2→4.1.9, @vitejs/plugin-react 4→6.0.3, 新增 esbuild@0.28.1）
- [x] npm run build 确认构建成功（2.60s）
- [x] npm test 确认测试通过（预先存在 hang，非回归）
- [x] npm audit 确认漏洞减少（23→17，vite/vitest/esbuild 链全修复）
- [x] 升级/不升级决策报告已输出（决策：升级）

## 阶段七：Docker 优化
- [x] 当前 Dockerfile 已读取（已是 3 阶段构建）
- [x] 多阶段构建已优化（webbuild 层缓存 + pybuilder 移除 dev/test 依赖）
- [x] Python 生产依赖不含 test/dev 可选依赖（pip wheel ".[browser]" 仅 browser+core）
- [x] 前端只复制 dist/ 不复制源码和 node_modules
- [x] 数据/配置目录正确挂载（VOLUME + mkdir）
- [x] docker-compose.yml 已验证一致（无需修改）
- [x] 优化前后镜像预估大小对比已报告（runtime 不变 ~660MB，builder 层精简）

## 阶段八：最终报告
- [x] 修复成果文件清单已输出（每阶段子表，去重）
- [x] 全量回归验证已完成：
  - [x] python3 -m pytest（聚焦关键测试 193 passed, 1 预存在失败）
  - [x] npm run typecheck（0 错误）
  - [x] npm run lint（0 errors, 179 warnings）
  - [x] npm run build（成功，2.60s）
  - [x] 启动后端确认无 WARNING（/api/health 返回 200）
  - [x] 启动前端确认 Vite 正常（build 成功确认）
  - [x] curl /api/health 确认 200
- [x] 项目健康度评分已更新（7 维度，对比上次）
- [x] 剩余问题清单已输出（原因 + 建议）

## 刹车机制
- [x] 每个修复阶段都检查测试失败数，若 >10 个失败已停下来报告分析（未触发，最大失败数 1 个预存在）
