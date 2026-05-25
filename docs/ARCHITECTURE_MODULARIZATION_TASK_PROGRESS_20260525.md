# Architecture Modularization Task Progress

Updated: 2026-05-25

Source checklist: user-provided QuantGPT comparison recommendations on architecture, data efficiency, LLM prompt chain, backtest workflow, and logging/robustness.

## Completed

- [x] AM-0 Created this execution checklist for the current architecture-modularization pass.
- [x] AM-1 Added `brain_alpha_ops/agent_tool_registry.py` as the unified registry boundary for MCP/Web/local assistant tools.
  - Registered category and chain-stage metadata so tool consumers can distinguish context, generation, lightweight scoring, deep validation/backtest, robustness, and submission steps.
  - Added QuantGPT-style aliases: `score_factor -> score_candidate` and `run_backtest -> run_simulation`.
  - MCP tool listing now exposes alias, category, chain-stage, live API, and destructive annotations.
- [x] AM-2 Moved assistant system-prompt text into `brain_alpha_ops/research/prompts/assistant_system_prompt.txt`.
  - The prompt now explicitly declares the WorldQuant BRAIN FASTEXPR factor-research role, safe tool boundary, and score-before-backtest workflow.
  - Added `brain_alpha_ops/research/prompt_templates.py` so the prompt is loaded as a packaged template with a safe fallback.
  - Updated Windows/PyInstaller packaging paths to include prompt templates in the runtime artifact.
- [x] AM-3 Added focused regression tests for the registry, aliases, prompt template, MCP metadata, and packaging coverage.
- [x] AM-4 Ran validation and synchronized this checklist with final evidence.

## Pending

- None for the current executable local refactor pass.

## Deferred

- [ ] AM-DATA-1 Introduce NumPy/Pandas/vectorbt/backtrader or a new vectorized market-data cache. This requires product-level dependency and data-model decisions beyond the current safe local refactor.
- [ ] AM-DATA-2 Implement true parallel full-market batch backtesting. Current official API/backtest safety gates are intentionally conservative; concurrency needs separate rate-limit and account-safety design.
- [ ] AM-EXEC-1 Add parameter-scan or evolutionary factor search loops. The repo already has iterative/guided research primitives, but broad automated search should be scoped separately with budget controls.
- [ ] AM-OPS-1 Add external monitoring or alert delivery. The current pass can improve local observability surfaces, but production alert routing needs an operator/channel choice.

## Verification

- [x] `python -m compileall -q brain_alpha_ops scripts tests`: passed.
- [x] Focused tests for agent tools, MCP, assistant request, and packaging:
  - `tests/test_agent_tools.py`
  - `tests/test_mcp_server.py`
  - `tests/test_assistant_request.py`
  - `tests/test_windows_packaging.py`
  - Result: `42 passed, 1 existing pytest config warning`.
- [x] `scripts/check_module_size.py --json`: passed, 179 files checked, no oversized-module findings.
- [x] `scripts/check_text_encoding.py --root . --json`: passed, 356 files checked, no findings.
- [x] Standard quality gate: `scripts/quality_gate.py --skip-tests --json` passed all configured steps.
- [x] Strict quality gate: `scripts/quality_gate.py --strict-official-context --skip-tests --json` passed, including strict official context and strict BRAIN contract validation.
- [x] Full repository pytest: `713 passed, 1 existing pytest config warning`.
