# BRAIN Alpha Ops 生产 E2E 测试报告

- 测试时间：2026-05-28 10:18-12:04（Asia/Shanghai）
- 浏览器：真实 Google Chrome（通过 `playwright-cli`，配置见 `.playwright-cli/chrome-extra-config.json`）
- 本地服务：http://127.0.0.1:18766/
- 环境：production / https://api.worldquantbrain.com
- 账号：真实生产账号（邮箱与密码均未写入报告）
- 证据目录：`data/e2e_screenshots/`

## 结果汇总

| 步骤 | 结果 | 关键证据 |
|---|---|---|
| 1. 页面加载 | 通过 | 标题、生产环境标识、工作台控制面板、视图导航加载成功；可见浏览器已复核当前页面，favicon 正常显示。 |
| 2. 连接测试 | 通过 | Header 显示 `已连接 — production · session_cookie`，`userProfile` 当时显示 `身份待同步`；旧 `offline --` 未再出现。后续本地修复已让连接态在 profile 区也显示明确连接信息，并在可见浏览器中复核。 |
| 3. 云端同步 | 通过 | 最新同步 `job_0005` 完成：`scanned=23254, added=0, updated=0, skipped=23254, failed=0`；官方上下文字段 7780、算子 66；`data/jobs_sync.json` 约 160 KB。 |
| 4. 视图导航 | 通过 | 候选池、达标、可提交、已提交、云端数据、研究记忆等视图均可切换；提交按钮在无选择时禁用。 |
| 5. 搜索功能 | 通过 | 搜索 `rank` 后搜索框状态保持，空结果展示稳定空态与恢复操作。 |
| 6. 图表渲染 | 通过 | Chart.js 缺失时本地 canvas 降级图表可见，表格视图可返回。 |
| 7. 插件控制 | 通过 | 策略插件开关与输入框 enabled/disabled 联动；摘要卡在开启时显示“已开启，未配置插件规格”，关闭时显示“关闭时不会加载插件规格”。 |
| 8. 错误恢复 | 通过 | 空达标检查只显示 `暂无达标 Alpha 可检查。`，不误建新检查任务；生产 `job_0008` 可安全停止，提交仍禁用。 |

## 生产流程结论

- 已使用真实凭据连接生产 BRAIN API，并完成真实云端同步。
- 已启动修复后的真实生产搜索：`job_0008`。
- `job_0008` 已按安全约束手动停止，最终状态为 `stopped`，`cancel=true`，`error=""`。
- 本次生产 run 摘要：`produced_count=3`、`official_validation_passed=1`、`submitted_this_run=0`、`auto_submitted=0`。
- 未发现 `data/submissions.jsonl`，本次没有写入提交账本，也没有触发真实提交。
- 最新候选存在高相似风险：`max_similarity=1.0`、`level=high`，因此继续阻断提交是正确行为。

## 可见浏览器复核补充

- 后续已用可见浏览器打开本地控制台 `http://127.0.0.1:8765/`，复核页面首屏显示 `BRAIN Alpha Ops`。
- 已复核 favicon 不再 404，连接区为 `form`，`connTestBtn` 的类型为 `submit`，回车可触发测试连接。
- 已切换到“生命周期”视图，复核“官方表达式验证通过”和“官方回测完成”标签不会混读。
- 可见浏览器截图已在会话中展示；受本地写入权限限制，截图文件未另存到仓库，因此仓库内证据仍以 `data/e2e_screenshots/` 的既有截图和自动汇总报告为准。

## 双重验证摘要

| 操作 | 前端验证 | 后端/账本验证 |
|---|---|---|
| 页面加载 | 主工作台、生产环境选项、核心动作和视图导航可见 | 本地服务在 `127.0.0.1:18766` 响应；当次 Chrome 控制台仅见 favicon 404 和密码框表单提示。后续本地修复已补 favicon 和连接表单语义，并已在可见浏览器中复核。 |
| 测试连接 | Header 从未连接态更新为 `已连接 — production · session_cookie` | 生产认证使用 session cookie；本地会话链路包含 Cookie、CSRF 和 `stream_token`。 |
| 云端同步 | 同步期间冲突操作锁定，完成后云端视图显示 `99+` | `data/jobs_sync.json` 最新 `job_0005` 完成，扫描 23254 条，官方上下文刷新成功。 |
| 生产搜索 | 启动后生产/同步/检查/提交互斥；停止后按钮恢复 | `data/jobs_production.json` 最新 `job_0008` 为 stopped，结果压缩后仍保留摘要和候选预览。 |
| 质量门槛 | 候选进入研究态但不可提交 | 本地预筛通过，但 local backtest 换手率超 70%，缺少 official metrics/pass/economic logic/self-correlation proxy，质量门槛未放行。 |
| 相似度阻断 | 提交按钮禁用且无可提交选择 | 候选 `cloud_correlation_risk.max_similarity=1.0`，超过 `<0.9` 安全要求，阻断提交。 |
| 插件控制 | 开关、输入框、摘要卡即时同步 | `collectPayload()` 关闭时不加载插件规格，避免误注入策略插件。 |
| 错误恢复 | 空达标检查显示 toast，不崩溃 | `data/jobs_check.json` 未新增误触发任务；无 submit 请求、无提交账本。 |

