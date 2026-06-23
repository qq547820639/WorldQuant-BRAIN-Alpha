# Architecture — BRAIN Alpha Ops

> Version 0.5.0 — Local alpha research workstation for the WorldQuant BRAIN platform.

## System Overview

BRAIN Alpha Ops is a **single-user local workstation** that automates the alpha
research lifecycle: generate → test → score → filter. It **never auto-submits** —
all submissions require human approval through a web console.

```
┌─────────────────────────────────────────────────────────────┐
│                     Web Console (React)                      │
│           http://127.0.0.1:8765  (default)                  │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP / SSE
┌──────────────────────────▼──────────────────────────────────┐
│                   Web Server (stdlib)                        │
│        Route dispatch │ Session │ CSP │ CSRF │ Redaction     │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                  AlphaResearchPipeline                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐  │
│  │Generator │→ │ Scorer   │→ │Converger │→ │ Submission │  │
│  └──────────┘  └──────────┘  └──────────┘  └────────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
   │   Browser    │  │     API     │  │  Official   │
   │  Playwright  │  │  (dev/CI)   │  │  Brain API  │
   └─────────────┘  └─────────────┘  └─────────────┘
```

## Module Responsibilities

### `brain_alpha_ops/research/` — Core Research Engine

The largest module (126+ files). Contains the pipeline, generators, scoring, and
convergence tracking.

| Module | Responsibility |
|---|---|
| `pipeline.py` | `AlphaResearchPipeline` — orchestrates the full research cycle. Uses 6 mixins for service factory, snapshots, candidate pool, context sync, backtest, and submission. |
| `generator.py` | `CandidateGenerator` — produces alpha candidates in three modes: hypothesis-driven (70%), experience-feedback (20%), random exploration (10%). |
| `scoring.py` | Three-layer scoring: Prior (30%) + Empirical (45%) + Checklist (25%). Entry point: `build_scorecard()`. |
| `convergence.py` | `ConvergenceTracker` — BCa Bootstrap confidence intervals, Spearman trend analysis, stall detection, strategy profile switching. |
| `hypotheses/` | YAML hypothesis definitions with JSON Schema validation for extensible investment ideas. |

### `brain_alpha_ops/scoring/` — Scoring System

| Module | Responsibility |
|---|---|
| `gates.py` | 8 official hard gates with constrained whitelist (`OFFICIAL_HARD_GATE_NAMES`). |
| `local_quality.py` | Local quality scoring (re-exported by `generator.py`). |

### `brain_alpha_ops/brain_api/` — BRAIN Official API Adapter

| Module | Responsibility |
|---|---|
| `official.py` | `OfficialBrainAPI` — assembled from 4 mixins (Auth, Context, Request, Simulation/Submission). Stdlib HTTP only. |
| `rate_limit_policy.py` | Rate limiting: max 3 concurrent simulations, 60s min retry, exponential backoff. |

### `brain_alpha_ops/browser/` — Browser Execution Backend

Playwright-based browser automation for driving the real BRAIN Web UI.
Used as the default production execution backend.

### `brain_alpha_ops/web/` — Web Console

| Submodule | Responsibility |
|---|---|
| `react_app/` | React 18 + TypeScript + Tailwind frontend (46 components, 15 hooks). |
| `security/` | Session management, CSRF validation, CSP headers, request origin checks. |
| `dispatch/` | Route dispatch (12 files) mapping HTTP requests to handlers. |
| `api/` | API handlers for candidates, scoring, configuration, submissions. |
| `business/` | Business logic for background jobs. |
| `candidates/` | Candidate management endpoints. |
| `config/` | Configuration panel handlers. |
| `handlers/` | Low-level request handlers. |
| `misc/` | SSE, HTML generation, lifecycle management. |
| `state/` | Runtime state management. |
| `submissions/` | Submission handling with human-in-the-loop gates. |

### `brain_alpha_ops/compliance/` — Redline Compliance

8 compliance check types: alignment, coverage, datasets, no-custom-extension,
thresholds, traceability, helpers, models. Entry point: `redline_verifier.py`.

