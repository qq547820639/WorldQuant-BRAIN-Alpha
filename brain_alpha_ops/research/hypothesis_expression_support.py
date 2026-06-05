"""Expression normalization helpers for hypothesis-driven generation."""

from __future__ import annotations

import logging
import re
from typing import Any

from brain_alpha_ops.research.expression_ast import (
    ExprNode,
    ExpressionParseError,
    canonicalize,
    ordered_operators,
    parse_expression,
    profile_expression,
)
from brain_alpha_ops.research.field_quality import generation_field_ids
from brain_alpha_ops.research.fallback_generation import DEFAULT_WINDOWS
from brain_alpha_ops.research.hypothesis_library import FieldCategoryDef


GROUP_KEYS = {"market", "sector", "industry", "subindustry"}
KNOWN_BRAIN_OPERATORS = {
    "rank", "zscore", "winsorize", "group_zscore", "group_rank", "group_mean",
    "ts_rank", "ts_delta", "ts_sum", "ts_mean", "ts_std", "ts_zscore",
    "ts_count_nans", "ts_decay_linear", "ts_std_dev", "ts_regression",
    "ts_av_diff", "ts_kurtosis", "ts_skewness", "ts_scale", "ts_step",
    "ts_product", "ts_corr", "ts_covariance", "ts_min", "ts_max",
    "ts_argmax", "ts_argmin", "ts_arg_max", "ts_arg_min", "ts_percentage",
    "ts_delay", "ts_backfill", "ts_quantile", "quantile", "normalize",
    "kth_element", "log", "signed_power", "inverse", "scale", "power",
    "sector", "industry", "market", "subindustry",
    "group_backfill", "backfill", "fill_na", "subtract", "divide", "greater",
    "if_else", "hump",
}


