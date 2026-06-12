"""Expression validation helpers for the official BRAIN API adapter."""

from __future__ import annotations

import logging
import re

from brain_alpha_ops.research.expression_engine import ExpressionEngine
from brain_alpha_ops.research.expression_official_context import GROUP_CONTEXT_FIELDS


logger = logging.getLogger("brain_alpha_ops.brain_api.official")


class OfficialExpressionValidator:
    def validate_expression(
        self,
        expression: str,
        settings: dict,
        known_operators: set | None = None,
        known_fields: set | None = None,
    ) -> dict:
        """Validate expression before simulation submission.

        Local checks catch common syntax and context mistakes before BRAIN
        performs the authoritative compile during simulation submission.
        """
        errors = []
        warnings = []

        if not isinstance(expression, str):
            return {"status": "FAIL", "errors": ["Expression must be a string"]}
        if "\x00" in expression:
            errors.append("Expression contains null bytes")

        if not expression.strip():
            return {"status": "FAIL", "errors": ["Empty expression"]}

        if expression.count("(") != expression.count(")"):
            return {"status": "FAIL", "errors": ["Unbalanced parentheses"]}

        if len(expression) > 250:
            warnings.append(f"Expression length {len(expression)} > 250 (may cause compile issues)")

        if re.search(r",\s*\)", expression):
            errors.append("Dangling comma before closing parenthesis")
        if re.search(r"\(\s*,", expression):
            errors.append("Leading comma after opening parenthesis")
        if re.search(r",\s*,", expression):
            errors.append("Consecutive commas in function arguments")

        if re.search(r"\b\w+\s*\(\s*\)", expression):
            warnings.append("Empty function call detected — ensure all functions have arguments")

        if expression.count('"') % 2 != 0 or expression.count("'") % 2 != 0:
            warnings.append("Unmatched quotes in expression")

        depth = 0
        max_depth = 0
        for char in expression:
            if char == "(":
                depth += 1
                max_depth = max(max_depth, depth)
            elif char == ")":
                depth -= 1
                if depth < 0:
                    errors.append("Unmatched closing parenthesis — depth went negative")
                    break
        if max_depth > 6:
            warnings.append(f"Nesting depth {max_depth} > 6 (may reduce interpretability)")

        known_ops: set = known_operators or set()
        known_flds: set = known_fields or set()
        if not known_ops or not known_flds:
            try:
                from brain_alpha_ops.data import OfficialDataLoader

                loader = OfficialDataLoader.instance()
                if not known_ops:
                    known_ops = {op.name.lower() for op in loader.get_operators() if op.name}
                if not known_flds:
                    known_flds = {field.id.lower() for field in loader.get_fields() if field.id}
            except Exception:
                logger.warning(
                    "OfficialDataLoader unavailable — skipping local field/operator validation",
                    exc_info=True,
                )

        if known_ops:
            used_ops = re.findall(r"\b([a-zA-Z_]\w*)\s*\(", expression)
            if len(set(used_ops)) > 8:
                warnings.append(f"High operator count: {len(set(used_ops))} unique operators (BRAIN recommends <= 8)")

        if known_ops or known_flds:
            report = ExpressionEngine(
                allowed_fields={field for field in known_flds if field not in GROUP_CONTEXT_FIELDS},
                allowed_operators=known_ops,
            ).validate(expression)
            for issue in report.issues:
                if issue.severity != "ERROR":
                    continue
                values = issue.detail.get("values") if isinstance(issue.detail, dict) else None
                if issue.code == "unknown_fields" and values:
                    errors.append("Unknown fields: " + ", ".join(str(value) for value in values))
                elif issue.code == "unknown_operators" and values:
                    errors.append("Unknown operators: " + ", ".join(str(value) for value in values))
                elif issue.code == "parse_error":
                    errors.append("Parse error: " + issue.message)
            if known_flds and not [field for field in report.profile.fields if field not in GROUP_CONTEXT_FIELDS]:
                errors.append("No known BRAIN data fields found in expression")

        if errors:
            return {"status": "FAIL", "errors": errors, "warnings": warnings}
        return {
            "status": "PASS",
            "errors": [],
            "warnings": warnings,
            "note": "simulation submission will confirm official BRAIN compile",
        }


class OfficialExpressionValidationMixin:
    def validate_expression(
        self,
        expression: str,
        settings: dict,
        known_operators: set | None = None,
        known_fields: set | None = None,
    ) -> dict:
        """Compatibility wrapper for callers that still compose the old mixin."""
        validator = getattr(self, "_expression_validator", None) or OfficialExpressionValidator()
        return validator.validate_expression(
            expression,
            settings,
            known_operators=known_operators,
            known_fields=known_fields,
        )
