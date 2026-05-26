from brain_alpha_ops.scoring.visualization import build_score_visualization_payload, summarize_score_attribution


def test_score_visualization_payload_flattens_attribution_tree():
    scorecard = {
        "total_score": 80,
        "decision_band": "optimize_before_submit",
        "attribution_tree": {
            "name": "total_score",
            "score": 80,
            "weight": 1.0,
            "contribution": 80,
            "children": [
                {"name": "prior_score", "score": 70, "weight": 0.3, "contribution": 21, "children": []},
                {"name": "empirical_score", "score": 90, "weight": 0.45, "contribution": 40.5, "children": []},
            ],
        },
        "top_failures": [{"severity": "warning", "item": "turnover", "reason": "high"}],
        "improvement_hints": ["adjust decay"],
    }

    payload = build_score_visualization_payload(scorecard)
    summary = summarize_score_attribution(scorecard)

    assert payload["ok"] is True
    assert payload["node_count"] == 3
    assert payload["contribution_bars"][0]["name"] == "total_score"
    assert summary["top_failures"][0]["item"] == "turnover"
    assert summary["visualization"]["decision_band"] == "optimize_before_submit"
