"""Minimal YAML parser for packaged hypothesis files.

Extracted from the original ``hypothesis_library.py`` monolith. Supports
the limited YAML subset used by packaged hypothesis files: mappings,
lists, scalars, quoted strings, and folded literal blocks introduced
by ``>``. Intentionally narrow so production can load the bundled
hypotheses without a PyYAML dependency.
"""

from __future__ import annotations

from typing import Any


def _minimal_yaml_load(text: str) -> dict[str, Any]:
    """Parse the limited YAML subset used by packaged hypothesis files.

    Supports mappings, lists, scalars, quoted strings, and folded literal
    blocks introduced by ``>``.  It is intentionally narrow so production can
    load the bundled hypotheses without a PyYAML dependency.
    """

    lines = text.splitlines()
    index = 0

    def current_line() -> str:
        return lines[index] if index < len(lines) else ""

    def indent_of(line: str) -> int:
        return len(line) - len(line.lstrip(" "))

    def strip_comment(line: str) -> str:
        in_quote = None
        out = []
        for ch in line:
            if ch in ("'", '"'):
                in_quote = None if in_quote == ch else ch
            if ch == "#" and in_quote is None:
                break
            out.append(ch)
        return "".join(out).rstrip()

    def parse_scalar(value: str) -> Any:
        raw = value.strip()
        if raw in {"", "null", "Null", "NULL", "~"}:
            return None
        if raw == "{}":
            return {}
        if raw in {"true", "True", "TRUE"}:
            return True
        if raw in {"false", "False", "FALSE"}:
            return False
        if raw.startswith(("'", '"')) and raw.endswith(("'", '"')) and len(raw) >= 2:
            return raw[1:-1]
        if raw.startswith("[") and raw.endswith("]"):
            inner = raw[1:-1].strip()
            if not inner:
                return []
            return [parse_scalar(part) for part in _split_inline_list(inner)]
        try:
            if "." in raw or "e" in raw.lower():
                num = float(raw)
                return int(num) if num.is_integer() else num
            return int(raw)
        except ValueError:
            return raw

    def parse_block(expected_indent: int) -> Any:
        nonlocal index
        mapping: dict[str, Any] = {}
        sequence: list[Any] = []
        is_sequence = False
        while index < len(lines):
            raw_line = strip_comment(current_line())
            if not raw_line.strip():
                index += 1
                continue
            indent = indent_of(raw_line)
            if indent < expected_indent:
                break
            content = raw_line[indent:]
            if content.startswith("- "):
                is_sequence = True
                value_part = content[2:].strip()
                index += 1
                if not value_part:
                    sequence.append(parse_block(indent + 2))
                elif ":" in value_part and not value_part.startswith(("'", '"')):
                    key, _, rest = value_part.partition(":")
                    item = {key.strip(): parse_scalar(rest.strip()) if rest.strip() else parse_block(indent + 4)}
                    merge_nested_item(item, indent + 2)
                    sequence.append(item)
                else:
                    sequence.append(parse_scalar(value_part))
                continue
            if is_sequence:
                break
            if ":" not in content:
                index += 1
                continue
            key, _, rest = content.partition(":")
            key = key.strip().strip('"')
            rest = rest.strip()
            index += 1
            if rest == ">":
                mapping[key] = parse_folded_block(indent + 2)
            elif rest == "":
                mapping[key] = parse_block(indent + 2)
            else:
                mapping[key] = parse_scalar(rest)
        return sequence if is_sequence else mapping

    def parse_folded_block(expected_indent: int) -> str:
        nonlocal index
        parts: list[str] = []
        while index < len(lines):
            line = current_line()
            if not line.strip():
                parts.append("")
                index += 1
                continue
            indent = indent_of(line)
            if indent < expected_indent:
                break
            parts.append(line[indent:])
            index += 1
        return " ".join(part.strip() for part in parts if part.strip())

    def merge_nested_item(item: dict[str, Any], expected_indent: int) -> None:
        nonlocal index
        if index >= len(lines):
            return
        if not current_line().strip():
            return
        indent = indent_of(current_line())
        if indent < expected_indent:
            return
        nested = parse_block(expected_indent)
        if isinstance(nested, dict):
            item.update(nested)

    def _split_inline_list(inner: str) -> list[str]:
        parts: list[str] = []
        current = []
        quote = None
        depth = 0
        for ch in inner:
            if ch in ("'", '"'):
                quote = None if quote == ch else ch
            elif ch == "[" and quote is None:
                depth += 1
            elif ch == "]" and quote is None and depth > 0:
                depth -= 1
            elif ch == "," and quote is None and depth == 0:
                parts.append("".join(current).strip())
                current = []
                continue
            current.append(ch)
        if current:
            parts.append("".join(current).strip())
        return parts

    result = parse_block(0)
    return result if isinstance(result, dict) else {}
