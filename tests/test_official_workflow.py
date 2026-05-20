from brain_alpha_ops.research.official_workflow import OfficialWorkflowService


def test_official_workflow_facade_delegates_calls():
    calls = []
    service = OfficialWorkflowService(
        validate_for_open_backtest_slots=lambda *args, **kwargs: calls.append(("validate", args, kwargs)) or ["candidate"],
        fill_backtest_slots=lambda *args, **kwargs: calls.append(("fill", args, kwargs)),
        poll_due_backtests=lambda *args, **kwargs: calls.append(("poll", args, kwargs)) or 2,
        finalization_service_factory=lambda: {"finalizer": True},
    )

    assert service.validate_slots(1, phase="validation") == ["candidate"]
    service.fill_slots(2)
    assert service.poll_due(3) == 2
    assert service.finalization_service() == {"finalizer": True}
    assert [call[0] for call in calls] == ["validate", "fill", "poll"]
