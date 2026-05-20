# Strategy Plugin Safety Guide

Strategy plugins are optional local Python extensions for the adaptive strategy lifecycle. They are loaded from `module:object` specs, so enabling a plugin is equivalent to executing trusted local code inside the current process.

## Supported Spec Format

- Web field: `Strategy Plugins` plus one `Plugin Specs` entry per line.
- Config fields: `ops.budget.strategy_plugins_enabled` and `ops.budget.strategy_plugin_specs`.
- Example spec: `brain_alpha_ops.examples.strategy_plugin:ConservativeMeanReversionPlugin`.

Each plugin object must expose:

- `name`
- `propose(context)`
- `validate(profile, context)`
- `mutate(profile, context)`
- `retire(profile, context)`

The registry records load errors and runtime errors in the pipeline summary instead of crashing the whole run.

## Safety Rules

- Load only reviewed local modules. Do not paste specs from untrusted sources.
- Keep plugin code deterministic and side-effect light. Prefer returning profile suggestions over calling network, shell, or file mutation APIs.
- Never store credentials, tokens, or raw assistant prompts in plugin results.
- Treat plugin output as advisory. Official validation, submission checks, duplicate detection, and observability confirmation still remain the final gates.
- Pin and review any third-party dependency used by a plugin before adding it to project dependencies.

## Review Checklist

- The plugin returns plain JSON-serializable dictionaries.
- The plugin has no import-time side effects beyond class/function definitions.
- Runtime errors are acceptable and visible in `strategy_plugins.runtime_errors`.
- The plugin does not bypass `SubmissionLedger`, official-call guards, or cloud duplicate checks.
- The plugin spec is disabled by default in shared config and enabled only for the intended workspace.

## Example

The repository includes `brain_alpha_ops/examples/strategy_plugin.py` as a safe template. It demonstrates a conservative mean-reversion profile suggestion, validation feedback, mutation, and retirement payloads without touching external services.
