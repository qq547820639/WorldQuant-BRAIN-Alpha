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
