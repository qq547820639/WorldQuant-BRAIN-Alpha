"""Deterministic production API stub for tests.

The shipping package no longer exposes a mock/test-mode BRAIN API. Tests that
exercise orchestration code can still inject this local stub explicitly so the
production package remains clean and no network calls are made.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import re
import threading
from typing import Any

from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.brain_api.context_defaults import DEFAULT_FIELDS, DEFAULT_OPERATORS
from brain_alpha_ops.brain_api.official_helpers import looks_non_production_alpha_id


def _operator_name(operator: Any) -> str:
    if isinstance(operator, dict):
        return str(operator.get("name") or operator.get("id") or "").strip()
    return str(operator or "").strip()


FIELDS: list[dict[str, Any]] = [dict(field) for field in DEFAULT_FIELDS]
OPERATORS: list[str] = [_operator_name(operator) for operator in DEFAULT_OPERATORS]

TEMPLATE_SAFE_FIELD_IDS = ("close", "volume", "returns", "sector")
TEMPLATE_SAFE_OPERATOR_NAMES = (
    "rank",
    "ts_delta",
    "ts_std_dev",
    "ts_rank",
    "zscore",
    "ts_mean",
    "group_rank",
    "ts_corr",
    "ts_decay_linear",
    "group_neutralize",
    "divide",
    "if_else",
    "greater",
    "winsorize",
    "ts_sum",
)


def write_template_safe_official_context(config: Any) -> None:
    """Write the smallest context that satisfies generator-template redlines."""
    from brain_alpha_ops.web_cloud_snapshot import save_official_context_json

    load_config = lambda: config
    dataset = {"id": "pv1", "name": "Price Volume"}
    datasets = [
        {
            "id": dataset["id"] if index == 0 else f"pv{index + 1}",
            "name": dataset["name"] if index == 0 else f"Dataset {index + 1}",
            "field_count": len(TEMPLATE_SAFE_FIELD_IDS) if index == 0 else 0,
        }
        for index in range(10)
    ]
    fields = [
        {"id": field_id, "name": field_id, "dataset": dataset}
        for field_id in TEMPLATE_SAFE_FIELD_IDS
    ]
    save_official_context_json("official_fields.json", fields, load_config=load_config)
    save_official_context_json(
        "official_operators.json",
        [{"name": name} for name in TEMPLATE_SAFE_OPERATOR_NAMES],
        load_config=load_config,
    )
    save_official_context_json(
        "official_datasets.json",
        datasets,
        load_config=load_config,
    )


class ProductionBrainAPIStub:
    def __init__(self):
        self._simulations: dict[str, dict[str, Any]] = {}
        self._counter = 0
        self._lock = threading.Lock()

    def authenticate(self) -> dict[str, Any]:
        return {"status": "ok", "environment": "production", "stub": True}

    def get_user_profile(self) -> dict[str, Any]:
        return {
            "tier": "Consultant",
            "account_tier": "ADVANCED",
            "level": 3,
            "points": 1250.0,
            "username": "production_stub@brain.alpha",
            "raw": {"stub": True},
        }

    def list_fields(
        self,
        query: str = "all",
        region: str = "",
        dataset: str = "",
        progress_callback=None,
    ) -> list[dict[str, Any]]:
        if query in ("", "all", None):
            items = list(FIELDS)
        else:
            needle = str(query).lower()
            items = [field for field in FIELDS if needle in str(field.get("name") or field.get("id") or "").lower()]
        if progress_callback:
            progress_callback({"scanned": len(items), "total": len(items), "range": region or "production"})
        return items

    def list_datasets(self, query: str = "all", region: str = "", progress_callback=None) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for field in FIELDS:
            raw_dataset = field.get("dataset")
            dataset_id = str(raw_dataset.get("id") if isinstance(raw_dataset, dict) else raw_dataset or "").strip()
            if not dataset_id:
                dataset_id = "production"
            row = grouped.setdefault(dataset_id, {"id": dataset_id, "name": dataset_id, "field_count": 0})
            row["field_count"] = int(row.get("field_count", 0) or 0) + 1
        items = sorted(grouped.values(), key=lambda item: str(item.get("id", "")))
        if query not in ("", "all", None):
            needle = str(query).lower()
            items = [
                item
                for item in items
                if needle in str(item.get("id", "")).lower() or needle in str(item.get("name", "")).lower()
            ]
        if progress_callback:
            progress_callback({"scanned": len(items), "total": len(items), "range": region or "production"})
        return items

    def list_operators(self, query: str = "all", progress_callback=None) -> list[dict[str, Any]]:
        items = [{"name": operator} for operator in OPERATORS]
        if query not in ("", "all", None):
            needle = str(query).lower()
            items = [item for item in items if needle in item["name"].lower()]
        if progress_callback:
            progress_callback({"scanned": len(items), "total": len(items)})
        return items

    def list_user_alphas(self, sync_range: str = "3d", progress_callback=None) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        rows: list[dict[str, Any]] = []
        expressions = [
            "rank(ts_delta(close, 20) / ts_std(returns, 20))",
            "rank(ts_mean(volume / adv20, 10))",
            "rank(-ts_std(returns, 60))",
            "rank(ts_mean(returns, 10)) * rank(ts_mean(volume / adv20, 20))",
        ]
        for index, expression in enumerate(expressions, start=1):
            rows.append(
                {
                    "id": f"prod_stub_alpha_{index:03d}",
                    "status": "SUBMITTED" if index % 2 else "PRODUCTION",
                    "expression": expression,
                    "created_at": (now - timedelta(days=index)).isoformat(),
                    "metrics": _metrics_for(expression),
                    "raw": {"stub": True},
                }
            )
            if progress_callback:
                total = 3 if sync_range == "3d" else len(expressions)
                progress_callback(
                    {"scanned": len(rows), "total": total, "last_id": rows[-1]["id"], "range": sync_range}
                )
        return rows[:3] if sync_range == "3d" else rows

    def validate_expression(self, expression: str, settings: dict[str, Any]) -> dict[str, Any]:
        known_fields = {str(field.get("name") or field.get("id") or "") for field in FIELDS}
        known_ops = {operator for operator in OPERATORS if operator}
        errors: list[str] = []
        if expression.count("(") != expression.count(")"):
            errors.append("Unbalanced parentheses")
        called_ops = set(re.findall(r"\b([a-zA-Z_]\w*)\s*\(", expression))
        invalid_ops = sorted(called_ops - known_ops)
        tokens = set(re.findall(r"\b([a-zA-Z_]\w*)\b", expression))
        invalid_fields = sorted(
            token
            for token in tokens - called_ops - known_ops - {"true", "false", "nan"}
            if token not in known_fields and token not in {"std"} and not re.match(r"^[a-z][a-z0-9_]*$", token)
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

    def submit_simulation(self, expression: str, settings: dict[str, Any]) -> str:
        with self._lock:
            self._counter += 1
            sim_id = f"prod_stub_sim_{self._counter:04d}"
            self._simulations[sim_id] = {
                "expression": expression,
                "settings": settings,
                "status": "COMPLETED",
                "alpha_id": f"prod_stub_alpha_{self._counter:04d}",
            }
        return sim_id

    def poll_simulation(self, simulation_id: str) -> str:
        if simulation_id not in self._simulations:
            raise BrainAPIError(f"unknown simulation id: {simulation_id}")
        return str(self._simulations[simulation_id]["status"])

    def fetch_result(self, simulation_id: str) -> dict[str, Any]:
        sim = self._simulations.get(simulation_id)
        if not sim:
            raise BrainAPIError(f"unknown simulation id: {simulation_id}")
        metrics = _metrics_for(str(sim["expression"]))
        metrics["official_alpha_id"] = sim["alpha_id"]
        return {
            "simulation_id": simulation_id,
            "alpha_id": sim["alpha_id"],
            "metrics": metrics,
            "raw": {"stub": True},
        }

    def check_alpha(self, alpha_id: str) -> dict[str, Any]:
        return {"status": "PASSED", "failed_checks": []}

    def submit_alpha(self, alpha_id: str, expression: str, settings: dict[str, Any]) -> dict[str, Any]:
        if looks_non_production_alpha_id(alpha_id):
            raise BrainAPIError(f"refusing to submit non-production alpha_id through ProductionBrainAPIStub: {alpha_id}")
        check = self.check_alpha(alpha_id)
        if check["status"] != "PASSED":
            raise BrainAPIError(f"alpha not submittable: {check}")
        return {
            "status": "SUBMITTED",
            "alpha_id": alpha_id,
            "pre_submit_check": check,
            "raw": {"stub": True},
        }


def _metrics_for(expression: str) -> dict[str, Any]:
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
    sub_universe_sharpe = round(sharpe * (0.55 + (bucket % 35) / 100), 2)
    correlation = round(0.12 + (bucket % 55) / 100, 3)
    concentration = round(0.03 + (bucket % 12) / 100, 3)

    pass_fail = (
        "PASS"
        if sharpe >= 1.25 and fitness >= 1.0 and 0.01 <= turnover <= 0.70 and correlation < 0.70
        else "FAIL"
    )
    return {
        "sharpe": sharpe,
        "fitness": fitness,
        "turnover": turnover,
        "returns": returns,
        "drawdown": drawdown,
        "margin": round(4.5 + bucket / 15, 2),
        "sub_universe_sharpe": sub_universe_sharpe,
        "correlation": correlation,
        "weight_concentration": concentration,
        "pass_fail": pass_fail,
        "turnover_quality_warning": turnover > 0.30,
        "failure_reason": None if pass_fail == "PASS" else "STUB_METRIC_FAIL",
    }
