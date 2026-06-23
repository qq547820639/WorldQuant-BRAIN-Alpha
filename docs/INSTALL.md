# Installation — BRAIN Alpha Ops

> Version 0.5.0 — Local alpha research workstation for the WorldQuant BRAIN platform.

## System Requirements

| Requirement | Minimum | Recommended |
|---|---|---|
| Python | 3.12+ | 3.13+ |
| Node.js | 18+ (for React frontend) | 22+ |
| RAM | 4 GB | 8 GB+ |
| Disk | 2 GB | 5 GB+ (including data cache) |
| OS | macOS, Linux, Windows (WSL2) | macOS or Linux |

### Optional

- **Playwright + Chromium**: Required for browser execution backend (default)
- **Docker**: For containerized deployment

## Local Python Installation

### 1. Clone the repository

```bash
git clone https://github.com/<org>/WorldQuant-BRAIN-Alpha.git
cd WorldQuant-BRAIN-Alpha
```

### 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -e ".[browser,test,dev]"
```

This installs:
- Core dependencies from `pyproject.toml`
- Browser extras (Playwright) for the browser execution backend
- Test dependencies (pytest, fixtures)
- Dev dependencies (linting, type checking)

### 4. Install Playwright browsers

```bash
python -m playwright install chromium --with-deps
```

This downloads Chromium and its system dependencies (~300 MB).

### 5. Set environment variables

```bash
export BRAIN_USERNAME="your_username"
export BRAIN_PASSWORD="your_password"
# OR use a bearer token instead:
export BRAIN_TOKEN="your_token"
```

See [Environment Variables](#environment-variables) for the full list.

### 6. Start the web console

```bash
python launch_web.py
```

Open http://127.0.0.1:8765 in your browser.

## Docker Installation

### 1. Build and run with Docker Compose

```bash
docker compose up --build
```

This builds a multi-stage container:
- **Stage 1**: Node 22 builds the React frontend
- **Stage 2**: Python 3.13-slim runs the backend with bundled frontend

### 2. Set credentials

Pass credentials via environment variables:

```bash
BRAIN_USERNAME=your_username \
BRAIN_PASSWORD=your_password \
docker compose up
```

Or create a `.env` file (do **not** commit it):

```env
BRAIN_USERNAME=your_username
BRAIN_PASSWORD=your_password
```

### 3. Data persistence

The `./data` directory is mounted into the container. Your pipeline state,
candidate history, and API cache persist across container restarts.

### 4. Health check

The container exposes a health endpoint at `http://127.0.0.1:8765/api/health`.

### Manual Docker build

```bash
docker build -t brain-alpha-ops .
docker run -p 8765:8765 \
  -e BRAIN_USERNAME=your_username \
  -e BRAIN_PASSWORD=your_password \
  -v $(pwd)/data:/app/data \
  brain-alpha-ops
```

## React Frontend Setup

The React frontend is bundled into the Python package during `pip install`. For
development with hot-reload:

### 1. Install frontend dependencies

```bash
cd brain_alpha_ops/web/react_app
npm install
```

### 2. Start the dev server

```bash
npm run dev
```

This starts Vite with hot module replacement. The dev server proxies API
requests to the Python backend at `http://127.0.0.1:8765`.

### 3. Build for production

```bash
npm run build
```

Output goes to `brain_alpha_ops/web/react_app/dist/`, which is served by the
Python backend.

### Frontend technology stack

- React 18.3
- TypeScript 5.4
- Vite 5.3
- Tailwind CSS 3.4
- Vitest (testing)

## Environment Variables

### Required (at least one auth method)

| Variable | Purpose |
|---|---|
| `BRAIN_USERNAME` | BRAIN account username |
| `BRAIN_PASSWORD` | BRAIN account password |
| `BRAIN_TOKEN` | Alternative: bearer token (use instead of username/password) |

### Optional

| Variable | Default | Purpose |
|---|---|---|
| `BRAIN_ALPHA_OPS_EXECUTION_MODE` | `browser` | Execution backend: `browser` or `api` |
| `BRAIN_ALPHA_OPS_WEB_FRONTEND` | `react` | Web frontend: `react` or default HTML |
| `BRAIN_ALPHA_OPS_HOME` | (project root) | Override project root directory |
| `BRAIN_ALPHA_OPS_WEB_ADMIN_TOKEN` | — | Required for remote access |
| `BRAIN_ALPHA_FORCE_REAL_SUBMIT` | — | Test-only: bypass submit guard (requires `1`) |
| `BRAIN_ALPHA_ENABLE_REAL_SUBMIT_TESTS` | — | Test-only: enable submit tests (requires `1`) |

### Docker defaults

| Variable | Value |
|---|---|
| `PYTHONDONTWRITEBYTECODE` | `1` |
| `PYTHONUNBUFFERED` | `1` |

## Configuration

### `config/run_config.json`

The main configuration file. Edit to customize:

- **Credentials**: Use `_env` fields to reference environment variables (e.g.,
  `username_env: "BRAIN_USERNAME"`)
- **Web settings**: Host, port, session TTL, remote access
- **Ops settings**: Budget, scoring, thresholds, submission policy, API endpoints

### Presets

7 built-in presets in `config/config_preset.json`:
`usa_standard`, `usa_liquid`, `usa_sector`, `usa_market`,
`europe_standard`, `global_market`, `china_standard`

### JSON Schema validation

`run_config.json` is validated against a JSON schema on load. Invalid configurations
will raise clear error messages.

## Troubleshooting

### Playwright/Chromium issues

**Symptom**: `playwright._impl._api.errors.Error: ...`

**Fix**: Reinstall Playwright with system dependencies:
```bash
python -m playwright install chromium --with-deps
```

**macOS-specific**: If Chromium fails to launch, check System Preferences → Security
& Privacy for blocked app permissions.

### Port already in use

**Symptom**: `OSError: [Errno 48] Address already in use`

**Fix**: Either kill the process using port 8765, or change the port in
`config/run_config.json`:
```json
"web": { "port": 8766 }
```

### Permission denied on data directory

**Symptom**: `PermissionError: [Errno 13] Permission denied: 'data/...'`

**Fix**: Ensure the data directory is writable:
```bash
chmod -R u+w data/
```

Or in Docker, check volume mount permissions.

### Missing credentials

**Symptom**: `RuntimeError: 环境变量 BRAIN_USERNAME 未设置`

**Fix**: Set the required environment variables before starting:
```bash
export BRAIN_USERNAME="your_username"
export BRAIN_PASSWORD="your_token"
```

### Frontend build fails

**Symptom**: `npm ERR! code ERESOLVE` or similar

**Fix**: Clear node_modules and reinstall:
```bash
cd brain_alpha_ops/web/react_app
rm -rf node_modules package-lock.json
npm install
npm run build
```

### Docker build fails at Playwright install

**Symptom**: Chromium download fails or system dependencies are missing

**Fix**: Ensure Docker has enough disk space and network access. The Playwright
install downloads ~300 MB of browser binaries and system libraries.

### Type checker errors

**Symptom**: `mypy` or `pyright` report type errors

**Fix**: Run with the project's type checking configuration:
```bash
mypy brain_alpha_ops/
```

### Tests fail

**Symptom**: `pytest` reports failures

**Fix**: Ensure test dependencies are installed:
```bash
pip install -e ".[test]"
pytest tests/
```

For browser-related tests, ensure Playwright is installed:
```bash
python -m playwright install chromium
```
