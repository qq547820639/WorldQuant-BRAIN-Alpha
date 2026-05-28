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

## Strict React Gate

Use strict mode when a machine is expected to have React build tooling installed:

```bash
python3 scripts/quality_gate.py --final-release --strict-react-build --json
```

Use strict build mode when CI must execute the React build:

```bash
python3 scripts/quality_gate.py --final-release --strict-react-build --run-react-build --json
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

## Current Local Status

On the 2026-05-28 local verification machine, strict React verification fails because `npm`, a lockfile, `node_modules`, and required React packages are not present. This is an environment/tooling gap, not a production inline Web console failure.
