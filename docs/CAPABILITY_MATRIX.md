# Template vs Local Evaluator Capability Matrix

Maps each fallback template to its operator dependencies and shows whether the
local expression evaluator (`LocalExpressionEvaluator`) can evaluate it offline.

## Quick reference

| Status | Meaning |
|--------|---------|
| ✅ | Template fully supported by local evaluator |
| ⚠️ | Template uses unsupported operators — needs official BRAIN API |

## Template matrix

| # | Family | Template expression | Local? |
|---|--------|---------------------|--------|
| 1 | momentum | `rank(divide(ts_delta({f1}, {w}), ts_std_dev({f2}, {w})))` | ✅ |
| 2 | momentum | `rank(ts_rank({f1}, {w}))` | ✅ |
| 3 | quality | `rank(zscore({f1}))` | ✅ |
| 4 | value | `rank(reverse({f1}))` | ✅ |
| 5 | liquidity | `rank(ts_mean({f1}, {w}))` | ✅ |
| 6 | relative_momentum | `rank(subtract(ts_delta({f1}, {w}), ts_delta({f2}, {w})))` | ✅ |
| 7 | reversal | `reverse(ts_rank({f1}, {w}))` | ✅ |
| 8 | hybrid | `multiply(rank({f1}), rank(ts_delta({f2}, {w})))` | ✅ |
| 9 | co_movement | `rank(ts_corr({f1}, {f2}, {w}))` | ✅ |
| 10 | momentum | `ts_rank(ts_delta({f1}, {w}), {w})` | ✅ |
| 11 | decay | `rank(ts_decay_linear(ts_delta({f1}, {w}), {w}))` | ✅ |
| 12 | volatility | `rank(reverse(ts_std_dev({f1}, {w})))` | ✅ |
| 13 | momentum | `rank(divide(ts_delta({f1}, {w}), ts_std_dev({f1}, {w})))` | ✅ |
| 14 | relative_value | `rank(subtract(zscore({f1}), zscore({f2})))` | ✅ |
| 15 | liquidity | `rank(divide({f1}, ts_mean({f1}, {w})))` | ✅ |
| 16 | relative_momentum | `rank(subtract(ts_mean({f1}, {w}), ts_mean({f2}, {w})))` | ✅ |
| 17 | co_movement | `rank(ts_covariance({f1}, {f2}, {w}))` | ⚠️ |
| 18 | conditional | `rank(if_else(greater(ts_delta({f1}, {w}), 0), {f1}, reverse({f1})))` | ✅ |
| 19 | momentum | `rank(winsorize(ts_delta({f1}, {w}), 3))` | ✅ |
| 20 | volatility | `rank(divide(ts_std_dev({f1}, {w}), ts_std_dev({f2}, {w})))` | ✅ |
| 21 | hybrid | `rank(divide(ts_mean({f1}, {w}), ts_std_dev({f2}, {w})))` | ✅ |
| 22 | momentum | `rank(ts_sum(ts_delta({f1}, {w}), {w}))` | ✅ |

## Summary

- **21 of 22** templates are fully evaluable locally.
- **1 template** (`ts_covariance`) requires the official BRAIN API and cannot be
  tested via `LocalExpressionEvaluator`.

## Operators: local vs official API

| Operator | Local evaluator | Official BRAIN API |
|----------|:-:|:-:|
| `rank` | ✅ | ✅ |
| `zscore` | ✅ | ✅ |
| `ts_zscore` | ✅ | ✅ |
| `ts_mean` | ✅ | ✅ |
| `ts_std_dev` | ✅ | ✅ |
| `ts_delta` | ✅ | ✅ |
| `ts_sum` | ✅ | ✅ |
| `ts_min` | ✅ | ✅ |
| `ts_max` | ✅ | ✅ |
| `ts_corr` | ✅ | ✅ |
| `ts_rank` | ✅ | ✅ |
| `ts_decay_linear` | ✅ | ✅ |
| `neg` / `reverse` | ✅ | ✅ |
| `abs` | ✅ | ✅ |
| `log` | ✅ | ✅ |
| `sign` | ✅ | ✅ |
| `power` | ✅ | ✅ |
| `multiply` | ✅ | ✅ |
| `divide` | ✅ | ✅ |
| `subtract` | ✅ | ✅ |
| `greater` | ✅ | ✅ |
| `if_else` | ✅ | ✅ |
| `group_rank` | ✅ (simplified) | ✅ |
| `group_neutralize` | ✅ | ✅ |
| `winsorize` | ✅ | ✅ |
| `normalize` | ✅ | ✅ |
| `ts_covariance` | ❌ | ✅ |
| `delta` | ❌ | ✅ |
| `delay` | ❌ | ✅ |
| `returns` | ❌ | ✅ |
| `ts_product` | ❌ | ✅ |
| `signedpower` | ❌ | ✅ |
| `ts_arg_max` | ❌ | ✅ |
| `ts_arg_min` | ❌ | ✅ |
| `sequence` | ❌ | ✅ |
| `indneutralize` | ❌ | ✅ |

## Notes

- Templates are defined in `brain_alpha_ops/research/templates.yaml` (also
  inlined as `_BUILTIN_FALLBACK_TEMPLATES` in `generator.py`).
- The local evaluator lives in
  `brain_alpha_ops/research/local_backtest/expression_evaluator.py`.
- The `group_rank` local implementation is simplified — it performs
  cross-sectional rank without actual sector grouping (the `s` argument is
  ignored).
- Unknown functions in the local evaluator silently return the first argument
  (or zeros), so unsupported operators won't crash but produce incorrect
  results. This is why `ts_covariance` templates must be filtered before
  local evaluation.
