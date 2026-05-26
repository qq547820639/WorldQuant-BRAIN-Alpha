# Architecture Modularization Task Progress

Updated: 2026-05-26

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
- [x] AM-4 Added a controlled agent/MCP batch simulation surface:
  - Registered `run_simulation_batch` plus QuantGPT-style alias `run_batch_backtest`.
  - The batch path reuses the single-expression simulation safety gates: live API confirmation, duplicate-expression preflight, validation-before-submit, per-item result capture, and bounded batch/concurrency limits.
  - Assistant prompt guidance now treats batch backtest as a budgeted deep-validation step, not a shortcut around `score_factor`.
- [x] AM-5 Ran validation and synchronized this checklist with final evidence.
- [x] AM-6 Hardened batch simulation result accounting.
  - `run_simulation` now marks terminal `FAILED`/`ERROR` poll statuses as failed tool results instead of reporting a successful submitted simulation.
  - `run_simulation_batch` therefore counts terminal simulation failures in `failed_count` and returns `ok=false` when any selected item finishes failed.
  - Added a regression test so failed terminal statuses cannot be silently counted as successful batch work.
- [x] AM-7 Reconciled the architecture-modularization diagnosis against the current repository state.
  - Confirmed the registry, prompt-template, MCP metadata, packaging, and bounded batch-simulation surfaces are present in code and tests.
  - Re-ran the executable local validation stack for this pass: focused regression slice, standard quality gate, strict official-context quality gate, and full pytest.
  - Synchronized the diagnosis/progress wording so current executable work is separated from product-level deferred work.
- [x] AM-8 Added lightweight market-data cache, parameter search, and local alert delivery helpers.
  - Introduced `brain_alpha_ops/research/market_data_cache.py` for a compact JSON-backed cache and connected it to the agent tool surface.
  - Introduced `brain_alpha_ops/research/parameter_search.py` for bounded parameter search and ranking.
  - Introduced `brain_alpha_ops/research/alerting.py` for local alert persistence and optional webhook delivery.
  - Wired the new capabilities into `brain_alpha_ops/agent_tool_registry.py` and `brain_alpha_ops/agent_tools.py`.
- [x] AM-9 Split the new research/observability helpers into smaller modules to keep line budgets healthy.
  - Extracted agent-facing helper wrappers into `brain_alpha_ops/agent_research_tools.py`.
  - Extracted observability optional-source handling into `brain_alpha_ops/research/observability_extensions.py`.
  - Extracted observability error-row conversion into `brain_alpha_ops/research/observability_errors.py`.
  - Re-ran module-size, compile, focused tests, standard gate, and strict official-context gate successfully.
- [x] AM-10 Added local productization extensions for the previously deferred gaps.
  - Added `brain_alpha_ops/research/market_data_vector.py` to expose a bounded symbol-by-feature matrix from the local market-data cache.
  - Added `brain_alpha_ops/research/parallel_backtest.py` to produce capacity-limited full-market backtest plans with rate-limit and account-safety metadata.
  - Added `brain_alpha_ops/research/search_orchestrator.py` to run bounded multi-round parameter search with explicit budget accounting.
  - Extended `brain_alpha_ops/research/alerting.py` with `AlertRouter` for multi-channel local/webhook/callback routing.
  - Registered `build_vectorized_market_data`, `plan_parallel_backtest`, `orchestrate_parameter_search`, and `route_alert` as safe agent tools.
- [x] AM-11 Hardened productization tool boundaries and added bounded parallel execution.
  - Added `ParallelBacktestExecutor` in `brain_alpha_ops/research/parallel_backtest.py` for capacity-limited multi-market execution with per-job result accounting.
  - Registered `run_parallel_backtest` as a live-API guarded agent/MCP tool and wired it through `BrainAlphaToolbox`.
  - Preserved live API confirmation, duplicate-expression preflight, validation-before-submit, max-batch, max-worker, and per-account limits.
  - Normalized scalar/list arguments for fields, markets, alert channels, and expression batches so MCP/UI callers do not accidentally split strings into characters.
  - Exposed alert metadata in the tool schema and added focused regression coverage for planning, execution failure accounting, and scalar argument normalization.
- [x] AM-12 Recovered module boundaries and hardened parameter search determinism.
  - Extracted assistant-guidance conversion helpers into `brain_alpha_ops/agent_guidance_tools.py`, bringing `brain_alpha_ops/agent_tools.py` back under the configured module-size baseline.
  - Added deterministic fallback mutations in `brain_alpha_ops/research/parameter_search.py` so parameter search can fill the requested bounded mutation budget when the optimizer returns too few variants.
  - Re-ran focused tests, module-size audit, standard quality gate, strict official-context quality gate, and full pytest successfully.
- [x] AM-13 Hardened the local productization extensions for operational use.
  - Extended `brain_alpha_ops/research/market_data_cache.py` with JSON/JSONL path ingestion, multi-source refresh, nested metric extraction, field coverage stats, time ranges, and cache-health metadata.
  - Extended `brain_alpha_ops/research/market_data_vector.py` with missing-value accounting, row stats, minimum field-coverage filtering, optional min-max normalization, and cache-health propagation.
  - Extended `brain_alpha_ops/research/parallel_backtest.py` with duplicate-expression reporting, empty-plan safety payloads, progress events/callbacks, terminal FAILED/ERROR normalization, and failure-code aggregation.
  - Extended `brain_alpha_ops/research/parameter_search.py` and `brain_alpha_ops/research/search_orchestrator.py` with mutation budgets, termination reasons, duplicate-expression filtering, lineage metadata, round summaries, and evaluated-candidate accounting.
  - Extended `brain_alpha_ops/research/alerting.py` with severity normalization, persistence status, sender/transport diagnostics, and routed failed-delivery counts.
  - Added `brain_alpha_ops/scoring/visualization.py` and exposed `attribution_summary` from official scoring/Web scoring attribution responses for stable UI/tool consumption.
