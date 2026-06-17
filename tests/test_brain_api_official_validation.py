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


# ── patch_properties tests ──────────────────────────────────────────────


def test_patch_properties_builds_correct_patch_body():
    """patch_properties sends only non-None properties via PATCH."""
    from brain_alpha_ops.brain_api.official import OfficialBrainAPI
    from brain_alpha_ops.config_models import OfficialAPIConfig
    import json

    captured = {}

    class FakeResponse:
        headers = {"Content-Type": "application/json"}
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self):
            return json.dumps({"id": "abc123", "name": "renamed_alpha"}).encode()

    def fake_open(req, timeout):
        captured["method"] = req.get_method()
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode()) if req.data else None
        return FakeResponse()

    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test"),
        token="token",
    )
    api._open = fake_open

    result = api.patch_properties("abc123", name="renamed_alpha", decay=5)

    assert captured["method"] == "PATCH"
    assert "/alphas/abc123" in captured["url"]
    assert captured["body"] == {"name": "renamed_alpha", "decay": 5}
    assert result["id"] == "abc123"


def test_patch_properties_rejects_empty_alpha_id():
    from brain_alpha_ops.brain_api.official import OfficialBrainAPI
    from brain_alpha_ops.brain_api.base import BrainAPIError
    from brain_alpha_ops.config_models import OfficialAPIConfig

    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test"),
        token="token",
    )

    try:
        api.patch_properties("", name="test")
        assert False, "Should have raised BrainAPIError"
    except BrainAPIError as exc:
        assert "alpha_id is required" in str(exc)


def test_patch_properties_rejects_empty_body():
    from brain_alpha_ops.brain_api.official import OfficialBrainAPI
    from brain_alpha_ops.brain_api.base import BrainAPIError
    from brain_alpha_ops.config_models import OfficialAPIConfig

    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test"),
        token="token",
    )

    try:
        api.patch_properties("abc123")
        assert False, "Should have raised BrainAPIError"
    except BrainAPIError as exc:
        assert "at least one property" in str(exc)


def test_patch_properties_sends_camelcase_for_official_fields():
    """BRAIN API uses camelCase for unitHandling, nanHandling, etc."""
    from brain_alpha_ops.brain_api.official import OfficialBrainAPI
    from brain_alpha_ops.config_models import OfficialAPIConfig
    import json

    captured = {}

    class FakeResponse:
        headers = {"Content-Type": "application/json"}
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self):
            return json.dumps({"id": "x"}).encode()

    def fake_open(req, timeout):
        captured["body"] = json.loads(req.data.decode()) if req.data else None
        return FakeResponse()

    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test"),
        token="token",
    )
    api._open = fake_open

    api.patch_properties("x", unit_handling="standard", nan_handling="subtract_mean")

    assert captured["body"] == {"unitHandling": "standard", "nanHandling": "subtract_mean"}
