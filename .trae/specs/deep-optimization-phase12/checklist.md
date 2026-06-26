# Checklist

> 每项验证后勾选。失败则新建 tasks.md 修复项并重验。

## 工作流 A：scripts 拆分

- [ ] `scripts/check_live_submit_readiness/` 子包存在且 `__init__.py` 含 `__all__`，所有子模块 ≤ 350 行
- [ ] `scripts/check_parameter_traceability/` 子包存在且 `__init__.py` 含 `__all__`，所有子模块 ≤ 350 行
- [ ] `scripts/check_review_gap_closure_tracker/` 子包存在且 `__init__.py` 含 `__all__`，所有子模块 ≤ 350 行
- [x] `scripts/final_release_gate/` 子包存在且 `__init__.py` 含 `__all__`，所有子模块 ≤ 350 行
- [ ] `scripts/quality_gate/` 子包存在且 `__init__.py` 含 `__all__`，所有子模块 ≤ 350 行
- [ ] `scripts/check_prod_defect_tracking/` 子包存在且 `__init__.py` 含 `__all__`，所有子模块 ≤ 350 行
- [ ] `scripts/check_tracked_data_inventory/` 子包存在且 `__init__.py` 含 `__all__`，所有子模块 ≤ 350 行
- [ ] `scripts/verify_canonical_compliance/` 子包存在且 `__init__.py` 含 `__all__`，所有子模块 ≤ 350 行
- [ ] `scripts/check_review_gap_closure_tracker_helpers/` 子包存在且 `__init__.py` 含 `__all__`，所有子模块 ≤ 350 行
- [ ] `scripts/check_frontend_surface_parity/` 子包存在且 `__init__.py` 含 `__all__`，所有子模块 ≤ 350 行
- [ ] 10 个 scripts 的原 `.py` 文件均改为 thin shim 或删除，外部导入路径不变
- [ ] `python3 -c "from scripts.check_live_submit_readiness import main"` 等导入验证全部通过

## 工作流 B：brain_alpha_ops 拆分

- [ ] `brain_alpha_ops/web_candidates/simulation_state/` 子包存在且 `__init__.py` 含 `__all__`，所有子模块 ≤ 350 行
- [ ] `brain_alpha_ops/web_cloud/sync_job/_service/` 子包存在且 `__init__.py` 含 `__all__`，所有子模块 ≤ 350 行
- [x] `brain_alpha_ops/web/__init__.py` 行数 ≤ 350（逻辑抽离到 `_reexports.py` 或等价）
- [ ] `brain_alpha_ops/research/auto_calibrator/` 子包存在且 `__init__.py` 含 `__all__`，所有子模块 ≤ 350 行
- [ ] `brain_alpha_ops/brain_api/official_simulation/` 子包存在且 `__init__.py` 含 `__all__`，所有子模块 ≤ 350 行
- [ ] `brain_alpha_ops/research/calibration_engine/` 子包存在且 `__init__.py` 含 `__all__`，所有子模块 ≤ 350 行
- [ ] `brain_alpha_ops/research/repository/` 子包存在且 `__init__.py` 含 `__all__`，所有子模块 ≤ 350 行
- [ ] `brain_alpha_ops/web/misc/web_facade_bindings/` 子包存在且 `__init__.py` 含 `__all__`，所有子模块 ≤ 350 行
- [ ] `brain_alpha_ops/web/security/web_session/` 子包存在且 `__init__.py` 含 `__all__`，所有子模块 ≤ 350 行
- [ ] `brain_alpha_ops/research/expression_index/` 子包存在且 `__init__.py` 含 `__all__`，所有子模块 ≤ 350 行
- [ ] 10 个 brain_alpha_ops 文件的原 `.py` 均改为 thin shim 或删除，外部导入路径不变
- [ ] logger 名硬编码为原模块名（拆分后日志前缀不变）
- [ ] monkeypatch 兼容性：`_pkg()` 模式与显式 re-export 私有符号保持

## 工作流 C：缺陷闭合

- [ ] DEF-019：`python3 -m pytest tests/test_web_backtest_slots.py -v` 全绿（无 0-arg API 失败）
- [ ] DEF-020：`python3 -m pytest tests/test_comprehensive_scoring_edge_cases.py --collect-only` 无 ImportError
- [x] DEF-021：`npm run test` 在 `brain_alpha_ops/web/react_app` 执行并记录结果（全绿或环境限制说明）
- [ ] DEF-022：`npm run typecheck` 在 `brain_alpha_ops/web/react_app` 退出 0，无 TS6133 `environment` 警告

## 工作流 D：验证与提交

- [ ] `scripts/check_module_size.py:BASELINE_LINE_LIMITS` 不再含 20 个已拆分文件条目
- [ ] `python3 scripts/check_module_size.py --json` 的 `findings` 对 20 个目标文件返回空
- [ ] `DEFECT_TRACKING.md` 中 DEF-019/020/022 状态为 `closed`
- [ ] `DEFECT_TRACKING.md` 摘要表 `Open` 计数更新（0 或 1，取决于 DEF-021）
- [ ] `python3 -m pytest tests/ --ignore=tests/test_read_jsonl_tail.py --ignore=tests/test_quality_gate.py --ignore=tests/test_official_scoring_system.py -q --tb=short` 无新增失败
- [ ] `python3 -m pytest tests/test_credential_leak_regression.py -q` 全绿（无凭据泄露回归）
- [ ] 20 个拆分子包 `from ... import *` 正常工作
- [ ] `git push origin main` 推送成功

## 全局约束

- [ ] 所有新增/修改的 Python 文件 ≤ 350 行
- [ ] 所有新增/修改的前端文件 ≤ 400 行
- [ ] 无新增运行时依赖（`pyproject.toml` / `package.json` 不变）
- [ ] 无凭据字面量泄露（邮箱 / 密码不出现在任何文件）
- [ ] `REAL_SUBMIT_DISABLED_WEB_FLOW` 保持 `True`
