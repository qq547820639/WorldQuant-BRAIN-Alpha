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
