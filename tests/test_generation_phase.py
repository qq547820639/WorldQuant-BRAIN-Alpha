from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.generation_phase import GenerationPhaseService


class _Generator:
    def __init__(self):
        self.calls = []

    def generate(self, count, *, dataset_id=""):
        self.calls.append((count, dataset_id))
        return [
            Candidate(
                alpha_id="a1",
                expression="rank(close)",
                family="Value",
                hypothesis="test",
            )
        ]


def test_generation_phase_service_attaches_assistant_guidance():
    generator = _Generator()
    attached = []
    service = GenerationPhaseService(
        generator=generator,
        max_candidates=3,
        dataset_id="fundamental6",
        attach_assistant_guidance=lambda candidate, guidance: attached.append((candidate.alpha_id, guidance["digest"])),
    )

    candidates = service.generate(assistant_guidance={"digest": "ag_1"})

    assert generator.calls == [(3, "fundamental6")]
    assert [candidate.alpha_id for candidate in candidates] == ["a1"]
    assert attached == [("a1", "ag_1")]
