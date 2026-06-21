"""Candidate generation and local quality prefiltering.

All field/operator knowledge sourced from OfficialDataLoader (official_*.json).
Zero hard-coded fields or templates.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

from brain_alpha_ops.models import Candidate, new_id

from brain_alpha_ops.research.expression_ast import (
    expression_fingerprint,
    expression_key,
    expression_similarity,
    ordered_operators,
    profile_expression,
)
from brain_alpha_ops.research.fallback_generation import (
    high_turnover_generation_risk_reasons,
    is_high_turnover_generation_risk,
)
from brain_alpha_ops.research.field_quality import (
    filter_generation_fields,
    generation_field_ids,
)
from brain_alpha_ops.research.generator_metadata import (

    _expression_operators_are_official,
    _load_official_operator_names,
    _load_operators_windows,
    expression_windows_within_constraints,
)

if TYPE_CHECKING:
    from brain_alpha_ops.data import FieldDatasetMapper, OfficialDataLoader


logger = logging.getLogger(__name__)

# Re-exported from scoring module for backward compatibility (W-06 refactor)
from brain_alpha_ops.scoring.local_quality import (
    LocalQualityConfig,
    extract_fields,
    extract_operators,
    local_quality,
    nesting_depth,
)

FORBIDDEN_PATTERN_SIMILARITY_THRESHOLD = 0.90


class CandidateGenerator:
    """Generates alpha candidates using official fields & operators.

    Usage::

        from brain_alpha_ops.data import OfficialDataLoader, FieldDatasetMapper
        from brain_alpha_ops.research.theme_engine import DynamicThemeEngine
        from brain_alpha_ops.research.dataset_selector import DatasetSelector

        loader = OfficialDataLoader.instance()
        mapper = FieldDatasetMapper(); mapper.build(loader)
        engine = DynamicThemeEngine(loader); engine.build_categories()
        selector = DatasetSelector(); selector.initialize(loader)

        gen = CandidateGenerator(loader, mapper, engine, selector)
        candidates = gen.generate(20, dataset_id="analyst4")
    """

    def __init__(
        self,
        loader: "OfficialDataLoader | None" = None,
        mapper: "FieldDatasetMapper | None" = None,
        theme_engine: "DynamicThemeEngine | None" = None,
        selector: "DatasetSelector | None" = None,
        *,
        max_field_pool_size: int = 50,
        local_quality_config: LocalQualityConfig | None = None,
    ) -> None:
        self._cursor = 0
        self._loader = loader
        self._mapper = mapper
        self._theme_engine = theme_engine
        self._selector = selector
        self._max_field_pool_size = max(10, int(max_field_pool_size))
        self._local_quality_config = local_quality_config
        self._windows, self._winsor_stds = _load_operators_windows(loader)
        self._official_operators = _load_official_operator_names(loader)

        # Lazy init fields/operators from loader
        self._fields: set[str] = set()
        self._operators: set[str] = set()
        self._dataset_id: str = ""

        # P2-2: Experience-guided generation
        self._experience_operators: list[str] = []
        self._experience_windows: list[int] = []
        self._experience_fields: list[str] = []
        self._observability_diversity_boost = False
        self._observability_avoid_keys: set[str] = set()
        self._observability_guidance: dict = {}
        self._knowledge_constraints: dict[str, Any] = {
            "preferred_fields": [],
            "preferred_operators": [],
            "forbidden_patterns": [],
            "strict_preferred_fields": False,
            "strict_preferred_operators": False,
        }

    @property
    def windows(self) -> list[int]:
        return list(self._windows)

    @property
    def winsor_stds(self) -> list[int]:
        return list(self._winsor_stds)

    # ------------------------------------------------------------------
    # Context
    # ------------------------------------------------------------------
    def update_context(self, fields: list[dict], operators: list[dict]) -> None:
        """Update known fields/operators (backward-compat, now sourced from loader)."""
        if fields:
            self._fields = set(generation_field_ids(fields))
        if operators:
            names = {str(item.get("name", "")).lower() for item in operators if item.get("name")}
            self._operators = names & self._official_operators if self._official_operators else set()

    def set_dataset(self, dataset_id: str) -> None:
        """Set the active dataset for generation."""
        self._dataset_id = dataset_id
        if self._mapper:
            self._fields = set(generation_field_ids(self._mapper.fields_for(dataset_id)))

    # ------------------------------------------------------------------
    # Field pool — official data only
    # ------------------------------------------------------------------
    def _build_official_field_pool(self, dataset_id: str = "") -> list[str]:
        """Build field pool exclusively from official data sources.
        
        Priority:
          1. OfficialDataLoader (data/official_fields.json)
          2. context_defaults.DEFAULT_FIELDS (lazy-loaded from official JSON)
          3. self._fields (set by update_context with official data)
        
        Never returns hardcoded field names.
        """
        # Priority 1: OfficialDataLoader
        if self._loader:
            try:
                # Treat empty string as None (all datasets)
                ds_id: str | None = dataset_id if dataset_id else None
                raw_fields = self._loader.get_fields(ds_id if ds_id else None)
                ds_fields = filter_generation_fields(raw_fields)
                if raw_fields and not ds_fields:
                    return []
                if ds_fields:
                    # Score fields by coverage, pick top N
                    # P1-5: Dynamic field pool — larger pools for datasets with more fields
                    dl_count = len(ds_fields)
                    dynamic_limit = max(30, min(100, int(dl_count * 0.05)))
                    pool_size = self._max_field_pool_size
                    scored = []
                    for f in ds_fields:
                        # userCount / alphaCount from raw JSON (may not be in schema)
                        user_bonus = min(int(getattr(f, 'userCount', 0) or 0), 50) * 0.01
                        alpha_bonus = min(int(getattr(f, 'alphaCount', 0) or 0), 20) * 0.005
                        coverage = float(getattr(f, 'coverage', 0.0) or 0.0)
                        scored.append((coverage * (1.0 + user_bonus + alpha_bonus), f.id))
                    scored.sort(reverse=True)
                    # P1-5: Use dynamic pool size — respects max_field_pool_size as upper bound
                    effective_limit = min(pool_size, dynamic_limit) if pool_size > 0 else dynamic_limit
                    return [fid for _, fid in scored[:effective_limit]]
            except Exception:
                import logging
                logging.getLogger(__name__).warning(
                    "OfficialDataLoader field pool failed for dataset %s", dataset_id, exc_info=True)

        # Priority 2: context_defaults (lazy-loaded from official JSON files)
        try:
            from brain_alpha_ops.brain_api.context_defaults import get_default_fields
            default_fields = get_default_fields()
            if default_fields:
                return generation_field_ids(default_fields)
        except Exception:
            logger.warning("context default fields unavailable; using in-memory field fallback", exc_info=True)

        # Priority 3: self._fields (set by update_context with official API data)
        if self._fields:
            return sorted(generation_field_ids(self._fields))

        return []

    # ------------------------------------------------------------------
    # P2-2: Experience-guided generation
    # ------------------------------------------------------------------
    def set_experience_guidance(self, patterns: dict) -> None:
        """Apply winning alpha patterns to bias future generation.

        Called by pipeline every N cycles with output from get_winning_patterns().
        Patterns include: top_operators, preferred_windows, field_combinations.
        """
        if not patterns or patterns.get("sample_size", 0) < 3:
            return
        self._experience_operators = patterns.get("top_operators", [])
        self._experience_windows = [int(w) for w in patterns.get("preferred_windows", []) if w]
        # Flatten field combinations
        field_combos = patterns.get("field_combinations", [])
        seen: set[str] = set()
        for combo in field_combos:
            for f in combo.get("fields", []):
                seen.add(str(f).lower())
        self._experience_fields = list(seen)

    def set_observability_guidance(self, guidance: dict) -> None:
        """Apply research-health diagnostics to diversify future generation."""
        guidance = dict(guidance or {})
        flags = {str(flag) for flag in guidance.get("health_flags") or []}
        duplicate_ratio = _safe_float(guidance.get("duplicate_ratio"))
        avoid_keys: set[str] = set()
        for row in guidance.get("avoid_expressions") or guidance.get("top_duplicates") or []:
            if isinstance(row, dict):
                for key in ("expression_canonical", "expression_fingerprint", "expression"):
                    value = str(row.get(key) or "").strip()
                    if value:
                        avoid_keys.add(value)
                expression = str(row.get("expression") or row.get("expression_canonical") or "").strip()
            else:
                expression = str(row or "").strip()
            if expression:
                avoid_keys.add(expression_key(expression))
                avoid_keys.add(expression_fingerprint(expression))
        self._observability_avoid_keys = {item for item in avoid_keys if item}
        self._observability_diversity_boost = bool(
            self._observability_avoid_keys
            or duplicate_ratio >= 0.25
            or {"duplicate_expression_history", "high_duplicate_expression_ratio"} & flags
        )
        self._observability_guidance = {
            "risk_level": guidance.get("risk_level", "unknown"),
            "health_flags": sorted(flags),
            "duplicate_ratio": duplicate_ratio,
            "avoid_expression_count": len(self._observability_avoid_keys),
            "diversity_boost": self._observability_diversity_boost,
        }

    def set_knowledge_constraints(self, constraints: dict[str, Any] | None) -> None:
        """Bias generation toward structured KB rules and away from failures."""
        constraints = dict(constraints or {})
        requested_fields = [str(item).lower() for item in constraints.get("preferred_fields") or [] if str(item)]
        preferred_fields = self._official_preferred_fields(requested_fields)
        preferred_operators = [
            str(item).lower()
            for item in constraints.get("preferred_operators") or []
            if str(item) and str(item).lower() in self._official_operators
        ]
        forbidden_patterns = [str(item).strip() for item in constraints.get("forbidden_patterns") or [] if str(item)]
        strict_preferred_fields = bool(constraints.get("strict_preferred_fields"))
        strict_preferred_operators = bool(constraints.get("strict_preferred_operators"))
        self._knowledge_constraints = {
            "preferred_fields": preferred_fields,
            "preferred_operators": preferred_operators,
            "forbidden_patterns": forbidden_patterns,
            "strict_preferred_fields": strict_preferred_fields,
            "strict_preferred_operators": strict_preferred_operators,
        }
        if preferred_fields:
            self._fields.update(preferred_fields)
        if preferred_operators:
            self._operators.update(preferred_operators)

    def _official_preferred_fields(self, fields: list[str]) -> list[str]:
        if not fields:
            return []
        official_fields = {str(field).lower() for field in self._fields if str(field)}
        if not official_fields:
            official_fields = {
                str(field).lower()
                for field in self._build_official_field_pool(self._dataset_id)
                if str(field)
            }
        return [field for field in fields if field in official_fields]

    # ------------------------------------------------------------------
    # Generate
    # ------------------------------------------------------------------

    # B-05: Public API for hypothesis weight adjustment from experience feedback
    def adjust_hypothesis_weight(self, hypothesis: str, factor: float) -> None:
        """Public method to adjust hypothesis weight from experience feedback.

        Previously accessed via cross-class private attribute
        (self._generator._library.adjust_weight). This public method
        provides a clean API that callers can use without knowing
        internal library details.
        """
        library = getattr(self, "_library", None)
        if library is not None and hasattr(library, "adjust_weight"):
            library.adjust_weight(hypothesis, factor)

    def generate(self, count: int, dataset_id: str = "") -> list[Candidate]:
        """Generate *count* alpha candidates for *dataset_id*."""
        ds = dataset_id or self._dataset_id

        # If we have theme_engine, use dynamic generation
        if self._theme_engine and ds:
            return self._generate_dynamic(count, ds)

        # Fallback: use existing fields-based generation
        return self._generate_fallback(count, ds)

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

    def _expression_satisfies_strict_preferred_constraints(self, expression: str) -> bool:
        """Apply strict KB constraints to generated expressions after mutation."""
        if self._knowledge_constraints.get("strict_preferred_fields"):
            allowed_fields = {str(field).lower() for field in self._knowledge_constraints.get("preferred_fields") or []}
            expression_fields = {str(field).lower() for field in profile_expression(expression).fields}
            groups = {"market", "sector", "industry", "subindustry"}
            expression_fields -= groups
            if not expression_fields or not expression_fields <= allowed_fields:
                return False
        if self._knowledge_constraints.get("strict_preferred_operators"):
            allowed_operators = {
                str(operator).lower()
                for operator in self._knowledge_constraints.get("preferred_operators") or []
            }
            if not allowed_operators:
                return False
            if {operator.lower() for operator in ordered_operators(expression)} - allowed_operators:
                return False
        return True

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

    def _is_observability_avoided(self, expression: str) -> bool:
        if not self._observability_avoid_keys:
            return False
        markers = {
            str(expression or "").strip(),
            expression_key(expression),
            expression_fingerprint(expression),
        }
        return bool(markers & self._observability_avoid_keys)

    def _expression_forbidden(self, expression: str) -> bool:
        expression_text = str(expression or "").strip()
        if not expression_text:
            return False
        expression_lower = expression_text.lower()
        if is_high_turnover_generation_risk(expression_text):
            return True
        try:
            current_key = expression_key(expression_text)
            current_fingerprint = expression_fingerprint(expression_text)
        except Exception:
            current_key = ""
            current_fingerprint = ""
        for pattern in self._knowledge_constraints.get("forbidden_patterns") or []:
            pattern_text = str(pattern or "").strip()
            if not pattern_text:
                continue
            needle = pattern_text.lower()
            if needle and needle in expression_lower:
                return True
            if pattern_text in {expression_text, current_key, current_fingerprint}:
                return True
            try:
                pattern_key = expression_key(pattern_text)
                pattern_fingerprint = expression_fingerprint(pattern_text)
            except Exception:
                pattern_key = ""
                pattern_fingerprint = ""
            if current_key and pattern_key and current_key == pattern_key:
                return True
            if current_fingerprint and pattern_fingerprint and current_fingerprint == pattern_fingerprint:
                return True
            try:
                if expression_similarity(expression_text, pattern_text) >= FORBIDDEN_PATTERN_SIMILARITY_THRESHOLD:
                    return True
            except Exception:
                logger.debug("failed to compare forbidden expression pattern", exc_info=True)
        return False



def update_known_fields(fields: list[dict]) -> None:
    """Legacy update (deprecated). Use OfficialDataLoader instead."""
    pass  # no-op in new architecture


def _safe_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


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
    ("rank(winsorize(ts_delta({f1}, {w}), 3))", "momentum"),
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
        template_path = Path(__file__).resolve().parent / "templates.yaml"
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



# ---- Backward-compat re-export for Phase 3.x migration ----
from .generator_mutation import mutate_expression  # noqa: F401  # backward-compat re-export

# Backward-compat: _get_default_windows moved to generator_metadata
from .generator_metadata import _get_default_windows  # noqa: F401

_MAX_EXPRESSION_LENGTH = 220  # backward-compat: moved to LocalQualityConfig.max_expression_length
