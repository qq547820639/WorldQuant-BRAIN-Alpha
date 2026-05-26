from types import SimpleNamespace

from brain_alpha_ops.research.dataset_selection import DatasetSelectionService


class Generator:
    def __init__(self):
        self.dataset = ""

    def set_dataset(self, dataset_id):
        self.dataset = dataset_id


class Selector:
    available_datasets: list[str] = ["ds_a"]

    def __init__(self):
        self.calls = []

    def select(self, strategy, **kwargs):
        self.calls.append((strategy, kwargs))
        if strategy in {"fixed", "locked", "specific"}:
            return [item for item in kwargs.get("dataset_ids", []) if item in self.available_datasets]
        return ["ds_a"]


class EmptySelector:
    available_datasets: list[str] = []


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


def test_dataset_selection_uses_configured_dataset_for_fixed_strategy():
    generator = Generator()
    settings = SimpleNamespace(dataset="ds_a")
    selector = Selector()

    result = DatasetSelectionService(
        selector=selector,
        generator=generator,
        settings=settings,
        strategy="fixed",
    ).select()

    assert result.should_continue is True
    assert result.dataset_id == "ds_a"
    assert selector.calls == [("fixed", {"dataset_ids": ["ds_a"]})]


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
