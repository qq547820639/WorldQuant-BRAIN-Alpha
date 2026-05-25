# BRAIN Alpha Ops Comprehensive Code Review

Review date: 2026-05-22

Scope: Python backend, local Web console, vanilla JavaScript frontend, configuration, persistence/indexing, security controls, quality gates, and maintainability hotspots.

Validation baseline: `scripts/quality_gate.py --skip-tests --json` passed in this review. The passing steps included Python compilation, config validation, dependency policy, 72 redline checks, frontend inline sync, frontend syntax, text encoding scan, sensitive artifact scan, and cache metadata audit. Full pytest was not rerun in this review pass.

## Executive Summary

No critical issue was confirmed in the default local-only configuration. The strongest remaining risk is conditional: if `web.allow_remote=true` is used to expose the console beyond loopback, the root page creates a valid session for any reachable client and there is no separate user authentication gate. Several medium and low findings remain around sensitive assistant context exposure, expensive similarity scans, residual string-based DOM rendering, deprecated command-line credentials, cache scan scaling, duplicated helper logic, and large coordinator modules.

## Critical

No confirmed critical finding in the reviewed state.

## High

### H-01 Remote Web mode can mint sessions for any reachable client

Locations:
- `brain_alpha_ops/web_routes.py:17`
- `brain_alpha_ops/web_handler_dispatch.py:119`
- `brain_alpha_ops/web_handler_dispatch.py:122`
- `brain_alpha_ops/web_security.py:49`
- `brain_alpha_ops/web_security.py:66`
- `brain_alpha_ops/web_security.py:74`
- `brain_alpha_ops/web.py:1400`
- `brain_alpha_ops/web.py:1414`
- `brain_alpha_ops/web.py:1479`

Evidence:
- `/` is marked `requires_session=False`.
- `_get_root()` calls `get_or_create_session()` and returns HTML containing CSRF and stream tokens plus a session cookie.
- `is_allowed_local_request()` validates Host/Origin/Referer shape, but if `allow_remote=True` it does not authenticate the remote client; when Origin/Referer are absent it returns `True` after Host validation.
- `serve(..., allow_remote=True)` enables remote request handling and secure cookies, but it does not add an application password, bearer token, Basic Auth, or reverse-proxy-auth requirement.

Impact:
If the console is bound to `0.0.0.0` or another non-loopback address with `web.allow_remote=true`, any network peer that can reach it can load `/`, obtain a valid local session, and call session-protected APIs. Those APIs can start jobs, sync cloud alphas, run checks, generate candidates, submit candidates, inspect local research state, and interact with configured BRAIN credentials.

Recommendations:
- Keep `allow_remote=false` as the only safe default.
- For remote mode, require a separate admin authentication layer before session creation, such as `web.admin_token_env`, Basic Auth, or a mandatory authenticated reverse proxy.
- Make missing Origin/Referer fail closed for remote mode except for explicitly documented non-browser clients with bearer auth.
- Add tests proving that remote `GET /` without admin auth does not create a session.
- Document remote mode as "behind authenticated HTTPS proxy only" if that is the intended deployment boundary.

## Medium

### M-01 Assistant context defaults and opt-in flags can expose sensitive local context

Locations:
- `brain_alpha_ops/research/context.py:49`
- `brain_alpha_ops/research/context.py:88`
- `brain_alpha_ops/research/context.py:95`
- `brain_alpha_ops/web_handler_dispatch.py:209`
- `brain_alpha_ops/web_handler_dispatch.py:214`
- `brain_alpha_ops/web_handler_dispatch.py:226`
- `brain_alpha_ops/web_handler_dispatch.py:232`
- `brain_alpha_ops/agent_tools.py:380`
- `brain_alpha_ops/agent_tools.py:396`
- `brain_alpha_ops/cli.py:307`
- `brain_alpha_ops/cli.py:321`
- `tests/test_web.py:1406`

Evidence:
- `build_assistant_context_pack(..., include_sensitive=True)` is still the core default.
- The Web snapshot wrapper defaults to redaction, but `include_sensitive=true` on `/api/assistant_context` and `/api/assistant_request` re-enables full context.
- CLI and agent-tool paths call `build_assistant_context_pack()` without explicitly setting `include_sensitive=False`.
- The test suite confirms `assistant_context_snapshot(..., include_sensitive=True)` includes `storage_dir`.

