# React Build Verification

The production Web console is the inline HTML/JS surface under `brain_alpha_ops/web/index.html`.
The React app under `brain_alpha_ops/web/react_app` is a mirror surface and is optional unless
CI or a release job explicitly enables strict React verification.

## Default Release Gate

Use the normal release gate for the production surface:

```bash
python3 scripts/quality_gate.py --final-release --json
```

This includes `react_build_env` as an advisory step. It reports whether the React build environment is ready, but it does not block the inline production release when local React tooling is missing.
The final-release path also runs pytest with the configured `80%` coverage threshold.

## Strict React Gate

Use strict mode when a machine is expected to have React build tooling installed:

```bash
python3 scripts/quality_gate.py --final-release --strict-react-build --json
```

Use strict build mode when CI must execute the React build:

```bash
python3 scripts/quality_gate.py --final-release --strict-react-build --run-react-build --json
```

Use the React preview smoke when the release check should also prove that the local backend can serve the built React artifact through the normal HTTP/session stack:

```bash
python3 scripts/quality_gate.py --final-release --react-preview-smoke --json
```

Strict build mode requires:

1. `node` and `npm` on `PATH`.
2. A committed package-manager lockfile in `brain_alpha_ops/web/react_app`.
3. Installed dependencies in `brain_alpha_ops/web/react_app/node_modules`.
4. Required packages: `react`, `react-dom`, `typescript`, `vite`, and `@vitejs/plugin-react`.

## Direct Preflight

Run the preflight without blocking:

```bash
python3 scripts/check_react_build_env.py --json
```

Run the preflight as a blocking check:

```bash
python3 scripts/check_react_build_env.py --strict --json
```

Run the React build directly through the preflight when prerequisites are ready:

```bash
python3 scripts/check_react_build_env.py --strict --run-build --json
```

## Backend Preview Mode

The local backend serves the inline production console by default. To preview the built React artifact through the same backend and API/session stack, opt in explicitly:

```bash
python3 launch_web.py --frontend react --no-browser
```

In this mode, `launch_web.py` serves `brain_alpha_ops/web/react_app/dist/index.html` when it exists, and serves `/assets/*` only from `brain_alpha_ops/web/react_app/dist/assets`. Leave the frontend selector unset, pass `--frontend inline`, or set `BRAIN_ALPHA_OPS_WEB_FRONTEND=inline`, for the production inline console. `BRAIN_ALPHA_OPS_WEB_FRONTEND=react` remains supported for scripts that prefer environment-variable configuration.

The same backend preview can be smoke-tested directly:

```bash
python3 launch_web.py --smoke-test --frontend react --port 9066
```

## Current Local Status

On the 2026-05-30 local verification machine, the React mirror has a lockfile, installed `node_modules`, required React packages, and a fresh `brain_alpha_ops/web/react_app/dist/index.html` artifact. The default advisory preflight still reports `ready=false` when `npm` is not on `PATH`, but the missing tool is now the only reported prerequisite gap on the default shell path. This remains an environment/tooling issue, not a production inline Web console failure.

The current local evidence also includes a successful `quality_gate.py --react-preview-smoke` run. That check launched `launch_web.py --smoke-test --frontend react` on a temporary loopback port, verified the backend-served React page and `/api/config`, then shut down cleanly.
