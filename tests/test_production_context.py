from brain_alpha_ops.research.production_context import (
    build_production_context,
    eligible_strategy_profiles,
    safe_field_ids,
)


def test_eligible_strategy_profiles_filter_advanced_only_profiles():
    basic = eligible_strategy_profiles({"account_tier": "BASIC"})
    advanced = eligible_strategy_profiles({"account_tier": "ADVANCED"})

    assert basic
    assert len(advanced) > len(basic)
    assert all(not profile.get("min_tier") for profile in basic)
    assert any(profile.get("min_tier") == "ADVANCED" for profile in advanced)


def test_safe_field_ids_excludes_vector_fields():
    fields = [
        {"id": "close", "type": "MATRIX"},
        {"name": "news_vector", "type": "VECTOR"},
        {"name": "volume", "type": ""},
        {"id": "", "type": "MATRIX"},
    ]

    assert safe_field_ids(fields) == ["close", "volume"]


def test_build_production_context_summarizes_profile_and_safe_fields():
    context = build_production_context(
        {"account_tier": "ADVANCED"},
        [{"id": "close", "type": "MATRIX"}, {"id": "embedding", "type": "VECTOR"}],
        config=None,
    )

    assert context["account_tier"] == "ADVANCED"
    assert context["eligible_profiles_count"] == len(context["eligible_profiles"])
    assert context["safe_fields"] == ["close"]
    assert context["safe_field_count"] == 1
    assert context["neutralization_available"] == "SUBINDUSTRY | SECTOR | MARKET"
