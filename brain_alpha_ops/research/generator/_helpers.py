"""Helper functions and constants extracted from the original ``generator.py``.

Contains module-level helpers (``update_known_fields``, ``_safe_float``,
template loading) plus the heavy generation method bodies
(``_generate_dynamic``, ``_generate_fallback``) which are attached as
methods on :class:`CandidateGenerator` in ``_generator.py``.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

from brain_alpha_ops.models import Candidate, new_id
from brain_alpha_ops.research.expression_ast import (
    expression_fingerprint,
    expression_key,
    ordered_operators,
)
from brain_alpha_ops.research.fallback_generation import (
    is_high_turnover_generation_risk,
)
from brain_alpha_ops.research.generator_metadata import (
    _expression_operators_are_official,
    expression_windows_within_constraints,
)
from brain_alpha_ops.scoring.local_quality import (
    extract_fields,
    extract_operators,
)
from brain_alpha_ops.research.generator._extras import _safe_float, update_known_fields

# Hardcoded logger name — preserves original ``brain_alpha_ops.research.generator``
# identity for test caplog filtering.
logger = logging.getLogger("brain_alpha_ops.research.generator")


# ═══════════════════════════════════════════════════════════════════════
# Q-03: Template loading — replaced hardcoded skeletons in
#       _generate_fallback() with a YAML-backed configuration.
# ═══════════════════════════════════════════════════════════════════════

# Built-in fallback templates (kept for environments without PyYAML).
# These MUST remain in sync with templates.yaml.
_BUILTIN_FALLBACK_TEMPLATES: list[tuple[str, str]] = [
    ("rank(divide(ts_delta({f1}, {w}), ts_std_dev({f2}, {w})))", "momentum"),
    ("rank(ts_rank({f1}, {w}))", "momentum"),
    ("rank(zscore({f1}))", "quality"),
    ("rank(reverse({f1}))", "value"),
    ("rank(ts_mean({f1}, {w}))", "liquidity"),
    ("rank(subtract(ts_delta({f1}, {w}), ts_delta({f2}, {w})))", "relative_momentum"),
    ("reverse(ts_rank({f1}, {w}))", "reversal"),
    ("multiply(rank({f1}), rank(ts_delta({f2}, {w})))", "hybrid"),
    ("rank(ts_corr({f1}, {f2}, {w}))", "co_movement"),
    ("ts_rank(ts_delta({f1}, {w}), {w})", "momentum"),
    ("rank(ts_decay_linear(ts_delta({f1}, {w}), {w}))", "decay"),
    ("rank(reverse(ts_std_dev({f1}, {w})))", "volatility"),
    ("rank(divide(ts_delta({f1}, {w}), ts_std_dev({f1}, {w})))", "momentum"),
    ("rank(subtract(zscore({f1}), zscore({f2})))", "relative_value"),
    ("rank(divide({f1}, ts_mean({f1}, {w})))", "liquidity"),
    ("rank(subtract(ts_mean({f1}, {w}), ts_mean({f2}, {w})))", "relative_momentum"),
    ("rank(ts_covariance({f1}, {f2}, {w}))", "co_movement"),
    ("rank(if_else(greater(ts_delta({f1}, {w}), 0), {f1}, reverse({f1})))", "conditional"),
    ("rank(winsorize(ts_delta({f1}, {w}), 4))", "momentum"),
    ("rank(divide(ts_std_dev({f1}, {w}), ts_std_dev({f2}, {w})))", "volatility"),
    ("rank(divide(ts_mean({f1}, {w}), ts_std_dev({f2}, {w})))", "hybrid"),
    ("rank(ts_sum(ts_delta({f1}, {w}), {w}))", "momentum"),
]


def _load_fallback_templates() -> tuple[list[str], list[str]]:
    """Load expression templates from ``templates.yaml``.

    Falls back to ``_BUILTIN_FALLBACK_TEMPLATES`` when PyYAML is unavailable
    or the YAML file is missing/corrupt.

    Returns ``(templates: list[str], families: list[str])``.
    """
    if yaml is not None:
        # NOTE: ``templates.yaml`` lives in the parent ``research/`` directory.
        # The original monolithic ``generator.py`` was at
        # ``brain_alpha_ops/research/generator.py``; this sub-module is at
        # ``brain_alpha_ops/research/generator/_helpers.py``, so we use
        # ``parent.parent`` to reach the original location.
        template_path = Path(__file__).resolve().parent.parent / "templates.yaml"
        try:
            if template_path.is_file() and template_path.stat().st_size > 0:
                raw = yaml.safe_load(template_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and isinstance(raw.get("templates"), list):
                    templates: list[str] = []
                    families: list[str] = []
                    for entry in raw["templates"]:
                        expr = str(entry.get("expression", "")).strip()
                        family = str(entry.get("family", "momentum")).strip()
                        if expr and family:
                            templates.append(expr)
                            families.append(family)
                    if templates and families:
                        return templates, families
        except Exception:
            logger.warning(
                "Failed to load templates.yaml; falling back to built-in templates.",
                exc_info=True,
            )

    # Fallback: built-in inline table.
    logger.debug(
        "Using built-in fallback templates (%d entries). Install PyYAML and "
        "ensure templates.yaml is present to customize generation skeletons.",
        len(_BUILTIN_FALLBACK_TEMPLATES),
    )
    templates = [expr for expr, _family in _BUILTIN_FALLBACK_TEMPLATES]
    families = [family for _expr, family in _BUILTIN_FALLBACK_TEMPLATES]
    return templates, families


# ---------------------------------------------------------------------------
# Generation method bodies — attached as methods on CandidateGenerator.
# ---------------------------------------------------------------------------

def _generate_dynamic(self, count: int, dataset_id: str) -> list[Candidate]:
    """Use DynamicThemeEngine to produce varied candidates."""
    exp_guided = False
    # P2-2: Apply experience guidance — prefer proven operators/windows
    if self._experience_operators:
        self._theme_engine.windows = list(
            self._experience_windows if self._experience_windows
            else self._theme_engine.windows
        )
        exp_guided = True
    # ═══ S-04 Phase C: Candidate generation from templates ═══
    themes = self._theme_engine.generate(dataset_id, n=count)  # type: ignore[union-attr]
    # P2-2: Extra generation using experience-proven operators
    if self._experience_operators and len(themes) < count:
        exp_count = min(count - len(themes), max(2, count // 3))
        exp_themes = self._theme_engine.generate(  # type: ignore[union-attr]
            dataset_id, n=exp_count, seed=42
        )
        themes.extend(exp_themes)
    # P2-2: Log whether experience guidance was applied
    if exp_guided:
        logging.info(
            "CandidateGenerator._generate_dynamic: Experience guidance ACTIVE — "
            "%d experience operators, %d experience windows, %d experience fields. "
            "Dataset: %s, count=%d.",
            len(self._experience_operators), len(self._experience_windows),
            len(self._experience_fields), dataset_id, count,
        )
    else:
        logging.debug(
            "CandidateGenerator._generate_dynamic: No experience guidance. "
            "Dataset: %s, count=%d.", dataset_id, count,
        )
    candidates: list[Candidate] = []

    for i, tmpl in enumerate(themes):
        seed = i * 3 + self._cursor if self._observability_diversity_boost else i
        mutated = self._theme_engine.mutate_expression(  # type: ignore[union-attr]
            tmpl.expression, dataset_id, seed=seed
        )
        if not _expression_operators_are_official(mutated, self._official_operators):
            continue
        if not self._expression_satisfies_strict_preferred_constraints(mutated):
            continue
        if is_high_turnover_generation_risk(mutated):
            continue
        if self._knowledge_constraints.get("forbidden_patterns") and self._expression_forbidden(mutated):
            continue
        if any(c.expression == mutated for c in candidates) or self._is_observability_avoided(mutated):
            continue
        candidates.append(
            Candidate(
                alpha_id=new_id("alpha"),
                expression=mutated,
                family=tmpl.category,
                hypothesis=f"Auto-generated {tmpl.category} alpha from dataset {dataset_id}",
                data_fields=sorted(self._fields & set(extract_fields(mutated, self._fields))),
                operators=extract_operators(mutated),
                dataset_id=dataset_id,
                template_source=f"dynamic:{tmpl.category}" + (":observability" if self._observability_diversity_boost else ""),
            )
        )
    self._cursor += max(1, len(themes))
    return candidates


def _generate_fallback(self, count: int, dataset_id: str = "") -> list[Candidate]:
    """Fallback generation — uses real official fields from OfficialDataLoader.

    Never uses hardcoded field names. If no loader/context available,
    raises a clear error rather than silently generating low-quality alphas.

    Template skeletons are loaded from ``templates.yaml``; the
    built-in table is only a fallback when the YAML file is missing.
    """
    candidates: list[Candidate] = []
    attempts = 0
    diversity_boost = self._observability_diversity_boost
    # ═══ S-04 Phase A: Field pool building ═══
    # P2-2: Blend experienced windows with defaults (70% experience, 30% exploration)
    if self._experience_windows:
        windows = self._experience_windows + [w for w in self._windows if w not in self._experience_windows]
    else:
        windows = self._windows

    ds_label = dataset_id or self._dataset_id or "default"

    # ═══ S-04 Phase B: Theme generation ═══
    # Build field pool — ONLY from official data sources, never hardcoded
    field_pool = self._build_official_field_pool(dataset_id or self._dataset_id)
    if not field_pool:
        logger.error(
            "CandidateGenerator._generate_fallback: No official fields available. "
            "Run pipeline with valid credentials to populate data/official_fields.json "
            "and data/official_operators.json."
        )
        return []

    # P2-2: Prefer experience-proven fields (front-load field_pool)
    if self._experience_fields:
        exp_in_pool = [f for f in self._experience_fields if f in field_pool]
        other_fields = [f for f in field_pool if f not in self._experience_fields]
        field_pool = exp_in_pool + other_fields
    frontloaded_preferred_fields: list[str] = []
    if self._knowledge_constraints.get("preferred_fields"):
        preferred_lower = {str(f).lower() for f in self._knowledge_constraints["preferred_fields"]}
        field_by_lower = {str(f).lower(): f for f in field_pool if str(f)}
        official_preferred = [
            field_by_lower.get(field) or field
            for field in self._knowledge_constraints["preferred_fields"]
            if str(field).lower() in preferred_lower
            and (str(field).lower() in field_by_lower or str(field).lower() in self._fields)
        ]
        preferred_fields = []
        seen_preferred: set[str] = set()
        for field in official_preferred:
            key = str(field).lower()
            if key and key not in seen_preferred:
                preferred_fields.append(str(field))
                seen_preferred.add(key)
        frontloaded_preferred_fields = list(preferred_fields)
        remainder = [f for f in field_pool if str(f).lower() not in seen_preferred]
        field_pool = preferred_fields if self._knowledge_constraints.get("strict_preferred_fields") else preferred_fields + remainder

    # Template skeletons must never name fields directly.  Even common
    # BRAIN fields such as returns/sector are unavailable when the local
    # official context is partial, so every field reference is supplied
    # from field_pool via f1/f2.
    templates, families = _load_fallback_templates()

    strict_operators = set(self._knowledge_constraints.get("preferred_operators") or [])
    template_pairs = [
        (template, family)
        for template, family in zip(templates, families)
        if _expression_operators_are_official(template, self._official_operators)
        and (
            not self._knowledge_constraints.get("strict_preferred_operators")
            or {operator.lower() for operator in ordered_operators(template)} <= strict_operators
        )
    ]
    if not template_pairs:
        logger.error(
            "CandidateGenerator._generate_fallback: no fallback templates match official operator snapshot"
        )
        return []
    templates = [template for template, _family in template_pairs]
    families = [family for _template, family in template_pairs]

    attempt_limit = count * (16 if diversity_boost else 8)
    max_generation_seconds = int(
        getattr(self, '_max_generation_seconds', 0) or 120
    )
    _gen_start = time.time()
    logger.info(
        'CandidateGenerator._generate_fallback: count=%d, attempt_limit=%d, max_seconds=%d, field_pool=%d',
        count, attempt_limit, max_generation_seconds, len(field_pool),
    )
    while len(candidates) < count and attempts < attempt_limit:
        if max_generation_seconds > 0 and (time.time() - _gen_start) > max_generation_seconds:
            logger.warning(
                'CandidateGenerator._generate_fallback: TIMEOUT after %d generations (%.1fs)',
                len(candidates), time.time() - _gen_start,
            )
            break
        attempts += 1
        if diversity_boost:
            idx = (attempts * 5 + self._cursor) % len(templates)
            field_index = (attempts * 7 + self._cursor) % len(field_pool)
            field2_index = (attempts * 11 + 3 + self._cursor) % len(field_pool)
            window_index = (attempts * 3 + self._cursor) % len(windows)
        else:
            base = attempts - 1
            idx = base % len(templates)
            field_index = base % len(field_pool)
            field2_index = (base + 3) % len(field_pool)
            window_index = base % len(windows)
        tmpl = templates[idx]
        if frontloaded_preferred_fields and len(candidates) < len(frontloaded_preferred_fields):
            field_index = (attempts - 1) % len(frontloaded_preferred_fields)
        f1 = field_pool[field_index]
        f2 = field_pool[field2_index] if "{f2}" in tmpl else f1
        w = windows[window_index]
        expr = tmpl.replace("{f1}", f1).replace("{f2}", f2).replace("{w}", str(w))
        if not _expression_operators_are_official(expr, self._official_operators):
            continue
        if not expression_windows_within_constraints(expr):
            continue
        if is_high_turnover_generation_risk(expr):
            continue
        if self._knowledge_constraints.get("forbidden_patterns") and self._expression_forbidden(expr):
            continue

        if any(c.expression == expr for c in candidates) or self._is_observability_avoided(expr):
            continue
        candidates.append(
            Candidate(
                alpha_id=new_id("alpha"),
                expression=expr,
                family=families[idx],
                hypothesis=f"Auto-generated {families[idx]} alpha from {ds_label} using {f1}",
                data_fields=(sorted(self._fields & set(extract_fields(expr, self._fields)))
                             if self._fields
                             else sorted(extract_fields(expr, set(field_pool)))),
                operators=extract_operators(expr),
                dataset_id=dataset_id or self._dataset_id,
                template_source=f"fallback:{families[idx]}" + (":observability" if diversity_boost else ""),
            )
        )
    _el = time.time() - _gen_start
    logger.info(
        'CandidateGenerator._generate_fallback: done — %d candidates, %d attempts, %.1fs',
        len(candidates), attempts, _el,
    )
    self._cursor += max(1, attempts)
    return candidates


_MAX_EXPRESSION_LENGTH = 220  # backward-compat: moved to LocalQualityConfig.max_expression_length
