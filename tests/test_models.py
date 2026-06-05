from brain_alpha_ops.models import Candidate


def test_candidate_from_dict_preserves_unknown_fields():
    candidate = Candidate.from_dict(
        {
            "alpha_id": "a1",
            "expression": "rank(close)",
            "family": "Momentum",
            "hypothesis": "test",
            "custom_label": "keep-me",
            "nested": {"x": 1},
        }
    )

    assert candidate.extra_fields == {
        "custom_label": "keep-me",
        "nested": {"x": 1},
    }
    payload = candidate.to_dict()
    assert payload["extra_fields"]["custom_label"] == "keep-me"


def test_candidate_from_dict_retains_explicit_extra_fields_payload():
    candidate = Candidate.from_dict(
        {
            "alpha_id": "a2",
            "expression": "rank(volume)",
            "family": "Volume",
            "hypothesis": "test",
            "extra_fields": {"source": "manual"},
            "custom_label": "keep-me",
        }
    )

    assert candidate.extra_fields == {
        "source": "manual",
        "custom_label": "keep-me",
    }
    payload = candidate.to_dict()
    assert payload["extra_fields"]["source"] == "manual"


def test_candidate_from_dict_prefers_explicit_extra_fields_on_collision():
    candidate = Candidate.from_dict(
        {
            "alpha_id": "a3",
            "expression": "rank(close)",
            "family": "Momentum",
            "hypothesis": "test",
            "extra_fields": {"custom_label": "explicit"},
            "custom_label": "overflow",
        }
    )

    assert candidate.extra_fields["custom_label"] == "explicit"


def test_candidate_copies_mutable_list_inputs():
    data_fields = ["close"]
    operators = ["rank"]
    source_tags = ["manual"]

    candidate = Candidate(
        alpha_id="a4",
        expression="rank(close)",
        family="Momentum",
        hypothesis="test",
        data_fields=data_fields,
        operators=operators,
        source_tags=source_tags,
    )

    data_fields.append("open")
    operators.append("ts_mean")
    source_tags.append("generated")

    assert candidate.data_fields == ["close"]
    assert candidate.operators == ["rank"]
    assert candidate.source_tags == ["manual"]