Impact:
Local paths, cache metadata, raw context fragments, or future credential-like fields can be included in assistant prompts or API responses. This is especially risky when combined with remote Web mode, exported prompts, logs, or MCP/agent tool use.

Recommendations:
- Change the core default to `include_sensitive=False`.
- Add explicit `--include-sensitive` / `include_sensitive` flags for CLI and agent tools, with warnings and test coverage.
- Prefer POST plus an explicit confirmation field for sensitive Web context instead of a GET query parameter.
- Keep the redaction test suite focused on paths, tokens, cookies, authorization headers, cache locations, and nested sensitive keys.

### M-02 SQLite expression lookup falls back to a full-table Python similarity scan

Locations:
- `brain_alpha_ops/web_handler_dispatch.py:190`
- `brain_alpha_ops/web_handler_dispatch.py:193`
- `brain_alpha_ops/research/expression_sqlite_index.py:217`
- `brain_alpha_ops/research/expression_sqlite_index.py:221`
- `brain_alpha_ops/research/expression_sqlite_index.py:228`

Evidence:
- The Web route bounds `top_n`, but not the number of rows scanned when no exact fingerprint match exists.
- `ExpressionSqliteIndex.lookup()` loads every row with `SELECT * FROM expression_records ORDER BY id DESC` and computes `expression_similarity()` in Python.

Impact:
As the expression index grows, a single miss can become an expensive CPU and memory operation. Repeated misses from the UI can cause local latency spikes and make the console feel hung.

Recommendations:
- Add a hard scan cap, for example `max_scan_rows`, independent of `top_n`.
- Prefilter candidates using indexed fields such as operators, fields, family, fingerprint prefixes, or a lightweight token table.
- Consider an FTS/minhash/trigram auxiliary index for approximate lookup.
- Return partial results with a `truncated=true` signal when the cap is hit.

### M-03 Residual string-based DOM rendering still depends on convention and regex whitelists

Locations:
- `brain_alpha_ops/web/js/utils.js:146`
- `brain_alpha_ops/web/js/utils.js:150`
- `brain_alpha_ops/web/js/components/table.js:92`
- `brain_alpha_ops/web/js/components/table.js:107`
- `brain_alpha_ops/web/js/views/detail.js:174`
- `brain_alpha_ops/web/js/views/detail.js:177`
- `brain_alpha_ops/web/js/app.js:480`
- `brain_alpha_ops/web/js/app.js:489`

Evidence:
- Table and detail rendering still assemble HTML strings and assign them through `innerHTML`.
- The current `renderSafeHtmlFragment()` whitelist is a meaningful improvement, but its safety depends on every renderer using the correct `htmlType` and every future HTML fragment matching the sanitizer assumptions.

Impact:
No active XSS exploit was confirmed in this pass. The residual risk is regression risk: future columns or detail sections can accidentally bypass escaping because the rendering model still allows raw HTML fragments.

Recommendations:
- Move high-traffic table and detail renderers toward DOM builders using `textContent`, `setAttribute`, and delegated event listeners.
- Replace free-form fragment strings with typed renderer return values, for example `{kind: "badge", text, tone}`.
- Add a lint/test rule that forbids new `innerHTML` assignments outside approved rendering helpers.
- Keep CSP hash-based protections and avoid reintroducing inline event handlers or `style=` attributes.

## Low

### L-01 Deprecated command-line credential arguments still exist outside production

Locations:
- `brain_alpha_ops/cli.py:48`
- `brain_alpha_ops/cli.py:69`
- `brain_alpha_ops/cli.py:74`
- `brain_alpha_ops/cli.py:78`
- `brain_alpha_ops/cli.py:511`
- `brain_alpha_ops/cli.py:519`
- `brain_alpha_ops/cli.py:521`
- `brain_alpha_ops/cli.py:524`

Evidence:
- The CLI warns that credentials can leak through shell history and process lists.
- Production rejects command-line credentials, but the arguments remain accepted for non-production runs.

Impact:
A user can still place real credentials in shell history or process lists if they run in mock or transitional configurations.

Recommendations:
- Remove `--password` and `--token` in the next breaking version, or require an explicit `--allow-insecure-cli-credentials` escape hatch.
- Add safer alternatives: environment variables, `getpass` prompt, or `--token-stdin`.
- Ensure documentation never recommends command-line secrets.

### L-02 Cached user-alpha discovery scans and sorts every matching cache file

