# Comprehensive Audit & Refactoring Plan
## WorldQuant-BRAIN-Alpha — v2026.06.17

**Scope**: 312 Python modules, 224 test files, 82 web_*.py files (22,794 lines), 35 React components, 2 SQLite databases, 12+ JSONL event stores.

**Priority order**: Correctness → Security → Architecture → Code quality → Cleanup

---

## Phase 0: P0 Critical — Correctness Bugs (Estimated: 3–4 hours)

These issues affect correctness of results or risk runtime exceptions. Each fix is small and isolated.

### 0.1 scoring.py duplicate import (will cause NameError or shadowing)
- **File**: `brain_alpha_ops/research/scoring.py:789–790`
- **Problem**: Two lines import `_ratio` and `normalize_brain_ratio` — first via relative (`from ._ratio`), second via absolute (`from brain_alpha_ops.research._ratio`). The second re-exports the same names, shadowing line 789. This works by accident but triggers `F401` lint noise and is confusing.
- **Fix**: Remove line 789. Keep line 790 (the canonical absolute import with the `S-13` comment). Delete the stale comment on line 786–788.
- **Verification**: `python -c "from brain_alpha_ops.research.scoring import _ratio, normalize_brain_ratio"` + `ruff check brain_alpha_ops/research/scoring.py`

### 0.2 convergence.py bootstrap non-deterministic
- **File**: `brain_alpha_ops/research/convergence.py:397`
- **Problem**: `random.choice(values)` in `_bootstrap_ci` uses unseeded global RNG. Bootstrap results differ across runs, making convergence diagnostics non-reproducible.
- **Fix**: Accept an optional `rng: random.Random | None = None` parameter on `ConvergenceTracker.__init__` and `_bootstrap_ci`. Default to `random.Random(42)` for reproducibility. Pass `self._rng` in `_bootstrap_ci`.
- **Verification**: Run bootstrap twice with same data → results must be identical.

### 0.3 attribution.py KeyError risk
- **File**: `brain_alpha_ops/scoring/attribution.py:194`
- **Problem**: `scorecard["total_score"]` uses direct dict access while line 192 uses defensive `.get()`. If `total_score` key is missing, this crashes with `KeyError`.
- **Fix**: Change line 194 to `contribution=scorecard.get("total_score", 0),`
- **Verification**: `ruff check brain_alpha_ops/scoring/attribution.py` + unit test with empty scorecard.

### 0.4 official_request.py token cleared during auth fallback
- **File**: `brain_alpha_ops/brain_api/official_request.py:111–112`
- **Problem**: `self.token = ""` clears the token mid-request. If the auth refresh fails (line 124–132), the token is only restored in error paths (lines 155–156, 163–164, 167–168). But if the cookie auth succeeds on the retry, the original token is permanently lost for subsequent requests.
- **Fix**: Move token restoration into a `finally`-like pattern: always restore `self.token` from `token_before_auth_fallback` after the retry loop completes, unless the request succeeded with a new auth mechanism. Or simpler: save/restore in the loop scope so that `self.token = ""` only affects the current iteration.
- **Verification**: Unit test: mock 401 on first attempt, successful cookie auth on retry, verify `self.token` is restored after request completes.

### 0.5 alpha_checks.py import inside function body
- **File**: `brain_alpha_ops/research/alpha_checks.py:758`
- **Problem**: `import re` inside a function body. While Python caches imports, this is a performance micro-inefficiency and poor style.
- **Fix**: Move `import re` to the top of the file with other imports.
- **Verification**: `ruff check brain_alpha_ops/research/alpha_checks.py`

### 0.6 anti_overfit.py dead code `_synthetic_ic_series`
- **File**: `brain_alpha_ops/research/anti_overfit.py:104–110`
- **Problem**: `_synthetic_ic_series` is defined but never called anywhere in the codebase. The previous audit (R5) confirmed this is dead code after the P0 fix that made anti_overfit return `insufficient_data` when no real IC is present.
- **Fix**: Delete lines 104–110 (the function body) and the unused imports it depends on (`hashlib`, `random` at module level if no other caller uses them — check first).
- **Verification**: `ruff check brain_alpha_ops/research/anti_overfit.py` + grep confirms no callers.

**Phase 0 verification**: Run full test suite `pytest tests/ -x -q`. All existing tests must pass.

---

## Phase 1: P0 Security & Reliability (Estimated: 2–3 hours)

