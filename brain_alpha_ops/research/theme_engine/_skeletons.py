"""Dynamic Alpha theme engine — template skeletons.

Holds the ``TEMPLATE_SKELETONS`` dict that maps category names to expression
skeleton lists.  P1-7 expanded from ~38 to 52+ templates to improve
expression diversity (checks.jsonl analysis showed 75%+ BLOCKED due to
skeleton convergence).
"""
from __future__ import annotations

TEMPLATE_SKELETONS: dict[str, list[str]] = {
    "momentum": [
        "ts_rank({FIELD}, {WINDOW})",
        "ts_delta({FIELD}, {WINDOW})",
        "ts_sum({FIELD}, {WINDOW})",
        "ts_rank(ts_delta({FIELD}, {WINDOW}), {WINDOW2})",
        "group_rank(ts_delta({FIELD}, {WINDOW}), {GROUP})",
        # P1-7 additions
        "rank(ts_decay_linear(ts_delta({FIELD}, {WINDOW}), {WINDOW2}))",
        "ts_rank({FIELD}, {WINDOW}) - ts_rank({FIELD}, {WINDOW2})",
        "rank(ts_mean(ts_delta({FIELD}, {WINDOW}), {WINDOW2}))",
        # M-01 v3: diversity expansion — mid-frequency momentum, weighted variants
        "rank(ts_delta({FIELD}, {WINDOW}) * ts_std_dev({FIELD}, {WINDOW2}))",
        "ts_rank(ts_decay_linear({FIELD}, {WINDOW}), {WINDOW2})",
        "group_rank(ts_decay_linear({FIELD}, {WINDOW}), {GROUP})",
        "rank(winsorize(ts_delta({FIELD}, {WINDOW}), 0.01))",
        "rank(ts_delta({FIELD}, {WINDOW}) / ts_delta({FIELD}, {WINDOW2}))",
        "ts_rank(divide({FIELD}, ts_mean({FIELD}, {WINDOW})), {WINDOW2})",
    ],
    "reversal": [
        "-1 * ts_rank({FIELD}, {WINDOW})",
        "ts_rank(-1 * ts_delta({FIELD}, {WINDOW}), {WINDOW2})",
        "-1 * ts_zscore({FIELD}, {WINDOW})",
        # P1-7 additions
        "-1 * rank(ts_delta({FIELD}, {WINDOW}) / ts_std_dev({FIELD}, {WINDOW2}))",
        "rank(-ts_delta({FIELD}, {WINDOW}) / ts_std_dev({FIELD}, {WINDOW2}))",
        # M-01 v3: short-term reversal, gap-reversal patterns
        "-1 * rank(ts_delta({FIELD}, {WINDOW}) * sign(ts_delta({FIELD}, {WINDOW2})))",
        "rank(-ts_decay_linear(ts_delta({FIELD}, {WINDOW}), {WINDOW2}))",
        "group_rank(-ts_delta({FIELD}, {WINDOW}), {GROUP})",
        "-1 * ts_rank(ts_mean({FIELD}, {WINDOW}), {WINDOW2})",
        "rank(-ts_delta({FIELD}, {WINDOW}) / ts_mean({FIELD}, {WINDOW2}))",
    ],
    "value": [
        "rank(-{FIELD})",
        "rank(zscore(-{FIELD}))",
        "group_rank(-{FIELD}, {GROUP})",
        # P1-7 additions
        "rank(divide(1, 1 + {FIELD}))",
        "rank(zscore(-{FIELD})) * rank(zscore(-1 / {FIELD}))",
        # M-01 v3: normalized value, sector-relative value
        "rank(-{FIELD} / ts_mean({FIELD}, {WINDOW}))",
        "rank(zscore(-ts_mean({FIELD}, {WINDOW})))",
        "group_rank(divide(1, 1 + {FIELD}), {GROUP})",
        "rank(divide(-{FIELD}, ts_std_dev({FIELD}, {WINDOW})))",
        "rank(zscore(-{FIELD})) + rank(zscore(ts_delta(-{FIELD}, {WINDOW})))",
    ],
    "quality": [
        "rank({FIELD})",
        "rank(zscore({FIELD}))",
        "group_rank({FIELD}, {GROUP})",
        # P1-7 additions
        "rank(ts_mean({FIELD}, {WINDOW}))",
        "rank(zscore(ts_mean({FIELD}, {WINDOW})))",
        # M-01 v3: quality stability, margin consistency
        "rank(ts_mean({FIELD}, {WINDOW}) / ts_std_dev({FIELD}, {WINDOW2}))",
        "rank(zscore(divide({FIELD}, ts_mean({FIELD}, {WINDOW}))))",
        "group_rank(ts_mean({FIELD}, {WINDOW}), {GROUP})",
        "rank(winsorize({FIELD}, 0.02))",
        "rank(ts_mean({FIELD}, {WINDOW}) - ts_mean({FIELD}, {WINDOW2}))",
    ],
    "growth": [
        "rank({FIELD})",
        "rank(ts_delta({FIELD}, {WINDOW}))",
        "group_rank({FIELD}, {GROUP})",
        # P1-7 additions
        "rank(ts_delta({FIELD}, {WINDOW}) / ts_std_dev({FIELD}, {WINDOW2}))",
        "rank(ts_sum(ts_delta({FIELD}, {WINDOW}), {WINDOW2}))",
        # M-01 v3: acceleration, sustained growth
        "rank(ts_delta(ts_delta({FIELD}, {WINDOW}), {WINDOW2}))",
        "rank(ts_mean(ts_delta({FIELD}, {WINDOW}), {WINDOW2}) / ts_std_dev(ts_delta({FIELD}, {WINDOW}), {WINDOW3}))",
        "group_rank(ts_delta({FIELD}, {WINDOW}), {GROUP})",
        "rank(ts_sum(ts_delta({FIELD}, {WINDOW}), {WINDOW2}) / ts_mean({FIELD}, {WINDOW3}))",
        "rank(ts_decay_linear(ts_delta({FIELD}, {WINDOW}), {WINDOW2}))",
    ],
    "volatility": [
        "rank(-ts_std_dev({FIELD}, {WINDOW}))",
        "rank(-ts_zscore(ts_std_dev({FIELD}, {WINDOW}), {WINDOW2}))",
        # P1-7 additions
        "rank(-ts_std_dev({FIELD}, {WINDOW}))",
        "rank(-ts_std_dev({FIELD}, {WINDOW}) / ts_mean({FIELD}, {WINDOW2}))",
        "rank(-ts_covariance({FIELD}, returns, {WINDOW}))",
        # M-01 v3: volatility regime, risk-adjusted variants
        "rank(ts_std_dev({FIELD}, {WINDOW}) - ts_std_dev({FIELD}, {WINDOW2}))",
        "rank(-ts_std_dev(ts_delta({FIELD}, {WINDOW}), {WINDOW2}))",
        "group_rank(-ts_std_dev({FIELD}, {WINDOW}), {GROUP})",
        "rank(-ts_std_dev({FIELD}, {WINDOW}) * ts_mean({FIELD}, {WINDOW2}))",
        "rank(-ts_corr({FIELD}, returns, {WINDOW}) * sign(ts_delta({FIELD}, {WINDOW2})))",
    ],
    "liquidity": [
        "rank(ts_mean({FIELD}, {WINDOW}))",
        "rank(ts_delta({FIELD}, {WINDOW}))",
        "rank(ts_corr({FIELD}, returns, {WINDOW}))",
        # P1-7 additions
        "rank(divide({FIELD}, ts_mean({FIELD}, {WINDOW})))",
        "rank(ts_corr(ts_delta({FIELD}, {WINDOW}), returns, {WINDOW2}))",
        # M-01 v3: liquidity shock, turnover-scaled
        "rank(ts_delta({FIELD}, {WINDOW}) / ts_mean({FIELD}, {WINDOW2}))",
        "rank(ts_std_dev({FIELD}, {WINDOW}) / ts_mean({FIELD}, {WINDOW2}))",
        "group_rank(divide({FIELD}, ts_mean({FIELD}, {WINDOW})), {GROUP})",
        "rank(ts_corr({FIELD}, ts_delta({FIELD}, {WINDOW}), {WINDOW2}))",
    ],
    "cross_sectional": [
        "group_rank({FIELD}, {GROUP})",
        "group_zscore({FIELD}, {GROUP})",
        "group_neutralize({FIELD}, {GROUP})",
        # P1-7 additions
        "group_rank(ts_delta({FIELD}, {WINDOW}), {GROUP})",
        "group_neutralize(zscore({FIELD}), {GROUP})",
        # M-01 v3: sector-relative momentum, industry dispersion
        "group_rank(ts_mean({FIELD}, {WINDOW}), {GROUP})",
        "group_zscore(ts_delta({FIELD}, {WINDOW}), {GROUP})",
        "group_neutralize(ts_rank({FIELD}, {WINDOW}), {GROUP})",
        "rank({FIELD} - group_mean({FIELD}, {GROUP}))",
        "group_rank(ts_decay_linear({FIELD}, {WINDOW}), {GROUP})",
    ],
    "hybrid": [
        "rank(ts_rank({FIELD_A}, {WINDOW})) + rank(ts_rank({FIELD_B}, {WINDOW2}))",
        "rank(zscore({FIELD_A})) * rank(zscore({FIELD_B}))",
        "rank(ts_delta({FIELD_A}, {WINDOW}) / ts_std_dev({FIELD_B}, {WINDOW2}))",
        "rank(zscore(ts_rank({FIELD_A}, {WINDOW})) + zscore(ts_rank({FIELD_B}, {WINDOW2})))",
        # P1-7 additions
        "rank(ts_corr({FIELD_A}, {FIELD_B}, {WINDOW}))",
        "rank(zscore({FIELD_A})) + rank(-ts_std_dev({FIELD_B}, {WINDOW}))",
        "rank(ts_delta({FIELD_A}, {WINDOW})) * rank(ts_corr({FIELD_B}, returns, {WINDOW2}))",
        "rank(ts_mean({FIELD_A}, {WINDOW}) / ts_std_dev({FIELD_B}, {WINDOW2}))",
        # M-01 v3: multi-factor interaction, signal blending
        "rank(ts_rank({FIELD_A}, {WINDOW}) * sign(ts_delta({FIELD_B}, {WINDOW2})))",
        "rank(zscore(ts_delta({FIELD_A}, {WINDOW})) - zscore(ts_std_dev({FIELD_B}, {WINDOW2})))",
        "rank(ts_corr(ts_delta({FIELD_A}, {WINDOW}), ts_delta({FIELD_B}, {WINDOW}), {WINDOW2}))",
        "group_rank(zscore({FIELD_A}) + zscore({FIELD_B}), {GROUP})",
        "rank(ts_mean({FIELD_A}, {WINDOW}) * ts_rank({FIELD_B}, {WINDOW2}))",
    ],
    "size": [
        # M-01 v3: size/anomaly category
        "rank(-{FIELD})",
        "rank(zscore(-{FIELD}))",
        "group_rank(-{FIELD}, {GROUP})",
        "rank(-ts_mean({FIELD}, {WINDOW}))",
        "rank(-{FIELD} / ts_std_dev({FIELD}, {WINDOW}))",
    ],
    # P1-7: Existing extra categories
    "decay": [
        "rank(ts_decay_linear({FIELD}, {WINDOW}))",
        "rank(ts_decay_linear(ts_delta({FIELD}, {WINDOW}), {WINDOW2}))",
        "ts_decay_linear(ts_rank({FIELD}, {WINDOW}), {WINDOW2})",
        # M-01 v3
        "rank(ts_decay_linear(zscore({FIELD}), {WINDOW}))",
        "rank(ts_decay_linear(ts_mean({FIELD}, {WINDOW}), {WINDOW2}))",
        "group_rank(ts_decay_linear({FIELD}, {WINDOW}), {GROUP})",
    ],
    "conditional": [
        "rank(if_else(greater({FIELD}, 0), {FIELD}, 0))",
        "rank(if_else(greater(ts_delta({FIELD}, {WINDOW}), 0), {FIELD}, -{FIELD}))",
        # M-01 v3
        "rank(if_else(less({FIELD}, ts_mean({FIELD}, {WINDOW})), -1, 1) * ts_std_dev({FIELD}, {WINDOW2}))",
        "rank(if_else(greater(ts_delta({FIELD}, {WINDOW}), ts_std_dev({FIELD}, {WINDOW2})), {FIELD}, -{FIELD}))",
    ],
    "multi_window": [
        "rank(ts_mean({FIELD}, {WINDOW}) - ts_mean({FIELD}, {WINDOW2}))",
        "rank(ts_std_dev({FIELD}, {WINDOW}) / ts_std_dev({FIELD}, {WINDOW2}))",
        "rank(ts_delta({FIELD}, {WINDOW}) - ts_delta({FIELD}, {WINDOW2}))",
        # M-01 v3
        "rank(ts_rank({FIELD}, {WINDOW}) - ts_rank({FIELD}, {WINDOW2}))",
        "rank(ts_delta({FIELD}, {WINDOW}) / ts_delta({FIELD}, {WINDOW2}))",
        "rank(ts_mean({FIELD}, {WINDOW}) / ts_mean({FIELD}, {WINDOW2}))",
        "rank(ts_std_dev({FIELD}, {WINDOW}) - ts_std_dev({FIELD}, {WINDOW2})) * sign(ts_delta({FIELD}, {WINDOW3}))",
    ],
}