- [x] AM-14 Refreshed credential-backed official BRAIN context and cleared the strict-freshness blocker.
  - Ran the official context refresh with process-scoped BRAIN credentials only; no credentials were written into config, docs, or status artifacts.
  - Refreshed official context to 7,780 fields, 66 operators, and 17 datasets; metadata now expires on 2026-05-27T02:01:41Z.
  - Added retryable rate-limit metadata to `fetch_official_context.py` so failed refresh attempts include `error_category`, `retryable`, `retry_after_seconds`, and `next_retry_at`.
  - Regenerated `docs/ALPHA_PRODUCTION_DIAGNOSIS_20260522.md` against the current refreshed context; the local production diagnosis now reports no unfinished local code checklist items.

## Pending

- None for the current executable local refactor pass.

## Deferred

- [ ] AM-DATA-PROD Connect the vectorized local matrix to a production market-data source or heavier analytics backend if a product owner chooses that dependency.
- [ ] AM-BACKTEST-PROD Enable real official full-market live execution in production by supplying credentials/account policy and selecting the desired market universe; the code path is now present but remains live-API guarded.
- [ ] AM-OPS-PROD Configure real external monitoring credentials/routes for email, webhook, or observability-platform delivery.

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
- [x] Full repository pytest: `718 passed, 1 existing pytest config warning`.
- [x] Incremental AM-6 verification:
  - `python -m compileall -q brain_alpha_ops tests`: passed.
  - Batch/agent/observability focused slice passed: `50 passed, 1 existing pytest config warning`.
  - Registry/prompt/packaging focused slice passed: `47 passed, 1 existing pytest config warning`.
  - Standard quality gate after AM-6: `scripts/quality_gate.py --skip-tests --json` passed all configured steps.
- [x] Current AM-7 verification:
  - Focused registry/prompt/MCP/packaging slice passed: `47 passed, 1 existing pytest config warning`.
  - Standard quality gate: `scripts/quality_gate.py --skip-tests --json` passed all configured steps.
  - Strict official-context quality gate: `scripts/quality_gate.py --strict-official-context --skip-tests --json` passed all configured steps, including strict BRAIN contract and strict official-context freshness.
  - Full repository pytest: `718 passed, 1 existing pytest config warning`.
- [x] Current AM-8/AM-9 verification:
  - `python -m compileall -q brain_alpha_ops tests`: passed.
  - Focused research-tool and observability slice passed: `79 passed`.
  - `scripts/check_module_size.py --json`: passed with no oversized-module findings.
  - `scripts/quality_gate.py --skip-tests --json`: passed.
  - `scripts/quality_gate.py --strict-official-context --skip-tests --json`: passed with strict freshness.
- [x] Current AM-10 focused verification:
  - `python -m compileall -q brain_alpha_ops tests`: passed.
  - Productization focused slice passed: `16 passed`.
  - `scripts/check_module_size.py --json`: passed with no oversized-module findings.
- [x] Current AM-11 focused verification:
  - `tests/test_parallel_backtest.py tests/test_new_research_tools.py tests/test_agent_tools.py tests/test_mcp_server.py`: `45 passed`.
- [x] Current AM-12 final verification:
  - `python -m compileall -q brain_alpha_ops tests`: passed.
  - `scripts/check_module_size.py --json`: passed with no oversized-module findings.
  - Parameter-search/productization focused slice passed: `9 passed`.
  - Standard quality gate: `scripts/quality_gate.py --skip-tests --json` passed.
  - Strict quality gate: `scripts/quality_gate.py --strict-official-context --skip-tests --json` passed with strict freshness.
  - Full repository pytest: `738 passed`.
- [x] Current AM-13 focused verification:
  - `tests/test_market_data_cache.py tests/test_market_data_vector.py tests/test_parallel_backtest.py tests/test_parameter_search.py tests/test_search_orchestrator.py tests/test_alerting.py tests/test_scoring_visualization.py tests/test_official_scoring_system.py tests/test_web_redline_scoring.py`: `28 passed`.
  - `python -m compileall -q brain_alpha_ops tests`: passed.
  - `scripts/check_module_size.py --json`: passed with no oversized-module findings.
  - Standard quality gate: `scripts/quality_gate.py --skip-tests --json` passed.
  - Strict quality gate: `scripts/quality_gate.py --strict-official-context --skip-tests --json` blocked only on expired official-context metadata (`p1_count=3`, `stale_count=3`); code, redline, frontend, module-size, secret-scan, and report-sync steps passed.
  - Full repository pytest: `745 passed`.
- [x] Current AM-14 official-context verification:
  - `scripts/check_official_context.py --config config/run_config.json --strict-freshness --json`: passed with `p1_count=0`, `field_count=7780`, `dataset_count=17`, and `dataset_field_count_sum=7780`.
  - `scripts/check_brain_contract.py --config config/run_config.json --strict-freshness --json`: passed with no findings and `blocking_count=0`.
  - Standard quality gate: `scripts/quality_gate.py --skip-tests --json` passed.
  - Strict quality gate: `scripts/quality_gate.py --strict-official-context --skip-tests --json` passed.
  - Official-refresh/diagnosis focused slice passed: `16 passed`.
  - Full repository pytest: `746 passed`.