### `brain_alpha_ops/config/` — Configuration System

| Module | Responsibility |
|---|---|
| `_loader.py` | `load_run_config()`, `validate_run_config()`, `write_run_config()` with jsonschema validation. |
| `config_models.py` | Dataclasses: `RunConfig`, `OpsConfig`, `WebConfig`, `ResearchBudget`, `ScoringConfig`, etc. |
| `config_schema.py` | JSON Schema validation for `run_config.json`. |
| `config_domain_validation.py` | Canonical enum validators for compliance (regions, delays, neutralizations, etc.). |
| `config_preset.json` | 7 preset configurations (usa_standard, usa_liquid, usa_sector, etc.). |

### `brain_alpha_ops/shared/` — Shared Utilities

Common helpers, constants, and cross-cutting concerns.

### `brain_alpha_ops/ux/` — User Experience

Guided pipeline flow, terminal formatting, and user interaction helpers.

### `brain_alpha_ops/i18n/` — Internationalization

Multi-language support for UI strings and messages.

### `brain_alpha_ops/monitoring/` — Observability

Metrics, health checks, and runtime monitoring.

## Data Flow

### Research Pipeline Cycle

```
1. Generator produces candidate alphas
   ├── Hypothesis-driven (70%): from YAML hypothesis library
   ├── Experience-feedback (20%): based on prior results
   └── Random exploration (10%): novel expressions

2. Candidates enter the candidate pool
   └── Filtered by local quality score threshold

3. Scoring applies three-layer evaluation
   ├── Prior score (30%): based on expression structure, fields, operators
   ├── Empirical score (45%): backtested metrics (sharpe, fitness, turnover)
   └── Checklist score (25%): hard gates + compliance checks

4. Convergence tracking monitors improvement
   ├── BCa Bootstrap 90% CI for avg_sharpe
   ├── Spearman rank-correlation trends
   └── Stall detection → strategy profile switching

5. Top candidates presented to human via web console
   └── Human approves → submission to BRAIN platform
```

### Execution Backend Selection

```
BRAIN_ALPHA_OPS_EXECUTION_MODE env var
        │
        ├── "browser" (default) → BrowserExecutionAdapter (Playwright)
        │   └── Drives real BRAIN Web UI
        │
        └── "api" → ApiExecutionBackend
            └── Direct HTTP to api.worldquantbrain.com
```

## Key Abstractions

### `AlphaResearchPipeline`

The central orchestrator. Composed via 6 mixins:

| Mixin | Responsibility |
|---|---|
| `PipelineServiceFactoryMixin` | Creates and wires service dependencies |
| `PipelineSnapshotMixin` | Serializes/deserializes pipeline state |
| `PipelineCandidatePoolMixin` | Manages the candidate alpha pool |
| `PipelineContextSyncMixin` | Syncs official BRAIN data context |
| `PipelineBacktestMixin` | Runs local and official backtests |
| `PipelineSubmissionMixin` | Handles submission with HIL gates |

Accepts either `OfficialBrainAPI` or any `AlphaExecutionBackend` implementor.

### `CandidateGenerator`

Three generation modes with configurable ratios:

```json
"generation_mode_ratio": "70/20/10"
```

Uses `OfficialDataLoader`, `FieldDatasetMapper`, `DynamicThemeEngine`, and
`DatasetSelector` to produce field-operator-combination expressions.

### Scoring System

Three-layer architecture with weighted combination:

```python
# Layer weights (configurable)
prior_weight = 0.30      # Expression structure analysis
empirical_weight = 0.45  # Backtest metrics
checklist_weight = 0.25  # Hard gates + compliance
```

8 hard gates with constrained whitelist:
`sharpe`, `fitness`, `turnover_min`, `turnover_platform`, `self_correlation`,
`prod_correlation`, `weight_concentration`, `sub_universe_sharpe`

### `ConvergenceTracker`

Statistical convergence monitoring:
- **BCa Bootstrap**: 90% confidence intervals for average Sharpe ratio
- **Spearman rank-correlation**: trend detection across cycles
- **Stall detection**: N cycles without significant improvement triggers
  strategy profile switching recommendation

