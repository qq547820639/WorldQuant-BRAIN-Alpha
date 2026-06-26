"""FASTEXPR tokenizer, parser, and canonicalization helpers (re-exported via expression_ast)."""
from __future__ import annotations

import hashlib
import re
from typing import Iterable

from brain_alpha_ops.research.expression_ast._types import (
    ExpressionParseError,
    ExprNode,
    _LEXICAL_TOKEN_RE,
    _TOKEN_RE,
)


def parse_expression(expression: str) -> ExprNode:
    tokens = _tokenize(expression)
    parser = _Parser(tokens)
    node = parser.parse_expression()
    if not parser.at_end():
        raise ExpressionParseError(f"unexpected token: {parser.peek()}")
    return node


def lexical_normalize(expression: str) -> str:
    return " ".join(token.lower() for token in _LEXICAL_TOKEN_RE.findall(str(expression or "")))


class _Parser:
    def __init__(self, tokens: list[str], max_depth: int = 32):
        self.tokens = tokens
        self.index = 0
        self._depth = 0
        self._max_depth = max(1, int(max_depth))

    def at_end(self) -> bool:
        return self.index >= len(self.tokens)

    def peek(self) -> str:
        return "" if self.at_end() else self.tokens[self.index]

    def peek_next(self) -> str:
        return "" if self.index + 1 >= len(self.tokens) else self.tokens[self.index + 1]

    def advance(self) -> str:
        token = self.peek()
        self.index += 1
        return token

    def consume(self, expected: str) -> None:
        if self.peek() != expected:
            raise ExpressionParseError(f"expected {expected!r}, got {self.peek()!r}")
        self.advance()

    def parse_expression(self) -> ExprNode:
        self._depth += 1
        if self._depth > self._max_depth:
            raise ExpressionParseError(
                f"expression nesting depth {self._depth} exceeds maximum {self._max_depth}"
            )
        try:
            return self.parse_conditional()
        finally:
            self._depth -= 1

    def parse_conditional(self) -> ExprNode:
        node = self.parse_comparison()
        if self.peek() == "?":
            self.advance()
            true_expr = self.parse_expression()
            self.consume(":")
            false_expr = self.parse_expression()
            node = ExprNode("conditional", "?", (node, true_expr, false_expr))
        return node

    def parse_comparison(self) -> ExprNode:
        node = self.parse_additive()
        while self.peek() in {">", "<", ">=", "<=", "==", "!="}:
            op = self.advance()
            right = self.parse_additive()
            node = ExprNode("binary", op, (node, right))
        return node

    def parse_additive(self) -> ExprNode:
        node = self.parse_term()
        while self.peek() in {"+", "-"}:
            op = self.advance()
            right = self.parse_term()
            node = ExprNode("binary", op, (node, right))
        return node

    def parse_term(self) -> ExprNode:
        node = self.parse_factor()
        while self.peek() in {"*", "/"}:
            op = self.advance()
            right = self.parse_factor()
            node = ExprNode("binary", op, (node, right))
        return node

    def parse_factor(self) -> ExprNode:
        token = self.peek()
        if token in {"+", "-"}:
            op = self.advance()
            child = self.parse_factor()
            if op == "+":
                return child
            return ExprNode("unary", op, (child,))
        return self.parse_primary()

    def parse_primary(self) -> ExprNode:
        token = self.advance()
        if not token:
            raise ExpressionParseError("unexpected end of expression")
        if token == "(":
            node = self.parse_expression()
            self.consume(")")
            return node
        if token in {")",
            ",",
            "+",
            "-",
            "*",
            "/",
            "?",
            ":",
            ">",
            "<",
            ">=",
            "<=",
            "==",
            "!=",
            "=",
        }:
            raise ExpressionParseError(f"unexpected token: {token}")
        if _is_number(token):
            return ExprNode("number", _normalize_number(token))
        ident = token.lower()
        if self.peek() != "(":
            return ExprNode("identifier", ident)
        self.consume("(")
        args: list[ExprNode] = []
        if self.peek() != ")":
            while True:
                args.append(self.parse_call_argument())
                if self.peek() != ",":
                    break
                self.advance()
        self.consume(")")
        return ExprNode("call", ident, tuple(args))

    def parse_call_argument(self) -> ExprNode:
        if _is_identifier_token(self.peek()) and self.peek_next() == "=":
            keyword = self.advance().lower()
            self.consume("=")
            return ExprNode("keyword", keyword, (self.parse_expression(),))
        return self.parse_expression()


def _tokenize(expression: str) -> list[str]:
    text = str(expression or "")
    tokens: list[str] = []
    pos = 0
    while pos < len(text):
        if text[pos:].strip() == "":
            break
        match = _TOKEN_RE.match(text, pos)
        if not match:
            raise ExpressionParseError(f"unexpected character at position {pos}")
        tokens.append(match.group(1))
        pos = match.end()
    if not tokens:
        raise ExpressionParseError("empty expression")
    return tokens


