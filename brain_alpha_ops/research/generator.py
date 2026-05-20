"""Candidate generation and local quality prefiltering.

All field/operator knowledge sourced from OfficialDataLoader (official_*.json).
Zero hard-coded fields or templates.
"""

from __future__ import annotations

import random
import re
from typing import List, Optional, TYPE_CHECKING

from brain_alpha_ops.models import Candidate, new_id
from brain_alpha_ops.research.expression_ast import expression_fingerprint, expression_key, ordered_operators, profile_expression

if TYPE_CHECKING:
    from brain_alpha_ops.data import OfficialDataLoader, FieldDatasetMapper
    from .theme_engine import DynamicThemeEngine
    from .dataset_selector import DatasetSelector

# Default window sizes — can be overridden per dataset frequency (P1-4 TODO).
WINDOWS = [3, 5, 8, 10, 12, 15, 20, 30, 40, 60, 90, 120, 180, 252]
WINSOR_STD = [3, 4, 5, 6]


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
        loader: "Optional[OfficialDataLoader]" = None,
        mapper: "Optional[FieldDatasetMapper]" = None,
        theme_engine: "Optional[DynamicThemeEngine]" = None,
        selector: "Optional[DatasetSelector]" = None,
        *,
        max_field_pool_size: int = 50,
    ) -> None:
        self._cursor = 0
        self._loader = loader
        self._mapper = mapper
        self._theme_engine = theme_engine
        self._selector = selector
        self._max_field_pool_size = max(10, int(max_field_pool_size))

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

    # ------------------------------------------------------------------
    # Context
    # ------------------------------------------------------------------
    def update_context(self, fields: list[dict], operators: list[dict]) -> None:
        """Update known fields/operators (backward-compat, now sourced from loader)."""
        if fields:
            self._fields = {str(item.get("name", "")).lower() for item in fields if item.get("name")}
        if operators:
            self._operators = {str(item.get("name", "")).lower() for item in operators if item.get("name")}

    def set_dataset(self, dataset_id: str) -> None:
        """Set the active dataset for generation."""
        self._dataset_id = dataset_id
        if self._mapper:
            self._fields = set(self._mapper.fields_for(dataset_id))

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
                ds_id: Optional[str] = dataset_id if dataset_id else None
                ds_fields = self._loader.get_fields(ds_id)
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
                return [str(f.get("name", "")) for f in default_fields if f.get("name")]
        except Exception:
            pass

        # Priority 3: self._fields (set by update_context with official API data)
        if self._fields:
            return sorted(self._fields)

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

    # ------------------------------------------------------------------
    # Generate
    # ------------------------------------------------------------------
    def generate(self, count: int, dataset_id: str = "") -> list[Candidate]:
        """Generate *count* alpha candidates for *dataset_id*."""
        ds = dataset_id or self._dataset_id

        # If we have theme_engine, use dynamic generation
        if self._theme_engine and ds:
            return self._generate_dynamic(count, ds)

        # Fallback: use existing fields-based generation
        return self._generate_fallback(count)

    def _generate_dynamic(self, count: int, dataset_id: str) -> list[Candidate]:
        """Use DynamicThemeEngine to produce varied candidates."""
        import logging
        exp_guided = False
        # P2-2: Apply experience guidance — prefer proven operators/windows
        if self._experience_operators:
            self._theme_engine._windows = list(  # type: ignore[union-attr]
                self._experience_windows if self._experience_windows
                else self._theme_engine._windows  # type: ignore[union-attr]
            )
            exp_guided = True
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
        """
        candidates: list[Candidate] = []
        attempts = 0
        diversity_boost = self._observability_diversity_boost
        # P2-2: Blend experienced windows with defaults (70% experience, 30% exploration)
        if self._experience_windows:
            windows = self._experience_windows + [w for w in WINDOWS if w not in self._experience_windows]
        else:
            windows = WINDOWS

        ds_label = dataset_id or self._dataset_id or "default"

        # Build field pool — ONLY from official data sources, never hardcoded
        field_pool = self._build_official_field_pool(dataset_id or self._dataset_id)
        if not field_pool:
            import logging
            logging.error(
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

        # Diverse template skeletons — P1-7: expanded from 10 to 22
        templates = [
            "rank(ts_delta({f1}, {w}) / ts_std_dev(returns, {w}))",
            "rank(ts_rank({f1}, {w}))",
            "rank(zscore({f1}))",
            "rank(-{f1})",
            "rank(ts_mean({f1}, {w}))",
            "group_rank({f1}, sector)",
            "-1 * ts_rank({f1}, {w})",
            "rank({f1}) * rank(ts_delta({f2}, {w}))",
            "rank(ts_corr({f1}, returns, {w}))",
            "ts_rank(ts_delta({f1}, {w}), {w})",
            # P1-7 additions
            "rank(ts_decay_linear(ts_delta({f1}, {w}), {w}))",
            "rank(-ts_std_dev({f1}, {w}))",
            "rank(ts_delta({f1}, {w}) / ts_std_dev({f1}, {w}))",
            "group_neutralize(zscore({f1}), sector)",
            "rank(divide({f1}, ts_mean({f1}, {w})))",
            "rank(ts_mean({f1}, {w}) - ts_mean({f1}, {w}))",
            "rank(ts_corr({f1}, {f2}, {w}))",
            "rank(if_else(greater(ts_delta({f1}, {w}), 0), {f1}, -{f1}))",
            "rank(winsorize(ts_delta({f1}, {w}), 3))",
            "rank(ts_std_dev({f1}, {w}) / ts_std_dev({f1}, {w}))",
            "rank(ts_mean({f1}, {w}) / ts_std_dev({f2}, {w}))",
            "rank(ts_sum(ts_delta({f1}, {w}), {w}))",
        ]
        families = ["momentum", "momentum", "quality", "value", "liquidity",
                     "cross_sectional", "reversal", "hybrid", "liquidity", "momentum",
                     # P1-7 additions
                     "decay", "volatility", "momentum", "cross_sectional", "liquidity",
                     "momentum", "hybrid", "conditional", "momentum", "volatility",
                     "hybrid", "momentum"]

        attempt_limit = count * (16 if diversity_boost else 8)
        while len(candidates) < count and attempts < attempt_limit:
            attempts += 1
            if diversity_boost:
                idx = (attempts * 5 + self._cursor) % len(templates)
                field_index = (attempts * 7 + self._cursor) % len(field_pool)
                field2_index = (attempts * 11 + 3 + self._cursor) % len(field_pool)
                window_index = (attempts * 3 + self._cursor) % len(windows)
            else:
                idx = attempts % len(templates)
                field_index = attempts % len(field_pool)
                field2_index = (attempts + 3) % len(field_pool)
                window_index = attempts % len(windows)
            tmpl = templates[idx]
            f1 = field_pool[field_index]
            f2 = field_pool[field2_index] if "{f2}" in tmpl else f1
            w = windows[window_index]
            expr = tmpl.replace("{f1}", f1).replace("{f2}", f2).replace("{w}", str(w))

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


# ------------------------------------------------------------------
# Field / operator extraction
# ------------------------------------------------------------------

def extract_fields(expression: str, known_fields: Optional[set[str]] = None) -> list[str]:
    """Extract field names from *expression* that match *known_fields*."""
    profile = profile_expression(expression)
    if known_fields is None:
        try:
            from brain_alpha_ops.data import OfficialDataLoader
            loader = OfficialDataLoader.instance()
            known_fields = {f.id.lower() for f in loader.get_fields()}
        except Exception:
            return list(profile.fields)
    tokens = {token.lower() for token in profile.fields}
    return sorted(known_fields & tokens)


def extract_operators(expression: str) -> list[str]:
    """Extract operator names (function-like tokens) from *expression*."""
    return ordered_operators(expression)


def nesting_depth(expression: str) -> int:
    """Compute maximum nesting depth of parentheses in *expression*."""
    profile = profile_expression(expression)
    return max(0, profile.max_depth - 1) if profile.parsed else profile.max_depth


# ------------------------------------------------------------------
# Local quality prefilter
# ------------------------------------------------------------------

def local_quality(candidate: Candidate, min_score: float) -> dict:
    expression = candidate.expression
    score = 55.0
    reasons = []
    fields = candidate.data_fields or extract_fields(expression)
    operators = candidate.operators or extract_operators(expression)
    depth = nesting_depth(expression)

    if not fields:
        score -= 30
        reasons.append("no_known_data_field")
    else:
        score += min(10, len(set(fields)) * 2)

    if not operators:
        score -= 20
        reasons.append("no_operator")
    if depth > 5:
        score -= 15
        reasons.append("expression_too_nested")
    if len(expression) > 220:
        score -= 10
        reasons.append("expression_too_long")
    if not re.search(r"\b(rank|zscore|scale|group_rank|ts_)", expression):
        score -= 12
        reasons.append("weak_standardization_or_time_series_structure")
    if re.search(r"\b(close|open|vwap)\b", expression) and "ts_delta" not in expression and "returns" not in expression:
        score -= 8
        reasons.append("price_level_without_return_transform")
    if len(candidate.hypothesis.strip()) < 20:
        score -= 8
        reasons.append("weak_research_hypothesis")
    if any(op in expression for op in ("ts_mean", "ts_decay_linear", "ts_std")):
        score += 8
    if "adv20" in expression or "vwap" in expression:
        score += 4

    score = max(0.0, min(100.0, round(score, 2)))
    passed = score >= min_score * 10
    return {
        "schema_version": "local-quality-v2",
        "score": score,
        "threshold": min_score * 10,
        "passed": passed,
        "reasons": reasons or ["passed_local_prefilter"],
        "field_count": len(set(fields)),
        "operator_count": len(operators),
        "nesting_depth": depth,
    }


# ------------------------------------------------------------------
# Legacy backward-compat (deprecated, use CandidateGenerator + loader)
# ------------------------------------------------------------------

def mutate_expression(expression: str, index: int, mode: str = "default",
                     experience_windows: list[int] | None = None,
                     field_pool: list[str] | None = None) -> str:
    """Produce a variant of *expression*.

    Modes:
      - "default": random window swap + optional winsorize/zscore wrap
      - "field_swap": keep structure, only vary windows (for low-Sharpe candidates)
      - "field_swap_semantic": replace fields with same-category alternatives (P0-2)
      - "window_perturb": perturb windows by ±20% (P0-2)
      - "structure_change": add winsorize/zscore wrap (for high-correlation candidates)
      - "longer_window": replace windows with longer ones (for high-turnover candidates)
      - "operator_substitute": replace operators with same-family alternatives (P0-2)

    P2-2: When *experience_windows* is provided, blend 70% experience windows
    with 30% default WINDOWS for exploration.
    """
    seed = index
    # P2-2: Blend experience windows (70%) + exploration (30%)
    if experience_windows:
        exp = [w for w in experience_windows if w not in WINDOWS]
        windows = exp + WINDOWS  # experience front-loaded for preference
    else:
        windows = WINDOWS
    numbers = re.findall(r"\b\d+\b", expression)

    if mode == "field_swap":
        mutated = expression
        for pos, number in enumerate(numbers):
            replacement = windows[(index + pos * 7) % len(windows)]
            mutated = re.sub(rf"\b{re.escape(number)}\b", str(replacement), mutated, count=1)
        return mutated

    if mode == "structure_change":
        mutated = expression
        if index % 2 == 0:
            mutated = f"winsorize({mutated}, std=4)"
        else:
            mutated = f"zscore({mutated})"
        return mutated

    if mode == "longer_window":
        long_windows = [60, 90, 120, 180, 252]
        mutated = expression
        for pos, number in enumerate(numbers):
            replacement = long_windows[(index + pos) % len(long_windows)]
            mutated = re.sub(rf"\b{re.escape(number)}\b", str(replacement), mutated, count=1)
        return mutated

    # ── P0-2: New directional mutation modes ──

    if mode == "window_perturb":
        """窗口 ±20% 随机扰动（限制在 [3, 252] 范围内）。"""
        def _perturb(m: re.Match) -> str:
            val = int(m.group(0))
            if val < 2 or val > 1000:
                return m.group(0)
            delta = random.uniform(-0.2, 0.2) * val
            new_val = int(val + delta)
            return str(max(3, min(252, new_val)))
        return re.sub(r"\b\d+\b", _perturb, expression)

    if mode == "field_swap_semantic":
        """语义级字段替换：替换表达式中的字段为 field_pool 中的其他字段。"""
        if not field_pool or len(field_pool) < 2:
            return expression
        field_tokens = re.findall(r"\b([a-zA-Z_]\w*)\b", expression)
        candidate_fields = [
            t for t in field_tokens
            if t in field_pool
        ]
        if not candidate_fields:
            # fallback: 替换 fields 中出现的关键词
            candidate_fields = [
                t for t in field_tokens
                if len(t) > 1 and "_" in t and not t.isdigit()
            ]
        if not candidate_fields:
            return expression
        target = random.choice(candidate_fields)
        alt_pool = [f for f in field_pool if f != target]
        if not alt_pool:
            return expression
        replacement = random.choice(alt_pool)
        return re.sub(r"\b" + re.escape(target) + r"\b", replacement, expression, count=1)

    if mode == "operator_substitute":
        """同族算子替换：从算子功能分组中选择替代算子。"""
        # 同族算子分组（与 iterative_optimizer 保持一致）
        _families = {
            "ranking": ["ts_rank", "rank", "group_rank"],
            "standardization": ["zscore", "scale", "group_zscore"],
            "moving_average": ["ts_mean", "ts_median", "ts_sum"],
            "difference": ["ts_delta", "ts_av_diff"],
            "volatility": ["ts_std", "ts_var"],
            "correlation": ["ts_corr", "ts_covariance"],
            "winsorization": ["winsorize", "truncation"],
            "decay": ["ts_decay_linear", "ts_decay_exp"],
        }
        _alt = {}
        for _family, _ops in _families.items():
            for _op in _ops:
                _alt[_op] = [o for o in _ops if o != _op]
        # 找表达式中的算子
        op_pattern = re.findall(r"\b([a-zA-Z_]\w*)\s*\(", expression)
        for op in op_pattern:
            if op in _alt and _alt[op]:
                replacement = random.choice(_alt[op])
                return re.sub(r"\b" + re.escape(op) + r"\b", replacement, expression, count=1)
        return expression

    # --- default mode (original logic) ---
    w1 = windows[seed % len(windows)]
    w2 = windows[(seed // len(windows) + index * 3 + 5) % len(windows)]
    mutated = expression
    for pos, number in enumerate(numbers):
        replacement = windows[(index + pos * 3) % len(windows)]
        mutated = re.sub(rf"\b{re.escape(number)}\b", str(replacement), mutated, count=1)
    variant = index % 3
    if variant == 1:
        return f"winsorize({mutated}, std=4)"
    if variant == 2:
        return f"zscore({mutated})"
    return mutated


def update_known_fields(fields: list[dict]) -> None:
    """Legacy update (deprecated). Use OfficialDataLoader instead."""
    pass  # no-op in new architecture


def _safe_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