def format_window(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = float(DEFAULT_WINDOWS[0])
    if numeric.is_integer():
        return str(int(numeric))
    return str(numeric).rstrip("0").rstrip(".")


def is_group_key_node(node: ExprNode) -> bool:
    return node.kind == "identifier" and node.value in GROUP_KEYS


def first_number_literal(nodes: tuple[ExprNode, ...]) -> str:
    for node in nodes:
        if node.kind == "number":
            return node.value
        if node.children:
            value = first_number_literal(node.children)
            if value:
                return value
    return ""


class HypothesisExpressionSupport:
    """Resolves semantic hypothesis templates into valid FASTEXPR expressions."""

    def __init__(
        self,
        *,
        fields: set[str],
        operators: set[str],
        loader: Any = None,
        dataset_id: str = "",
        logger: logging.Logger | None = None,
    ) -> None:
        self._fields = fields
        self._operators = operators
        self._loader = loader
        self._dataset_id = dataset_id
        self._logger = logger or logging.getLogger(__name__)

    def normalize_wq_expression_shape(self, expr: str, window: int | None = None) -> str:
        """Convert resolved semantic shorthands into operator-based FASTEXPR."""
        expr = str(expr or "").strip()
        if not expr:
            return expr

        field_call = re.fullmatch(r"([A-Za-z_]\w*)\s*\(\s*(\d+(?:\.\d+)?)\s*\)", expr)
        if field_call:
            field_name = field_call.group(1)
            if field_name.lower() in {field.lower() for field in self._fields}:
                lookback = format_window(field_call.group(2) or window or DEFAULT_WINDOWS[0])
                if self.operator_available("rank") and self.operator_available("ts_delta"):
                    return f"rank(ts_delta({field_name}, {lookback}))"
                if self.operator_available("ts_delta"):
                    return f"ts_delta({field_name}, {lookback})"
                if self.operator_available("rank"):
                    return f"rank({field_name})"

        expr = self.normalize_field_function_calls(expr, window)
        profile = profile_expression(expr)
        if profile.parsed and profile.fields and not profile.operators and self.operator_available("rank"):
            return f"rank({expr})"
        return expr

    def operator_available(self, name: str) -> bool:
        return not self._operators or name.lower() in self._operators

    def normalize_field_function_calls(self, expr: str, window: int | None = None) -> str:
        """Rewrite accidental field-as-function calls into supported operators."""
        if not self._fields:
            return expr
        try:
            root = parse_expression(expr)
        except ExpressionParseError:
            return expr
        rewritten = self.rewrite_field_function_node(root, window)
        if rewritten == root:
            return expr
        return canonicalize(rewritten)

    def rewrite_field_function_node(self, node: ExprNode, window: int | None = None) -> ExprNode:
        if node.kind == "call":
            rewritten_children = tuple(
                self.rewrite_field_function_node(child, window) for child in node.children
            )
            if self.is_field_function_name(node.value):
                return self.replacement_for_field_function(node.value, rewritten_children, window)
            if rewritten_children != node.children:
                return ExprNode(node.kind, node.value, rewritten_children)
            return node
        if not node.children:
            return node
        rewritten_children = tuple(
            self.rewrite_field_function_node(child, window) for child in node.children
        )
        if rewritten_children == node.children:
            return node
        return ExprNode(node.kind, node.value, rewritten_children)

    def is_field_function_name(self, name: str) -> bool:
        value = str(name or "").lower()
        if value not in {field.lower() for field in self._fields}:
            return False
        operator_pool = self._operators or KNOWN_BRAIN_OPERATORS
        return value not in operator_pool

    def replacement_for_field_function(
        self,
        field_name: str,
        args: tuple[ExprNode, ...],
        window: int | None = None,
    ) -> ExprNode:
        field = ExprNode("identifier", field_name.lower())
        group_arg = next((arg for arg in args if is_group_key_node(arg)), None)
        if group_arg is not None and self.operator_available("group_rank"):
            return ExprNode("call", "group_rank", (field, group_arg))

        lookback = first_number_literal(args) or format_window(window or DEFAULT_WINDOWS[0])
        expression: ExprNode = field
        if self.operator_available("ts_delta"):
            expression = ExprNode("call", "ts_delta", (field, ExprNode("number", lookback)))
        if self.operator_available("rank"):
            expression = ExprNode("call", "rank", (expression,))
        return expression

    def sanitize_expression(
        self,
        expr: str,
        fields: list[str],
        already_used: set[str] | None = None,
    ) -> str:
        """Replace remaining semantic tokens with actual dataset field names."""
        if not fields:
            return expr

        dataset_fields = sorted(self._fields) if self._fields else []
        dataset_fields_lower = {f.lower() for f in dataset_fields}
        field_set_lower = {f.lower() for f in fields}
        known_ops = self._operators if self._operators else set()
        brain_ops = {
            'rank', 'zscore', 'winsorize', 'group_zscore', 'group_rank', 'group_mean',
            'ts_rank', 'ts_delta', 'ts_sum', 'ts_mean', 'ts_std', 'ts_zscore',
            'ts_count_nans', 'ts_decay_linear', 'ts_std_dev', 'ts_regression',
            'ts_av_diff', 'ts_kurtosis', 'ts_skewness', 'ts_scale', 'ts_step',
            'ts_product', 'ts_corr', 'ts_covariance', 'ts_min', 'ts_max',
            'ts_argmax', 'ts_argmin', 'ts_arg_max', 'ts_arg_min', 'ts_percentage',
            'quantile', 'normalize', 'kth_element', 'log', 'signed_power',
            'inverse', 'scale', 'power', 'sector', 'industry', 'market',
            'subindustry', 'group_backfill', 'backfill', 'fill_na',
        }

        tokens = re.findall(r'\b([a-zA-Z_]\w+)\b', expr)
        replacements: dict[str, str] = {}
        used_fields: set[str] = set(already_used or set())
        used_fields.update(t.lower() for t in tokens if t.lower() in dataset_fields_lower)

        for token in tokens:
            t_lower = token.lower()
            if (
                t_lower in dataset_fields_lower
                or t_lower in known_ops
                or t_lower in field_set_lower
                or t_lower in brain_ops
                or t_lower in {'-1', 'nan', 'inf', 'std'}
            ):
                continue

            best_field = self.find_best_field_match(token, dataset_fields, used_fields)
            if best_field:
                replacements[token] = best_field
                used_fields.add(best_field)
            else:
                for df in dataset_fields:
                    if df not in used_fields:
                        replacements[token] = df
                        used_fields.add(df)
                        break

        if not replacements:
            return expr

        for token, field in sorted(replacements.items(), key=lambda x: -len(x[0])):
            expr = re.sub(rf'\b{re.escape(token)}\b', field, expr)

        return expr

    def find_best_field_match(
        self,
        token: str,
        dataset_fields: list[str],
        used_fields: set[str],
    ) -> str | None:
        """Find best dataset field matching an unknown token."""
        t_lower = token.lower()
        t_tokens = set(t_lower.split('_'))
        scored: list[tuple[int, str]] = []

        for df in dataset_fields:
            if df in used_fields:
                continue
            df_lower = df.lower()
            score = 0
            if t_lower == df_lower:
                score += 100
            if t_lower in df_lower:
                score += 25
            df_tokens = set(df_lower.split('_'))
            common = t_tokens & df_tokens
            score += len(common) * 8
            if score > 0:
                scored.append((score, df))

        if not scored:
            return None

        scored.sort(key=lambda x: -x[0])
        return scored[0][1]

    def validate_dataset_fields(self, expr: str, fallback_fields: list[str]) -> str:
        """Replace field-like tokens not present in the active dataset."""
        if not self._fields:
            return expr

        ds_fields_lower = {f.lower() for f in self._fields}
        fallback_fields = [field for field in fallback_fields if field.lower() in ds_fields_lower]
        if not fallback_fields:
            fallback_fields = sorted(self._fields)
        if not fallback_fields:
            return expr
        tokens = re.findall(r'\b([a-zA-Z_]\w+)\b', expr)
        operators = {
            'rank', 'zscore', 'winsorize', 'group_zscore', 'group_rank', 'group_mean',
            'ts_rank', 'ts_delta', 'ts_sum', 'ts_mean', 'ts_std', 'ts_zscore',
            'ts_count_nans', 'ts_decay_linear', 'ts_std_dev', 'quantile', 'normalize',
            'kth_element', 'log', 'sector', 'industry', 'market', 'subindustry',
            'group_backfill', 'backfill', 'fill_na', 'subtract', 'divide', 'greater',
            'if_else', 'signed_power', 'inverse', 'scale', 'power', 'ts_step',
            'ts_product', 'ts_corr', 'ts_covariance', 'ts_min', 'ts_max',
            'ts_argmax', 'ts_argmin', 'ts_arg_max', 'ts_arg_min', 'ts_percentage',
            'ts_delay', 'last_diff_value', 'days_from_last_change', 'ts_av_diff',
            'ts_kurtosis', 'ts_skewness', 'ts_scale', 'ts_regression',
            'ts_backfill', 'hump', 'ts_quantile',
        }
        field_like = []
        for token in tokens:
            t_lower = token.lower()
            if (
                t_lower not in operators
                and t_lower not in ds_fields_lower
                and not token.isdigit()
                and token not in {'-1', 'nan', 'inf', 'std'}
            ):
                field_like.append(token)

        if not field_like:
            return expr

        field_iter = iter(fallback_fields)
        used: set[str] = set()
        for token in field_like:
            try:
                replacement = next(field_iter)
            except StopIteration:
                replacement = fallback_fields[0]
            if replacement in used:
                continue
            used.add(replacement)
            expr = re.sub(rf'\b{re.escape(token)}\b', replacement, expr)

        return expr

    def resolve_named_field(
        self,
        name: str,
        field_categories: list[FieldCategoryDef],
        selected_fields: list[str],
        exclude: set[str] | None = None,
    ) -> str:
        """Resolve a named field placeholder to a concrete BRAIN field."""
        name_lower = name.lower()
        dataset_fields = sorted(self._fields) if self._fields else []
        ds_fields_lower = {f.lower() for f in dataset_fields}
        excluded = exclude or set()

        if name_lower in ds_fields_lower:
            candidate = next(f for f in dataset_fields if f.lower() == name_lower)
            if candidate not in excluded:
                return candidate

        name_tokens = set(name_lower.split('_'))
        scored: list[tuple[int, str]] = []
        for df in dataset_fields:
            df_lower = df.lower()
            score = 0
            if name_lower == df_lower:
                score += 100
            if name_lower in df_lower:
                score += 30
            df_tokens = set(df_lower.split('_'))
            common = name_tokens & df_tokens
            score += len(common) * 10
            if score > 0:
                scored.append((score, df))

        if scored:
            scored.sort(key=lambda x: -x[0])
            for _, field in scored:
                if field not in excluded:
                    return field

        if field_categories:
            for category in field_categories:
                cat_lower = category.category.lower()
                if name_lower in cat_lower or cat_lower in name_lower:
                    cat_tokens = set(cat_lower.split('_'))
                    cat_scored: list[tuple[int, str]] = []
                    for df in dataset_fields:
                        df_lower = df.lower()
                        df_tokens = set(df_lower.split('_'))
                        common = cat_tokens & df_tokens
                        score = len(common) * 5
                        if name_lower in df_lower:
                            score += 20
                        if score > 0:
                            cat_scored.append((score, df))
                    if cat_scored:
                        cat_scored.sort(key=lambda x: -x[0])
                        for _, field in cat_scored:
                            if field not in excluded:
                                return field

        for selected in selected_fields:
            selected_lower = selected.lower()
            if name_lower in selected_lower and selected not in excluded:
                return selected

        if dataset_fields:
            for field in dataset_fields:
                if field not in excluded:
                    return field
            return dataset_fields[0]

        for selected in selected_fields:
            if selected not in excluded:
                return selected
        return selected_fields[0] if selected_fields else "returns"

    def extract_fields(self, expression: str) -> list[str]:
        """Extract active-dataset field names used in an expression."""
        profile = profile_expression(expression)
        fields = self._fields
        if not fields and self._loader:
            try:
                fields = set(generation_field_ids(self._loader.get_fields(self._dataset_id or None)))
                if not fields:
                    fields = {field.id.lower() for field in self._loader.get_fields(self._dataset_id or None)}
            except Exception:
                self._logger.warning(
                    "generator field extraction metadata unavailable for dataset_id=%s",
                    self._dataset_id or "",
                    exc_info=True,
                )
                fields = set()
        if not fields:
            return list(profile.fields)
        tokens = {token.lower() for token in profile.fields}
        return sorted(fields & tokens)

    def extract_operators(self, expression: str) -> list[str]:
        """Extract operator names from an expression."""
        return ordered_operators(expression)