def canonicalize(node: ExprNode, max_depth: int = 64) -> str:
    if max_depth < 1:
        raise ExpressionParseError("AST canonicalize depth limit exceeded")
    if node.kind in {"identifier", "number"}:
        return node.value
    if node.kind == "call":
        return f"{node.value}({','.join(canonicalize(child, max_depth - 1) for child in node.children)})"
    if node.kind == "keyword":
        return f"{node.value}={canonicalize(node.children[0], max_depth - 1)}"
    if node.kind == "unary":
        child = node.children[0]
        child_text = canonicalize(child, max_depth - 1)
        if child.kind in {"binary", "conditional"}:
            child_text = f"({child_text})"
        return f"{node.value}{child_text}"
    if node.kind == "conditional":
        condition, true_expr, false_expr = node.children
        return f"{canonicalize(condition, max_depth - 1)}?{canonicalize(true_expr, max_depth - 1)}:{canonicalize(false_expr, max_depth - 1)}"
    if node.kind == "binary":
        op = node.value
        if op in {"+", "*"}:
            parts = sorted(canonicalize(child, max_depth - 1) for child in _flatten(node, op, max_depth - 1))
            return op.join(parts)
        left, right = node.children
        left_text = _canonical_child(left, op, is_right=False, max_depth=max_depth - 1)
        right_text = _canonical_child(right, op, is_right=True, max_depth=max_depth - 1)
        return f"{left_text}{op}{right_text}"
    raise ExpressionParseError(f"unknown node kind: {node.kind}")


def _canonical_child(child: ExprNode, parent_op: str, *, is_right: bool, max_depth: int = 64) -> str:
    text = canonicalize(child, max_depth)
    if child.kind == "conditional":
        return f"({text})"
    if child.kind != "binary":
        return text
    child_prec = _precedence(child.value)
    parent_prec = _precedence(parent_op)
    needs_parens = child_prec < parent_prec or (is_right and parent_op in {"-", "/"} and child_prec <= parent_prec)
    return f"({text})" if needs_parens else text


def _flatten(node: ExprNode, op: str, max_depth: int = 64) -> Iterable[ExprNode]:
    if max_depth < 1:
        raise ExpressionParseError("AST flatten depth limit exceeded")
    if node.kind == "binary" and node.value == op:
        for child in node.children:
            yield from _flatten(child, op, max_depth - 1)
    else:
        yield node


def _collect(node: ExprNode, operators: list[str], fields: list[str], windows: list[int], max_depth: int = 64) -> None:
    if max_depth < 1:
        raise ExpressionParseError("AST collect depth limit exceeded")
    """Recursively collect operators, fields, and window values from an expression AST.
    S-15: The `index > 0` heuristic treats the second+ argument to any call as a window.
    This works for common operators like ts_mean(x, 20) but may misidentify non-window
    positional args (e.g., rank(x, 5)). A future improvement should use a per-operator
    window-parameter position table instead of the position heuristic.
    """
    if node.kind == "keyword":
        _collect(node.children[0], operators, fields, windows, max_depth - 1)
        return
    if node.kind == "call":
        operators.append(node.value)
        for index, child in enumerate(node.children):
            value_node = child.children[0] if child.kind == "keyword" else child
            if index > 0 and value_node.kind == "number":
                try:
                    windows.append(int(float(value_node.value)))
                except ValueError:
                    pass
            _collect(child, operators, fields, windows, max_depth - 1)
        return
    if node.kind == "identifier":
        fields.append(node.value)
        return
    for child in node.children:
        _collect(child, operators, fields, windows, max_depth - 1)


def _collect_operators(node: ExprNode, operators: list[str], max_depth: int = 64) -> None:
    if max_depth < 1:
        raise ExpressionParseError("AST collect_operators depth limit exceeded")
    if node.kind == "call":
        operators.append(node.value)
    for child in node.children:
        _collect_operators(child, operators, max_depth - 1)


def _operators_from_text(text: str) -> list[str]:
    return re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", text)


def _fields_from_text(text: str) -> list[str]:
    operators = set(_operators_from_text(text))
    fields: list[str] = []
    for token in re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", text):
        lowered = token.lower()
        if lowered not in operators:
            fields.append(lowered)
    return list(dict.fromkeys(fields))


def _windows_from_text(text: str) -> list[int]:
    values: list[int] = []
    for item in re.findall(r",\s*(\d+(?:\.\d+)?)\s*\)", text):
        try:
            values.append(int(float(item)))
        except ValueError:
            pass
    return values


def _max_depth(node: ExprNode, max_depth: int = 64) -> int:
    if max_depth < 1:
        raise ExpressionParseError(f"AST depth limit {max_depth} exceeded")
    if not node.children:
        return 1
    return 1 + max(_max_depth(child, max_depth - 1) for child in node.children)


def _node_count(node: ExprNode, max_nodes: int = 512) -> int:
    if max_nodes < 1:
        raise ExpressionParseError(f"AST node count limit {max_nodes} exceeded")
    return 1 + sum(_node_count(child, max_nodes - 1) for child in node.children)


def _paren_depth(expression: str) -> tuple[int, bool]:
    """Return (max_depth, balanced) for parentheses in expression."""
    depth = 0
    max_depth = 0
    for char in str(expression or ""):
        if char == "(":
            depth += 1
            max_depth = max(max_depth, depth)
        elif char == ")":
            depth = max(0, depth - 1)
    return max_depth, depth == 0


def _paren_depth_simple(expression: str) -> int:
    """Lexical fallback: max parenthesis nesting depth without balanced check."""
    return _paren_depth(expression)[0]


def _is_number(token: str) -> bool:
    return bool(re.fullmatch(r"\d+(?:\.\d+)?", token))


def _is_identifier_token(token: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token or ""))


def _normalize_number(token: str) -> str:
    if "." not in token:
        return token
    value = token.rstrip("0").rstrip(".")
    return value or "0"


def _precedence(op: str) -> int:
    if op in {"*", "/"}:
        return 3
    if op in {"+", "-"}:
        return 2
    if op in {">", "<", ">=", "<=", "==", "!="}:
        return 1
    return 0

def _fingerprint(canonical: str) -> str:
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
