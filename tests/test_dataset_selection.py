from types import SimpleNamespace

from brain_alpha_ops.research.dataset_selection import DatasetSelectionService


class Generator:
    def __init__(self):
        self.dataset = ""

    def set_dataset(self, dataset_id):
        self.dataset = dataset_id


class Selector:
    available_datasets = ["ds_a"]

    def select(self, strategy):
        return ["ds_a"]


class EmptySelector:
    available_datasets = []


class Loader:
    def get_datasets(self):
        return [SimpleNamespace(id="loader_ds")]


def test_dataset_selection_uses_selector_and_updates_settings():
    generator = Generator()
    settings = SimpleNamespace(dataset="")

    result = DatasetSelectionService(
        selector=Selector(),
        generator=generator,
        settings=settings,
        strategy="rotate",
    ).select()

    assert result.should_continue is True
    assert result.dataset_id == "ds_a"
    assert generator.dataset == "ds_a"
    assert settings.dataset == "ds_a"


def test_dataset_selection_falls_back_to_loader_and_emits_event():
    generator = Generator()
    settings = SimpleNamespace(dataset="")
    events = []

    result = DatasetSelectionService(
        loader=Loader(),
        generator=generator,
        settings=settings,
        event=lambda *args, **kwargs: events.append((args, kwargs)),
    ).select()

    assert result.should_continue is True
    assert result.dataset_id == "loader_ds"
    assert events[0][0][0] == "dataset_fallback_loader"


def test_dataset_selection_breaks_without_sources():
    result = DatasetSelectionService(
        generator=Generator(),
        settings=SimpleNamespace(dataset=""),
    ).select()

    assert result.should_break is True
    assert result.level == "ERROR"
