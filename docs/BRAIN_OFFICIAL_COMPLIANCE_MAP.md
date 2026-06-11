# WorldQuant BRAIN Official Compliance Map

**Verified date**: 2026-06-09
**Authoritative evidence**: local official-context cache metadata sourced from `official_api`, canonical compliance verifier, redline verifier, parameter traceability, and final release gate.
**Scope**: map the current repository implementation to executable BRAIN compliance gates. This document is evidence-derived; community notes are not used as normative rules.

---

## Current Gate Status

| Gate | Current result | What it proves |
|---|---:|---|
| `brain_alpha_ops.compliance.redline_verifier --block --json` | PASS 79/79 | Six technical redlines are executable and currently non-blocking. |
| `scripts/verify_canonical_compliance.py --config config/run_config.json --json` | PASS 6/6 | Thresholds, API paths, settings enums, scoring simulation, official context, and dataset IDs match canonical policy. |
| `scripts/check_official_context.py --config config/run_config.json --strict-freshness --json` | PASS | Official fields/operators/datasets are complete, hash-matched, and fresh. |
| `scripts/check_parameter_traceability.py --config config/run_config.json --json` | PASS | Production parameters are traceable to canonical sources. |
| `scripts/final_release_gate.py --config config/run_config.json --json` | PASS | Release-level compliance checks are currently green. |
| `scripts/check_live_submit_readiness.py --config config/run_config.json --json` | Not submit-ready | Submit is still blocked unless same-candidate readiness becomes true and the user explicitly confirms. |

Latest official cache metadata:

- fields: `7780`, source `official_api`, complete, not stale.
- operators: `66`, source `official_api`, complete, not stale.
- datasets: `17`, source `official_api`, complete, not stale.
- saved at `2026-06-07T15:19:07Z`, expires at `2026-06-14T15:19:07Z`.

---

## API Endpoint Alignment

| Endpoint | Config field | Current status |
|---|---|---|
| `https://api.worldquantbrain.com` | `base_url` | PASS |
| `/authentication` | `authentication_path` | PASS |
| `/simulations` | `simulations_path` | PASS |
| `/data-sets` | `data_sets_path` | PASS |
| `/data-fields` | `data_fields_path` | PASS |
| `/operators` | `operators_path` | PASS |
| `/users/self/alphas` | `user_alphas_path` | PASS |
| `/users/self` | `user_profile_path` | PASS |
| `/alphas/{alpha_id}` | `alpha_path_template` | PASS |
| `/alphas/{alpha_id}/check` | `alpha_check_path_template` | PASS |
| `/alphas/{alpha_id}/submit` | `alpha_submit_path_template` | PASS |
| `/alphas/correlations/check` | `alpha_correlations_path` | PASS |

---

## Settings And Threshold Alignment

Current configured production settings are canonical-compliant:

- `instrumentType=EQUITY`
- `region=USA`
- `universe=TOP3000`
- `delay=1`
- `neutralization=SUBINDUSTRY`
- `pasteurization=ON`
- `unitHandling=VERIFY`
- `nanHandling=ON`
- `language=FASTEXPR`
- `type=REGULAR`

Current threshold verifier reports zero deviation for:

- `min_sharpe=1.25`
- `min_sharpe_delay0=2.0`
- `min_fitness=1.0`
- `min_fitness_delay0=1.3`
- `min_turnover=0.01`
- `platform_max_turnover=0.70`
- `max_self_correlation=0.70`
- `max_prod_correlation=0.70`
- `max_weight_concentration=0.10`
- `sub_universe_sharpe_min_ratio=0.75`

---

## Official Context And Dataset Coverage

The official context gate reports:

- `official_fields.json`: 7780 identities, no duplicate or missing identities.
- `official_operators.json`: 66 identities, no duplicate or missing identities.
- `official_datasets.json`: 17 identities, no duplicate or missing identities.
- Dataset lineage: dataset field count sum equals field count.

Current dataset IDs accepted by the canonical verifier:

`analyst4`, `fundamental2`, `fundamental6`, `model16`, `model51`, `model53`, `model77`, `news12`, `news18`, `option8`, `option9`, `pv1`, `pv13`, `sentiment1`, `socialmedia12`, `socialmedia8`, `univ1`.

---

## Safety Boundary

This compliance map does not claim that an Alpha is ready to submit. The current stop rule remains:

1. Run `scripts/check_live_submit_readiness.py --config config/run_config.json --json`.
2. Require `ready_to_submit=true` for the same candidate that would be submitted.
3. Require explicit human confirmation before any real BRAIN submit.

As of this verification pass, local compliance is green but submit readiness is still blocked by missing eligible same-candidate evidence.

---

## Maintenance Rule

Update this file only from current executable evidence. If any compliance gate starts reporting deviations, record the failing command, exact deviation, affected module, and remediation status here.
