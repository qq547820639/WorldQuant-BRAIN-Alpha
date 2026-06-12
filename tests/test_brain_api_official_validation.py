from brain_alpha_ops.brain_api.official_validation import OfficialExpressionValidator


def test_official_expression_validator_blocks_every_unknown_expression_symbol():
    validator = OfficialExpressionValidator()

    result = validator.validate_expression(
        "rank(ts_fake(custom_field, 20))",
        {},
        known_operators={"rank"},
        known_fields={"close"},
    )

    assert result["status"] == "FAIL"
    assert "Unknown fields: custom_field" in result["errors"]
    assert "Unknown operators: ts_fake" in result["errors"]


def test_official_expression_validator_accepts_group_context_identifier():
    validator = OfficialExpressionValidator()

    result = validator.validate_expression(
        "group_neutralize(rank(close), subindustry)",
        {},
        known_operators={"rank", "group_neutralize"},
        known_fields={"close"},
    )

    assert result["status"] == "PASS"
    assert result["errors"] == []