### 1.1 test_coverage.py in production package
- **File**: `brain_alpha_ops/test_coverage.py` (111 lines)
- **Problem**: Test infrastructure code lives inside the production package. It gets shipped, imported by accident, and clutters namespace.
- **Fix**: Move to `tests/test_coverage.py`. Update any imports (likely none — it's a standalone report generator).
- **Verification**: `pytest tests/ -x -q` + `python -c "import brain_alpha_ops.test_coverage"` should fail after move.

### 1.2 guided_pipeline.py.bak backup file
- **File**: `brain_alpha_ops/ux/guided_pipeline.py.bak`
- **Problem**: Stale backup file in production package. Can be accidentally imported on case-insensitive filesystems or committed to repo.
- **Fix**: Delete the file.
- **Verification**: `ls brain_alpha_ops/ux/guided_pipeline.py.bak` should fail.

### 1.3 Mixed Chinese/English error messages (partial i18n)
- **File**: `brain_alpha_ops/web_state_contract.py:20–80+` (16 error types, all Chinese), `brain_alpha_ops/ux/guided_pipeline.py:43`
- **Problem**: User-facing strings are hardcoded in Chinese without i18n separation. Error messages in `web_state_contract.py` mix Chinese titles/messages with English `next_action` and `error_code` keys. Frontend must hardcode Chinese strings.
- **Fix (minimal)**: No full i18n system needed. But extract user-facing strings into a `_MESSAGES` dict with `zh` keys so they're easy to find and eventually localize. For now, keep Chinese as default.
- **Impact**: Low — this is a local tool for a Chinese-speaking user. Document the decision as intentional.
- **Verification**: No functional change. Code review only.

### 1.4 _LegacyMarketDataFrameShim removal
- **File**: `brain_alpha_ops/research/local_backtest_engine.py:70–99`
- **Problem**: Deprecated alias kept for backward compatibility. No code should be using it after P2-14 extraction.
- **Fix**: Grep for all `_LegacyMarketDataFrameShim` references. If only self-referential (this file + tests), delete the class. If external code uses it, add a `DeprecationWarning` and schedule removal for Phase 4.
- **Verification**: `grep -r "_LegacyMarketDataFrameShim" brain_alpha_ops/` + `pytest tests/ -x -q`

**Phase 1 verification**: `ruff check brain_alpha_ops/` + `pytest tests/ -x -q`

---

## Phase 2: P1 Architecture — Web Layer Consolidation (Estimated: 8–12 hours)

The web layer has 82 `web_*.py` files totaling 22,794 lines. This is the highest-impact architecture debt.

### 2.1 Eliminate dual dispatch system
- **Files**: `brain_alpha_ops/web_handler_dispatch.py` (981 lines) + `brain_alpha_ops/web/__init__.py` (legacy ~1053 lines)
- **Problem**: Two dispatch systems coexist. `web/__init__.py` has its own `_send_json`/`_send_html`/`_html`/`_json` methods and route handling. `web_handler_dispatch.py` has the new dispatch. The facade at `web/__init__.py:888–892` just delegates `_html` → `_send_html` and `_json` → `_send_json`.
- **Fix**:
  1. Identify which routes are still served by the legacy `web/__init__.py` dispatch vs `web_handler_dispatch.py`.
  2. Migrate remaining legacy routes to `web_handler_dispatch.py`.
  3. Remove `_send_html`/`_send_json` from `web/__init__.py` Handler class — they duplicate `web_http_handler.py`.
  4. Remove `_html`/`_json` facade methods once no callers remain.
- **Verification**: `grep -r "handler\._send_json\|handler\._send_html\|handler\._html\|handler\._json" brain_alpha_ops/` should show only `web_http_handler.py` definitions.

### 2.2 Handler type annotation
- **File**: `brain_alpha_ops/web_handler_dispatch.py:74`, `brain_alpha_ops/web_http_handler.py:57`
- **Problem**: Handler parameter typed as `Any` everywhere. No static analysis support.
- **Fix**: Create a `WebHandler` Protocol class in `web_dispatch_context.py`:
  ```python
  class WebHandler(Protocol):
      def _send_json(self, payload: dict, status: int = 200, *, extra_headers: Any = None) -> None: ...
      def _send_html(self, html: str | bytes, *, extra_headers: Any = None) -> None: ...
      def _read_json(self) -> dict: ...
      # ... etc
  ```
  Update `RouteDispatcher` and `PayloadRouteDispatcher` type aliases.
- **Verification**: `mypy brain_alpha_ops/web_handler_dispatch.py --ignore-missing-imports` (if mypy is available) or `ruff check`.

### 2.3 Web module grouping analysis
- **Action**: Create a `web_modules_inventory.md` documenting which of the 82 web_*.py files serve which purpose:
  - **Core dispatch** (keep as-is): `web_handler_dispatch.py`, `web_handler_dispatch_core.py`, `web_http_handler.py`
  - **Context/state** (keep as-is): `web_dispatch_context.py`, `web_state_contract.py`, `web_runtime_state.py`
  - **Domain groups** (candidates, jobs, config, snapshots, submissions) — identify natural clusters
  - **Facade/compat** (candidates for deletion): `web_compat_facade.py`, `web_legacy_exports.py`
- **No code changes** in this phase — just inventory and decision documentation.
- **Verification**: Document produced with recommended consolidation targets.

**Phase 2 verification**: Full test suite + manual smoke test of web UI.

---

## Phase 3: P1 Architecture — Pipeline Service Migration (Estimated: 6–8 hours)

### 3.1 PipelineServices container activation
- **File**: `brain_alpha_ops/research/pipeline_services_container.py` (83 lines), `brain_alpha_ops/research/pipeline.py:182–197`
- **Problem**: `PipelineServices` container exists and is lazily created, but the main pipeline still uses Mixin inheritance (10 Mixins). The container is documented as "recommended for new code" but no code actually uses it.
- **Fix**:
  1. In each Mixin, add a `@property` that delegates to `self.services.<name>` (or vice versa — have the Mixin methods be thin wrappers).
  2. New code added in future should use `pipeline.services.X` instead of `self.X_from_mixin`.
  3. Do NOT attempt to remove all 10 Mixins in one go — that's a multi-week refactoring. Instead, ensure new code uses the container.
- **Verification**: `pipeline.services` returns the same objects as `pipeline.<mixin_method>()`.

### 3.2 pipeline.py run() decomposition
- **File**: `brain_alpha_ops/research/pipeline.py` (770 lines)
- **Problem**: `run()` method is ~340 lines despite mixin extraction attempts.
- **Fix**: Continue extracting phases into the existing mixin modules:
  - Move the "check convergence and recommend strategy switch" block into `PipelineRuntimeMixin`.
  - Move the "finalize and persist results" block into `PipelineSnapshotMixin`.
  - Target: `run()` under 150 lines, pure orchestration.
- **Verification**: `wc -l brain_alpha_ops/research/pipeline.py` + `pytest tests/ -x -q`

### 3.3 iterative_optimizer.py strategy ranking
- **File**: `brain_alpha_ops/research/iterative_optimizer.py:126–137, 148–153, 206–213`
- **Problem**: `_FAILURE_TO_STRATEGY` hardcoded mapping coexists with learned `strategy_ranking` from AB tests. When no AB data is available, it falls back to hardcoded defaults. This is intentional but the fallback path is undocumented.
- **Fix**: Add a log message when falling back to hardcoded defaults: `logger.debug("No AB data for dimension %s, using hardcoded defaults", dim)`.
- **Verification**: `grep -A2 "strategy_ranking" brain_alpha_ops/research/iterative_optimizer.py`

### 3.4 stall_monitor._iter_job_rows normalization
- **File**: `brain_alpha_ops/stall_monitor.py:189–212`
- **Problem**: Handles 3 different job store formats (dict, list-of-dicts, list-of-tuples). This fragility suggests the job store API is not well-defined.
- **Fix**: Add a `NormalizedJob` dataclass or Protocol and normalize at the boundary. Or at minimum, add type hints and a docstring documenting the 3 formats.
- **Verification**: Unit tests for each format.

**Phase 3 verification**: Full test suite + pipeline integration test.

---

## Phase 4: P1 Code Quality (Estimated: 4–5 hours)

### 4.1 scoring.py _ratio import cleanup
- Already covered in Phase 0.1. If not done, do it here.

### 4.2 rolling_validation.py synthetic fallback
- **File**: `brain_alpha_ops/research/rolling_validation.py:76–87`
- **Problem**: When no real rolling series exists, `_metric_series` falls back to `[base * factor for factor in (0.85, 0.95, 1.0, 0.9)]` — a synthetic 4-point series. This produces misleading results.
- **Fix**: Return empty list instead (consistent with anti_overfit's `insufficient_data` pattern). The `evaluate()` method already handles `len(series) < 4` by returning `insufficient_data`.
- **Verification**: `pytest tests/ -x -q` + verify rolling validation returns `insufficient_data` when no real series.

### 4.3 guided_pipeline.py Python 3.9 compat
- **File**: `brain_alpha_ops/ux/guided_pipeline.py` (502 lines)
- **Problem**: The previous audit noted Python 3.9 f-string compat issues. The file starts with `from __future__ import annotations` (line 12), which should handle most cases. Verify no remaining issues.
- **Fix**: `ruff check brain_alpha_ops/ux/guided_pipeline.py` — any remaining issues will surface.
- **Verification**: Lint clean.

### 4.4 web_dispatch_context.py name allowlist
- **File**: `brain_alpha_ops/web_dispatch_context.py:5–105+`
- **Problem**: `WEB_CONTEXT_ALLOWED_NAMES` is a 100+ entry frozenset that must be manually maintained. Easy to get out of sync.
- **Fix**: Generate the allowlist from the actual exports of the module using `dir()` at runtime, or use `__all__`. The current approach is a maintenance trap.
- **Verification**: `python -c "from brain_alpha_ops.web_dispatch_context import WEB_CONTEXT_ALLOWED_NAMES; print(len(WEB_CONTEXT_ALLOWED_NAMES))"` — compare with actual exports.

### 4.5 Mixed import style cleanup
- **Files**: Various
- **Problem**: Some files use relative imports, some absolute, some mix. The `scoring.py` duplicate is the worst case.
- **Fix**: Run `ruff check --select I` (isort) to normalize import ordering. Do NOT change import style (relative vs absolute) — that's a separate, larger refactoring.
- **Verification**: `ruff check brain_alpha_ops/ --select I`

**Phase 4 verification**: `ruff check brain_alpha_ops/` + `pytest tests/ -x -q`

---

## Phase 5: P2 Frontend Decomposition (Estimated: 6–8 hours, deferred)

### 5.1 CandidateTable.tsx split
- **File**: `brain_alpha_ops/web/react_app/src/components/CandidateTable.tsx` (2,107 lines)
- **Problem**: Monolithic component handling table rendering, sorting, filtering, selection, detail panels, and action buttons.
- **Fix**: Extract into:
  - `CandidateTableHeader.tsx` — column headers, sort controls
  - `CandidateTableBody.tsx` — row rendering, virtual scrolling
  - `CandidateDetailPanel.tsx` — expanded row detail view
  - `CandidateActions.tsx` — per-row action buttons
  - `CandidateTable.tsx` — orchestrator only (~200 lines)
- **Verification**: `npm run build` + visual regression.

### 5.2 App.tsx decomposition
- **File**: `brain_alpha_ops/web/react_app/src/App.tsx` (662 lines)
- **Fix**: Extract route-level components into separate files. Keep App.tsx as router + layout shell.

**Phase 5 verification**: `npm run build && npm test`

---

## Phase 6: P2 Cleanup (Estimated: 2–3 hours, deferred)

### 6.1 Remove web_compat_facade.py
- **File**: `brain_alpha_ops/web_compat_facade.py` (59 lines)
- **Problem**: Backward-compatible facade for legacy test modules. If tests have been updated, this is dead code.
- **Fix**: Grep for callers. If none, delete.
- **Verification**: `pytest tests/ -x -q`

### 6.2 Remove web_legacy_exports.py
- **File**: `brain_alpha_ops/web_legacy_exports.py`
- **Problem**: Legacy export shim. Same analysis as 6.1.
- **Verification**: Grep + test.

### 6.3 PipelineServices full adoption
- **File**: `brain_alpha_ops/research/pipeline.py` + all Mixin files
- **Fix**: After Phase 3 proves the container works, gradually migrate all Mixin method calls to use `pipeline.services.X`. This is a long-term goal — don't rush it.
- **Verification**: Each migration step: `pytest tests/ -x -q`

### 6.4 Data layer documentation
- **Action**: Document the 12+ JSONL event stores, 2 SQLite databases, and JSON cache structure in a `data/README.md`. Include schema evolution rules.
- **No code changes**.

---

## Execution Order & Dependencies

```
Phase 0 (P0 correctness) ──→ Phase 1 (P0 security) ──→ Phase 2 (web consolidation)
                                    │                          │
                                    ▼                          ▼
                              Phase 4 (code quality)    Phase 3 (pipeline migration)
                                                            │
                                                            ▼
                                                      Phase 5 (frontend)
                                                            │
                                                            ▼
                                                      Phase 6 (cleanup)
```

**Phases 0 and 1** are independent of each other and can be done in parallel.
**Phase 2** depends on Phase 1.1 (test_coverage.py move) to avoid confusion.
**Phase 3** depends on Phase 0 completion (pipeline correctness must be verified first).
**Phases 4–6** are incremental and can be interleaved.

---

## Risk Assessment

| Phase | Risk | Mitigation |
|-------|------|------------|
| P0 | Correctness fix introduces regression | Each fix is <10 lines, covered by existing tests |
| P1 | Moving test_coverage.py breaks imports | Grep for importers before moving |
| P2 | Web dispatch migration breaks routes | Migrate one route at a time, test after each |
| P3 | Pipeline refactor breaks run() loop | Extract one phase at a time, run integration test |
| P5 | Frontend split breaks component tree | Visual regression testing after each split |

---

## Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Largest Python file | pipeline.py (770 lines) | <500 lines |
| Largest TSX file | CandidateTable.tsx (2,107 lines) | <500 lines |
| web_*.py file count | 82 | <60 (after consolidation) |
| Duplicate imports | 1 (scoring.py) | 0 |
| Dead code functions | 1 (_synthetic_ic_series) | 0 |
| Mixin count | 10 | 10 (but container adopted) |
| test_coverage.py location | production package | tests/ |
| .bak files | 1 | 0 |
