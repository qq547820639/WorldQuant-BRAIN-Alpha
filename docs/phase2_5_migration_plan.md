# 2.5 迁移与兼容策略

> **日期**: 2026-05-15  
> **策略核心**: 后端先行 → 前端基于新契约重构 → 渐进切换，每步可回滚

---

## 一、迭代节奏

```
                           Week 1           Week 2           Week 3
Phase A (P0 致命)   ████████████
Phase B (P1 契约)                    ████████████
Phase C (P1 状态机)                  ████████████████
Phase D (P2 基建)                                     ████████████
Frontend P0                               ████████
Frontend P1                                    ████████████████
Frontend P2                                         ████████████
```

**铁律**:
1. 后端每个 Phase 完成后，前端**立即**基于新契约对接（不等所有 Phase 完成）
2. 前端重构按 P0 → P1 → P2 顺序，**每模块完成后独立回归**
3. 后端新增字段保持**向后兼容** — 老前端不受影响

---

## 二、Phase A: 致命缺陷修复 (Day 1-2)

### 任务序列

| 序号 | 任务 | 文件 | 风险 | 验证 |
|------|------|------|------|------|
| A1 | 实现 `check_candidate()` | web.py +25行 | 低 | curl POST /api/check 返回完整结果 |
| A2 | 修复 SSE `await` 语法 | index.html 1行 | 极低 | 浏览器 Console 无 SyntaxError |
| A3 | submit_batch 幂等 | web.py +5行 | 低 | 重试批量提交不重复 |

**兼容性**: 全部向后兼容。A1 只新增路由功能，A2 纯修复，A3 不影响现有调用。

**回滚**: `git revert` 单个 commit。

---

## 三、Phase B: 契约对齐 (Day 3-5)

### B1-B3: 新增字段（无破坏性）

| 子任务 | 新增字段 | 老前端行为 |
|--------|---------|----------|
| B1 | `checked_at`, `is_stale` | 忽略新字段，功能不受影响 |
| B2 | `label_cn`, `suggestion` | 忽略新字段，仍使用 `humanCheckName()` 硬编码 |
| B3 | `phase_label` | 忽略新字段，仍使用 `phaseName()` 硬编码 |

**策略**: 新增字段不删老字段，给前端迁移留缓冲期。

### B4: error_code 新增

所有 POST 错误响应增加 `error_code`：

```json
// 老响应（保持兼容）
{"ok": false, "error": "已有生产任务正在运行"}

// 新响应（增加字段）
{"ok": false, "error": "...", "error_code": "CONFLICT_RUNNING", "error_id": "uuid"}
```

**前端兼容**: `data.ok === false` 时优先读 `error_code` 获取用户提示，fallback 读 `error`。

### B5-B6: 字段消费与补充

| 子任务 | 改动 | 兼容性 |
|--------|------|--------|
| B5 `continuousMode` | 后端消费 `payload.continuousMode` | 老前端传此字段即生效 ✅ |
| B6 stats 字段 | progress.data 增加 stats 子对象 | 老前端忽略 ✅ |

### B 阶段前端对接 (Day 4-5)

| 序号 | 前端任务 | 依赖后端 |
|------|---------|---------|
| F-B1 | `api-client.js` 增加 error_code → 用户消息映射 | B4 完成 |
| F-B2 | `views/detail.js` 使用 `check.label_cn` 代替 `humanCheckName()` | B2 完成 |
| F-B3 | 所有进度渲染使用 `progress.phase_label` 代替 `phaseName()` | B3 完成 |
| F-B4 | `isFreshCheck()` 改为读取 `result.is_stale` | B1 完成 |

---

## 四、Phase C: 状态机/校验补全 (Day 6-10)

### C1: BLOCKED 状态 (关键)

**后端**: 在 `lifecycle_from_job` 中增加 `status_category: "blocked"`。

**前端同步**:

```
前端 P0-①: views/results.js → failedRows() 正则增加 BLOCKED 匹配
前端 P0-②: views/results.js → BLOCKED 子视图 + 阻断原因列
前端 P0-③: views/detail.js → BLOCKED 详情弹窗
```

### C2: 配置校验

**后端**: `run_config_from_payload` 增加枚举值校验。

**兼容性**: **可能破坏** — 如果老前端发送了非标准枚举值（如 `type: "UNKNOWN"`），新后端会返回 400。

**迁移**: 先检查前端 `collectPayload()` 和 `applyPreset()` 中的枚举值是否均在合法范围内 → 确认后端预设和前端预设完全对齐 → 再上线校验。

### C3: Fields/Operators 刷新非静默

**后端**: 移除 `pass` 改为 `logger.warning` + 使用缓存旧数据。

**兼容性**: 完全向后兼容。

### C4: 文件归档

**后端**: `maybe_archive_lifecycle()` 自动归档。