### `AlphaExecutionBackend` Protocol

Clean separation between browser and API execution modes:

```python
class AlphaExecutionBackend(Protocol):
    def authenticate(self, credentials: dict) -> dict: ...
    def simulate_alpha(self, expression: str, settings: dict) -> dict: ...
    def check_alpha(self, alpha_id: str) -> dict: ...
    def submit_alpha(self, alpha_id: str) -> dict: ...
    def get_evidence(self) -> ExecutionEvidence: ...
```

Two implementations:
- `ApiExecutionBackend`: direct HTTP (dev/tools only)
- `BrowserExecutionAdapter`: Playwright browser automation (production default)

## Configuration System

### `config/run_config.json`

Central configuration file validated by JSON Schema. Structure:

```json
{
  "schema_version": "v2.0",
  "environment": "production",
  "auto_submit": false,
  "credentials": { "username_env": "...", "password_env": "...", "token_env": "..." },
  "web": { "host": "127.0.0.1", "port": 8765, "session_ttl_seconds": 43200, ... },
  "ops": {
    "settings": { "instrumentType": "EQUITY", "region": "USA", ... },
    "budget": { "max_candidates_per_cycle": 20, "max_cycles": 10, ... },
    "scoring": { ... },
    "thresholds": { "min_sharpe": 1.25, "min_fitness": 1.0, ... },
    "submission_policy": { "max_auto_submissions_per_day": 3, ... },
    "official_api": { "base_url": "https://api.worldquantbrain.com", ... }
  }
}
```

### Preset Configurations

7 built-in presets in `config_preset.json`:
`usa_standard`, `usa_liquid`, `usa_sector`, `usa_market`,
`europe_standard`, `global_market`, `china_standard`

### Environment Variables

| Variable | Purpose |
|---|---|
| `BRAIN_USERNAME` / `BRAIN_PASSWORD` / `BRAIN_TOKEN` | API credentials |
| `BRAIN_ALPHA_OPS_EXECUTION_MODE` | `browser` or `api` |
| `BRAIN_ALPHA_OPS_WEB_FRONTEND` | `react` or default HTML |
| `BRAIN_ALPHA_OPS_HOME` | Override project root |
| `BRAIN_ALPHA_OPS_WEB_ADMIN_TOKEN` | Admin token for remote access |
| `BRAIN_ALPHA_FORCE_REAL_SUBMIT` | Test-only submit bypass |
| `BRAIN_ALPHA_ENABLE_REAL_SUBMIT_TESTS` | Test-only submit enable |

## Persistence

- **JSONL files**: Candidate history, pipeline snapshots, research journals
- **SQLite**: Structured query storage
- **API cache**: Cached BRAIN API responses in `data/api_cache/`
- **No external database** — fully self-contained

## Frontend Architecture

React 18 + TypeScript + Tailwind CSS (46 components, 15 hooks):

- `Dashboard`, `Sidebar`, `PhaseShell` — layout and navigation
- `CandidateTable`, `CandidateDetailPanel`, `CandidateRow` — candidate display
- `ConfigPanel`, `ScoringPanel`, `QualityCheckPanel` — configuration and scoring
- `SubmissionPanel`, `SubmissionConfirmPanel`, `SubmissionGates` — submission workflow
- `JobMonitor`, `ProgressFeedback`, `ToastContainer` — operational feedback
- `FlowGuide`, `StepGuide`, `StatusFlowDiagram` — guided workflow

Key hooks: `useApi`, `useCandidateActions`, `useJobState`, `useSSE`,
`useKeyboardShortcuts`, `useToast`.

## Technology Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12+ (stdlib HTTP, no framework) |
| Frontend | React 18, TypeScript 5.4, Vite 5, Tailwind CSS 3.4 |
| Browser automation | Playwright + Chromium |
| Persistence | JSONL, SQLite (no external DB) |
| Testing | pytest (2,874+ tests), Vitest (frontend) |
| Container | Docker multi-stage (Node 22 + Python 3.13-slim) |
| CI | GitHub Actions (quality-gate.yml) |
