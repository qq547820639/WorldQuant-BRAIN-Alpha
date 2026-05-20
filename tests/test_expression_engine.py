from brain_alpha_ops.research.expression_engine import ExpressionEngine, validate_expression


def test_expression_engine_validates_official_field_and_operator_scope():
    engine = ExpressionEngine(
        allowed_fields={"close", "volume"},
        allowed_operators={"rank", "ts_delta", "ts_corr"},
    )

    report = engine.validate("rank(ts_delta(close, 20))")

    assert report.valid is True
    assert report.blocked is False
    assert report.parsed is True
    assert "time_series" in report.semantic_tags
    assert "cross_sectional" in report.semantic_tags
    assert report.complexity_score > 0
    assert report.to_dict()["schema_version"] == "expression-engine-report.v1"


def test_expression_engine_blocks_parse_and_unknown_symbols():
    engine = ExpressionEngine(
        allowed_fields={"close"},
        allowed_operators={"rank"},
    )

    report = engine.validate("rank(ts_delta(open, 20)")

    assert report.valid is False
    assert report.blocked is True
    codes = {issue.code for issue in report.issues}
    assert "parse_error" in codes
    assert "unknown_fields" in codes
    assert "unknown_operators" in codes


def test_expression_engine_warns_on_complexity_without_blocking_warnings():
    engine = ExpressionEngine(
        allowed_fields={"close", "volume"},
        allowed_operators={"rank", "ts_corr"},
        max_window=30,
    )

    payload = engine.validate("rank(ts_corr(close, volume, 120))").to_dict()

    assert payload["valid"] is True
    assert payload["blocked"] is False
    assert "long_horizon" in payload["semantic_tags"]
    assert any(issue["code"] == "window_too_long" for issue in payload["issues"])


def test_validate_expression_function_returns_serializable_report():
    payload = validate_expression(
        "close",
        allowed_fields={"close"},
        allowed_operators={"rank"},
        mode="local",
    )

    assert payload["valid"] is True
    assert payload["operators"] == []
    assert payload["fields"] == ["close"]
