# BRAIN Alpha Ops

**Account-safety-first** WorldQuant BRAIN alpha research operations toolkit.

A local-first web console for end-to-end BRAIN alpha lifecycle management:
connect → sync cloud alphas → generate candidates → score & validate → pre-submit review → monitor progress.

All operations are observable, traceable, and auditable.

![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square)
![License MIT](https://img.shields.io/badge/License-MIT-111827?style=flat-square)
![Version](https://img.shields.io/badge/Version-0.3.0-6366F1?style=flat-square)

---

## Quick Start

### Prerequisites

- Python 3.10+
- WorldQuant BRAIN account
- Modern browser (Chrome / Edge / Safari / Firefox)

### Install & Launch

```bash
cd WorldQuant-BRAIN-Alpha
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
python3 launch_web.py
```

The web console opens at `http://127.0.0.1:8765`. Enter your BRAIN credentials in the connection panel.

### Credentials

Three options, in order of security preference:

| Method | Setting | Security |
|--------|---------|----------|
| Browser input | Web console connection panel | ⭐⭐⭐ Best |
| Environment variables | `BRAIN_USERNAME` / `BRAIN_PASSWORD` | ⭐⭐ Good |
| Config file | `config/run_config.json` credentials field | ⭐ Dev only |

Credentials are never written to disk, logs, or screenshots.

---

## Architecture

The system runs as a local HTTP server (Python standard library) with an inline web console. No external web dependencies.

```
Browser (localhost:8765)  ←→  Local HTTP Server  ←→  BRAIN API (api.worldquantbrain.com)
                                        ↕
                                  Local Storage (data/)
```

### Key Modules

| Module | Purpose |
|--------|---------|
| `brain_alpha_ops/web/` | HTTP server, routing, session management, SSE progress |
| `brain_alpha_ops/brain_api/` | BRAIN official API adapter (auth, pagination, simulation, validation) |
| `brain_alpha_ops/research/` | Alpha generation, scoring, optimization, backtesting, pipeline orchestration |
| `brain_alpha_ops/compliance/` | Redline checks, dataset verification, traceability |
| `brain_alpha_ops/scoring/` | Multi-dimensional scoring, anti-overfit, release gates |
| `brain_alpha_ops/config/` | Runtime configuration loader and validation |

### Quality Gate

CI/CD runs on every push to `main` via GitHub Actions:

1. Python compile check
2. Config validation
3. Dependency policy check
4. Frontend inline sync check
5. Secret artifact scan
6. Log redaction audit
7. Module size audit
8. Full test suite (2600+ tests)

---

## Configuration

Main config: `config/run_config.json`

```text
config/run_config.json
├── environment        → "production" | "simulation"
├── credentials        → username / password (leave empty, use env vars)
├── web                → host, port, session TTL
├── ops                → market settings, scoring, thresholds, submission policy
│   ├── settings       → instrumentType, region, universe, delay, dataset
│   ├── thresholds     → min_sharpe, min_fitness, max_self_correlation
│   └── submission_policy → max_auto_submissions, max_similarity
└── official_api       → BRAIN API endpoints and polling parameters
```

---

## Project Structure

```text
WorldQuant-BRAIN-Alpha/
├── brain_alpha_ops/       # Core source code
│   ├── web/               # Web console (frontend + backend)
│   ├── brain_api/         # BRAIN official API adapter
│   ├── research/          # Research engine
│   ├── compliance/        # Compliance checks
│   ├── scoring/           # Scoring system
│   ├── config/            # Config loader
│   └── data/              # Data adapters
├── config/                # Runtime configuration
├── data/                  # Runtime data (cache, history, job ledgers)
├── tests/                 # Test suite (2600+ tests)
├── scripts/               # Quality gate and maintenance scripts
├── launch_web.py          # Web server entry point
├── build_prod.py          # PyInstaller production build
├── fetch_official_context.py  # BRAIN context refresh entry point
├── pyproject.toml         # Project metadata
└── requirements.lock      # Locked dependencies
```

---

## Development

### Install dev dependencies

```bash
python3 -m pip install -e ".[test,dev]"
```

### Run tests

```bash
python3 -m pytest tests/ -v
python3 -m pytest tests/ --cov=brain_alpha_ops --cov-report=html
```

### React frontend (optional)

```bash
cd brain_alpha_ops/web/react_app
npm run dev
```

Then launch with React frontend:

```bash
BRAIN_ALPHA_OPS_WEB_FRONTEND=react python3 launch_web.py
```

### Code quality

- Lint: `ruff check brain_alpha_ops/`
- Type check: `mypy brain_alpha_ops/`
- Coverage minimum: 75% (enforced by CI)

---

## Security

- Credentials stay in memory only — never persisted to disk, logs, or screenshots
- Web server binds to `127.0.0.1` by default (localhost only)
- CSRF protection, session management, and replay attack prevention built in
- Secret artifact scan runs on every CI push

---

## License

MIT License — see [LICENSE](LICENSE).

---

## Links

- [WorldQuant BRAIN](https://brainai.worldquant.com/)
- [GitHub Repository](https://github.com/qq547820639/WorldQuant-BRAIN-Alpha)
- [CI / Quality Gate](https://github.com/qq547820639/WorldQuant-BRAIN-Alpha/actions)
