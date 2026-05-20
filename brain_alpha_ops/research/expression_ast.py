"""FASTEXPR parsing helpers for canonical keys and similarity checks."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import hashlib
import re
from typing import Iterable


_TOKEN_RE = re.compile(r"\s*([A-Za-z_][A-Za-z0-9_]*|\d+(?:\.\d+)?|[(),+\-*/])")
_LEXICAL_TOKEN_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*|\d+(?:\.\d+)?|[-+*/(),]")


class ExpressionParseError(ValueError):
    """Raised when a FASTEXPR string cannot be parsed by the local parser."""


@dataclass(frozen=True)
class ExprNode:
    kind: str
    value: str = ""
    children: tuple["ExprNode", ...] = ()


@dataclass(frozen=True)
class ExpressionProfile:
    expression: str
    parsed: bool
    canonical: str
    fingerprint: str
    operators: tuple[str, ...]
    fields: tuple[str, ...]
    windows: tuple[int, ...]
    max_depth: int
    node_count: int
    parse_error: str = ""


def parse_expression(expression: str) -> ExprNode:
    tokens = _tokenize(expression)
    parser = _Parser(tokens)
    node = parser.parse_expression()
    if not parser.at_end():
        raise ExpressionParseError(f"unexpected token: {parser.peek()}")
    return node


def profile_expression(expression: str) -> ExpressionProfile:
    text = str(expression or "")
    try:
        root = parse_expression(text)
    except ExpressionParseError as exc:
        canonical = lexical_normalize(text)
        return ExpressionProfile(
            expression=text,
            parsed=False,
            canonical=canonical,
            fingerprint=_fingerprint(canonical),
            operators=tuple(_operators_from_text(canonical)),
            fields=tuple(_fields_from_text(canonical)),
            windows=tuple(_windows_from_text(canonical)),
            max_depth=_paren_depth(text),
            node_count=max(0, len(canonical.split())),
            parse_error=str(exc),
        )

    canonical = canonicalize(root)
    operators: list[str] = []
    fields: list[str] = []
    windows: list[int] = []
    _collect(root, operators, fields, windows)
    return ExpressionProfile(
        expression=text,
        parsed=True,
        canonical=canonical,
        fingerprint=_fingerprint(canonical),
        operators=tuple(dict.fromkeys(operators)),
        fields=tuple(dict.fromkeys(fields)),
        windows=tuple(windows),
        max_depth=_max_depth(root),
        node_count=_node_count(root),
    )


def expression_profile_summary(expression: str) -> dict:
    profile = profile_expression(expression)
    summary = {
        "expression_canonical": profile.canonical,
        "expression_fingerprint": profile.fingerprint,
        "expression_profile": {
            "schema_version": "expression-profile.v1",
            "parsed": profile.parsed,
            "operators": list(profile.operators),
            "fields": list(profile.fields),
            "windows": list(profile.windows),
            "max_depth": profile.max_depth,
            "node_count": profile.node_count,
        },
    }
    if profile.parse_error:
        summary["expression_profile"]["parse_error"] = profile.parse_error
    return summary


def canonical_expression(expression: str) -> str:
    return profile_expression(expression).canonical


def expression_key(expression: str) -> str:
    return canonical_expression(expression)


def expression_fingerprint(expression: str) -> str:
    return profile_expression(expression).fingerprint


def lexical_normalize(expression: str) -> str:
    return " ".join(token.lower() for token in _LEXICAL_TOKEN_RE.findall(str(expression or "")))


def expression_similarity(left: str, right: str) -> float:
    left_profile = profile_expression(left)
    right_profile = profile_expression(right)
    if not left_profile.canonical or not right_profile.canonical:
        return 0.0
    if left_profile.fingerprint == right_profile.fingerprint:
        return 1.0

    seq = SequenceMatcher(None, left_profile.canonical, right_profile.canonical).ratio()
    token_jaccard = _jaccard(_semantic_tokens(left_profile), _semantic_tokens(right_profile))
    if left_profile.parsed and right_profile.parsed and left_profile.canonical != right_profile.canonical:
        token_jaccard = min(token_jaccard, 0.999)
    operator_jaccard = _jaccard(
        {f"op:{item}" for item in left_profile.operators},
        {f"op:{item}" for item in right_profile.operators},
    )
    field_jaccard = _jaccard(
        {f"field:{item}" for item in left_profile.fields},
        {f"field:{item}" for item in right_profile.fields},
    )
    score = max(seq, token_jaccard, 0.6 * operator_jaccard + 0.4 * field_jaccard)
    if left_profile.parsed and right_profile.parsed and left_profile.canonical != right_profile.canonical:
        score = min(score, 0.999)
    return round(score, 4)


def canonical_tokens(expression: str) -> set[str]:
    return _semantic_tokens(profile_expression(expression))


def ordered_operators(expression: str) -> list[str]:
    try:
        root = parse_expression(expression)
    except ExpressionParseError:
        return _operators_from_text(lexical_normalize(expression))
    operators: list[str] = []
    _collect_operators(root, operators)
    return operators


class _Parser:
    def __init__(self, tokens: list[str]):
        self.tokens = tokens
        self.index = 0

    def at_end(self) -> bool:
        return self.index >= len(self.tokens)

    def peek(self) -> str:
        return "" if self.at_end() else self.tokens[self.index]

    def advance(self) -> str:
        token = self.peek()
        self.index += 1
        return token

    def consume(self, expected: str) -> None:
        if self.peek() != expected:
            raise ExpressionParseError(f"expected {expected!r}, got {self.peek()!r}")
        self.advance()

    def parse_expression(self) -> ExprNode:
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
                args.append(self.parse_expression())
                if self.peek() != ",":
                    break
                self.advance()
        self.consume(")")
        return ExprNode("call", ident, tuple(args))


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


def canonicalize(node: ExprNode) -> str:
    if node.kind in {"identifier", "number"}:
        return node.value
    if node.kind == "call":
        return f"{node.value}({','.join(canonicalize(child) for child in node.children)})"
    if node.kind == "unary":
        child = node.children[0]
        child_text = canonicalize(child)
        if child.kind == "binary":
            child_text = f"({child_text})"
        return f"{node.value}{child_text}"
    if node.kind == "binary":
        op = node.value
        if op in {"+", "*"}:
            parts = sorted(canonicalize(child) for child in _flatten(node, op))
            return op.join(parts)
        left, right = node.children
        left_text = _canonical_child(left, op, is_right=False)
        right_text = _canonical_child(right, op, is_right=True)
        return f"{left_text}{op}{right_text}"
    raise ExpressionParseError(f"unknown node kind: {node.kind}")


def _canonical_child(child: ExprNode, parent_op: str, *, is_right: bool) -> str:
    text = canonicalize(child)
    if child.kind != "binary":
        return text
    child_prec = _precedence(child.value)
    parent_prec = _precedence(parent_op)
    needs_parens = child_prec < parent_prec or (is_right and parent_op in {"-", "/"} and child_prec <= parent_prec)
    return f"({text})" if needs_parens else text


def _flatten(node: ExprNode, op: str) -> Iterable[ExprNode]:
    if node.kind == "binary" and node.value == op:
        for child in node.children:
            yield from _flatten(child, op)
    else:
        yield node


def _collect(node: ExprNode, operators: list[str], fields: list[str], windows: list[int]) -> None:
    if node.kind == "call":
        operators.append(node.value)
        for index, child in enumerate(node.children):
            if index > 0 and child.kind == "number":
                try:
                    windows.append(int(float(child.value)))
                except ValueError:
                    pass
            _collect(child, operators, fields, windows)
        return
    if node.kind == "identifier":
        fields.append(node.value)
        return
    for child in node.children:
        _collect(child, operators, fields, windows)


def _collect_operators(node: ExprNode, operators: list[str]) -> None:
    if node.kind == "call":
        operators.append(node.value)
    for child in node.children:
        _collect_operators(child, operators)


def _semantic_tokens(profile: ExpressionProfile) -> set[str]:
    tokens = {f"op:{item}" for item in profile.operators}
    tokens.update(f"field:{item}" for item in profile.fields)
    tokens.update(f"w:{_window_bucket(item)}" for item in profile.windows)
    if profile.parsed:
        tokens.add(f"depth:{profile.max_depth}")
    return tokens


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


def _max_depth(node: ExprNode) -> int:
    if not node.children:
        return 1
    return 1 + max(_max_depth(child) for child in node.children)


def _node_count(node: ExprNode) -> int:
    return 1 + sum(_node_count(child) for child in node.children)


def _paren_depth(expression: str) -> int:
    depth = 0
    max_depth = 0
    for char in str(expression or ""):
        if char == "(":
            depth += 1
            max_depth = max(max_depth, depth)
        elif char == ")":
            depth = max(0, depth - 1)
    return max_depth


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _is_number(token: str) -> bool:
    return bool(re.fullmatch(r"\d+(?:\.\d+)?", token))


def _normalize_number(token: str) -> str:
    if "." not in token:
        return token
    value = token.rstrip("0").rstrip(".")
    return value or "0"


def _precedence(op: str) -> int:
    return 2 if op in {"*", "/"} else 1


def _window_bucket(value: int) -> str:
    if value <= 7:
        return "short"
    if value <= 30:
        return "medium"
    return "long"


def _fingerprint(canonical: str) -> str:
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
