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


class _DuplicateGenerator:
    def generate(self, count, *, dataset_id=""):
        return [
            Candidate(alpha_id="a1", expression="rank(close)", family="Value", hypothesis="base"),
            Candidate(alpha_id="a2", expression=" rank( close ) ", family="Value", hypothesis="same"),
            Candidate(alpha_id="a3", expression="rank(open)", family="Value", hypothesis="different"),
        ][:count]


class _RefillGenerator:
    def __init__(self):
        self.calls = 0
        self.requests = []

    def generate(self, count, *, dataset_id=""):
        self.calls += 1
        self.requests.append(count)
        if self.calls == 1:
            return [
                Candidate(alpha_id="a1", expression="rank(close)", family="Value", hypothesis="base"),
                Candidate(alpha_id="a2", expression=" rank( close ) ", family="Value", hypothesis="same"),
            ][:count]
        return [
            Candidate(alpha_id=f"a_refill_{self.calls}", expression=f"rank(open_{self.calls})", family="Value", hypothesis="refill")
        ][:count]


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

    assert len(generator.calls) >= 1 and generator.calls[0] == (3, "fundamental6") and all(ds == "fundamental6" for _, ds in generator.calls)
    assert [candidate.alpha_id for candidate in candidates] == ["a1"]
    assert attached == [("a1", "ag_1")]


def test_generation_phase_service_deduplicates_similar_expressions():
    service = GenerationPhaseService(
        generator=_DuplicateGenerator(),
        max_candidates=3,
        max_expression_similarity=0.9,
    )

    candidates = service.generate()

    assert [candidate.alpha_id for candidate in candidates] == ["a1", "a3"]


def test_generation_phase_service_refills_after_deduplication():
    generator = _RefillGenerator()
    service = GenerationPhaseService(
        generator=generator,
        max_candidates=2,
        max_expression_similarity=0.9,
        max_generation_attempts=3,
    )

    candidates = service.generate()

    assert [candidate.alpha_id for candidate in candidates] == ["a1", "a_refill_2"]
    assert generator.calls == 2
    assert generator.requests == [2, 2]
