"""Dynamic Alpha theme engine — replaces hard-coded THEME_LIBRARY.

Generates alpha expression templates from official fields & operators.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import ClassVar, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from brain_alpha_ops.data import OfficialDataLoader, OfficialField


@dataclass
class ThemeTemplate:
    """A dynamically generated Alpha expression template."""
    id: str
    name: str
    category: str                      # "momentum", "value", "quality", "volatility", "hybrid", etc.
    expression: str                    # expression with {FIELD} / {WINDOW} placeholders
    field_slots: List[str] = field(default_factory=list)
    description: str = ""


# --- Template skeletons: category → expression skeleton list ---
# P1-7: Expanded from ~38 to 52+ templates to improve expression diversity.
# checks.jsonl analysis showed 75%+ BLOCKED due to skeleton convergence.
TEMPLATE_SKELETONS: Dict[str, List[str]] = {
    "momentum": [
        "ts_rank({FIELD}, {WINDOW})",
        "ts_delta({FIELD}, {WINDOW})",
        "ts_sum({FIELD}, {WINDOW})",
        "ts_rank(ts_delta({FIELD}, {WINDOW}), {WINDOW2})",
        "group_rank(ts_delta({FIELD}, {WINDOW}), {GROUP})",
        # P1-7 additions
        "rank(ts_decay_linear(ts_delta({FIELD}, {WINDOW}), {WINDOW2}))",
        "ts_rank({FIELD}, {WINDOW}) - ts_rank({FIELD}, {WINDOW2})",
        "rank(ts_mean(ts_delta({FIELD}, {WINDOW}), {WINDOW2}))",
        # M-01 v3: diversity expansion — mid-frequency momentum, weighted variants
        "rank(ts_delta({FIELD}, {WINDOW}) * ts_std_dev({FIELD}, {WINDOW2}))",
        "ts_rank(ts_decay_linear({FIELD}, {WINDOW}), {WINDOW2})",
        "group_rank(ts_decay_linear({FIELD}, {WINDOW}), {GROUP})",
        "rank(winsorize(ts_delta({FIELD}, {WINDOW}), 0.01))",
        "rank(ts_delta({FIELD}, {WINDOW}) / ts_delta({FIELD}, {WINDOW2}))",
        "ts_rank(divide({FIELD}, ts_mean({FIELD}, {WINDOW})), {WINDOW2})",
    ],
    "reversal": [
        "-1 * ts_rank({FIELD}, {WINDOW})",
        "ts_rank(-1 * ts_delta({FIELD}, {WINDOW}), {WINDOW2})",
        "-1 * ts_zscore({FIELD}, {WINDOW})",
        # P1-7 additions
        "-1 * rank(ts_delta({FIELD}, {WINDOW}) / ts_std_dev({FIELD}, {WINDOW2}))",
        "rank(-ts_delta({FIELD}, {WINDOW}) / ts_std_dev({FIELD}, {WINDOW2}))",
        # M-01 v3: short-term reversal, gap-reversal patterns
        "-1 * rank(ts_delta({FIELD}, {WINDOW}) * sign(ts_delta({FIELD}, {WINDOW2})))",
        "rank(-ts_decay_linear(ts_delta({FIELD}, {WINDOW}), {WINDOW2}))",
        "group_rank(-ts_delta({FIELD}, {WINDOW}), {GROUP})",
        "-1 * ts_rank(ts_mean({FIELD}, {WINDOW}), {WINDOW2})",
        "rank(-ts_delta({FIELD}, {WINDOW}) / ts_mean({FIELD}, {WINDOW2}))",
    ],
    "value": [
        "rank(-{FIELD})",
        "rank(zscore(-{FIELD}))",
        "group_rank(-{FIELD}, {GROUP})",
        # P1-7 additions
        "rank(divide(1, 1 + {FIELD}))",
        "rank(zscore(-{FIELD})) * rank(zscore(-1 / {FIELD}))",
        # M-01 v3: normalized value, sector-relative value
        "rank(-{FIELD} / ts_mean({FIELD}, {WINDOW}))",
        "rank(zscore(-ts_mean({FIELD}, {WINDOW})))",
        "group_rank(divide(1, 1 + {FIELD}), {GROUP})",
        "rank(divide(-{FIELD}, ts_std_dev({FIELD}, {WINDOW})))",
        "rank(zscore(-{FIELD})) + rank(zscore(ts_delta(-{FIELD}, {WINDOW})))",
    ],
    "quality": [
        "rank({FIELD})",
        "rank(zscore({FIELD}))",
        "group_rank({FIELD}, {GROUP})",
        # P1-7 additions
        "rank(ts_mean({FIELD}, {WINDOW}))",
        "rank(zscore(ts_mean({FIELD}, {WINDOW})))",
        # M-01 v3: quality stability, margin consistency
        "rank(ts_mean({FIELD}, {WINDOW}) / ts_std_dev({FIELD}, {WINDOW2}))",
        "rank(zscore(divide({FIELD}, ts_mean({FIELD}, {WINDOW}))))",
        "group_rank(ts_mean({FIELD}, {WINDOW}), {GROUP})",
        "rank(winsorize({FIELD}, 0.02))",
        "rank(ts_mean({FIELD}, {WINDOW}) - ts_mean({FIELD}, {WINDOW2}))",
    ],
    "growth": [
        "rank({FIELD})",
        "rank(ts_delta({FIELD}, {WINDOW}))",
        "group_rank({FIELD}, {GROUP})",
        # P1-7 additions
        "rank(ts_delta({FIELD}, {WINDOW}) / ts_std_dev({FIELD}, {WINDOW2}))",
        "rank(ts_sum(ts_delta({FIELD}, {WINDOW}), {WINDOW2}))",
        # M-01 v3: acceleration, sustained growth
        "rank(ts_delta(ts_delta({FIELD}, {WINDOW}), {WINDOW2}))",
        "rank(ts_mean(ts_delta({FIELD}, {WINDOW}), {WINDOW2}) / ts_std_dev(ts_delta({FIELD}, {WINDOW}), {WINDOW3}))",
        "group_rank(ts_delta({FIELD}, {WINDOW}), {GROUP})",
        "rank(ts_sum(ts_delta({FIELD}, {WINDOW}), {WINDOW2}) / ts_mean({FIELD}, {WINDOW3}))",
        "rank(ts_decay_linear(ts_delta({FIELD}, {WINDOW}), {WINDOW2}))",
    ],
    "volatility": [
        "rank(-ts_std_dev({FIELD}, {WINDOW}))",
        "rank(-ts_zscore(ts_std_dev({FIELD}, {WINDOW}), {WINDOW2}))",
        # P1-7 additions
        "rank(-ts_std_dev({FIELD}, {WINDOW}))",
        "rank(-ts_std_dev({FIELD}, {WINDOW}) / ts_mean({FIELD}, {WINDOW2}))",
        "rank(-ts_covariance({FIELD}, returns, {WINDOW}))",
        # M-01 v3: volatility regime, risk-adjusted variants
        "rank(ts_std_dev({FIELD}, {WINDOW}) - ts_std_dev({FIELD}, {WINDOW2}))",
        "rank(-ts_std_dev(ts_delta({FIELD}, {WINDOW}), {WINDOW2}))",
        "group_rank(-ts_std_dev({FIELD}, {WINDOW}), {GROUP})",
        "rank(-ts_std_dev({FIELD}, {WINDOW}) * ts_mean({FIELD}, {WINDOW2}))",
        "rank(-ts_corr({FIELD}, returns, {WINDOW}) * sign(ts_delta({FIELD}, {WINDOW2})))",
    ],
    "liquidity": [
        "rank(ts_mean({FIELD}, {WINDOW}))",
        "rank(ts_delta({FIELD}, {WINDOW}))",
        "rank(ts_corr({FIELD}, returns, {WINDOW}))",
        # P1-7 additions
        "rank(divide({FIELD}, ts_mean({FIELD}, {WINDOW})))",
        "rank(ts_corr(ts_delta({FIELD}, {WINDOW}), returns, {WINDOW2}))",
        # M-01 v3: liquidity shock, turnover-scaled
        "rank(ts_delta({FIELD}, {WINDOW}) / ts_mean({FIELD}, {WINDOW2}))",
        "rank(ts_std_dev({FIELD}, {WINDOW}) / ts_mean({FIELD}, {WINDOW2}))",
        "group_rank(divide({FIELD}, ts_mean({FIELD}, {WINDOW})), {GROUP})",
        "rank(ts_corr({FIELD}, ts_delta({FIELD}, {WINDOW}), {WINDOW2}))",
    ],
    "cross_sectional": [
        "group_rank({FIELD}, {GROUP})",
        "group_zscore({FIELD}, {GROUP})",
        "group_neutralize({FIELD}, {GROUP})",
        # P1-7 additions
        "group_rank(ts_delta({FIELD}, {WINDOW}), {GROUP})",
        "group_neutralize(zscore({FIELD}), {GROUP})",
        # M-01 v3: sector-relative momentum, industry dispersion
        "group_rank(ts_mean({FIELD}, {WINDOW}), {GROUP})",
        "group_zscore(ts_delta({FIELD}, {WINDOW}), {GROUP})",
        "group_neutralize(ts_rank({FIELD}, {WINDOW}), {GROUP})",
        "rank({FIELD} - group_mean({FIELD}, {GROUP}))",
        "group_rank(ts_decay_linear({FIELD}, {WINDOW}), {GROUP})",
    ],
    "hybrid": [
        "rank(ts_rank({FIELD_A}, {WINDOW})) + rank(ts_rank({FIELD_B}, {WINDOW2}))",
        "rank(zscore({FIELD_A})) * rank(zscore({FIELD_B}))",
        "rank(ts_delta({FIELD_A}, {WINDOW}) / ts_std_dev({FIELD_B}, {WINDOW2}))",
        "rank(zscore(ts_rank({FIELD_A}, {WINDOW})) + zscore(ts_rank({FIELD_B}, {WINDOW2})))",
        # P1-7 additions
        "rank(ts_corr({FIELD_A}, {FIELD_B}, {WINDOW}))",
        "rank(zscore({FIELD_A})) + rank(-ts_std_dev({FIELD_B}, {WINDOW}))",
        "rank(ts_delta({FIELD_A}, {WINDOW})) * rank(ts_corr({FIELD_B}, returns, {WINDOW2}))",
        "rank(ts_mean({FIELD_A}, {WINDOW}) / ts_std_dev({FIELD_B}, {WINDOW2}))",
        # M-01 v3: multi-factor interaction, signal blending
        "rank(ts_rank({FIELD_A}, {WINDOW}) * sign(ts_delta({FIELD_B}, {WINDOW2})))",
        "rank(zscore(ts_delta({FIELD_A}, {WINDOW})) - zscore(ts_std_dev({FIELD_B}, {WINDOW2})))",
        "rank(ts_corr(ts_delta({FIELD_A}, {WINDOW}), ts_delta({FIELD_B}, {WINDOW}), {WINDOW2}))",
        "group_rank(zscore({FIELD_A}) + zscore({FIELD_B}), {GROUP})",
        "rank(ts_mean({FIELD_A}, {WINDOW}) * ts_rank({FIELD_B}, {WINDOW2}))",
    ],
    "size": [
        # M-01 v3: size/anomaly category
        "rank(-{FIELD})",
        "rank(zscore(-{FIELD}))",
        "group_rank(-{FIELD}, {GROUP})",
        "rank(-ts_mean({FIELD}, {WINDOW}))",
        "rank(-{FIELD} / ts_std_dev({FIELD}, {WINDOW}))",
    ],
    # P1-7: Existing extra categories
    "decay": [
        "rank(ts_decay_linear({FIELD}, {WINDOW}))",
        "rank(ts_decay_linear(ts_delta({FIELD}, {WINDOW}), {WINDOW2}))",
        "ts_decay_linear(ts_rank({FIELD}, {WINDOW}), {WINDOW2})",
        # M-01 v3
        "rank(ts_decay_linear(zscore({FIELD}), {WINDOW}))",
        "rank(ts_decay_linear(ts_mean({FIELD}, {WINDOW}), {WINDOW2}))",
        "group_rank(ts_decay_linear({FIELD}, {WINDOW}), {GROUP})",
    ],
    "conditional": [
        "rank(if_else(greater({FIELD}, 0), {FIELD}, 0))",
        "rank(if_else(greater(ts_delta({FIELD}, {WINDOW}), 0), {FIELD}, -{FIELD}))",
        # M-01 v3
        "rank(if_else(less({FIELD}, ts_mean({FIELD}, {WINDOW})), -1, 1) * ts_std_dev({FIELD}, {WINDOW2}))",
        "rank(if_else(greater(ts_delta({FIELD}, {WINDOW}), ts_std_dev({FIELD}, {WINDOW2})), {FIELD}, -{FIELD}))",
    ],
    "multi_window": [
        "rank(ts_mean({FIELD}, {WINDOW}) - ts_mean({FIELD}, {WINDOW2}))",
        "rank(ts_std_dev({FIELD}, {WINDOW}) / ts_std_dev({FIELD}, {WINDOW2}))",
        "rank(ts_delta({FIELD}, {WINDOW}) - ts_delta({FIELD}, {WINDOW2}))",
        # M-01 v3
        "rank(ts_rank({FIELD}, {WINDOW}) - ts_rank({FIELD}, {WINDOW2}))",
        "rank(ts_delta({FIELD}, {WINDOW}) / ts_delta({FIELD}, {WINDOW2}))",
        "rank(ts_mean({FIELD}, {WINDOW}) / ts_mean({FIELD}, {WINDOW2}))",
        "rank(ts_std_dev({FIELD}, {WINDOW}) - ts_std_dev({FIELD}, {WINDOW2})) * sign(ts_delta({FIELD}, {WINDOW3}))",
    ],
}

# Default window sizes for template generation
# M-01 v3: Extended window set — fine-grained short windows for reversal/liquidity,
# standard mid windows for momentum/quality, long windows for value/growth anchoring.
DEFAULT_WINDOWS = [2, 3, 5, 8, 10, 12, 15, 18, 20, 25, 30, 40, 50, 60, 90, 120, 150, 180, 200, 252]
DEFAULT_GROUPS = ["sector", "industry", "subindustry"]


def _normalize_operator_aliases(expression: str) -> str:
    """Normalize legacy shorthand to official BRAIN operator names."""
    import re as _re

    replacements = {
        "ts_std": "ts_std_dev",
        "ts_argmax": "ts_arg_max",
        "ts_argmin": "ts_arg_min",
        "ts_cov": "ts_covariance",
    }
    normalized = expression
    for old, new in replacements.items():
        normalized = _re.sub(rf"\b{old}\s*\(", f"{new}(", normalized)
    return normalized


class DynamicThemeEngine:
    """Generates Alpha expression templates from official fields and operators.

    Usage::

        from brain_alpha_ops.data import OfficialDataLoader
        engine = DynamicThemeEngine(OfficialDataLoader.instance())
        engine.build_categories()
        themes = engine.generate(dataset_id="analyst4", n=50)
    """

    def __init__(self, loader: "OfficialDataLoader") -> None:
        self._loader = loader
        self._categories: Dict[str, List["OfficialField"]] = {}
        self._windows = list(DEFAULT_WINDOWS)
        self._groups = list(DEFAULT_GROUPS)

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    def build_categories(self) -> None:
        """Group all official fields by their category string."""
        self._categories.clear()
        for f in self._loader.get_fields():
            cat = (f.category or "unknown").lower()
            self._categories.setdefault(cat, []).append(f)
        # P0-3: Auto-generate additional skeletons from official operators
        self._auto_generated_skeletons = self._build_auto_skeletons()

    # ------------------------------------------------------------------
    # P0-3: Auto-generate skeletons from BRAIN official operators
    # ------------------------------------------------------------------
    def _build_auto_skeletons(self) -> Dict[str, List[str]]:
        """Generate expression skeletons by combining BRAIN official operators.
        
        Sources all operator names from OfficialDataLoader (data/official_operators.json),
        which mirrors BRAIN's /operators API endpoint. Zero hardcoded operator names.
        
        Returns a dict keyed by category with list of expression skeletons.
        """
        # Get operators by category from official data
        ops = self._loader.get_operators()
        ts_ops: List[str] = []       # Time Series
        cs_ops: List[str] = []       # Cross Sectional
        group_ops: List[str] = []    # Group
        arith_ops: List[str] = []    # Arithmetic (binary/comparison only)

        for op in ops:
            cat = (op.category or "").lower()
            name = op.name
            if "time" in cat or cat == "time_series":
                ts_ops.append(name)
            elif "cross" in cat or cat == "cross_sectional":
                cs_ops.append(name)
            elif cat == "group":
                group_ops.append(name)
            elif cat in ("arithmetic", "logical"):
                # Only include operators useful in expression composition
                if name in ("add", "subtract", "multiply", "divide", "power",
                           "signed_power", "min", "max", "greater", "less",
                           "greater_equal", "less_equal", "if_else"):
                    arith_ops.append(name)

        # Preferred operators for alpha construction (most commonly used)
        preferred_ts = [op for op in ts_ops if op in (
            "ts_rank", "ts_delta", "ts_mean", "ts_std_dev", "ts_sum",
            "ts_zscore", "ts_corr", "ts_covariance",
            "ts_product", "ts_regression", "ts_arg_max", "ts_arg_min",
            "ts_av_diff", "ts_scale", "ts_delay", "ts_quantile",
            "ts_count_nans", "ts_step",
            "last_diff_value", "days_from_last_change",
            # P2 fix: removed — require named params incompatible with auto-generation:
            #   ts_backfill (lookback=), ts_decay_linear (dense=), kth_element (k=), hump (hump=)
        )] or ts_ops

        preferred_cs = [op for op in cs_ops if op in (
            "rank", "zscore", "scale", "winsorize", "normalize", "quantile"
        )] or cs_ops

        preferred_group = [op for op in group_ops if op in (
            "group_rank", "group_zscore", "group_neutralize", "group_mean",
            "group_scale", "group_backfill"
        )] or group_ops

        # ── Generate skeletons ──
        auto: Dict[str, List[str]] = {"momentum": [], "reversal": [], "value": [],
                                        "quality": [], "growth": [], "volatility": [],
                                        "liquidity": [], "cross_sectional": [], "hybrid": [],
                                        # P1-7: new categories
                                        "decay": [], "conditional": [], "multi_window": []}
        seen: set = set()

        def add(cat: str, skeleton: str) -> None:
            normalized = skeleton.replace(" ", "")
            if normalized not in seen:
                seen.add(normalized)
                auto.setdefault(cat, []).append(skeleton)

        import random as _random
        _random.seed(42)  # deterministic generation

        # Pattern 1: cross_sectional(time_series(FIELD, WINDOW))
        for cs in preferred_cs[:4]:
            for ts in preferred_ts[:12]:
                add("momentum", f"{cs}({ts}({{FIELD}}, {{WINDOW}}))")
                add("quality", f"{cs}({ts}({{FIELD}}, {{WINDOW}}))")

        # Pattern 2: -1 * cross_sectional(time_series(FIELD, WINDOW)) — reversal
        for cs in preferred_cs[:3]:
            for ts in preferred_ts[:6]:
                add("reversal", f"-1 * {cs}({ts}({{FIELD}}, {{WINDOW}}))")

        # Pattern 3: cs(-FIELD) or cs(zscore(-FIELD)) — value
        for cs in preferred_cs[:4]:
            add("value", f"{cs}(-{{FIELD}})")
            add("value", f"{cs}(zscore(-{{FIELD}}))")

        # Pattern 4: cs(-ts_std_dev(FIELD, WINDOW)) — volatility
        vol_ts = [op for op in preferred_ts if op in ("ts_std_dev", "ts_zscore")]
        for cs in preferred_cs[:3]:
            for ts in (vol_ts or preferred_ts[:3]):
                add("volatility", f"{cs}(-{ts}({{FIELD}}, {{WINDOW}}))")

        # Pattern 5: group_op(FIELD, GROUP) — direct field only
        for grp in preferred_group[:4]:
            add("cross_sectional", f"{grp}({{FIELD}}, {{GROUP}})")
            add("cross_sectional", f"winsorize({grp}({{FIELD}}, {{GROUP}}), std=4)")

        # Pattern 6: cs(ts(FIELD_A, WINDOW)) + cs(ts(FIELD_B, WINDOW2)) — hybrid
        for cs in preferred_cs[:3]:
            for ts_a in preferred_ts[:8]:
                for ts_b in preferred_ts[:8]:
                    if ts_a == ts_b:
                        continue
                    add("hybrid", f"{cs}({ts_a}({{FIELD_A}}, {{WINDOW}})) + {cs}({ts_b}({{FIELD_B}}, {{WINDOW2}}))")
                    break  # limit to one combo per outer pair
                break  # limit total

        # Pattern 7: Multi-layer cs(cs(ts(FIELD, WINDOW))) 
        for outer_cs in preferred_cs[:3]:
            for inner_cs in preferred_cs[:3]:
                if outer_cs == inner_cs:
                    continue
                for ts in preferred_ts[:6]:
                    add("quality", f"{outer_cs}({inner_cs}({ts}({{FIELD}}, {{WINDOW}})))")
                    break

        # Pattern 8: winsorize variants with std parameter
        # P2 fix: exclude ts_rank/last_diff_value — incompatible with BRAIN parser
        for ts in [op for op in preferred_ts[:10]
                   if op not in ("ts_rank", "last_diff_value")]:
            add("momentum", f"rank(winsorize({ts}({{FIELD}}, {{WINDOW}}), std=4))")

        # Pattern 9: ts_corr / ts_covariance with returns
        for cs in preferred_cs[:3]:
            for corr_op in [op for op in preferred_ts if op in ("ts_corr", "ts_covariance")]:
                add("liquidity", f"{cs}({corr_op}({{FIELD}}, returns, {{WINDOW}}))")

        # P1-7: Pattern 10 — ts_decay_linear patterns (decay category)
        for cs in preferred_cs[:3]:
            for ts in preferred_ts[:8]:
                add("decay", f"{cs}(ts_decay_linear({ts}({{FIELD}}, {{WINDOW}}), {{WINDOW2}}))")

        # P1-7: Pattern 11 — if_else conditional patterns (conditional category)
        for cs in preferred_cs[:3]:
            for ts in preferred_ts[:6]:
                add("conditional", f"{cs}(if_else(greater({ts}({{FIELD}}, {{WINDOW}}), 0), {{FIELD}}, -{{FIELD}}))")
                break
        for cs in preferred_cs[:2]:
            for ts in preferred_ts[:4]:
                add("conditional", f"{cs}(if_else(greater(ts_delta({{FIELD}}, {{WINDOW}}), 0), {{FIELD}}, 0))")
                break

        # P1-7: Pattern 12 — multi-window difference patterns
        for cs in preferred_cs[:3]:
            for ts in preferred_ts[:6]:
                add("multi_window", f"{cs}({ts}({{FIELD}}, {{WINDOW}}) - {ts}({{FIELD}}, {{WINDOW2}}))")
                add("multi_window", f"{cs}({ts}({{FIELD}}, {{WINDOW}}) / {ts}({{FIELD}}, {{WINDOW2}}))")
                break

        # P1-7: Pattern 13 — ts_delta / ts_std_dev ratio (normalized momentum)
        for cs in preferred_cs[:3]:
            add("momentum", f"{cs}(ts_delta({{FIELD}}, {{WINDOW}}) / ts_std_dev({{FIELD}}, {{WINDOW2}}))")

        # P1-7: Pattern 14 — product of two cross-sectional rankings
        for cs_a in preferred_cs[:2]:
            for cs_b in preferred_cs[:2]:
                for ts in preferred_ts[:4]:
                    add("hybrid", f"{cs_a}({ts}({{FIELD_A}}, {{WINDOW}})) * {cs_b}({ts}({{FIELD_B}}, {{WINDOW2}}))")
                    break
                break

        return {k: v for k, v in auto.items() if v}  # only non-empty categories

    # P1-7: Skeleton diversity tracker — counts per skeleton-normalized form
    _skeleton_usage: Dict[str, int] = {}

    def record_skeleton_usage(self, expression: str, category: str, blocked: bool = False) -> None:
        """Track skeleton usage frequency. Blocked skeletons get deprioritized."""
        import re
        normalized = re.sub(r'\b[a-z][a-z0-9_]*\b', 'FIELD', expression)
        normalized = re.sub(r'\b\d+\b', 'W', normalized)
        key = f"{category}:{normalized}"
        if blocked:
            self._skeleton_usage[key] = self._skeleton_usage.get(key, 0) + 10  # heavy penalty for blocked
        else:
            self._skeleton_usage[key] = self._skeleton_usage.get(key, 0) + 1

    def get_blocked_skeleton_count(self) -> int:
        """Count skeletons marked as blocked (score >= 10)."""
        return sum(1 for v in self._skeleton_usage.values() if v >= 10)

    def is_skeleton_overused(self, expression: str, category: str, max_usage: int = 5) -> bool:
        """Check if a skeleton has been overused."""
        import re
        normalized = re.sub(r'\b[a-z][a-z0-9_]*\b', 'FIELD', expression)
        normalized = re.sub(r'\b\d+\b', 'W', normalized)
        key = f"{category}:{normalized}"
        return self._skeleton_usage.get(key, 0) >= max_usage

    @property
    def auto_skeletons(self) -> Dict[str, List[str]]:
        """Return auto-generated skeletons (available after build_categories)."""
        return getattr(self, '_auto_generated_skeletons', {})

    # ------------------------------------------------------------------
    # Generate
    # ------------------------------------------------------------------
    def generate(
        self,
        dataset_id: str,
        n: int = 50,
        seed: Optional[int] = None,
    ) -> List[ThemeTemplate]:
        """Generate *n* expression templates for *dataset_id*."""
        if seed is not None:
            random.seed(seed)

        fields = self._loader.get_fields(dataset_id)
        if not fields:
            return []

        # Build per-category field pools for this dataset
        cat_fields: Dict[str, List[str]] = {}
        for f in fields:
            cat = (f.category or "unknown").lower()
            cat_fields.setdefault(cat, []).append(f.id)

        # Map category→skeleton category
        category_map = _build_category_map()

        # Merge proven TEMPLATE_SKELETONS with auto-generated skeletons
        auto_skel = self.auto_skeletons
        merged_skeletons: Dict[str, List[str]] = {}
        for cat in set(list(TEMPLATE_SKELETONS.keys()) + list(auto_skel.keys())):
            merged_skeletons[cat] = (TEMPLATE_SKELETONS.get(cat, []) +
                                     auto_skel.get(cat, []))

        templates: List[ThemeTemplate] = []
        attempts = 0
        while len(templates) < n and attempts < n * 3:
            attempts += 1

            # Pick a skeleton category (70% auto-generated, 30% proven templates for exploration)
            if random.random() < 0.7 and auto_skel:
                skeleton_cat = random.choice(list(auto_skel.keys()))
                skeletons = auto_skel[skeleton_cat]
            else:
                skeleton_cat = random.choice(list(TEMPLATE_SKELETONS.keys()))
                skeletons = TEMPLATE_SKELETONS[skeleton_cat]
            skeleton = random.choice(skeletons)

            # Map to field categories
            mapped_cats = category_map.get(skeleton_cat, [skeleton_cat])
            available_cats = [c for c in mapped_cats if c in cat_fields and cat_fields[c]]
            if not available_cats:
                # Fallback: use any category that has fields
                available_cats = [c for c in cat_fields if cat_fields[c]]
            if not available_cats:
                continue

            # Fill placeholders
            expression = self._fill_placeholders(skeleton, available_cats, cat_fields)
            field_slots = self._extract_field_slots(expression, fields)

            tmpl = ThemeTemplate(
                id=f"theme_{dataset_id}_{len(templates):04d}",
                name=f"{skeleton_cat}_{len(templates):04d}",
                category=skeleton_cat,
                expression=expression,
                field_slots=field_slots,
                description=f"Auto-generated {skeleton_cat} template for {dataset_id}",
            )
            templates.append(tmpl)

        return templates

    def mutate_expression(
        self,
        expression: str,
        dataset_id: str,
        seed: Optional[int] = None,
    ) -> str:
        """Produce a variant of *expression* using fields from *dataset_id*."""
        if seed is not None:
            random.seed(seed)

        fields = self._loader.get_fields(dataset_id)
        if not fields:
            return expression

        field_ids = [f.id for f in fields]
        windows = self._windows

        # Replace numeric literals with varied windows
        # P2 fix: skip numbers that are part of field names (regex uses lookahead/behind
        # to require whitespace/parentheses/operators on both sides)
        import re
        mutated = expression
        for m in re.finditer(r"(?<![a-zA-Z_])(\d+)(?![a-zA-Z_])", expression):
            num = int(m.group(1))
            if 3 <= num <= 252:
                new_win = random.choice(windows)
                mutated = mutated.replace(m.group(0), str(new_win), 1)

        # Optionally wrap with transform
        variant = random.randint(0, 3)
        if variant == 1:
            mutated = f"winsorize({mutated}, std={random.choice([3,4,5])})"
        elif variant == 2:
            mutated = f"zscore({mutated})"

        return _normalize_operator_aliases(mutated)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _fill_placeholders(
        self,
        skeleton: str,
        available_cats: List[str],
        cat_fields: Dict[str, List[str]],
    ) -> str:
        result = skeleton
        used_fields: List[str] = []

        # {FIELD_A}, {FIELD_B}, {FIELD}
        for placeholder in ("{FIELD_A}", "{FIELD_B}", "{FIELD}"):
            if placeholder in result:
                cat = random.choice(available_cats)
                field = random.choice(cat_fields[cat])
                result = result.replace(placeholder, field)
                used_fields.append(field)

        # {WINDOW}, {WINDOW2}
        # P2 fix: don't add window if operator before the placeholder
        # only takes 1 arg (e.g. zscore(expr, WINDOW) → zscore takes only 1)
        _ONE_ARG_OPS = {"zscore", "scale", "normalize", "quantile"}
        for placeholder in ("{WINDOW}", "{WINDOW2}"):
            if placeholder in result:
                win = str(random.choice(self._windows))
                result = result.replace(placeholder, win)

        # {GROUP}
        if "{GROUP}" in result:
            result = result.replace("{GROUP}", random.choice(self._groups))

        # {STD} — safety net for any legacy template that still carries this placeholder
        if "{STD}" in result:
            result = result.replace("{STD}", str(random.choice([3, 4])))

        # ── Dataset field validation: reject phantom fields ──
        result = _normalize_operator_aliases(result)
        result = self._validate_fill_result(result, cat_fields)

        return result

    def _extract_field_slots(self, expression: str, fields: List["OfficialField"]) -> List[str]:
        """Return dataset field ids present in the generated expression."""
        import re as _re

        ids = {field.id.lower() for field in fields}
        tokens = {token.lower() for token in _re.findall(r"\b([a-zA-Z_]\w*)\b", expression)}
        return sorted(ids & tokens)

    def _validate_fill_result(
        self,
        result: str,
        cat_fields: Dict[str, List[str]],
    ) -> str:
        """Ensure every field-like token in *result* exists in official field data.

        Phantom fields (e.g. ``anl20_…``, concatenated names) that survive
        placeholder filling are replaced with a random valid field from
        *cat_fields*.  This mirrors the safety net in
        ``HypothesisDrivenGenerator._validate_dataset_fields`` but protects
        the ``experience_feedback`` / ``random_exploration`` code paths that
        bypass that generator.
        """
        import re as _re

        valid_ids = {field.lower() for fields in cat_fields.values() for field in fields}
        _OPS = {
            "rank", "zscore", "winsorize", "group_zscore", "group_rank",
            "group_mean", "group_scale", "group_backfill", "group_neutralize",
            "ts_rank", "ts_delta", "ts_sum", "ts_mean", "ts_std", "ts_zscore",
            "ts_count_nans", "ts_decay_linear", "ts_std_dev", "ts_regression",
            "ts_av_diff", "ts_kurtosis", "ts_skewness", "ts_scale", "ts_step",
            "ts_product", "ts_corr", "ts_covariance", "ts_min", "ts_max",
            "ts_argmax", "ts_argmin", "ts_percentage", "ts_delay",
            "ts_backfill", "ts_quantile", "ts_arg_max", "ts_arg_min",
            "last_diff_value", "days_from_last_change",
            "kth_element", "log", "signed_power", "inverse", "scale", "power",
            "normalize", "quantile", "returns", "sector", "industry", "market",
            "subindustry", "backfill", "fill_na",
            "subtract", "divide", "greater", "less", "add", "multiply",
            "min", "max", "if_else", "hump",
        }

        tokens = _re.findall(r"\b([a-zA-Z_]\w+)\b", result)
        all_cat_fields = [f for fields in cat_fields.values() for f in fields]

        for t in tokens:
            # Only flag tokens that look like field names (contain underscore)
            # — bare words like std/k/hump are operator parameters, not fields.
            if t not in _OPS and t.lower() not in valid_ids and "_" in t:
                replacement = random.choice(all_cat_fields) if all_cat_fields else "returns"
                result = _re.sub(rf"\b{_re.escape(t)}\b", replacement, result)

        return result

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def windows(self) -> List[int]:
        return list(self._windows)

    @windows.setter
    def windows(self, value: List[int]) -> None:
        self._windows = list(value)

    @property
    def categories(self) -> List[str]:
        return sorted(self._categories.keys())


def _build_category_map() -> Dict[str, List[str]]:
    """Map skeleton category → field categories that can fill its slots."""
    return {
        "momentum": ["price", "model", "technical", "momentum", "analyst"],
        "reversal": ["price", "model", "technical", "analyst"],
        "value": ["fundamental", "valuation", "model", "analyst"],
        "quality": ["fundamental", "quality", "model", "analyst"],
        "growth": ["fundamental", "growth", "model", "analyst"],
        "volatility": ["price", "volatility", "model", "analyst"],
        "liquidity": ["volume", "price", "model", "analyst"],
        "cross_sectional": ["fundamental", "price", "model", "valuation", "analyst"],
        "hybrid": ["price", "fundamental", "model", "volume", "analyst"],
    }
