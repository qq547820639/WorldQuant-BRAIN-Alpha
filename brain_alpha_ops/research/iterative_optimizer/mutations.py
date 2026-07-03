"""Mutation-strategy mixin for ``IterativeOptimizer``.

Consolidated from the original ``iterative_optimizer.py`` monolith. The five
mutation operators (``field_swap``, ``field_swap_semantic``,
``window_perturb``, ``structure_refine``, ``operator_substitute``) and the
``_safe_replace_token`` helper live here, alongside the
``_STRUCTURE_WRAPS`` constant they depend on. They are mixed into
``IterativeOptimizer`` in ``optimizer``.
"""

from __future__ import annotations

import re

from brain_alpha_ops.research.fallback_generation import normalize_operator_aliases


# Alternative operators per family, used by operator_substitute.
_STRUCTURE_WRAPS: list[str] = ["winsorize", "zscore", "scale"]


class _MutationsMixin:
    """Mutation operators mixed into ``IterativeOptimizer``."""

    def field_swap(
        self, expression: str, fields: list[str], dataset_id: str = ""
    ) -> str:
        """Replace a field in the expression with another field from the same class.

        Prefer fields from the same dataset. If the mapper is unavailable, fall
        back to rotating within the provided fields list.
        """
        if not fields or len(fields) < 2:
            return expression

        # Try to pull replacement fields from the same dataset via the mapper.
        if self._mapper and dataset_id:
            dataset_fields = self._mapper.fields_for(dataset_id)
            if dataset_fields and len(dataset_fields) > 1:
                alt_pool = [f for f in dataset_fields if f not in fields]
                if not alt_pool:
                    alt_pool = dataset_fields
            else:
                alt_pool = fields
        else:
            alt_pool = fields

        # Replace one of the fields appearing in the expression.
        target = self._rng.choice(fields) if fields else ""
        if not target or target not in expression:
            return expression

        alternatives = [f for f in alt_pool if f != target]
        if not alternatives:
            return expression
        replacement = self._rng.choice(alternatives)
        return self._safe_replace_token(expression, target, replacement)

    def field_swap_semantic(self, expression: str, dataset_id: str = "") -> str:
        """Replace a field in the expression with another field from the same class.

        Uses FieldDatasetMapper to find a closely related field from the same dataset.
        """
        expression = normalize_operator_aliases(expression)
        field_tokens = re.findall(r"\b([a-zA-Z_]\w*)\b", expression)
        # Filter tokens that could be field names (exclude operators and numbers).
        operator_names = set(self._family_alternatives.keys())
        candidate_fields = [
            t for t in field_tokens
            if t not in operator_names and not t.isdigit()
            and len(t) > 1 and "_" in t
        ]

        if not candidate_fields:
            return expression

        target = self._rng.choice(candidate_fields)
        if self._mapper and dataset_id:
            replacements = self._mapper.fields_for(dataset_id)
            if replacements:
                alternatives = [f for f in replacements if f != target]
                if alternatives:
                    replacement = self._rng.choice(alternatives)
                    return self._safe_replace_token(expression, target, replacement)

        return expression

    def window_perturb(self, expression: str, factor: float = 0.2) -> str:
        """Perturb windows by +/-factor.

        Apply a random +/-random()*factor*value perturbation to all numbers in
        the expression, clamping the result to [3, 252].
        """
        def _perturb(m: re.Match) -> str:
            val = int(m.group(0))
            if val < 2 or val > 1000:  # Non-window numbers such as coefficients.
                return m.group(0)
            delta = self._rng.uniform(-factor, factor) * val
            new_val = int(val + delta)
            new_val = max(3, min(252, new_val))
            return str(new_val)

        return re.sub(r"\b\d+\b", _perturb, expression)

    def structure_refine(self, expression: str) -> str:
        """Add or remove a normalization layer.

        50% of the time this adds a normalization wrapper
        (winsorize/zscore/scale); otherwise it removes the outermost wrapper if
        one exists.
        """
        if self._rng.random() < 0.5:
            # Add a wrapper.
            wrap = self._rng.choice(_STRUCTURE_WRAPS)
            # Check whether the expression is already wrapped.
            stripped = expression.strip()
            for existing_wrap in _STRUCTURE_WRAPS:
                if stripped.startswith(f"{existing_wrap}(") and stripped.endswith(")"):
                    return expression  # Already wrapped; do not wrap again.
            # winsorize requires a std parameter.
            if wrap == "winsorize":
                return f"{wrap}({expression}, std=4)"
            return f"{wrap}({expression})"
        else:
            # Remove the outermost wrapper.
            stripped = expression.strip()
            for existing_wrap in _STRUCTURE_WRAPS:
                prefix = f"{existing_wrap}("
                if stripped.startswith(prefix) and stripped.endswith(")"):
                    inner = stripped[len(prefix):-1]
                    # Handle parameterized forms such as winsorize(expr, std=4).
                    if "," in inner:
                        # Keep the portion before the first comma up to the matching bracket.
                        inner = inner[:inner.rfind(",")].strip()
                    return inner if inner else expression
            return expression

    def operator_substitute(self, expression: str) -> str:
        """Replace an operator with another operator from the same family.

        Identify operators in the expression and replace one with a family peer.
        """
        # Extract all operator names.
        expression = normalize_operator_aliases(expression)
        op_pattern = re.findall(r"\b([a-zA-Z_]\w*)\s*\(", expression)
        known_ops = set(self._family_alternatives.keys())

        substituted = False
        result = expression

        for op in op_pattern:
            if op in known_ops and op in self._family_alternatives:
                alternatives = self._family_alternatives[op]
                if alternatives:
                    replacement = self._rng.choice(alternatives)
                    # Safe replacement as a whole token, not a substring.
                    result = self._safe_replace_token(result, op, replacement)
                    substituted = True
                    break  # Replace only one operator at a time.

        return result if substituted else expression

    # Helpers

    @staticmethod
    def _safe_replace_token(text: str, old: str, new: str) -> str:
        """Safely replace a token, ensuring old is a whole word."""
        # Use word-boundary matching.
        pattern = r"\b" + re.escape(old) + r"\b"
        if not re.search(pattern, text):
            return text
        return re.sub(pattern, new, text, count=1)