Locations:
- `brain_alpha_ops/web_cloud_snapshot.py:96`
- `brain_alpha_ops/web_cloud_snapshot.py:119`
- `brain_alpha_ops/web_cloud_snapshot.py:125`

Evidence:
- `cached_user_alpha_paths()` performs `glob("user_alphas_*.json")`, stats all matches, sorts the full list, and then readers parse files until one contains alpha rows.

Impact:
Usually harmless, but large or stale cache directories can add avoidable latency to dashboard refreshes.

Recommendations:
- Maintain a small manifest or `latest_user_alphas.json` pointer when writing cache files.
- Limit the number of candidate cache files examined.
- Add cache pruning for stale `user_alphas_*.json` files.

### L-03 Duplicate helper logic can drift

Locations:
- `brain_alpha_ops/research/pipeline_helpers.py:17`
- `brain_alpha_ops/research/pipeline_helpers.py:138`
- `brain_alpha_ops/research/pipeline_helpers.py:145`
- `brain_alpha_ops/research/candidate_pool.py:157`
- `brain_alpha_ops/research/candidate_pool.py:162`
- `brain_alpha_ops/research/candidate_pool.py:171`

Evidence:
- `ranking_score()`, `expr_key()`, and `is_hard_backtest_blocked()` exist in more than one helper module.
- `pipeline.py` imports many helpers from `pipeline_helpers`, but not the duplicated `is_hard_backtest_blocked()` implementation.

Impact:
Low immediate risk, but duplicated production-gate and backtest-blocking semantics are easy to update in one place and miss in another.

Recommendations:
- Keep one authoritative helper module for shared candidate lifecycle semantics.
- Delete unused duplicates or re-export a single implementation.
- Add focused tests around hard-block statuses so refactors preserve behavior.

### L-04 Large coordinator modules remain the main maintainability bottleneck

Locations and size snapshot:
- `brain_alpha_ops/research/pipeline.py`: 3203 lines
- `brain_alpha_ops/web.py`: 1494 lines
- `brain_alpha_ops/research/hypothesis_driven_generator.py`: 1190 lines
- `brain_alpha_ops/web/js/app.js`: 1066 lines
- `brain_alpha_ops/agent_tools.py`: 947 lines
- `brain_alpha_ops/research/observability.py`: 936 lines
- `brain_alpha_ops/brain_api/official.py`: 899 lines

Evidence:
- Previous refactors introduced helper modules, but several files still coordinate many responsibilities: lifecycle orchestration, API adaptation, persistence, UI state, submission safety, cache behavior, and compatibility facades.

Impact:
This increases review cost and regression probability, especially around submission safety and Web/API state transitions.

Recommendations:
- Continue splitting by stable business boundaries: generation, validation, simulation, submission, cloud sync, auth/session/cache, and UI action controllers.
- Keep compatibility facades thin and push behavior into tested services.
- Track module size and cyclomatic complexity as non-blocking quality signals.

## Positive Controls Observed

- Sensitive artifact scan reported no findings.
- Config validation passed for the current `config/run_config.json`.
- Redline verification passed 72/72 checks.
- Web responses use `Cache-Control: no-store` for HTML/JSON and security headers including CSP, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, and `Referrer-Policy: no-referrer`.
- Session cookies are `HttpOnly` and `SameSite=Strict`; remote mode enables `Secure` cookies.
- SQLite query paths reviewed here use parameterized SQL for user-provided values.
- Repository JSONL writes now include filename allowlisting and path containment checks.

## Open Questions and Assumptions

- I treated the Web console as a local-first operations tool. If remote/LAN deployment is a supported product mode, H-01 should be prioritized before further exposure.
- I did not run full pytest in this pass; only the non-test quality gate was rerun.
- I did not inspect external infrastructure, reverse proxy settings, or secret rotation history.
- I did not modify runtime behavior as part of this review; this file is a review artifact only.

## Suggested Fix Order

1. Add mandatory authentication for remote Web mode and fail closed when remote requests lack trusted origin evidence.
2. Make assistant context redaction the core default across Web, CLI, and agent tools.
3. Cap and prefilter SQLite similarity lookup.
4. Add a frontend rule to block new raw `innerHTML` sinks outside approved helpers.
5. Remove or further gate deprecated CLI secret arguments.
6. Consolidate duplicated pipeline/candidate helper functions.
7. Continue module-boundary refactors for the largest coordinators.
