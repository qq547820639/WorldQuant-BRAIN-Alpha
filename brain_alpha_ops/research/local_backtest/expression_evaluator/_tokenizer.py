"""Tokenizer and parser mixin for ``LocalExpressionEvaluator``."""

from __future__ import annotations

import re

# Pre-compiled tokenizer regex — executed once at import, not per-expression
_TOKEN_PATTERN = re.compile(
    r"("
    r"[a-zA-Z_][a-zA-Z0-9_]*"  # identifier
    r"|[0-9]+(?:\.[0-9]*)?"  # number
    r'|[+\-*/()=<>!?,]'  # operator / punctuation
    r")\s*"
)


class _TokenizerMixin:
    """Tokenizer and recursive-descent parser for FASTEXPR expressions."""

    def _tokenize(self, expression: str) -> list[tuple[str, str]]:
        """Tokenize a FASTEXPR expression string."""
        tokens: list[tuple[str, str]] = []
        for match in _TOKEN_PATTERN.finditer(expression):
            token = match.group(1).strip()
            if not token:
                continue
            if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", token):
                tokens.append(("ident", token))
            elif re.match(r"^[0-9]+(?:\.[0-9]*)?$", token):
                tokens.append(("number", token))
            elif token in ("+", "-", "*", "/"):
                tokens.append(("arith", token))
            elif token == "(":
                tokens.append(("lparen", token))
            elif token == ")":
                tokens.append(("rparen", token))
            elif token == ",":
                tokens.append(("comma", token))
            else:
                tokens.append(("punct", token))
        return tokens

    def _parse(
        self,
        tokens: list[tuple[str, str]],
        *,
        max_depth: int = 6,
        depth: int = 0,
    ) -> dict:
        if depth > max_depth:
            raise ValueError(f"expression exceeds max depth {max_depth}")

        index = 0
        current_depth = depth  # nonlocal depth tracker for nested calls

        def peek() -> tuple[str, str] | None:
            nonlocal index
            return tokens[index] if index < len(tokens) else None

        def consume() -> tuple[str, str]:
            nonlocal index
            tok = tokens[index]
            index += 1
            return tok

        def parse_primary() -> dict:
            nonlocal current_depth
            current_depth += 1
            if current_depth > max_depth:
                raise ValueError(
                    f"expression exceeds max depth {max_depth}"
                )

            tok = peek()
            if tok is None:
                raise ValueError("unexpected end of expression")
            kind, value = tok

            if (
                kind == "ident"
                and index + 1 < len(tokens)
                and tokens[index + 1][0] == "lparen"
            ):
                # Function call — depth increments for the call itself and for each arg
                func_name = value
                consume()  # ident
                consume()  # lparen
                args = []
                while peek() and peek()[0] != "rparen":
                    args.append(parse_expr())
                    if peek() and peek()[0] == "comma":
                        consume()
                if peek() and peek()[0] == "rparen":
                    consume()
                else:
                    raise ValueError(
                        f"missing closing paren for {func_name}"
                    )
                current_depth -= 1
                return {
                    "kind": "call",
                    "func": func_name,
                    "args": args,
                    "depth": current_depth,
                }

            elif kind == "lparen":
                consume()
                expr = parse_expr()
                if peek() and peek()[0] == "rparen":
                    consume()
                current_depth -= 1
                return expr

            elif kind == "number":
                consume()
                current_depth -= 1
                return {"kind": "literal", "value": float(value)}

            elif kind == "ident":
                consume()
                current_depth -= 1
                return {"kind": "ident", "value": value}

            elif (
                kind == "arith"
                and value == "-"
                and (
                    index == 0
                    or tokens[index - 1][0]
                    in ("lparen", "arith", "comma")
                )
            ):
                # Unary minus
                consume()
                operand = parse_primary()
                current_depth -= 1
                return {"kind": "unary", "op": "neg", "arg": operand}

            else:
                raise ValueError(f"unexpected token: {tok}")

        def parse_expr() -> dict:
            # Build: primary (arith primary)*  — left-associative
            left = parse_primary()
            while peek() and peek()[0] == "arith":
                op = peek()[1]
                # Check for unary minus (already handled in parse_primary)
                if (
                    op == "-"
                    and isinstance(left, dict)
                    and left.get("kind") == "literal"
                    and left.get("value") == 0.0
                ):
                    break  # handled as unary
                consume()  # consume arith
                right = parse_primary()
                left = {
                    "kind": "binary",
                    "op": op,
                    "left": left,
                    "right": right,
                }
            return left

        return parse_expr()
