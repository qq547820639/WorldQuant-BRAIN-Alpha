"""Legacy expression mutation helpers for candidate generation."""

from __future__ import annotations

import random
import re

from brain_alpha_ops.research.generator_metadata import (
    OFFICIAL_OPERATOR_SUBSTITUTE_FAMILIES,
    expression_windows_within_constraints,
    _expression_operators_are_official,
    _get_default_windows,
    _load_official_operator_names,
)


def mutate_expression(
    expression: str,
    index: int,
    mode: str = "default",
    experience_windows: list[int] | None = None,
    field_pool: list[str] | None = None,
) -> str:
    """Produce a backward-compatible variant of *expression*."""
    seed = index
    official_operators = _load_official_operator_names()

    def _official_or_original(mutated: str) -> str:
        return (
            mutated
            if _expression_operators_are_official(mutated, official_operators)
            and expression_windows_within_constraints(mutated)
            else expression
        )

    default_windows = _get_default_windows()
    if experience_windows:
        exp = [window for window in experience_windows if window not in default_windows]
        windows = exp + default_windows
    else:
        windows = default_windows
    numbers = re.findall(r"\b\d+\b", expression)

    if mode == "field_swap":
        mutated = expression
        for pos, number in enumerate(numbers):
            replacement = windows[(index + pos * 7) % len(windows)]
            mutated = re.sub(rf"\b{re.escape(number)}\b", str(replacement), mutated, count=1)
        return _official_or_original(mutated)

    if mode == "structure_change":
        mutated = expression
        wrappers = []
        if "winsorize" in official_operators:
            wrappers.append(lambda expr: f"winsorize({expr}, std=4)")
        if "zscore" in official_operators:
            wrappers.append(lambda expr: f"zscore({expr})")
        if wrappers:
            mutated = wrappers[index % len(wrappers)](mutated)
        return _official_or_original(mutated)

    if mode == "longer_window":
        long_windows = [60, 90, 120, 180, 252]
        mutated = expression
        for pos, number in enumerate(numbers):
            replacement = long_windows[(index + pos) % len(long_windows)]
            mutated = re.sub(rf"\b{re.escape(number)}\b", str(replacement), mutated, count=1)
        return _official_or_original(mutated)

    if mode == "window_perturb":
        def _perturb(match: re.Match) -> str:
            val = int(match.group(0))
            if val < 2 or val > 1000:
                return match.group(0)
            delta = random.uniform(-0.2, 0.2) * val
            new_val = int(val + delta)
            return str(max(3, min(252, new_val)))

        return _official_or_original(re.sub(r"\b\d+\b", _perturb, expression))

    if mode == "field_swap_semantic":
        if not field_pool or len(field_pool) < 2:
            return expression
        field_tokens = re.findall(r"\b([a-zA-Z_]\w*)\b", expression)
        candidate_fields = [token for token in field_tokens if token in field_pool]
        if not candidate_fields:
            candidate_fields = [
                token for token in field_tokens
                if len(token) > 1 and "_" in token and not token.isdigit()
            ]
        if not candidate_fields:
            return expression
        target = random.choice(candidate_fields)
        alt_pool = [field for field in field_pool if field != target]
        if not alt_pool:
            return expression
        replacement = random.choice(alt_pool)
        return _official_or_original(
            re.sub(r"\b" + re.escape(target) + r"\b", replacement, expression, count=1)
        )

    if mode == "operator_substitute":
        alternatives = {}
        for family_ops in OFFICIAL_OPERATOR_SUBSTITUTE_FAMILIES.values():
            official_family_ops = [op for op in family_ops if op in official_operators]
            for op in official_family_ops:
                alternatives[op] = [candidate for candidate in official_family_ops if candidate != op]
        for op in re.findall(r"\b([a-zA-Z_]\w*)\s*\(", expression):
            if op in alternatives and alternatives[op]:
                replacement = random.choice(alternatives[op])
                return _official_or_original(
                    re.sub(r"\b" + re.escape(op) + r"\b", replacement, expression, count=1)
                )
        return expression

    mutated = expression
    for pos, number in enumerate(numbers):
        replacement = windows[(index + pos * 3) % len(windows)]
        mutated = re.sub(rf"\b{re.escape(number)}\b", str(replacement), mutated, count=1)
    variant = seed % 3
    if variant == 1 and "winsorize" in official_operators:
        return _official_or_original(f"winsorize({mutated}, std=4)")
    if variant == 2 and "zscore" in official_operators:
        return _official_or_original(f"zscore({mutated})")
    return _official_or_original(mutated)
