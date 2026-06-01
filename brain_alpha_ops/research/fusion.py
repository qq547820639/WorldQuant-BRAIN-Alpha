"""True factor fusion with orthogonal combinations and residual Alpha construction.

Fuse two Alpha expressions into a new composite Alpha with less redundant
information. This replaces the earlier pseudo-fusion that only wrapped
zscore/winsorize.

Fusion operators:
- orthogonal_blend: orthogonal combination, alpha1 - beta * alpha2
- residual_alpha: residual Alpha, the residual of signal regressed on base
- composite_fusion: simple rank-product composition

All fusion is expression-level only (it constructs new BRAIN expressions) and
does not depend on local numeric computation.

Usage::

    from brain_alpha_ops.research.fusion import orthogonal_blend, residual_alpha

    fused = orthogonal_blend("rank(ts_delta(f1, 20))", "rank(zscore(f2))")
    # → (rank(ts_delta(f1, 20))) - ts_regression((rank(ts_delta(f1, 20))), (rank(zscore(f2))), 252) * (rank(zscore(f2)))
"""

from __future__ import annotations

from brain_alpha_ops.models import Candidate


# ═══════════════════════════════════════════════════════════════════════
# Fusion operators
# ═══════════════════════════════════════════════════════════════════════

def orthogonal_blend(alpha1_expr: str, alpha2_expr: str) -> str:
    """Orthogonally combine two Alpha expressions.

    Form: alpha1 - beta * alpha2
    where beta is estimated dynamically via ts_regression inside the
    expression.

    BRAIN expression equivalent:
        ({alpha1}) - ts_regression(({alpha1}), ({alpha2}), 252) * ({alpha2})

    This keeps the fused Alpha orthogonal to alpha2 over a 252-day window,
    reducing redundant information.
    """
    return (
        f"({alpha1_expr}) - "
        f"ts_regression(({alpha1_expr}), ({alpha2_expr}), 252) * ({alpha2_expr})"
    )


def residual_alpha(base_expr: str, signal_expr: str) -> str:
    """Construct a residual Alpha from signal after linear regression on base.

    Form: signal - beta * base
    where beta is estimated dynamically via ts_regression inside the
    expression.

    BRAIN expression equivalent:
        ({signal}) - ts_regression(({signal}), ({base}), 252) * ({base})

    Use this when signal contains information already captured by base and you
    want the incremental remainder.
    """
    return (
        f"({signal_expr}) - "
        f"ts_regression(({signal_expr}), ({base_expr}), 252) * ({base_expr})"
    )


def composite_fusion(ex1: str, ex2: str, mode: str = "orthogonal") -> str:
    """Multi-mode fusion entry point.

    Args:
        ex1: first Alpha expression
        ex2: second Alpha expression
        mode: fusion mode
            - "orthogonal" → orthogonal_blend(ex1, ex2)
            - "residual"   → residual_alpha(ex1, ex2)  (ex2 regressed on ex1)
            - "reverse_residual" → residual_alpha(ex2, ex1) (ex1 regressed on ex2)
            - "composite"  → rank(ex1) * rank(ex2)

    Returns:
        Fused expression string
    """
    if mode == "orthogonal":
        return orthogonal_blend(ex1, ex2)
    elif mode == "residual":
        return residual_alpha(ex1, ex2)
    elif mode == "reverse_residual":
        return residual_alpha(ex2, ex1)
    elif mode == "composite":
        return f"rank({ex1}) * rank({ex2})"
    else:
        # Default to orthogonal.
        return orthogonal_blend(ex1, ex2)


def composite_ensemble(expressions: list[str], mode: str = "average") -> str:
    """Multi-Alpha ensemble.

    Args:
        expressions: list of Alpha expressions (at least 2)
        mode: ensemble mode
            - "average": equal-weight average of all expressions
            - "rank_average": equal-weight average after rank()
            - "max": maximum value across expressions
            - "min": minimum value across expressions

    Returns:
        Ensemble expression string
    """
    if len(expressions) < 2:
        return expressions[0] if expressions else ""

    if mode == "average":
        terms = " + ".join(f"({e})" for e in expressions)
        return f"({terms}) / {len(expressions)}"
    elif mode == "rank_average":
        terms = " + ".join(f"rank({e})" for e in expressions)
        return f"({terms}) / {len(expressions)}"
    elif mode == "max":
        result = f"ts_max(({expressions[0]}), ({expressions[1]}), 252)"
        for e in expressions[2:]:
            result = f"ts_max(({result}), ({e}), 252)"
        return result
    elif mode == "min":
        result = f"ts_min(({expressions[0]}), ({expressions[1]}), 252)"
        for e in expressions[2:]:
            result = f"ts_min(({result}), ({e}), 252)"
        return result
    else:
        return orthogonal_blend(expressions[0], expressions[1])


# ═══════════════════════════════════════════════════════════════════════
# Fusion candidate selection
# ═══════════════════════════════════════════════════════════════════════

def select_fusion_candidates(
    pool: dict[str, Candidate],
    top_n: int = 3,
    require_official: bool = True,
) -> list[tuple[Candidate, Candidate]]:
    """Select the best fusion pairs from the candidate pool.

    Strategy: sort by score, take the top-N candidates, then form pairwise
    fusion pairs. Prefer complementary Sharpe profiles (for example, one high
    Sharpe candidate paired with one low-correlation candidate).

    Args:
        pool: candidate pool (expression -> Candidate mapping)
        top_n: number of top candidates to pair
        require_official: whether to keep only candidates with official_metrics

    Returns:
        List of fusion pairs [(c1, c2), ...], sorted by c1 score descending
    """
    # Filter candidates.
    candidates = list(pool.values())
    if require_official:
        candidates = [c for c in candidates if c.official_metrics]
    if not candidates:
        return []

    # Sort by score.
    candidates.sort(
        key=lambda c: c.scorecard.get("total_score", 0) if c.scorecard else 0,
        reverse=True,
    )

    top = candidates[:min(top_n, len(candidates))]
    if len(top) < 2:
        return []

    # Generate unique, non-self pairs.
    pairs = []
    for i in range(len(top)):
        for j in range(i + 1, len(top)):
            pairs.append((top[i], top[j]))

    return pairs


def get_fusion_modes() -> list[str]:
    """Return all available fusion modes."""
    return ["orthogonal", "residual", "reverse_residual", "composite"]


def generate_fusion_expressions(
    c1: Candidate, c2: Candidate,
) -> dict[str, str]:
    """Generate all fusion-mode expressions for a candidate pair.

    Returns:
        Dictionary of {mode: expression}
    """
    ex1 = c1.expression or ""
    ex2 = c2.expression or ""
    if not ex1 or not ex2:
        return {}

    return {
        "orthogonal": orthogonal_blend(ex1, ex2),
        "residual": residual_alpha(ex1, ex2),
        "reverse_residual": residual_alpha(ex2, ex1),
        "composite": composite_fusion(ex1, ex2, mode="composite"),
    }
