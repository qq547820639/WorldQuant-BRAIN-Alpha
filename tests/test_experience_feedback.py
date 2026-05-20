from brain_alpha_ops.research.experience_feedback import ExperienceFeedbackService


class Generator:
    def __init__(self):
        self.guidance = None

    def set_experience_guidance(self, patterns):
        self.guidance = patterns


class Memory:
    def __init__(self, _storage_dir):
        pass

    def generation_guidance(self, top_n):
        return {"sample_size": 4, "top_operators": ["rank"], "preferred_windows": [20]}


def test_experience_feedback_skips_non_feedback_cycles(tmp_path):
    generator = Generator()

    result = ExperienceFeedbackService(
        storage_dir=str(tmp_path),
        generator=generator,
    ).apply(4)

    assert result.applied is False
    assert result.reason == "not_feedback_cycle"
    assert generator.guidance is None


def test_experience_feedback_uses_winning_patterns(tmp_path):
    generator = Generator()
    events = []

    result = ExperienceFeedbackService(
        storage_dir=str(tmp_path),
        generator=generator,
        event=lambda *args, **kwargs: events.append((args, kwargs)),
        winning_patterns=lambda *args, **kwargs: {"sample_size": 2, "top_operators": ["ts_rank"]},
    ).apply(5)

    assert result.applied is True
    assert result.source == "winning_patterns"
    assert generator.guidance["top_operators"] == ["ts_rank"]
    assert events[0][0][0] == "experience_feedback"


def test_experience_feedback_falls_back_to_memory_guidance(tmp_path):
    generator = Generator()

    result = ExperienceFeedbackService(
        storage_dir=str(tmp_path),
        generator=generator,
        memory_factory=Memory,
        winning_patterns=lambda *args, **kwargs: {"sample_size": 0},
    ).apply(5)

    assert result.applied is True
    assert result.source == "research_memory"
    assert generator.guidance["top_operators"] == ["rank"]