## 安全约束验证

| 约束 | 结果 |
|---|---|
| 默认不自动提交 | 通过：`auto_submitted=0`，自动提交开关未打开。 |
| 提交前必须同步云端 | 通过：真实同步 `job_0005` 在生产 run 前完成，run 内加载 23243 条本地云端缓存。 |
| 通过达标检查后才提交 | 通过：无 submission-ready 选择，提交按钮禁用。 |
| 每日上限 3 次 | 通过：本次 `submitted_this_run=0`，未消耗当日提交额度。 |
| 相似度 `<0.9` 阻断 | 通过：`max_similarity=1.0` 被记录为 high risk，未提交。 |
| 审计追踪 | 通过：无提交即无 `data/submissions.jsonl`；生产任务和同步任务分别写入本地 job 账本。 |

## 交互与验证逻辑分析

- 前端互斥控制有效：生产、同步、检查、提交共享 busy 状态，避免重复点击和冲突操作。
- 后端会话链路较完整：普通 API 走 session/CSRF，SSE 走同一 session 下的 `stream_token`，写操作有防重放校验。
- 提交流程是 fail-closed：缺官方 ID、未 submission-ready、未同步云端、云端状态已提交、高相似度或官方检查失败都会阻断。
- 后续本地修复已将“官方表达式验证通过”和“官方回测完成”拆分为不同标签；账本仍会同时记录 `official_validation_passed=1` 与 `officially_simulated=0` 这两种不同阶段，二者不应再被混读。该 UI 修复已在可见浏览器中复核。
- 空达标检查恢复路径正确，但 toast 文案可加上下一步建议，例如“请先运行生产搜索或切换到候选池”。

## 优化方案

1. 将生产进度流的 SSE 状态暴露到 UI：显示“实时流 / 轮询降级 / 已恢复”，便于用户判断任务是否仍在健康推进。
2. 已在本地代码中区分“官方验证通过”和“官方回测完成”：候选生命周期与详情弹窗使用不同标签，避免把 validation pass 误读为可提交；已在可见浏览器中复核。
3. 云端快照继续保持 compact 存储，并对表格详情做懒加载，降低 2 万级云端缓存对 UI 的压力。
4. 给高相似阻断增加可操作建议：展示匹配 Alpha ID、相似度、建议变异方向和“重新生成不同表达式”入口。
5. 对空达标检查做前端预禁用：当达标视图计数为 0 时直接禁用检查按钮，同时保留后端 `candidate_ids` 校验。
6. 已在本地代码中为 favicon 和登录字段补齐细节：添加 favicon，凭据输入包入表单并支持回车触发测试连接；已在可见浏览器中复核。
7. 已新增报告自动汇总基础版：`docs/E2E_ARTIFACT_SUMMARY_20260528.md` / `.json` 自动汇总 job 账本摘要、控制台错误、截图清单，并在输出前脱敏。
8. 为 `playwright-cli` 保留当前 Chrome 配置，并增加固定截图命名规范，后续可直接复用真实浏览器会话。

## 验证命令结果

- `pytest` 回归：1085 passed, 8 skipped。
- `scripts/quality_gate.py --final-release --skip-tests --json`：passed，包含红线 76/76、contract、gap、final release、frontend、web console contract、secret scan。
- `brain_alpha_ops/web/build_inline.py --check --json`：passed。
- `scripts/check_module_size.py`：passed。
- `scripts/check_frontend_innerhtml.py`：passed。
- `scripts/check_web_console_contract.py --html brain_alpha_ops/web/index.html --json`：passed，覆盖 favicon、连接表单、测试连接 submit 和生命周期视图 wiring。
- `scripts/summarize_e2e_artifacts.py --root . --evidence-dir data/e2e_screenshots --output-json docs/E2E_ARTIFACT_SUMMARY_20260528.json --output-md docs/E2E_ARTIFACT_SUMMARY_20260528.md --json`：passed。
- `scripts/final_release_gate.py`、`scripts/check_brain_contract.py`、诊断报告检查已在交付收口中再次执行并通过。

## 证据文件

- `data/e2e_screenshots/page-2026-05-28T03-47-28-760Z.yml`
- `data/e2e_screenshots/page-2026-05-28T04-00-25-269Z.yml`
- `data/e2e_screenshots/page-2026-05-28T04-02-26-552Z.yml`
- `data/e2e_screenshots/page-2026-05-28T04-03-44-263Z.yml`
- `data/e2e_screenshots/page-2026-05-28T04-04-11-373Z.png`
- `data/e2e_screenshots/console-2026-05-28T03-47-28-618Z.log`
- `data/e2e_screenshots/20260528-production-e2e-summary.json`
- `data/jobs_sync.json`
- `data/jobs_production.json`
- `data/jobs_check.json`
- `docs/E2E_ARTIFACT_SUMMARY_20260528.md`
- `docs/E2E_ARTIFACT_SUMMARY_20260528.json`
