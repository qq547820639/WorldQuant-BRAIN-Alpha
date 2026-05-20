"""Deterministic mock BRAIN API for tests and local demos."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import re
from typing import Any

from .base import BrainAPIError


FIELDS: list[dict] = [
    {"name": "close", "category": "price", "delay": 1, "coverage": 0.99},
    {"name": "open", "category": "price", "delay": 1, "coverage": 0.99},
    {"name": "high", "category": "price", "delay": 1, "coverage": 0.99},
    {"name": "low", "category": "price", "delay": 1, "coverage": 0.99},
    {"name": "vwap", "category": "price", "delay": 1, "coverage": 0.96},
    {"name": "volume", "category": "volume", "delay": 1, "coverage": 0.98},
    {"name": "adv20", "category": "volume", "delay": 1, "coverage": 0.97},
    {"name": "returns", "category": "price", "delay": 1, "coverage": 0.99},
    {"name": "market_cap", "category": "fundamental", "delay": 1, "coverage": 0.92},
    {"name": "sector", "category": "group", "delay": 1, "coverage": 1.0},
    {"name": "industry", "category": "group", "delay": 1, "coverage": 0.99},
    {"name": "subindustry", "category": "group", "delay": 1, "coverage": 0.98},
    {"name": "adv60", "category": "volume", "delay": 1, "coverage": 0.95},
    {"name": "pe_ratio", "category": "fundamental", "delay": 1, "coverage": 0.88},
    {"name": "pb_ratio", "category": "fundamental", "delay": 1, "coverage": 0.87},
    {"name": "dividend_yield", "category": "fundamental", "delay": 1, "coverage": 0.85},
    {"name": "beta", "category": "risk", "delay": 1, "coverage": 0.90},
    {"name": "ivol", "category": "risk", "delay": 1, "coverage": 0.89},
    {"name": "turn", "category": "liquidity", "delay": 1, "coverage": 0.91},
]

OPERATORS: list[str] = [
    "rank", "zscore", "scale",
    "group_rank", "group_zscore", "group_neutralize",
    "ts_mean", "ts_std", "ts_sum", "ts_delta", "ts_rank", "ts_corr",
    "ts_decay_linear", "ts_zscore", "ts_product",
    "ts_min", "ts_max", "ts_argmax", "ts_argmin", "ts_median",
    "winsorize", "abs", "sign", "log", "max", "min", "power", "sqrt", "signed_power",
    "add", "subtract", "multiply", "divide",
    "if_else",
]


def _init_from_official_loader():
    """Try to load fields/operators from OfficialDataLoader JSON files.

    Side-effect: mutates module-level FIELDS and OPERATORS lists in-place
    when official JSON data is available. Called once during first
    MockBrainAPI construction.
    """
    global FIELDS, OPERATORS, _OFFICIAL_LOADED
    if _OFFICIAL_LOADED:
        return
    _OFFICIAL_LOADED = True
    try:
        from brain_alpha_ops.data import OfficialDataLoader

        loader = OfficialDataLoader.instance()
        official_fields = loader.get_fields()
        official_operators = loader.get_operators()

        if official_fields:
            FIELDS = [
                {"name": f.id, "category": f.category, "delay": f.delay, "coverage": f.coverage}
                for f in official_fields
            ]
        if official_operators:
            OPERATORS = [op.name for op in official_operators]
    except Exception:
        # Keep the expanded built-in lists (already populated above)
        pass


_OFFICIAL_LOADED = False


class MockBrainAPI:
    def __init__(self):
        _init_from_official_loader()
        self._simulations: dict[str, dict[str, Any]] = {}
        self._counter = 0

    def authenticate(self) -> dict:
        return {"status": "ok", "environment": "mock"}

    def get_user_profile(self) -> dict:
        """Mock user profile — reflects simulated Consultant tier."""
        return {
            "tier": "Consultant",
            "level": 3,
            "points": 1250.0,
            "username": "mock_consultant@brain.alpha",
            "raw": {
                "tier": "Consultant",
                "level": 3,
                "points": 1250.0,
                "username": "mock_consultant@brain.alpha",
            },
        }

    def list_fields(self, query: str = "all", region: str = "", progress_callback=None) -> list[dict]:
        if query in ("", "all", None):
            items = list(FIELDS)
        else:
            items = [field for field in FIELDS if query.lower() in field["name"].lower()]
        if progress_callback:
            progress_callback({"scanned": len(items), "total": len(items), "range": region or "mock"})
        return items

    def list_datasets(self, query: str = "all", region: str = "", progress_callback=None) -> list[dict]:
        items: list[dict[str, Any]] = []
        try:
            from brain_alpha_ops.data import OfficialDataLoader

            for ds in OfficialDataLoader.instance().get_datasets():
                items.append({"id": ds.id, "name": ds.name, "field_count": ds.field_count})
        except Exception:
            items = []
        if not items:
            grouped: dict[str, dict[str, Any]] = {}
            for field in FIELDS:
                raw_dataset = field.get("dataset")
                dataset_id = str(raw_dataset.get("id") if isinstance(raw_dataset, dict) else raw_dataset or "").strip()
                if not dataset_id:
                    continue
                row = grouped.setdefault(dataset_id, {"id": dataset_id, "name": dataset_id, "field_count": 0})
                row["field_count"] = int(row.get("field_count", 0) or 0) + 1
            items = sorted(grouped.values(), key=lambda item: str(item.get("id", "")))
        if not items:
            items = [{"id": "mock", "name": "Mock Dataset", "field_count": len(FIELDS)}]
        if query not in ("", "all", None):
            needle = str(query).lower()
            items = [item for item in items if needle in str(item.get("id", "")).lower() or needle in str(item.get("name", "")).lower()]
        if progress_callback:
            progress_callback({"scanned": len(items), "total": len(items), "range": region or "mock"})
        return items

    def list_operators(self, query: str = "all", progress_callback=None) -> list[dict]:
        items = [{"name": operator} for operator in OPERATORS]
        if query not in ("", "all", None):
            items = [item for item in items if query.lower() in item["name"].lower()]
        if progress_callback:
            progress_callback({"scanned": len(items), "total": len(items)})
        return items

    def list_user_alphas(self, sync_range: str = "3d", progress_callback=None) -> list[dict]:
        now = datetime.now(timezone.utc)
        rows = []
        expressions = [
            "rank(ts_delta(close, 20) / ts_std(returns, 20))",
            "rank(ts_mean(volume / adv20, 10))",
            "rank(-ts_std(returns, 60))",
            "rank(ts_mean(returns, 10)) * rank(ts_mean(volume / adv20, 20))",
        ]
        for index, expression in enumerate(expressions, start=1):
            rows.append(
                {
                    "id": f"mock_cloud_alpha_{index:03d}",
                    "status": "SUBMITTED" if index % 2 else "PRODUCTION",
                    "expression": expression,
                    "created_at": (now - timedelta(days=index)).isoformat(),
                    "metrics": _metrics_for(expression),
                    "raw": {"mock": True},
                }
            )
            if progress_callback:
                progress_callback({"scanned": len(rows), "total": 3 if sync_range == "3d" else len(expressions), "last_id": rows[-1]["id"], "range": sync_range})
        if sync_range == "3d":
            return rows[:3]
        return rows

    def validate_expression(self, expression: str, settings: dict) -> dict:
        known_fields = {field["name"] for field in FIELDS}
        known_ops = set(OPERATORS)
        errors = []
        if expression.count("(") != expression.count(")"):
            errors.append("Unbalanced parentheses")
        called_ops = set(re.findall(r"\b([a-zA-Z_]\w*)\s*\(", expression))
        invalid_ops = sorted(called_ops - known_ops)
        # In mock mode, accept any identifier-like token as a potential field
        # (real fields come from official_*.json which the mock doesn't replicate)
        tokens = set(re.findall(r"\b([a-zA-Z_]\w*)\b", expression))
        invalid_fields = sorted(
            token
            for token in tokens - called_ops - known_ops - {"true", "false", "nan"}
            if token not in known_fields
            and token not in {"std"}
            and not re.match(r"^[a-z][a-z0-9_]*$", token)  # accept snake_case identifiers as potential real fields
        )
        if invalid_ops:
            errors.append("Unknown operators: " + ", ".join(invalid_ops))
        if invalid_fields:
            errors.append("Unknown fields: " + ", ".join(invalid_fields))
        return {
            "status": "PASS" if not errors else "FAIL",
            "errors": errors,
            "invalid_operators": invalid_ops,
            "invalid_fields": invalid_fields,
        }

    def submit_simulation(self, expression: str, settings: dict) -> str:
        self._counter += 1
        sim_id = f"mock_sim_{self._counter:04d}"
        self._simulations[sim_id] = {
            "expression": expression,
            "settings": settings,
            "status": "COMPLETED",
            "alpha_id": f"mock_alpha_{self._counter:04d}",
        }
        return sim_id

    def poll_simulation(self, simulation_id: str) -> str:
        if simulation_id not in self._simulations:
            raise BrainAPIError(f"unknown simulation id: {simulation_id}")
        return self._simulations[simulation_id]["status"]

    def fetch_result(self, simulation_id: str) -> dict:
        sim = self._simulations.get(simulation_id)
        if not sim:
            raise BrainAPIError(f"unknown simulation id: {simulation_id}")
        expression = sim["expression"]
        metrics = _metrics_for(expression)
        metrics["official_alpha_id"] = sim["alpha_id"]
        return {
            "simulation_id": simulation_id,
            "alpha_id": sim["alpha_id"],
            "metrics": metrics,
            "raw": {"mock": True},
        }

    def check_alpha(self, alpha_id: str) -> dict:
        return {"status": "PASSED", "failed_checks": []}

    def submit_alpha(self, alpha_id: str, expression: str, settings: dict) -> dict:
        check = self.check_alpha(alpha_id)
        if check["status"] != "PASSED":
            raise BrainAPIError(f"mock alpha not submittable: {check}")
        return {
            "status": "SUBMITTED",
            "alpha_id": alpha_id,
            "pre_submit_check": check,
            "raw": {"mock": True},
        }


def _metrics_for(expression: str) -> dict:
    digest = hashlib.md5(expression.encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) % 100
    expr = expression.lower()
    quality_bonus = 0.0
    if "ts_std" in expr and "returns" in expr:
        quality_bonus += 0.45
    if "adv20" in expr or "vwap" in expr:
        quality_bonus += 0.20
    if "ts_mean" in expr or "ts_decay_linear" in expr:
        quality_bonus += 0.10

    sharpe = round(0.80 + bucket / 80 + quality_bonus, 2)
    fitness = round(max(0.0, sharpe * 0.78), 2)
    turnover = round(0.05 + (bucket % 55) / 100, 3)
    returns = round(0.015 + sharpe * 0.025, 4)
    drawdown = round(0.05 + (bucket % 16) / 100, 3)
    sub_u = round(sharpe * (0.55 + (bucket % 35) / 100), 2)
    correlation = round(0.12 + (bucket % 55) / 100, 3)
    concentration = round(0.03 + (bucket % 12) / 100, 3)

    # ── Pass/fail using actual QualityThresholds ──
    # Threshold sources:
    #   min_sharpe=1.25             → BRAIN LOW_SHARPE (Delay-1)
    #   min_fitness=1.0             → BRAIN LOW_FITNESS (Delay-1)
    #   min_turnover=0.01           → BRAIN LOW_TURNOVER
    #   platform_max_turnover=0.70  → BRAIN HIGH_TURNOVER (平台硬门槛)
    #   target_max_turnover=0.30    → 顾问质量目标 (WARNING)
    #   max_correlation=0.70        → BRAIN SELF_CORRELATION
    #   max_concentration=0.10      → BRAIN CONCENTRATED_WEIGHT
    try:
        from brain_alpha_ops.config import QualityThresholds
        thresholds = QualityThresholds()
    except Exception:
        thresholds = None

    if thresholds is not None:
        pass_fail = (
            "PASS"
            if sharpe >= thresholds.min_sharpe
            and fitness >= thresholds.min_fitness
            and thresholds.min_turnover <= turnover <= thresholds.platform_max_turnover
            and correlation < thresholds.max_self_correlation
            and concentration <= thresholds.max_weight_concentration
            else "FAIL"
        )
        turnover_quality_warning = (
            turnover > getattr(thresholds, "target_max_turnover", 0.30)
        )
    else:
        # Fallback aligned with BRAIN official thresholds (Delay-1)
        pass_fail = (
            "PASS"
            if sharpe >= 1.25
            and fitness >= 1.0
            and 0.01 <= turnover <= 0.70
            and correlation < 0.70
            else "FAIL"
        )
        turnover_quality_warning = turnover > 0.30

    return {
        "sharpe": sharpe,
        "fitness": fitness,
        "turnover": turnover,
        "returns": returns,
        "drawdown": drawdown,
        # BRAIN 顾问标准: margin in bps, typically 2-15 for viable alphas
        "margin": round(4.5 + bucket / 15, 2),
        "sub_universe_sharpe": sub_u,
        "correlation": correlation,
        "weight_concentration": concentration,
        "pass_fail": pass_fail,
        "turnover_quality_warning": turnover_quality_warning,
        "failure_reason": None if pass_fail == "PASS" else "MOCK_METRIC_FAIL",
    }
