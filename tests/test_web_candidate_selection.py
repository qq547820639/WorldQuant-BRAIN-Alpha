from brain_alpha_ops.web_candidate_selection import (
    candidate_from_payload,
    official_alpha_id,
    passed_candidates_from_payload,
)


class Store:
    def __init__(self, rows):
        self.rows = rows

    def get(self, job_id):
        return self.rows.get(job_id)


def test_candidate_from_payload_prefers_inline_candidate_and_falls_back_to_job_pools():
    inline = {"alpha_id": "inline"}
    store = Store(
        {
            "job_1": {
                "result": {
                    "candidates": [{"alpha_id": "a1"}],
                    "summary": {"passed_candidates": [{"alpha_id": "a2"}]},
                },
                "progress": {"data": {"candidates": [{"alpha_id": "a3"}], "passed_candidates": [{"alpha_id": "a4"}]}},
            }
        }
    )

    assert candidate_from_payload({"candidate": inline}, store) is inline
    assert candidate_from_payload({"job_id": "job_1", "alpha_id": "a4"}, store) == {"alpha_id": "a4"}
    assert candidate_from_payload({"job_id": "job_1", "alpha_id": "missing"}, store) == {}


def test_passed_candidates_from_payload_filters_deduplicates_and_job_fallback():
    store = Store(
        {
            "job_1": {
                "result": {
                    "summary": {
                        "passed_candidates": [
                            {"alpha_id": "a1", "gate": {"submission_ready": True}},
                            {"alpha_id": "a1", "gate": {"submission_ready": True}},
                        ]
                    },
                    "candidates": [
                        {"alpha_id": "a2", "official_alpha_id": "off_2", "metrics": {"pass_fail": "PASS"}},
                        {"alpha_id": "a3", "metrics": {"pass_fail": "FAIL"}},
                    ],
                },
                "progress": {"data": {}},
            }
        }
    )

    rows = passed_candidates_from_payload({"job_id": "job_1"}, store)

    assert [row["alpha_id"] for row in rows] == ["a1", "a2"]
    assert official_alpha_id(rows[1]) == "off_2"
