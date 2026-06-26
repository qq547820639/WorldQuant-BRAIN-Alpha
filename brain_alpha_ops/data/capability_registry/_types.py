"""Capability registry data types.

Defines frozen dataclasses for BRAIN capability metadata. Each CapabilityEntry
captures a single capability (field, operator, dataset, region, etc.) along
with provenance, scope, allowed/forbidden values, validation rule, and an
error hint used when validation fails.

Per the project convention, logger names MUST be hardcoded to maintain
original module names after splitting.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

CapabilityKind = Literal[
    "field",
    "operator",
    "dataset",
    "region",
    "universe",
    "delay",
    "decay",
    "neutralization",
    "truncation",
    "pasteurization",
    "nan_handling",
    "unit_handling",
    "test_period",
    "visualization",
]


class CapabilityResolutionError(Exception):
    """Raised when a capability is missing/ambiguous and requires human confirmation.

    Catching this exception lets upstream code surface a "needs human
    confirmation" state to the user rather than auto-extending or guessing
    platform rules. The spec requires that any missing/ambiguous capability
    triggers this state; the registry MUST NOT silently invent values.
    """


@dataclass(frozen=True)
class CapabilityEntry:
    """A single BRAIN capability (field, operator, region, etc.).

    Frozen so registry contents are immutable after construction. Callers
    that need to override a value should construct a new entry via
    ``dataclasses.replace``.
    """

    name: str
    kind: CapabilityKind
    source: str  # filepath or "official_context"
    updated_at: str = ""
    scope: tuple[str, ...] = ()
    default_value: Any = None
    allowed_values: frozenset[Any] = field(default_factory=frozenset)
    forbidden_values: tuple[Any, ...] = ()
    validation_rule: Callable[[Any], bool] | str | None = None
    error_hint: str = ""

    def matches(self, value: Any) -> bool:
        """Return True when *value* is permitted by this entry."""
        if value in self.forbidden_values:
            return False
        if self.allowed_values and value not in self.allowed_values:
            return False
        if isinstance(self.validation_rule, str):
            return True  # rule id is informational; caller defers
        if callable(self.validation_rule):
            try:
                return bool(self.validation_rule(value))
            except Exception:
                return False
        return True


@dataclass(frozen=True)
class CapabilityRegistry:
    """Immutable view over a collection of CapabilityEntry objects.

    Lookup helpers cover the common BRAIN-Ops access patterns: operator
    names, field ids, dataset ids, and allowed-values for the BrainSettings
    enums (region/universe/delay/decay/...).
    """

    entries: tuple[CapabilityEntry, ...] = ()
    built_at: str = ""
    source_tag: str = "official_context"

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------
    def operators(self) -> set[str]:
        """Return the set of operator names known to the registry."""
        return {e.name for e in self.entries if e.kind == "operator"}

    def fields(self) -> set[str]:
        """Return the set of field ids known to the registry."""
        return {e.name for e in self.entries if e.kind == "field"}

    def field_category_index(self) -> dict[str, list[str]]:
        """Return a ``category → [field_ids]`` index built from field entries.

        Field entries store their category as the first element of ``scope``.
        Entries without a category are grouped under the empty-string key.
        Field ids are lowercased to match the existing DatasetSelector
        convention. The order of field ids within each category follows the
        registry's entry order (stable).
        """
        index: dict[str, list[str]] = {}
        for entry in self.entries:
            if entry.kind != "field":
                continue
            category = entry.scope[0] if entry.scope else ""
            index.setdefault(category, []).append(entry.name.lower())
        return index

    def datasets(self) -> set[str]:
        """Return the set of dataset ids known to the registry."""
        return {e.name for e in self.entries if e.kind == "dataset"}

    def by_kind(self, kind: CapabilityKind) -> list[CapabilityEntry]:
        """Return all entries of *kind*."""
        return [e for e in self.entries if e.kind == kind]

    def get(self, name: str, kind: CapabilityKind | None = None) -> CapabilityEntry:
        """Return the entry matching *name* (case-insensitive).

        Raises CapabilityResolutionError if missing or ambiguous, surfacing
        a "needs human confirmation" state to the caller.
        """
        needle = name.lower()
        matches = [
            e for e in self.entries
            if e.name.lower() == needle and (kind is None or e.kind == kind)
        ]
        if not matches:
            raise CapabilityResolutionError(
                f"capability {name!r} (kind={kind or 'any'}) is missing from the "
                "registry; needs human confirmation before extension"
            )
        if len(matches) > 1:
            kinds = sorted({e.kind for e in matches})
            raise CapabilityResolutionError(
                f"capability {name!r} is ambiguous across kinds {kinds}; "
                "needs human confirmation"
            )
        return matches[0]

    def allowed_values(self, kind: CapabilityKind) -> frozenset[Any]:
        """Return the union of allowed_values for entries of *kind*.

        For region/universe/etc. this returns the canonical BRAIN set. For
        field/operator/dataset kinds, returns the union of all entry names.
        """
        union: set[Any] = set()
        for e in self.entries:
            if e.kind != kind:
                continue
            if e.allowed_values:
                union.update(e.allowed_values)
            else:
                union.add(e.name)
        return frozenset(union)

    def default_value(self, kind: CapabilityKind) -> Any:
        """Return the default value for the first entry of *kind* with a default."""
        for e in self.entries:
            if e.kind == kind and e.default_value is not None:
                return e.default_value
        return None

    def __len__(self) -> int:
        return len(self.entries)


__all__ = [
    "CapabilityEntry",
    "CapabilityKind",
    "CapabilityRegistry",
    "CapabilityResolutionError",
]