**兼容性**: 完全透明，不影响数据读取。

---

## 五、Phase D: 基建增强 (Day 11-14)

### D1: 预设配置外部化

**后端**: 新增 `config/presets.json` + `GET /api/presets`。

**前端同步**:

```
前端 P1-④: 删除 applyPreset() 中的硬编码 map → 从 GET /api/presets 加载
前端 P1-⑤: 删除 syncPresetFromSettings() → 后端 settings 响应中包含 preset_id
```

### D2: 异常类层次

**后端**: 新增 `brain_alpha_ops/errors.py`。

**兼容性**: 完全向后兼容（继承 Exception，catch 逻辑不受影响）。

---

## 六、灰度与回滚

### 6.1 新旧前端并存策略

由于前端是单文件 `index.html`，无法做 A/B 测试。策略改为：

1. **开发分支**：`index.html` 持续重构
2. **每完成一个模块** → 本地回归测试通过 → merge
3. **保留 `index_backup_*.html`** → 出问题时直接恢复

### 6.2 新旧接口并存

| 接口变化类型 | 策略 |
|-------------|------|
| 新增字段 | 直接加入响应，老前端忽略 ✅ |
| 新增可选参数 | 直接加入，老前端不传用默认值 ✅ |
| 修改字段名 | **不做** — 保持旧名 + 新增别名 |
| 修改字段类型 | **不做** — 新增 `_v2` 字段 |
| 新增错误码 | error_code 新增枚举值 ✅ |

### 6.3 回滚流程

```
发现问题
  ├── 前端问题 → 恢复 index_backup_*.html → 重启服务
  └── 后端问题 → git revert → 重启服务
```

**服务重启方式**: `POST /api/shutdown` → 重新 `python launch_web.py`。

---

## 七、前端模块重构顺序

按**依赖关系**自底向上重构：

```
第1层 (基础设施, 无依赖):
  ├── api-client.js        ← 所有 API 调用的基础
  ├── utils.js             ← escapeHtml, formatScore
  └── state.js             ← AppState 管理器

第2层 (组件, 仅依赖第1层):
  ├── components/toast.js
  ├── components/spinner.js
  ├── components/modal.js
  ├── components/progress.js
  └── components/table.js

第3层 (视图, 依赖第1+2层):
  ├── views/detail.js      ← 被多个视图引用，优先
  ├── views/monitor.js     ← 详情页依赖
  ├── views/candidates.js
  ├── views/results.js     ← P0 修复 BLOCKED
  ├── views/cloud.js
  ├── views/lifecycle.js
  └── views/charts.js

第4层 (组装):
  └── app.js               ← 初始化所有模块
```

**每一层完成后验证**:

```bash
python -m compileall brain_alpha_ops/  # Python 语法
# 前端: 打开浏览器 → 检查 Console 无错误 → 走一轮完整流程
```

---

## 八、风险矩阵

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| `check_candidate()` 实现引入新 bug | 低 | 中 | 充分测试 + 复用现有函数 |
| 配置校验上线后拒绝老前端请求 | 中 | 高 | 先对齐前端枚举值再上线 |
| 文件归档误删数据 | 低 | 高 | 归档前备份 + 30天保留窗口 |
| 模块化后 .exe 打包失败 | 中 | 中 | 构建脚本先行验证 |
| `is_stale` 时区计算偏差 | 低 | 低 | 统一 UTC |
| 批量提交幂等与现有 `SUBMIT_LOCK` 冲突 | 低 | 低 | 幂等仅在单次 batch 内生效 |

---

## 九、交付里程碑

| 里程碑 | 内容 | 验收标准 |
|--------|------|---------|
| M1 (Day 2) | Phase A 完成 | 单条检查可用 + SSE 无错误 + 批量提交不重复 |
| M2 (Day 5) | Phase B 完成 | 所有 API 响应含 error_code + label_cn + phase_label |
| M3 (Day 7) | 前端 P0 完成 | BLOCKED 可见 + 批量提交失败明细可展开 |
| M4 (Day 10) | Phase C 完成 | 配置校验上线 + 文件自动归档 |
| M5 (Day 12) | 前端 P1 完成 | 模块拆分完成 + api-client 统一 |
| M6 (Day 14) | Phase D + 前端 P2 完成 | 预设外部化 + 异常类层次 + .exe 打包验证 |

---

## 十、排期确认清单

请确认以下关键决策：

- [ ] Phase A Day 1-2: 致命修复优先 — `check_candidate()` + SSE + 幂等
- [ ] Phase B Day 3-5: 契约对齐（新增字段向后兼容）
- [ ] 前端 P0 Day 5-7: BLOCKED + 批量提交失败明细
- [ ] 前端重构按"后端先行"原则，每 Phase 后立即对接
- [ ] 单文件 .exe 打包在 M5/M6 节点验证
