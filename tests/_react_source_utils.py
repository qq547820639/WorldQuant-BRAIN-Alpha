"""Shared helpers for resolving React source files through re-export entries.

React components were refactored into subdirectories.  The top-level entry
files (e.g. ``components/ScoringPanel.tsx``) now often contain only a re-export
statement such as ``export { default } from './ScoringPanel/ScoringPanel'``.
Static tests that read these entry files see only the re-export stub instead of
the actual implementation.

``resolve_react_source`` follows these re-export entries to the real
implementation files and returns their aggregated content.  It also aggregates
all ``.tsx``/``.ts`` files when pointed at a directory.
"""

from __future__ import annotations

import re
from pathlib import Path

# Matches re-export statements:
#   export { default } from './path'
#   export { foo, bar } from './path'
#   export type { Foo } from './path'
#   export * from './path'
# The { ... } block may span multiple lines (DOTALL).
_REEXPORT_RE = re.compile(
    r'export\s+(?:type\s+)?(?:\*\s*|\{[^}]*\}\s*)from\s+["\']([^"\']+)["\']\s*;?',
    re.DOTALL,
)

_BLOCK_COMMENT_RE = re.compile(r'/\*.*?\*/', re.DOTALL)
_LINE_COMMENT_RE = re.compile(r'//.*$', re.MULTILINE)

_MAX_DEPTH = 8


def _strip_comments(text: str) -> str:
    """Remove ``/* */`` block comments and ``//`` line comments."""
    text = _BLOCK_COMMENT_RE.sub('', text)
    text = _LINE_COMMENT_RE.sub('', text)
    return text


def _resolve_target(base_dir: Path, target: str) -> Path | None:
    """Resolve a re-export target (relative to ``base_dir``) to a concrete path."""
    resolved = (base_dir / target).resolve()
    if resolved.exists():
        return resolved
    # Try adding .tsx / .ts extensions when the target has no extension.
    if not resolved.suffix:
        for ext in ('.tsx', '.ts'):
            candidate = resolved.with_suffix(ext)
            if candidate.exists():
                return candidate
    return None


def _aggregate_directory(directory: Path, _depth: int) -> str:
    """Aggregate all source files in a directory.

    Globs ``.tsx``/``.ts`` (React/TypeScript) and ``.css`` (stylesheets split
    in Phase 15).  ``index.ts`` / ``index.tsx`` re-export files are skipped to
    avoid double-counting the implementation files they re-export.
    """
    parts: list[str] = []
    seen: set[Path] = set()
    for pattern in ('*.tsx', '*.ts', '*.css'):
        for path in sorted(directory.glob(pattern)):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            if path.name in ('index.ts', 'index.tsx'):
                continue
            parts.append(resolve_react_source(path, _depth + 1))
    return "\n".join(parts)


def resolve_react_source(path: Path, _depth: int = 0) -> str:
    """Read a React source file, following re-export entries to actual implementation.

    * If ``path`` points to a directory, aggregate all ``.tsx``/``.ts`` files in
      it (skipping ``index.ts``/``index.tsx`` re-export files).
    * If the file content consists only of re-export statements (optionally
      preceded by comments), follow each re-export to the actual implementation
      file(s) and return their aggregated content instead.
    * Otherwise the file's own content is returned unchanged.

    A depth limit guards against infinite recursion.
    """
    if _depth > _MAX_DEPTH:
        return ''

    if path.is_dir():
        return _aggregate_directory(path, _depth)

    if not path.exists():
        return ''

    content = path.read_text(encoding='utf-8')
    stripped = _strip_comments(content)

    matches = list(_REEXPORT_RE.finditer(stripped))
    if not matches:
        return content

    # Only follow re-exports when the file is a *pure* re-export entry — i.e. it
    # contains nothing besides re-export statements (and comments/whitespace).
    remaining = _REEXPORT_RE.sub('', stripped)
    if remaining.strip():
        return content

    parts: list[str] = []
    for match in matches:
        target = match.group(1)
        resolved = _resolve_target(path.parent, target)
        if resolved is None:
            continue
        parts.append(resolve_react_source(resolved, _depth + 1))
    return "\n".join(parts)
