from __future__ import annotations

import math

import pytest

from brain_alpha_ops.research.local_backtest_engine import (
    BacktestMetrics,
    LocalBacktestEngine,
    LocalExpressionEvaluator,
    MarketDataFrame,
    MetricsComputer,
    PortfolioConstructor,
    SyntheticDataProvider,
    _cumsum,
    _rank_values,
    _safe_corr,
    _safe_mean,
    _safe_stdev,
    _spearman_r,
)


def _small_data() -> MarketDataFrame:
    return MarketDataFrame(
        fields={
            "close": [
                [10.0, 20.0, 30.0],
                [11.0, 18.0, 33.0],
                [12.0, 17.0, 36.0],
                [13.0, 16.0, 39.0],
            ],
            "returns": [
                [0.01, -0.01, 0.02],
                [0.02, -0.02, 0.01],
                [-0.01, 0.03, 0.0],
                [0.01, 0.01, -0.02],
            ],
            "volume": [
                [100, 200, 300],
                [120, 180, 330],
                [130, 170, 360],
                [140, 160, 390],
            ],
            "sector": [
                [1, 1, 2],
                [1, 1, 2],
                [1, 1, 2],
                [1, 1, 2],
            ],
        },
        dates=["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"],
        symbols=["A", "B", "C"],
        n_dates=4,
        n_symbols=3,
    )


def test_synthetic_data_provider_generates_weekdays_and_field_variants():
    provider = SyntheticDataProvider()
    data = provider.generate(
        n_dates=6,
        n_symbols=4,
        fields=["close", "volume", "returns", "market_cap", "momentum_1m", "volatility_1m", "rsi_14", "beta", "custom"],
        seed=7,
    )

    assert data.n_dates == 6
    assert data.n_symbols == 4
    assert data.symbols == ["STOCK_0000", "STOCK_0001", "STOCK_0002", "STOCK_0003"]
    assert set(data.fields) == {"close", "volume", "returns", "market_cap", "momentum_1m", "volatility_1m", "rsi_14", "beta", "custom"}
    assert all(len(row) == 4 for rows in data.fields.values() for row in rows)


def test_market_data_frame_missing_column_returns_zeros():
    data = _small_data()

    assert data.get("missing") == []
    assert data.column("close", 1) == [11.0, 18.0, 33.0]
    assert data.column("close", 99) == [0.0, 0.0, 0.0]


def test_expression_evaluator_covers_supported_functions():
    data = _small_data()
    evaluator = LocalExpressionEvaluator()
    expressions = [
        "rank(close)",
        "zscore(close)",
        "ts_zscore(close, 2)",
        "ts_rank(close, 3)",
        "ts_decay_linear(close, 3)",
        "ts_mean(close, 2)",
        "ts_std_dev(close, 2)",
        "ts_delta(close, 2)",
        "ts_sum(close, 2)",
        "ts_min(close, 2)",
        "ts_max(close, 2)",
        "ts_corr(close, volume, 3)",
        "group_rank(close, sector)",
        "group_neutralize(close, sector)",
        "winsorize(close, 2)",
        "normalize(close)",
        "abs(subtract(close, 20))",
        "neg(close)",
        "reverse(close)",
        "log(close)",
        "sign(subtract(close, 20))",
        "power(close, 2)",
        "multiply(close, volume)",
        "divide(close, volume)",
        "greater(close, volume)",
        "if_else(greater(close, 20), close, volume)",
        "unknown_func(close)",
        "price + return * 2",
        "-close",
    ]

    for expression in expressions:
        result = evaluator.evaluate(expression, data)
        assert len(result) == data.n_dates, expression
        assert all(len(row) == data.n_symbols for row in result), expression
        assert all(math.isfinite(value) for row in result for value in row), expression


def test_expression_evaluator_rejects_invalid_inputs():
    evaluator = LocalExpressionEvaluator()
    data = _small_data()

    for expression in ["", "rank(close", "rank("]:
        try:
            evaluator.evaluate(expression, data)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for {expression!r}")

    with pytest.raises(ValueError, match="expression too long"):
        evaluator.evaluate("x" * 501, data, max_length=500)


def test_portfolio_constructor_and_metrics_computer():
    alphas = [[0.1, 0.5, -0.2], [0.3, -0.1, 0.7], [0.0, 0.4, -0.3]]
    returns = [[0.01, -0.02, 0.03], [0.02, 0.01, -0.01], [-0.01, 0.02, 0.01]]
    weights = PortfolioConstructor(long_quantile=0.34, short_quantile=0.34).construct(alphas)

    assert len(weights) == 3
    assert all(abs(sum(day)) < 1e-10 for day in weights)
    assert PortfolioConstructor().construct([[]]) == [[]]

    metrics = MetricsComputer().compute(weights, returns, alphas=alphas)
    data = metrics.to_dict()
    assert data["n_dates"] == 3
    assert data["n_symbols"] == 3
    assert "sharpe" in data
    assert "margin" in data

    empty = MetricsComputer().compute([[0.0]], [[0.0]])
    assert isinstance(empty, BacktestMetrics)
    assert empty.sharpe == 0.0


def test_local_backtest_engine_evaluate_batch_rank_and_cache():
    engine = LocalBacktestEngine(seed=1, n_dates=8, n_symbols=5)
    data = _small_data()

    ok = engine.evaluate("rank(ts_delta(close, 1))", data=data)
    bad = engine.evaluate("rank(", data=data)
    batch = engine.batch_evaluate(["rank(close)", "rank("], data=data)
    ranked = engine.rank_expressions(["rank(close)", "rank("], data=data, top_n=1)

    assert ok["ok"] is True
    assert ok["expression"] == "rank(ts_delta(close, 1))"
    assert len(ok["pass_reasons"]) == 5
    assert bad["ok"] is False
    assert bad["pass_local"] is False
    assert len(batch) == 2
    assert len(ranked) == 1
    assert ranked[0]["ok"] is True
    assert "close" in engine.supported_fields
    assert "rank" in engine.supported_operators
    assert "reverse" in engine.supported_operators
    assert "multiply" in engine.supported_operators

    for i in range(10):
        engine.get_data(f"k{i}")
    assert len(engine._cache) <= engine._cache_maxsize


def test_math_helpers_cover_degenerate_and_normal_cases():
    assert _safe_mean([]) == 0.0
    assert _safe_stdev([1.0]) == 0.0
    assert _safe_corr([1, 2], [1, 2]) == 0.0
    assert _safe_corr([1, 2, 3], [1, 2, 3]) > 0.9
    assert _spearman_r([3, 1, 2], [30, 10, 20]) > 0.9
    assert _rank_values([30, 10, 20]) == [1.0, 0.0, 0.5]
    assert _cumsum([1, -2, 3]) == [1.0, -1.0, 2.0]
