from brain_alpha_ops.research.research_cycle_orchestrator import ResearchCycleOrchestrator


def test_research_cycle_orchestrator_stops_at_max_cycles():
    orchestrator = ResearchCycleOrchestrator(run_forever=False, max_cycles=2, should_stop=lambda: False)

    assert orchestrator.next_cycle().cycle == 1
    assert orchestrator.next_cycle().cycle == 2
    decision = orchestrator.next_cycle()

    assert decision.should_run is False
    assert decision.reason == "max_cycles_reached"


def test_research_cycle_orchestrator_honors_stop_callback():
    orchestrator = ResearchCycleOrchestrator(run_forever=True, max_cycles=1, should_stop=lambda: True)

    decision = orchestrator.next_cycle()

    assert decision.should_run is False
    assert decision.reason == "stopped"
